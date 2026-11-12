# Refuter report: W5-P0-2 (k3s SQLite backup and restore), technical lens

- **Refuter lens:** technical (datastore internals, restore mechanics, PVC data consistency, version skew)
- **Date:** 2026-11-10 · **Re-check by:** 2027-05-10 (Kubernetes/k3s facts: 6 months)
- **Verdict:** **weakened.** The mechanism is correct and the lab ran it end to end. But the claim leaves out a condition the lab itself depended on (the same node name). The PVC-data proof for the *SQLite* restore comes from a log taken after a second restart that also converted the box to etcd. "Supported" overstates what the vendor documents. The test covered one run, one k3s version, identical VMs and a static 33-byte file.

## Claim under test

> A single-box k3s SQLite datastore has a supported backup path: copy /var/lib/rancher/k3s/server/db plus the server token. Because kine opens SQLite in WAL mode, the copy must use SQLite's online backup API (or k3s must be stopped). An online `sqlite3 .backup` plus token, node password and a restic snapshot of the local-path volumes restored onto a second, freshly installed VM, recovering a ConfigMap, an encrypted Secret and the PVC data.

## What the cited sources confirm (re-opened 2026-11-10)

| Item | Source | Status |
|---|---|---|
| SQLite backup = copy `server/db/`; restore its contents plus the token; a wrong token makes the snapshot unusable because the token encrypts confidential data | `k3s-io/docs@8958508d:docs/datastore/backup-restore.md` L7-L18 | Confirmed. The page says **nothing** about WAL, online copies, `sqlite3 .backup`, stopping k3s, or `/etc/rancher/node/password`. |
| kine opens SQLite with `_journal_mode=WAL&_synchronous=NORMAL...` | `k3s-io/kine@35f43197:pkg/drivers/sqlite/sqlite.go` L22-L23 | Confirmed. The same file also has a `NewWithLitestream` variant (kine runs with WAL checkpointing and startup checkpoint off so Litestream can replicate). The claim does not mention it, and it is a first-party continuous-backup path. |
| H1: `k3s etcd-snapshot save` on SQLite fails | lab `logs/a1.log` | Confirmed: `fatal ... etcd datastore disabled`, exit 1. |
| Online `.backup` while k3s running, `PRAGMA integrity_check` = ok, token + node password copied, restic of `/var/lib/rancher/k3s/storage` | lab `logs/a1.log` | Confirmed. A live `state.db-wal` (4.9 MB) existed at backup time, so the WAL premise holds. |
| ConfigMap and encrypted Secret recovered on the second VM | lab `logs/b1.log` | Confirmed: same CM value and Secret value. `logs/plaintext-check.log` shows the Secret is not plaintext in the backup (`secret-plaintext=0`), so the token really was needed. |
| PVC data recovered **on the SQLite restore** | lab `logs/b1.log`, `logs/b2-reverify.log` | **Not shown by b1.** b1 printed `pod Running` (stale status from the restored datastore), then `error: unable to upgrade connection: container not found ("w")` and an **empty** marker. The matching marker appears only in `b2.log` (01:19:14Z) and `b2-reverify.log` (01:29:48Z). Both come **after** phase b2 restarted k3s with `cluster-init: true` and migrated the datastore to etcd. |

## Strongest counter-argument

1. **The SQLite restore never verified the PVC data by itself.** Under the cited logs, the SQLite-only restore (b1) failed its marker check. The marker was read only after a further restart that converted the box to embedded etcd (b2). The data on disk does not depend on the datastore, so the claim is very probably true. But the evidence chain as cited proves "SQLite restore, *then* etcd conversion, recovers PVC data", not "SQLite restore recovers PVC data". b1 also shows a real operational trap: right after a restore, the API reports the old Pod as `Running` from restored state before containerd has recreated the container. A restore drill that trusts `kubectl get pod` will pass when it should not. Fix: rerun b1 alone with the same retry loop as `reverify.sh`, and gate drills on reading the data, not on pod phase.

2. **The claim drops a required condition: the node name.** `logs/pv-type.log` and `a1.log` show the local-path PV is a `local` volume with `nodeAffinity=["box1"]`. Both VMs ran with `node-name: box1` pinned in `config.yaml`, and the lab README states H2 "PROVIDED the node name is kept". Restoring onto new hardware with a default hostname leaves the PVC bound to a node that never appears, and the Pod stays Pending. The claim's "freshly installed VM" hides this. Any OneMind whole-box restore (UX-6, new hardware) must pin or migrate the node name, or rewrite PV affinity.

3. **"Supported" overstates the vendor position.** The only vendor-supported procedure is "take a copy of `server/db/`". Taken literally on a running box (cp, rsync, a restic file backup of `/var/lib/rancher`), that is exactly what SQLite warns can corrupt: "Systems that run automatic backups in the background might try to make a backup copy of an SQLite database file while it is in the middle of a transaction... might contain some old and some new content, and thus be corrupt" (sqlite.org/howtocorrupt §1.2). The online `.backup` procedure is the **author's derived, correct practice**, not something k3s documents or tests. The node-password step is also undocumented. Call it "documented minimum plus a required WAL-safe method", not "supported path".

4. **Version skew is untested and is a real failure mode.** Both VMs ran the pinned v1.37.2+k3s1. A real restore months later onto a "fresh install" gets whatever `get.k3s.io` serves, which is the latest stable release. k3s maintainers say minor versions must be stepped through without skipping (k3s#13066, brandond: "you need to step through each of the 13 minor versions... without skipping any"). kine has changed the stored format of internal rows between patch-level bundles: in k3s#13650, the `compact_rev_key` value format changed between kine v0.14.0 and v0.14.11 (k3s v1.34.1 to v1.35.1). That one was benign (one error per second until the first compact), but it shows the SQLite file is not a version-neutral artifact. A backup must record the k3s version and restore onto **that** version, then upgrade.

5. **PVC data consistency was not tested.** The workload wrote 33 bytes once and then slept. restic reads a live file system, which Velero's own docs call "not captured at the same point in time, so is less consistent than the snapshot approaches" (velero.io file-system-backup). For OneMind's real apps (Postgres, SQLite-backed apps, Home Assistant), a restic run over `/var/lib/rancher/k3s/storage` while pods are writing can produce a torn database. The claim's "PVC data" result does not carry over to databases without app-level dumps, quiesce hooks or a filesystem snapshot (ZFS/btrfs/LVM).

6. **Edge-hardware failure modes that affect the backup itself.** On a Pi with an SD card, `state.db` can grow to 19 GB and stall k3s when compaction falls behind (k3s#11901). kine never actually runs `VACUUM`, despite a maintainer saying it did (kine#607, maintainer: "it doesn't actually vacuum, it just truncates the WAL"), so a DB that ballooned stays large in every backup. On-disk corruption reports ("database disk image is malformed", k3s#9787) show the source can be corrupt before backup. `PRAGMA integrity_check` on the copy (which the lab did) must be mandatory, and a corrupt copy must fail the job.

7. **Sample size.** One run, same architecture (arm64 VMs, virtio disk), same k3s version, same hostname, no restore-without-token negative control, and no x86, Pi SD card or Jetson.

## New sources (opened 2026-11-10; found by searching for failure, corruption, regressions and lifecycle cuts)

1. **SQLite, "How To Corrupt An SQLite Database File"** §1.2-1.4: https://www.sqlite.org/howtocorrupt.html . Copying a database during a transaction can corrupt it. The safe methods are the backup API, `VACUUM INTO` and `sqlite3_rsync`. Copying while idle is safe only if the `-wal` file travels with the database. (Failure mode; PRIMARY.)
2. **k3s#13650**, "failed to parse compact revision ... following upgrade" (Feb 2026, single-server SQLite): https://github.com/k3s-io/k3s/issues/13650 . The kine row format changed between k3s v1.34.1 and v1.35.1. (Regression and version skew; PRIMARY.)
3. **k3s#13066**, "k3s cannot start after running for a while using the built-in database sqlite" (Oct 2025): https://github.com/k3s-io/k3s/issues/13066 . Maintainer: minor versions must be stepped through without skipping. The user's SQLite-to-etcd migration hung. (Failure and lifecycle; PRIMARY.)
4. **k3s#11901**, "`state.db` grows too large" (Mar 2025, Pi 4 on a 32 GB SD card, 19 GB DB): https://github.com/k3s-io/k3s/issues/11901 . (Edge-hardware failure; PRIMARY.)
5. **kine#607**, "Kine never calls VACUUM despite comment claims" (closed 2026-04-07): https://github.com/k3s-io/kine/issues/607 . Also **kine#586** (Litestream needs WAL checkpointing off; closed 2026-01-23): https://github.com/k3s-io/kine/issues/586 . (Docs vs code drift; PRIMARY.)
6. **k3s#9787**, "database disk image is malformed": https://github.com/k3s-io/k3s/issues/9787 . A compaction failure on a Pi 4 master with a 400 MB DB. (Corruption; PRIMARY.)
7. **Velero, File System Backup**: https://velero.io/docs/main/file-system-backup/ . Live file-system backup "is less consistent than the snapshot approaches". (PVC consistency limit; PRIMARY.)

## Suggested rewrite of the claim

> k3s documents SQLite backup as "copy `server/db/` plus the server token". Because kine runs SQLite in WAL mode, OneMind must take that copy with the SQLite online backup API (`sqlite3 .backup` or `VACUUM INTO`, then `PRAGMA integrity_check`), or with k3s stopped. It also saves `/etc/rancher/node/password`, the exact k3s version and the node name. In a 2026-11-10 lab (one run, arm64 VMs, k3s v1.37.2+k3s1), restoring onto a fresh VM **with the same k3s version and pinned node name** recovered a ConfigMap and an encrypted Secret. The local-path PVC file was read back after a later restart (the first in-pod read raced container recreation). App volumes need app-consistent dumps or a filesystem snapshot; restic of live volumes is not enough for databases. kine's Litestream mode is a candidate for continuous replication.

## What evidence would flip the decision

- **To upheld:** a rerun of phase b1 alone, on SQLite with no etcd conversion, that reads the marker with a retry loop. Plus one restore onto a VM **with a different hostname**, showing the documented node-name pin (or PV affinity rewrite) as a required step. Plus one restore of a backup from k3s N-1 onto a fresh N-1 install, then an upgrade.
- **To refuted:** any reproducible case where an integrity-checked `sqlite3 .backup` of a running k3s `state.db`, with the matching token, fails to start or loses objects on the same k3s version. Or a k3s or kine change that stops a SQLite file from being portable between installs (for example, binding encryption material to the host and not to the token).
- **Would change the method, not the verdict:** k3s adding a first-party `k3s sqlite-snapshot` or documenting Litestream as supported. OneMind should then use that and not its own `.backup` script.
