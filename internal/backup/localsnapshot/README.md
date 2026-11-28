# Files history with Snapper

On a Debian image with btrfs, the data provisioner creates the `@storage`
subvolume at `/data/storage` and a separate `.snapshots` subvolume there.
The shipped `snapper-timeline.timer` creates read-only storage snapshots hourly.
Snapper retains up to 24 hourly, 7 daily, 4 weekly and 6 monthly restore points.

Files stays at `/data/onemind/files` across OS slot switches. On a btrfs hub,
first boot prepares a subvolume at that path before the gateway, Samba and
backups start. It preserves file contents, ownership and permissions. Older
slots can read and write the same tree without an extra mount.

A Snapper plugin pairs each storage timeline entry with a read-only snapshot
of that Files subvolume. The capture lives under `/data/storage/.snapshots/.files`,
outside the live tree used by off-box backups. The root-owned history directory
grants read and traversal access to the `onemind` group. When Snapper expires an
entry, the plugin removes its Files capture too.

An ext4 hub keeps its existing Files tree and has no local history. Files,
trash and off-box backups still work. The existing Snapper timers schedule
creation and cleanup for both storage history and its Files captures.

Open a file preview and choose **Previous versions**. Restore places a copy
beside the current file, or at its original path if the name is free. If the
original folder is gone, API callers must supply `to_path` in an existing folder
in the same space. Retained snapshots can still hold copies after trash is
emptied. Use Backups for copies that survive disk failure.

On the hub, run `sudo onemind snapshots` or `sudo onemind snapshots --json` to
list its Snapper storage timeline. Snapshot writes and retention remain managed
by Snapper. Folder history, folder restore and a CLI restore command are deferred.

## Linux integration check

Run from the repository root on a Linux build worker. The container creates a
disposable loopback btrfs filesystem, tests the older slot's read and write
behavior, runs the shipped timeline helper, and verifies signed-in restore and
capture cleanup.

```sh
docker run --rm --privileged -v "$PWD:/work:ro" -w /work python:3.12-slim-trixie \
  sh -ec 'apt-get update -qq; apt-get install -y -qq snapper btrfs-progs dbus; pip install -q uv; sh internal/backup/localsnapshot/test-timeline.sh'
```
