# Refuter report: W5-P0-1 (security lens)

- **Claim:** On k3s v1.37.2+k3s1 with the default single-server SQLite datastore, `k3s etcd-snapshot` cannot back up the cluster. With no managed etcd driver, k3s answers its `/db/` snapshot routes with "etcd datastore disabled", and `k3s etcd-snapshot save` exits 1 with that error.
- **Refuter lens:** security. I saw only the claim and its cited sources, not the author's reasoning.
- **Date:** 2026-11-10
- **Verdict:** **upheld.** The narrow mechanical claim is correct. Two security caveats below must travel with it (the scope of the claim and key custody); they do not weaken it.

## 1. What I checked independently

| Check | Result |
|---|---|
| Tag `v1.37.2+k3s1` resolves to the cited commit | `gh api repos/k3s-io/k3s/commits/v1.37.2%2Bk3s1` returns `f6973cb850e9b245585363d15bde80904ac862fd`. The release was published 2026-11-03T17:32:38Z. The lab binary reports `k3s version v1.37.2+k3s1 (f6973cb8)`. |
| Cited lines L70-L75 | At that commit, `registerDBHandlers` returns `handlerNoEtcd(handler)` when `c.managedDB == nil`. |
| Cited lines L145-L157 | `handlerNoEtcd` registers `/db/` and replies `util.SendError(errors.New("etcd datastore disabled"), ..., http.StatusBadRequest)`. Every other path falls through to the normal handler. |
| CLI path actually hits that route | `pkg/cli/etcdsnapshot/etcd_snapshot.go` sends save, delete, list and prune as `info.Post("/db/snapshot", ...)` (lines 132, 173, 228, 291). It wraps server errors with `"see server log for details"` (line 100). The router is k3s's own `pkg/util/mux`, not gorilla. I did not test whether `/db/` is a prefix match in that router. The lab output shows it is. |
| Lab log integrity | `shasum -a 256 work/.lab/w5-restore/logs/a1.log` = `6dbc95cb...e8b1cd`, matching the citation. |
| Lab result | `level=fatal msg="Error: see server log for details: etcd datastore disabled"`, then `H1 exit=1`. Only `state.db`, `state.db-shm` and `state.db-wal` exist in `server/db/`, which confirms SQLite through kine. |
| Third-party reproduction | A separate k3s lab lesson shows the same error from `k3s etcd-snapshot save` on a default single server, and attributes it to SQLite through kine (see sources). |

## 2. Strongest counter-argument

The claim is precise, but a reader could take it as "a default k3s box cannot be backed up". That would be a wrong and dangerous conclusion. These three points are the best case against using it as a decision input in that form:

1. **SQLite has an official backup path; it just isn't `etcd-snapshot`.** The k3s docs say: "No special commands are required to back up or restore the SQLite datastore". You copy `/var/lib/rancher/k3s/server/db/` plus the server token. The lab did exactly this. `drill.sh` runs an online `sqlite3 .backup` and gets `integrity_check: ok`, then restores in `b1`. So the right conclusion is "`etcd-snapshot` is unavailable", not "the cluster can't be backed up". The claim's own subject is `k3s etcd-snapshot`, so it is literally correct. Downstream documents must keep that subject.
2. **The limitation can be lifted in place.** The k3s docs say that a cluster on the default embedded SQLite database "can convert it to etcd" by "simply restarting your K3s server with the `--cluster-init` flag". The lab's `b2` step tests this ("Migrating content from sqlite"). After conversion, `etcd-snapshot` works, with scheduled snapshots at 00:00 and 12:00 and optional S3 upload. So "default SQLite → no snapshots" is a default, not a constraint, for any OneMind design.
3. **Security risk in the file-copy fallback (the real security finding).** The docs say the token "is used to encrypt confidential data within the datastore itself". In the lab, `drill.sh` copies `state.db`, `token` and `node-password` in plaintext into `shared/bk-sqlite/`, outside the restic repository. Only `/var/lib/rancher/k3s/storage` goes into restic; that is why restic shows `processed 1 files, 33 B`, which is by design, not data loss. `plaintext-check.log` shows `secret-plaintext=0` for `bk-sqlite/state.db`, so Secrets are encrypted at rest. But a plaintext token stored next to the datastore copy hands anyone who reads that directory the decryption key for the confidential bootstrap data, and therefore the cluster. Any OneMind backup design built on the SQLite fallback must encrypt the token and the datastore together (restic or age) and keep the token in a separate key-custody path. This does not refute the claim, but it must be attached to any recommendation that uses the fallback.

### Failure and longevity evidence (new sources, all opened)

These show that SQLite-on-k3s is a real operational risk. That supports, not undermines, the claim's implied recommendation: do not rely on SQLite plus `etcd-snapshot`.

- k3s issue #12898 (closed 2025-09-11): when kine compaction fails, `state.db` "will grow without bound" (maintainer brandond). The reporter saw single-node databases from 20 MB to 12 GB. No fix version is named; the advice was to upgrade the patch release.
- A k3s crash postmortem (mnguyen.fr, 2024-12-18): a SQLite `state.db` on a Pi became "database disk image is malformed". `.recover` and `.dump` both failed, and only a restore from backup worked. The author's lesson was "Better backup and restore logical backups than SQLite files". That is evidence that raw file copies need integrity checks. The lab's `sqlite3 .backup` plus `PRAGMA integrity_check` already does this.
- Search also found a homelab incident (doemefu/homelab #129): kine SQLite compaction stalled for 5 days and produced a 5 GB `state.db` with API timeouts. I saw this only as a search result and did not open it, so it is not counted as evidence.

None of these sources shows `etcd-snapshot` working on SQLite, or any CVE, deprecation or regression that changes the cited code path.

## 3. Verdict: upheld

- The source at the exact tagged commit, the hash-verified lab log and an independent third-party lab all agree on the error string and the exit status.
- Required wording guard: "`k3s etcd-snapshot` is unavailable on the default SQLite datastore. Back up SQLite with `sqlite3 .backup` (or a copy taken with k3s stopped) of `server/db/` plus the token, or convert to embedded etcd with `--cluster-init`." Never write "the cluster cannot be backed up".
- Required security note for W5 and W6: the token is key material. It must never be stored in plaintext next to the datastore copy. The lab's `shared/bk-sqlite/` layout is acceptable for a throwaway drill only.

## 4. What evidence would flip this

- **Refute:** a run of `k3s etcd-snapshot save` on v1.37.x with the SQLite datastore that exits 0 and writes a snapshot. Or a k3s commit or release note after `f6973cb8` adding a kine/SQLite snapshot driver, so that `managedDB` is no longer nil for SQLite. Or proof that `/db/` in `pkg/util/mux` is not a prefix match and the error comes from somewhere else (that would only change the mechanism, not the outcome).
- **Weaken:** k3s docs or source showing that the `--cluster-init` conversion is unsupported or lossy on the versions OneMind ships, which would make SQLite the only option on a box. Or a k3s release that changes the default datastore to embedded etcd, which would make the claim moot for new installs.
- **Make the security caveat a blocker:** evidence that a `state.db` copy without the token still exposes Secrets in plaintext with `secrets-encryption: true`. The lab's `plaintext-check.log` currently says it does not (`secret-plaintext=0`).

## Sources

Cited by the claim (re-verified):
- https://github.com/k3s-io/k3s/blob/f6973cb850e9b245585363d15bde80904ac862fd/pkg/cluster/managed.go#L70-L75
- https://github.com/k3s-io/k3s/blob/f6973cb850e9b245585363d15bde80904ac862fd/pkg/cluster/managed.go#L145-L157
- `work/.lab/w5-restore/logs/a1.log` (sha256 `6dbc95cbc331304d57ff13ea2e46a5a0ef4fd7f65eacc9689aa07a33c9e8b1cd`, verified), plus `work/.lab/w5-restore/scripts/drill.sh` and `logs/plaintext-check.log`

New:
- https://github.com/k3s-io/k3s/blob/f6973cb850e9b245585363d15bde80904ac862fd/pkg/cli/etcdsnapshot/etcd_snapshot.go (CLI posts to `/db/snapshot`)
- https://docs.k3s.io/datastore/backup-restore (SQLite backup by file copy; the token encrypts confidential datastore data)
- https://docs.k3s.io/datastore/ha-embedded (SQLite to etcd conversion with `--cluster-init`)
- https://github.com/k3s-io/k3s/issues/12898 (failure: compaction failure leads to unbounded `state.db` growth)
- https://mnguyen.fr/blog/2024-12-18-k3s-crash-postmortem (failure: corrupted SQLite datastore, recovered only from backup)
- https://labhub.hopto.org/lesson/k8s-distros/r-distro-k3s-datastore?lang=en (third-party reproduction of the same error; seen through search results only)

Re-check by: 2027-05-10 (Kubernetes/k3s fact, 6 months).
