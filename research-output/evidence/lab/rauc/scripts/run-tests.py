#!/usr/bin/env python3
"""LAB-rauc test driver. Runs INSIDE the disposable Lima VM.

Boots the x86_64 RAUC A/B disk image under QEMU TCG (no network device),
drives the serial console, and runs T1..T7 from README section 3.
Power cut = SIGKILL of the QEMU process.

  python3 -I run-tests.py --disk /var/lab/out/disk.img --log /path/serial.log
"""
import argparse, os, re, shutil, subprocess, sys, threading, time

ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][0-9A-B]|\r")


class VM:
    def __init__(self, disk, vars_fd, log):
        self.disk, self.vars_fd, self.logf = disk, vars_fd, log
        self.buf, self.pos, self.lock, self.proc = "", 0, threading.Lock(), None

    def start(self):
        cmd = ["qemu-system-x86_64", "-machine", "q35", "-accel", "tcg,thread=multi",
               "-cpu", "max", "-smp", "4", "-m", "2048", "-nodefaults",
               "-display", "none", "-vga", "none", "-nic", "none",
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

    def expect(self, pattern, timeout):
        rx, end = re.compile(pattern), time.time() + timeout
        while time.time() < end:
            with self.lock:
                m = rx.search(self.buf, self.pos)
                if m:
                    self.pos = m.end()
                    return m
            if self.proc.poll() is not None and not self.proc.stdout:
                break
            time.sleep(0.2)
        raise TimeoutError(f"timeout {timeout}s waiting for {pattern!r}")

    def send(self, s):
        self.proc.stdin.write((s + "\n").encode()); self.proc.stdin.flush()

    def run(self, cmd, timeout=120):
        """Run a shell command; return (rc, output)."""
        with self.lock:
            start = len(self.buf)
        self.send(f"{cmd}; echo __R''C=$?__")
        m = self.expect(r"__RC=(\d+)__", timeout)
        with self.lock:
            out = self.buf[start:m.start()]
        return int(m.group(1)), out

    def wait_gate(self, timeout=900):
        """Wait for one health-gate RESULT line; return (verb, slot, version)."""
        m = self.expect(r"HEALTH-GATE: RESULT (\S+) slot=(\w) version=(\d+)", timeout)
        return m.group(1), m.group(2), int(m.group(3))

    def shell_ready(self):
        time.sleep(2); self.send("")
        self.expect(r"root@onemind-lab:~# ", 120)
        self.run("stty cols 200; export SYSTEMD_PAGER= SYSTEMD_COLORS=0")

    def kill(self):
        self.mark("POWER CUT: SIGKILL qemu")
        self.proc.kill(); self.proc.wait()

    def poweroff(self):
        self.send("systemctl poweroff")
        try:
            self.proc.wait(180)
        except subprocess.TimeoutExpired:
            self.proc.kill(); self.proc.wait()
        self.mark("QEMU EXIT (poweroff)")


RESULTS = []


def record(tid, ok, detail):
    RESULTS.append((tid, "PASS" if ok else "FAIL", detail))
    print(f"===> {tid}: {'PASS' if ok else 'FAIL'} {detail}", flush=True)


def state(vm, tag):
    vm.run("echo '--- state:" + tag + "'; cat /etc/onemind-release; "
           "grub-editenv /boot/efi/EFI/BOOT/grubenv list; rauc status 2>&1 | head -30")
    return vm.run("grub-editenv /boot/efi/EFI/BOOT/grubenv list")[1]


def install(vm, bundle, timeout=1800):
    rc, out = vm.run(f"rauc install /data/bundles/{bundle} 2>&1 | tail -5; "
                     "test ${PIPESTATUS[0]} -eq 0", timeout)
    return rc, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disk", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    work = os.path.dirname(a.disk)
    vars_fd = os.path.join(work, "OVMF_VARS.fd")
    shutil.copy("/usr/share/OVMF/OVMF_VARS_4M.fd", vars_fd)
    logf = open(a.log, "w")
    t0 = time.time()
    vm = VM(a.disk, vars_fd, logf)

    # T1 first boot
    vm.mark("T1 first boot"); vm.start()
    verb, slot, ver = vm.wait_gate()
    vm.shell_ready(); env = state(vm, "T1")
    record("T1", verb == "mark-good" and slot == "A" and ver == 1 and "A_OK=1" in env,
           f"gate={verb} slot={slot} v={ver}; first boot {time.time()-t0:.0f}s")

    # T2 wrong-key bundle must be refused, boot env unchanged
    vm.mark("T2 wrong-key bundle")
    before = env
    rc, out = install(vm, "wrong-key.raucb", 600)
    after = vm.run("grub-editenv /boot/efi/EFI/BOOT/grubenv list")[1]
    sig_err = re.search(r"(?i)signature|verif|certificate", out) is not None
    record("T2", rc != 0 and sig_err and before.split() == after.split(),
           f"rc={rc} sig_error_msg={sig_err} env_unchanged={before.split()==after.split()}")

    # T3 good update A -> B, commit, survives a second reboot
    vm.mark("T3 good update"); t = time.time()
    rc, out = install(vm, "good.raucb")
    vm.mark(f"T3 install rc={rc} in {time.time()-t:.0f}s")
    vm.send("systemctl reboot")
    verb, slot, ver = vm.wait_gate()
    vm.shell_ready(); state(vm, "T3-after-update")
    vm.send("systemctl reboot")
    verb2, slot2, ver2 = vm.wait_gate(); vm.shell_ready(); state(vm, "T3-second-reboot")
    record("T3", rc == 0 and (verb, slot, ver) == ("mark-good", "B", 2) and (verb2, slot2, ver2) == ("mark-good", "B", 2),
           f"install_rc={rc} boot1={verb}/{slot}/v{ver} boot2={verb2}/{slot2}/v{ver2}")

    # T4 bad-health: boots, gate rejects, back on B v2
    vm.mark("T4 bad-health update")
    rc, out = install(vm, "bad-health.raucb")
    vm.send("systemctl reboot")
    g1 = vm.wait_gate(); g2 = vm.wait_gate()
    vm.shell_ready(); state(vm, "T4-end")
    record("T4", rc == 0 and g1 == ("mark-bad", "A", 3) and g2 == ("mark-good", "B", 2),
           f"install_rc={rc} boot1={g1} boot2={g2}")

    # T5 bad-boot: kernel panic, GRUB falls back to B v2
    vm.mark("T5 bad-boot update")
    rc, out = install(vm, "bad-boot.raucb")
    vm.send("systemctl reboot")
    panic = vm.expect(r"Kernel panic[^\n]*", 900).group(0)
    g = vm.wait_gate(); vm.shell_ready(); state(vm, "T5-end")
    record("T5", rc == 0 and g == ("mark-good", "B", 2), f"install_rc={rc} panic='{panic.strip()}' then {g}")

    # T6 power cut mid-write (target slot A), reboot, reinstall
    vm.mark("T6 power cut during write")
    # Mirror RAUC's service log to the serial console (backgrounded; not via
    # run(), because "cmd &; echo" is a bash syntax error).
    vm.send("journalctl -f -n0 -o cat -u rauc.service > /dev/console 2>&1 &")
    time.sleep(2)
    vm.send("rauc install /data/bundles/good.raucb")
    vm.expect(r"Marking target slot rootfs\.0 as non-bootable", 600)
    vm.expect(r"writing data to device|Copying image|Extracting", 600)
    time.sleep(4)
    with vm.lock:
        tail = vm.buf[vm.pos:]
    activated_before_kill = "as bootable (active/primary)" in tail
    vm.kill()
    vm.mark("T6 restart after power cut"); vm.buf, vm.pos = "", 0; vm.start()
    g = vm.wait_gate(); vm.shell_ready(); env6 = state(vm, "T6-after-cut")
    rc2, _ = install(vm, "good.raucb")
    vm.send("systemctl reboot"); g2 = vm.wait_gate(); vm.shell_ready(); state(vm, "T6-after-reinstall")
    record("T6", (not activated_before_kill) and g == ("mark-good", "B", 2) and "A_OK=0" in env6
           and rc2 == 0 and g2 == ("mark-good", "A", 2),
           f"killed_mid_write=True activated_before_kill={activated_before_kill} after_cut={g} "
           f"A_OK=0:{'A_OK=0' in env6} reinstall_rc={rc2} then={g2}")

    # T7 power cut in the commit window (booted new slot B, not yet marked good)
    vm.mark("T7 power cut in commit window")
    rc, _ = install(vm, "good.raucb")
    vm.send("systemctl reboot")
    m = vm.expect(r"HEALTH-GATE: start slot=(\w)", 900)
    started = m.group(1)
    time.sleep(3); vm.kill()
    vm.mark("T7 restart"); vm.buf, vm.pos = "", 0; vm.start()
    g = vm.wait_gate(); vm.shell_ready(); state(vm, "T7-end")
    record("T7", rc == 0 and started == "B" and g == ("mark-good", "A", 2),
           f"install_rc={rc} killed_after_gate_start_on={started} next={g}")

    vm.run("echo '--- gate log'; cat /data/gate.log")
    vm.poweroff()
    print("\nSUMMARY (total %.0f min)" % ((time.time() - t0) / 60))
    for r in RESULTS:
        print(" | ".join(r))
    logf.close()
    return 0 if all(r[1] == "PASS" for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
