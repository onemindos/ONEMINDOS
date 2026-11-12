# Sources: TD-home-assistant-os (Home Assistant OS Tier A teardown)

Used in: `research-output/02-competitors/home-assistant-os.md`. Claims: `evidence/claims/TD-home-assistant-os.csv` (C-TD-home-assistant-os-001 to 048).

**Archiving note.** The Wayback "save" request was refused in this environment, because the sandbox counts it as a public upload. Instead, load-bearing issue and PR pages are saved as text snapshots, with sha256 hashes, in `evidence/sources/TD-home-assistant-os/` (see `SHA256SUMS` there). Snapshots keep only the title, state, dates, the opening post and the quoted maintainer comment. Reporter handles, system-information HTML and any network details were removed. Source code needs no archive, because every code citation is pinned to a commit SHA.

## Code (pinned)

| Source | Pin | Accessed | Type | Archive |
|---|---|---|---|---|
| github.com/home-assistant/operating-system | tag `18.5` → commit `fc301f556647b53281e853b9ce7f44915b3c7b14` (annotated tag object `3b161a56…`), released 2026-11-06 | 2026-11-10 | PRIMARY (code) | SHA-pinned |
| github.com/home-assistant/buildroot (submodule of the above) | `5c344b3789e3f6d620cf11ffab60e522a875cc79` | 2026-11-10 | PRIMARY (code, pointer only) | SHA-pinned |
| github.com/home-assistant/supervisor | tag `2026.11.0` → `c1c6f0a754c0656eb1af189f11009f1cfc4b3e28`, released 2026-11-06 | 2026-11-10 | PRIMARY (code) | SHA-pinned |
| github.com/home-assistant-libs/securetar (formerly pvizeli/securetar) | tag `2026.10.0` → `224df990ebea9a9f99ee72c53564fbed710eb46b`, released 2026-10-09 | 2026-11-10 | PRIMARY (code) | SHA-pinned |
| github.com/home-assistant/core (sparse: `auth/`, `components/mcp_server`, `components/backup`) | tag `2026.11.1` → `d8a0dc698c8946b44e455d904000db563cfbf1ba`, released 2026-11-09 | 2026-11-10 | PRIMARY (code) | SHA-pinned |
| github.com/home-assistant/contributors.home-assistant.io (sparse: `docs/apps`, `docs/os`) | `1fb72833546780ab815de3967dd9054d8c91ceba` | 2026-11-10 | PRIMARY (official docs source) | SHA-pinned |
| github.com/home-assistant/home-assistant.io (`backups.markdown`, SecureTar v3 blog post) | `6f38b5b48d737b455deeeeed2e82be53b0cee294` | 2026-11-10 | PRIMARY (official docs/blog source) | SHA-pinned; blog copy saved as `TD-home-assistant-os/ha-blog-securetar-v3@6f38b5b4.md` (the reporter's name is redacted) |

## Issue trackers and PRs (failure reports, decisions)

| URL | Accessed | Type | Archive (saved text, sha256) |
|---|---|---|---|
| https://github.com/home-assistant/operating-system/issues/4632 | 2026-11-10 | PRIMARY (issue) | `haos-issue-4632.txt` 173dc043df548dbb46843c5cf10c39a50ba5db830039507de36542ad109de068 |
| https://github.com/home-assistant/operating-system/issues/4845 | 2026-11-10 | PRIMARY (issue + maintainer reply) | `haos-issue-4845.txt` d3d869fd335c2cedc7b092e12d72b8f17e6e23377802128e23c30bc0bc145373 |
| https://github.com/home-assistant/operating-system/issues/5031 | 2026-11-10 | PRIMARY (issue + maintainer reply) | `haos-issue-5031.txt` 3a49fec79c42d683884cb30b0f1d462dc38d3db526303c29815c62b0b852135d |
| https://github.com/home-assistant/operating-system/issues/4785 | 2026-11-10 | PRIMARY (issue, open) | `haos-issue-4785.txt` 81ca7a3e2222be8063454c1766f6d4d555266b633b07d4a4a016bb79c516ce08 |
| https://github.com/home-assistant/supervisor/issues/7034 | 2026-11-10 | PRIMARY (issue + maintainer reply) | `supervisor-issue-7034.txt` 481626c67b112bc9684a0b0d76479ffece0c956ee213fad10d4c7183c98e2ca6 |
| https://github.com/home-assistant/operating-system/pull/4757 | 2026-11-10 | PRIMARY (PR, CA rotation) | `haos-pr-4757.txt` 23b1c11a3ee8d490f1b88e9774c308b3fc0eea70f1d0e437344a9e42fc5dc821 |
| https://github.com/home-assistant/operating-system/pull/5053 | 2026-11-10 | PRIMARY (PR, cosign) | `haos-pr-5053.txt` 744ab7b9b4f5b61a3030df3d0acdc0ed307204a8f49102b996b024ba3dd90ed5 |
| https://github.com/home-assistant/operating-system/releases/tag/18.5 | 2026-11-10 | PRIMARY-METADATA (GitHub API release date) | Not archived (metadata only) |
| https://github.com/home-assistant/supervisor/releases/tag/2026.11.0 | 2026-11-10 | PRIMARY-METADATA | Not archived (metadata only) |

## Web pages

| URL | Accessed | Type | Archive |
|---|---|---|---|
| https://www.openhomefoundation.org/structure/ | 2026-11-10 | PRIMARY (organisation page) | Archive blocked (see the note above); re-fetch before relying on it in 17-business |
| https://www.home-assistant.io/installation/ | 2026-11-10 | PRIMARY (official docs) | Archive blocked; the page source is in home-assistant.io@6f38b5b4 `source/installation/` |
| https://github.com/trailofbits/publications/blob/master/reviews/2026-03-open-home-foundation-securetar-v3-securityreview.pdf | Not opened | Referenced by the HA blog only | Not cited as a source. The audit facts come from the HA blog post |

## Prior in-repo verification reused (not re-cited as new claims)

| File | Used for |
|---|---|
| research/platform/verify-updates-rollback-backups-security.md §1–§2 | HAOS doc-level facts (SSH on port 22222, backup agents), umbrelOS comparison rows |
| context/03-repo-findings-index.md §1 (HAOS rows 105–114) | Baseline cross-check. All rows were re-checked against code here |
| research/competitors/landscape.md §1.4 | HA Cloud/Link pricing (not re-verified in this teardown, marked as such in the text) |
