# Sources: PLAN180 (`20-PLAN-180-DAYS.md`)

All accessed 2026-11-11. The plan mostly re-uses claims already in the ledger (cited inline by their own IDs). The five new rows `C-PLAN180-001…005` are **re-checks of gate-trigger facts on the day the plan was written**, because a gate is only as good as the status it starts from. API responses were saved as text in `PLAN180/` (fields extracted, nothing masked was needed: no credentials, account IDs or personal data in these responses) with hashes in `PLAN180/SHA256SUMS`. New Wayback captures are blocked in this environment (ARCHIVE-GAP for all five; the saved text plus sha256 stands in).

| # | Source | Type | Pin / capture | Used for |
|---|---|---|---|---|
| S1 | `git ls-remote --tags https://github.com/rauc/rauc` | PRIMARY | `PLAN180/rauc-tags.txt` (v1.15.2 → 4fb7c798) | C-PLAN180-001: RAUC pin at Day 1 |
| S2 | GitHub API: `repos/fedora-iot/greenboot-rs/issues/219`, `commits/main`, `releases` — https://github.com/fedora-iot/greenboot-rs/issues/219 | PRIMARY | `PLAN180/greenboot-rs-219.txt` (main 6efc3c10) | C-PLAN180-002: S1 → bootc trigger status |
| S3 | GitHub API: `repos/coreos/bootupd/pulls/935` — https://github.com/coreos/bootupd/pull/935 | PRIMARY | `PLAN180/bootupd-pr-935.txt` (head fdf4b312) | C-PLAN180-003: Pi 5 bootc prerequisite status |
| S4 | Launchpad API: https://api.launchpad.net/1.0/bugs/2170238/bug_tasks | PRIMARY | `PLAN180/launchpad-2170238.txt` | C-PLAN180-004: S1 → Ubuntu trigger status |
| S5 | GitHub API: `repos/k3s-io/k3s/releases` — https://github.com/k3s-io/k3s/releases | PRIMARY | `PLAN180/k3s-releases.txt` | C-PLAN180-005: k3s pins for LT-VM-04 |
| S6 | This repo: `RESEARCH-MISSION.md` §6; `context/02-prior-planning.md` §16–§18 (M0–M6, 30/60/90, A01–A24); `docs/DECISIONS.md`; `docs/REQUIREMENTS.md`; `research-output/` 00, 01, 04, 05, 08, 09, 11, 16, 22, 23, 24, 26, 27, 28; `evidence/decision-critical.md`; `evidence/lifecycle-cost-2036.md`; `evidence/critic/pass-2.md` | Internal | working tree on `research/ultracode-foundation`, 2026-11-11 | The decisions, tests and assumptions the plan schedules |

**Note on an unresolved reference.** 03 §3 names "bootupd PR #935 **and issue #82**" as Pi 5 prerequisites. `coreos/bootupd` #82 is a 2020 dependency-bump pull request, not a Pi 5 item, so the reference is probably to another repository. This plan cites only PR #935; the W2 owner should correct the #82 reference.
