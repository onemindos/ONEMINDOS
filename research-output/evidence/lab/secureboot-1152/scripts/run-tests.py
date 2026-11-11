#!/usr/bin/env python3
"""LAB-secureboot-1152 test driver (derived from ../../secureboot-rauc/scripts/run-tests.py;
adds the guest RAUC version to T1, T8 verity-only policy and the T9 slot-detection probe).
Original: LAB-secureboot-rauc (X-2R) test driver. Runs INSIDE the disposable Lima VM.

Boots the x86_64 image under QEMU q35 + OVMF (Secure Boot build, SMM) + swtpm,
TCG emulation, no network device, and runs T1..T7 from README section 4.

  python3 -I run-tests.py --out /var/lab/sbout --run /var/lab/sbrun --log serial.log
"""
import argparse, os, re, shutil, subprocess, sys, threading, time

ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][0-9A-B]|\r")
CODE = "/usr/share/OVMF/OVMF_CODE_4M.secboot.fd"
GATE = r"HEALTH-GATE: RESULT (\S+) slot=(\w) version=(\d+)"


class VM:
    def __init__(self, run, log):
        self.run_dir, self.logf = run, log
        self.buf, self.pos, self.lock = "", 0, threading.Lock()
        self.proc = self.tpm = None

    def start(self, vars_fd):
        sock = os.path.join(self.run_dir, "swtpm.sock")
        if os.path.exists(sock):
            os.unlink(sock)
        self.tpm = subprocess.Popen(
            ["swtpm", "socket", "--tpm2", "--tpmstate", f"dir={self.run_dir}/tpm",
             "--ctrl", f"type=unixio,path={sock}", "--terminate"],
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        for _ in range(50):
            if os.path.exists(sock):
                break
            time.sleep(0.1)
        cmd = ["qemu-system-x86_64", "-machine", "q35,smm=on", "-accel", "tcg,thread=multi",
               "-cpu", "max", "-smp", "4", "-m", "2048", "-nodefaults",
               "-display", "none", "-vga", "none", "-nic", "none",
               "-global", "driver=cfi.pflash01,property=secure,value=on",
               "-global", "ICH9-LPC.disable_s3=1",
               "-drive", f"if=pflash,format=raw,unit=0,readonly=on,file={CODE}",
               "-drive", f"if=pflash,format=raw,unit=1,file={vars_fd}",
               "-drive", f"if=virtio,format=raw,cache=writeback,file={self.run_dir}/disk.img",
               "-drive", f"if=virtio,format=raw,readonly=on,file={self.run_dir}/bundles.img",
               "-chardev", f"socket,id=chrtpm,path={sock}",
               "-tpmdev", "emulator,id=tpm0,chardev=chrtpm", "-device", "tpm-tis,tpmdev=tpm0",
               "-serial", "stdio", "-monitor", "none"]
        self.mark("QEMU START " + " ".join(cmd))
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

    def gate(self, timeout=1500):
        m = self.expect(GATE, timeout)
        return m.group(1), m.group(2), int(m.group(3))

    def shell(self):
        time.sleep(3); self.send("")
        self.expect(r"root@onemind-lab:~# ", 180)
        self.run("stty cols 220; export SYSTEMD_PAGER= SYSTEMD_COLORS=0")

    def stop(self):
        self.send("systemctl poweroff")
        try:
            self.proc.wait(300)
        except subprocess.TimeoutExpired:
            self.proc.kill(); self.proc.wait()
        try:
            self.tpm.wait(30)
        except subprocess.TimeoutExpired:
            self.tpm.kill()
        self.mark("QEMU EXIT (poweroff)")


RESULTS = []


def record(tid, ok, detail):
    RESULTS.append((tid, "PASS" if ok else "FAIL", detail))
    print(f"===> {tid}: {'PASS' if ok else 'FAIL'} {detail}", flush=True)


def state(vm, tag):
    rc, out = vm.run("echo '--- state:" + tag + "'; cat /etc/onemind-release; "
                     "mokutil --sb-state 2>&1; efibootmgr; mountpoint /data; "
                     "rauc status 2>&1 | grep -E 'Booted from|Activated|boot status|^ *\\[|bootname' ")
    return out


def bootorder_first(out):
    order = re.search(r"BootOrder: (\S+)", out)
    names = dict(re.findall(r"Boot([0-9A-F]{4})\*? (OneMind-[AB])", out))
    if not order:
        return None
    first = order.group(1).split(",")[0]
    return names.get(first, first)


def bootnext(out):
    m = re.search(r"BootNext: ([0-9A-F]{4})", out)
    names = dict(re.findall(r"Boot([0-9A-F]{4})\*? (OneMind-[AB])", out))
    return names.get(m.group(1), m.group(1)) if m else None


def install(vm, b):
    rc, out = vm.run(f"rauc install /mnt/bundles/{b}.raucb 2>&1 | tail -4; test ${{PIPESTATUS[0]}} -eq 0", 2400)
    _, eo = vm.run("efibootmgr")
    return rc, out, eo


def probe(vm, tag):
    """T9/H4: what does RAUC report as booted when rauc.slot= is hidden from it?
    Bind-mounts a copy of /proc/cmdline without rauc.slot=, restarts the RAUC
    service, reads 'rauc status', then undoes both."""
    _, out = vm.run(
        "echo '--- probe:" + tag + "'; efibootmgr | grep -E '^Boot(Current|Order)'; "
        "rauc status 2>&1 | grep -E '^Booted from|^Activated'; "
        "sed 's/ rauc\\.slot=[^ ]*//' /proc/cmdline > /run/cmdline.probe; "
        "mount --bind /run/cmdline.probe /proc/cmdline && echo PROBE-CMDLINE: $(cat /proc/cmdline | grep -o 'root=[^ ]*\\|rauc.slot=[^ ]*' | tr '\\n' ' '); "
        "systemctl restart rauc; sleep 2; echo PROBE-STATUS-''BEGIN; rauc status 2>&1 | grep -E '^Booted from|^Activated|rror|bootname' ; "
        "journalctl -b -u rauc --no-pager -o cat 2>/dev/null | grep -i -E 'bootname|BootCurrent|booted|rror' | tail -4; echo PROBE-STATUS-''END; "
        "umount /proc/cmdline; systemctl restart rauc; sleep 2; rauc status 2>&1 | grep -E '^Booted from'", 240)
    m = re.search(r"PROBE-STATUS-BEGIN(.*?)PROBE-STATUS-END", out, re.S)
    return out, (m.group(1).strip() if m else "")


def reboot(vm):
    vm.send("systemctl reboot")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--log", required=True)
    a = ap.parse_args()
    shutil.rmtree(a.run, ignore_errors=True); os.makedirs(f"{a.run}/tpm")
    for f in ("disk.img", "bundles.img"):
        subprocess.run(["cp", "--sparse=always", f"{a.out}/{f}", f"{a.run}/{f}"], check=True)
    vars_sb = f"{a.run}/OVMF_VARS.fd"; shutil.copy(f"{a.out}/OVMF_VARS_sb.fd", vars_sb)
    logf = open(a.log, "w"); t0 = time.time()
    vm = VM(a.run, logf)

    # T1 first boot under Secure Boot
    vm.mark("T1 first boot (Secure Boot, lab keys)"); i = vm.here(); vm.start(vars_sb)
    verb, slot, ver = vm.gate(); vm.shell()
    _, extra = vm.run("dmesg | grep -i -E 'secure ?boot|lockdown' | head -5; efi-readvar -v PK | head -6; "
                      "rauc --version; cryptsetup luksDump /dev/disk/by-partlabel/onemind-data | grep -E '^Version|systemd-|tpm2-pcrs|Keyslot|^  [0-9]+: luks2' ")
    st = state(vm, "T1"); seg = vm.since(i)
    checks = {
        "gate": (verb, slot, ver) == ("mark-good", "A", 1),
        "SecureBoot=1 SetupMode=0": "SecureBoot=1 SetupMode=0" in seg,
        "kernel SB": re.search(r"[Ss]ecure boot enabled", seg) is not None,
        "lab PK": "OneMind LAB PK" in seg,
        "LUKS2": re.search(r"Version:\s+2", extra) is not None,
        "tpm2 token": "systemd-tpm2" in extra,
        "unlock": "UNLOCK OK method=tpm2" in seg,
        "no prompt": "Please enter passphrase" not in seg,
        "guest rauc 1.15.2": re.search(r"^rauc v?1\.15\.2\s*$", extra, re.M) is not None,
    }
    record("T1", all(checks.values()), f"{checks}; first boot {time.time()-t0:.0f}s")
    bonus = {"T1/A": "BONUS-PCR11: UNLOCK OK slot=A" in seg}

    # T8 verity-only policy: a validly signed plain bundle must be refused
    vm.mark("T8 plain-format bundle (verity-only device)")
    _, before = vm.run("efibootmgr | grep -E '^Boot(Next|Order)'")
    rc, out, eo = install(vm, "plain-good")
    _, after = vm.run("efibootmgr | grep -E '^Boot(Next|Order)'")
    fmt_err = re.search(r"[Bb]undle format .plain. not allowed", out) is not None
    ok = (rc != 0 and fmt_err and "BootNext" not in after
          and re.search(r"BootOrder: \S+", before).group(0) == re.search(r"BootOrder: \S+", after).group(0))
    record("T8", ok, f"install rc={rc} format-error={fmt_err} before={before.split()[-2:]} after={after.split()[-2:]} "
           f"msg={[l for l in out.splitlines() if 'plain' in l][:2]}")

    # T2 good update A -> B
    vm.mark("T2 good update A->B"); rc, out, eo = install(vm, "good")
    bn = bootnext(eo); i = vm.here(); reboot(vm)
    verb, slot, ver = vm.gate(); vm.shell(); st = state(vm, "T2a"); seg = vm.since(i)
    ok1 = (rc == 0 and bn == "OneMind-B" and (verb, slot, ver) == ("mark-good", "B", 2)
           and "SecureBoot=1 SetupMode=0" in seg and "UNLOCK OK method=tpm2" in seg
           and bootorder_first(st) == "OneMind-B")
    bonus["T2/B"] = "BONUS-PCR11: UNLOCK OK slot=B" in seg
    i = vm.here(); reboot(vm); verb2, slot2, ver2 = vm.gate(); vm.shell(); seg2 = vm.since(i)
    ok2 = (verb2, slot2, ver2) == ("mark-good", "B", 2) and "UNLOCK OK method=tpm2" in seg2
    pout, pst = probe(vm, "T9 on committed B")
    print(f"===> T9 (info): status with rauc.slot hidden: {pst!r}", flush=True)
    RESULTS.append(("T9 (info)", "INFO", pst.replace(chr(10), " / ")))
    record("T2", ok1 and ok2, f"install rc={rc} BootNext={bn} gate1={verb}/{slot}/v{ver} "
           f"BootOrder[0]={bootorder_first(st)} gate2={verb2}/{slot2}/v{ver2}")

    # T3 health-gated rollback
    vm.mark("T3 bad-health update (into A) -> rollback to B"); rc, out, eo = install(vm, "bad-health")
    bn = bootnext(eo); i = vm.here(); reboot(vm)
    g1 = vm.gate(); g2 = vm.gate(); vm.shell(); st = state(vm, "T3"); seg = vm.since(i)
    unlocks = seg.count("UNLOCK OK method=tpm2")
    ok = (rc == 0 and bn == "OneMind-A" and g1 == ("mark-bad", "A", 3) and g2 == ("mark-good", "B", 2)
          and unlocks >= 2 and seg.count("SecureBoot=1 SetupMode=0") >= 2)
    bonus["T3/A-bad"] = seg.count("BONUS-PCR11: UNLOCK OK slot=A") >= 1
    bonus["T3/B-after-rollback"] = "BONUS-PCR11: UNLOCK OK slot=B" in seg
    record("T3", ok, f"install rc={rc} BootNext={bn} gate1={g1} gate2={g2} tpm-unlocks={unlocks} "
           f"BootOrder[0]={bootorder_first(st)}")

    # T4/T5 tampered and unsigned kernels must be refused by the firmware
    for tid, b, v in (("T4", "tampered", 4), ("T5", "unsigned", 5)):
        vm.mark(f"{tid} {b} UKI (into A) -> firmware must refuse"); rc, out, eo = install(vm, b)
        bn = bootnext(eo); i = vm.here(); reboot(vm)
        g = vm.gate(); vm.shell(); st = state(vm, tid); seg = vm.since(i)
        fw = re.findall(r"BdsDxe: failed to load Boot[0-9A-F]{4}[^\n]*|[^\n]*(?:Access Denied|Security Violation)[^\n]*", seg)
        ran = f"onemind.version={v}" in seg or f"version={v} cmdline" in seg or f"slot=A version={v}" in seg
        ok = (rc == 0 and bn == "OneMind-A" and g == ("mark-good", "B", 2) and not ran
              and "UNLOCK OK method=tpm2" in seg and "SecureBoot=1 SetupMode=0" in seg)
        record(tid, ok, f"install rc={rc} BootNext={bn} new-kernel-ran={ran} gate={g} firmware={fw[:2]}")
    vm.stop()

    # T6 same disk + same TPM, Secure Boot switched off -> TPM must refuse
    vm.mark("T6 Secure Boot OFF, same TPM: data must stay locked")
    vars_off = f"{a.run}/OVMF_VARS_off.fd"
    subprocess.run(["virt-fw-vars", "--input", vars_sb, "--output", vars_off,
                    "--set-false", "SecureBootEnable"], check=True, capture_output=True)
    i = vm.here(); vm.start(vars_off)
    g = vm.gate(); vm.shell(); st = state(vm, "T6"); seg = vm.since(i)
    ok = ("SecureBoot=0" in seg and "UNLOCK FAILED" in seg and "UNLOCK OK" not in seg
          and g[0] != "mark-good" and "Please enter passphrase" not in seg)
    record("T6", ok, f"gate={g} unlock-failed={'UNLOCK FAILED' in seg}")
    vm.stop()

    # T6b (informational): Secure Boot back on -> unlock works again
    vm.mark("T6b Secure Boot back ON: unlock again")
    i = vm.here(); vm.start(vars_sb); g = vm.gate(); vm.shell(); state(vm, "T6b"); seg = vm.since(i)
    print(f"===> T6b (info): gate={g} unlock={'UNLOCK OK method=tpm2' in seg}", flush=True)
    vm.stop()

    rb = all(bonus.values())
    RESULTS.append(("T7 (bonus)", "PASS" if rb else "FAIL", str(bonus)))
    print(f"===> T7 (bonus): {'PASS' if rb else 'FAIL'} {bonus}", flush=True)
    vm.mark(f"SUMMARY total {time.time()-t0:.0f}s")
    for r in RESULTS:
        vm.mark(" | ".join(r))
    sys.exit(0 if all(r[1] == "PASS" for r in RESULTS if not r[0].startswith(("T7", "T9"))) else 1)


if __name__ == "__main__":
    main()
