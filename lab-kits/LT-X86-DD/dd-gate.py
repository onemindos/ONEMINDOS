#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Daily-driver gate (#234): one command that runs the definition-of-done checks for living on a OneMind
box, and writes one pass/fail evidence file with timings. It runs on a CONTROLLER (your Mac or the lab
box), never on the box under test, and talks to the box over HTTPS and SSH. Python standard library only.

  dd-gate.py run --host root@BOX --base-url https://BOX --ca box-ca.pem --token-file tok --out evidence/
  dd-gate.py run ... --stage install,portscan      run only some stages
  dd-gate.py plan                                  list the stages and how each is judged

Stages (id: how it is judged):
  install    runs: the API answers over TLS with the box CA, time-to-ready, Debian 13, read-only root, RAUC slot good
  passkey    runs: the owner has at least one passkey registered (registering one is a human step: PENDING until done)
  rollback   ingests the G1 kit's result.json (lab-kits/G1/g1-run.py): every update and forced-rollback step PASS
  powerpull  ingests the g1-power.py results file: --cycles passes (default 20), no failure
  portscan   runs: TCP connect scan from the controller; only the allowed ports may be open
  restore    ingests the restore-drill result (test/restore-drill): PASS inside the 60 minute budget
  load       runs: test/perf/perf.py load on the box, then its budget check
The gate never calls a stage PASS without evidence. A stage with no evidence yet is PENDING (exit 3),
a stage that ran and missed is FAIL (exit 1), all PASS is exit 0, bad usage is exit 2.
"""
import argparse, concurrent.futures, json, os, re, shlex, socket, ssl, subprocess, sys, time, urllib.error, urllib.request

KIT = "onemind.dd-gate/1"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
STAGES = ["install", "passkey", "rollback", "powerpull", "portscan", "restore", "load"]
DEFAULT_ALLOWED = [22, 80, 443]
# The ports a hub could leak by mistake: well-known range plus the services in the image.
EXTRA_PORTS = [2379, 2380, 4222, 5432, 6443, 8080, 8222, 9100, 10250, 10248, 30000, 32767]
G1_SSH_RESULT = "/data/onemind-lab/g1/result.json"
RESTORE_BUDGET_S = 3600
P, F, W = "PASS", "FAIL", "PENDING"


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def scrub(text, *secrets):
    """Evidence goes in a public repo: mask addresses, MACs, mails, home paths and the box name."""
    for s in secrets:
        if s:
            text = text.replace(s, "<box>")
    for pat, rep in ((r"([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", "<mac>"), (r"\b(\d{1,3}\.){3}\d{1,3}\b", "<ip>"),
                     (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}", "<email>"), (r"/(Users|home)/[A-Za-z0-9._-]+", "/<home>"),
                     (r"[A-Za-z0-9.-]+\.ts\.net", "<tailnet-name>")):
        text = re.sub(pat, rep, text)
    return text


class Ctx:
    def __init__(self, a):
        self.a = a
        self.host = a.host
        self.addr = (a.scan_host or (a.host.split("@")[-1] if a.host else "") or
                     (re.sub(r"^https?://", "", a.base_url or "").split("/")[0].split(":")[0]))

    def ssh(self, cmd, timeout=120):
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
        if os.environ.get("DD_SSH_KEY"):
            argv += ["-i", os.environ["DD_SSH_KEY"]]
        return self._run(argv + [self.host, cmd], timeout)

    def scp_to(self, src, dst):
        argv = ["scp", "-q", "-o", "BatchMode=yes"] + (["-i", os.environ["DD_SSH_KEY"]] if os.environ.get("DD_SSH_KEY") else [])
        return self._run(argv + [src, f"{self.host}:{dst}"], 120)

    @staticmethod
    def _run(argv, timeout):
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            return p.returncode, (p.stdout + p.stderr).strip()
        except (OSError, subprocess.TimeoutExpired) as e:
            return 127, str(e)

    def http(self, path, token=None, timeout=10):
        ctx = ssl.create_default_context(cafile=self.a.ca) if self.a.ca else ssl.create_default_context()
        req = urllib.request.Request(self.a.base_url.rstrip("/") + path, headers={"Authorization": f"Bearer {token}"} if token else {})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.status, r.read().decode("utf-8", "replace")

    def token(self):
        if self.a.token_file and os.path.exists(self.a.token_file):
            with open(self.a.token_file) as f:
                return f.read().strip()
        return os.environ.get("ONEMIND_TOKEN")


def res(verdict, detail, **extra):
    return dict(verdict=verdict, detail=detail, **extra)


def need(c, *names):
    miss = [n for n in names if not getattr(c.a, n)]
    return f"needs --{', --'.join(m.replace('_', '-') for m in miss)}" if miss else None


def st_install(c):
    m = need(c, "base_url", "host")
    if m:
        return res(W, m)
    t0, last, ready = time.monotonic(), "no answer", None
    while time.monotonic() - t0 <= c.a.ready_timeout:
        try:
            code, _ = c.http("/healthz")
            if code == 200:
                ready = time.monotonic() - t0
                break
            last = f"HTTP {code}"
        except (urllib.error.URLError, OSError, ssl.SSLError) as e:
            last = str(getattr(e, "reason", e))
            if isinstance(e, ssl.SSLError) or "CERTIFICATE" in last.upper():
                return res(F, f"TLS not trusted with the given CA ({scrub(last, c.addr)}): a passkey cannot work either")
        time.sleep(min(5, c.a.ready_timeout))
    if ready is None:
        return res(F, f"/healthz did not answer 200 within {c.a.ready_timeout}s (last: {scrub(last, c.addr)})")
    bad, facts = [], [f"ready after {ready:.1f}s"]
    rc, osr = c.ssh("cat /etc/os-release")
    idv = dict(re.findall(r'^(ID|VERSION_ID)="?([^"\n]*)"?', osr, re.M)) if rc == 0 else {}
    if (idv.get("ID"), idv.get("VERSION_ID")) != ("debian", "13"):
        bad.append(f"base is {idv.get('ID')} {idv.get('VERSION_ID')}, want debian 13 (D-007)")
    else:
        facts.append("debian 13")
    rc, opts = c.ssh("findmnt -no OPTIONS /")
    if rc != 0 or "ro" not in opts.split(","):
        bad.append(f"root is not read-only (findmnt rc={rc}: {opts[:60]})")
    else:
        facts.append("root read-only")
    rc, rauc = c.ssh("rauc status")
    if rc != 0 or not re.search(r"boot status:\s*good", rauc, re.I):
        bad.append(f"RAUC booted slot is not good (rc={rc})")
    else:
        facts.append("rauc slot good")
    return res(F if bad else P, "; ".join(bad or facts), seconds_to_ready=round(ready, 1))


def st_passkey(c):
    m = need(c, "base_url")
    if m:
        return res(W, m)
    tok = c.token()
    if not tok:
        return res(W, "needs --token-file or ONEMIND_TOKEN (the owner token)")
    try:
        code, body = c.http("/v1/auth/passkeys", token=tok)
        data = json.loads(body)
    except (urllib.error.URLError, OSError, ValueError, ssl.SSLError) as e:
        return res(F, f"passkey list failed: {scrub(str(e), c.addr)}")
    items = data if isinstance(data, list) else (data.get("items") or data.get("passkeys") or [])
    if not items:
        return res(W, "no passkey registered yet: register one in the first-run wizard in a browser that trusts the box CA, then re-run")
    return res(P, f"{len(items)} passkey(s) registered for the owner")


def read_json(path):
    with open(path) as f:
        return json.load(f)


def st_rollback(c):
    doc = None
    if c.a.g1_result:
        doc = read_json(c.a.g1_result)
    elif c.host:
        rc, out = c.ssh(f"cat {G1_SSH_RESULT}")
        doc = json.loads(out) if rc == 0 and out.startswith("{") else None
    else:
        return res(W, "needs --g1-result FILE or --host")
    if not doc:
        return res(W, "no G1 result yet: run lab-kits/G1/g1-run.py on the box first (it survives reboots)")
    steps = doc.get("steps", [])
    bad = [s["id"] for s in steps if s.get("verdict") == "FAIL"]
    wait = [s["id"] for s in steps if s.get("verdict") not in ("PASS", "FAIL")]
    if bad:
        return res(F, f"G1 steps failed: {', '.join(bad)}")
    if not steps or wait:
        return res(W, f"{len(wait) or 'all'} G1 step(s) not finished")
    return res(P, f"{len(steps)} update and rollback steps PASS")


def st_powerpull(c):
    if not c.a.power_results:
        return res(W, "needs --power-results (the g1-power.py results file; power pulls are run from the controller)")
    if not os.path.exists(c.a.power_results):
        return res(W, f"{os.path.basename(c.a.power_results)} not found yet")
    with open(c.a.power_results) as f:
        recs = [json.loads(l) for l in f if l.strip()]
    cyc = [r for r in recs if "verdict" in r]
    fails = [r for r in cyc if r["verdict"] != "PASS"]
    if fails:
        return res(F, f"{len(fails)} of {len(cyc)} power pulls did not come back clean")
    if len(cyc) < c.a.cycles:
        return res(W, f"{len(cyc)} of {c.a.cycles} power pulls done, all clean so far")
    return res(P, f"{len(cyc)} of {len(cyc)} power pulls came back with no keyboard", cycles=len(cyc))


def scan(addr, ports, timeout=0.6, workers=128):
    def one(p):
        try:
            with socket.create_connection((addr, p), timeout=timeout):
                return p
        except OSError:
            return None
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        return sorted(p for p in ex.map(one, ports) if p)


def st_portscan(c):
    if not c.addr:
        return res(W, "needs --host, --base-url or --scan-host")
    allowed = set(c.a.allow_ports)
    t0 = time.monotonic()
    open_ports = scan(c.addr, sorted(set(range(1, 1025)) | set(EXTRA_PORTS) | allowed), c.a.scan_timeout)
    dt = round(time.monotonic() - t0, 1)
    extra = [p for p in open_ports if p not in allowed]
    if extra:
        return res(F, f"unexpected open TCP ports: {extra} (allowed {sorted(allowed)})", open=open_ports, scan_seconds=dt)
    if 443 in allowed and 443 not in open_ports:
        return res(F, "443 is closed: the dashboard is not reachable", open=open_ports, scan_seconds=dt)
    return res(P, f"only allowed ports open: {open_ports}", open=open_ports, scan_seconds=dt)


def st_restore(c):
    if not c.a.restore_results:
        return res(W, "needs --restore-results (JSON written by test/restore-drill/drill.py; run it on the lab box with KVM)")
    if not os.path.exists(c.a.restore_results):
        return res(W, "restore result not found yet")
    r = read_json(c.a.restore_results)
    secs = r.get("restore_seconds")
    if r.get("verdict") == "PASS" and isinstance(secs, (int, float)) and secs <= RESTORE_BUDGET_S:
        return res(P, f"whole-box restore verified byte for byte in {secs:.0f}s (budget {RESTORE_BUDGET_S}s)", restore_seconds=secs)
    return res(F, f"restore drill verdict {r.get('verdict')}, {secs}s: {'; '.join(r.get('reasons', []))[:200]}", restore_seconds=secs)


def st_load(c):
    m = need(c, "host")
    if m:
        return res(W, m)
    perf = os.path.join(REPO, "test", "perf", "perf.py")
    budget = os.path.join(REPO, "test", "perf", "budget.json")
    d = "/tmp/dd-gate"
    steps = [(f"mkdir -p {d}", None), (None, (perf, f"{d}/perf.py")), (None, (budget, f"{d}/budget.json")),
             (f"python3 -I {d}/perf.py token --out {d}/tok", None),
             (f"python3 -I {d}/perf.py load --token-file {d}/tok --out {d}/load.json", None),
             (f"python3 -I {d}/perf.py check --budget {d}/budget.json {d}/load.json", "check")]
    t0, out = time.monotonic(), ""
    for cmd, cp in steps:
        rc, out = c.scp_to(*cp) if cmd is None else c.ssh(cmd, timeout=c.a.load_timeout)
        if rc != 0:
            where = cp[1] if cmd is None else cmd.split()[2] if "perf.py" in cmd else cmd
            return res(F, f"step failed ({scrub(where, c.addr)}, rc={rc}): {scrub(out, c.addr)[-200:]}")
    return res(P, f"load run inside the budget ({scrub(out, c.addr)[-120:]})", seconds=round(time.monotonic() - t0, 1))


RUN = dict(install=st_install, passkey=st_passkey, rollback=st_rollback, powerpull=st_powerpull,
           portscan=st_portscan, restore=st_restore, load=st_load)


def run_all(a, only):
    c, rows = Ctx(a), []
    for sid in only:
        t0 = time.monotonic()
        try:
            r = RUN[sid](c)
        except Exception as e:  # a crashed check is a failed check, never a pass
            r = res(F, f"check crashed: {type(e).__name__}: {scrub(str(e), c.addr)}")
        r.update(id=sid, seconds=r.get("seconds", round(time.monotonic() - t0, 1)), at=now())
        r["detail"] = scrub(r["detail"], c.addr, c.host)
        rows.append(r)
        print(f"{sid:<10} {r['verdict']:<7} {r['seconds']:>7}s  {r['detail']}")
    return rows


def summarise(rows):
    n = lambda v: sum(r["verdict"] == v for r in rows)
    ok = bool(rows) and n(P) == len(rows)
    return dict(passed=n(P), failed=n(F), pending=n(W), all_passed=ok)


def write_report(out, rows, a):
    os.makedirs(out, exist_ok=True)
    doc = dict(kit=KIT, finished=now(), device=a.label, summary=summarise(rows), stages=rows)
    with open(os.path.join(out, "dd-gate.json"), "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    lines = [f"<!-- SPDX-License-Identifier: Apache-2.0 -->", f"# Daily-driver gate: {a.label}", "",
             f"Finished {doc['finished']}. Summary: {json.dumps(doc['summary'])}", "",
             "| Stage | Verdict | Seconds | Detail |", "|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['verdict']} | {r['seconds']} | {r['detail'].replace('|', '/')} |" for r in rows]
    lines += ["", "PENDING means no evidence yet, not a pass. The gate never writes a verdict for the founder.", ""]
    with open(os.path.join(out, "DD-GATE.md"), "w") as f:
        f.write("\n".join(lines))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    r = sub.add_parser("run")
    r.add_argument("--host", help="ssh target user@host of the box under test")
    r.add_argument("--base-url", help="https URL of the box dashboard and API")
    r.add_argument("--ca", help="the box CA certificate (PEM) the controller trusts")
    r.add_argument("--token-file")
    r.add_argument("--scan-host", help="address to port-scan (default: the host of --host or --base-url)")
    r.add_argument("--allow-ports", type=lambda s: [int(x) for x in s.split(",") if x], default=DEFAULT_ALLOWED)
    r.add_argument("--g1-result"), r.add_argument("--power-results"), r.add_argument("--restore-results")
    r.add_argument("--cycles", type=int, default=20)
    r.add_argument("--stage", default=",".join(STAGES))
    r.add_argument("--out", default="dd-gate-evidence")
    r.add_argument("--label", default="x86 daily-driver candidate", help="device name for the record, no serial numbers")
    r.add_argument("--ready-timeout", type=float, default=900)
    r.add_argument("--scan-timeout", type=float, default=0.6)
    r.add_argument("--load-timeout", type=float, default=3600)
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        print(__doc__.split("Stages (id")[1].split("The gate never")[0].join(["Stages (id", ""]))
        return 0
    only = [s for s in a.stage.split(",") if s]
    unknown = [s for s in only if s not in STAGES]
    if unknown:
        print(f"unknown stage: {unknown}; known: {STAGES}", file=sys.stderr)
        return 2
    rows = run_all(a, only)
    write_report(a.out, rows, a)
    s = summarise(rows)
    print(json.dumps(s))
    return 1 if s["failed"] else 0 if s["all_passed"] else 3


if __name__ == "__main__":
    sys.exit(main())
