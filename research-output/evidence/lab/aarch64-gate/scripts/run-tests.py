#!/usr/bin/env python3
"""LAB-aarch64-gate test driver (from LAB-rauc-1152; changes: QEMU aarch64 + KVM
command line, AAVMF firmware, 60 MiB/s write throttle, T8 kill delay 2 s,
uname check in T1). Runs INSIDE the disposable Lima VM (nested KVM).

Boots the arm64 RAUC A/B image under QEMU/KVM (virt machine) with user-mode networking
(restrict=on: no route to the LAN or internet) and an i6300esb watchdog,
drives the serial console, and runs T1..T11 from README section 3.
Power cut = SIGKILL of the QEMU process.

  python3 -I run-tests.py --disk /var/lab/run/disk.img --log serial.log [--upto T3]
"""
import argparse, os, re, shutil, subprocess, sys, threading, time

ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][0-9A-B]|\r")
GATE = r"HEALTH-GATE: \S+ RESULT (\S+) slot=(\w) version=(\d+)"
ENV = "grub-editenv /boot/efi/EFI/BOOT/grubenv list"
ACCEL = os.environ.get("LAB_ACCEL", "kvm")          # "hvf" for the host fallback (README §4)
CODE_FD = os.environ.get("LAB_CODE_FD", "/usr/share/AAVMF/AAVMF_CODE.fd")
VARS_FD = os.environ.get("LAB_VARS_FD", "/usr/share/AAVMF/AAVMF_VARS.fd")
WRITE_BPS = int(os.environ.get("LAB_WRITE_BPS", "62914560"))  # 60 MiB/s (README §4, frozen); 0 = off (diagnosis only)


def envkv(out):
    # Compare only grubenv KEY=VALUE lines: terminal escape fragments split across
    # serial reads can leak into captured text (LAB-rauc-1152 deviation 4).
    out = re.sub(r"\x1b?\[\?[0-9;]*[A-Za-z]|\x1b\[[0-9;]*[A-Za-z]", "", out)   # also escapes split across reads
    return sorted(x.strip() for x in re.findall(r"^(?:ORDER=[AB ]+|[AB]_(?:OK|TRY)=\d+)[ \t]*$", out, re.M))


class VM:
    def __init__(self, disk, vars_fd, log):
        self.disk, self.vars_fd, self.logf = disk, vars_fd, log
        self.buf, self.pos, self.lock, self.proc = "", 0, threading.Lock(), None

    def start(self):
        cmd = ["qemu-system-aarch64", "-machine", "virt", "-accel", ACCEL,
               "-cpu", "host", "-smp", "4", "-m", "3072", "-nodefaults",
               "-display", "none",
               "-nic", "user,model=virtio-net-pci,restrict=on",
               "-device", "i6300esb", "-action", "watchdog=reset",
               "-drive", f"if=pflash,format=raw,readonly=on,file={CODE_FD}",
               "-drive", f"if=pflash,format=raw,file={self.vars_fd}",
               "-drive", f"if=virtio,format=raw,cache=writeback,{f'throttling.bps-write={WRITE_BPS},' if WRITE_BPS else ''}file={self.disk}",
               "-serial", "stdio", "-monitor", "none"]
        self.mark(f"QEMU START {' '.join(cmd)}")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, bufsize=0)
        CHILDREN.append(self.proc)
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
CHILDREN = []   # every QEMU this driver started


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append((tid, verdict, detail))
    print(f"===> {tid}: {verdict} {detail}", flush=True)


def state(vm, tag):
    vm.run("echo '--- state:" + tag + "'; cat /etc/onemind-release; " + ENV +
           "; rauc status 2>&1 | grep -E 'Booted from|boot status|rootfs\\.[01]'; "
           "cat /data/onemind/pending 2>/dev/null || echo 'pending: none'; "
           "k3s kubectl get pods -A --no-headers 2>&1 | head -8")
    return vm.run(ENV)[1]


def install(vm, bundle, timeout=2400):
    t = time.time()
    rc, out = vm.run(f"rauc install /data/bundles/{bundle} 2>&1 | tail -4; test ${{PIPESTATUS[0]}} -eq 0", timeout)
    vm.mark(f"install {bundle} rc={rc} in {time.time()-t:.0f}s")
    return rc, out


def wait_fresh(vm, timeout=1500):
    m = vm.expect(r"K3S-FRESH (ok|ALERT)[^\n]*", timeout)
    return m.group(0).strip()


def update_and_reboot(vm, bundle):
    rc, _ = install(vm, bundle)
    seg = vm.here()
    vm.send("systemctl reboot")
    return rc, seg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disk", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--upto", default="T10")
    a = ap.parse_args()
    order = ["T1", "T2", "T11", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10"]
    upto = order.index(a.upto)
    vars_fd = os.path.join(os.path.dirname(a.disk), "AAVMF_VARS.fd")
    shutil.copy(VARS_FD, vars_fd)
    logf = open(a.log, "w")
    t0 = time.time()
    vm = VM(a.disk, vars_fd, logf)
    want = lambda t: order.index(t) <= upto

    # T1 first boot: committed slot A v1, k3s passes the fresh check
    vm.mark("T1 first boot"); vm.start()
    g = vm.wait_gate()
    f = wait_fresh(vm)
    vm.shell_ready(); env = state(vm, "T1")
    _, apps = vm.run("k3s kubectl -n apps get pods --no-headers")
    _, ver = vm.run("rauc --version; grep bundle-formats /etc/rauc/system.conf; dpkg-query -W rauc 2>&1 | tail -1; echo ARCH=$(uname -m) KERNEL=$(uname -r)")
    ver = re.sub(r"\x1b?\[\?[0-9;]*[A-Za-z]", "", ver)   # bracketed-paste fragments split across reads (run-1 driver bug)
    v1152 = re.search(r"^rauc v?1\.15\.2\s*$", ver, re.M) is not None and "ARCH=aarch64" in ver
    record("T1", g == ("committed-boot", "A", 1) and f.startswith("K3S-FRESH ok") and "0/1" in apps and v1152,
           f"gate={g} {f[:90]} apps_not_ready={'0/1' in apps} rauc_1.15.2_and_aarch64={v1152} t={time.time()-t0:.0f}s")

    if want("T2"):
        vm.mark("T2 wrong-key bundle")
        before = vm.run(ENV)[1]
        rc, out = install(vm, "wrong-key.raucb", 900)
        after = vm.run(ENV)[1]
        sig = re.search(r"(?i)signature|verif|certificate", out) is not None
        _, pend = vm.run("cat /data/onemind/pending 2>/dev/null || echo none")
        record("T2", rc != 0 and sig and envkv(before) == envkv(after) != [] and "none" in pend,
               f"rc={rc} sig_error={sig} env_unchanged={envkv(before)==envkv(after)!=[]} marker_written={'none' not in pend}")

    if want("T11"):
        vm.mark("T11 plain-format bundle, valid signature, verity-only policy")
        before = vm.run(ENV)[1]
        rc, out = install(vm, "plain-good.raucb", 900)
        after = vm.run(ENV)[1]
        fmt = "Bundle format 'plain' not allowed" in out
        _, pend = vm.run("cat /data/onemind/pending 2>/dev/null || echo none")
        record("T11", rc != 0 and fmt and envkv(before) == envkv(after) != [] and "none" in pend,
               f"rc={rc} format_error={fmt} env_unchanged={envkv(before)==envkv(after)!=[]} marker_written={'none' not in pend}")

    if want("T3"):
        vm.mark("T3 good update -> B")
        rc, seg = update_and_reboot(vm, "good.raucb")
        g = vm.wait_gate(); s = vm.since(seg)
        passes = len(re.findall(r"CHECK pass \d/3", s)); fails = re.findall(r"CHECK fail at \d+s: ([^\n]*)", s)
        apps = re.search(r"APPS \(excluded from gate\): ([^\n]*)", s)
        vm.shell_ready(); state(vm, "T3-after-commit")
        seg2 = vm.here(); vm.send("systemctl reboot")
        g2 = vm.wait_gate(); vm.shell_ready(); state(vm, "T3-second-reboot")
        apps_s = apps.group(1) if apps else ""
        record("T3", rc == 0 and g == ("mark-good", "B", 2) and passes >= 3 and "0/1" in apps_s
               and g2 == ("committed-boot", "B", 2),
               f"rc={rc} trial={g} passes={passes} first_fails={fails[:2]} apps='{apps_s[:60]}' reboot={g2}")

    for tid, bundle, ver in (("T4", "bad-k3s.raucb", 3), ("T5", "bad-noagent.raucb", 4)):
        if not want(tid):
            continue
        vm.mark(f"{tid} {bundle} -> A")
        rc, seg = update_and_reboot(vm, bundle)
        ts = time.time()
        g1 = vm.wait_gate(); dt = time.time() - ts
        s = vm.since(seg); last = re.findall(r"CHECK fail at \d+s: ([^\n]*)", s)
        g2 = vm.wait_gate(); f = wait_fresh(vm)
        vm.shell_ready(); env = state(vm, f"{tid}-end")
        record(tid, rc == 0 and g1 == ("mark-bad", "A", ver) and g2 == ("committed-boot", "B", 2)
               and "A_OK=0" in env and f.startswith("K3S-FRESH ok"),
               f"rc={rc} trial={g1} decided_after~{dt:.0f}s(since reboot) last_fail='{last[-1] if last else ''}' then={g2} {f[:40]}")

    for tid, bundle, mark in (("T6", "bad-boot.raucb", "BAD-BOOT: broken init exiting"),
                              ("T7", "bad-hang.raucb", "BAD-HANG: arming watchdog")):
        if not want(tid):
            continue
        vm.mark(f"{tid} {bundle} -> A")
        rc, seg = update_and_reboot(vm, bundle)
        ts = time.time()
        g = vm.wait_gate(3000); s = vm.since(seg)
        attempts = s.count(mark); grub = re.findall(r"GRUB-RAUC: [^\n]*", s)
        vm.shell_ready(); env = state(vm, f"{tid}-end")
        seg2 = vm.here(); vm.send("systemctl reboot")
        g2 = vm.wait_gate(); s2 = vm.since(seg2)
        retried = mark in s2
        vm.shell_ready()
        record(tid, rc == 0 and attempts == 3 and g == ("fell-back", "B", 2) and "A_OK=0" in env
               and not retried and g2 == ("committed-boot", "B", 2),
               f"rc={rc} attempts={attempts} in {time.time()-ts:.0f}s grub={grub[-1] if grub else ''} result={g} retried_next_boot={retried}")

    if want("T8"):
        vm.mark("T8 power cut during write (target A)")
        vm.send("journalctl -f -n0 -o cat -u rauc.service > /dev/console 2>&1 &")
        time.sleep(2)
        vm.send("rauc install /data/bundles/good.raucb")
        vm.expect(r"trial marker slot=A", 900)
        vm.expect(r"Marking target slot rootfs\.0 as non-bootable", 900)
        vm.expect(r"Copying image|writing data to device", 900)
        time.sleep(2)                       # was 6 s under TCG (README §4)
        pct = re.findall(r"(\d+)% Copying image", vm.since(0))
        activated = "as bootable (active/primary)" in vm.since(vm.pos)
        vm.kill()
        vm.restart("T8 restart after power cut")
        g = vm.wait_gate(); vm.shell_ready(); env = state(vm, "T8-after-cut")
        _, pend = vm.run("cat /data/onemind/pending 2>/dev/null || echo none")
        rc2, seg = update_and_reboot(vm, "good.raucb")
        g2 = vm.wait_gate(); vm.shell_ready(); state(vm, "T8-after-reinstall")
        record("T8", not activated and g == ("fell-back", "B", 2) and "A_OK=0" in env and "none" in pend
               and rc2 == 0 and g2 == ("mark-good", "A", 2),
               f"cut_at={pct[-1] if pct else '?'}% activated_before_cut={activated} after_cut={g} "
               f"marker_cleared={'none' in pend} reinstall_rc={rc2} then={g2}")

    if want("T9"):
        vm.mark("T9 power cut in commit window (target B)")
        rc, seg = update_and_reboot(vm, "good.raucb")
        vm.expect(r"HEALTH-GATE: \S+ start slot=B version=2 mode=trial", 1500)
        vm.expect(r"CHECK (pass|fail)", 900)
        committed_before = "RESULT mark-good" in vm.since(seg)
        vm.kill()
        vm.restart("T9 restart")
        grub = vm.expect(r"GRUB-RAUC: [^\n]*", 300).group(0)
        g = vm.wait_gate(); vm.shell_ready(); state(vm, "T9-end")
        record("T9", rc == 0 and not committed_before and "B_TRY=2" in grub and g == ("mark-good", "B", 2),
               f"rc={rc} killed_before_commit={not committed_before} next_boot='{grub.strip()}' result={g}")

    if want("T10"):
        vm.mark("T10 naive gate observation (target A)")
        rc, seg = update_and_reboot(vm, "naive-noagent.raucb")
        g = vm.wait_gate(); s = vm.since(seg)
        npass = re.findall(r"CHECK pass \d/3 at (\d+)s: ([^\n]*)", s)
        record("T10", "OBSERVED", f"naive gate result={g} passes={[p[0] for p in npass]} "
               f"=> {'COMMITTED A BROKEN SYSTEM' if g[0] == 'mark-good' else 'did not commit'}")
        if g[0] == "mark-bad":
            g = vm.wait_gate()
        vm.shell_ready(); state(vm, "T10-after")
        _, kubelet = vm.run("curl -s -m 3 http://localhost:10248/healthz || echo NO-KUBELET")
        vm.mark(f"T10 kubelet on committed naive slot: {kubelet.strip()[-40:]}")
        rc2, seg2 = update_and_reboot(vm, "good.raucb")
        g2 = vm.wait_gate(); vm.shell_ready(); state(vm, "T10r-end")
        tgt = "B" if g[1] == "A" else "A"
        record("T10r", rc2 == 0 and g2 == ("mark-good", tgt, 2), f"recovery install rc={rc2} result={g2}")

    vm.run("echo '--- gate log'; cat /data/onemind/gate.log | cut -c1-220")
    vm.poweroff()
    print("\nSUMMARY (total %.0f min)" % ((time.time() - t0) / 60))
    for r in RESULTS:
        print(" | ".join(r))
    logf.close()
    return 0 if all(r[1] in ("PASS", "OBSERVED") for r in RESULTS) else 1


if __name__ == "__main__":
    import atexit, signal
    # Never leave QEMU running if the driver dies (run-1 lesson: a stray QEMU kept
    # writing the disk and loading the CPU after the driver was stopped).
    atexit.register(lambda: [p.kill() for p in CHILDREN if p.poll() is None])   # only our own QEMU
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    sys.exit(main())
