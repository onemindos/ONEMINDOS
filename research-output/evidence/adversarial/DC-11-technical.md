# DC-11: refuter report on backup and restore coverage, including single-node SQLite (technical lens, round 4)

- **Conclusion under test (decision-critical DC-11 Result, rev. 3; 01 §4.6):** single-box datastore = online `sqlite3 .backup` + integrity check + token + node password + encryption config inside a restic snapshot. A full restore onto a fresh VM brought back all 32 pods with identical data [C-LAB-k3s-footprint-restore-011]. Clusters use `etcd-snapshot`, restic-wrapped. Daily `restic check --read-data-subset`, weekly scratch restore. The integrity check gates the backup.
- **Flip condition:** no supported SQLite backup/restore and no in-place migration to etcd, so the single-box default must change.
- **Lens:** technical. I read only the conclusion, 01 §4.6 and claim C-LAB-k3s-footprint-restore-011. I formed this view before reading any other refuter file.
- **Date:** 2026-11-11

## Verdict: **weakened** (the flip condition is not met, since backup and restore work; but the gate checks the wrong property, and the lab proved only the easy case)

The lab result is real: a WAL-safe online copy plus token restores a small, healthy datastore. The procedure has a blind spot. **`PRAGMA integrity_check` detects corruption, not a sick datastore**:

1. **A stalled compactor makes a structurally valid but runaway database.** On SQLite, failed kine compaction means "the database will grow without bound. That is how it works", with state.db reported at up to 12 GB [C-REF4-DC-technical-006]. kine v0.13.4–v0.13.9 could stop compacting permanently after one SQL error [C-REF4-DC-technical-007]. Upstream's answer for a spiralling datastore is operational (let compaction catch up), not a code fix [C-REF4-DC-technical-008]. Such a database passes the integrity gate. OneMind would back it up faithfully every night and restore it faithfully, together with the API timeouts it causes.
2. **The restore drill doesn't cover that size.** The lab restored a 32-pod, freshly created datastore. Recovering a bloated one needs offline compaction plus `VACUUM`, which needs up to about twice the database size in free space. None of this is in 01 §4.6, and on a full 4 GB-class box the space may not exist.
3. **Daily `--read-data` checks on non-ECC boxes will raise alarms nobody can triage.** restic 0.19.1 (the version the lab used) has an open report of `check --read-data` declaring a repository damaged after transient "wrong data" reads, which maintainers attribute to hardware [C-REF4-DC-technical-009]. OneMind's boxes are non-ECC consumer hardware. A "last verified restore" dashboard fed by that check will produce alarms that a home user can't tell apart from real corruption, and memory errors can also corrupt data before it is backed up. The procedure says nothing about either.

## Strongest counter-argument

D5's single-box guarantee is "we can put back exactly what was there". For k3s on SQLite, the most likely datastore failure is not corruption. It is unbounded growth from a stalled compactor, which upstream treats as normal, and which has had a recent stop-forever regression. A backup design that validates only page-level integrity and restores only a small fresh database will certify the failure as healthy, then restore it. The restore should be judged on whether the API server is healthy after restore, within a size budget, not on bytes being identical.

## New sources (searched for regressions and data-integrity failures; each opened)

- **N1.** k3s-io/k3s issue #12898 (unbounded state.db growth on compaction failure). [C-REF4-DC-technical-006]
- **N2.** k3s-io/kine PR #414 (compaction stop-forever regression). [C-REF4-DC-technical-007]
- **N3.** k3s-io/k3s issue #10619 (compaction "spiral", operational remedy only; Galera context, so it shows the mechanism, not SQLite incidence). [C-REF4-DC-technical-008]
- **N4.** restic/restic issue #22105 (0.19.1 `check --read-data` false-damage pattern, attributed to hardware). [C-REF4-DC-technical-009]

## What would flip this verdict

- **To upheld:** the backup gate adds datastore-health checks (state.db size budget, compact-revision lag, API latency after a restore probe), and the CI restore drill includes a multi-GB, compaction-stalled state.db that is restored **and** recovered (offline compaction + VACUUM) within the box's free-space budget.
- **To refuted (SQLite default):** a bloated state.db cannot be compacted back on-device within free space, or the restored cluster stays unhealthy. Then single boxes need etcd (pending T-W5-03) or a different recovery path.

## Recommended change (for the owner, not applied)

Add to 01 §4.6: (a) pin kine ≥ v0.13.10 in every shipped k3s; (b) refuse to mark a backup "verified" if state.db exceeds a size budget or compaction lags; (c) a documented on-device offline-compaction procedure with a free-space precheck; (d) on `restic check` failure, retry once and run a memory test before telling the user the repository is damaged.
