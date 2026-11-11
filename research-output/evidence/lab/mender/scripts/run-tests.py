#!/usr/bin/env python3
"""LAB-mender test driver. Runs INSIDE the disposable Lima VM.

Boots the x86_64 Mender A/B image under QEMU TCG with user-mode networking
(restrict=on: no route to the LAN or internet) and an i6300esb watchdog,
drives the serial console, and runs T1..T10 from README section 3 (Mender standalone).
Power cut = SIGKILL of the QEMU process.

  python3 -I run-tests.py --disk /var/lab/run/disk.img --log serial.log [--upto T3]
"""
import argparse, os, re, shutil, subprocess, sys, threading, time

ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][0-9A-B]|\r")
GATE = r"HEALTH-GATE: \S+ RESULT (\S+) slot=(\w) version=(\d+)"
ENV = "grub-mender-grubenv-print mender_boot_part upgrade_available bootcount"


class VM:
    def __init__(self, disk, vars_fd, log):
        self.disk, self.vars_fd, self.logf = disk, vars_fd, log
        self.buf, self.pos, self.lock, self.proc = "", 0, threading.Lock(), None

    def start(self):
        cmd = ["qemu-system-x86_64", "-machine", "q35", "-accel", "tcg,thread=multi",
               "-cpu", "max", "-smp", "4", "-m", "3072", "-nodefaults",
               "-display", "none", "-vga", "none",
               "-nic", "user,model=virtio-net-pci,restrict=on",
               "-device", "i6300esb", "-action", "watchdog=reset",
               "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd",
               "-drive", f"if=pflash,format=raw,file={self.vars_fd}",
               "-drive", f"if=virtio,format=raw,cache=writeback,file={self.disk}",
               "-serial", "stdio", "-monitor", "none"]
        self.mark(f"QEMU START {' '.join(cmd)}")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, bufsize=0)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while True:
            b = self.proc.stdout.read(4096)
            if not b:
                break
            t = ANSI.sub(b"", b).decode("utf-8", "replace")
            with self.lock:
                self.buf += t
            self.logf.write(t); self.logf.flush()

    def mark(self, msg):
        line = f"\n##### [{time.strftime('%H:%M:%S')}] {msg}\n"
        self.logf.write(line); self.logf.flush(); print(line.strip(), flush=True)

    def here(self):
        with self.lock:
            return len(self.buf)

    def since(self, i):
        with self.lock:
            return self.buf[i:]

    def expect(self, pattern, timeout):
        rx, end = re.compile(pattern), time.time() + timeout
        while time.time() < end:
            with self.lock:
                m = rx.search(self.buf, self.pos)
                if m:
                    self.pos = m.end()
                    return m
            time.sleep(0.2)
        raise TimeoutError(f"timeout {timeout}s waiting for {pattern!r}")

    def send(self, s):
        self.proc.stdin.write((s + "\n").encode()); self.proc.stdin.flush()

    def run(self, cmd, timeout=180):
        start = self.here()
        self.send(f"{cmd}; echo __R''C=$?__")
        m = self.expect(r"__RC=(\d+)__", timeout)
        with self.lock:
            out = self.buf[start:m.start()]
        return int(m.group(1)), out

    def wait_gate(self, timeout=1500):
        m = self.expect(GATE, timeout)
        return m.group(1), m.group(2), int(m.group(3))

    def shell_ready(self):
        time.sleep(2); self.send("")
        self.expect(r"root@onemind-lab:~# ", 300)
        self.run("stty cols 200; export SYSTEMD_PAGER= SYSTEMD_COLORS=0 KUBECONFIG=/run/k3s/k3s.yaml")

    def kill(self):
        self.mark("POWER CUT: SIGKILL qemu")
        self.proc.kill(); self.proc.wait()

    def restart(self, tag):
        self.mark(tag); self.buf, self.pos = "", 0; self.start()

    def poweroff(self):
        self.send("systemctl poweroff")
        try:
            self.proc.wait(240)
        except subprocess.TimeoutExpired:
            self.proc.kill(); self.proc.wait()
        self.mark("QEMU EXIT (poweroff)")


RESULTS = []

def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append((tid, verdict, detail))
    print(f"===> {tid}: {verdict} {detail}", flush=True)


PART = {"A": "2", "B": "3"}
OTHER = {"A": "B", "B": "A"}


def state(vm, tag):
    vm.run("echo '--- state:" + tag + "'; cat /etc/onemind-release; " + ENV +
           "; echo artifact=$(mender-update show-artifact 2>&1 | tail -n1); findmnt -no SOURCE /; "
           "k3s kubectl get pods -A --no-headers 2>&1 | head -8")
    return vm.run(ENV)[1]


def install(vm, art, timeout=2400):
    t = time.time()
    rc, out = vm.run(f"mender-update install /data/artifacts/{art} 2>&1 | grep -v '^$' | tail -5; test ${{PIPESTATUS[0]}} -eq 0", timeout)
    vm.mark(f"install {art} rc={rc} in {time.time()-t:.0f}s")
    return rc, out


def wait_fresh(vm, timeout=1500):
    m = vm.expect(r"K3S-FRESH (ok|ALERT)[^\n]*", timeout)
    return m.group(0).strip()


def update_and_reboot(vm, art):
    rc, out = install(vm, art)
    seg = vm.here()
    vm.send("systemctl reboot")
    return rc, seg


def env_is(env, slot):
    return f"mender_boot_part={PART[slot]}" in env and "upgrade_available=0" in env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disk", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--upto", default="T10")
    a = ap.parse_args()
    order = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10"]
    upto = order.index(a.upto)
    vars_fd = os.path.join(os.path.dirname(a.disk), "OVMF_VARS.fd")
    shutil.copy("/usr/share/OVMF/OVMF_VARS_4M.fd", vars_fd)
    logf = open(a.log, "w")
    t0 = time.time()
    vm = VM(a.disk, vars_fd, logf)
    want = lambda t: order.index(t) <= upto
    cur = "A"   # committed slot

    vm.mark("T1 first boot"); vm.start()
    g = vm.wait_gate()
    f = wait_fresh(vm)
    vm.shell_ready(); env = state(vm, "T1")
    _, apps = vm.run("k3s kubectl -n apps get pods --no-headers")
    record("T1", g == ("committed-boot", "A", 1) and f.startswith("K3S-FRESH ok") and "0/1" in apps and env_is(env, "A"),
           f"gate={g} {f[:90]} apps_not_ready={'0/1' in apps} t={time.time()-t0:.0f}s")

    if want("T2"):
        vm.mark("T2 wrong-key artifact")
        before = vm.run(ENV)[1]; art_b = vm.run("mender-update show-artifact")[1]
        rc, out = install(vm, "wrong-key.mender", 900)
        after = vm.run(ENV)[1]; art_a = vm.run("mender-update show-artifact")[1]
        sig = re.search(r"(?i)signature|verif|key", out) is not None
        _, probe = vm.run("mender-update commit 2>&1 | grep -v '^$' | tail -2")
        none = "No update in progress" in probe
        record("T2", rc != 0 and sig and before.split() == after.split() and art_b.split()[-1:] == art_a.split()[-1:] and none,
               f"rc={rc} sig_error={sig} env_unchanged={before.split()==after.split()} no_update_in_progress={none} err='{(re.findall(r'[^\n]*(?:ignature|erif)[^\n]*', out) or [''])[0].strip()[:120]}'")

    if want("T3"):
        tgt = OTHER[cur]
        vm.mark(f"T3 good update -> {tgt}")
        rc, seg = update_and_reboot(vm, "good.mender")
        g = vm.wait_gate(); s = vm.since(seg)
        passes = len(re.findall(r"CHECK pass \d/3", s)); fails = re.findall(r"CHECK fail at \d+s: ([^\n]*)", s)
        apps = re.search(r"APPS \(excluded from gate\): ([^\n]*)", s)
        grub = re.findall(r"MENDER-GRUB: [^\n]*", s)
        vm.shell_ready(); state(vm, "T3-after-commit")
        seg2 = vm.here(); vm.send("systemctl reboot")
        g2 = vm.wait_gate(); vm.shell_ready(); env = state(vm, "T3-second-reboot")
        apps_s = apps.group(1) if apps else ""
        ok = rc == 0 and g == ("mark-good", tgt, 2) and passes >= 3 and "0/1" in apps_s and g2 == ("committed-boot", tgt, 2) and env_is(env, tgt)
        record("T3", ok, f"rc={rc} grub={grub[:1]} trial={g} passes={passes} first_fails={fails[:2]} apps='{apps_s[:60]}' reboot={g2}")
        if ok:
            cur = tgt

    for tid, art, ver in (("T4", "bad-k3s.mender", 3), ("T5", "bad-noagent.mender", 4)):
        if not want(tid):
            continue
        tgt = OTHER[cur]
        vm.mark(f"{tid} {art} -> {tgt}")
        rc, seg = update_and_reboot(vm, art)
        ts = time.time()
        g1 = vm.wait_gate(); dt = time.time() - ts
        s = vm.since(seg); last = re.findall(r"CHECK fail at \d+s: ([^\n]*)", s)
        g2 = vm.wait_gate(); f = wait_fresh(vm)
        vm.shell_ready(); env = state(vm, f"{tid}-end")
        seg2 = vm.here(); vm.send("systemctl reboot")
        g3 = vm.wait_gate(); retried = f"slot={tgt}" in vm.since(seg2); vm.shell_ready()
        record(tid, rc == 0 and g1 == ("mark-bad", tgt, ver) and g2 == ("committed-boot", cur, 2)
               and env_is(env, cur) and f.startswith("K3S-FRESH ok") and g3 == ("committed-boot", cur, 2) and not retried,
               f"rc={rc} trial={g1} decided_after~{dt:.0f}s(since reboot) last_fail='{last[-1] if last else ''}' then={g2} env_ok={env_is(env, cur)} {f[:40]} next_reboot={g3}")

    for tid, art, mark in (("T6", "bad-boot.mender", "BAD-BOOT: broken init exiting"),
                           ("T7", "bad-hang.mender", "BAD-HANG: arming watchdog")):
        if not want(tid):
            continue
        tgt = OTHER[cur]
        vm.mark(f"{tid} {art} -> {tgt}")
        rc, seg = update_and_reboot(vm, art)
        ts = time.time()
        g = vm.wait_gate(3000); s = vm.since(seg)
        attempts = s.count(mark); grub = re.findall(r"MENDER-GRUB: [^\n]*|Rolling back\.\.\.|Booting new update\.\.\.", s)
        vm.shell_ready(); env = state(vm, f"{tid}-end")
        seg2 = vm.here(); vm.send("systemctl reboot")
        g2 = vm.wait_gate(); s2 = vm.since(seg2)
        retried = mark in s2
        vm.shell_ready()
        record(tid, rc == 0 and attempts >= 1 and g == ("fell-back", cur, 2) and env_is(env, cur)
               and not retried and g2 == ("committed-boot", cur, 2),
               f"rc={rc} attempts={attempts} in {time.time()-ts:.0f}s grub={grub} result={g} retried_next_boot={retried}")

    if want("T8"):
        tgt = OTHER[cur]
        vm.mark(f"T8 power cut during write (target {tgt})")
        p = PART[tgt]
        awk = "awk '{print \"sectors_read=\" $3 \" sectors_written=\" $7 \" sectors_rw=\" $3+$7}' /sys/block/vda/vda%s/stat" % p
        vm.send("(while :; do echo WRITE-PROGRESS vda%s $(%s); sleep 3; done) > /dev/console 2>&1 &" % (p, awk))
        time.sleep(2)
        before = vm.here()
        vm.send("mender-update install /data/artifacts/good.mender")
        w = [int(x) for x in re.findall(r"sectors_rw=(\d+)", vm.expect(r"WRITE-PROGRESS vda\d sectors_read=\d+[^\n]*", 60).group(0))]
        # wait until the slot write is clearly under way (> 400 MiB read+written on the target
        # partition; mender-flash reads the target and skips identical blocks)
        end = time.time() + 900; prog = w[0]
        while time.time() < end:
            m = re.findall(r"sectors_rw=(\d+)", vm.since(before))
            if m and int(m[-1]) - w[0] > 400 * 2048:
                prog = int(m[-1]); break
            time.sleep(1)
        out_so_far = vm.since(before)
        finished = re.search(r"Installed, but not committed|Installed and committed|Installation failed", out_so_far) is not None
        mib = (prog - w[0]) // 2048
        vm.kill()
        vm.restart("T8 restart after power cut")
        g = vm.wait_gate(); vm.shell_ready(); env = state(vm, "T8-after-cut")
        rc2, seg = update_and_reboot(vm, "good.mender")
        g2 = vm.wait_gate(); vm.shell_ready(); state(vm, "T8-after-reinstall")
        ok = (not finished and g[0] in ("committed-boot", "fell-back") and g[1:] == (cur, 2) and env_is(env, cur)
              and rc2 == 0 and g2 == ("mark-good", tgt, 2))
        lastp = (re.findall(r"WRITE-PROGRESS[^\n]*", out_so_far) or [""])[-1].strip()
        record("T8", ok, f"cut_after~{mib}MiB_rw_on_vda{p} last='{lastp}' install_finished_before_cut={finished} after_cut={g} "
               f"env_unchanged={env_is(env, cur)} reinstall_rc={rc2} then={g2}")
        if ok:
            cur = tgt

    if want("T9"):
        tgt = OTHER[cur]
        vm.mark(f"T9 power cut in commit window (target {tgt})")
        rc, seg = update_and_reboot(vm, "good.mender")
        vm.expect(rf"HEALTH-GATE: \S+ start slot={tgt} version=2 mode=trial", 1500)
        vm.expect(r"CHECK (pass|fail)", 900)
        committed_before = "RESULT mark-good" in vm.since(seg)
        vm.kill()
        vm.restart("T9 restart")
        grub = vm.expect(r"MENDER-GRUB: [^\n]*", 300).group(0)
        g = vm.wait_gate(); f = wait_fresh(vm); vm.shell_ready(); env = state(vm, "T9-end")
        record("T9", rc == 0 and not committed_before and g == ("mark-good", tgt, 2),
               f"rc={rc} killed_before_commit={not committed_before} next_boot='{grub.strip()}' result={g} (H4 predicts fell-back on {cur})")
        endslot = g[1]
        record("T9s", g[0] in ("mark-good", "fell-back", "committed-boot") and g[2] == 2 and f.startswith("K3S-FRESH ok")
               and env_is(env, endslot), f"ended on {g} {f[:40]} env_ok={env_is(env, endslot)}")
        cur = endslot

    if want("T10"):
        tgt = OTHER[cur]
        vm.mark(f"T10 naive gate observation (target {tgt})")
        rc, seg = update_and_reboot(vm, "naive-noagent.mender")
        g = vm.wait_gate(); s = vm.since(seg)
        npass = re.findall(r"CHECK pass \d/3 at (\d+)s: ([^\n]*)", s)
        record("T10", "OBSERVED", f"naive gate result={g} passes={[p[0] for p in npass]} "
               f"=> {'COMMITTED A BROKEN SYSTEM' if g[0] == 'mark-good' else 'did not commit'}")
        if g[0] == "mark-bad":
            g = vm.wait_gate()
        else:
            cur = tgt
        vm.shell_ready(); state(vm, "T10-after")
        _, kubelet = vm.run("curl -s -m 3 http://localhost:10248/healthz || echo NO-KUBELET")
        vm.mark(f"T10 kubelet on committed naive slot: {kubelet.strip()[-40:]}")
        tgt = OTHER[cur]
        rc2, seg2 = update_and_reboot(vm, "good.mender")
        g2 = vm.wait_gate(); vm.shell_ready(); state(vm, "T10r-end")
        record("T10r", rc2 == 0 and g2 == ("mark-good", tgt, 2), f"recovery install rc={rc2} result={g2}")

    vm.run("echo '--- gate log'; cat /data/onemind/gate.log | cut -c1-220")
    vm.poweroff()
    print("\nSUMMARY (total %.0f min)" % ((time.time() - t0) / 60))
    for r in RESULTS:
        print(" | ".join(r))
    logf.close()
    # Overall: every pass/fail test except T9 must pass (README section 3).
    return 0 if all(r[1] in ("PASS", "OBSERVED") for r in RESULTS if r[0] != "T9") else 1


if __name__ == "__main__":
    sys.exit(main())
