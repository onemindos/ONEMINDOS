#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, Secure Boot and signed UKI (SB1-SB7). Criteria: test/qemu/CRITERIA-SECUREBOOT.md
(pre-registered; never edited to make a result pass). Reuses run-tests.py's VM driver.

Input is one disk built with `assemble.py ... --boot efi` and `--sb-key K --sb-cert C`, and a bundles disk with one
bundle that carries the signed UKIs (make secureboot-image, test/qemu/secureboot-image.sh). This script makes its own
throwaway PK, KEK and db, enrols them in a copy of OVMF's variable store, and boots copies of the disk.
No real key is read or written. Runs in the tools container:

  python3 -I secureboot.py --disk disk.img --keys DIR --work DIR --log serial.log [--results r.json]
                           [--bundles bundles.img]   (default: bundles.img next to the disk; SB5-SB7 need it)
  (--keys: the directory with db.crt, the certificate that signed the image; PK and KEK are made here)
"""
import argparse, importlib.util, json, os, platform, re, shutil, subprocess, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "os", "assemble"))
import uki  # noqa: E402

_spec = importlib.util.spec_from_file_location("battery", os.path.join(HERE, "run-tests.py"))
battery = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(battery)

# Secure Boot needs the firmware build with the SB code, and q35 with SMM (variables are guarded by SMM).
CODE = os.environ.get("ONEMIND_FW_CODE", "/usr/share/OVMF/OVMF_CODE_4M.secboot.fd")
VARS = os.environ.get("ONEMIND_FW_VARS", "/usr/share/OVMF/OVMF_VARS_4M.fd")
STARTED = r"EFI stub:|Loading, please wait|Welcome to|systemd\[1\]|Kernel panic|ONEMIND-FIRSTBOOT|HEALTH-GATE"
SB_ON = r"EFI stub: UEFI Secure Boot is enabled"
REFUSED = r"Access Denied|Security Violation|cannot load image|Image .* failed to load|Verification failed"
WATCH = 240
GATE_WAIT = 1500
INSTALL_WAIT = 2400
SB5_BUNDLE = "good.raucb"
SB6_BUNDLE = "bad-k3s.raucb"       # version 3: k3s exits at start, the health gate rejects slot B
SB7_BUNDLE = "bad-boot.raucb"      # version 5: PID 1 exits, the kernel panics in slot B's one trial boot
BAD_BOOT_MARK = "BAD-BOOT: broken init exiting"
BOOTED = r"rauc[.]slot=[AB]|Booted from: [^(]*[(]\w+[)]"     # the booted slot as the kernel and RAUC name it
RESULTS = []


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


class SBVM(battery.VM):
    """The battery's VM driver with one disk and Secure Boot firmware."""

    def __init__(self, work, logf, disk, varsfile, bundles=None):
        super().__init__("x86_64-efi", work, logf, work)
        self.disk, self.vars, self.bundles = disk, varsfile, bundles

    def start(self):
        c = self.cfg
        cmd = [c["qemu"], "-machine", "q35,smm=on", "-global", "driver=cfi.pflash01,property=secure,value=on",
               "-accel", self.accel, "-cpu", self.cpu, "-smp", "4", "-m", "3072", "-nodefaults", "-display", "none",
               "-vga", "none", "-nic", "user,model=virtio-net-pci,restrict=on", "-device", "i6300esb",
               "-action", "watchdog=reset",
               "-drive", f"if=pflash,format=raw,readonly=on,file={CODE}",
               "-drive", f"if=pflash,format=raw,file={self.vars}",
               "-drive", f"if=virtio,format=raw,cache=writeback,file={self.disk}"]
        if self.bundles:   # SB5: the bundles disk (ext4 "onemind-test"), read-only, as in the T-battery
            cmd += ["-drive", f"if=virtio,format=raw,readonly=on,file={self.bundles}"]
        cmd += ["-serial", "stdio", "-monitor", "none"]
        self.mark(f"QEMU START {' '.join(cmd)}")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, bufsize=0)
        threading.Thread(target=self._reader, daemon=True).start()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()


def sh(*cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def esp_offset(disk, label):
    """Byte offset of the partition with this GPT name (sgdisk), so mtools can open it inside the disk file."""
    for n in range(1, 12):
        info = subprocess.run(["sgdisk", "-i", str(n), disk], capture_output=True, text=True).stdout
        if f"'{label}'" in info:
            return int(re.search(r"First sector: (\d+)", info).group(1)) * 512
    raise SystemExit(f"ERROR: no partition {label} in {disk}")


def mtools(disk, label):
    return f"{disk}@@{esp_offset(disk, label)}"


def fresh_disk(src, work, name):
    dst = os.path.join(work, name)
    sh("cp", "--sparse=always", src, dst)
    return dst


def parse_efi(text):
    """efibootmgr output -> {"BootCurrent", "BootNext", "BootOrder": [...], "A"/"B": boot number, "A_line"/"B_line"}.
    Entry labels are the RAUC bootnames; the label ends at the tab before the device path (as RAUC reads it)."""
    text = battery.strip_escapes(text)
    st = {"BootCurrent": None, "BootNext": None, "BootOrder": [], "A": None, "B": None, "A_line": "", "B_line": ""}
    for k in ("BootCurrent", "BootNext"):
        m = re.search(rf"^{k}: ([0-9A-Fa-f]{{4}})\s*$", text, re.M)
        st[k] = m.group(1).upper() if m else None
    m = re.search(r"^BootOrder: (\S+)", text, re.M)
    st["BootOrder"] = [x.upper() for x in m.group(1).split(",")] if m else []
    for m in re.finditer(r"^Boot([0-9A-Fa-f]{4})[* ] (.+)$", text, re.M):
        # The label ends at the tab before the device path; a console that expands tabs leaves spaces instead.
        label = re.split(r"\t|\s{2,}|\s+(?=HD\()", m.group(2))[0].strip()
        if label in ("A", "B") and st[label] is None:
            st[label], st[label + "_line"] = m.group(1).upper(), m.group(0).strip()
    return st


def sb5_verdict(installed, gate1, gate2, after):
    """SB5 PASS rule (CRITERIA-SECUREBOOT.md section 4): A committed first, `rauc install` set BootNext to B's entry,
    then slot B booted its own UKI (BootCurrent = B, loader onemind-B.efi), the gate committed it as version 2 and
    B leads BootOrder. Secure Boot being on in that boot is checked by the caller (the EFI stub line)."""
    return (gate1[0].startswith("committed") and gate1[1] == "A"
            and installed["B"] is not None and installed["BootNext"] == installed["B"]
            and tuple(gate2) == ("mark-good", "B", "2")
            and after["B"] is not None and after["BootCurrent"] == after["B"]
            and "onemind-B.efi" in after["B_line"]
            and after["BootOrder"][:1] == [after["B"]])


def back_on_a(installed, gate1, gate3, after):
    """The shared tail of SB6 and SB7: slot A committed first, `rauc install` set BootNext to B's entry, and after the
    failed trial the box is on slot A again (BootCurrent = A's entry, A leads BootOrder, the gate committed or fell
    back to A at version 1)."""
    return (gate1[0].startswith("committed") and gate1[1] == "A"
            and installed["B"] is not None and installed["BootNext"] == installed["B"]
            and after["A"] is not None and after["BootCurrent"] == after["A"]
            and after["BootOrder"][:1] == [after["A"]]
            and gate3[1:] == ("A", "1"))


def sb6_verdict(installed, gate1, gate2, gate3, after):
    """SB6 PASS rule (CRITERIA-SECUREBOOT.md section 5): the gate rejected slot B (`mark-bad`, version 3) and the next
    boot, back on A, committed version 1. Secure Boot being on in all three boots is checked by the caller."""
    return (back_on_a(installed, gate1, gate3, after) and tuple(gate2) == ("mark-bad", "B", "3")
            and gate3[0] == "committed-boot")


def sb7_verdict(installed, gate1, gate3, after, panics):
    """SB7 PASS rule (CRITERIA-SECUREBOOT.md section 5): slot B's trial boot panicked exactly once (BootNext is used up
    by the firmware, so there is no second try) and A came back, with the gate's `fell-back` decision for version 1."""
    return back_on_a(installed, gate1, gate3, after) and gate3[0] == "fell-back" and panics == 1


def efi_state(vm):
    _, out = vm.run("efibootmgr -v")
    return parse_efi(out)


def short(st):
    return {k: st[k] for k in ("BootCurrent", "BootNext", "BootOrder", "A", "B")}


def watch_refusal(vm, seconds=WATCH):
    """(refused text seen, started match) after watching the console for `seconds`."""
    time.sleep(seconds)
    with vm.lock:
        text = vm.buf
    return bool(re.search(REFUSED, text)), re.search(STARTED, text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disk", required=True); ap.add_argument("--keys", required=True)
    ap.add_argument("--work", required=True); ap.add_argument("--log", required=True)
    ap.add_argument("--results"); ap.add_argument("--only", default="")
    ap.add_argument("--bundles", help="bundles disk for SB5 (default: bundles.img next to --disk)")
    ap.add_argument("--kernel-only", action="store_true",
                    help="harness self-test on an image with no usable root: SB1 only waits for the kernel to start "
                         "and is reported as SELFTEST, never PASS")
    a = ap.parse_args()
    a.bundles = a.bundles or os.path.join(os.path.dirname(os.path.abspath(a.disk)), "bundles.img")
    os.makedirs(a.work, exist_ok=True)
    accel, _ = battery.accel_for(battery.BOARDS["x86_64-efi"])
    print(f"accel={accel} cpus={os.cpu_count()}", flush=True)

    # Throwaway PK + KEK are made here; the db is the image's signing certificate (copied in, key not needed).
    kd = os.path.join(a.work, "keys"); os.makedirs(kd, exist_ok=True)
    pk = uki.make_test_keys(os.path.join(kd, "own"))
    for n in ("PK", "KEK"):
        shutil.copy(pk[n][1], os.path.join(kd, f"{n}.crt"))
    shutil.copy(os.path.join(a.keys, "db.crt"), os.path.join(kd, "db.crt"))
    enrolled = os.path.join(a.work, "VARS-enrolled.fd")
    uki.enroll(VARS, enrolled, kd)
    wrong = uki.make_test_keys(os.path.join(a.work, "wrong"))["db"]   # a key that is NOT in db
    want = set(a.only.split(",")) - {""}

    def boot(tid, disk, bundles=None):
        vs = os.path.join(a.work, f"VARS-{tid}.fd"); shutil.copy(enrolled, vs)
        vm = SBVM(a.work, logf, disk, vs, bundles); vm.mark(f"{tid}: boot"); vm.start()
        return vm

    with open(a.log, "w") as logf:
        try:
            if not want or "SB1" in want:
                vm = boot("SB1", fresh_disk(a.disk, a.work, "sb1.img"))
                try:
                    if a.kernel_only:
                        m = vm.expect(STARTED, 600)
                        vm.expect(SB_ON, 60)
                        record("SB1", "SELFTEST", f"kernel started, Secure Boot on ({m.group(0)}) accel={accel}")
                        raise StopIteration
                    vm.expect(SB_ON, 600)
                    slot_ok = vm.wait_gate(GATE_WAIT)
                    record("SB1", slot_ok[0].startswith("committed") and slot_ok[1] == "A",
                           f"secure_boot_on=True gate={vm.last_gate!r} accel={accel}")
                except StopIteration:
                    pass
                except (TimeoutError, RuntimeError) as e:
                    record("SB1", False, f"{e} accel={accel}")
                vm.stop()

            def refusal(tid, mutate):
                d = fresh_disk(a.disk, a.work, f"{tid.lower()}.img")
                mutate(d)
                vm = boot(tid, d)
                refused, started = watch_refusal(vm)
                vm.stop()
                record(tid, refused and not started,
                       f"refusal_text={refused} started={started.group(0) if started else None} accel={accel}")

            ESP, BOOTFILE = "onemind-esp", "::/EFI/BOOT/BOOTX64.EFI"

            def fetch(d, name):
                tmp = os.path.join(a.work, name)
                sh("mcopy", "-o", "-n", "-i", mtools(d, ESP), BOOTFILE, tmp)
                return tmp

            def put(d, tmp):
                sh("mcopy", "-o", "-i", mtools(d, ESP), tmp, BOOTFILE)

            def flip(d):   # one byte in the middle of the signed UKI
                tmp = fetch(d, "boot-flip.efi")
                with open(tmp, "r+b") as f:
                    f.seek(os.path.getsize(tmp) // 2); b = f.read(1); f.seek(-1, 1); f.write(bytes([b[0] ^ 0xFF]))
                put(d, tmp)

            def resign(d):   # signature from a key that is not in db
                tmp = fetch(d, "boot-wrong.efi")
                sh("sbattach", "--remove", tmp)
                uki.sign_efi(tmp, tmp + ".s", wrong[0], wrong[1])
                put(d, tmp + ".s")

            def unsigned(d):
                tmp = fetch(d, "boot-unsigned.efi")
                sh("sbattach", "--remove", tmp)
                put(d, tmp)

            for tid, fn in (("SB2", flip), ("SB3", resign), ("SB4", unsigned)):
                if not want or tid in want:
                    refusal(tid, fn)

            # SB5 (#148 slice 1): slot B boots its own signed UKI, chosen by RAUC's efi backend (BootNext).
            if (not want or "SB5" in want) and not a.kernel_only:
                if not os.path.exists(a.bundles):
                    record("SB5", "BLOCKED", f"no bundles disk at {a.bundles} (make secureboot-image builds it)")
                else:
                    vm = boot("SB5", fresh_disk(a.disk, a.work, "sb5.img"), a.bundles)
                    try:
                        vm.expect(SB_ON, 600)
                        gate1 = vm.wait_gate(GATE_WAIT)
                        first = vm.last_gate
                        if not (gate1[0].startswith("committed") and gate1[1] == "A"):
                            raise RuntimeError(f"slot A did not commit first: {first!r}")
                        vm.shell_ready()
                        before = efi_state(vm)
                        rc, out = battery.install(vm, SB5_BUNDLE, INSTALL_WAIT)
                        if rc:
                            raise RuntimeError(f"rauc install {SB5_BUNDLE} rc={rc}: {out.strip()[-300:]!r}")
                        installed = efi_state(vm)
                        vm.send("systemctl reboot")
                        vm.expect(SB_ON, 600)
                        gate2 = vm.wait_gate(GATE_WAIT)
                        second = vm.last_gate
                        vm.shell_ready()
                        after = efi_state(vm)
                        _, cmd = vm.run("grep -o 'rauc\\.slot=[AB]' /proc/cmdline; rauc status 2>&1 | grep -m1 'Booted from'")
                        record("SB5", sb5_verdict(installed, gate1, gate2, after),
                               f"gate1={first!r} before={short(before)} after_install={short(installed)} "
                               f"secure_boot_on_after_reboot=True gate2={second!r} after={short(after)} "
                               f"b_entry={after['B_line']!r} booted={re.findall(BOOTED, cmd)} "
                               f"accel={accel}")
                    except (TimeoutError, RuntimeError) as e:
                        record("SB5", False, f"{e} accel={accel}")
                    vm.stop()
            # SB6 and SB7 (#148, rollback under Secure Boot): a bad update must come back to slot A.
            def failed_update(tid, bundle):
                vm = boot(tid, fresh_disk(a.disk, a.work, f"{tid.lower()}.img"), a.bundles)
                try:
                    vm.expect(SB_ON, 600)
                    gate1 = vm.wait_gate(GATE_WAIT)
                    if not (gate1[0].startswith("committed") and gate1[1] == "A"):
                        raise RuntimeError(f"slot A did not commit first: {vm.last_gate!r}")
                    first = vm.last_gate
                    vm.shell_ready()
                    rc, out = battery.install(vm, bundle, INSTALL_WAIT)
                    if rc:
                        raise RuntimeError(f"rauc install {bundle} rc={rc}: {out.strip()[-300:]!r}")
                    installed = efi_state(vm)
                    seg = vm.here()
                    vm.send("systemctl reboot")
                    return vm, gate1, first, installed, seg
                except BaseException:
                    vm.stop()
                    raise

            if (not want or "SB6" in want) and not a.kernel_only and os.path.exists(a.bundles):
                try:
                    vm, gate1, first, installed, seg = failed_update("SB6", SB6_BUNDLE)
                    try:
                        vm.expect(SB_ON, 600)                    # slot B's own signed UKI starts (BootNext)
                        gate2 = vm.wait_gate(GATE_WAIT * 2); second = vm.last_gate   # the gate rejects it, reboots
                        vm.expect(SB_ON, 900)                    # and the firmware returns to slot A, still signed
                        gate3 = vm.wait_gate(GATE_WAIT); third = vm.last_gate
                        vm.shell_ready()
                        after = efi_state(vm)
                        record("SB6", sb6_verdict(installed, gate1, gate2, gate3, after),
                               f"gate1={first!r} after_install={short(installed)} secure_boot_on_all_boots=True "
                               f"gate2={second!r} gate3={third!r} after={short(after)} accel={accel}")
                    finally:
                        vm.stop()
                except (TimeoutError, RuntimeError) as e:
                    record("SB6", False, f"{e} accel={accel}")
            elif (not want or "SB6" in want) and not a.kernel_only:
                record("SB6", "BLOCKED", f"no bundles disk at {a.bundles}")

            if (not want or "SB7" in want) and not a.kernel_only and os.path.exists(a.bundles):
                try:
                    vm, gate1, first, installed, seg = failed_update("SB7", SB7_BUNDLE)
                    try:
                        vm.expect(SB_ON, 600)                    # slot B starts and panics ...
                        vm.expect(SB_ON, 900)                    # ... the firmware has used BootNext: A, still signed
                        gate3 = vm.wait_gate(GATE_WAIT); third = vm.last_gate
                        panics = vm.since(seg).count(BAD_BOOT_MARK)
                        vm.shell_ready()
                        after = efi_state(vm)
                        record("SB7", sb7_verdict(installed, gate1, gate3, after, panics),
                               f"gate1={first!r} after_install={short(installed)} panics={panics} "
                               f"gate3={third!r} after={short(after)} accel={accel}")
                    finally:
                        vm.stop()
                except (TimeoutError, RuntimeError) as e:
                    record("SB7", False, f"{e} accel={accel}")
            elif (not want or "SB7" in want) and not a.kernel_only:
                record("SB7", "BLOCKED", f"no bundles disk at {a.bundles}")
        finally:
            if a.results:
                json.dump({"board": "x86_64-efi", "results": RESULTS, "accel": accel, "cpus": os.cpu_count()},
                          open(a.results, "w"), indent=1)
    sys.exit(0 if RESULTS and all(r["verdict"] in ("PASS", "SELFTEST") for r in RESULTS) else 1)


if __name__ == "__main__":
    main()
