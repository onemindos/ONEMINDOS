#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind QEMU battery, encrypted and btrfs data. Criteria: test/qemu/CRITERIA-DATAENC.md (E1-E4) and
test/qemu/CRITERIA-DATABTRFS.md (E5-E7) and test/qemu/CRITERIA-DATARESET.md (R1-R2), all pre-registered; never edited to make a result pass. Reuses
run-tests.py's VM driver and adds a software TPM (swtpm).

Input: fixtures made with `make fixtures` (the data partition is blank in the image, the default for x86_64-efi since
D-020). The disk is copied into --work (E5 and E7 copy it again, to start from a blank partition). Runs in the tools
container:

  python3 -I dataenc.py --board x86_64-efi --fixtures DIR --work DIR --log serial.log [--results r.json]
"""
import argparse, base64, importlib.util, json, os, platform, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("battery", os.path.join(HERE, "run-tests.py"))
battery = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(battery)

# #1118 (CRITERIA-DATAENC.md section 4): the key is never on the serial console by default. The console says the key was
# made (KEY_MADE); the harness reads the key from RAM over the test shell (read_key) and checks the boot's serial output
# for any key (key_on_serial).
KEY_MADE = r"ONEMIND-DATA-CRYPT: recovery key made"
KEY_RX = re.compile(r"[cbdefghijklnrtuv]{8}(?:-[cbdefghijklnrtuv]{8}){7}")
# systemd 257 asks "Please enter recovery key for disk ..." when the volume has a recovery-key token and "passphrase" when it
# has none (a passphrase-only volume): both are the prompt for the disk's key.
PROMPT = r"(?i)(please enter (passphrase|recovery key) for disk onemind-data|enter passphrase)"
RESULTS = []


def record(tid, ok, detail):
    verdict = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    RESULTS.append({"test": tid, "verdict": verdict, "detail": detail})
    print(f"===> {tid}: {verdict} {detail}", flush=True)


class Tpm:
    """One software TPM 2.0 (its own state directory = its own endorsement and storage keys).

    swtpm exits when QEMU shuts the TPM down (every power-off), taking its socket with it, so boot() calls start()
    again before each QEMU start: the same state directory is the same TPM, with the keys sealed by an earlier boot."""
    def __init__(self, root, name):
        self.dir = os.path.join(root, name)
        shutil.rmtree(self.dir, ignore_errors=True)
        os.makedirs(self.dir)
        self.sock = os.path.join(self.dir, "sock")
        self.start()

    def alive(self):
        try:
            os.kill(int(open(f"{self.dir}/pid").read()), 0)
        except (OSError, ValueError):
            return False
        return os.path.exists(self.sock)

    def start(self):
        if self.alive():
            return
        for f in (self.sock, f"{self.dir}/pid"):
            try:
                os.remove(f)
            except OSError:
                pass
        subprocess.run(["swtpm", "socket", "--tpm2", "--tpmstate", f"dir={self.dir}", "--ctrl",
                        f"type=unixio,path={self.sock}", "--pid", f"file={self.dir}/pid", "--daemon",
                        "--flags", "not-need-init,startup-clear"], check=True)
        for _ in range(100):                      # --daemon returns once it forked; the socket appears a moment later
            if os.path.exists(self.sock):
                break
            time.sleep(0.1)

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


def guest_vals(vm, cmd, timeout=180):
    """Run a shell snippet that prints K=V lines; return {K: V} (last value of each key)."""
    _, out = vm.run(cmd, timeout)
    return dict(re.findall(r"^([A-Z0-9_]+)=(.*?)\s*$", out, re.M))


def read_key(vm):
    """The recovery key from /run/onemind/data-recovery-key (RAM), or "" when it is missing or malformed."""
    k = guest_vals(vm, "echo RKEY=$(cat /run/onemind/data-recovery-key 2>/dev/null)").get("RKEY", "")
    return k if KEY_RX.fullmatch(k) else ""


def key_on_serial(text, key=""):
    """True when serial output carries a recovery key: the given one, any eight-groups modhex key, or the key line."""
    return bool((key and key in text) or KEY_RX.search(text) or "RECOVERY KEY" in text)


MARK_CMD = ("head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \\n' > {path}; sync; "
            "echo {name}=$(sha256sum {path} | cut -c1-64)")
SUBVOLS_CMD = ("echo SRC=$(findmnt -n -o SOURCE /data); echo RAW=$(blkid -p -o value -s TYPE /dev/disk/by-partlabel/onemind-data); "
               "echo LUKS=$(cryptsetup isLuks /dev/disk/by-partlabel/onemind-data && echo yes || echo no); "
               "echo DEF=$(btrfs subvolume get-default /data | sed 's/.*path //'); "
               "echo SUBS=$(btrfs subvolume list -a /data | sed 's/.*path //; s#^<FS_TREE>/##' | sort | tr '\\n' ,); "
               "echo STOR=$(findmnt -n -o SOURCE,OPTIONS /data/storage | grep -c 'subvol=/@storage'); "
               "echo FAILED=$(systemctl --failed --no-legend | wc -l)")


def sizes(vm):
    """Disk, data partition, unlocked volume and filesystem sizes in bytes, and how far the partition ends from the end."""
    v = guest_vals(vm, "D=$(lsblk -dnbo SIZE /dev/vda); PN=$(lsblk -nro NAME,PARTLABEL /dev/vda | awk '$2==\"onemind-data\"{print $1}'); "
                       "echo DISK=$D; echo PSTART=$(cat /sys/class/block/$PN/start); echo PSIZE=$(cat /sys/class/block/$PN/size); "
                       "echo MAP=$(blockdev --getsize64 /dev/mapper/onemind-data 2>/dev/null); "
                       "echo FS=$(stat -f -c '%b %S' /data | awk '{print $1*$2}'); "
                       "echo GREW=$(journalctl -b --no-pager -u onemind-data-extend.service | grep -c 'growing /dev/')")
    n = {k: int(x) if x.isdigit() else None for k, x in v.items()}
    if None not in (n.get("DISK"), n.get("PSTART"), n.get("PSIZE")):
        n["TAIL"] = (n["DISK"] // 512 - 33) - (n["PSTART"] + n["PSIZE"])      # sectors between the partition and the backup table
        n["PBYTES"] = n["PSIZE"] * 512
    return n


def fresh_vm(a, logf, tag, grow_to=None):
    """A VM on its own copy of the fixtures disk (blank data partition), optionally written to a bigger disk."""
    w = a.work + "-" + tag
    make_work(a.fixtures, w)
    if grow_to:
        with open(os.path.join(w, "disk.img"), "r+b") as f:
            f.truncate(grow_to)
    return battery.VM(a.board, w, logf, w), w


def boot(vm, tpm, tag):
    if tpm:
        tpm.start()                                # swtpm quit with the last QEMU (see Tpm); same state, same TPM
    vm.extra_args = tpm.args() if tpm else []
    vm.restart(tag) if vm.proc else vm.start()


def power_off(vm):
    vm.poweroff()


def e57(a, logf, env):
    """E5 (no TPM: plain btrfs) and E7 (growth on a large disk, encrypted) on fresh copies of the blank-data disk.
    Returns False when a step could not run to its end."""
    ok = True
    # E5: no TPM at all, nobody types: D-020's no-TPM branch.
    vm5, w5, vm7, w7 = None, None, None, None
    try:
        vm5, w5 = fresh_vm(a, logf, "e5")
        vm5.failfast = False
        vm5.mark("E5 no TPM, blank data: plain btrfs, nobody types")
        boot(vm5, None, "E5 boot")
        vm5.expect(r"ONEMIND-DATA-CRYPT: data partition ready \(btrfs, unencrypted\)", 900)
        s5 = vm5.since(0)
        vm5.pos = 0
        vm5.wait_gate(); vm5.shell_ready()
        lay = guest_vals(vm5, SUBVOLS_CMD)
        ptype = guest_vals(vm5, "echo PTYPE=$(lsblk -no PARTTYPE $(readlink -f /dev/disk/by-partlabel/onemind-data))").get("PTYPE", "")
        ma = guest_vals(vm5, MARK_CMD.format(path="/data/onemind/e-marker", name="MA")).get("MA", "")
        mb = guest_vals(vm5, MARK_CMD.format(path="/data/storage/e-marker2", name="MB")).get("MB", "")
        seg = vm5.here(); vm5.send("systemctl reboot"); vm5.pos = seg
        vm5.wait_gate(); s5b = vm5.since(seg); vm5.shell_ready()
        after = guest_vals(vm5, "echo MA=$(sha256sum /data/onemind/e-marker 2>&1 | cut -c1-64); "
                                "echo MB=$(sha256sum /data/storage/e-marker2 2>&1 | cut -c1-64); " + SUBVOLS_CMD)
        subs = lay.get("SUBS", "").split(",")
        record("E5", "making it plain btrfs, NOT encrypted" in s5 and "RECOVERY KEY" not in s5 and "RECOVERY KEY" not in s5b
               and not re.search(PROMPT, s5 + s5b) and lay.get("RAW") == "btrfs" and lay.get("LUKS") == "no"
               and "/dev/mapper" not in lay.get("SRC", "x") and lay.get("DEF") == "@"
               and "@" in subs and "@storage" in subs and "@storage/.snapshots" in subs and "@snapshots" not in subs
               and lay.get("STOR") == "1" and ptype.lower() == "d6bbb545-ec40-5f2a-9cfe-3c397e4d8112"
               and lay.get("FAILED") == "0" and len(ma) == 64 and len(mb) == 64
               and after.get("MA") == ma and after.get("MB") == mb and after.get("STOR") == "1" and after.get("FAILED") == "0",
               f"raw={lay.get('RAW')} luks={lay.get('LUKS')} source={lay.get('SRC')} default={lay.get('DEF')} subvolumes={lay.get('SUBS')} "
               f"storage_mounted={lay.get('STOR')} type_guid={ptype} failed_units={lay.get('FAILED')} "
               f"markers_kept={after.get('MA') == ma and after.get('MB') == mb} after_reboot_storage={after.get('STOR')} failed_after={after.get('FAILED')}")
    except (TimeoutError, RuntimeError, ValueError) as e:
        record("E5", False, f"aborted: {e}")
        ok = False
    if vm5 is not None and vm5.proc and vm5.proc.poll() is None:
        vm5.kill()
    if w5:
        os.path.lexists(os.path.join(w5, "disk.img")) and os.remove(os.path.join(w5, "disk.img"))
    # E7: the image written to a 64 GiB disk, with a TPM: partition, LUKS2 volume and btrfs all grow, nothing fails.
    tpm3 = None
    try:
        tpm3 = Tpm(a.work, "tpm3")
        vm7, w7 = fresh_vm(a, logf, "e7", grow_to=64 << 30)
        vm7.failfast = False
        vm7.mark("E7 growth on a large disk, encrypted (swtpm #3)")
        boot(vm7, tpm3, "E7 boot")
        vm7.expect(KEY_MADE, 900)
        vm7.pos = 0
        vm7.wait_gate(); vm7.shell_ready()
        n1 = sizes(vm7)
        failed1 = guest_vals(vm7, "echo FAILED=$(systemctl --failed --no-legend | wc -l)").get("FAILED")
        m7 = guest_vals(vm7, MARK_CMD.format(path="/data/onemind/e-marker", name="M7")).get("M7", "")
        seg = vm7.here(); vm7.send("systemctl reboot"); vm7.pos = seg
        vm7.expect(r"ONEMIND-DATA-CRYPT: data disk unlocked \((\w[\w-]*)\)", 900)
        vm7.wait_gate(); s7 = vm7.since(seg); vm7.shell_ready()
        n2 = sizes(vm7)
        after = guest_vals(vm7, "echo M7=$(sha256sum /data/onemind/e-marker 2>&1 | cut -c1-64); "
                                "echo FAILED=$(systemctl --failed --no-legend | wc -l)")
        def grown(n):
            return (all(k in n for k in ("DISK", "PSIZE", "MAP", "FS", "TAIL"))
                    and 0 <= n["TAIL"] <= 2048 and n["PBYTES"] > 40 << 30
                    and 0 <= n["PBYTES"] - n["MAP"] <= 32 << 20 and n["FS"] >= 0.98 * n["MAP"])
        first_half = (grown(n1) and n1.get("GREW", 0) >= 1 and failed1 == "0" and grown(n2) and after.get("M7") == m7 and len(m7) == 64
                      and after.get("FAILED") == "0" and "unlocked (tpm2)" in s7 and not re.search(PROMPT, s7)
                      and n2.get("PBYTES") == n1.get("PBYTES") and n2.get("MAP") == n1.get("MAP"))
        # Second half (CRITERIA-DATABTRFS.md section 4): the disk grows again while the box is off; the volume is now
        # opened by systemd-cryptsetup with the TPM, not by the first-boot code.
        power_off(vm7)
        with open(os.path.join(w7, "disk.img"), "r+b") as f:
            f.truncate(80 << 30)
        boot(vm7, tpm3, "E7 boot 3 (disk enlarged to 80 GiB)")
        seg = vm7.here(); vm7.pos = seg
        vm7.expect(r"ONEMIND-DATA-CRYPT: data disk unlocked \((\w[\w-]*)\)", 900)
        vm7.wait_gate(); s7c = vm7.since(seg); vm7.shell_ready()
        n3 = sizes(vm7)
        again = guest_vals(vm7, "echo M7=$(sha256sum /data/onemind/e-marker 2>&1 | cut -c1-64); "
                                "echo FAILED=$(systemctl --failed --no-legend | wc -l)")
        second_half = (grown(n3) and n3.get("DISK", 0) >= 80 << 30 and n3.get("PBYTES", 0) > 56 << 30
                       and n3.get("PBYTES", 0) > n2.get("PBYTES", 0) and n3.get("GREW", 0) >= 1 and again.get("M7") == m7
                       and again.get("FAILED") == "0" and "unlocked (tpm2)" in s7c and not re.search(PROMPT, s7c))
        record("E7", first_half and second_half,
               f"first_boot={n1} failed_units={failed1} after_reboot={n2} marker_kept={after.get('M7') == m7} "
               f"tpm2_unlock={'unlocked (tpm2)' in s7} prompted={bool(re.search(PROMPT, s7))} failed_after={after.get('FAILED')} | "
               f"second_growth_80GiB={n3} marker_kept={again.get('M7') == m7} tpm2_unlock={'unlocked (tpm2)' in s7c} "
               f"prompted={bool(re.search(PROMPT, s7c))} failed={again.get('FAILED')}")
    except (TimeoutError, RuntimeError, ValueError) as e:
        record("E7", False, f"aborted: {e}")
        ok = False
    if vm7 is not None and vm7.proc and vm7.proc.poll() is None:
        vm7.kill()
    if w7:
        os.path.lexists(os.path.join(w7, "disk.img")) and os.remove(os.path.join(w7, "disk.img"))
    if tpm3:
        tpm3.stop()
    return ok

# Writes the ESP marker the owner's approval would write, for the plan this box prints (CRITERIA-DATARESET.md section 1).
ARM_PY = r"""
import datetime as d, json, os, subprocess
p = json.loads(subprocess.check_output(["/usr/bin/onemindd", "host", "plan", "factory-reset"]))
assert p["available"], p.get("refusal")
n, f = d.datetime.now(d.timezone.utc), "%Y-%m-%dT%H:%M:%SZ"
lines = ["ACTION_ID=r-test", "REQUESTED_AT=" + n.strftime(f), "DATA_SET=" + p["set_uuid"], "PLAN_SHA256=" + p["plan_sha256"],
         "EXPIRES_AT=" + (n + d.timedelta(hours=1)).strftime(f), "STATE=", "ATTEMPTS=0"]
lines += ["MEMBER=%s:%d" % (m["partuuid"], m["generation"]) for m in p["members"]]
os.makedirs("/boot/efi/onemind", exist_ok=True)
open("/boot/efi/onemind/factory-reset", "w").write("\n".join(lines) + "\n")
print("ARMED=%d" % len(p["members"]))
"""
ARM_CMD = "echo " + base64.b64encode(ARM_PY.encode()).decode() + " | base64 -d | python3 -"
RESET_AFTER = ("echo UUID=$(blkid -s UUID -o value /dev/disk/by-partlabel/onemind-data); "
               "echo ARMED=$(test -e /boot/efi/onemind/factory-reset && echo yes || echo no); "
               "echo DONE=$(test -e /boot/efi/onemind/factory-reset.done && echo yes || echo no); "
               "echo MA=$(test -e /data/onemind/e-marker && echo yes || echo no); echo MB=$(test -e /data/storage/e-marker2 && echo yes || echo no); ")


def reset_case(a, logf, tag, tpm):
    """R1 (tpm=None, plain btrfs) or R2 (a software TPM, LUKS2 + btrfs): arm a factory reset, reboot once, and the box
    must come back as a fresh first boot (CRITERIA-DATARESET.md). Returns (verdict, detail)."""
    vm, w = None, None
    plain = tpm is None
    try:
        vm, w = fresh_vm(a, logf, tag)
        vm.failfast = False
        vm.mark(f"{tag.upper()} factory reset of a {'plain btrfs' if plain else 'encrypted'} box")
        boot(vm, tpm, f"{tag.upper()} boot")
        vm.expect(r"ONEMIND-DATA-CRYPT: data partition ready \(btrfs, unencrypted\)" if plain else KEY_MADE, 900)
        vm.pos = 0
        vm.wait_gate(); vm.shell_ready()
        old_key = None if plain else read_key(vm)
        old = guest_vals(vm, "echo UUID=$(blkid -s UUID -o value /dev/disk/by-partlabel/onemind-data)").get("UUID", "")
        guest_vals(vm, MARK_CMD.format(path="/data/onemind/e-marker", name="MA"))
        guest_vals(vm, MARK_CMD.format(path="/data/storage/e-marker2", name="MB"))
        armed = guest_vals(vm, ARM_CMD).get("ARMED", "")
        seg = vm.here(); vm.send("systemctl reboot"); vm.pos = seg
        vm.expect(r"ONEMIND-DATA-CRYPT: data partition ready \(btrfs, unencrypted\)" if plain else KEY_MADE, 1200)
        vm.wait_gate(); s = vm.since(seg); vm.shell_ready()
        v = guest_vals(vm, RESET_AFTER + SUBVOLS_CMD)
        new_key = None if plain else read_key(vm)
        serial_key = key_on_serial(s, new_key or "") or bool(old_key and old_key in s)
        recovered = bool(re.search(battery.RECOV, s))
        want_src = "/dev/mapper/onemind-data" if not plain else None
        src = v.get("SRC", "")
        ok = bool(armed not in ("", "0") and bool(old) and v.get("UUID") and v.get("UUID") != old
              and v.get("ARMED") == "no" and v.get("DONE") == "yes" and v.get("MA") == "no" and v.get("MB") == "no"
              and v.get("STOR") == "1" and v.get("FAILED") == "0" and not recovered
              and (("making it plain btrfs, NOT encrypted" in s and "/dev/mapper" not in src) if plain else
                   (src.startswith(want_src) and bool(old_key) and bool(new_key) and new_key != old_key
                    and not serial_key and "data disk unlocked" not in s and not re.search(PROMPT, s))))
        return ok, (f"plan_members={armed} old_uuid={old} new_uuid={v.get('UUID')} armed_marker_left={v.get('ARMED')} done={v.get('DONE')} "
                    f"markers_left={v.get('MA')},{v.get('MB')} data_source={src} storage_mounted={v.get('STOR')} failed_units={v.get('FAILED')} "
                    f"recovery_mode={recovered} prompted={bool(re.search(PROMPT, s))} unlocked_old={'data disk unlocked' in s} "
                    f"new_recovery_key={bool(new_key) and new_key != old_key} key_on_serial={False if plain else serial_key}")
    except (TimeoutError, RuntimeError, ValueError) as e:
        return False, f"aborted: {e}"
    finally:
        if vm is not None and vm.proc and vm.proc.poll() is None:
            vm.kill()
        if w and os.path.lexists(os.path.join(w, "disk.img")):
            os.remove(os.path.join(w, "disk.img"))


def reset_tests(a, logf):
    """R1 and R2 (CRITERIA-DATARESET.md). Returns False when a step could not run to its end."""
    ok1, d1 = reset_case(a, logf, "r1", None)
    record("R1", ok1, d1)
    tpm4 = Tpm(a.work, "tpm4")
    try:
        ok2, d2 = reset_case(a, logf, "r2", tpm4)
    finally:
        tpm4.stop()
    record("R2", ok2, d2)
    return ok1 and ok2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=["x86_64-efi", "vm"])
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--results")
    ap.add_argument("--only", choices=["reset"], help="run only the factory-reset tests R1 and R2 (a quick re-run)")
    a = ap.parse_args()
    if a.only == "reset":
        logf = open(a.log, "w")
        ok = reset_tests(a, logf)
        logf.close()
        if a.results:
            json.dump({"criteria": "test/qemu/CRITERIA-DATARESET.md", "results": RESULTS}, open(a.results, "w"), indent=2)
        return 0 if ok else 1
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
        vm.expect(KEY_MADE, 900)
        vm.pos = 0
        vm.wait_gate()
        s1 = vm.since(0)                 # this VM's first boot, power-on to the gate, before any shell command
        vm.shell_ready()
        recovery = read_key(vm)
        serial_key = key_on_serial(s1, recovery)
        _, out = vm.run("echo SRC=$(findmnt -n -o SOURCE /data); "
                        "dev=$(cryptsetup status onemind-data | sed -n 's/^ *device: *//p'); "
                        "echo RAW=$(blkid -p -o value -s TYPE $dev); "
                        "echo DUMP=$(cryptsetup luksDump $dev | grep -cE 'systemd-tpm2|systemd-recovery'); "
                        "echo FILE=$(stat -c %a /run/onemind/data-recovery-key 2>&1); "
                        "echo JOURNALKEY=$(journalctl -b --no-pager | grep -c " + (recovery or "no-key-read") + ")")
        g = lambda k, o: (re.findall(rf"^{k}=(\S*)\s*$", o, re.M) or [""])[-1]
        _, o2 = vm.run(marker)
        mark = g("MARK", o2)
        record("E1", "/dev/mapper/onemind-data" in g("SRC", out) and g("DUMP", out) == "2" and g("FILE", out) == "600" and g("RAW", out) == "crypto_LUKS"
               and g("JOURNALKEY", out) == "0" and bool(recovery) and not serial_key
               and len(mark) == 64,
               f"data_source={g('SRC', out)} tpm2_and_recovery_tokens={g('DUMP', out)} keyfile_mode={g('FILE', out)} "
               f"key_in_journal={g('JOURNALKEY', out)} key_in_ram={bool(recovery)} key_on_serial={serial_key} "
               f"raw_type_probe={g('RAW', out)}")
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

        # E6: an update and a rollback keep the encrypted /data, and /data/storage stays its own mount (plan PR 5).
        vm.mark("E6 update and rollback keep the encrypted /data (swtpm #1)")
        boot(vm, tpm1, "E6 boot")
        vm.expect(r"ONEMIND-DATA-CRYPT: data disk unlocked \((\w[\w-]*)\)", 900)
        vm.wait_gate(); vm.shell_ready()
        mark2 = guest_vals(vm, MARK_CMD.format(path="/data/storage/e-marker2", name="MARK2")).get("MARK2", "")
        lay0 = guest_vals(vm, SUBVOLS_CMD)
        check2 = "echo MARK=$(sha256sum /data/onemind/e-marker 2>&1 | cut -c1-64); " \
                 "echo MARK2=$(sha256sum /data/storage/e-marker2 2>&1 | cut -c1-64); " + \
                 "echo STOR=$(findmnt -n -o SOURCE,OPTIONS /data/storage | grep -c 'subvol=/@storage')"
        rc_up, seg = battery.update_and_reboot(vm, "good.raucb")
        vm.pos = seg
        g_up = vm.wait_gate(); s_up = vm.since(seg); vm.shell_ready()
        up = guest_vals(vm, check2)
        rc_bad, seg2 = battery.update_and_reboot(vm, "bad-k3s.raucb")
        vm.pos = seg2
        g_bad = vm.wait_gate(); g_back = vm.wait_gate(); s_bad = vm.since(seg2); vm.shell_ready()
        back = guest_vals(vm, check2)
        kept = lambda d: d.get("MARK") == mark and d.get("MARK2") == mark2 and d.get("STOR") == "1" and len(mark2) == 64
        record("E6", rc_up == 0 and rc_bad == 0 and lay0.get("STOR") == "1" and g_up == ("mark-good", "B", "2")
               and g_bad == ("mark-bad", "A", "3") and g_back == ("committed-boot", "B", "2")
               and kept(up) and kept(back)
               and "unlocked (tpm2)" in s_up and "unlocked (tpm2)" in s_bad
               and not re.search(PROMPT, s_up) and not re.search(PROMPT, s_bad),
               f"installs_rc={rc_up},{rc_bad} update={g_up} rollback={g_bad}->{g_back} markers_kept_after_update={kept(up)} "
               f"markers_kept_after_rollback={kept(back)} tpm2_unlock_in_both={'unlocked (tpm2)' in s_up and 'unlocked (tpm2)' in s_bad} "
               f"prompted={bool(re.search(PROMPT, s_up) or re.search(PROMPT, s_bad))} storage_mount_kept={up.get('STOR')},{back.get('STOR')}")
        power_off(vm)

        # E8: snapper timeline snapshot of @storage, restore, scrub, and survival of an A/B update (CRITERIA-SNAPPER.md).
        vm.mark("E8 snapshots of the owner's files (swtpm #1)")
        boot(vm, tpm1, "E8 boot")
        vm.expect(r"ONEMIND-DATA-CRYPT: data disk unlocked \((\w[\w-]*)\)", 900)
        vm.wait_gate(); vm.shell_ready()
        u = guest_vals(vm, "echo ENABLED=$(systemctl is-enabled snapper-timeline.timer snapper-cleanup.timer btrfs-scrub.timer | tr '\\n' ,); "
                           "echo ACTIVE=$(systemctl is-active snapper-timeline.timer snapper-cleanup.timer btrfs-scrub.timer | tr '\\n' ,); "
                           "echo MASKED=$(systemctl is-enabled snapper-boot.timer btrfs-balance.timer btrfs-defrag.timer btrfs-trim.timer "
                           "btrfsmaintenance-refresh.path 2>&1 | tr '\\n' ,); "
                           "echo CONFIGS=$(snapper --no-dbus list-configs 2>&1 | grep -c '^storage *| /data/storage *$'); "
                           "echo ONECONFIG=$(snapper --no-dbus list-configs 2>&1 | grep -c '|'); "
                           "echo MONTHLY=$(systemctl cat btrfs-scrub.timer | grep -c '^OnCalendar=monthly'); "
                           "echo SNAPSV=$(btrfs subvolume show /data/storage/.snapshots >/dev/null 2>&1 && echo yes || echo no)")
        units_ok = (u.get("ENABLED") == "enabled,enabled,enabled," and u.get("ACTIVE") == "active,active,active,"
                    and u.get("MASKED") == "masked,masked,masked,masked,masked," and u.get("CONFIGS") == "1"
                    and u.get("ONECONFIG") == "2" and u.get("MONTHLY") == "1" and u.get("SNAPSV") == "yes")
        w = guest_vals(vm, "head -c 1048576 /dev/urandom > /data/storage/payload.bin; sync; echo H0=$(sha256sum /data/storage/payload.bin | cut -c1-64); "
                           "echo BEFORE=$(ls /data/storage/.snapshots | grep -cE '^[0-9]+$')")
        h0 = w.get("H0", "")
        guest_vals(vm, "systemctl start snapper-timeline.service; for i in $(seq 1 60); do systemctl is-active -q snapper-timeline.service || break; sleep 1; done")
        t = guest_vals(vm, "echo RES=$(systemctl show -p Result --value snapper-timeline.service); "
                           "echo AFTER=$(ls /data/storage/.snapshots | grep -cE '^[0-9]+$'); "
                           "N=$(ls /data/storage/.snapshots | grep -E '^[0-9]+$' | sort -n | tail -1); echo N=$N; "
                           "echo TYPE=$(grep -c '<type>single</type>' /data/storage/.snapshots/$N/info.xml); "
                           "echo CLEAN=$(grep -c '<cleanup>timeline</cleanup>' /data/storage/.snapshots/$N/info.xml); "
                           "echo RO=$(btrfs property get -ts /data/storage/.snapshots/$N/snapshot ro); "
                           "echo SNAPSHOTS_OF_DATA=$(ls /data/.snapshots 2>&1 | grep -c '^[0-9]'); "
                           "echo CONFIGS_DIR=$(ls /etc/snapper/configs | tr '\\n' ,)")
        n = t.get("N", "")
        timeline_ok = (t.get("RES") == "success" and n.isdigit() and int(t.get("AFTER", 0)) == int(w.get("BEFORE", 0)) + 1
                       and t.get("TYPE") == "1" and t.get("CLEAN") == "1" and t.get("RO") == "ro=true"
                       and t.get("SNAPSHOTS_OF_DATA") == "0" and t.get("CONFIGS_DIR") == "storage,")
        r = guest_vals(vm, f"echo hello >> /data/storage/payload.bin; sync; cp /data/storage/.snapshots/{n}/snapshot/payload.bin /data/storage/restored.bin; "
                           "echo HR=$(sha256sum /data/storage/restored.bin | cut -c1-64); echo HL=$(sha256sum /data/storage/payload.bin | cut -c1-64)")
        restore_ok = len(h0) == 64 and r.get("HR") == h0 and r.get("HL") != h0
        guest_vals(vm, "systemctl start btrfs-scrub.service; for i in $(seq 1 300); do systemctl is-active -q btrfs-scrub.service || break; sleep 1; done", 420)
        sc = guest_vals(vm, "echo RES=$(systemctl show -p Result --value btrfs-scrub.service); "
                            "echo STATUS=$(btrfs scrub status /data 2>&1 | tr -s ' \\n' ' '); "
                            "echo LOG=$(journalctl -b --no-pager -u btrfs-scrub.service | tail -6 | cut -d' ' -f5- | tr -s ' \\n' ' ' | cut -c1-500)")
        scrub_ok = (sc.get("RES") == "success" and re.search(r"(?i)status: +finished", sc.get("STATUS", "")) is not None
                    and re.search(r"(?i)error summary: +no errors found", sc.get("STATUS", "")) is not None)
        info0 = guest_vals(vm, f"echo INFO=$(sha256sum /data/storage/.snapshots/{n}/info.xml | cut -c1-64)").get("INFO", "")
        rc_up, seg = battery.update_and_reboot(vm, "good.raucb")
        vm.pos = seg
        g_up = vm.wait_gate(); s_up = vm.since(seg); vm.shell_ready()
        post = guest_vals(vm, f"echo INFO=$(sha256sum /data/storage/.snapshots/{n}/info.xml | cut -c1-64); "
                           f"cp /data/storage/.snapshots/{n}/snapshot/payload.bin /data/storage/restored2.bin; "
                           "echo H2=$(sha256sum /data/storage/restored2.bin | cut -c1-64); "
                           f"echo LISTED=$(snapper --no-dbus -c storage list 2>&1 | grep -cE '^ *{n} *\\|'); "
                           "echo FAILED=$(systemctl --failed --no-legend | wc -l)")
        survive_ok = (rc_up == 0 and g_up == ("mark-good", "A", "2") and post.get("INFO") == info0 and len(info0) == 64
                      and post.get("H2") == h0 and post.get("LISTED") == "1" and post.get("FAILED") == "0"
                      and "unlocked (tpm2)" in s_up and not re.search(PROMPT, s_up))
        record("E8", units_ok and timeline_ok and restore_ok and scrub_ok and survive_ok,
               f"units_ok={units_ok} {u} timeline_ok={timeline_ok} {t} restore_ok={restore_ok} scrub_ok={scrub_ok} {sc} "
               f"update_survived={survive_ok} install_rc={rc_up} result={g_up} snapshot={n} {post}")
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
        _, o = vm.run("echo TYPE=$(blkid -p -o value -s TYPE /dev/disk/by-partlabel/onemind-data); "
                      "echo DATAMNT=$(mountpoint -q /data && echo yes || echo no)")
        record("E4", g("TYPE", o) == "crypto_LUKS" and g("DATAMNT", o) == "no",
               f"raw_type={g('TYPE', o)} data_mounted={g('DATAMNT', o)}")
        rc = 0
    except (TimeoutError, RuntimeError) as e:
        record("HARNESS", False, f"aborted: {e}")
    if vm.proc and vm.proc.poll() is None:
        vm.kill()
    rc = rc if e57(a, logf, env) else 1
    rc = rc if reset_tests(a, logf) else 1
    tpm1.stop(); tpm2.stop()
    total = (time.time() - t0) / 60
    print("\nSUMMARY (total %.0f min, accel=%s)" % (total, env["accel"]))
    for r in RESULTS:
        print(" | ".join((r["test"], r["verdict"], r["detail"])))
    logf.close()
    if a.results:
        json.dump({"env": env, "minutes": round(total, 1), "criteria": "test/qemu/CRITERIA-DATAENC.md, CRITERIA-DATABTRFS.md, CRITERIA-DATARESET.md",
                   "results": RESULTS}, open(a.results, "w"), indent=2)
    return 0 if rc == 0 and RESULTS and all(r["verdict"] == "PASS" for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
