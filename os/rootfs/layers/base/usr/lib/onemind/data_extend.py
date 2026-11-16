# SPDX-License-Identifier: Apache-2.0
"""Grow the onemind-data partition to the end of the disk, then its ext4 filesystem (IMG-02, #149).

An image written to a bigger disk (a 256 GiB NVMe, a Mac VM disk someone enlarged) has the layout of
the build disk: the data partition stops where the 32 GiB image stopped. This runs at every boot,
after /data is mounted, and is a no-op unless there is free space behind the data partition.

What it will NOT do, ever (the data is the owner's):
  - shrink, move, delete or re-create the partition, or make a new filesystem;
  - touch the disk if the data partition is not the last partition, is not GPT, or does not hold ext4;
  - run when the partition's free space is under 4 MiB (the rounding of a normal disk).
It rewrites ONE partition table entry (same start, same GUIDs and name, bigger size) and grows the ext4
online (resize2fs; the data stays mounted and untouched). Boards that grow the disk another way
(cloud-init's growpart on clouds and droplets, rpi5-grow on the Pi) leave nothing for this to do.
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


def disk_of(node):
    return "/dev/" + run(["lsblk", "-ndo", "PKNAME", node]).strip()


def main():
    node = os.path.realpath(f"/dev/disk/by-partlabel/{LABEL}")
    if not os.path.exists(node):
        say(f"no partition labelled {LABEL} (not a GPT OneMind disk); nothing to do")
        return 0
    if run(["blkid", "-o", "value", "-s", "TYPE", node]).strip() != "ext4":
        say("the data partition does not hold ext4; nothing to do")
        return 0
    disk = disk_of(node)
    sectors = int(run(["blockdev", "--getsz", disk]).strip())
    table = json.loads(run(["sfdisk", "--json", disk]))
    todo, why = plan(table, sectors)
    if todo is None:
        say(why)
        return 0
    if todo["node"] != node:
        say(f"{todo['node']} is not {node}; refusing")
        return 1
    say(f"growing {node} by {todo['free_mib']} MiB to fill {disk}")
    run(["sfdisk", "--quiet", "--no-reread", "--no-tell-kernel", "-N", str(todo["number"]), disk],
        input=todo["script"])
    run(["partx", "-u", "--nr", str(todo["number"]), disk])
    run(["resize2fs", node])
    say("/data is now " + run(["df", "-h", "--output=size", "/data"]).split()[-1])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        say(f"failed: {' '.join(exc.cmd)}: {(exc.stderr or '').strip()[-300:]}")
        sys.exit(1)
