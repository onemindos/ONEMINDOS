# W5 P0-2 refuter: longevity and vendor risk

| Field | Value |
|---|---|
| Claim | W5-P0-2: a single-box k3s SQLite datastore has a supported backup path: copy `/var/lib/rancher/k3s/server/db` plus the server token. Because kine opens SQLite in WAL mode, the copy must use SQLite's online backup API, or k3s must be stopped. An online `sqlite3 .backup` plus token, node password and a restic snapshot of the local-path volumes restored onto a second, freshly installed VM, recovering a ConfigMap, an encrypted Secret and the PVC data. |
| Cited claims | C-W5-003, C-W5-004 (k3s-io/docs@8958508 `datastore/backup-restore.md`), C-W5-007 (kine@35f4319 `sqlite.go` L22-L23), C-W5-009 (lab), C-LAB-k3s-footprint-restore-011 (second lab) |
| Lens | Longevity and vendor risk (third refuter; technical and security ran earlier) |
| Protocol | RESEARCH-MISSION.md §2 rule 7. This refuter read only the claim, its cited sources and the new sources below; it did not read the author's reasoning or the other refuter files first. |
| Date | 2026-11-11 |
| Verdict | **weakened**: the mechanism holds; "supported" and its fitness for a 10-year product do not hold without conditions |

## 1. Cited sources re-opened

| Source | Result |
|---|---|
| `docs/datastore/backup-restore.md` L7-L18 | Confirmed, and it is the **entire** vendor procedure: "No special commands are required … take a copy of `/var/lib/rancher/k3s/server/db/`", plus the token warning. It says nothing about WAL, the online backup API, the node password or volume data. |
| `docs/datastore/datastore.md` L9, L16 | SQLite is the default. The vendor's own example use for it is "a simple, short-lived cluster in your CI/CD environment" [C-REF-W5-longevity-009]. |
| kine `sqlite.go` L22-L23 | Confirmed: `_journal_mode=WAL&...&_synchronous=NORMAL`. The same file also has a `NewWithLitestream` variant. |
| Lab C-W5-009 / C-LAB-k3s-footprint-restore-011 | Not re-run. The second lab's log is in the repo. Both labs used **one** k3s version (v1.37.2+k3s1) on source and target. |

## 2. Strongest counter-argument (longevity)

"'Supported' means SUSE stands behind it for the product's life. Here it means a three-line doc paragraph that is less safe than the claim's own procedure. The vendor says plain 'take a copy'; the claim correctly adds the WAL caveat, which is **OneMind's engineering, not the vendor's**. The datastore underneath is maintained in practice by one person. It has a public record of corruption that the maintainer says k3s can't prevent. Its exit path to etcd has broken once in a shipped patch. And each k3s minor lives 17-18 months, while a restore only works onto the same or a newer version within skew. A backup taken on a 2027 box can't simply be restored onto a 2031 box. Over a 10-year horizon this is a path that **OneMind has to own and keep testing itself**, not a vendor-supported path."

## 3. New failure-seeking sources

| ID | What it shows | Effect |
|---|---|---|
| C-REF-W5-longevity-006 | Of the human-authored commits to `k3s-io/kine` in the last 12 months, **42 of 50 are by one maintainer** (brandond). All-time: 190, against 64 for the next human. | Bus factor ≈ 1 for the layer that defines the on-disk format being backed up. SUSE still employs the k3s maintainers (they spoke at KubeCon EU 2026), so this is concentration, not abandonment. |
| C-REF-W5-longevity-004 | Upstream SQLite corruption reports on single-server k3s (#2623 on v1.18.6, #9787 on v1.22-1.24). Maintainer: "There is nothing that can be done within K3s to prevent this." #2623 was closed by the stale bot with no fix. | The vendor treats datastore integrity as the operator's problem. That backs up the claim's need for an integrity check, but undercuts "supported". |
| C-REF-W5-longevity-005 | A 2024 Pi 4 k3s post-mortem: `integrity_check` failed and `.recover` and `.dump` both failed. A raw-file backup restored fine. The DB later grew to 1.5 GB with compaction failing. The author concludes that logical backups are safer than raw file copies. | Real-world proof that the backup **is** the recovery path (supports the claim). It also shows that a backup of a bloated or half-corrupt DB can carry the fault forward, so the integrity check must gate the backup, not just be logged. |
| C-REF-W5-longevity-002, -003 | The SQLite-to-etcd migration broke in v1.32.5 (kine#464), and the restart came up as an **empty cluster**. Upstream had no e2e test for it until mid-2025. | The one-way exit from SQLite has regressed once. A kine change also altered SQLite-adjacent behaviour without a k3s test catching it, which is the same kind of risk the backup format runs. |
| C-REF-W5-longevity-007 | k3s minors: about 17-18 months GA to EOL (1.31-1.37). | A restore needs the same or a newer k3s within skew (C-W5-015). Long-lived backups therefore need either the matching k3s binary stored with them, or stepped upgrades on restore. |

No SUSE or Rancher layoff, licence change or SQLite deprecation was found. The k3s 1.37 release adds kine T4 and Memory drivers and doesn't mention SQLite [C-REF-W5-longevity-008].

## 4. Verdict: weakened

The mechanism is sound, and two labs reproduced it. The longevity attack lands on two words and one missing condition:

1. **"Supported" overstates what the vendor provides.** The vendor documents a plain file copy. The WAL-safe procedure is OneMind's own and should be described as such: "vendor-documented approach, OneMind-hardened procedure".
2. **Version binding is missing from the claim.** The backup is bound to the kine schema and the k3s version that wrote it. With 17-18 month minors and no downgrade path, every snapshot must record the exact k3s version and keep (or be able to fetch) that binary, so the restore runs on the same version first and upgrades afterwards.
3. **Single-maintainer kine and a record of regressions** mean OneMind must re-run the restore drill (SQLite online backup → fresh box → verified data) on **every k3s version bump it ships**, as a release gate, not as a one-off lab.

None of these sources show the path failing outright, and the alternative (etcd on a single box) has its own wear cost. So the decision stands with conditions; it isn't refuted.

## 5. What would flip it

- **To refuted:** a k3s/kine release that changes the SQLite schema or WAL handling so that an online `.backup` copy no longer restores (for example, a required migration that runs only on the live DB, or a format bump with no forward path). Or a SUSE notice that deprecates embedded SQLite, or limits it to non-production use.
- **To refuted (vendor):** loss of the kine maintainer with no successor activity for 6+ months (human commits in `k3s-io/kine` falling to near zero), while k3s keeps SQLite as the default.
- **To upheld:** (a) the k3s docs adopt the online-backup and WAL procedure, which would make "supported" true; (b) OneMind's CI shows the restore drill passing across at least three consecutive k3s minors, including a restore of an older-minor backup followed by a stepped upgrade.
