# Claims-ledger audit (LEDGER), 2026-11-11

**Scope:** every row in `evidence/claims/*.csv` (61 files, 2,035 rows). This audit addresses critic pass 1 (`tier-a-pass-1.md`) items #10, #11, #13, #14 (source copies), #15 and #16. No claim ID was changed or added, and `evidence/claims.csv` was not regenerated; the orchestrator merges it. A pre-audit copy of the ledger was kept outside the repo, and 526 field changes were logged.

> **Explain it like I'm the founder.** The claims ledger is the list of facts the report rests on, each with where it came from. This pass made the list checkable by a machine. Every row now has one of four simple statuses. Facts that change quickly (kernels, Jetson software, Kubernetes) are flagged for a re-check in 6 months instead of 12. Two facts that turned out to be outdated are marked "superseded" and point to the row that replaced them. Links to code now point at an exact commit, so they can't silently change. Six NVIDIA, Raspberry Pi and Umbrel pages that we had only seen as summaries were read in full and saved.

## 1. What changed

| Item | Result |
|---|---|
| **Status normalised** (critic #16) | 162 rows changed. The ledger now uses only four statuses: **verified 1,986 · partial 32 · unverified 15 · superseded 2**. Each old qualifier (for example "page summarised" or "VM, not Pi silicon") was appended to the claim text as `[status note: …]`, and no notes column was added. |
| **source_type normalised** | 57 rows changed. The ledger now uses only **PRIMARY 1,855 · PRIMARY-METADATA 90 · SECONDARY 79 · UNVERIFIED 11**. Qualifiers moved into `[source: …]`. The old values mapped as follows: COMMUNITY → SECONDARY (except a GitHub PR, C-REF-W7L-008 → PRIMARY); VENDOR → PRIMARY when a vendor describes its own product, SECONDARY for third-party or press-release sites (C-STEEL-updates-mender-019, C-REF-W6-technical-003), and UNVERIFIED for a page that was never opened (C-STEEL-updates-mender-020); INTERNAL → PRIMARY; SECONDARY-RESEARCHER → SECONDARY. |
| **6-month re-check** (critic #15) | 34 rows moved from 12 to 6 months (`accessed_date` + 6). They were selected by component: kernel, Jetson Linux/JetPack/L4T, BSP, meta-tegra, k3s/RKE2/k0s/kine/Talos/MicroShift and Pi firmware. Five rows (C-W7-048, C-W5-033, C-DEC-007, C-TD-olares-040 and C-LAB-k3s-footprint-restore-015) were set by ID because the critic listed them. All 16 IDs the critic named now end on 2027-05-10. Lifecycle, pricing and hardware-availability rows stay at 12 months. Rows that authors had already set shorter (1–3 months, for imminent events) were left alone. |
| **Superseded** (critic #11) | **C-W7-005** ("r35 still active") is superseded by **C-REF-W7L-001** (JetPack 5.1.8 is the final JetPack 5 release, 2026-10-30; see also C-STEEL-jb-012). **C-W7-056** (Tegra BSP licence, UNVERIFIED) is superseded by **C-LIC-001**, which opened the agreement text. **C-W18-027** is now `partial`, narrowed by **C-STEEL-jb-015**: CUDA lists Debian 13 for amd64 and arm64-SBSA but not for Jetson. |
| **Re-pinned to SHAs** (critic #13) | 41 rows got new `source_url` and `commit_or_tag` values: every row named in the brief, plus other licence rows built from GitHub metadata (C-W6-074, C-W9-027, C-TD-flagged-034, C-STEEL-jb-007, C-TD-villageos-037…039), the Linux tag permalinks and the scarthgap branch link (C-W7-018). Versioned claims are pinned to the commit their release tag points to. The rest are pinned to the head of the default branch at the access date. All 72 new SHA permalinks were re-fetched and resolve. Details are in `sources/LEDGER.md` §2. |
| **Corrections found while re-pinning** | C-W7-051: NVIDIA/Cosmos's LICENSE is **OpenMDW-1.1**, and IsaacLab's LICENSE states BSD-3-Clause (GitHub reports NOASSERTION for both). C-W7-053: rknn-toolkit2's licence is the **proprietary RKNN SDK License**, and hailort has no top-level licence file at v5.5.0. C-W9-027: sqlite-vec is **dual MIT/Apache-2.0**. C-W2-049: the Mender and Isar LICENSE files are multi-licence notices. C-W6-074: GitHub reports NOASSERTION for cosign at the pinned SHA, but the file is the unmodified Apache-2.0 text. These were added to the claims as `[LEDGER …]` notes; no Apache-compatibility verdict changed. |
| **Fetch-summary claims re-checked** (critic #10) | C-W3-042, -049, -050, -051, -057 and -066, plus C-W3-027, were each confirmed against the full text. The pages are saved in `sources/W3/` with `SHA256SUMS`, and every row quotes its line ranges. All seven are now `verified`. C-W3-066 cites the pinned docs source because raspberrypi.com served a Cloudflare challenge, which was not bypassed. |
| **Lab source copies** (critic #14) | 94 text copies were placed in `sources/{W4,W5,W6,W18,TD-villageos}/` and `sources/TD-truenas-scale/from-lab/`, each folder with an `INDEX.md` and `SHA256SUMS`. They are masked (e-mail addresses, private IP addresses, tailnet host names and forum user names) and each is under 1 MB. gitleaks and the IP, e-mail and `.ts.net` greps are clean. Originals in `work/.lab/` were left in place. |
| **Other fixes** | C-STEEL-backup-kopia-014 had 15 fields because an unquoted comma split `commit_or_tag`; the field was rejoined. Nine C-LAB-fedora-bootc rows cited a URL that points at the branch; these now use repo-relative paths. |

## 2. Status definitions now used

- **verified:** the cited source was opened and supports the claim *as worded*. That includes "X reports Y" claims that rest on a secondary source, whose `source_type` stays SECONDARY.
- **partial:** only part of the claim is supported, or the claim rests on an inference or interpretation, or on a secondary source for a fact stated as fact.
- **unverified:** the source was not opened (blocked, or only a search summary was seen).
- **superseded:** a newer row replaces the claim; the bracket names that row.

## 3. Check rerun (critic #16)

Of the IDs cited in 01, **12 are not `verified`**: C-LAB-secureboot-rauc-005, C-REF-W19-technical-009, C-REF-W6-technical-008, C-STEEL-ubu-011, C-W18-027, C-W19-022, C-W19-027 and C-W19-047…049 are `partial`; C-REF-W8-longevity-009 is `unverified`; and C-W7-005 is `superseded`. Files 03–07 cite no claim that is not verified. 01 cites 33 non-primary IDs, mostly refuters' failure reports, which is expected. 03, 04 and 06 cite 1, 2 and 3 SECONDARY rows respectively, all worded as reports.

## 4. Left for owners (not done here)

| # | Item | Owner |
|---|---|---|
| L1 | 08 lines 26, 53 and 78 and 01's FF-1 rows still describe r35 as active and cite C-W7-005; they should cite C-REF-W7L-001. 28 and 01 should reflect C-W18-027's narrowing. | W7, W18, 01 editors |
| L2 | `sources/W4.md`, `W5.md`, `W6.md`, `W18.md`, `TD-villageos.md` and `TD-truenas-scale.md` still point to `work/.lab/` paths. They should be repointed to the new folders; `INDEX.md` maps them by raw sha256. | each tag |
| L3 | Claim rows still cite `work/.lab` **lab logs**: C-W4-076…081 and C-W5-002, -006, -009, -010, -014, -017, -018 and -054. These need the lab-spike copy (critic #5), which was out of scope for this audit. Do not copy `w5-restore/shared/`. | lab owner |
| L4 | C-W18-038 (gitcode `master`, search summary only) is now `unverified` and is not pinned. C-W18-004 (CIP wiki 403) is `unverified`. | W18 |
| L5 | Rows pinned to the head of the default branch reflect the access-date HEAD, not necessarily the commit the author read. Several W8 and W11 rows carry 7–8-character SHAs; they resolve but could be expanded. Rows that are metadata only (stars, contributors, activity via the API) are timestamped, not SHA-pinned, by design. | — |
| L6 | The C-LAB-fedora-bootc rows should be repinned to the commit that lands them once the branch is committed. | lab owner |
| L7 | `cjis61.txt` (1.18 MB) was not copied; `W6-archive/` keeps the excerpt. | W6 |

## Glossary

- **SHA permalink:** a link to a file at one exact commit. Unlike a branch link, it never changes.
- **Superseded:** replaced by a newer fact; the row is kept for history.
- **PRIMARY / SECONDARY:** the original source (official docs, code, law) versus someone else's report of it.
- **Re-check-by:** the date by which the fact should be looked up again.
