# SPDX-License-Identifier: Apache-2.0
"""Grow the onemind-data partition to the end of the disk, then what sits on it: the LUKS2 volume (if any) and the
btrfs or ext4 filesystem (IMG-02, #149; plan PR 5 for LUKS2 + btrfs).

An image written to a bigger disk (a 256 GiB NVMe, a Mac VM disk someone enlarged) has the layout of
the build disk: the data partition stops where the 32 GiB image stopped. This runs at every boot,
after /data is mounted, and is a no-op unless there is free space behind the data partition.

What it will NOT do, ever (the data is the owner's):
  - shrink, move, delete or re-create the partition, or make a new filesystem;
  - touch the disk if the data partition is not the last partition, is not GPT, or does not hold ext4 or btrfs
    (directly, or inside a LUKS2 volume that data_encrypt.py unlocked);
  - run when the partition's free space is under 4 MiB (the rounding of a normal disk).
It rewrites ONE partition table entry (same start, same type, GUIDs and name, bigger size) and grows what is on it
online, with /data mounted and untouched: `cryptsetup resize` for a LUKS2 volume (the volume key is in the kernel
keyring since it was unlocked, so no passphrase is asked), then `btrfs filesystem resize max` or resize2fs.
The same filesystem step runs when the partition was already enlarged by someone else (cloud-init's growpart on
clouds and droplets, rpi5-grow on the Pi): a btrfs or LUKS2 /data is always made to fill its device, and an ext4 one
too when called with --fs (the cloud grow service does).
"""
import json, os, re, subprocess, sys

LABEL = "onemind-data"
MIN_FREE_SECTORS = 8192          # 4 MiB at 512 bytes; below this the "free space" is rounding
BACKUP_GPT_SECTORS = 33          # the backup table and header at the end of a GPT disk


def say(msg):
    line = f"onemind-data-extend: {msg}"
    print(line, flush=True)
    try:
        with open("/dev/console", "w") as c:
            c.write(line + "\n")
    except OSError:
        pass


def plan(table, disk_sectors, label=LABEL):
    """(None, why) when nothing should be done, else ({node, number, script}, why).
    `table` is `sfdisk --json` output; `disk_sectors` the disk size in 512-byte sectors."""
    pt = table["partitiontable"]
    if pt.get("label") != "gpt":
        return None, f"the disk has a {pt.get('label')} table, not GPT"
    if int(pt.get("sectorsize", 512)) != 512:
        return None, "sector size is not 512 bytes"
    parts = pt.get("partitions", [])
    data = [p for p in parts if p.get("name") == label]
    if len(data) != 1:
        return None, f"found {len(data)} partitions named {label}, need exactly one"
    d = data[0]
    end = d["start"] + d["size"]
    if any(p["start"] + p["size"] > end for p in parts if p is not d):
        return None, "the data partition is not the last one; leaving the disk alone"
    free = (disk_sectors - BACKUP_GPT_SECTORS) - end
    if free < MIN_FREE_SECTORS:
        return None, "the data partition already fills the disk"
    m = re.search(r"(\d+)$", d["node"])
    if not m:
        return None, f"cannot read the partition number from {d['node']}"
    # Same start, GUIDs and name; only the size changes ("+" is sfdisk's "as large as possible").
    script = f"start={d['start']}, size=+, type={d['type']}, uuid={d['uuid']}, name={label}\n"
    return {"node": d["node"], "number": int(m.group(1)), "script": script,
            "free_mib": free * 512 // (1 << 20)}, "growing"


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout


def rewrite_entry(number, disk, script):
    """Rewrite the partition entry and tell the kernel, with udev's event queue paused.

    Why (issue 391): `partx -u` makes the kernel announce a change for the disk and every partition, and
    udev re-reads the table while it is still being written. For a moment the by-partlabel, by-partuuid
    and by-path names of the *mounted* data partition vanish, systemd sees those device units go dead
    and, because data.mount and every bind mount from it require the device, unmounts /data and stops
    everything that needs it: cloud-init, first boot, rauc. It happened on roughly one first boot in
    fifty (cloud images, where this always grows the disk). With the queue paused, udev reads the table
    once, after both steps are done. 240 rewrites on a booted image never dropped /data this way;
    without the pause it dropped within 30. The queue is always started again, even when a step fails:
    a queue left stopped would stop every later device event on the box."""
    paused = subprocess.run(["udevadm", "control", "--stop-exec-queue"], capture_output=True).returncode == 0
    try:
        run(["sfdisk", "--quiet", "--no-reread", "--no-tell-kernel", "-N", str(number), disk], input=script)
        run(["partx", "-u", "--nr", str(number), disk])
    finally:
        if paused:
            subprocess.run(["udevadm", "control", "--start-exec-queue"], capture_output=True)
            subprocess.run(["udevadm", "settle", "--timeout=30"], capture_output=True)


def sysfs(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def crypt_parent(node):
    """For the unlocked volume data_encrypt.py opened (/dev/dm-N, LUKS2): (mapper name, the one partition under it).
    (None, None) for anything else, including a dm device that is not LUKS2 or has more than one device under it."""
    base = os.path.basename(node)
    name, uuid = sysfs(f"/sys/class/block/{base}/dm/name"), sysfs(f"/sys/class/block/{base}/dm/uuid")
    try:
        slaves = os.listdir(f"/sys/class/block/{base}/slaves")
    except OSError:
        slaves = []
    if not name or not uuid.startswith("CRYPT-LUKS2-") or len(slaves) != 1:
        return None, None
    return name, "/dev/" + slaves[0]


def grow_fs(node, fstype, crypt=None, mountpoint="/data"):
    """Make the LUKS2 volume (when there is one) and then the filesystem as large as what is under them. Idempotent: at
    full size each command changes nothing. Online, /data stays mounted."""
    if crypt:
        run(["cryptsetup", "resize", crypt])
    if fstype == "btrfs":
        run(["btrfs", "filesystem", "resize", "max", mountpoint])
    elif fstype == "ext4":
        run(["resize2fs", node])


def disk_of(node):
    return "/dev/" + run(["lsblk", "-ndo", "PKNAME", node]).strip()


def main(argv=()):
    node = os.path.realpath(f"/dev/disk/by-partlabel/{LABEL}")
    if not os.path.exists(node):
        say(f"no partition labelled {LABEL} (not a GPT OneMind disk); nothing to do")
        return 0
    part, crypt = node, None
    if os.path.basename(node).startswith("dm-"):
        # Encrypted /data (data_encrypt.py): the name points at the unlocked volume, not at a partition.
        crypt, part = crypt_parent(node)
        if not crypt:
            say("the data volume is a device-mapper volume that is not the LUKS2 one made by data_encrypt.py; nothing to do")
            return 0
    fstype = run(["blkid", "-o", "value", "-s", "TYPE", node]).strip()
    if fstype not in ("ext4", "btrfs"):
        say(f"the data partition holds {fstype or 'nothing recognised'}, not ext4 or btrfs; nothing to do")
        return 0
    disk = disk_of(part)
    sectors = int(run(["blockdev", "--getsz", disk]).strip())
    table = json.loads(run(["sfdisk", "--json", disk]))
    todo, why = plan(table, sectors)
    grew = False
    if todo is None:
        say(why)
    elif todo["node"] != part:
        say(f"{todo['node']} is not {part}; refusing")
    else:
        say(f"growing {part} by {todo['free_mib']} MiB to fill {disk}")
        rewrite_entry(todo["number"], disk, todo["script"])
        grew = True
    if grew or crypt or fstype == "btrfs" or "--fs" in argv:
        grow_fs(node, fstype, crypt)
        say("/data is now " + run(["df", "-h", "--output=size", "/data"]).split()[-1])
    return 0


def safe_main(argv=()):
    """Growing the disk is a convenience, never a reason for a box not to boot: whatever goes wrong
    (a missing tool, an odd table, a failed command) is logged with its reason and the exit is 0."""
    try:
        return main(argv)
    except subprocess.CalledProcessError as exc:
        say(f"not grown (command failed): {' '.join(map(str, exc.cmd))}: {(exc.stderr or '').strip()[-300:]}")
    except Exception as exc:  # noqa: BLE001 (nothing may fail the boot)
        say(f"not grown ({type(exc).__name__}): {str(exc)[:300]}")
    return 0


if __name__ == "__main__":
    sys.exit(safe_main(sys.argv[1:]))
