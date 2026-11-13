#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Structure test of an assembled rpi5 disk image (brief 30 D-B2.2: "rpi5 images pass a ... structure
test"; QEMU cannot boot the Pi firmware). No loop devices: the MBR is parsed here, FAT partitions are
read with mtools at their offset, ext4 with debugfs "?offset=". Run in the tools container:

  check-image.py <disk.img> [--bundle X.raucb --keyring ca.pem] [--json out.json]
Exit 0 only if every check passes; prints one line per check.
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rpi5_boot as R  # noqa: E402
import yaml  # noqa: E402


def sh(*c):
    r = subprocess.run(list(c), capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("disk"); ap.add_argument("--bundle"); ap.add_argument("--keyring"); ap.add_argument("--json")
    a = ap.parse_args(argv)
    board = yaml.safe_load(open(os.path.join(HERE, "board.yaml")))
    layout = yaml.safe_load(open(os.path.join(HERE, "layout.yaml")))
    want = R.plan(layout)
    checks = {}

    with open(a.disk, "rb") as f:
        def rd(lba):
            f.seek(lba * R.SECTOR); return f.read(R.SECTOR)
        got = R.parse_mbr(rd)
    checks["disk_size"] = os.path.getsize(a.disk) == want["total"] * R.SECTOR
    checks["mbr_disk_id"] = got["disk_id"] == board["disk_id"]
    checks["mbr_partitions"] = {n: (t, s, c) for n, (t, s, c) in got["parts"].items()} == {
        n: (R.MBR_TYPES[t], s, c) for n, (_, t, s, c) in want["parts"].items()}

    def fat(n):
        return f"{a.disk}@@{want['parts'][n][2] * R.SECTOR}"

    def mtype(n, path):
        rc, out, _ = sh("mtype", "-i", fat(n), "::/" + path)
        return out if rc == 0 else None

    def mls(n, path=""):
        rc, out, _ = sh("mdir", "-b", "-i", fat(n), "::/" + path)
        return [l.rsplit("/", 1)[-1] for l in out.split()] if rc == 0 else []

    checks["autoboot_txt_A_committed"] = mtype(1, "autoboot.txt") == R.autoboot_txt("A")
    root1 = mls(1)
    checks["autoboot_slot_A_good"] = "slot-A.good" in root1 and "slot-B.good" not in root1
    checks["autoboot_onemind_conf"] = "onemind.conf" in root1
    for name, text in R.boot_files(board).items():
        checks[f"boot_{name}"] = mtype(2, name) == text
    root2 = mls(2)
    for f in ("kernel_2712.img", "initramfs_2712", "kernel8.img", "initramfs8", "bcm2712-rpi-5-b.dtb",
              "bcm2712d0-rpi-5-b.dtb", "bcm2712-rpi-cm5-cm5io.dtb", "bcm2712-rpi-500.dtb"):
        checks[f"boot_has_{f}"] = f in root2
    checks["boot_overlays"] = len(mls(2, "overlays")) > 100
    checks["boot_no_os_prefix"] = "\nos_prefix=" not in (mtype(2, "config.txt") or "\nos_prefix=")
    checks["boot_b_empty_until_update"] = not mls(3)

    def e2(n, cmd):
        rc, out, err = sh("debugfs", "-R", cmd, f"{a.disk}?offset={want['parts'][n][2] * R.SECTOR}")
        return out if rc == 0 else ""

    conf = e2(5, "cat /etc/rauc/system.conf")
    checks["rauc_custom_backend"] = "bootloader=custom" in conf and "bootloader-custom-backend=/usr/lib/onemind/rpi-tryboot-ab.sh" in conf
    checks["rauc_slots_by_partuuid"] = all(f"/dev/disk/by-partuuid/{R.partuuid(board['disk_id'], n)}" in conf for n in (2, 3, 5, 6))
    checks["rauc_verity_only"] = "bundle-formats=verity" in conf
    checks["fstab_partuuid"] = f"PARTUUID={R.partuuid(board['disk_id'], 1)}" in e2(5, "cat /etc/fstab")
    for p in ("/usr/lib/onemind/rpi-tryboot-ab.sh", "/usr/lib/onemind/gate-slot-env", "/usr/lib/onemind/onemind-health-gate",
              "/usr/bin/onemindd", "/usr/bin/nats-server", "/usr/bin/rauc", "/usr/local/bin/k3s"):
        checks[f"root_has_{p}"] = "Inode:" in e2(5, f"stat {p}")
    info = e2(5, "cat /usr/lib/onemind/build-info.txt")
    checks["build_info_rpi_kernel"] = "board=rpi5" in info and "-rpi-2712" in info and "boot_kernel=" in info
    checks["no_debian_kernel"] = "-arm64" not in e2(5, "ls -l /usr/lib/modules")
    checks["no_rpi_eeprom_autoupdate"] = "Inode:" not in e2(5, "stat /usr/lib/systemd/system/rpi-eeprom-update.service")
    checks["data_label"] = "onemind-data" in e2(7, "stats").split("Filesystem UUID")[0]

    if a.bundle:
        rc, out, err = sh("rauc", "info", f"--keyring={a.keyring}", a.bundle)
        checks["bundle_verified_verity"] = rc == 0 and "verity" in out
        checks["bundle_has_boot_and_rootfs"] = "boot.vfat" in out and "rootfs.ext4" in out and f"'{board['compatible']}'" in out

    ok = all(checks.values())
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")
    print("rpi5 image structure:", "PASS" if ok else "FAIL")
    if a.json:
        json.dump({"test": "rpi5-structure", "pass": ok, "checks": checks}, open(a.json, "w"), indent=2)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
