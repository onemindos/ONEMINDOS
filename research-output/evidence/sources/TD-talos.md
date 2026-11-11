# Sources: TD-talos (Talos Linux, Tier B condensed teardown)

Used in: `research-output/02-competitors/talos.md`. Claims: `evidence/claims/TD-talos.csv` (C-TD-talos-001 to 042).

**Archiving note.** Wayback "save" requests are refused in this environment. Vendor web pages and issue opening posts are saved as extracted text with sha256 hashes in `evidence/sources/TD-talos/` (see `SHA256SUMS`). Vendor contact emails and testimonial author names and handles in the saved pages are masked, and IP-shaped strings are replaced. Issue snapshots keep only the title, state, dates and the first 45 lines of the opening post. Code and docs need no archive, because every citation is pinned to a commit SHA.

## Code and official docs (pinned)

| Source | Pin | Accessed | Type |
|---|---|---|---|
| github.com/siderolabs/talos | tag `v1.14.5` → `dad8d3edfe7ca381044d7cad259fdf3030efa700` (released 2026-10-26) | 2026-11-11 | PRIMARY (code) |
| github.com/siderolabs/extensions | `8db133ae509f67480f6973f302eab062b8a3b3d6` (main, 2026-11-10) | 2026-11-11 | PRIMARY (code) |
| github.com/siderolabs/image-factory | `c9c1f3946ddb1efbe8f221639b04dd39a60ba801` (main, 2026-11-03) | 2026-11-11 | PRIMARY (code, licence) |
| github.com/siderolabs/omni | `bcbb0eff06a64f1cf03d7fb69f5130574d45cc61` (main; LICENSE only) | 2026-11-11 | PRIMARY (licence) |
| github.com/siderolabs/docs (source of docs.siderolabs.com) | `9cddec20fd08e34d2228e734a8098a476060701a` (main, 2026-11-10) | 2026-11-11 | PRIMARY (official docs source) |
| github.com/siderolabs/sbc-raspberrypi | `9fa9252cca1a832a6154e3f431927302bb09d9bb` (tag v0.3.0, 2026-11-02) | 2026-11-11 (clone reused from W2) | PRIMARY (code) |
| github.com/siderolabs/sbc-jetson | `6468a58b8d1191869ec92dad7d31821c1c2a9de6` (v0.2.0) | reused from W2 [C-W2-038] | PRIMARY (code) |
| github.com/siderolabs/talos/releases/tag/v1.14.5 | release body via GitHub API | 2026-11-11 | PRIMARY |
| GitHub API: `repos/siderolabs/talos/commits?since=2025-11-11`, `/contributors` | n/a | 2026-11-11 | PRIMARY-METADATA |

Local shallow clones: `work/.lab/src/siderolabs_talos-v1.14.5`, `siderolabs_extensions`, `siderolabs_image-factory`, `siderolabs_docs` (outside the repo, read-only research copies).

## Web pages (saved text)

| URL | Accessed | Type | Saved file | sha256 |
|---|---|---|---|---|
| https://www.siderolabs.com/pricing/ | 2026-11-11 | PRIMARY (vendor pricing) | `siderolabs-pricing-2026-11-11.txt` | 987eb9d9faa7162d7a30707073e716dbdb53c6c91dadea23ba9be12a5a497dd4 |
| https://www.siderolabs.com/platform/talos-os-for-kubernetes/ | 2026-11-11 | PRIMARY (vendor product page) | `siderolabs-talos-platform-2026-11-11.txt` | 78c9351b41af48b59db9008185131a01d51c8ff2cdd090d5e68de48b6c9dbd7d |

## Issue trackers (failure reports)

| URL | Accessed | Type | Saved file | sha256 |
|---|---|---|---|---|
| https://github.com/siderolabs/talos/issues/14260 | 2026-11-11 | PRIMARY (issue) | `talos-issue-14260.txt` | 5c22237b0a1fe440d1fd7f0aade88ff337b4ecf613d90cfec7a3d412c010fb78 |
| https://github.com/siderolabs/talos/issues/14000 | 2026-11-11 | PRIMARY (issue) | `talos-issue-14000.txt` | b58b04c89678a01097d22dca633c999b21488936abe91153c74cfa3670e6212f |
| https://github.com/siderolabs/talos/issues/14061 | 2026-11-11 | PRIMARY (issue, open) | `talos-issue-14061.txt` | 6c3b9b10279be178e94e2de6682631b26d201cb4d97cd017af057fefb190775b |
| https://github.com/siderolabs/talos/issues/14002 | 2026-11-11 | PRIMARY (issue, fixed) | `talos-issue-14002.txt` | 628b2e12a50cc1eb49d679f405dcd8dd6072c57f0cda79cecd0f18368afbf62d |

## Reused from earlier workstreams (not re-fetched)

C-W2-038 and C-W4-064 (SBC overlays, Orin PR #23), C-W4-037 (AICR lists Talos), C-W4-038 and C-W4-073 (conformance listings), C-W18-045 (Talos's own kernel build), C-REF-DC-longevity-007/-009 (sbc-jetson v0.2.0; Pi 5 RP1 discussion), C-STEEL-jb-017 / C-REF-W7L-008 (pkgs PR #1518, nvgpu on mainline for Orin).
