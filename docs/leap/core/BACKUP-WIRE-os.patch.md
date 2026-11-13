<!-- SPDX-License-Identifier: Apache-2.0 -->
# BACKUP-WIRE: changes for the image stream (`os/**`)

**From:** branch `feat/backups-on` (BACKUP-WIRE-1, DB-SHARED-1, CORE-BACKUP-1 image part). **For:** the image-line stream, which owns `os/**` (WORKSTREAMS §3). The developer install already does all of this in `deploy/backup.sh`; the image needs the same, in its own places. Nothing below is applied by this branch.

> **Why.** On a OneMind image the root is read-only and `/data` holds everything that changes. The backup agent and the shared PostgreSQL need a few files baked in (pinned binaries, a systemd unit, manifests) and a few created on first boot (keys, settings). Each item names the file the developer install uses, so both paths stay the same.

## 1. `os/versions.lock.yaml` (add-only, under `tools:`)

Values are `internal/backup/pins.go` (read 2026-11-12 from the GitHub release `SHA256SUMS` and re-hashed); `deploy/check-pins.py` already compares `deploy/pins.env` with `pins.go`.

```yaml
  restic:           # backup engine (BACKUPS.md B-R1); /usr/lib/onemind/restic; the agent refuses another sha256
    version: 0.19.1
    linux_amd64_archive: restic_0.19.1_linux_amd64.bz2
    linux_amd64_sha256: f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c
    linux_amd64_binary_sha256: 20d4142678d0d95ec11a4759def1b73fd9190abc9ca19e4b62d067c0b387e639
    linux_arm64_archive: restic_0.19.1_linux_arm64.bz2
    linux_arm64_sha256: a5f64aaab53d51e311fa3829124c5b703f2d14cf187d8640b6be3b2b49376465
    linux_arm64_binary_sha256: 2fb45ac6f9071b6f20eb883953a188f9e7c7cb6bbe43c67a2e47ada4e85ee7f0
    license: BSD-2-Clause
    source: https://github.com/restic/restic/releases/tag/v0.19.1 SHA256SUMS, read 2026-11-12
  rest-server:      # append-only target on another OneMind box (BACKUPS.md §4); /usr/lib/onemind/rest-server
    version: 0.14.0
    linux_amd64_archive: rest-server_0.14.0_linux_amd64.tar.gz
    linux_amd64_sha256: 4c9c95bc079a0334e81fad379b19dc5c3353c71c2c88d652cafce2081c2b1c66
    linux_amd64_binary_sha256: ec4fa7c3472bdc1cde6bfa994d1ee3344bb6e9dc3d9c10c8ff5316e3e77af6fd
    linux_arm64_archive: rest-server_0.14.0_linux_arm64.tar.gz
    linux_arm64_sha256: cef139cbe8b27b16bda731d17f093b0aa466b8c60b136c12d78b6f2bff3daf22
    linux_arm64_binary_sha256: 578549202f1772706ae0f940ef684d1c19b2b2abe8e16d4c6845b1c0ee62f40c
    license: BSD-2-Clause
    source: https://github.com/restic/rest-server/releases/tag/v0.14.0 SHA256SUMS, read 2026-11-12
  postgres:         # shared PostgreSQL for apps (DB-SHARED-1); deploy/platform/postgres/statefulset.yaml
    image: docker.io/library/postgres:17.11-trixie@sha256:ff87138949ad9a46f32ff23bd6852b52ce024a13dffe9b4087be98292cdd3b4f
    license: PostgreSQL
    source: registry-1.docker.io manifest index (amd64, arm64 and others), read 2026-11-12
```

## 2. Root filesystem (`os/rootfs/**`)

| Put | From | Notes |
|---|---|---|
| `/usr/lib/onemind/restic` (0755) | the pinned archive above, sha256-checked twice (archive, binary) | the agent's `pins.go` check runs at every start |
| `/usr/lib/systemd/system/onemindd.service.d/backup.conf` | `deploy/systemd/onemindd-backup.conf` | **one backup service, inside onemindd** (`backup.Service()`): no separate unit. The drop-in gives onemindd four capabilities and the writable folders a restore needs; loopback API `127.0.0.1:7480/api/v1/backup/` |
| `/usr/lib/tmpfiles.d/onemind-backup.conf` | `d /run/onemind/backup 0755 root root -` and `d /data/onemind/storage 0700 root root -` | **required:** systemd drops a `ReadWritePaths=-…` entry whose folder is missing at start, which leaves app volumes read-only for restores (found by `test/backup-wire`) |
| Debian `sqlite3` | apt, in the image build | online copies of the gateway and k3s databases |
| `/usr/share/onemind/platform/postgres/` | `deploy/platform/postgres/` | the gateway applies it the first time an app asks for a database (`ONEMIND_DATABASES_PLATFORM_DIR` default) |
| `/usr/share/onemind/platform/storage/storageclass-onemind-local.yaml` | `deploy/platform/storage/` | CORE-BACKUP-1: on the image make it the **default** class and remove the default flag from k3s `local-path`; point the provisioner path at `/data/onemind/storage` |

## 3. First boot (before the gateway starts)

1. `/data/onemind/custodian/job.key` (0600, gateway user) with `job.pub` beside it: the gateway creates it on its first start if missing (`core/onemind_core/backups/jobs.py`); copy `job.pub` to `/data/onemind/backup/job.pub` for the agent, or point `job_pubkey_file` at it.
2. `/data/onemind/backup/agent.json`: as `deploy/backup.sh` writes it, with `box_id` and `node_id` = the node id (sha256 of `/etc/machine-id`, 12 hex), `state_dir` `/data/onemind/backup`, `storage_roots` `["/data/onemind/storage"]`, `schedule.gateway_hourly: true`, and the `system` unit naming the gateway database and audit log under `/data/onemind/`.
3. The device key: `ExecStartPre=onemindd backup-init` in the same drop-in (one-shot, not a daemon) creates it (256 random bits, 0600, never overwritten), on the LUKS2 `/data` once CORE-SEC-5 lands.
4. Gateway environment: `ONEMIND_BACKUPS_ENABLED=1`, `ONEMIND_BACKUPS_JOB_KEY_FILE=/data/onemind/custodian/job.key`.
5. onemindd environment: `ONEMIND_BACKUP_CONF=/data/onemind/backup/agent.json` (it starts the backup agent from it and reads the agent's state file for the heartbeat's `backup` object).

## 4. Not in this patch

USB disk detection and mounting at `/run/onemind/backup/<uuid>` (BACKUPS.md K5, storage stream), rest-server units on target boxes, and the onboarding restore are follow-ups listed in `core/onemind_core/backups/README.md`.
