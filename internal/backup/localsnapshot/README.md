# Files history with Snapper

On a Debian image with btrfs, the data provisioner creates the `@storage`
subvolume at `/data/storage` and a separate `.snapshots` subvolume there.
The shipped `snapper-timeline.timer` creates read-only storage snapshots hourly.
Snapper retains up to 24 hourly, 7 daily, 4 weekly and 6 monthly restore points.

On hub boot, Files uses `/data/storage/files` through a bind mount at its existing
`/data/onemind/files` path. First boot migrates the previous Files tree before
the gateway, Samba and backups start, preserving ownership and permissions.
The gateway reads Snapper history through the root-owned snapshot directory,
which grants read and traversal access to the `onemind` group. The history
appears once a timeline snapshot contains Files.

An ext4 hub keeps its existing Files tree and has no local history. Files,
trash and off-box backups still work. The schedule requires no extra subvolume,
configuration file or timer on a supported btrfs hub.

Open a file preview and choose **Previous versions**. Restore places a copy
beside the current file, or at its original path if the name is free. If the
original folder is gone, API callers must supply `to_path` in an existing folder
in the same space. Retained snapshots can still hold copies after trash is
emptied. Use Backups for copies that survive disk failure.

On the hub, run `sudo onemind snapshots` or `sudo onemind snapshots --json` to
list its Snapper storage timeline. Snapshot writes and retention remain managed
by Snapper. Folder restore and a CLI restore command are deferred.

## Linux integration check

Run from the repository root on a Linux build worker. The container creates a
disposable loopback btrfs filesystem, runs the shipped timeline helper, and
verifies that a signed-in household member restores the original bytes.

```sh
docker run --rm --privileged -v "$PWD:/work:ro" -w /work python:3.12-slim-trixie \
  sh -ec 'apt-get update -qq; apt-get install -y -qq snapper btrfs-progs dbus; pip install -q uv; sh internal/backup/localsnapshot/test-timeline.sh'
```
