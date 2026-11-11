# Refuter report: W5-P0-1 (technical lens)

- Date: 2026-11-10
- Lens: technical
- Protocol: RESEARCH-MISSION.md §2 rule 7. This refuter saw only the claim and its cited sources.
- **Verdict: UPHELD.** The mechanism and the observed behaviour hold. Two wording fixes are required: the scope of "cannot back up the cluster", and the exact error text.

## Claim under test

> On k3s v1.37.2+k3s1 with the default single-server SQLite datastore, `k3s etcd-snapshot` cannot back up the cluster. With no managed etcd driver, k3s answers its /db/ snapshot routes with 'etcd datastore disabled', and `k3s etcd-snapshot save` exits 1 with that error.

## What I checked in the cited sources

| Source | Result |
|---|---|
| `k3s-io/k3s@f6973cb850e9b245585363d15bde80904ac862fd:pkg/cluster/managed.go#L70-L75` | Confirmed, but the line numbers are off by about 2. The `if c.managedDB == nil { return handlerNoEtcd(handler), nil }` branch in `registerDBHandlers` sits at L72-L76. Cite `#L72-L76`. |
| same file `#L145-L157` | Confirmed. `handlerNoEtcd` (L146-L155) registers a wildcard `/db/` route that returns `errors.New("etcd datastore disabled")` with HTTP 400. Every other path falls through to the normal handler. The string appears nowhere else in the file. |
| `work/.lab/w5-restore/logs/a1.log` | The sha256 matches (`6dbc95cb…b1cd`). The binary reports `k3s version v1.37.2+k3s1 (f6973cb8)`, the same commit as the code citation. The log shows `level=fatal msg="Error: see server log for details: etcd datastore disabled"`, followed by `H1 exit=1`. |
| `work/.lab/w5-restore/scripts/drill.sh:95` | The exit code is genuine. `$?` is read straight after `/usr/local/bin/k3s etcd-snapshot save`, with no pipe or `tee` to mask it. |

## Strongest counter-argument

The narrow mechanism (no managed DB, so the `/db/` routes return 400 and the CLI exits fatally) can't be refuted. It is in pinned source and was reproduced on the same commit. The attack is on how the claim is framed and how far it reaches:

1. **"Cannot back up the cluster" overreaches.** Only *the `etcd-snapshot` subcommand* cannot. The official k3s docs say that "No special commands are required to back up or restore the SQLite datastore": copy `/var/lib/rancher/k3s/server/db/` plus the server token. The same lab run (a1.log, after H1) took an online copy, which passed `sqlite3 integrity: ok`, and stored it in restic in 4 s. A reader could take the claim to mean "SQLite k3s is not backup-able". That would be false, and it could push a decision towards etcd for the wrong reason.
2. **This is the default configuration, not a permanent limitation.** Restarting the server with `--cluster-init` converts SQLite to embedded etcd in place. After that, `etcd-snapshot` works; the same `drill.sh` exercises this at L128. Any decision that rests on this claim must weigh the conversion's own failure modes (below), not treat SQLite as a dead end.
3. **The error text is quoted loosely.** The CLI prints `Error: see server log for details: etcd datastore disabled`, because the server-side 400 is wrapped. A runbook or detection rule that greps for the bare string will still match. One that does an exact match will not.
4. **Version fragility.** The behaviour depends on `handlerNoEtcd` existing. A future k3s could add a kine-native snapshot path, which would invalidate the claim. I found no evidence that upstream plans this.

## New sources (searched for failure, regression and abandonment)

1. **k3s official docs, Backup and Restore**: https://docs.k3s.io/datastore/backup-restore (opened 2026-11-10). Documents SQLite backup as a file copy of `server/db/` plus the token, and mentions `etcd-snapshot` only under "Backup and Restore with Embedded etcd Datastore". This supports the claim's mechanism and refutes the broad reading "cannot back up the cluster".
2. **k3s-io/k3s issue #9765**, "K3s should not disable etcd and apiserver when used with kine": https://github.com/k3s-io/k3s/issues/9765 (opened 2026-11-10). Closed as completed on 2024-04-04, milestone v1.29.4+k3s1. It shows a past regression in how kine and etcd flags interact: a nil-pointer panic when `k3s server` was run directly, and a server that started but never became ready. The etcd-or-not code path has a bug history, so the claim needs re-checking per release (rule 10: re-check-by 2027-05-10).
3. **T. Wostal, "When Your Homelab Grows Up: How SQLite Took Down My k3s Control Plane"**, 2026-06-19: https://wostal.eu/blog/homelab-grows-up-sqlite-to-etcd/ (opened 2026-11-10; `SECONDARY`). This is a failure report on k3s SQLite. Kine compaction fell behind, leaving about 1.36M rows and a 13.8 GB WAL that wouldn't checkpoint. Separately, the "already migrated" check gave a false positive because a leftover `db/etcd` stub existed, and the migration needed downtime. This is the strongest *contextual* counter: the real risk on SQLite is datastore bloat and a brittle conversion, not the lack of `etcd-snapshot`. It also shows that a file-copy backup of a bloated WAL is large and slow. No k3s version is stated.
4. **k3s-io/k3s Discussion #9432**, "Embedded SQLite migration to ETCD Cluster": https://github.com/k3s-io/k3s/discussions/9432 (found by search, `SECONDARY`, not quoted). Maintainers say restarting with `--cluster-init` is the only supported direct SQLite-to-etcd path.

## Required edits to the claim

- Reword it to: "`k3s etcd-snapshot` is unavailable on the default SQLite datastore… SQLite clusters are backed up by copying `server/db/` and the token (docs.k3s.io/datastore/backup-restore)."
- Quote the CLI error exactly: `Error: see server log for details: etcd datastore disabled`.
- Fix the first permalink to `#L72-L76`.
- **Hygiene flag (rule 5):** `a1.log` contains an RFC1918 node InternalIP (the Lima default user-mode network address) in its `kubectl get nodes -o wide` output. Redact it before this log is committed to the public repo.

## What would flip the verdict

- **To refuted:** a run of `k3s etcd-snapshot save` on v1.37.2+k3s1 with SQLite (no `--cluster-init`, no `--datastore-endpoint`) that exits 0 and writes a snapshot. Or a k3s change at or before f6973cb8 that registers a kine-backed snapshot handler when `managedDB == nil`.
- **To weakened:** the downstream decision cites this claim as evidence that SQLite k3s "cannot be backed up", without the file-copy path. Or a supported k3s release adds kine snapshotting (look for removal of `handlerNoEtcd` in `pkg/cluster/managed.go`), which would make the claim release-specific. Re-check by 2027-05-10.
