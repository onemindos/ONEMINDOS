#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assembler for the rpi5 board: rootfs tar -> MBR A/B disk image + RAUC bundles (brief 30 D-B2.2, BD-07).

Same commands and arguments as os/assemble/assemble.py (tree, ext4, disk, bundle, image), so
os/assemble/dev-image.sh and test/qemu/mkfixtures.sh drive it unchanged (board.yaml `assembler:`).
It reuses assemble.py for the tree, the ext4 slot image and the image/SHA256SUMS step, and replaces
the boot side: no GRUB; the Pi firmware boots partition 2 or 3 as autoboot.txt says.

  boot slot (FAT, partitions 2 and 3, one image): kernel_2712.img + initramfs_2712 and kernel8.img +
      initramfs8 (from Raspberry Pi's kernel debs in the tree), bcm2712*.dtb, overlays/, config.txt,
      cmdline_a.txt, cmdline_b.txt (rpi5_boot.py).
  autoboot (FAT, partition 1, label ONEMIND): autoboot.txt (A committed), slot-A.good, onemind.conf.
  bundle: [image.boot] boot.vfat + [image.rootfs] rootfs.ext4, so an update replaces the kernel too.
Runs as root in the tools container, like assemble.py. Partition table: rpi5_boot.mbr_sectors.
"""
import argparse, glob, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OS_DIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(OS_DIR, "assemble"))
sys.path.insert(0, HERE)
import assemble as A  # noqa: E402
import rpi5_boot as R  # noqa: E402

BOOT_IMG = "boot.vfat"


def load_board(name="rpi5"):
    d = os.path.join(OS_DIR, "boards", name)
    board = A.load_yaml(os.path.join(d, "board.yaml"))
    board["layout_data"] = A.load_yaml(os.path.join(d, board.get("layout", "layout.yaml")))
    R.plan(board["layout_data"])  # validates
    return board


def part(board, label):
    return next(p for p in board["layout_data"]["partitions"] if p["label"] == label)


def system_conf(board):
    t = open(os.path.join(HERE, "system.conf.in")).read()
    return t.replace("@COMPATIBLE@", board["compatible"]).replace("@DISK_ID@", board["disk_id"])


# ------------------------------------------------------------------ tree
def cmd_tree(a):
    board = load_board(a.board)
    tree = os.path.join(a.work, "tree")
    if os.path.exists(tree):
        shutil.rmtree(tree)
    os.makedirs(tree)
    A.run("tar", "--numeric-owner", "-xpf", a.rootfs, "-C", tree)
    A.finalize(tree, board, a.version, a.keyring, a.overlay or [])
    open(os.path.join(tree, "etc/rauc/system.conf"), "w").write(system_conf(board))  # custom backend, MBR slots
    ver = kernel_version(tree, str(board["kernel"]))
    with open(os.path.join(tree, "usr/lib/onemind/build-info.txt"), "a") as f:
        f.write(f"boot_kernel={ver} (kernel={R.KERNELS[str(board['kernel'])][0]})\n")


# ------------------------------------------------------------------ boot slot
def kernel_version(tree, flavour):
    found = sorted(glob.glob(os.path.join(tree, "boot", f"vmlinuz-*-rpi-{flavour}")))
    if len(found) != 1:
        sys.exit(f"ERROR: expected one Raspberry Pi {flavour} kernel in /boot, found {found}")
    return os.path.basename(found[0])[len("vmlinuz-"):]


def boot_tree(board, tree, dst):
    """Lay out one boot slot's files in `dst` (what raspi-firmware's kernel hook would copy to
    /boot/firmware, for both kernel flavours, plus the generated config)."""
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(os.path.join(dst, "overlays"))
    default = str(board["kernel"])
    for flavour, (kname, iname) in R.KERNELS.items():
        ver = kernel_version(tree, flavour)
        shutil.copyfile(os.path.join(tree, "boot", f"vmlinuz-{ver}"), os.path.join(dst, kname))
        initrd = os.path.join(tree, "boot", f"initrd.img-{ver}")
        if not os.path.exists(initrd):
            sys.exit(f"ERROR: no initramfs for {ver}")
        shutil.copyfile(initrd, os.path.join(dst, iname))
        if flavour == default:   # dtbs and overlays of the kernel that boots by default
            lib = os.path.join(tree, "usr/lib", f"linux-image-{ver}")
            dtbs = sorted(glob.glob(os.path.join(lib, "broadcom", "bcm2712*.dtb")))
            if not dtbs:
                sys.exit(f"ERROR: no bcm2712 device trees in {lib}")
            for f in dtbs:
                shutil.copyfile(f, os.path.join(dst, os.path.basename(f)))
            for f in sorted(glob.glob(os.path.join(lib, "overlays", "*.dtb*")) + [os.path.join(lib, "overlays", "README")]):
                if os.path.exists(f):
                    shutil.copyfile(f, os.path.join(dst, "overlays", os.path.basename(f)))
    for name, text in R.boot_files(board).items():
        open(os.path.join(dst, name), "w").write(text)


def fat_from_dir(path, size_mib, label, src):
    A.fat_image(path, size_mib, label)
    entries = sorted(os.listdir(src))
    if entries:
        A.run("mcopy", "-s", "-Q", "-i", path, *[os.path.join(src, e) for e in entries], "::/", stdout=subprocess.DEVNULL)


def size_mib(board, label):
    return R.mib(part(board, label)["size"])


def build_boot(board, work):
    tree, stage = os.path.join(work, "tree"), os.path.join(work, "stage")
    os.makedirs(stage, exist_ok=True)
    bdir = os.path.join(stage, "boot")
    boot_tree(board, tree, bdir)
    img = os.path.join(work, BOOT_IMG)
    fat_from_dir(img, size_mib(board, "onemind-boot-a"), part(board, "onemind-boot-a")["fs_label"], bdir)
    shutil.rmtree(bdir)
    return img


def build_autoboot(board, work, onemind_conf):
    stage = os.path.join(work, "stage", "autoboot")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    open(os.path.join(stage, "autoboot.txt"), "w").write(R.autoboot_txt("A"))
    open(os.path.join(stage, "slot-A.good"), "w").close()
    shutil.copyfile(onemind_conf, os.path.join(stage, "onemind.conf"))
    img = os.path.join(work, "stage", "autoboot.vfat")
    p = part(board, "onemind-autoboot")
    fat_from_dir(img, R.mib(p["size"]), p["fs_label"], stage)
    shutil.rmtree(stage)
    return img


# ------------------------------------------------------------------ disk
def cmd_disk(a):
    board = load_board(a.board)
    lay = board["layout_data"]
    geo = R.plan(lay)
    boot = build_boot(board, a.work)
    auto = build_autoboot(board, a.work, os.path.join(OS_DIR, "assemble", "onemind.conf.in"))
    datafs = os.path.join(a.work, "datafs")
    shutil.rmtree(datafs, ignore_errors=True)
    for d in ("onemind", "rauc", "k3s", "state/var-tmp"):
        os.makedirs(os.path.join(datafs, d))
    data = os.path.join(a.work, "stage", "data.ext4")
    if os.path.exists(data):
        os.remove(data)
    _, _, _, dsec = geo["parts"][7]
    A.run("mke2fs", "-q", "-t", "ext4", "-L", part(board, "onemind-data")["fs_label"], "-E", "root_owner=0:0",
          "-d", datafs, data, f"{dsec * 512 >> 20}M")
    shutil.rmtree(datafs)

    disk = a.out
    if os.path.exists(disk):
        os.remove(disk)
    with open(disk, "wb") as f:
        f.truncate(geo["total"] * R.SECTOR)
        for lba, sec in R.mbr_sectors(lay, board["disk_id"]).items():
            f.seek(lba * R.SECTOR)
            f.write(sec)
    # partition 3 (boot B) and 6 (system B) stay empty until the first update writes them
    for n, img in ((1, auto), (2, boot), (5, a.system), (7, data)):
        label, _, first, count = geo["parts"][n]
        if os.path.getsize(img) > count * R.SECTOR:
            sys.exit(f"ERROR: {img} is larger than partition {n} ({label})")
        A.sparse_copy(img, disk, first * R.SECTOR)
    for img in (auto, data):
        os.remove(img)
    for n in sorted(geo["parts"]):
        label, t, first, count = geo["parts"][n]
        A.log(f"p{n} {label:18} {t:9} start {first:>9} sectors {count:>9} ({count * 512 >> 20} MiB)"
              f" PARTUUID={R.partuuid(board['disk_id'], n)}")
    A.log(f"disk {disk} ({lay['disk_size']}) for board {board['name']}; boot slot image kept at {boot}")


# ------------------------------------------------------------------ bundle
def cmd_bundle(a):
    board = load_board(a.board)
    boot = getattr(a, "boot", None) or os.path.join(os.path.dirname(os.path.abspath(a.system)), BOOT_IMG)
    if not os.path.exists(boot):
        sys.exit(f"ERROR: {boot} missing: run `disk` (or pass --boot) first")
    d = tempfile.mkdtemp(prefix="bundle-", dir=os.path.dirname(os.path.abspath(a.out)))
    try:
        for src, name in ((a.system, "rootfs.ext4"), (boot, BOOT_IMG)):
            dst = os.path.join(d, name)
            os.link(src, dst) if A.same_fs(src, d) else shutil.copyfile(src, dst)
        open(os.path.join(d, "manifest.raucm"), "w").write(
            f"[update]\ncompatible={board['compatible']}\nversion={a.version}\n\n[bundle]\nformat={a.format}\n\n"
            f"[image.boot]\nfilename={BOOT_IMG}\n\n[image.rootfs]\nfilename=rootfs.ext4\n")
        if os.path.exists(a.out):
            os.remove(a.out)
        A.run("rauc", "bundle", f"--cert={a.cert}", f"--key={a.key}", d, a.out, stdout=subprocess.DEVNULL)
    finally:
        shutil.rmtree(d)


# ------------------------------------------------------------------ image
def cmd_image(a):
    # assemble.cmd_image (disk, bundle, "-next" bundle, packages.txt, SHA256SUMS) with this board's steps.
    A.cmd_tree, A.cmd_disk, A.cmd_bundle = cmd_tree, cmd_disk, cmd_bundle
    A.cmd_image(a)
    boot = os.path.join(a.work, BOOT_IMG)
    if os.path.exists(boot):
        os.remove(boot)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    t = sp.add_parser("tree"); t.set_defaults(fn=cmd_tree)
    e = sp.add_parser("ext4"); e.set_defaults(fn=A.cmd_ext4)
    d = sp.add_parser("disk"); d.set_defaults(fn=cmd_disk)
    b = sp.add_parser("bundle"); b.set_defaults(fn=cmd_bundle)
    i = sp.add_parser("image"); i.set_defaults(fn=cmd_image)
    for p in (t, i):
        p.add_argument("--board", required=True); p.add_argument("--rootfs", required=True)
        p.add_argument("--work", required=True); p.add_argument("--version", required=True)
        p.add_argument("--keyring", required=True); p.add_argument("--overlay", action="append")
    e.add_argument("--work", required=True); e.add_argument("--out", required=True)
    e.add_argument("--size-mib", type=int)
    d.add_argument("--board", required=True); d.add_argument("--work", required=True)
    d.add_argument("--system", required=True); d.add_argument("--out", required=True)
    b.add_argument("--board", required=True); b.add_argument("--system", required=True)
    b.add_argument("--version", required=True); b.add_argument("--out", required=True)
    b.add_argument("--format", default="verity", choices=["verity", "plain"])
    b.add_argument("--boot", help="boot slot FAT image (default: boot.vfat next to --system)")
    for p in (b, i):
        p.add_argument("--cert", required=p is b); p.add_argument("--key", required=p is b)
    i.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    if getattr(a, "board", "rpi5") != "rpi5":
        sys.exit("assemble_rpi5.py builds the rpi5 board only")
    a.fn(a)


if __name__ == "__main__":
    main()
