# Local versions (BAK-04 / #241)

An administrator can opt an **already-provisioned btrfs subvolume** (the Files root) into hourly
and daily read-only snapshots. Defaults in the example retain 24 hourly and 7
daily versions. Downtime produces one current snapshot per cadence, not fake
historical versions. Creation and filesystem sync finish before retention runs.
Snapshots share the disk with live files: keep off-box backups through Backups.

Members see a file's earlier versions on the dashboard Files page (preview, then
"Previous versions") and restore one as a **new file**: beside the current file when
its name is taken, never over it. The gateway reads the snapshots read-only
(`GET /v1/files/versions`, op `restore_version` on `POST /v1/files/ops`,
core/onemind_core/files/versions.py); only people restore, never an app or agent.

The current image still formats `/data` as ext4. This slice never formats,
converts, migrates or restores data. Image enablement remains with STOR-1 / #152.
The RAUC slots, health gate and rollback are unchanged.

On an existing btrfs installation, provision the Files root as a subvolume and
the snapshot directory outside it on the same filesystem. Both need protected,
administrator-owned ancestors with no symlinks or group/other write access (a sticky
directory such as `/tmp` is the one exception, and never directly above the Files root).
The Files root itself may be owned by the gateway user `onemind`, which creates folders in it.
The snapshot directory must be mode 0700, or 0750 with group `onemind` so the
gateway can show versions in Files (root alone writes it; others get nothing). Nested subvolumes are refused because
[btrfs snapshots are non-recursive](https://btrfs.readthedocs.io/en/stable/btrfs-subvolume.html).
Do not convert an existing Files directory in place with this kit.

Write `/data/onemind/snapshots.json`, owned by root with mode 0600:

```json
{"source":"/data/onemind/files","directory":"/data/.snapshots/files","hourly":24,"daily":7}
```

The image ships `onemind-snapshots.service` and `.timer` in `/usr/lib/systemd/system`
with the timer already enabled; the service runs `/usr/bin/onemindd snapshots-tick`
only when that file exists, so writing it is the whole opt-in. For Files to show
versions, make the directory `root:onemind` mode 0750 and keep the gateway's
`ONEMIND_FILES_SNAPSHOTS_DIR` (default `/data/.snapshots/files`) pointing at it.
`sudo onemind snapshots --json` lists real retained versions locally.
`journalctl -u onemind-snapshots.service` reports errors. Deleting the file
stops future runs without deleting retained versions.

The directory is a reserved namespace: `hourly-<UTC time>` and `daily-<UTC time>`
belong to this scheduler. Other names remain untouched. Matching names must be
read-only btrfs snapshots with the configured source's Parent UUID; otherwise
the entire run fails before pruning. An advisory lock excludes concurrent ticks.

Run unit tests with `go test -race ./internal/backup/localsnapshot`. In a disposable
Linux VM with root, btrfs-progs, util-linux and coreutils, run
`sudo env ONEMIND_BTRFS_TEST=1 go test -v ./internal/backup/localsnapshot`.
The integration test formats only a new 512 MiB loop file under `/run`, tests
byte preservation, read-only snapshots, retention and nested-subvolume refusal,
then unmounts it. It never formats an existing disk or changes RAUC state.
