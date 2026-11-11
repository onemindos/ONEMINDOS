# Sources: MATRIX (cross-competitor comparison)

**Tag:** MATRIX · **Accessed:** 2026-11-11 · **Used in:** `02-competitors/MATRIX.md` · **Claims:** `evidence/claims/MATRIX.csv` (C-MATRIX-001 … 015)

The matrix reuses every teardown's own claims (`evidence/claims/TD-*.csv`) and a few workstream and lab claims (`W2`, `W7`, `W8`, `W9`, `DEC`, `LAB-*`). Their sources are listed in each tag's own sources file. This file lists only the sources opened for the 15 new MATRIX claims.

| # | Source | Type | Accessed | Saved copy (sha256 in `MATRIX/SHA256SUMS`) | Claims |
|---|---|---|---|---|---|
| S1 | `home-assistant/core` tree at `d8a0dc698c8946b44e455d904000db563cfbf1ba`, `homeassistant/components/` (read with `git ls-tree` on a local partial clone) | PRIMARY (code) | 2026-11-11 | `MATRIX/protocol-grep-2026-11-11.txt` | C-MATRIX-001 |
| S2 | Case-insensitive protocol search over 11 pinned local clones (repo and SHA listed in the saved file). Nothing was built or run | PRIMARY (code) | 2026-11-11 | `MATRIX/protocol-grep-2026-11-11.txt` | C-MATRIX-002, -003, -004 |
| S3 | GitHub REST API `GET /repos/{owner}/{repo}/commits?since=2025-11-11T00:00:00Z&until=2026-11-11T00:00:00Z` (authenticated `gh api`, paginated) for `getumbrel/umbrel`, `home-assistant/operating-system`, `home-assistant/supervisor`, `IceWhaleTech/CasaOS`. Logins replaced by rank labels in the saved file | PRIMARY-METADATA | 2026-11-11 | `MATRIX/commit-author-concentration-2026-11-11.txt` | C-MATRIX-005 … 008 |
| S4 | `docs/REQUIREMENTS.md` L20–L21, L84–L86 at repo commit `53e55a5f` | PRIMARY (founder document) | 2026-11-11 | in repo | C-MATRIX-009 … 011 |
| S5 | `docs/DECISIONS.md` L7–L13 (D-001) at `53e55a5f` | PRIMARY (founder decision) | 2026-11-11 | in repo | C-MATRIX-012 |
| S6 | `context/01-proven-infrastructure-cluster.md` L117 at `53e55a5f` (reported state, not checked against the live cluster) | PRIMARY (founder report) | 2026-11-11 | in repo | C-MATRIX-013 |
| S7 | CasaOS core repos (CasaOS, AppManagement, UserService, Gateway, Common, UI) at pinned SHAs, searched for backup and AI words; `kairos-io/kairos-docs@b1bf8bed` `docs/advanced/partition_encryption.md` L118–L124 | PRIMARY (code, docs) | 2026-11-11 | `MATRIX/casaos-kairos-checks-2026-11-11.txt` | C-MATRIX-014, -015 |

**Limits.** A grep finds words, not features. Zero matches means "no code in these trees mentions these protocols", not "a user can never run such software in a container". Commit counts measure activity on the default branch, not headcount; bots were excluded by login name. No Wayback capture applies to S1–S3 (git objects and API responses), so the saved text plus hash is the archive.
