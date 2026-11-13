<!-- SPDX-License-Identifier: Apache-2.0 -->
# internal/backup: the onemindd backup agent

**Design:** [docs/architecture/BACKUPS.md](../../docs/architecture/BACKUPS.md) (build step K2, with the node-side parts of K5, K6 and K7). **API shapes:** CONTRACT-12-DRAFT §12.5 and §12.11.

> **In plain words.** Every hour this agent asks restic, a well-known open-source backup program, to copy what changed on this machine into an encrypted backup on a USB disk, on another OneMind machine, or in an S3 bucket. Each piece (the system's own records, Kubernetes, each app, the node's identity) becomes its own *snapshot* (a frozen copy at one moment). Old snapshots are thinned out on a ladder: one per hour for a day, one per day for a week, one per week for a month, one per month for a year. Every week the agent restores each piece into an empty scratch folder and reads every file back. A backup only counts as *verified* when that test passes. You can browse any snapshot and put back one file or folder. Before it overwrites anything, the agent snapshots what is there now, so every restore can be undone.

## What is in the package

| File | What it does |
|---|---|
| `pins.go` | restic 0.19.1 and rest-server 0.14.0 for amd64 and arm64: release URL, archive sha256 (upstream `SHA256SUMS`) and binary sha256. `New` refuses a restic binary whose sha256 is not the pin |
| `config.go` | `agent.json`: box and node ids, generation, targets (`usb`, `node`, `s3`), units, schedule, retention ladder (hourly 24, daily 7, weekly 4, monthly 12, configurable) |
| `restic.go` | `Repo` interface and `Restic`, which runs restic as a subprocess. Credentials go into the child's environment, never onto the command line. The child gets a minimal environment, so stray `RESTIC_*` or `AWS_*` variables are not inherited |
| `units.go` | Units `system`, `k3s`, `app:<id>`, `node:<id>` and their hooks: SQLite online backup plus `PRAGMA integrity_check` (gateway DB, k3s `state.db`), a command whose output is stored (for example `pg_dump`), and an audit-log copy that checks the hash chain links and tags the head hash |
| `agent.go` | `Run`: fence check, space check, one snapshot per unit, retention per unit and keep class. Also `WriteFence`, `GenerateKey`, `Heartbeat`, `Status` |
| `schedule.go` | Hourly run at a fixed minute per box. Daily, in the maintenance hour: repository check, plus a direct run to every non-primary target (the off-site copy). Weekly: verified restores and prune. `Loop` drives it |
| `verify.go` | `VerifyRestore`: restore into scratch, read every file back, compare sizes with the snapshot listing, run hook checks on the restored copies, record "last verified restore". `CheckRepo`: rotating `--read-data-subset` (n/7, or n/28 on S3) with one retry |
| `rewind.go` | `ListSnapshots`, `Tree`, `DumpFile`, `RestorePath` (one file or directory, pre-restore snapshot first, atomic rename into place, refuses symlinked parents and paths outside the unit's sources) |
| `api.go` | Loopback-only `GET /api/v1/backup/status` and signed `POST /api/v1/backup/jobs` (the unsigned `/run` route was removed: runs only come as gateway-signed jobs) |
| `state.go` | `state.json` (0600, atomic replace): runs, verifications, last verified per unit, schedule bookkeeping. Badge rules for BT-11 |

### Tags and retention

Every snapshot carries `onemind`, `box=`, `gen=`, `unit=`, `node=`, `run=`, `reason=`, plus per unit `app=`, `rev=`, `k3s=` or `audit_head=` (BACKUPS.md §10). So `restic snapshots` explains the repository without OneMind. The agent adds one tag that BACKUPS.md does not list yet: **`keep=ladder|14d|30d`**. Retention runs per unit and per keep class (`forget --tag onemind,box=<id>,unit=<u>,keep=<class> --group-by ''`). Scheduled and manual snapshots share the ladder. `pre-update` and `pre-restore` snapshots are kept 14 days, and `pre-delete` snapshots 30 days, on their own rule, so the ladder never thins out a safety snapshot. The filter always names the box, so boxes that share a bucket never forget each other's snapshots. restic's `--keep-within` counts back from the newest snapshot in the group, not from now.

The agent never runs `forget` or `prune` against an append-only target, and rest-server would refuse it anyway (tested). Pruning those targets is the owner-approved job on the target node (BACKUPS.md §4).

### Safety rules in the code

- **USB disk must be mounted.** If the disk is unplugged, `/run/onemind/backup/<uuid>` is an empty folder on the system disk. The agent checks that the path is a mount point (its device differs from its parent's) and refuses otherwise.
- **Space check:** before a run to a USB disk, the agent refuses when free space is less than 2 × (growth of the sources since the last run + 10 %), and says how many bytes are needed.
- **Fence:** if any target holds a fence record with a newer generation for this box, the run is refused and the status turns red ("this box was replaced by a restore").
- **Hook failure fails the unit:** a damaged k3s `state.db` (integrity check not `ok`) or a broken audit chain writes no snapshot for that unit, and the run is `partial`.
- **Incomplete backups count as failed:** restic exit code 3 (snapshot made, some files unreadable) fails the unit. The snapshot id is still recorded.
- **Device key file** must be 0600 and non-empty. `GenerateKey` writes 256 random bits and never overwrites an existing key.

## Tests

```sh
go test ./internal/backup/                       # unit tests: in-memory fake repo, scripted restic runner
internal/backup/testdata/lima-integration.sh     # real restic + rest-server in a Debian 13 Lima VM
```

The unit tests cover BT-1, BT-2, BT-9, BT-11, BT-12 (source side) and BT-14 from BACKUPS.md §12, the FILES-7 file criteria (content and mtime match, undo restores the newer version), the restic command lines (one `--tag a,b` means AND, `--group-by ''`, no secret in argv), pins, config validation and the scheduler (catch-up after downtime runs once, not 24 times).

`integration_test.go` (build tag `integration`) runs against the real binaries. The Lima script cross-compiles the test on the host, downloads both pinned releases inside the VM, checks the archive sha256 values from `pins.go`, installs Debian's `sqlite3`, and runs with `ONEMIND_VERIFY_PINS=1`, so the binaries' own sha256 values are checked too. It covers:
- local target: tags visible to plain restic, excludes, tree and dump, restore one file with mtime plus undo, directory restore, verified restore of every unit (including a real SQLite online copy and integrity check), `check`, ladder retention with `--group-by ''` leaving pre-restore snapshots alone, `prune`, an added owner key opening the repository by itself (BT-3 part), and the fence (BT-9);
- `node` target: rest-server with `--tls --append-only --private-repos`, the agent's own CA file, backup, list and dump over HTTPS, `forget` refused by the server (BT-12), a wrong password refused rather than the repository re-created.

Result on 2026-11-12: both pass on Debian 13 arm64 (Lima, vz) with the linux/arm64 pins. They also pass on macOS arm64 with the darwin builds of the same versions. **Not covered:** an S3 target against a real S3 server (no S3-compatible server is pinned yet), and the linux/amd64 pins at run time (their sha256 values were computed from the verified archives, but no amd64 VM run was done).

## Wiring (BACKUP-WIRE-1, branch `feat/backups-on`)

| Step | Where | State |
|---|---|---|
| **One service:** the agent runs inside onemindd as `backup.Service()` (`optionalServices`), enabled when `agent.json` exists. `onemindd backup-init` is a one-shot that creates the device key; it is not a daemon | `service.go`, `cmd/onemindd/backup.go` | done. There is no second backup process or unit. Restores write app data with its owners, so the onemindd unit needs a drop-in with four capabilities (see `docs/leap/core/BACKUP-WIRE-os.patch.md`); `deploy/backup.sh` installs it |
| Loopback API on onemindd's `127.0.0.1:7480` under `/api/v1/backup/` (contract §12.12); the handler refuses non-loopback callers | `api.go`, `jobapi.go` | done |
| Signed jobs `POST /api/v1/backup/jobs` (`onemind.job/v1`, Ed25519, canonical JSON shared with the gateway, params hash, expiry, done-list) | `job.go`, `canonical.go`, `jobapi.go` | done |
| Gateway-managed destinations and apps (`managed.json`; credentials as 0600 files in `target-secrets/`; apps only by volume) | `managed.go` | done |
| App restore with move-aside, commit or rollback; volumes matched by claim | `apprestore.go` | done |
| Heartbeat `backup` object (§12.10) | `internal/heartbeat`, `internal/agent`, `cmd/onemindd/backup.go` | done |
| Gateway coordinator: hooks via exec, database dumps, schedule, status, restore orchestration | `core/onemind_core/backups/` | done |
| Developer install: pinned restic, `onemind-local`, keys, unit, gateway switch | `deploy/backup.sh` | done |
| Image | `docs/leap/core/BACKUP-WIRE-os.patch.md` | for the image stream |
| Updater gets a pre-update backup run through a gateway-signed `backup.run` job (the unsigned `/api/v1/backup/run` route was removed in #91) | `internal/update` | open (updater stream) |
| Owner and escrow keys on every target | `backup.key.add` job; the gateway's emergency kit adds the owner key | done for the owner key; escrow and rotation open |
| Whole-box restore and `WriteFence` | | open (onboarding) |

**End-to-end proof:** `test/backup-wire/lima-e2e.sh` (Debian 13 VM: developer install, back up, break, restore, Rewind, badge green, undo).

Steps from the earlier plan that are still open: the updater gets its pre-update run via a signed job (item above), and the image stream adds restic and rest-server pins (`BACKUP-WIRE-os.patch.md`).

## Where the repository password and keys live (and what is never logged)

In plain words: restic encrypts every backup with a password. The box makes that password itself (256 random bits, `onemindd backup-init`), keeps it in one file (`device_key_file`, mode 0600, folder 0700, on the encrypted `/data` partition once CORE-SEC-5 lands), and hands it to restic only as `RESTIC_PASSWORD_FILE`, a path. The password is never in a command line, never in an environment variable, never in the settings file, and never in a log line, an event or the audit log; the gateway's audit records only that destination credentials were `provided`. The owner and escrow keys are extra restic keys on the same repository (`restic key add`), so the printed emergency kit can open a backup with the device gone. Lose every key and the backup cannot be read: that is the point of encryption, and why setup blocks until the owner has typed the kit back. `backup-init` never overwrites an existing key, because a new password would orphan every snapshot already made (tested in `cmd/onemindd/backup_test.go`). If the agent cannot save its own state file (disk full or read-only) it logs it, counts it, and shows `state_write_errors` in `GET /api/v1/backup/status` (tested in `statewrite_test.go`).

Restores never start on their own: the agent obeys only a job signed with the gateway's Ed25519 key, and the gateway signs one only for an action the owner approved; the app restore moves the old data aside first and rolls back if the fresh pod fails its health check. The weekly verified-restore check (a scratch restore of every unit, `verify.go`) and the daily repository check still run on the agent's schedule, which is what keeps the badge green (`schedule_test.go`).

## Not done here (follow-ups)

- App verification with fresh pods in a sealed namespace (K7, gateway side). This package proves the files and databases. The gateway proves that the app starts.
- The memory test after a failed repository check (D-B7.6), and alerts. Results are recorded, but nothing raises an alert yet.
- `restic copy` from the primary to off-site targets. The daily off-site job is a direct run instead, which BACKUPS.md §3 allows.
- The space check only covers USB targets. `node` and S3 targets do not report free space to restic.
- Secrets passed through the environment are readable by root through `/proc/<pid>/environ` while restic runs. TPM-sealed keys (phase 3) do not change that for the child process.

## Third-party components

| Component | Version | Licence | How it is used |
|---|---|---|---|
| restic | 0.19.1 | BSD-2-Clause | separate executable, run as a subprocess |
| rest-server | 0.14.0 | BSD-2-Clause | separate executable on target nodes and in tests |
| sqlite3 CLI | Debian 13 package, pinned by the image stream | public domain | separate executable for online copies |

No code from umbrelOS or any other noncommercial-licensed project was used. The retention ladder values come from BACKUPS.md §3.
