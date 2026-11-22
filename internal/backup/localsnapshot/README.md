<!-- SPDX-License-Identifier: Apache-2.0 -->
# Local versions (BAK-04 / #241, scheduler slice)

An administrator can opt an **already-provisioned btrfs subvolume** into hourly
and daily read-only snapshots. Defaults in the example retain 24 hourly and 7
daily versions. Downtime produces one current snapshot per cadence, not fake
historical versions. Creation and filesystem sync finish before retention runs.
Snapshots share the disk with live files: keep off-box backups through Backups.

The current image still formats `/data` as ext4. This slice never formats,
converts, migrates or restores data. Image enablement remains with STOR-1 / #152;
Files previous-version browsing and approved restore are later #241 slices.
The RAUC slots, health gate and rollback are unchanged.

On an existing btrfs installation, provision the Files root as a subvolume and
the snapshot directory outside it on the same filesystem. Both need protected,
administrator-owned ancestors with no symlinks or group/other write access.
The snapshot directory must be mode 0700. Nested subvolumes are refused because
[btrfs snapshots are non-recursive](https://btrfs.readthedocs.io/en/stable/btrfs-subvolume.html).
Do not convert an existing Files directory in place with this kit.

Write `/data/onemind/snapshots.json`, owned by root with mode 0600:

```json
{"source":"/data/onemind/files","directory":"/data/.snapshots/files","hourly":24,"daily":7}
```

Install the two `deploy/systemd/onemind-snapshots.*` units in systemd's local
unit directory, alongside `/usr/local/bin/onemindd`, then enable the timer with
`systemctl enable --now onemind-snapshots.timer`. Image binaries use `/usr/bin`;
an image integration must adapt the service path before enabling it.
`sudo onemind snapshots --json` lists real retained versions locally.
`journalctl -u onemind-snapshots.service` reports errors. Disabling the timer
stops future runs without deleting retained versions. No HTTP/AI mutation route
exists; the root-owned configuration is the administrator's schedule opt-in.

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
