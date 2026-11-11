# 06 · Backups, recovery and data (W5)

**Workstream:** W5 (Tier A, P0) · **Date:** 2026-11-10 · **Owner of:** DC-11 (Q129, Q136), plus Q156, Q281 (backup format part), Q300
**Claims:** `evidence/claims/W5.csv` (C-W5-001 … 058) · **Sources:** `evidence/sources/W5.md` · **Question statuses:** `evidence/qbank/W5.md`
**Scorecard:** frozen weights v1.0 (`evidence/scorecard-weights.md`), decision **S4. Backup and restore**
**Serves requirements:** R-1, R-2, R-3, M-2, M-4, M-6, U-1, U-4, UX-6, AI-4, P-5, P-7, F-11, F-14, H-1, D-001
**ADR-001 D5 verdict:** **confirmed with changes** (restic stays; the k3s datastore line is wrong for a single box and is replaced; see §2 and §11)

> ### Explain it like I'm the founder
> A backup is only worth something if you can **restore it onto a different machine, with a key you still have**. Everything in this file is built around that one test.
>
> ADR-001 said: "back up the k3s datastore with `k3s etcd-snapshot`, and app data with restic". We tested that in two throw-away virtual machines. Result:
> 1. **`k3s etcd-snapshot` does not work on a single OneMind box.** A single box uses SQLite (a one-file database), not etcd, and the command fails with "etcd datastore disabled" [C-W5-001, C-W5-002]. This is not a dead end: SQLite is backed up by copying its file safely plus one secret file (the "token") [C-W5-003, C-W5-004]. We did exactly that, wiped nothing on the old box, built a brand-new VM, restored, and the app came back with its data [C-W5-009].
> 2. **A single box can grow into a cluster without reinstalling.** One restart with `--cluster-init` moved all 409 records from SQLite into etcd in our test [C-W5-005, C-W5-006]. So we keep SQLite for small boxes (it wrote about 8× less to disk while idle in our test [C-W5-018]) and switch to etcd only when a household adds servers.
> 3. **restic is the right engine** for app data. It beats Kopia (Umbrel's choice) on every criterion we score, mainly because one restic repository can have **several keys**, so we can give the owner a printed **recovery key** in addition to the box's own key [C-W5-023, C-W5-028].
> 4. **Kubernetes' own snapshots are not encrypted.** Anyone who gets a copy can read most of the box's configuration [C-W5-013, C-W5-014]. So OneMind always wraps them inside an encrypted restic backup.
> 5. Two traps we found that nobody documents together: after a restore, Kubernetes briefly *says* everything is healthy because it is reading the old saved status [C-W5-010]; and the default storage class **deletes app data when an app's volume claim is deleted** [C-W5-019]. Both have simple fixes (§6, §7).
>
> What competitors do: Home Assistant encrypts everything and hands you an "emergency kit" with the key; Umbrel backs up the whole box every hour with Kopia; Olares uses restic but can only restore one app. **Nobody automatically proves a backup can be restored.** Your own cloud cluster already does this for its databases [C-W5-056]. That is the feature OneMind should lead with: a dashboard line saying **"last verified restore: 3 hours ago".**

---

## Contents
1. [Glossary](#1-glossary)
2. [DC-11: the k3s datastore on a single box (full method)](#2-dc-11-the-k3s-datastore-on-a-single-box-full-method)
3. [What must be backed up: the OneMind backup set](#3-what-must-be-backed-up-the-onemind-backup-set)
4. [Engine choice: scorecard S4](#4-engine-choice-scorecard-s4)
5. [What competitors do](#5-what-competitors-do)
6. [Encryption, keys and key recovery](#6-encryption-keys-and-key-recovery)
7. [App-consistent backups and the app manifest](#7-app-consistent-backups-and-the-app-manifest)
8. [3-2-1, destinations, box-to-box and mirroring (UX-6)](#8-3-2-1-destinations-box-to-box-and-mirroring-ux-6)
9. [Restore paths, drills and automatic verification](#9-restore-paths-drills-and-automatic-verification)
10. [RPO/RTO targets per edition](#10-rporto-targets-per-edition)
11. [Recommendations with requirement IDs](#11-recommendations-with-requirement-ids)
12. [Lab spike: k3s + restic restore onto a fresh VM](#12-lab-spike-k3s--restic-restore-onto-a-fresh-vm)
13. [Failure reports and what they teach](#13-failure-reports-and-what-they-teach)
14. [Founder-runnable tests (for 22-…)](#14-founder-runnable-tests-for-22-)
15. [Corrections to earlier files, open items](#15-corrections-to-earlier-files-open-items)

---

## 1. Glossary

| Term | Meaning |
|---|---|
| **Backup** | A separate, independent copy you can restore from. A RAID mirror or ZFS "FailSafe" is *availability*, not a backup (Umbrel says the same). |
| **Restore drill** | Actually restoring a backup somewhere clean and checking the data, to prove it works. |
| **RPO** (recovery point objective) | How much recent data you can afford to lose. RPO 1 h = at most the last hour. |
| **RTO** (recovery time objective) | How long it may take to be running again. |
| **3-2-1** | 3 copies of data, on 2 different kinds of storage, 1 off-site. |
| **k3s datastore** | Where Kubernetes keeps its state (apps, settings, secrets). **SQLite** (one file) on a single server; **etcd** (a replicated database) on multi-server clusters. |
| **kine** | The small adapter inside k3s that lets Kubernetes use SQLite as if it were etcd. |
| **Token** | k3s's server secret (`/var/lib/rancher/k3s/server/token`). It encrypts the sensitive parts of the datastore; a backup without it is unusable [C-W5-004]. |
| **WAL** | SQLite's write-ahead log. With WAL on, the database is spread over several files, so copying one file while it runs is not safe [C-W5-007]. |
| **restic / Kopia / borg** | Open-source, encrypting, de-duplicating backup programs. They split files into chunks and store each chunk once. |
| **Velero** | A Kubernetes backup tool that saves cluster objects plus volume data (using Kopia underneath). |
| **Append-only** | A backup target that accepts new data but refuses deletions, so ransomware on the source box can't wipe the backups [C-W5-024]. |
| **Crash-consistent vs app-consistent** | Crash-consistent = a copy like after a power cut; most databases survive it. App-consistent = the app was told to flush or dump first, so the copy is clean. |
| **Emergency kit / recovery key** | A file or printout with the key needed to decrypt backups. Lose it and the backups are noise [C-W5-051]. |
| **local-path** | k3s's default storage: each app volume is a folder on the box's disk [C-W5-019]. |
| **GFS retention** | Grandfather-father-son: keep hourly, then daily, weekly, monthly copies. |

---

## 2. DC-11: the k3s datastore on a single box (full method)

**Question (Q129, primary of DC-11):** what does `k3s etcd-snapshot` cover on a single-node SQLite box, what is the supported backup/restore path, and should a single box use embedded etcd instead?
**Flip condition (frozen in `decision-critical.md`):** *no supported SQLite backup/restore, and no in-place migration to etcd, so the single-box default must change.*

### 2.1 Evidence

| # | Finding | Evidence type | Claim |
|---|---|---|---|
| 1 | On SQLite there is no managed DB driver; k3s answers every `/db/` call (what `etcd-snapshot` uses) with "etcd datastore disabled". | Code, k3s v1.37.2+k3s1 `pkg/cluster/managed.go` L70–75, L145–157 | C-W5-001 |
| 2 | `k3s etcd-snapshot save` on a SQLite box exits 1, "etcd datastore disabled". | Lab | C-W5-002 |
| 3 | The supported SQLite path: copy `server/db/` and restore it with the token; "no special commands". | k3s docs | C-W5-003, C-W5-004 |
| 4 | kine opens SQLite in WAL mode, so a plain file copy of `state.db` while k3s runs is not consistent. Use SQLite's online backup API (`sqlite3 .backup`) or stop k3s. | Code, kine v0.17.1 (the version k3s pins) | C-W5-007 |
| 5 | An online `.backup` + token + node password + restic of the volumes restored onto a **second, freshly installed VM**; ConfigMap, encrypted Secret and volume data all verified. | Lab | C-W5-009 |
| 6 | In-place SQLite → etcd conversion with `--cluster-init`: code copies every `/registry/` key and renames `state.db` to `state.db.migrated`. Lab: 409 keys, ~15 s, all objects intact. | Code + docs + lab | C-W5-005, C-W5-006 |
| 7 | After conversion, `etcd-snapshot` works, and a snapshot plus token restores onto a wiped VM. | Lab | C-W5-017 |
| 8 | kine has a "litestream" mode built for continuous SQLite replication (Litestream is Apache-2.0). | Code | C-W5-008, C-W5-035 |
| 9 | Idle writes in 10 min (VM, indicative only): SQLite ~19 MiB, etcd ~166 MiB; etcd data dir 142 MiB vs 13 MiB. | Lab | C-W5-018 |
| 10 | k3s rollback to an older minor needs a datastore copy from that minor; for SQLite it's "replace the .db file". | k3s docs | C-W5-016 |

### 2.2 Verdict

**The flip condition is not met.** SQLite has a documented backup/restore path that we reproduced across machines, and an in-place migration to etcd exists and works. **Keep SQLite as the single-box default.** What changes is ADR-001 D5's wording: `etcd-snapshot` is not the single-box mechanism.

**New single-box datastore procedure** (implemented by the OneMind backup agent, not by the user):
1. `sqlite3 state.db ".backup <staging>/state.db"` while k3s runs, then `PRAGMA integrity_check` on the copy (we got "ok") [C-W5-009]. This mirrors what Umbrel does for its own database: a standalone SQLite snapshot checked with `quick_check`, with the live DB and WAL files excluded [C-W5-043].
2. Copy the token, `/etc/rancher/node/password`, and (if enabled) the secrets-encryption config [C-W5-004, C-W5-012].
3. Put all of it inside the same restic snapshot as the app volumes, so one restic snapshot = one consistent restore point.
4. On clusters (3+ servers, etcd): use `k3s etcd-snapshot save` instead, then restic-wrap the snapshot file, because k3s snapshots are **not encrypted** [C-W5-013, C-W5-014].

### 2.3 Adversarial table (refuter lenses)

> **Method note.** This run had no tool for spawning independent sub-agents, so the passes below were run in-agent, each told only the claim and its sources and asked to disprove it. They are **not independent**. The P0 claims are returned to the orchestrator as standalone statements for independent refuters (brief §2 rule 7). Failure-seeking sources found for this table: C-W5-010, C-W5-018, C-W5-026, C-W5-047, C-W5-052.

| Lens | Strongest counter-argument | New sources sought for failure | Verdict | Response |
|---|---|---|---|---|
| Technical | "Copying SQLite with `.backup` while kine writes can still miss k3s state, and a restored box says it's healthy when it isn't." | Lab C-W5-010 (stale Ready/Running after restore) | **weakened** | True for status, not data: the restored Node/Pod status is stale until the kubelet re-syncs. Fix: the restore health gate checks fresh evidence (a new Lease/heartbeat time, `kubectl exec` or an app probe), never the restored `.status`. Data integrity held in all four phases. |
| Longevity / vendor | "SQLite on k3s is the 'CI/short-lived' option; k3s may drop or neglect it." | k3s docs datastore page lists SQLite for simple/short-lived clusters (S2 `datastore.md` L9); TrueNAS `database disk image is malformed` report C-W5-052 | **weakened** | SQLite remains the k3s default when nothing else is configured (S2 L16), and kine v0.17 added a dedicated Litestream mode in 2026 [C-W5-008], which is investment, not neglect. The corruption report is why we keep hourly verified copies; the exit is the in-place etcd migration [C-W5-005]. |
| Security | "The datastore backup leaks secrets and CA keys." | k3s security note C-W5-013; lab C-W5-014 | **upheld (with condition)** | Correct for raw copies, so raw copies never leave the box unencrypted: everything goes into restic [C-W5-023], and k3s runs with `--secrets-encryption` so Secret values are not plaintext even inside the copy [C-W5-014]. The token sits in the same encrypted snapshot; anyone holding the restic key can rebuild the cluster, which is the intended owner property (M-2). |
| Cost / flash wear | "etcd from day one avoids a migration later." | Lab C-W5-018; k3s docs on etcd and SD cards (C-W4-002) | **upheld** | etcd wrote ~8.7× more while idle in our VM and k3s itself warns SD/eMMC can't handle etcd [C-W5-018]; the migration is one restart [C-W5-006]. Default stays SQLite. |
| Robotics fit | "A robot needs the datastore restore to be instant and offline." | — | **upheld** | Both restores in the lab were API-ready in 6–13 s on tiny data [C-W5-054]; robots should not own cluster authority anyway (they are agents or NATS leaves, per W4), so robot restore = config + maps + logs (§10). |

### 2.4 Steelman of the runner-up: "embedded etcd on every box from day one"

*Argued for, by design:* one datastore everywhere means one backup command (`etcd-snapshot`) with built-in schedule, retention and S3 upload [C-W5-011], one restore command, no migration step, and every box is already "HA-ready" so a second and third server can join at any time. The founder's cloud cluster already uses etcd. A restore tool that only has to understand one format is simpler to test, which matters for a solo developer (M-6).

*Response:* the convenience is real, but (a) `etcd-snapshot`'s built-in features don't remove the need for restic, because snapshots are unencrypted and must be wrapped anyway [C-W5-013]; (b) the single-box SQLite path is three commands that the backup agent runs, not the user; (c) etcd's write volume is the wrong default for SD/eMMC Lite boxes [C-W5-018]; (d) a two-server household gains nothing from etcd (no quorum), and the third server can trigger the one-restart migration [C-W5-005]. **What would flip it:** a 72-hour founder-hardware measurement (T-W5-03) showing etcd's write rate on Pi 5 NVMe below ~2× SQLite, or a k3s announcement deprecating SQLite.

---

## 3. What must be backed up: the OneMind backup set

Back up **data and declarations, not images**. Container images and the OS image are re-downloaded (multi-arch) on restore. This is why Home Assistant can restore a Pi backup onto a different device type [C-W5-039].

| Layer | What | How | In ADR-001 D5? |
|---|---|---|---|
| L0 OS image | Read-only A/B slots | **Not backed up.** Reflash or reinstall; the image is reproducible. | Yes (implied) |
| L1 Cluster state | SQLite `state.db` via online backup (single box) or `etcd-snapshot` (cluster); token; node password; secrets-encryption config | §2.2 | **Changed** (SQLite path added) |
| L2 OneMind identity and config | Users/roles, device enrolments, app install list with versions and settings (the Market state), certificates, NATS config | Exported as files into the restic snapshot **and** reproducible from the app list | Yes ("recovery kit") |
| L3 App volumes | local-path folders under `/var/lib/rancher/k3s/storage`, Longhorn volumes on clusters | restic, with app hooks (§7) | Yes |
| L4 App databases | Postgres/MariaDB/SQLite inside apps | Dump or online-backup hooks declared in the app manifest (§7), then restic | **Added** |
| L5 User files and media | Files, photos, documents | restic; large media may get their own schedule | Yes |
| L6 Keys | restic keys, emergency kit | **Never inside the backup alone**: printed/exported recovery key held by the owner (§6) | Yes (recovery kit) |
| Excluded | Image layers, caches, thumbnails, the backup tool's own cache, logs | Ignore list, like Umbrel's (Kopia cache, thumbnails, live DB/WAL) [C-W5-043] | Added |

**Restore-relevant facts to design around:**
- k3s's local-path PVs are `local` volumes **pinned by nodeAffinity to the node name**, and the storage class's reclaim policy is **Delete** [C-W5-019]. So (a) an exact-box restore must keep the node name (the lab used a fixed `node-name`), and (b) deleting a PVC deletes the folder. OneMind should ship its own storage class with `Retain` for app data and delete only through an explicit "remove app data" step that first takes a backup. This matches the founder's own cluster rule of retain-class storage for stateful claims.
- Velero's File System Backup does support `local` volumes but only while a pod mounts them, is "beta quality", and by default uses one hard-coded repository password [C-W5-020, C-W5-021]. That is why Velero is not in the single-box path.

---

## 4. Engine choice: scorecard S4

**Candidates** (from the frozen list): restic · Kopia · borg · Velero (+Kopia uploader) · Longhorn backup · ZFS send/recv. *k3s datastore snapshots* are not an alternative engine; they are covered as layer L1 above (§2), so they are not ranked here.
**Interpretation (per the scorecard's note for S2–S5):** C1 = the project's own release/format stability, maintainers and licence-forkability; C2 = runs on x86, Pi 5 and Jetson (arm64) from one binary, at single-box and cluster scale; C3 = encryption, authentication, key management and tamper resistance; C4 = shipping products using it, confirmed in code.

| Candidate | G1 | G2 | G3 | G4 | G5 | C1 (20) | C2 (20) | C3 (15) | C4 (15) | C5 (10) | C6 (10) | C7 (10) | Total | Rank |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **restic** | PASS BSD-2 [C-W5-023] | PASS arm64 lab, x86 releases [C-W5-009, C-W5-025] | PASS documented repo format, forkable [C-W5-023] | PASS n/a | PASS single binary on box; k8up/VolSync at cluster [C-W5-033, C-W5-034] | 3 [C-W5-023, C-W5-025] | 4 lab arm64 [C-W5-009] | 4 multi-key, AEAD-style auth, append-only [C-W5-023, C-W5-024] | 3 Olares, k8up, VolSync [C-W5-050, C-W5-033, C-W5-034] | 4 [C-W5-009] | 5 [C-W5-058] | 4 [C-W5-033, C-W5-034, C-W5-024] | **75** | **1** |
| Kopia | PASS Apache-2.0 [C-W5-027] | PASS amd64+arm64 pinned by Umbrel [C-W5-046] | PASS [C-W5-027] | PASS | PASS Velero uploader at cluster [C-W5-022] | 3 [C-W5-030] | 3 doc-only [C-W5-046] | 3 one password per repo [C-W5-028] | 3 Umbrel (constraint match) [C-W5-041] | 4 [C-W5-041] | 5 [C-W5-058] | 3 [C-W5-022] | 66 | 2 |
| borg | PASS BSD-3 [C-W5-030] | CONDITIONAL doc-only [C-W5-030] | CONDITIONAL borg 2 needs repo re-creation [C-W5-030] | PASS | CONDITIONAL no operator found | 2 [C-W5-030] | 3 [C-W5-030] | 3 [C-W5-030] | 0 unverified | 3 SSH remote [C-W5-030] | 5 [C-W5-030] | 2 | 49 | 3 (tie) |
| Velero (+Kopia) | PASS [C-W5-058] | PASS | PASS | PASS | CONDITIONAL needs k8s + object store, pod-mounted volumes [C-W5-020] | 3 | 2 [C-W5-020] | 1 static default key [C-W5-021] | 2 Olares installs it; founder cluster [C-W5-056] | 2 | 5 [C-W5-058] | 3 [C-W5-057] | 49 | 3 (tie) |
| ZFS send/recv | **FAIL→CONDITIONAL** CDDL kernel module [C-W5-058] | CONDITIONAL DKMS per kernel | PASS | PASS | CONDITIONAL | 3 | 2 | 3 raw send to untrusted box [C-W5-032] | 1 | 2 | 2 [C-W5-058] | 3 | 46 | not ranked (G1 needs legal review) |
| Longhorn backup | PASS [C-W5-058] | PASS | PASS | PASS | **FAIL** needs 3 nodes, 4 vCPU/4 GiB each (context/03 VERIFIED) | 3 | 1 | 2 encrypted only if volume is LUKS [C-W5-031] | 1 | 2 | 5 | 3 | 45 | not ranked |

`total = Σ(weight × score)/5`. Cells without a claim inherit the row's gate evidence; the ones that matter for the ranking (restic vs Kopia) all carry claim IDs.

**Sensitivity (§6 of the frozen weights).** restic scores **≥ Kopia on every criterion** (C2, C3, C7 higher; the rest equal), so no weight change can reverse the order: restic wins all 14 ±5 runs. Margin over Kopia is 9.0 points (not a tie). **Robust.** Gate relaxation: relaxing G5 for Longhorn (45) or G1 for ZFS (46) leaves restic first.

**pending-lab / doc-only cells:** restic C2 is lab-proven on arm64 only (x86 and Pi silicon `pending-lab`, T-W5-01); Kopia C2 `doc-only`; nobody scored 5 on C3 because power-cut tests on the backup target are not done.

### 4.1 Steelman of the runner-up (Kopia)

*Argued for:* Kopia is what **Umbrel**, the most constraint-matched competitor (Debian appliance, Pi, small team), ships today [C-W5-041]. It is Apache-2.0, the same licence as OneMind. It has a built-in server and UI, optional Reed-Solomon error correction for bit-rot on cheap USB disks [C-W5-029], modern AES-GCM with scrypt [C-W5-027], and it is the engine **inside Velero**, so the cluster tier would share a repository format [C-W5-022]. Picking Kopia means copying a proven product line for line.

*Response:* (1) **Keys:** Kopia has one password per repository [C-W5-028], so a separate owner recovery key or an escrow key means sharing one secret; restic supports several keys natively [C-W5-023], which is the core of §6. (2) **Field failure on Pi:** Umbrel's Kopia cache exhausted an SD card's inodes and backups failed silently for ~22 h [C-W5-047]; Umbrel now ships special cache limits for small filesystems. (3) **Ransomware:** restic has a first-party append-only server [C-W5-024]. (4) restic is what Olares, k8up and the founder's VolSync already use [C-W5-050, C-W5-033, C-W5-034]. **What would flip it:** restic failing the 4 GB Pi 5 memory test with a 1 TB repository (T-W5-01; known index-memory issue [C-W5-026]) while Kopia passes, or restic development stalling for 12+ months.

### 4.2 What about Velero, Longhorn and ZFS?

- **Velero:** not in the core. Its file-system backup is beta, needs object storage and pod-mounted volumes, and creates a repository with the hard-coded password `static-passw0rd` unless you pre-create the Secret [C-W5-020, C-W5-021]. Keep it as an **optional Market app for the Cluster/Omni tier** (namespace migration between clusters, e.g. the founder's DOKS), with the Secret pre-created and the bucket encrypted. Its hook model is worth copying [C-W5-057].
- **Longhorn backup:** only on 3+ node clusters, and only with encrypted (LUKS) volumes, because backups of unencrypted volumes are not encrypted and the key lives in a Kubernetes Secret that must itself be in the recovery kit [C-W5-031].
- **ZFS send/recv:** the best tool for box-to-box replication when both boxes run ZFS, because a **raw** send can be stored on an untrusted friend's box without the key [C-W5-032]. But it is a CDDL kernel module [C-W5-058] built per kernel, which couples to A/B OS rollback (Umbrel pins pool feature flags so a rolled-back OS can still import pools; context/03). Offer only on Pro boxes with FailSafe-style pools, never as the only backup.

---

## 5. What competitors do

| Product | Engine and format | What is backed up | Encryption and keys | App consistency | Destinations | Restore onto new hardware | Constraint fit with OneMind |
|---|---|---|---|---|---|---|---|
| **Home Assistant OS** (Buildroot, Docker, funded team, no k8s) | SecureTar: plain outer tar, inner tars per part [C-W5-038] | HA config, history DB (optional), apps and their data, folders | Encrypted by default; v3 XChaCha20-Poly1305 + Argon2id; "emergency kit" key [C-W5-038, C-W5-039] | Per-app **hot** (pre/post commands) or **cold** (app stopped) declared in the app manifest; Core told BACKUP_START/END [C-W5-036, C-W5-037] | Local, NAS, Google Drive, OneDrive, Synology, HA Cloud (latest only, 5 GB) [C-W5-040] | Yes, during onboarding, **across device types** (Pi → other) [C-W5-039] | **High for UX and key model** (appliance, consumer, Pi); no k8s, so no datastore lesson. Copy: emergency kit, hot/cold manifest hooks, onboarding restore. |
| **umbrelOS 2.0** (Debian 13 + Rugix, Compose, small company) | Kopia (0.19.0 on 2.0.1 stable; 0.23.1 on beta) [C-W5-046] | Whole data dir: account, settings, files, apps; per-app `backupIgnore`, user exclusions [C-W5-044] | Password → first 64 bits of SHA-256 used as Kopia password, Kopia scrypt [C-W5-042]; unrecoverable if lost (Umbrel support page, C-TD-umbrelos-032) | **None for apps** (live crash-consistent copy); own DB via SQLite snapshot + quick_check [C-W5-043] | Network share or external drive only (code) [C-W5-041]; "Private Cloud coming soon" [C-W5-048] | Restore allowed before any user exists (onboarding) [C-W5-045]; one failed SMB onboarding report [C-W5-049] | **High** (Debian appliance, Pi 5, small team). Copy: hourly GFS retention, 2× space check, onboarding restore, ignore list. Do better: app hooks, recovery key, cloud/offsite. |
| **Olares** (k3s, funded team) | restic SDK [C-W5-050] | Selected folders; app backup only through an app's own HTTP endpoint, hardwired to Wise [C-W5-050] | Backup password (per user settings) | Cooperative app endpoint (`{app}/backup/start`) [C-W5-050] | Local path, Olares Space, S3, COS (context/03) | App restore Wise-only (context/03) | **High for k8s** (k3s), low for whole-box restore. Copy: restic on k3s. Do better: generic hooks instead of one hardwired app. |
| **Founder's DOKS cluster** (reported) | VolSync (restic), Velero, CNPG Barman, logical dumps [C-W5-056] | 46 PVC sources, namespaces, DB dumps, NATS streams | Encrypted exports; keys in a recovery export | Logical dumps restored into scratch DBs before "verified" [C-W5-056] | DigitalOcean Spaces | Rebuild-from-zero documented; export verified by decrypt only | Cloud k8s, not an appliance; **its verified-restore loop is the pattern to productise**. VolSync is AGPL [C-W5-034]: fine to run, avoid bundling modified. |
| **Velero** (generic k8s) | Kopia uploader [C-W5-022] | k8s objects + pod volumes | One static common key by default [C-W5-021] | Pre/post hook annotations, fsfreeze [C-W5-057] | Object storage | Cluster migration | Low for a single box. |

**No product I read automatically restores its backups to prove them.** Umbrel validates its own SQLite snapshot before backing it up [C-W5-043]; HA, Umbrel and Olares code paths read show no scheduled restore test (search was of the backup modules only; treat "none" as not found, not proven absent).

---

## 6. Encryption, keys and key recovery

**Design (serves M-2, U-4, R-2):**
1. **One restic repository per box per destination**, encrypted (AES-256-CTR + Poly1305-AES) [C-W5-023].
2. **Three keys on that repository** (restic supports several [C-W5-023]):
   - **Device key:** random, stored root-only on the data partition today; sealed to the TPM / Pi OTP later (W6 roadmap).
   - **Owner recovery key:** generated at setup, shown once as a printable emergency kit (text + QR), like HA's emergency kit [C-W5-039]. Setup isn't finished until the owner confirms they saved it (type back 4 random words).
   - **Optional escrow key** (opt-in): a second household admin, or later a OneMind-hosted escrow for people who want it. **Off by default** (M-2: users own their keys).
3. **Never derive the repository key from a short password** the way Umbrel does (64-bit truncation of SHA-256 of the user's password [C-W5-042]); use random keys and let the recovery key be the human-held secret.
4. **The k3s token and Kubernetes snapshots only ever leave the box inside restic** [C-W5-013, C-W5-014]. Run k3s with `--secrets-encryption` so Secret values aren't plaintext even inside the encrypted backup [C-W5-014].
5. **Rotation and revocation:** `restic key add` / `key remove` [C-W5-023] lets OneMind replace a lost device key or revoke a departed admin's escrow key without re-uploading data.
6. **Per-user keys (U-1):** phase 2. Private user spaces get their own repository and key so one household member's admin can't read another's private files. Phase 1 uses one box repository and states that the box owner can restore everything.
7. **Why this matters:** the most common real-world backup failure we found is a lost key, not a broken engine [C-W5-051].

---

## 7. App-consistent backups and the app manifest

Live copies of running databases are only crash-consistent. Umbrel copies app data live [C-W5-043]; HA lets each app declare how it wants to be backed up [C-W5-036]; Velero and k8up use pod annotations for pre-backup commands [C-W5-057, C-W5-033]; Olares calls an app endpoint [C-W5-050]. OneMind should put this **in the app manifest** (Q134/Q249, W12/W19), so every Market app gets it without the platform knowing the app:

```yaml
# onemind.app.yaml (backup section, proposal)
backup:
  mode: hot            # hot (default) | cold (stop app, copy, start) — HA pattern
  pre:  ["pg_dump -Fc -f /data/.onemind-backup/db.dump app"]   # run inside the container
  post: ["rm -f /data/.onemind-backup/db.dump"]
  sqlite: ["/data/app.db"]   # platform runs an online .backup for each, excludes live -wal/-shm
  exclude: ["cache/", "logs/", "thumbnails/"]                 # Umbrel backupIgnore pattern
  restore:
    post: ["pg_restore --clean -d app /data/.onemind-backup/db.dump"]
  rpo: 1h               # hint; the platform may back this app up more often than the box
```

Rules: `cold` and `pre/post` are mutually exclusive (HA validates the same [C-W5-036]); a failing `pre` fails that app's backup and raises an alert rather than silently copying a half-written DB; apps without a `backup` section default to `hot` with crash-consistent copy and a "not app-consistent" badge in the Market.

**Per-app rollback (Q156):** before an app upgrade, the platform runs that app's backup (HA keeps one pre-update backup per app by default, context/03). Rollback = Helm rollback of the release **plus** restic restore of that app's volume from the pre-upgrade snapshot. Schema-migrating apps must declare it, and the Market blocks downgrade without the matching snapshot (mirrors k3s's own rule [C-W5-016]).

---

## 8. 3-2-1, destinations, box-to-box and mirroring (UX-6)

**Default policy (copy Umbrel's schedule, HA's encryption, add offsite):**
- **Hourly** incremental, GFS retention: 24 hourly, 7 daily, 4 weekly, 12 monthly (Umbrel's code values [C-W5-041]); warn if the destination has less than 2× the backup size free (Umbrel's rule [C-W5-048]).
- **Copy 1:** on-box (fast undo, not a backup). **Copy 2:** USB disk or NAS. **Copy 3:** off-site: another OneMind box (friend/family), or any S3-compatible bucket, or a future OneMind cloud (M-1: later, optional). HA Cloud keeps only the latest backup [C-W5-040] and Umbrel's cloud is not shipped [C-W5-048], so a real offsite option is a gap competitors leave open.

**Box-to-box ("back up to your friend's OneMind")**
- The receiving box runs restic's **rest-server in append-only mode** for each guest box. The sending box can add but not delete, so ransomware on the sender can't wipe its backups; pruning runs on the receiver as a separate admin job [C-W5-024]. The receiver cannot read the data (it has no key).
- Where both boxes have ZFS pools, raw `zfs send -w` gives the same "untrusted receiver" property for whole datasets [C-W5-032].

**Mirroring (UX-6), three meanings, one roadmap.** The founder hasn't said which meaning of "mirror" he wants (Q300, `blocked: founder-decision`). Assumption used here: **(b) warm standby**.

| Meaning | How | RPO / RTO | Hardware | Phase |
|---|---|---|---|---|
| (a) Backup to another box | restic → append-only rest-server on box B | 1 h / hours | Any 2 boxes | 180 days |
| **(b) Warm standby ("mirror")** | Box B **continuously restores** box A's latest snapshot into a stopped standby (the restore drill of §9 doubles as the mirror). One click "promote B" starts it with A's identity; A is fenced. | 1 h / minutes | 2 boxes, B ≥ A's storage | Year 1 |
| (c) Live HA | 3 k3s servers on etcd (`--cluster-init` migration [C-W5-005]) + Longhorn replicated volumes | ~0 / seconds | 3+ nodes, 4 vCPU / 4 GiB each for Longhorn | Pro/Cluster, year 1–2 |

Fencing matters: the Blueprint's rule is "one writer authority per resource or site" (context/02 §10). Promotion must stop A's apps and NATS publishers before B starts.

---

## 9. Restore paths, drills and automatic verification

**Two restore modes** (this is the main design choice in this file):

| | **Portable restore** (default, user-facing) | **Exact restore** (disaster / same hardware) |
|---|---|---|
| Restores | OneMind identity + config (L2), app list with versions and settings, app volumes and DB dumps (L3–L5) | Everything in portable, plus the k3s datastore (L1) |
| Apps are | Reinstalled from the Market/app list, images pulled for the new architecture | Restored as they were |
| Works across | **Pi → x86, single box → cluster, k3s version jumps** | Same architecture, same node name, k3s same-or-newer within the skew rule [C-W5-015] |
| Competitor precedent | HA (Pi → other device) [C-W5-039], Umbrel (whole data dir) | k3s docs restore [C-W5-003, C-W5-012] |
| Risk | Apps whose state lives only in Kubernetes objects need an export hook | Stale status after restore [C-W5-010]; node affinity [C-W5-019] |

Portable restore avoids the two k3s traps (version skew, node name) and is what makes "restore onto a new box" and "move from Lite to Pro" the same button. Cross-architecture restore is **not yet tested** in our lab (T-W5-04).

**Restore at onboarding:** a fresh box offers "Restore from backup" before account creation, like Umbrel's no-user restore route [C-W5-045] and HA's onboarding restore [C-W5-039]. Test it hardest: it's where both competitors' users report failures [C-W5-049].

**Restore health gate:** after any restore, the box is "recovered" only when fresh signals pass: a new node Lease/heartbeat after the restore time, each app's own readiness probe, and a read of one known file per restored volume. Never trust the restored `.status` fields [C-W5-010].

**Automatic verification (the feature to lead with):**
- **Daily:** `restic check --read-data-subset=1/30` (rotates through 1/30 of the data each day, so all data is re-read monthly) (S5, `045_working_with_repos.rst`).
- **Weekly:** restore the latest snapshot into a scratch area (a throw-away namespace or a standby box), run each app's `restore.post` and a probe, then record **"last verified restore"** on the dashboard. This is exactly the founder cluster's PostgreSQL "verified" marker loop [C-W5-056] and the Blueprint's rule that "a backup counts as verified only after a restore drill" [C-W5-053].
- **Alert** when a backup fails, when the last success is older than 2× the schedule, or when the destination is nearly full. Umbrel's 22-hour silent failure is the counter-example [C-W5-047].

**Interplay with A/B OS updates (DC-12, W3):** before every OS or k3s update, run one backup (it is incremental, seconds when little changed [C-W5-054]) and keep it as the "pre-update" point. An OS rollback never rolls back data (Blueprint "host rollback does not roll back data", context/02 §14), but a k3s minor rollback needs the pre-upgrade datastore copy [C-W5-016], which this provides.

---

## 10. RPO/RTO targets per edition

Founder Blueprint targets: Core/identity RPO ≤ 1 h, RTO ≤ 4 h on a prepared spare; knowledge RPO ≤ 24 h [C-W5-053].

| Edition / profile | Datastore | App data | Off-site | RPO target | RTO target | Notes |
|---|---|---|---|---|---|---|
| Lite (Pi 5, 4–8 GB) | SQLite online backup, hourly with app data | restic hourly | Weekly minimum | 1 h | 4 h onto a new Pi or any box (portable) | Keep the repository small per box: restic index RAM grows with repo size [C-W5-026]. |
| Pro (mini PC) | Same | restic hourly; ZFS FailSafe optional (not a backup) | Daily | 1 h | 1 h onto spare; minutes with warm standby | |
| Robotics (Jetson) | Robot is usually a k3s agent or NATS leaf, not a server (W4) | Config, maps, calibration, mission logs via restic; telemetry via NATS JetStream mirrors | On dock | Last dock sync | Re-image + restore < 1 h | The robot never holds the only copy of anything authoritative. |
| Cluster / Omni (3+ servers) | `etcd-snapshot` hourly (`--etcd-snapshot-schedule-cron "0 * * * *"`) then restic-wrapped | restic per node, or k8up operator [C-W5-033] | Daily | 1 h | 4 h | Velero optional for namespace migration. |
| Greenhouse/IIoT profile (P-8, F-11) | As Lite | Sensor history: ≤ 24 h or documented discard | Weekly | 1 h config, 24 h history | 4 h, but **control continues locally** | Physical control must not depend on restore (Blueprint "controller continuity"). |

The lab restores reached API-ready in 6–13 s on a tiny dataset [C-W5-054]; real RTO is dominated by data size and link speed, so it must be measured on founder hardware (T-W5-02).

---

## 11. Recommendations with requirement IDs

| ID | Recommendation | Requirements | Evidence |
|---|---|---|---|
| **W5-R1** | **Engine: restic** (pin an upstream binary per arch, like Umbrel pins Kopia; Debian 13 ships 0.18.0 vs upstream 0.19.1). | R-2, R-3, M-6, D-001, F-14 | §4, C-W5-023, C-W5-025, C-W5-046 |
| **W5-R2** | **Single box keeps SQLite.** Datastore backup = SQLite online backup + integrity check + token + node password + encryption config, inside restic. Clusters use `etcd-snapshot`, restic-wrapped. **Replaces ADR-001 D5 item 1.** | R-1, R-2, F-14, M-4 | §2, C-W5-001…009 |
| **W5-R3** | **Grow by migration, not reinstall:** adding the 3rd server triggers `--cluster-init` (SQLite → etcd in place). | UX-6, M-4, F-14 | C-W5-005, C-W5-006 |
| **W5-R4** | **Three-key repository** (device, owner recovery, optional escrow); emergency kit required to finish setup; never derive keys from short passwords. | M-2, U-4, R-2 | §6, C-W5-023, C-W5-042, C-W5-051 |
| **W5-R5** | **`backup:` section in `onemind.app.yaml`** (hot/cold, pre/post, sqlite, exclude, restore.post). | A-1, A-5, R-2 | §7, C-W5-036, C-W5-044, C-W5-057 |
| **W5-R6** | **Two restore modes:** portable (default; cross-arch, cross-version) and exact (same hardware). Restore at onboarding. | P-7, H-1, R-3, F-14 | §9, C-W5-039, C-W5-045 |
| **W5-R7** | **Verified restores:** daily `check --read-data-subset`, weekly scratch restore with app probes, dashboard "last verified restore", alerts on stale/failing backups. | R-2, AI-4 | §9, C-W5-047, C-W5-053, C-W5-056 |
| **W5-R8** | **Restore health gate uses fresh signals only** (new heartbeat/Lease, app probes, file read), never restored `.status`. Share this gate with the A/B update commit (W3, DC-12). | R-1, AI-4 | C-W5-010 |
| **W5-R9** | **OneMind storage class with `Retain`**; app data deleted only through an explicit, backed-up "remove data" action; fixed node name per box. | R-2, M-2 | C-W5-019 |
| **W5-R10** | **3-2-1 by default:** hourly GFS, 2× space check, off-site to another OneMind box (append-only rest-server) or S3; OneMind-hosted offsite later and optional. | M-1, M-2, UX-6, N-6 | §8, C-W5-024, C-W5-040, C-W5-041 |
| **W5-R11** | **Mirror (UX-6) = warm standby** via continuous restore on box B, with fencing; live HA only on 3+ nodes. | UX-6, M-4 | §8 (founder-decision) |
| **W5-R12** | **Velero, Longhorn backup, ZFS send** are optional Cluster/Pro features, never the default; Velero only with a pre-created repository Secret. | F-14, U-4, D-001 | §4.2, C-W5-020, C-W5-021, C-W5-031, C-W5-032, C-W5-058 |
| **W5-R13** | **Agent permissions (AI-4):** agents may *trigger* a backup and *read* backup status; **restore, key changes, destination changes and deletes require human approval**, matching Umbrel's choice to keep backups out of its MCP tools (context/03, Q102). Restoring an attacker's snapshot hands them the box [C-W5-013]. | AI-4, U-4 | C-W5-013 |
| **W5-R14** | **Export for exit (Q281/M-2):** the backup is a standard restic repository (documented format, BSD tool [C-W5-023]) plus plain files (YAML app list, DB dumps), so an owner can restore without OneMind. | M-2, M-5 | C-W5-023 |

**ADR-001 D5, line by line:** disk layout and local-path: confirmed (add the Retain class, W5-R9) · Longhorn for 3+ nodes: confirmed with the encryption condition [C-W5-031] · item 1 (etcd-snapshot): **changed** (W5-R2) · item 2 (restic, not Velero FSB): **confirmed**; the stated reasons need correcting: k3s local-path volumes are `local` type, which Velero does support, but Velero is still rejected for its default static key, beta status and object-store dependency [C-W5-019, C-W5-020, C-W5-021] · item 3 (recovery kit): confirmed and specified (W5-R4) · policy: confirmed, plus app hooks (W5-R5), verified restores (W5-R7) and append-only box-to-box (W5-R10).

---

## 12. Lab spike: k3s + restic restore onto a fresh VM

Spike `w5-restore` (brief §7 item 5). README with hypotheses and pass/fail criteria was written **before** running; hashes of the README, script and logs are in `evidence/sources/W5.md`. The spike lives in `work/.lab/w5-restore/` (outside the repo, because this workstream may write only its assigned files); the orchestrator can move a scrubbed copy into `evidence/lab/w5-restore/`.

**Setup:** two disposable Lima VMs (Apple Virtualization, aarch64, Debian 13, 2 vCPU / 4 GiB), only a lab folder mounted. k3s v1.37.2+k3s1 with `--secrets-encryption`; restic 0.18.0; a namespace with a ConfigMap, a Secret and a pod writing a random marker to a local-path PVC.

| Hypothesis | Result | Evidence |
|---|---|---|
| H1 `etcd-snapshot` fails on SQLite | **PASS** (exit 1, "etcd datastore disabled") | C-W5-002 |
| H2 online SQLite backup + token + restic restores on a fresh VM | **PASS** (ConfigMap, Secret and marker match) | C-W5-009 |
| H3 `--cluster-init` migrates SQLite → etcd in place | **PASS** (409 keys, `state.db.migrated`, objects intact) | C-W5-006 |
| H4 etcd snapshot + token + restic restores on a wiped VM | **PASS** | C-W5-017 |
| Observed: restored status is stale | Node Ready / Pod Running reported before the container existed | C-W5-010 |
| Observed: snapshots expose plaintext objects | ConfigMap value readable in both; Secret not (secrets-encryption on) | C-W5-014 |
| Measured: idle writes, 10 min | SQLite ~19 MiB, etcd ~166 MiB (whole VM disk, indicative) | C-W5-018 |
| Measured: timings (tiny data) | backup 4.0 s; SQLite restore → API ready 5.8 s; etcd restore 13.0 s | C-W5-054 |

**Limits:** arm64 VMs on a Mac, not Pi/Jetson silicon; tiny data set; idle-write numbers include the whole VM disk and only 10 minutes; the etcd measurement started right after the migration; cross-architecture restore and power cuts during backup were not tested. One harness bug (a ServiceAccount race on the first run) was fixed and the run repeated; the aborted log is kept.

---

## 13. Failure reports and what they teach

| Report | What happened | Lesson for OneMind |
|---|---|---|
| Umbrel #2207 (2026-08) [C-W5-047] | Kopia's cache filled an SD card's **inodes**; backups failed for ~22 h with no warning while the dashboard looked healthy. | Alert on backup age, not just on errors; cap engine caches on small filesystems; keep caches off the backup source. |
| Umbrel forum, SMB onboarding restore (2026-09) [C-W5-049] | 100 GB restore from SMB hung at onboarding; a later restore "finished" but restored nothing. | Restore at onboarding needs its own test suite and a post-restore verification that counts files/apps. |
| HA forum, lost encryption key (2025-07) [C-W5-051] | After a storm, the owner rebuilt the box, but every backup was encrypted with a key that died with the old install. ~3 days of manual rebuild. | Make the recovery key a setup step that can't be skipped; show "recovery key last confirmed" on the dashboard. |
| TrueNAS forum, k3s SQLite malformed (2024-07) [C-W5-052] | k3s compaction failed with "database disk image is malformed". | Integrity-check every datastore copy; keep several hourly copies; document the etcd migration as an exit. |
| restic #1988 / #3374 (open) [C-W5-026] | Index memory grows with repository size; a 1 GB Pi ran out of memory after a 3 TB backup was added to a shared repository. | One repository per box; never share a huge repository with a Pi; measure on a 4 GB Pi 5 (T-W5-01). |
| Lab, stale status (this run) [C-W5-010] | After restore the API reported healthy pods that did not exist yet. | Health gates use fresh signals (W5-R8). |

---

## 14. Founder-runnable tests (for 22-…)

| ID | Test | Pass criteria | Decision consequence |
|---|---|---|---|
| **T-W5-01** | Pi 5 (4 GB, NVMe) running k3s + 5 apps; restic backup of ~200 GB to USB, then `restic check --read-data-subset=1/30`; record peak RSS (`/usr/bin/time -v`). | Peak RSS < 1 GB; backup completes; no OOM. | Fail → Kopia re-scored (§4.1 flip) or cap repo size on Lite. |
| **T-W5-02** | Whole-box drill: Beelink with 10 apps → wipe → **portable restore** onto the Dell 5540 (x86 → x86), then exact restore onto a re-imaged Beelink. Time each step. | All apps and data back; RTO ≤ 4 h; dashboard shows "last verified restore". | Fail → restore design changes before M4. |
| **T-W5-03** | 72 h idle + light load on Pi 5 NVMe: SQLite vs `--cluster-init` etcd; `cat /proc/diskstats` before/after, `smartctl -a` wear. | Report MiB/day for both. | etcd < 2× SQLite → reconsider etcd default (§2.4 flip). |
| **T-W5-04** | Cross-arch: back up a Pi 5 box, portable-restore onto x86 (and reverse). | Apps reinstall with the right arch images; data intact. | Fail on any app → that app needs a manifest fix or a non-portable flag. |
| **T-W5-05** | Power cut during a backup (pull the plug mid-upload to USB and to an append-only rest-server), then `restic check`. | Repository consistent; next backup succeeds. | Needed for C3 = 5. |
| **T-W5-06** | Founder cluster, read-only: `kubectl get replicationsources -A`, `velero backup get`, `kubectl get backups.postgresql.cnpg.io -A` to confirm reported state (context/01). | Matches context/01. | Informs the DOKS conversion plan (W4). |

---

## 15. Corrections to earlier files, open items

**Corrections (evidence-backed; `docs/` and `context/` not edited, per house rules):**
- context/03 lists Umbrel "Kopia 0.23.1 pinned" against the current release: **stable 2.0.1 pins Kopia 0.19.0**; 0.23.1 is on 2.1.0-beta.1/master [C-W5-046].
- context/03 / VUPD: "SQLite snapshot coverage UNVERIFIED" → **resolved: not covered by `etcd-snapshot`; covered by a file-level backup** [C-W5-001, C-W5-003, C-W5-009].
- context/03: "Longhorn backup encryption UNVERIFIED" → **encrypted only for LUKS-encrypted volumes** [C-W5-031].
- context/03: "borg licence clause count UNVERIFIED" → **BSD 3-clause** [C-W5-030].
- ADR-001 D5 reason "Velero doesn't support hostPath": correct as a Velero fact, but k3s's local-path volumes are `local` type, which Velero supports [C-W5-019, C-W5-020]. The decision stands for other reasons (§11).

**Open items:**
- Q300 meaning of "mirror": `blocked: founder-decision` (assumed warm standby). Goes to `26-OPEN-QUESTIONS-FOR-ZEUS.md`.
- Per-user repositories (U-1) phase and UX: design only.
- Whether HA/Umbrel run any scheduled restore test outside the modules read: not found, not proven absent.
- Cross-arch restore, power-cut during backup, real Pi/Jetson memory: founder-hardware tests above.
- The lab logs need scrubbing of VM-internal addresses before being copied into `evidence/lab/`.
