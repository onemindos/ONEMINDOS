# Runner-up steelman: Kopia as the OneMind backup engine

- **Role:** runner-up steelman (RESEARCH-MISSION.md §2 rule 7). This agent was told to argue **for** Kopia over restic. It is advocacy held to the evidence rules: each fact is primary-sourced and opened on 2026-11-11 (code and docs at pinned SHAs), or labelled VENDOR, INFERENCE or UNVERIFIED. The honest weaknesses are in §7.
- **Date:** 2026-11-11 · **Re-check by:** 2027-05-11
- **Verdict:** `steelman`
- **Decision under test:** ADR-001 **D5** / scorecard **S4**. Current result: restic 75, Kopia 66, "restic ≥ Kopia on every criterion, robust" ([`06` §4](../../06-backups-recovery.md), [`01` §3.4](../../01-FOUNDATION-DECISION.md)).
- **Ledger:** [`evidence/claims/STEEL-backup-kopia.csv`](../claims/STEEL-backup-kopia.csv) (C-STEEL-backup-kopia-001…021)
- **Serves requirements:** F-11, F-14, M-6, R-1, R-2, R-3, D-001

> ### Explain it like I'm the founder
> restic and Kopia are close cousins: both chop your data into chunks, store each chunk once, encrypt it, and are single Go programs. The study chose restic mainly because one restic repository can hold **several keys**, so you can print the owner a recovery key separate from the box's own key.
> The best case for Kopia is that this key advantage is smaller than it looks, and that Kopia is ahead on the thing that matters most when a box gets hacked: **making the off-site copy impossible to delete.** Kopia can lock every backup file in the cloud for, say, 30 days, so that even stolen admin credentials can't delete it, and it keeps renewing those locks itself. restic can only *tolerate* such buckets. Kopia also comes with the features OneMind would otherwise have to write: built-in pre/post hooks for database dumps, scheduling, daily self-checks, replication of a whole repository to a second place, a server mode that keeps each device's backups apart, and a GUI.
> The catch (§7): Kopia promises less about reading very old backups, it gets dangerous if a box's clock is badly wrong (a real risk off-grid), and its Pi memory advantage is still on paper. **Even argued at full strength, Kopia ties restic rather than beating it, unless restic fails the Pi memory test.**

---

## 1. The claim

> **For OneMind's box-to-offsite backup engine, Kopia is at least as good as restic and better on the security criterion that decides real-world recovery (immutable off-site copies), on fleet isolation at enterprise scale, and on the amount of glue code a solo developer must write. The scorecard's 9-point gap comes mostly from one overstated security cell, one evidence asymmetry (restic lab-tested, Kopia not), and one citation error.**

## 2. Strongest arguments

### 2.1 Ransomware: Kopia manages immutable off-site copies; restic only survives them (C3, R-1)

| Fact | Evidence |
|---|---|
| Kopia creates repositories in **COMPLIANCE-mode object lock** (`--retention-mode COMPLIANCE --retention-period 30d`) and **renews the locks during full maintenance** (`--extend-object-locks`). The same works on Azure (version-level immutability) and Google (object retention). Point-in-time reconnect lets you open the repository as it was before an attack. | [C-STEEL-backup-kopia-001] Kopia docs `Ransomware Protection` @72ec08f L83–L141 |
| restic's object-lock support is an **upload checksum**, added in 0.13.0, so that it "can now be used" with lock-enabled buckets. It doesn't set or extend retention. Its anti-ransomware model is `rest-server --append-only` plus a separate trusted host for `forget`/`prune`. The restic issue that lists that model's drawbacks has been open since 2024-09. | [C-STEEL-backup-kopia-002], [C-W5-024] |

**Why this matters to OneMind:** a box owner's off-site copy goes to S3-compatible storage (Backblaze, R2, Wasabi, a OneMind cloud). The append-only design requires OneMind to run a rest-server and a separate pruning host per owner, or per fleet. Object lock needs only a bucket setting. A provider enforces it, and **even the box's own leaked credentials can't defeat it.** For a consumer product, protection that needs no extra server is the stronger one. The scorecard credited restic's C3 = 4 partly for "append-only" [C-W5-024]. On this axis Kopia is at least equal, and arguably ahead.

### 2.2 The multi-key advantage is narrower than the scorecard implies (C3)

- restic's own design doc says that a leaked key gives access to the **master key**. "A password change will not prevent this," and replacing the master key means `copy` into a new repository [C-STEEL-backup-kopia-004]. So restic's extra keys are **extra doors to the same safe**. Removing a key doesn't revoke what a thief already decrypted.
- Kopia uses **envelope encryption**. The password derives a key that wraps the format blob holding the content keys. `ChangePassword` rewrites only the config and blobcfg blobs [C-STEEL-backup-kopia-005]. That is the same revocation strength as restic: neither engine rotates the data key.
- *INFERENCE (design, not tested):* OneMind can get "box key + printed owner recovery key + optional escrow" on Kopia by **wrapping the one repository password to several recipients** (for example, an `age` file with a TPM-sealed box identity and an owner recovery identity). That is a small amount of OneMind code, and it can be audited, because the wrapped secret is the same secret restic's key files wrap. The real difference is convenience, not capability: restic stores the wrappers inside the repository, while OneMind would store them next to it.
- Net: the scorecard's note "Kopia C3 = 3: one password per repo" [C-W5-028] scores a packaging difference as a security difference.

### 2.3 Fleet and enterprise isolation (F-14, F-11 fleets)

- **Kopia Repository Server:** each device authenticates as `user@host`, **holds no storage credentials**, sees only its own snapshots and policies, and ACLs can be customized (`kopia server acl`, since v0.8) [C-STEEL-backup-kopia-003]. A compromised greenhouse Pi can't list or delete the warehouse's snapshots, and it never holds the bucket key. Deduplication across devices still works.
- This matches F-14's "one OS from a Pi to enterprise". The **same binary** is the single-box engine, the fleet backup server (with an HTTP/gRPC API for a OneMind console, per the Features doc), and **the default data mover in Velero** (restic path deprecated since v1.15 [C-W5-022]) and in **Veeam Kasten** [C-STEEL-backup-kopia-016, VENDOR]. At the GPU-cluster tier, OneMind would meet Kopia anyway. Choosing restic means two repository formats in one product line.
- *Fair counterpoint:* restic's rest-server `--private-repos` gives per-user sub-repositories [C-STEEL-backup-kopia-020]. That provides isolation, but it gives up cross-device deduplication, and it's still a separate server to run.

### 2.4 Less glue for a solo developer (C5, M-6)

Here is what Kopia ships in the box, and what OneMind would otherwise write around restic:

| Need in `06` | Kopia built-in | Evidence |
|---|---|---|
| App hooks (DB dump, fsfreeze) before backup | **Actions**: before/after per snapshot root *and* per folder; can redirect the upload to a snapshot mountpoint | [C-STEEL-backup-kopia-007] |
| "Last verified restore" | Daily full maintenance runs `snapshot verify`; `--verify-files-percent` downloads and decrypts a random sample | [C-STEEL-backup-kopia-009] |
| 3-2-1 (USB copy + off-site) | `repository sync-to`: incremental whole-repository replication, no re-encryption, `--must-exist` guards an unmounted USB disk | [C-STEEL-backup-kopia-008] |
| Retention, scheduling, per-path policy | Policy engine with scheduling and GFS retention (what Umbrel uses [C-W5-041]) | Features doc @72ec08f |
| Bit-rot on cheap USB disks | Reed-Solomon ECC (experimental, see §7) | [C-STEEL-backup-kopia-012] |
| Owner-facing browse/restore UI | KopiaUI / server web UI; Umbrel built "Rewind in Files" on it | [C-STEEL-backup-kopia-017] |

restic has none of the first four as a built-in feature. Hooks, scheduling and verification become OneMind code and systemd units. For one developer, every line not written is a line not maintained to 2036.

### 2.5 Pi memory: the structural argument (C2, F-11, F-14)

- restic's index memory grows with repository size. The issue has been open since 2018, and a 1 GB Pi 3 ran out of memory after a 3 TB backup [C-W5-026]. That is why `06` makes **T-W5-01 (4 GB Pi 5, 1 TB repository)** the flip test.
- Kopia **memory-maps its committed index from the on-disk cache** instead of loading it onto the heap [C-STEEL-backup-kopia-006]. Memory-mapped pages can be evicted under pressure, so a large repository should degrade into disk reads rather than an OOM kill. *This is design evidence, not a measurement.* Kopia has had OOM reports of its own (for example, maintenance memory on Windows, issue #1846, open). It needs the same lab test.
- The scorecard's C2 split (restic 4 "lab", Kopia 3 "doc-only") is an **evidence asymmetry**: only restic went to the lab. On the documented design, Kopia is the safer bet on the 4 GB tier.

### 2.6 The constraint-matched competitor chose it (C4, RS-2)

- **umbrelOS** (Debian appliance, Pi 5, small team: the closest match to OneMind) ships hourly whole-box Kopia backups, pinned per architecture [C-W5-041, C-W5-046].
- Its public failures are **integration bugs in umbreld**: a cache filling inodes [C-W5-047], passwords logged to the journal, a cache written to the root overlay, and a stale mount path [C-STEEL-backup-kopia-018]. None of them is a Kopia data-loss bug. OneMind gets to **read Umbrel's bug list before writing a line**, which is the "copy the proven competitor" rule working as intended.
- Production weight beyond Umbrel: Velero's default uploader [C-W5-022] and Veeam Kasten's data mover [C-STEEL-backup-kopia-016]. Kasten is a commercial enterprise product that depends on Kopia's format.

### 2.7 Longevity to 2036 (C1)

- **Licence fit:** Apache-2.0 [C-W5-027], the same licence as OneMind, which keeps the open-core story clean.
- **Corporate dependence as a survival signal:** Veeam Kasten and Velero both ship Kopia's repository format to enterprise customers [C-STEEL-backup-kopia-016, C-W5-022]. Vendors that sell on a format have a commercial reason to keep it readable. restic has no comparable vendor stake that this run found.
- **Release cadence is healthy:** six minor releases from 0.18 (2024-11) to 0.23.1 (2026-06), against restic's 0.18 to 0.19.1 [C-STEEL-backup-kopia-014].
- **Bus factor is equal, not worse:** in the last 12 months one human led each project. julio-lopez made 154 of 423 Kopia commits; MichaelEischer made 475 of 653 restic commits [C-STEEL-backup-kopia-015]. Kopia has a written governance document with a two-person PMC.
- **Bookkeeping defect:** the Kopia C1 cell in `06` §4 cites **C-W5-030, which is the borg claim** [C-STEEL-backup-kopia-021]. Kopia's C1 = 3 currently has no Kopia source. This steelman keeps it at 3 and supplies sources (014, 015, 016).

### 2.8 Robotics and IIoT fit (F-11, C2)

- Both are static Go binaries for x86_64 and arm64 (Jetson, Pi 5, RK3588). Kopia also ships armhf `.deb`s for older 32-bit IIoT gateways [C-STEEL-backup-kopia-013].
- **Fleet reality for robots:** a robot or field gateway is the device most likely to be stolen or compromised. Under Kopia server mode it holds **no bucket credentials** and can't see its siblings' data (§2.3). Object lock (§2.1) means a compromised robot can't erase the fleet's history. For IEC 62443-style zone separation, that model fits better than "every device holds a full repository key".
- Per-folder Actions (§2.4) fit robot data: run an MCAP/rosbag close-and-rotate hook on the log directory only, before that folder is read.

## 3. Re-scored S4 (steelman, frozen weights)

| Criterion (weight) | restic (current) | Kopia (current) | Kopia (steelman) | Basis |
|---|---|---|---|---|
| C1 Longevity (20) | 3 | 3 (mis-cited) | **3** | Same score, now with Kopia sources [014–016] |
| C2 Hardware/robotics (20) | 4 lab | 3 doc-only | **3, pending lab** | Can't claim 4 without a lab run; design favours Kopia [006] |
| C3 Security (15) | 4 | 3 | **4** | Object lock + extension [001] vs append-only [002]; key revocation equal [004, 005]; server isolation [003] |
| C4 Proven (15) | 3 | 3 | **3** | Umbrel + Velero + Kasten, but no robotics/industrial product and Umbrel is only ~12 months [017] |
| C5 Solo operability (10) | 4 | 4 | **4** | Built-ins (§2.4) argue for 5, but the anchor needs a lab dry run |
| C6 Cost/licence (10) | 5 | 5 | **5** | Apache-2.0 |
| C7 Ecosystem (10) | 4 | 3 | **4** | Velero default + Kasten + Umbrel + Kopiur [019]; one engine across box and cluster tiers |
| **Total** | **75** | 66 | **71** | `Σ(w×s)/5` |

- **Honest result:** at full strength, the gap shrinks from 9 to **4**. restic still wins.
- **If Kopia passes the Pi lab test (C2 = 4):** 75 vs 75, a tie.
- **If restic also fails T-W5-01 (restic C2 = 3):** Kopia wins, **75 to 71**.

## 4. What this steelman changes even if restic stays

1. Fix the C1 citation in `06` §4 (C-W5-030 is borg) [021].
2. Restate restic's C3 rationale. "Multi-key" doesn't give revocation [004]. Off-site immutability should be designed **explicitly**: object-lock buckets with a lifecycle rule, or rest-server append-only with a separate pruning identity. It shouldn't be implied by the engine choice.
3. Run **T-W5-01 for both engines** on the same Pi 5 and 1 TB repository. A test of only one engine can't settle a C2 difference.
4. Record that the cluster tier (Velero) will hold Kopia repositories anyway, so OneMind runs two formats. Decide that on purpose.

## 5. F-14 in one picture

```
Pi greenhouse ──kopia──┐
Robot / gateway ─kopia─┼──► Kopia Repository Server (per-device ACL, no bucket keys on devices)
Home box ──kopia───────┘          │  sync-to (USB) · object-locked S3 (off-site)
GPU cluster ── Velero (Kopia uploader) ──► same format, same tooling
```

With restic, the cluster row uses a **different** engine (Velero has deprecated restic [C-W5-022]), unless OneMind standardizes on VolSync/k8up there.

## 6. Where competitors stand (for context)

| Product | Engine | Note |
|---|---|---|
| umbrelOS | Kopia | Constraint match; Backups since 1.5.0 (2025-11-05) [017] |
| Olares | restic SDK | App-cooperative backups [C-W5-050] |
| Velero / Kasten | Kopia | Enterprise k8s; Velero's restic path deprecated [C-W5-022, 016] |
| VolSync | restic (Kopia mover never merged) | PR #1723 closed unmerged [019] |

## 7. Genuine weaknesses (the steelman's own refutation)

1. **Clock skew can destroy data.** Kopia's own docs: large skew "can lead to … Kopia deleting its own data" [C-STEEL-backup-kopia-010]. Off-grid, mesh and robot boxes without NTP or a battery-backed clock are exactly OneMind's F-11/F-13 territory. Kopia would need a hard guard: refuse maintenance until time sync is confirmed. restic's prune is lock-based. *UNVERIFIED* whether restic has an equivalent time hazard; none was found in this pass.
2. **A weaker backward-compatibility promise.** Kopia guarantees reading only the current and previous minor format on v0.x; anything older is "likely" [C-STEEL-backup-kopia-011]. A 2026 backup restored in 2036 is outside the promise. OneMind would have to pin and archive old binaries, or run format upgrades.
3. **ECC is experimental** and must be chosen at repository creation [012]. Don't count it as a feature.
4. **No upstream RISC-V or other architecture builds** (amd64/arm/arm64 only), against restic's riscv64, ppc64le and s390x [013]. Go cross-compiles easily, but it would be untested upstream. That matters for a 2036 horizon.
5. **No native multi-key.** OneMind would own the key-wrapping code (§2.2). It's small, but it's security code a solo developer must get right.
6. **Smaller community and more open issues:** 14.6k stars and 939 open issues, against restic's 37.1k and 648 (gh api, 2026-11-11). VolSync, which the founder already runs, has **no** Kopia mover, and the community fork moved to a new AGPL operator (Kopiur) rather than upstream [019]. AGPL is a licence-boundary question for OneMind (G1) if it were ever bundled.
7. **The Umbrel proof is young** (~12 months in stable) [017], and its first year produced a silent-failure incident [C-W5-047].
8. **Server-mode ACLs protect manifests, not content** [003]. Isolation relies on content IDs being unguessable.

## 8. What evidence would make Kopia the winner

| Evidence | Effect |
|---|---|
| T-W5-01 run for **both** engines: restic peaks over 1 GB or OOMs on a 4 GB Pi 5 with a 1 TB repository, Kopia stays under | restic C2 → 3, Kopia C2 → 4: **Kopia 75 vs restic 71** |
| OneMind commits to object-locked S3 off-site as the default ransomware control (instead of rest-server append-only) | restic C3 → 3: restic 72, below Kopia's 75 if C2 lab ties |
| A cluster-tier decision to use Velero (Kopia) for GPU clusters | Strengthens Kopia C7 (one format), arguably → 5 |
| A lab test showing that a Kopia time-sync guard prevents the skew deletion on an RTC-less box | Removes weakness 1 |
| A restic stall of 12+ months, or Kopia reaching v1.0 with a multi-version read guarantee | C1 moves in Kopia's favour |

**Bottom line for the decision record:** restic remains the right default on today's evidence, but the margin is about 4 points, not 9. The deciding test is a **two-engine** Pi memory run, plus an explicit off-site immutability design.
