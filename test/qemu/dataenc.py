#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, encrypted data (E1-E4). Criteria: test/qemu/CRITERIA-DATAENC.md (pre-registered; never
edited to make a result pass). Reuses run-tests.py's VM driver and adds a software TPM (swtpm).

Input: fixtures made with `make fixtures DATA_FS=luks2` (the data partition is blank in the image). The disk is
copied into --work. Runs in the tools container:

  python3 -I dataenc.py --board x86_64-efi --fixtures DIR --work DIR --log serial.log [--results r.json]
"""
import argparse, importlib.util, json, os, platform, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("battery", os.path.join(HERE, "run-tests.py"))
battery = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(battery)

KEY = re.compile(r"ONEMIND-DATA-CRYPT: RECOVERY KEY[^\n]*?: ([cbdefghijklnrtuv]{8}(?:-[cbdefghijklnrtuv]{8}){7})")
PROMPT = r"(?i)(please enter passphrase for disk onemind-data|enter passphrase)"
RESULTS = []


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


class Tpm:
    """One software TPM 2.0 (its own state directory = its own endorsement and storage keys)."""
    def __init__(self, root, name):
        self.dir = os.path.join(root, name)
        shutil.rmtree(self.dir, ignore_errors=True)
        os.makedirs(self.dir)
        self.sock = os.path.join(self.dir, "sock")
        subprocess.run(["swtpm", "socket", "--tpm2", "--tpmstate", f"dir={self.dir}", "--ctrl",
                        f"type=unixio,path={self.sock}", "--pid", f"file={self.dir}/pid", "--daemon",
                        "--flags", "not-need-init,startup-clear"], check=True)

    def args(self):
        return ["-chardev", f"socket,id=chrtpm,path={self.sock}", "-tpmdev", "emulator,id=tpm0,chardev=chrtpm",
                "-device", "tpm-tis,tpmdev=tpm0"]

    def stop(self):
        try:
            os.kill(int(open(f"{self.dir}/pid").read()), 15)
        except (OSError, ValueError):
            pass


def make_work(fx, work):
    os.makedirs(work, exist_ok=True)
    subprocess.run(["cp", "--sparse=always", os.path.join(fx, "disk.img"), os.path.join(work, "disk.img")], check=True)
    dst = os.path.join(work, "bundles.img")
    if os.path.lexists(dst):
        os.remove(dst)
    os.symlink(os.path.abspath(os.path.join(fx, "bundles.img")), dst)


def boot(vm, tpm, tag):
    vm.extra_args = tpm.args() if tpm else []
    vm.restart(tag) if vm.proc else vm.start()


def power_off(vm):
    vm.poweroff()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=["x86_64-efi", "vm"])
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--results")
    a = ap.parse_args()
    make_work(a.fixtures, a.work)
    logf = open(a.log, "w")
    t0 = time.time()
    vm = battery.VM(a.board, a.work, logf, a.work)
    env = {"board": a.board, "accel": vm.accel, "cpu": vm.cpu, "host_cpus": os.cpu_count(), "host_machine": platform.machine()}
    print(f"ENV {json.dumps(env)}", flush=True)
    tpm1, tpm2 = Tpm(a.work, "tpm1"), Tpm(a.work, "tpm2")
    marker = "head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \\n' > /data/onemind/e-marker; sync; " \
             "echo MARK=$(sha256sum /data/onemind/e-marker | cut -c1-64)"
    check = "echo MARK=$(sha256sum /data/onemind/e-marker 2>&1 | cut -c1-64)"
    rc = 1
    vm.failfast = False
    try:
        # E1: first boot, blank partition, TPM present.
        vm.mark("E1 first boot encrypts /data (swtpm #1)")
        boot(vm, tpm1, "E1 boot")
        recovery = KEY.search(vm.expect(KEY.pattern, 900).group(0)).group(1)
        vm.pos = 0
        vm.wait_gate(); vm.shell_ready()
        _, out = vm.run("echo SRC=$(findmnt -n -o SOURCE /data); "
                        "dev=$(cryptsetup status onemind-data | sed -n 's/^ *device: *//p'); "
                        "echo RAW=$(blkid -p -o value -s TYPE $dev); "
                        "echo DUMP=$(cryptsetup luksDump $dev | grep -cE 'systemd-tpm2|systemd-recovery'); "
                        "echo FILE=$(stat -c %a /run/onemind/data-recovery-key 2>&1); "
                        "echo JOURNALKEY=$(journalctl -b --no-pager | grep -c " + recovery + ")")
        g = lambda k, o: (re.findall(rf"^{k}=(\S*)\s*$", o, re.M) or [""])[-1]
        _, o2 = vm.run(marker)
        mark = g("MARK", o2)
        record("E1", "/dev/mapper/onemind-data" in g("SRC", out) and g("DUMP", out) == "2" and g("FILE", out) == "600" and g("RAW", out) == "crypto_LUKS"
               and g("JOURNALKEY", out) == "0"
               and len(mark) == 64,
               f"data_source={g('SRC', out)} tpm2_and_recovery_tokens={g('DUMP', out)} keyfile_mode={g('FILE', out)} "
               f"key_in_journal={g('JOURNALKEY', out)} raw_type_probe={g('RAW', out)}")
        power_off(vm)

        # E2: same disk, same TPM: unlocks with nobody there.
        vm.mark("E2 reboot unlocks unattended (swtpm #1)")
        boot(vm, tpm1, "E2 boot")
        seg = vm.here()
        vm.expect(r"ONEMIND-DATA-CRYPT: data disk unlocked \((\w[\w-]*)\)", 900)
        vm.wait_gate(); vm.shell_ready()
        s = vm.since(seg)
        _, o = vm.run(check)
        record("E2", g("MARK", o) == mark and "unlocked (tpm2)" in s and not re.search(PROMPT, s),
               f"marker_kept={g('MARK', o) == mark} unlocked_with_tpm2={'unlocked (tpm2)' in s} prompted={bool(re.search(PROMPT, s))}")
        power_off(vm)

        # E3: the disk moved to another machine (a different TPM): it must ask, and the recovery key must work.
        vm.mark("E3 moved disk asks for the recovery key (swtpm #2)")
        boot(vm, tpm2, "E3 boot")
        seg = vm.here()
        vm.expect(PROMPT, 900)
        vm.send(recovery)
        vm.expect(r"ONEMIND-DATA-CRYPT: data disk unlocked \((recovery-key)\)", 600)
        vm.wait_gate(); vm.shell_ready()
        _, o = vm.run(check)
        record("E3", g("MARK", o) == mark, f"prompted=True marker_kept={g('MARK', o) == mark}")
        power_off(vm)

        # E4: no TPM at all and a wrong key: stays locked, recovery mode, nothing formatted.
        vm.mark("E4 no TPM, wrong key: stays locked, never formats")
        boot(vm, None, "E4 boot")
        vm.expect(PROMPT, 900)
        for _ in range(3):
            vm.send("wrong-wrong-wrong")
            time.sleep(8)
        vm.expect(r"ONEMIND-DATA-CRYPT: the data disk is locked", 600)
        vm.expect_line(battery.RECOV, 600)
        vm.send(""); vm.expect(r"root@onemind:~# ", 300)
        _, o = vm.run("echo TYPE=$(blkid -p -o value -s TYPE $(lsblk -ndo PATH,PARTLABEL | awk '$2==\"onemind-data\"{print $1}' | head -1)); "
                      "echo DATAMNT=$(mountpoint -q /data && echo yes || echo no)")
        record("E4", g("TYPE", o) == "crypto_LUKS" and g("DATAMNT", o) == "no",
               f"raw_type={g('TYPE', o)} data_mounted={g('DATAMNT', o)}")
        rc = 0
    except (TimeoutError, RuntimeError) as e:
        record("HARNESS", False, f"aborted: {e}")
    if vm.proc and vm.proc.poll() is None:
        vm.kill()
    tpm1.stop(); tpm2.stop()
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env["accel"]))
    for r in RESULTS:
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    logf.close()
    if a.results:
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-DATAENC.md",
                   "results": RESULTS}, open(a.results, "w"), indent=2)
    return 0 if rc == 0 and RESULTS and all(r["verdict"] == "PASS" for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
