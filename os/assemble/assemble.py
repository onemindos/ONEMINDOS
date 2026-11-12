#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind assembler (brief 30 BD-05, D-B2.2): rootfs tar -> A/B disk image + RAUC bundle.

Uses only the tools the passing labs used (sgdisk, mkfs.fat/mtools, mke2fs -d, grub-mkstandalone /
grub-mkimage from the rootfs's own GRUB, rauc bundle) [lab rauc-1152/scripts/build.sh]. No loop
devices and no privileges beyond root inside the tools container (tar ownership, chroot).

Run inside the tools container (os/rootfs/Containerfile target "tools"), as root, with python3 -I:

  assemble.py tree   --board B --rootfs rootfs.tar --work W --version V --keyring ca.pem [--overlay DIR]...
  assemble.py ext4   --work W --out system.ext4 [--size-mib N]
  assemble.py disk   --board B --work W --system system.ext4 --out disk.img
  assemble.py bundle --board B --system system.ext4 --version V --cert C --key K --out x.raucb [--format plain]
  assemble.py image  (tree + ext4 + disk + bundle in one go; see --help)
"""
import argparse, hashlib, os, shutil, struct, subprocess, sys, tempfile, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
OS_DIR = os.path.dirname(HERE)
# Fixed namespace so partition UUIDs are the same on every box built from a layout (lab and HAOS
# do the same); RAUC finds slots by PARTLABEL, GRUB passes root=PARTUUID.
PU_NS = uuid.UUID("6e0a8b0e-0000-4a00-8000-000000000000")
GPT_TYPES = {"esp": "EF00", "bios": "EF02", "linux": "8300"}
CHUNK = 1 << 20


def log(msg):
    print(f"[assemble] {msg}", flush=True)


def run(*cmd, **kw):
    log("$ " + " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def out(*cmd):
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, text=True).stdout


# ------------------------------------------------------------------ layout
def load_yaml(path):
    import yaml  # python3-yaml in the tools container
    with open(path) as f:
        return yaml.safe_load(f)


def mib(size):
    """'10GiB' / '512MiB' -> MiB (int). 'rest' -> None."""
    s = str(size).strip()
    if s == "rest":
        return None
    for suf, mul in (("GiB", 1024), ("MiB", 1)):
        if s.endswith(suf):
            return int(float(s[: -len(suf)]) * mul)
    raise ValueError(f"size must end in GiB or MiB, or be 'rest': {size!r}")


def load_board(name):
    d = os.path.join(OS_DIR, "boards", name)
    board = load_yaml(os.path.join(d, "board.yaml"))
    layout = load_yaml(os.path.join(d, board.get("layout", "layout.yaml")))
    board["layout_data"] = validate_layout(layout)
    return board


def validate_layout(layout):
    """Structural rules every layout must meet (the 01 §4.3 contract is tested in test/unit)."""
    parts = layout["partitions"]
    labels = [p["label"] for p in parts]
    assert len(set(labels)) == len(labels), "duplicate partition label"
    for need in ("onemind-esp", "onemind-system-a", "onemind-system-b", "onemind-data"):
        assert need in labels, f"layout lacks {need}"
    rest = [p for p in parts if mib(p["size"]) is None]
    assert len(rest) <= 1 and (not rest or parts[-1] is rest[0]), "only the last partition may be 'rest'"
    fixed = sum(mib(p["size"]) for p in parts if mib(p["size"]) is not None)
    total = mib(layout["disk_size"])
    assert fixed + 2 < total, f"partitions ({fixed} MiB) do not fit the disk ({total} MiB)"
    for i, p in enumerate(parts, 1):
        p["index"] = i
        p["partuuid"] = str(uuid.uuid5(PU_NS, p["label"]))
        assert p["type"] in GPT_TYPES, f"unknown type {p['type']}"
    return layout


def part(layout, label):
    return next(p for p in layout["partitions"] if p["label"] == label)


# ------------------------------------------------------------------ tree
def cmd_tree(a):
    board = load_board(a.board)
    tree = os.path.join(a.work, "tree")
    if os.path.exists(tree):
        shutil.rmtree(tree)
    os.makedirs(tree)
    run("tar", "--numeric-owner", "-xpf", a.rootfs, "-C", tree)
    finalize(tree, board, a.version, a.keyring, a.overlay or [])


def finalize(tree, board, version, keyring, overlays):
    j = lambda p: os.path.join(tree, p.lstrip("/"))
    # Version (brief 30 B5 G7): ONEMIND_VERSION in /usr/lib/os-release.
    osr = j("/usr/lib/os-release")
    lines = [l for l in open(osr).read().splitlines() if not l.startswith(("ONEMIND_VERSION=", "ONEMIND_BOARD="))]
    lines += [f'ONEMIND_VERSION="{version}"', f'ONEMIND_BOARD="{board["name"]}"']
    open(osr, "w").write("\n".join(lines) + "\n")
    apply_brand(tree)
    # RAUC: system.conf from the template + the keyring (public CA cert only).
    conf = open(os.path.join(OS_DIR, "rauc", "system.conf.in")).read()
    conf = conf.replace("@COMPATIBLE@", board["compatible"]).replace("@BOOTLOADER@", board["rauc_bootloader"])
    os.makedirs(j("/etc/rauc"), exist_ok=True)
    open(j("/etc/rauc/system.conf"), "w").write(conf)
    shutil.copyfile(keyring, j("/etc/rauc/keyring.pem"))
    # Files a container build cannot set (they are bind mounts during RUN).
    for f in ("/etc/resolv.conf",):
        if os.path.lexists(j(f)):
            os.remove(j(f))
    os.symlink("../run/systemd/resolve/stub-resolv.conf", j("/etc/resolv.conf"))
    shutil.copyfile(os.path.join(OS_DIR, "rootfs", "layers", "base", "etc", "hostname"), j("/etc/hostname"))
    shutil.copyfile(os.path.join(OS_DIR, "rootfs", "layers", "base", "etc", "hosts"), j("/etc/hosts"))
    # Empty machine-id: systemd makes a transient one on the read-only root (handbook/findings.md F-05).
    open(j("/etc/machine-id"), "w").close()
    for ov in overlays:
        log(f"overlay {ov}")
        run("cp", "-a", "--no-preserve=ownership", os.path.join(ov, "."), tree)
    # Safety: a shipped tree must not contain a naive gate (brief 30 B5).
    chk = open(j("/usr/lib/onemind/onemind-k3s-check")).read()
    if "NAIVE" in chk and not any("naive" in o for o in overlays):
        sys.exit("ERROR: naive gate found in a non-test tree")


# ------------------------------------------------------------------ ext4
def tree_mib(tree):
    return int(out("du", "-s", "-B1M", "--apparent-size", tree).split()[0])


def cmd_ext4(a):
    tree = os.path.join(a.work, "tree")
    size = a.size_mib or (int(tree_mib(tree) * 1.3) + 384 + 63) // 64 * 64
    if os.path.exists(a.out):
        os.remove(a.out)
    run("mke2fs", "-q", "-t", "ext4", "-L", "onemind-root", "-E", "root_owner=0:0", "-d", tree, a.out, f"{size}M")
    log(f"{a.out}: {size} MiB ext4 from a {tree_mib(tree)} MiB tree")


# ------------------------------------------------------------------ boot files
BRAND_DIR = os.path.join(os.path.dirname(OS_DIR), "brand", "generated", "os")
BRAND_KEYS = ("NAME=", "PRETTY_NAME=", "HOME_URL=", "ANSI_COLOR=")


def brand_os_release(text, brand):
    """Merge brand/generated/os/os-release into an os-release text (brand/README.md "What the image
    stream must wire"): drop Debian's NAME, PRETTY_NAME, HOME_URL, ANSI_COLOR and append ours. ID and
    VERSION_ID stay Debian's: apt and k3s read them."""
    new = [l for l in brand.splitlines() if l.startswith(BRAND_KEYS)]
    keep = [l for l in text.splitlines() if not l.startswith(BRAND_KEYS)]
    return "\n".join(keep + new) + "\n"


def apply_brand(tree, brand_dir=BRAND_DIR):
    """os-release keys and /etc/motd from the brand generator. No generated files, no change."""
    osr, motd = os.path.join(brand_dir, "os-release"), os.path.join(brand_dir, "motd")
    if os.path.exists(osr):
        dst = os.path.join(tree, "usr/lib/os-release")
        merged = brand_os_release(open(dst).read(), open(osr).read())   # read both before truncating dst
        open(dst, "w").write(merged)
    if os.path.exists(motd):
        shutil.copyfile(motd, os.path.join(tree, "etc/motd"))


def brand_grub(brand_dir=BRAND_DIR):
    """The `set` lines of brand/generated/os/grub/onemind-brand.cfg (colours only: no gfxterm, so the
    serial console and the QEMU battery see the same menu)."""
    f = os.path.join(brand_dir, "grub", "onemind-brand.cfg")
    if not os.path.exists(f):
        return ""
    return "".join(l + "\n" for l in open(f).read().splitlines() if l.startswith("set "))


def render_grub_cfg(board):
    lay = board["layout_data"]
    a, b = part(lay, "onemind-system-a"), part(lay, "onemind-system-b")
    t = open(os.path.join(HERE, "grub.cfg.in")).read()
    for k, v in (("@ESP_FSUUID@", esp_fsuuid(lay)), ("@IDX_A@", a["index"]), ("@IDX_B@", b["index"]),
                 ("@PU_A@", a["partuuid"]), ("@PU_B@", b["partuuid"]), ("@CONSOLE@", board["console"])):
        t = t.replace(k, str(v))
    return t.replace("@BRAND@\n", brand_grub())


def esp_volid(lay):
    return str(part(lay, "onemind-esp")["volume_id"]).upper()


def esp_fsuuid(lay):
    v = esp_volid(lay)
    return f"{v[:4]}-{v[4:]}"


def grub_binaries(board, tree, stage):
    """Build GRUB from the rootfs's own GRUB packages (same arch: native runner or emulated container)."""
    lay = board["layout_data"]
    # Partition maps are not auto-loaded, so load them before searching (the lab did the same).
    embed = f"insmod part_gpt\ninsmod fat\nsearch --no-floppy --fs-uuid --set=root {esp_fsuuid(lay)}\n"
    tmp = os.path.join(tree, "tmp", "onemind-grub")
    os.makedirs(tmp, exist_ok=True)
    files = {}
    if board["route"] == "grub-efi":
        open(os.path.join(tmp, "embed.cfg"), "w").write(embed + "configfile ($root)/EFI/BOOT/grub.cfg\n")
        name = board["efi_binary"]
        run("chroot", tree, "grub-mkstandalone", "-O", board["grub_target"], "-o", f"/tmp/onemind-grub/{name}",
            "boot/grub/grub.cfg=/tmp/onemind-grub/embed.cfg")
        files[f"EFI/BOOT/{name}"] = os.path.join(tmp, name)
    elif board["route"] == "grub-bios":
        # Minimal core.img; normal.mod and friends load from the ESP's /boot/grub/i386-pc
        # (what grub-install does). Embedded config finds the ESP by UUID and sets the prefix.
        open(os.path.join(tmp, "embed.cfg"), "w").write(embed + "set prefix=($root)/boot/grub\n")
        run("chroot", tree, "grub-mkimage", "-O", "i386-pc", "-o", "/tmp/onemind-grub/core.img",
            "-c", "/tmp/onemind-grub/embed.cfg", "-p", "/boot/grub",
            "biosdisk", "part_gpt", "fat", "search", "search_fs_uuid")
        shutil.copyfile(os.path.join(tree, "usr/lib/grub/i386-pc/boot.img"), os.path.join(stage, "boot.img"))
        shutil.copyfile(os.path.join(tmp, "core.img"), os.path.join(stage, "core.img"))
        open(os.path.join(stage, "esp-grub.cfg"), "w").write("configfile ($root)/EFI/BOOT/grub.cfg\n")
        files["boot/grub/grub.cfg"] = os.path.join(stage, "esp-grub.cfg")
        files["boot/grub/i386-pc/"] = os.path.join(tree, "usr/lib/grub/i386-pc")
    else:
        raise SystemExit(f"unknown route {board['route']}")
    for k, v in list(files.items()):
        if v.startswith(tmp):
            dst = os.path.join(stage, os.path.basename(v))
            shutil.copyfile(v, dst)
            files[k] = dst
    shutil.rmtree(tmp)
    return files


def install_bios_boot(disk, stage, core_lba, max_sectors):
    """What grub-bios-setup does for a GPT disk with a BIOS boot partition, without a loop device.
    Offsets from GRUB 2.12 include/grub/i386/pc/boot.h and grub-core/boot/i386/pc/diskboot.S:
    boot.img KERNEL_SECTOR 0x5c (u64), BOOT_DRIVE 0x64, DRIVE_CHECK 0x66; diskboot's blocklist is the
    last 12 bytes of core.img's first sector {u64 start, u16 len, u16 segment=0x820}."""
    boot = bytearray(open(os.path.join(stage, "boot.img"), "rb").read())
    core = bytearray(open(os.path.join(stage, "core.img"), "rb").read())
    assert len(boot) == 512
    nsec = (len(core) + 511) // 512
    assert nsec <= max_sectors, f"core.img ({nsec} sectors) does not fit the BIOS boot partition"
    core += b"\0" * (nsec * 512 - len(core))
    struct.pack_into("<Q", boot, 0x5C, core_lba)
    boot[0x64] = 0xFF              # use the drive the BIOS booted from
    boot[0x66:0x68] = b"\x90\x90"  # hard disk: skip the floppy drive check (grub-bios-setup does this)
    struct.pack_into("<QHH", core, 0x200 - 12, core_lba + 1, nsec - 1, 0x820)
    with open(disk, "r+b") as f:
        f.seek(0)
        f.write(boot[:0x1B8])      # boot code only; keep the disk signature and the protective MBR table
        f.seek(core_lba * 512)
        f.write(core)
    log(f"BIOS boot: boot.img -> MBR, core.img ({nsec} sectors) -> LBA {core_lba}")


def fat_image(path, size_mib, label, volid=None, files=None):
    if os.path.exists(path):
        os.remove(path)
    cmd = ["mkfs.fat", "-F", "32", "-n", label]
    if volid:
        cmd += ["-i", volid]
    run(*cmd, "-C", path, size_mib * 1024, stdout=subprocess.DEVNULL)
    for dst, src in (files or {}).items():
        parts = dst.strip("/").split("/")
        for i in range(1, len(parts)):
            subprocess.run(["mmd", "-D", "s", "-i", path, "::/" + "/".join(parts[:i])], stderr=subprocess.DEVNULL)
        if dst.endswith("/"):
            run("mcopy", "-s", "-i", path, src, "::/" + dst.rstrip("/").rsplit("/", 1)[0] + "/")
        else:
            run("mcopy", "-i", path, src, "::/" + dst)


def sparse_copy(src, dst_path, offset):
    with open(src, "rb") as s, open(dst_path, "r+b") as d:
        pos = offset
        while True:
            buf = s.read(CHUNK)
            if not buf:
                break
            if buf.count(0) != len(buf):
                d.seek(pos)
                d.write(buf)
            pos += len(buf)


# ------------------------------------------------------------------ disk
def cmd_disk(a):
    board = load_board(a.board)
    lay = board["layout_data"]
    tree = os.path.join(a.work, "tree")
    stage = os.path.join(a.work, "stage")
    os.makedirs(stage, exist_ok=True)
    files = grub_binaries(board, tree, stage)
    open(os.path.join(stage, "grub.cfg"), "w").write(render_grub_cfg(board))
    files["EFI/BOOT/grub.cfg"] = os.path.join(stage, "grub.cfg")
    env = os.path.join(stage, "grubenv")
    if os.path.exists(env):
        os.remove(env)
    run("grub-editenv", env, "create")
    run("grub-editenv", env, "set", "ORDER=A B", "A_OK=1", "A_TRY=0", "B_OK=0", "B_TRY=0")
    files["EFI/BOOT/grubenv"] = env
    # First-boot settings a user can edit after flashing (all commented out: the wizard runs).
    files["onemind.conf"] = os.path.join(HERE, "onemind.conf.in")

    disk = a.out
    if os.path.exists(disk):
        os.remove(disk)
    with open(disk, "wb") as f:
        f.truncate(mib(lay["disk_size"]) << 20)
    run("sgdisk", "-Z", disk, stdout=subprocess.DEVNULL)
    args = []
    for p in lay["partitions"]:
        size = mib(p["size"])
        args += ["-n", f"{p['index']}:0:" + (f"+{size}M" if size else "0"), "-t", f"{p['index']}:{GPT_TYPES[p['type']]}",
                 "-c", f"{p['index']}:{p['label']}", "-u", f"{p['index']}:{p['partuuid']}"]
    run("sgdisk", *args, disk, stdout=subprocess.DEVNULL)
    geo = {}
    for p in lay["partitions"]:
        info = out("sgdisk", "-i", p["index"], disk)
        first = int(next(l for l in info.splitlines() if l.startswith("First sector")).split()[2])
        last = int(next(l for l in info.splitlines() if l.startswith("Last sector")).split()[2])
        geo[p["label"]] = (first, last - first + 1)

    for p in lay["partitions"]:
        first, nsec = geo[p["label"]]
        size_mib = nsec * 512 >> 20
        img = os.path.join(stage, p["label"] + ".img")
        fs = p.get("fs", "none")
        if p["label"] == "onemind-esp":
            fat_image(img, size_mib, "ONEMIND-ESP", esp_volid(lay), files)
        elif fs == "vfat":
            fat_image(img, size_mib, p.get("fs_label", p["label"][-6:].upper()))
        elif p["label"] == "onemind-system-a":
            img = a.system
        elif p["label"] == "onemind-data":
            datafs = os.path.join(a.work, "datafs")
            shutil.rmtree(datafs, ignore_errors=True)
            for d in ("onemind", "rauc", "k3s", "state/var-tmp"):
                os.makedirs(os.path.join(datafs, d))
            if os.path.exists(img):
                os.remove(img)
            run("mke2fs", "-q", "-t", "ext4", "-L", "onemind-data", "-E", "root_owner=0:0", "-d", datafs, img, f"{size_mib}M")
        else:
            continue  # bios (written below), system-b (filled by the first update), recovery (empty, B2.3)
        if os.path.getsize(img) > nsec * 512:
            sys.exit(f"ERROR: {img} is larger than partition {p['label']}")
        sparse_copy(img, disk, first * 512)
        if img != a.system:
            os.remove(img)
    if board["route"] == "grub-bios":
        bios = next(p for p in lay["partitions"] if p["type"] == "bios")
        first, nsec = geo[bios["label"]]
        install_bios_boot(disk, stage, first, nsec)
    print(out("sgdisk", "-p", disk))
    log(f"disk {disk} ({lay['disk_size']}) for board {board['name']}")


# ------------------------------------------------------------------ bundle
def cmd_bundle(a):
    board = load_board(a.board)
    d = tempfile.mkdtemp(prefix="bundle-", dir=os.path.dirname(os.path.abspath(a.out)))
    try:
        os.link(a.system, os.path.join(d, "rootfs.ext4")) if same_fs(a.system, d) else shutil.copyfile(a.system, os.path.join(d, "rootfs.ext4"))
        open(os.path.join(d, "manifest.raucm"), "w").write(
            f"[update]\ncompatible={board['compatible']}\nversion={a.version}\n\n"
            f"[bundle]\nformat={a.format}\n\n[image.rootfs]\nfilename=rootfs.ext4\n")
        if os.path.exists(a.out):
            os.remove(a.out)
        run("rauc", "bundle", f"--cert={a.cert}", f"--key={a.key}", d, a.out, stdout=subprocess.DEVNULL)
    finally:
        shutil.rmtree(d)


def same_fs(p, d):
    return os.stat(p).st_dev == os.stat(d).st_dev


# ------------------------------------------------------------------ image
def cmd_image(a):
    os.makedirs(a.out_dir, exist_ok=True)
    cmd_tree(a)
    system = os.path.join(a.work, "system.ext4")
    cmd_ext4(argparse.Namespace(work=a.work, out=system, size_mib=None))
    disk = os.path.join(a.out_dir, f"onemind-{a.board}-{a.version}.img")
    cmd_disk(argparse.Namespace(board=a.board, work=a.work, system=system, out=disk))
    outs = [disk]
    if a.cert and a.key:
        bundle = os.path.join(a.out_dir, f"onemind-{a.board}-{a.version}.raucb")
        cmd_bundle(argparse.Namespace(board=a.board, system=system, version=a.version, cert=a.cert,
                                      key=a.key, out=bundle, format="verity"))
        outs.append(bundle)
        # A second bundle one version later, signed by the same throwaway CA, so a founder kit
        # (LT-DO-01, LT-X86-01) can run a real A -> B update on the image it just flashed.
        nxt = f"{a.version}-next"
        osr = os.path.join(a.work, "tree", "usr/lib/os-release")
        txt = open(osr).read().replace(f'ONEMIND_VERSION="{a.version}"', f'ONEMIND_VERSION="{nxt}"')
        open(osr, "w").write(txt)
        cmd_ext4(argparse.Namespace(work=a.work, out=system, size_mib=None))
        nbundle = os.path.join(a.out_dir, f"onemind-{a.board}-{nxt}.raucb")
        cmd_bundle(argparse.Namespace(board=a.board, system=system, version=nxt, cert=a.cert,
                                      key=a.key, out=nbundle, format="verity"))
        outs.append(nbundle)
    shutil.copyfile(os.path.join(a.work, "tree", "usr/lib/onemind/packages.txt"),
                    os.path.join(a.out_dir, f"onemind-{a.board}-{a.version}.packages.txt"))
    with open(os.path.join(a.out_dir, "SHA256SUMS"), "a") as f:
        for o in outs:
            h = hashlib.sha256()
            with open(o, "rb") as s:
                for buf in iter(lambda: s.read(CHUNK), b""):
                    h.update(buf)
            f.write(f"{h.hexdigest()}  {os.path.basename(o)}\n")
    os.remove(system)
    log("done: " + ", ".join(os.path.basename(o) for o in outs))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    t = sp.add_parser("tree"); t.set_defaults(fn=cmd_tree)
    e = sp.add_parser("ext4"); e.set_defaults(fn=cmd_ext4)
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
    for p in (b,):
        p.add_argument("--board", required=True); p.add_argument("--system", required=True)
        p.add_argument("--version", required=True); p.add_argument("--out", required=True)
        p.add_argument("--format", default="verity", choices=["verity", "plain"])
    for p in (b, i):
        p.add_argument("--cert", required=p is b); p.add_argument("--key", required=p is b)
    i.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
