#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""G1 on metal runner (CORE-UPDATE-4, #215): drives the LT-X86-01 sequence on the box and starts the
Pi soak. Run it ON the device, as root, from the test image built with `make fixtures ... HW=1`.

It reuses what already exists: the fixtures' signed bundles (test/qemu/mkfixtures.sh), RAUC and the
image's own health gate. It adds only the sequencing, a resume across reboots and a result file.
The verdict source for every step is the gate's own log (/data/onemind/gate.log), parsed the way
test/qemu/run-tests.py parses it. The kit never asserts that G1 passed: that is the founder's call,
written in G1-RECORD.md (template: G1-RECORD.template.md).

  g1-run.py run [--rounds N]     start, or resume after a reboot (re-run it after every reboot)
  g1-run.py run --dry-run        print the plan and the commands; change nothing
  g1-run.py status | report      show progress | write G1-RECORD.md from result.json
  g1-run.py soak-start|soak-sample   start the 30-day soak record (4 GB Pi) | add one sample
  g1-run.py autoresume on|off    a systemd unit that resumes `run` after each boot (optional)

Exit codes: 0 done or step started, 3 waiting for the gate (re-run in a minute), 1 a check failed, 2 usage or setup.
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, time, urllib.request

KIT = "onemind.g1-kit/1"
GATE_RE = re.compile(r"HEALTH-GATE: \S+ RESULT (\S+) slot=(\w) version=([^\s;]+)([^\n]*)")  # = run-tests.py GATE
E = os.environ.get
ROOT = E("ONEMIND_LAB_ROOT", "/data/onemind-lab/g1")
GATE_LOG = E("ONEMIND_GATE_LOG", "/data/onemind/gate.log")
PENDING = E("ONEMIND_PENDING", "/data/onemind/pending")
CMDLINE = E("ONEMIND_CMDLINE", "/proc/cmdline")
PROC = E("ONEMIND_PROC", "/proc")
UNIT_DIR = E("ONEMIND_UNIT_DIR", "/etc/systemd/system")
HEALTHZ = E("ONEMIND_HEALTHZ_URL", "http://127.0.0.1:10248/healthz")
STATE_DB = E("ONEMIND_STATE_DB", "/var/lib/rancher/k3s/server/db/state.db")
BUNDLES = [p for p in ("/run/onemind-test/bundles", "/data/bundles") if os.path.isdir(p)][:1] or ["/run/onemind-test/bundles"]
NEED = ["good", "wrong-key", "plain-good", "bad-k3s", "bad-noagent", "bad-boot", "bad-hang"]
SOAK_DAYS = 30


def wr(path, text, mode="w"):
    with open(path, mode) as f:
        f.write(text)


def rd(path):
    with open(path) as f:
        return f.read()


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sh(*cmd, timeout=3600):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def slot():
    m = re.search(r"rauc\.slot=([A-Z])", rd(CMDLINE)) if os.path.exists(CMDLINE) else None
    return m.group(1) if m else None


def other(s):
    return "B" if s == "A" else "A"


def gate_size():
    return os.path.getsize(GATE_LOG) if os.path.exists(GATE_LOG) else 0


def gate_since(off):
    if not os.path.exists(GATE_LOG):
        return "", []
    with open(GATE_LOG, "rb") as f:
        f.seek(off)
        txt = f.read().decode("utf-8", "replace")
    return txt, [(m.group(1), m.group(2), m.group(3), m.group(4)) for m in GATE_RE.finditer(txt)]


def healthz():
    try:
        with urllib.request.urlopen(HEALTHZ, timeout=5) as r:
            return r.read().decode().strip()[:40]
    except Exception as e:  # evidence only; the gate's decision is the verdict
        return f"unreachable ({type(e).__name__})"


def plan(rounds):
    p = [dict(id="refuse-wrong-key", kind="refuse", bundle="wrong-key", expect="install refused (signature), nothing written"),
         dict(id="refuse-plain-good", kind="refuse", bundle="plain-good", expect="install refused (plain format not allowed)"),
         dict(id="good-commit", kind="commit", bundle="good", expect="other slot boots, gate mark-good (health-gated commit)"),
         dict(id="reboot-committed", kind="confirm", bundle=None, expect="second reboot: committed-boot, no trial")]
    for b, k in (("bad-k3s", "markbad"), ("bad-noagent", "markbad"), ("bad-boot", "fellback"), ("bad-hang", "fellback")):
        p.append(dict(id="bad-" + b[4:], kind=k, bundle=b,
                      expect="gate mark-bad, back to old slot" if k == "markbad" else "3 boot attempts, GRUB or firmware falls back"))
    p += [dict(id=f"rollback-{i:02d}", kind="markbad", bundle="bad-k3s", expect="chaos release rolled back, old slot committed")
          for i in range(1, rounds + 1)]
    return p


def preflight(bundles, need):
    c = [("root", os.geteuid() == 0 or bool(E("ONEMIND_LAB_NOROOT")), "needs root"), ("rauc", bool(shutil.which("rauc")), "rauc on PATH"),
         ("systemctl", bool(shutil.which("systemctl")), "systemctl on PATH"),
         ("booted_slot", slot() is not None, f"rauc.slot= in {CMDLINE}"),
         ("no_trial_pending", not (os.path.exists(PENDING) and os.path.getsize(PENDING)), f"{PENDING} must be empty: wait for the gate"),
         ("gate_log", os.path.exists(GATE_LOG), f"{GATE_LOG} exists (the gate has run once)")]
    for n in need:
        c.append((f"bundle_{n}", os.path.isfile(os.path.join(bundles, n + ".raucb")), f"{bundles}/{n}.raucb"))
    return [dict(check=n, ok=bool(ok), detail=d) for n, ok, d in c]


def device():
    def rdq(p):
        try:
            return rd(p).strip("\0\n ")
        except OSError:
            return None
    mem = re.search(r"MemTotal:\s+(\d+)", rdq(f"{PROC}/meminfo") or "")
    rc, rv = sh("rauc", "--version")
    return dict(model=rdq("/proc/device-tree/model") or rdq("/sys/class/dmi/id/product_name"), arch=os.uname().machine,
                kernel=os.uname().release, mem_total_mib=int(mem.group(1)) // 1024 if mem else None,
                rauc=rv.strip().splitlines()[0] if rc == 0 and rv.strip() else None,
                os_version=next((l.split("=", 1)[1].strip('"') for l in (rdq("/usr/lib/os-release") or "").splitlines()
                                 if l.startswith("ONEMIND_VERSION=")), None))


class Run:
    def __init__(self, a):
        self.a, self.path = a, os.path.join(a.root, "result.json")
        os.makedirs(os.path.join(a.root, "evidence"), exist_ok=True)

    def load(self):
        if os.path.exists(self.path):
            return json.loads(rd(self.path))
        return None

    def save(self, st):
        st["updated"] = now()
        done = [s for s in st["steps"] if s["verdict"] in ("PASS", "FAIL")]
        st["summary"] = dict(passed=sum(s["verdict"] == "PASS" for s in st["steps"]), failed=sum(s["verdict"] == "FAIL" for s in st["steps"]),
                             pending=len(st["steps"]) - len(done), all_automated_checks_passed=bool(st["steps"]) and all(s["verdict"] == "PASS" for s in st["steps"]),
                             g1_verdict="NOT ASSERTED BY THE KIT: the founder decides in G1-RECORD.md",
                             manual_still_open=["20 of 20 power pulls during the trial still boot (lab-kits/LT-X86-02, PP-10)",
                                                "no keyboard input after any reboot (you watch the screen)",
                                                "Pi 5 4 GB soak (soak-start; 30 days)"])
        tmp = self.path + ".new"
        wr(tmp, json.dumps(st, indent=1))
        os.replace(tmp, self.path)

    def evidence(self, step, name, text):
        p = os.path.join(self.a.root, "evidence", f"{step['id']}-{name}.txt")
        wr(p, text)
        return p

    def new(self):
        return dict(kit=KIT, started=now(), device=device(), bundles_dir=self.a.bundles, rounds=self.a.rounds,
                    steps=[dict(s, verdict="PENDING", detail="", phase="idle") for s in plan(self.a.rounds)])

    def run(self):
        a = self.a
        pf = preflight(a.bundles, NEED)
        st = self.load()
        if a.dry_run:
            return self.dry(pf)
        if st is None:
            bad = [p for p in pf if not p["ok"]]
            if bad:
                for p in bad:
                    print("PREFLIGHT FAIL:", p["check"], "-", p["detail"], file=sys.stderr)
                return 2
            st = self.new()
            st["preflight"] = pf
        while True:
            idx = next((i for i, s in enumerate(st["steps"]) if s["verdict"] == "PENDING"), None)
            self.save(st)
            if idx is None:
                print("all steps done; run `g1-run.py report` and fill G1-RECORD.md")
                return 0
            s = st["steps"][idx]
            if s["phase"] == "rebooting":
                r = self.evaluate(s)
                if r == "wait":
                    print(f"{s['id']}: gate still deciding; re-run in a minute")
                    return 3
            else:
                if self.start(s) == "reboot":
                    self.save(st)
                    print(f"{s['id']}: installed, rebooting. After it is back, run this command again.")
                    sh("systemctl", "reboot")
                    return 0
            if s["verdict"] == "FAIL":
                print(f"{s['id']}: FAIL {s['detail']}")
                self.save(st)
                return 1

    def dry(self, pf):
        print(f"DRY RUN: nothing is installed or rebooted (bundles: {self.a.bundles})")
        for p in pf:
            print(f"  preflight {'ok  ' if p['ok'] else 'MISS'} {p['check']}: {p['detail']}")
        for s in plan(self.a.rounds):
            cmd = f"rauc install {self.a.bundles}/{s['bundle']}.raucb" if s["bundle"] else "(no install)"
            print(f"  {s['id']:<18} {cmd}  -> {'reboot, ' if s['kind'] != 'refuse' else ''}expect: {s['expect']}")
        return 0

    def start(self, s):
        s["pre_slot"], s["offset"], s["t0"] = slot(), gate_size(), time.time()
        if s["kind"] == "confirm":
            s["phase"] = "rebooting"
            return "reboot"
        rc, out = sh("rauc", "install", os.path.join(self.a.bundles, s["bundle"] + ".raucb"))
        s["rauc_rc"], s["evidence"] = rc, self.evidence(s, "install", out)
        pend = rd(PENDING).split() if os.path.exists(PENDING) else []
        if s["kind"] == "refuse":
            ok = rc != 0 and not pend
            s["verdict"], s["detail"] = ("PASS" if ok else "FAIL"), f"rc={rc} trial_marker_written={bool(pend)}"
            return "done"
        if rc != 0:
            s["verdict"], s["detail"] = "FAIL", f"rauc install rc={rc}: {out.strip().splitlines()[-1:] }"
            return "done"
        if pend[:1] != [other(s["pre_slot"])]:
            s["verdict"], s["detail"] = "FAIL", f"install ok but trial marker is {pend}, expected slot {other(s['pre_slot'])}"
            return "done"
        s["phase"] = "rebooting"
        return "reboot"

    def evaluate(self, s):
        txt, res = gate_since(s["offset"])
        booted, pre, new = slot(), s["pre_slot"], other(s["pre_slot"])
        waited = time.time() - s["t0"]
        names = [r[0] for r in res]
        def verdict(ok, detail):
            s["verdict"], s["detail"], s["phase"] = ("PASS" if ok else "FAIL"), detail, "done"
            s["evidence"] = self.evidence(s, "gate", txt)
            return "done"
        if s["kind"] == "confirm":
            if any(r[0] == "committed-boot" and r[1] == pre for r in res) and booted == pre:
                return verdict(True, f"committed-boot on slot {pre}")
        elif s["kind"] == "commit":
            if "mark-bad" in names or "fell-back" in names or "unhealthy" in names:
                return verdict(False, f"gate rejected the good bundle: {names}")
            m = next((r for r in res if r[0] == "mark-good" and r[1] == new), None)
            if m and booted == new:
                t = re.search(r"after (\d+)s", m[3])
                return verdict(True, f"mark-good slot={new} version={m[2]} after {t.group(1) if t else '?'}s; healthz={healthz()}")
        elif s["kind"] == "markbad":
            if "mark-good" in names:
                return verdict(False, "COMMITTED A BAD SLOT: gate said mark-good")
            bad = next((r for r in res if r[0] == "mark-bad" and r[1] == new), None)
            if bad and booted == pre and any(r[0] == "committed-boot" and r[1] == pre for r in res):
                v = re.search(r"verdict=(\S+)", bad[3])
                return verdict(True, f"mark-bad slot={new} version={bad[2]} verdict={v.group(1) if v else '?'}; back on {pre}")
        elif s["kind"] == "fellback":
            if "mark-good" in names:
                return verdict(False, "COMMITTED A BAD SLOT: gate said mark-good")
            fb = next((r for r in res if r[0] == "fell-back" and r[1] == pre), None)
            if fb and booted == pre:
                return verdict(True, f"fell-back on {pre}: {fb[3].strip()[:120]}")
        if waited > self.a.step_timeout:
            return verdict(False, f"timeout after {waited:.0f}s; booted={booted}, gate results={names}")
        return "wait"


def record_text(st):
    d, rows = st.get("device", {}), []
    for s in st["steps"]:
        rows.append(f"| {s['id']} | {s['bundle'] or '-'} | {s['verdict']} | {s['detail'].replace('|', '/')} |")
    tpl = rd(os.path.join(os.path.dirname(os.path.abspath(__file__)), "G1-RECORD.template.md"))
    return (tpl.replace("{{device}}", f"{d.get('model')} ({d.get('arch')}, {d.get('mem_total_mib')} MiB RAM)")
               .replace("{{software}}", f"OneMind {d.get('os_version')}, kernel {d.get('kernel')}, {d.get('rauc')}")
               .replace("{{started}}", st.get("started", "")).replace("{{updated}}", st.get("updated", ""))
               .replace("{{rows}}", "\n".join(rows)).replace("{{summary}}", json.dumps(st.get("summary", {}), indent=1)))


def meminfo(key):
    m = re.search(rf"^{key}:\s+(\d+)", rd(f"{PROC}/meminfo"), re.M)
    return int(m.group(1)) // 1024 if m else None


def sample(a):
    disk = None
    for l in rd(f"{PROC}/diskstats").splitlines():
        f = l.split()
        if len(f) > 9 and f[2] == a.disk:
            disk = int(f[9]) * 512 // 1048576
    rc, sm = sh("smartctl", "-a", "/dev/" + a.disk.rstrip("0123456789p")) if shutil.which("smartctl") else (1, "")
    w = re.search(r"Data Units Written:\s+([\d,]+)", sm)
    u = re.search(r"Percentage Used:\s+(\d+)", sm)
    return dict(ts=now(), slot=slot(), mem_total_mib=meminfo("MemTotal"), mem_available_mib=meminfo("MemAvailable"),
                disk=a.disk, mib_written=disk, nvme_data_units_written=w.group(1) if w else None,
                nvme_pct_used=int(u.group(1)) if u else None,
                state_db_mib=round(os.path.getsize(STATE_DB) / 1048576, 1) if os.path.exists(STATE_DB) else None)


def soak(a, start):
    p, log = os.path.join(a.root, "soak-start.json"), os.path.join(a.root, "soak.jsonl")
    os.makedirs(a.root, exist_ok=True)
    s = sample(a)
    if start:
        if os.path.exists(p):
            print("soak already started:", rd(p))
            return 1
        mem = s["mem_total_mib"] or 0
        info = dict(started=s["ts"], ends=time.strftime("%Y-%m-%d", time.gmtime(time.time() + SOAK_DAYS * 86400)),
                    mem_total_mib=mem, is_4gb_board=3000 <= mem <= 4300, disk=a.disk, pass_rule="30 days: MemAvailable >= 2048 MiB, <= 5 GB/day written (LT-PI5-03)")
        wr(p, json.dumps(info, indent=1))
        if not info["is_4gb_board"]:
            print(f"WARNING: {mem} MiB RAM is not a 4 GB Pi; the soak record says so. LT-PI5-03 needs the 4 GB board.", file=sys.stderr)
        for n, body in (("onemind-g1-soak.service", f"[Unit]\nDescription=OneMind G1 soak sample\n[Service]\nType=oneshot\nExecStart={os.path.abspath(__file__)} soak-sample --root {a.root} --disk {a.disk}\n"),
                        ("onemind-g1-soak.timer", "[Unit]\nDescription=OneMind G1 soak, daily\n[Timer]\nOnCalendar=daily\nPersistent=true\n[Install]\nWantedBy=timers.target\n")):
            try:
                wr(os.path.join(UNIT_DIR, n), body)
            except OSError as e:
                print(f"could not write {n} ({e}): run `g1-run.py soak-sample` once a day yourself", file=sys.stderr)
                break
        else:
            sh("systemctl", "daemon-reload")
            rc, _ = sh("systemctl", "enable", "--now", "onemind-g1-soak.timer")
            print("daily timer", "enabled" if rc == 0 else "NOT enabled: sample by hand")
    wr(log, json.dumps(s) + "\n", "a")
    print(json.dumps(s))
    return 0


def autoresume(a):
    n = "onemind-g1-resume.service"
    p = os.path.join(UNIT_DIR, n)
    if a.mode == "off":
        sh("systemctl", "disable", n)
        if os.path.exists(p):
            os.remove(p)
        return 0
    wr(p, "[Unit]\nDescription=OneMind G1 kit: resume after reboot\nAfter=onemind-health-gate.service\n"
                       f"[Service]\nType=oneshot\nExecStart=/bin/sh -c 'sleep 60; {sys.executable} {os.path.abspath(__file__)} run --root {a.root} --bundles {a.bundles} || true'\n"
                       "[Install]\nWantedBy=multi-user.target\n")
    sh("systemctl", "daemon-reload")
    return sh("systemctl", "enable", n)[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "status", "report", "soak-start", "soak-sample", "autoresume"])
    ap.add_argument("mode", nargs="?", choices=["on", "off"], help="for autoresume")
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--bundles", default=BUNDLES[0])
    ap.add_argument("--rounds", type=int, default=10, help="chaos rollback rounds (UPDATES.md: rollback 10/10)")
    ap.add_argument("--step-timeout", type=int, default=2400)
    ap.add_argument("--disk", default="nvme0n1", help="soak: disk whose writes are counted")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return Run(a).run()
    if a.cmd in ("status", "report"):
        st = Run(a).load()
        if not st:
            print("no result.json yet: run `g1-run.py run`", file=sys.stderr)
            return 2
        if a.cmd == "report":
            out = os.path.join(a.root, "G1-RECORD.md")
            wr(out, record_text(st))
            print("wrote", out)
        else:
            for s in st["steps"]:
                print(f"{s['verdict']:<8} {s['id']:<18} {s['detail']}")
            print(json.dumps(st["summary"], indent=1))
        return 0
    if a.cmd == "autoresume":
        return autoresume(a) if a.mode else 2
    return soak(a, a.cmd == "soak-start")


if __name__ == "__main__":
    sys.exit(main())
