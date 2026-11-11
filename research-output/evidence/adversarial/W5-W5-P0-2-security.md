# Adversarial review: W5-P0-2 (single-box k3s SQLite backup path), security lens

- Refuter: independent, security lens. Date: 2026-11-10.
- Claim under test: a single-box k3s SQLite datastore has a supported backup path, which is to copy `/var/lib/rancher/k3s/server/db` plus the server token. Because kine opens SQLite in WAL mode, the copy must use SQLite's online backup API, or k3s must be stopped. In the lab, an online `sqlite3 .backup` plus the token, the node password and a restic snapshot of the local-path volumes was restored onto a second, freshly installed VM and recovered a ConfigMap, an encrypted Secret and the PVC data.
- **Verdict: WEAKENED.** The mechanics hold, and I could not refute them:
  - kine's default DSN is `_journal_mode=WAL`.
  - The docs name the directory and the token.
  - The lab restore recovered all three objects.

  As a backup *design*, though, the claim is unsafe as written. It treats the backup set as an availability artifact. It is in fact a credential bundle equal to cluster-admin plus every Secret plus the cluster CA private keys. The lab recipe stores that bundle unencrypted next to the one key that unlocks it. The claim needs security requirements attached before it is frozen.

## 1. Strongest counter-argument

1. **`state.db` plus the token decrypts everything, including the Secret encryption key and the CA keys.**
   - k3s stores its bootstrap data (cluster CA and service-account private keys, plus the secrets-encryption config) inside the datastore. It encrypts that data with AES-GCM under a PBKDF2 key derived from the server token (GHSA-cxm9-4m6p-24mc; docs.k3s.io/cli/token: "The server token is also used as the PBKDF2 passphrase to encrypt confidential information").
   - The lab proves this end to end. The restore step (`scripts/drill.sh` b1) copied only `state.db`, `token` and `node-password`, and never `server/cred/encryption-config.json`. The Secret still decoded to its original value (`b1.log`: "secret value: s3cret-…"). The aescbc key therefore came out of `state.db` through the token.
   - "Secrets encrypted at rest" thus protects nothing in a backup that carries its token alongside. The docs themselves say: "Anyone with access to the server token essentially has full administrator access to the cluster."
2. **The lab recipe co-locates the ciphertext with its keys, unencrypted.**
   - `shared/bk-sqlite/` holds `state.db` (mode 0644, world-readable), `token` (0600) and `node-password` (0600) in one directory.
   - restic covers only `/var/lib/rancher/k3s/storage`, so neither the datastore nor the token is inside restic's encryption.
   - `restic-pass` is 0644 and sits next to `restic-repo`.
   - `plaintext-check.log` shows ConfigMaps in `state.db` in cleartext (`cm-plaintext=1`). Every non-Secret object (ConfigMaps, env-in-manifests, Helm release metadata) is readable with no key at all.
   - Anyone who reads that one directory, for example on a NAS share or a synced cloud folder, owns the cluster and every Secret ever stored in it.
3. **The KDF is weak, and the first server can only take a password-style token.**
   - Current k3s `main` (`pkg/cluster/encrypt.go` L31/L60, commit 51d3b704) derives the key with `pbkdf2.Key(passphrase, salt, 4096, 32, sha1.New)`. That is 4,096 iterations of SHA-1, cheap to brute-force offline.
   - The docs say "only the short (password-only) token format can be used when starting the first server in the cluster."
   - If OneMind ever lets a user or installer pick a human-memorable token, a leaked `state.db` alone, without the token, is offline-crackable.
   - The safe case is k3s's random token, and only if OneMind never overrides it.
4. **Rotation does not revoke old backups.**
   - docs.k3s.io/cli/token: "Snapshots taken before the rotation will require the old server token when restoring the cluster." The old backup and old token pair stays a working key ring.
   - Restoring also restores the CA private keys. Anyone who ever held an old backup can mint client certificates that the restored cluster still trusts, until the CA is rotated.
   - The same holds for the aescbc key unless `secrets-encrypt rotate-keys` is run *and* the old backups are destroyed. The claim offers no retention or destruction rule.
5. **The token is the single point of both failure and compromise.**
   - In CVE-2021-32001 (GHSA-cxm9-4m6p-24mc), k3s encrypted bootstrap data with an *empty-string* key when no token was supplied, for external SQL and etcd datastores.
   - Standalone SQLite was not affected. The advisory still shows that the confidentiality of this exact blob has already failed once, silently, through a defaulting bug. A backup design whose only confidentiality control is that blob's encryption inherits that fragility.
6. **The "supported" path, as documented, is the unsafe one.**
   - The cited k3s page says only "take a copy of `/var/lib/rancher/k3s/server/db/`" and "No special commands are required". It says nothing about stopping k3s, WAL or `-shm` files, or protecting the copy.
   - SQLite's own guidance says a copy taken during a transaction "might contain some old and some new content, and thus be corrupt", and mispairing a database with its `-wal` file causes corruption (sqlite.org/howtocorrupt.html §1.2, §1.4).
   - k3s issue #9787 shows `state.db` reaching "database disk image is malformed". The maintainer's answer is "There is nothing that can be done within K3s to prevent this", followed by a manual `.recover`. One user had to delete `state.db-shm` and `state.db-wal` to escape a restart loop.
   - The claim's correction (use the backup API) is right. It is OneMind's requirement, though, not "the supported path". The upstream docs, as written, lead to integrity failures, and an integrity failure in a security-relevant store (RBAC, admission config) is itself a security event.
7. **The evidence is thinner than "recovered the PVC data" suggests.**
   - In `b1.log` the PVC check failed on the first run: "error: unable to upgrade connection: container not found ("w")", with an empty marker.
   - Only `b2-reverify.log`, about 10 minutes later after one pod restart (RESTARTS 1), shows the marker matching. That is a pass, but it is a pass after retry, not the clean one-shot restore the claim implies.
   - It was also one run, on one architecture (arm64 VM), with one tiny dataset, and no hostile conditions: no restore under a changed hostname, and no tamper test.
   - **Integrity is unauthenticated.** Nothing in the recipe signs or MACs `state.db`. Whoever can write to the backup location can plant RBAC bindings or webhooks that the restored cluster trusts. The `PRAGMA integrity_check` the lab ran detects corruption, not tampering.

## 2. What survives (fairness)

- kine pins `_journal_mode=WAL&…&_synchronous=NORMAL` (cited `sqlite.go`), so the online-backup-API requirement is correct.
- `etcd-snapshot` does not apply to SQLite, so a file-level path is the only native one for this datastore.
- The restore genuinely needed the token. Secrets were encrypted at rest in `state.db` (`secret-plaintext=0`, `k8s-enc-prefix=8`), so a `state.db` leak *without* the token (and with a random token) does not expose Secret values.
- None of my findings show the path to be broken or abandoned. They show it to be under-specified for security.

## 3. Required conditions for the claim to stand (security)

1. Put `state.db` inside an encrypted, authenticated backup (restic or age), not beside it. Store the server token, and the restic password, *separately*: offline, in a hardware key or the operator's password manager. Never put them in the same repository or share.
2. Use only k3s-generated random tokens. Forbid user-chosen short tokens (4,096-iteration PBKDF2-SHA1).
3. Set a retention and destruction policy. After token rotation, `secrets-encrypt rotate-keys` or a CA rotation, destroy older backup and token pairs. Document that a leaked backup means a full CA rotation.
4. Make the online `.backup` (or `VACUUM INTO`) plus `PRAGMA integrity_check` a requirement in OneMind's own tooling. Do not cite the bare upstream "copy the directory" as sufficient.
5. Before restore, verify a signature or MAC over the backup set, so that a writable backup target cannot inject RBAC or webhooks.

## 4. What would flip the decision

- **To UPHELD:**
  - A repeat lab run with the backup set (`state.db`, token, node password, PVC data) under conditions 1, 2 and 5. That means restic or age encryption, the token held out of band, and a verified signature before restore.
  - A clean one-shot PVC verify, with no retry.
  - A file-permission and leak check of the backup target.
- **To REFUTED:** any of these:
  - A k3s advisory or bug showing bootstrap data in standalone SQLite readable without the token.
  - The PBKDF2 key being recoverable from a k3s-generated random token.
  - A k3s release that stops storing the aescbc key in bootstrap data. That would mean `state.db` plus the token no longer recovers Secrets, which breaks the claimed recipe.
  - A reproducible case where `sqlite3 .backup` of a live kine database restores as corrupt or inconsistent, for example a torn compaction.

## 5. Sources

Cited by the claim and re-opened:
- k3s docs backup-restore.md @8958508 L7-18. Says "take a copy of `/var/lib/rancher/k3s/server/db/`" and nothing about WAL, stopping k3s or protecting the copy.
- kine `pkg/drivers/sqlite/sqlite.go` @35f4319. `DefaultParams = "_journal_mode=WAL&_busy_timeout=30000&_synchronous=NORMAL&…"`.
- Lab: `work/.lab/w5-restore/logs/b1.log`, `logs/b2-reverify.log`, `logs/plaintext-check.log`, `scripts/drill.sh` (a1/b1 cases), and the `shared/bk-sqlite/` file modes.

New, found by searching for failures, CVEs and corruption:
- GHSA-cxm9-4m6p-24mc / CVE-2021-32001, "K3S bootstrap data is encrypted with empty string if user does not supply a token": https://github.com/k3s-io/k3s/security/advisories/GHSA-cxm9-4m6p-24mc
- k3s token docs (rotation does not cover old snapshots, the short-token-only first server, and token = admin): https://docs.k3s.io/cli/token
- k3s issue #9787, "database disk image is malformed" (state.db corruption, `-wal`/`-shm` deletion, maintainer says k3s cannot prevent it): https://github.com/k3s-io/k3s/issues/9787
- SQLite, "How To Corrupt An SQLite Database File" §1.2 and §1.4: https://www.sqlite.org/howtocorrupt.html
- k3s `pkg/cluster/encrypt.go` (PBKDF2, 4096 iterations, SHA-1), main @51d3b7043183cbd61381773e6345082bd4cf2280: https://github.com/k3s-io/k3s/blob/51d3b7043183cbd61381773e6345082bd4cf2280/pkg/cluster/encrypt.go#L31
- k3s secrets-encryption docs (the key lives in `server/cred/encryption-config.json` on disk; the docs are silent on backups): https://docs.k3s.io/security/secrets-encryption
