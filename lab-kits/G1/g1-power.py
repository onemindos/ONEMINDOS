#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""G1 power-pull harness (CORE-UPDATE-4, #215): drives the "20 of 20 power pulls still boot" cycles from
a CONTROLLER (your Mac or the lab box), not from the device under test. Stdlib only.

Each cycle (PP-10, lab-kits/common/PP-10.md): start `rauc install` on the box over SSH, cut power at a
phase (write-start, write-mid, write-done, reboot, trial-boot; cycles 6+ pick phases at random), hold it
off, power on, then wait. PASS = the box comes back with no keyboard, on a committed slot, RAUC says
the booted slot is good, the health probe answers. Every cycle is appended to a results file.

Power backends (--power): manual (you pull the cord when asked), redfish (BMC Reset action, Dell iDRAC
and others), ipmi (ipmitool chassis power), hook (a smart plug or relay reached by HTTP URLs).
Credentials come ONLY from the environment and are never written to the results file:
  redfish: G1_BMC_HOST, G1_BMC_USER, G1_BMC_PASS [G1_BMC_SYSTEM_ID, default System.Embedded.1; G1_BMC_CACERT]
  ipmi:    G1_BMC_HOST, G1_BMC_USER, G1_BMC_PASS (handed to ipmitool as IPMI_PASSWORD, never on argv)
  hook:    G1_PLUG_OFF_URL, G1_PLUG_ON_URL [G1_PLUG_METHOD=GET|POST, default GET]  (URLs may hold a token)
  probe:   G1_SSH_TARGET (user@host), [G1_SSH_KEY path or agent], [G1_HEALTH_URL, e.g. http://<box-ip>:10248/healthz]

  g1-power.py plan [--cycles N]          print the phases; touch nothing
  g1-power.py run --power P --confirm-power [--cycles N] [--bundle PATH_ON_BOX]
  g1-power.py summary                    count passes, print the line for G1-RECORD.md section B

A power backend other than manual changes real hardware, so it needs --confirm-power: a human saying
yes to this box. The harness never decides G1; the founder does, in G1-RECORD.md.
Exit codes: 0 all cycles in this run passed, 1 a cycle failed, 2 usage or setup.
"""
import argparse, json, os, random, re, shutil, subprocess, sys, time, urllib.request, urllib.error, ssl, base64

KIT = "onemind.g1-power/1"
E = os.environ.get
PHASES = ["write-start", "write-mid", "write-done", "reboot", "trial-boot"]
GATE_RE = re.compile(r"HEALTH-GATE: \S+ RESULT (\S+) slot=(\w)")
INSTALL_LOG = "/run/g1-power-install.log"
SECRETS = ("G1_BMC_PASS", "G1_PLUG_OFF_URL", "G1_PLUG_ON_URL", "G1_BMC_HOST", "G1_SSH_TARGET")


def scrub(text):
    """Remove any credential or address taken from the environment before text is stored or printed."""
    for k in SECRETS:
        v = E(k)
        if v and len(v) > 3:
            text = text.replace(v, f"<{k.lower()}>")
    return text


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def need_env(*names):
    miss = [n for n in names if not E(n)]
    if miss:
        raise SystemExit("set in the environment: " + ", ".join(miss))


# ---------------------------------------------------------------- power backends
class Power:
    name = "?"

    def off(self): raise NotImplementedError
    def on(self): raise NotImplementedError


class Manual(Power):
    name = "manual"

    def __init__(self, ask=input, say=print):
        self.ask, self.say = ask, say

    def off(self):
        self.ask("PULL THE POWER CORD now (not a soft power-off), then press Enter: ")

    def on(self):
        self.ask("Plug the power cord back in, press the power button if the box needs it, then press Enter: ")


class Redfish(Power):
    name = "redfish"

    def __init__(self, opener=None):
        need_env("G1_BMC_HOST", "G1_BMC_USER", "G1_BMC_PASS")
        self.url = (f"https://{E('G1_BMC_HOST')}/redfish/v1/Systems/{E('G1_BMC_SYSTEM_ID', 'System.Embedded.1')}"
                    "/Actions/ComputerSystem.Reset")
        tok = base64.b64encode(f"{E('G1_BMC_USER')}:{E('G1_BMC_PASS')}".encode()).decode()
        self.auth = "Basic " + tok
        ctx = ssl.create_default_context(cafile=E("G1_BMC_CACERT")) if E("G1_BMC_CACERT") else ssl.create_default_context()
        self.opener = opener or (lambda req: urllib.request.urlopen(req, timeout=30, context=ctx))

    def _reset(self, kind):
        req = urllib.request.Request(self.url, data=json.dumps({"ResetType": kind}).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": self.auth})
        try:
            self.opener(req).read()
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(scrub(f"redfish {kind} failed: {e}"))

    def off(self): self._reset("ForceOff")   # ForceOff = power drop, no OS shutdown
    def on(self): self._reset("On")


class Ipmi(Power):
    name = "ipmi"

    def __init__(self, run=None):
        need_env("G1_BMC_HOST", "G1_BMC_USER", "G1_BMC_PASS")
        self.run = run or self._run

    def _run(self, action):
        if not shutil.which("ipmitool"):
            raise RuntimeError("ipmitool not on PATH")
        env = dict(os.environ, IPMI_PASSWORD=E("G1_BMC_PASS"))   # -E reads it: the password never appears on argv
        p = subprocess.run(["ipmitool", "-I", "lanplus", "-H", E("G1_BMC_HOST"), "-U", E("G1_BMC_USER"), "-E",
                            "chassis", "power", action], capture_output=True, text=True, timeout=60, env=env)
        if p.returncode:
            raise RuntimeError(scrub(f"ipmitool power {action} rc={p.returncode}: {(p.stderr or p.stdout).strip()[:200]}"))

    def off(self): self.run("off")   # off = immediate, not `soft`
    def on(self): self.run("on")


class Hook(Power):
    name = "hook"

    def __init__(self, opener=None):
        need_env("G1_PLUG_OFF_URL", "G1_PLUG_ON_URL")
        self.method = E("G1_PLUG_METHOD", "GET").upper()
        if self.method not in ("GET", "POST"):
            raise SystemExit("G1_PLUG_METHOD must be GET or POST")
        self.opener = opener or (lambda req: urllib.request.urlopen(req, timeout=15))

    def _call(self, var):
        req = urllib.request.Request(E(var), method=self.method, data=b"" if self.method == "POST" else None)
        try:
            self.opener(req).read()
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(scrub(f"plug hook {var} failed: {e}"))

    def off(self): self._call("G1_PLUG_OFF_URL")
    def on(self): self._call("G1_PLUG_ON_URL")


def make_power(name):
    return {"manual": Manual, "redfish": Redfish, "ipmi": Ipmi, "hook": Hook}[name]()


# ---------------------------------------------------------------- probe of the box
def ssh_run(cmd, timeout=20):
    """Run `cmd` on the box. Returns (rc, output); rc 255 means unreachable."""
    target = E("G1_SSH_TARGET")
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=accept-new"]
    if E("G1_SSH_KEY"):
        argv += ["-i", E("G1_SSH_KEY"), "-o", "IdentitiesOnly=yes"]
    try:
        p = subprocess.run(argv + [target, cmd], capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 255, str(e)


def http_ok(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def parse_rauc(js):
    """`rauc status --output-format=json` -> (booted bootname, boot_status of that slot). Tolerant of layouts."""
    try:
        d = json.loads(js)
    except ValueError:
        return None, None
    booted = d.get("booted")
    for slot in d.get("slots", []):
        for _name, info in (slot.items() if isinstance(slot, dict) else []):
            if isinstance(info, dict) and (info.get("bootname") == booted or info.get("state") == "booted"):
                return info.get("bootname", booted), info.get("boot_status")
    return booted, None


def last_gate(text):
    m = GATE_RE.findall(text)
    return (m[-1][0], m[-1][1]) if m else (None, None)


class Harness:
    def __init__(self, power, ssh=ssh_run, http=http_ok, sleep=time.sleep, clock=time.time, rng=None, a=None):
        self.power, self.ssh, self.http, self.sleep, self.clock = power, ssh, http, sleep, clock
        self.rng, self.a = rng or random.Random(), a

    # --- probe
    def reachable(self):
        return self.ssh("true", 10)[0] == 0

    def probe(self):
        """One health reading: reachable, booted slot good, no pending trial, gate says committed, HTTP ok."""
        rc, out = self.ssh("rauc status --output-format=json", 30)
        if rc != 0:
            return dict(ok=False, reason="unreachable" if rc == 255 else f"rauc status rc={rc}")
        booted, boot_status = parse_rauc(out)
        _, pend = self.ssh("cat /data/onemind/pending 2>/dev/null; true", 15)
        _, gate = self.ssh("tail -n 40 /data/onemind/gate.log 2>/dev/null; true", 15)
        res, gslot = last_gate(gate)
        r = dict(booted=booted, boot_status=boot_status, pending=pend.strip(), gate_result=res, gate_slot=gslot,
                 http=self.http(self.a.health_url) if self.a.health_url else None)
        bad = []
        if boot_status != "good": bad.append(f"boot_status={boot_status}")
        if r["pending"]: bad.append("trial still pending")
        if res not in ("committed-boot", "mark-good") or gslot != booted: bad.append(f"gate={res}/{gslot}")
        if r["http"] is False: bad.append("health probe failed")
        r["ok"], r["reason"] = not bad, "; ".join(bad) or "committed and healthy"
        return r

    def wait_until(self, pred, limit, every=5):
        end = self.clock() + limit
        while self.clock() < end:
            if pred():
                return True
            self.sleep(every)
        return pred()

    def settle(self):
        """After power-on: wait for the box, then for the gate to decide. Returns the last probe."""
        last = dict(ok=False, reason="unreachable")
        end = self.clock() + self.a.settle
        while self.clock() < end:
            last = self.probe()
            if last["ok"]:
                return last
            self.sleep(self.a.poll)
        return last

    # --- one cycle
    def cut(self, phase):
        a = self.a
        self.ssh(f"rm -f {INSTALL_LOG}; nohup sh -c 'rauc install {a.bundle} >{INSTALL_LOG} 2>&1; echo rc=$? >>{INSTALL_LOG}' >/dev/null 2>&1 &", 15)
        if phase == "write-start":
            self.sleep(a.write_start)
        elif phase == "write-mid":
            self.sleep(a.write_mid)
        else:
            if not self.wait_until(lambda: "rc=" in self.ssh(f"cat {INSTALL_LOG}", 15)[1], a.install_timeout, a.poll):
                return "install never finished"
            if "rc=0" not in self.ssh(f"cat {INSTALL_LOG}", 15)[1]:
                return "install failed before the pull (not a power-pull result)"
            if phase in ("reboot", "trial-boot"):
                self.ssh("systemctl reboot", 10)
                if not self.wait_until(lambda: not self.reachable(), a.install_timeout, 1):
                    return "box never went down after reboot"
                self.sleep(a.reboot_delay if phase == "reboot" else a.trial_delay)
        self.power.off()
        return None

    def cycle(self, n, phase):
        rec = dict(cycle=n, phase=phase, start=now(), power=self.power.name)
        pre = self.probe()
        if not pre["ok"]:
            rec.update(verdict="ABORT", detail=f"box not healthy before the pull: {pre['reason']}")
            return rec
        rec["slot_before"] = pre["booted"]
        try:
            err = self.cut(phase)
            if err:
                self.power.on()
                rec.update(verdict="ABORT", detail=err)
                return rec
            self.sleep(self.a.hold_off)
            self.power.on()
            post = self.settle()
        except RuntimeError as e:
            rec.update(verdict="ABORT", detail=scrub(str(e)))
            return rec
        rec.update(slot_after=post.get("booted"), boot_status=post.get("boot_status"), gate=post.get("gate_result"),
                   http=post.get("http"), detail=scrub(post["reason"]), verdict="PASS" if post["ok"] else "FAIL")
        if rec["verdict"] == "PASS" and self.a.reinstall_check:
            rc, out = self.ssh(f"rauc install {self.a.bundle}", self.a.install_timeout)
            rec["reinstall_rc"] = rc
            if rc != 0:
                rec.update(verdict="FAIL", detail="re-run of the install failed after the pull")
            else:
                self.ssh("systemctl reboot", 10)
                self.sleep(self.a.poll)
                again = self.settle()
                if not again["ok"]:
                    rec.update(verdict="FAIL", detail="after the re-install: " + scrub(again["reason"]))
        rec["end"] = now()
        return rec


def phases_for(cycles, rng):
    """PP-10: first five cover each phase once in order, the rest are spread at random over the same phases."""
    return [PHASES[i] if i < len(PHASES) else rng.choice(PHASES) for i in range(cycles)]


def load(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def summary_line(recs):
    done = [r for r in recs if r["verdict"] in ("PASS", "FAIL")]
    p = sum(r["verdict"] == "PASS" for r in done)
    return (f"Power pulls (g1-power.py, {len(done)} counted, {len(recs) - len(done)} aborted and not counted): "
            f"bootable after {p} / {len(done)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["plan", "run", "summary"])
    ap.add_argument("--power", choices=["manual", "redfish", "ipmi", "hook"], default="manual")
    ap.add_argument("--confirm-power", action="store_true", help="required for redfish, ipmi, hook: you own this box")
    ap.add_argument("--cycles", type=int, default=20, help="G1 wants 20 of 20")
    ap.add_argument("--results", default="g1-power.jsonl", help="one JSON line per cycle; resume = same file")
    ap.add_argument("--bundle", default="/run/onemind-test/bundles/good.raucb", help="bundle path ON THE BOX")
    ap.add_argument("--health-url", default=E("G1_HEALTH_URL"))
    ap.add_argument("--seed", type=int, default=None, help="fix the random phases (cycles 6+)")
    ap.add_argument("--write-start", type=float, default=2, help="seconds after install starts")
    ap.add_argument("--write-mid", type=float, default=20)
    ap.add_argument("--reboot-delay", type=float, default=2, help="seconds after the box goes down")
    ap.add_argument("--trial-delay", type=float, default=40, help="seconds into the trial boot, before the gate decides")
    ap.add_argument("--hold-off", type=float, default=10, help="seconds the power stays off")
    ap.add_argument("--settle", type=float, default=900, help="PP-10: wait this long, touching nothing")
    ap.add_argument("--poll", type=float, default=15)
    ap.add_argument("--install-timeout", type=float, default=900)
    ap.add_argument("--reinstall-check", action="store_true", help="PP-10 also wants a re-run of the install to succeed")
    a = ap.parse_args(argv)
    rng = random.Random(a.seed)
    if a.cmd == "plan":
        for i, ph in enumerate(phases_for(a.cycles, rng), 1):
            print(f"cycle {i:02d}: pull at {ph}")
        return 0
    recs = load(a.results)
    if a.cmd == "summary":
        print(summary_line(recs))
        return 0
    if a.power != "manual" and not a.confirm_power:
        print(f"--power {a.power} cuts real power: re-run with --confirm-power once you are sure this is the lab box.", file=sys.stderr)
        return 2
    try:
        need_env("G1_SSH_TARGET")
        power = make_power(a.power)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2
    h = Harness(power, rng=rng, a=a)
    ph = phases_for(a.cycles, rng)
    counted = sum(r["verdict"] in ("PASS", "FAIL") for r in recs)
    rc = 0
    for n in range(counted + 1, a.cycles + 1):
        r = h.cycle(n, ph[n - 1])
        with open(a.results, "a") as f:
            f.write(json.dumps(r) + "\n")
        recs.append(r)
        print(f"cycle {n:02d} {r['phase']:<12} {r['verdict']}: {r.get('detail', '')}")
        if r["verdict"] != "PASS":
            rc = 1
            break
    print(summary_line(recs))
    return rc


if __name__ == "__main__":
    sys.exit(main())
