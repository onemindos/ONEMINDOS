#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, Secure Boot and signed UKI (SB1-SB4). Criteria: test/qemu/CRITERIA-SECUREBOOT.md
(pre-registered; never edited to make a result pass). Reuses run-tests.py's VM driver.

Input is one disk built with `assemble.py ... --sb-key K --sb-cert C` (make secureboot-image). This script makes
its own throwaway PK, KEK and db, enrols them in a copy of OVMF's variable store, and boots copies of the disk.
No real key is read or written. Runs in the tools container:

  python3 -I secureboot.py --disk disk.img --keys DIR --work DIR --log serial.log [--results r.json]
  (--keys: the directory with db.key and db.crt that signed the image; PK and KEK are made here)
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
RESULTS = []


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


class SBVM(battery.VM):
    """The battery's VM driver with one disk and Secure Boot firmware."""

    def __init__(self, work, logf, disk, varsfile):
        super().__init__("x86_64-efi", work, logf, work)
        self.disk, self.vars = disk, varsfile

    def start(self):
        c = self.cfg
        cmd = [c["qemu"], "-machine", "q35,smm=on", "-global", "driver=cfi.pflash01,property=secure,value=on",
               "-accel", self.accel, "-cpu", self.cpu, "-smp", "4", "-m", "3072", "-nodefaults", "-display", "none",
               "-vga", "none", "-nic", "user,model=virtio-net-pci,restrict=on", "-device", "i6300esb",
               "-action", "watchdog=reset",
               "-drive", f"if=pflash,format=raw,readonly=on,file={CODE}",
               "-drive", f"if=pflash,format=raw,file={self.vars}",
               "-drive", f"if=virtio,format=raw,cache=writeback,file={self.disk}",
               "-serial", "stdio", "-monitor", "none"]
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
    ap.add_argument("--kernel-only", action="store_true",
                    help="harness self-test on an image with no usable root: SB1 only waits for the kernel to start "
                         "and is reported as SELFTEST, never PASS")
    a = ap.parse_args()
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

    def boot(tid, disk):
        vs = os.path.join(a.work, f"VARS-{tid}.fd"); shutil.copy(enrolled, vs)
        vm = SBVM(a.work, logf, disk, vs); vm.mark(f"{tid}: boot"); vm.start()
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
        finally:
            if a.results:
                json.dump({"board": "x86_64-efi", "results": RESULTS, "accel": accel, "cpus": os.cpu_count()},
                          open(a.results, "w"), indent=1)
    sys.exit(0 if RESULTS and all(r["verdict"] in ("PASS", "SELFTEST") for r in RESULTS) else 1)


if __name__ == "__main__":
    main()
