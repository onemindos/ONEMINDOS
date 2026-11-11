# Sources: TD-flagged (founder-flagged repos, RS-5)

Used in: `research-output/02-competitors/flagged-repos.md`. Claims: `evidence/claims/TD-flagged.csv` (C-TD-flagged-001 to 034).

**Safety note.** All three repos were cloned shallow and partial (`--depth 1 --filter=blob:none --no-checkout`, git hooks disabled) into `.lab/src/` outside the repo. Only text files (READMEs, licences, policy files, TypeScript/Rust source) were checked out and read. Nothing was installed, built or run: no `npm`, `npx`, `cargo`, `install.sh` or test scripts. No VM was needed because no code was executed.

**Archiving note.** Source code needs no archive because every code citation is pinned to a commit SHA. Volatile web data (GitHub metadata, commit activity, npm downloads, one issue) is saved as text in `evidence/sources/TD-flagged/` with hashes in `SHA256SUMS`. The issue snapshot omits the reporter's handle. Wayback "save" requests were not attempted (a sibling workstream found the sandbox refuses them as a public upload).

## Code (pinned)

| Source | Pin | Accessed | Type | Archive |
|---|---|---|---|---|
| github.com/morluto/rea | `e2585aa7ce31c37866ca46991ec656fdffaa3b90` (HEAD of `main`, 2026-11-10; latest release `rea-agents-6.8.0`, 2026-10-25) | 2026-11-10 | PRIMARY (code, docs) | SHA-pinned |
| github.com/storytold/craft-anything | `4f61975f25d96c71635bacb07619b5b5bd0a0bd1` (HEAD of `main`, 2026-11-10; latest release `v0.6.0`, 2026-11-09) | 2026-11-10 | PRIMARY (code, docs) | SHA-pinned |
| github.com/qybaihe/bla | `3e53a1e5b63f1267cc94560a3411d0bb7775313d` (HEAD of `main`, 2026-11-10; package 3.2.4, release `bla-agents-3.2.4`, 2026-11-10) | 2026-11-10 | PRIMARY (code, docs) | SHA-pinned |
| github.com/getumbrel/umbrel `LICENSE.md` | `c43beed964074d08865d648ca9ac3359826a14ff` | 2026-11-10 | PRIMARY (licence text) | SHA-pinned |
| github.com/gitleaks/gitleaks `config/gitleaks.toml` | `5f6ec56cfa6f8c67648d863582c7ae2f206d5c1c` | 2026-11-10 | PRIMARY (code) | SHA-pinned |

Files read in each repo:
- **rea:** `README.md`, `DISCLAIMER.md`, `SECURITY.md`, `LICENSE`, `install.sh`, `package.json`, `.gitmodules`, `THIRD_PARTY_NOTICES.md`.
- **craft-anything:** `README.md`, `NOTICE`, `LICENSE-MIT`, `LICENSE-APACHE`, `Cargo.toml`, `deny.toml`, `docs/licences.md`, `docs/STATUS.md`, `docs/tool-ids.md`.
- **bla:** `README.md`, `DISCLAIMER.md`, `STATE.md`, `package.json`, `src/core/llm-directives.ts`, `src/core/release-exposure.ts`, `src/core/debug-posture.ts`, `src/engine/plaintext-secret-lint.ts`, `src/shields/deception/prompt-completion-poison.ts`, `src/shields/deception/canary-honeypot.ts`, `src/setup/setup.ts` (lines 375-411 and 621-640), file list of `src/`.

## Metadata and web

| Source | Accessed | Type | Archive |
|---|---|---|---|
| GitHub REST `/repos/{morluto/rea, storytold/craft-anything, qybaihe/bla}` | 2026-11-10 | PRIMARY-METADATA | `TD-flagged/github-repo-metadata.json` |
| GitHub REST `/repos/{r}/commits?since=2026-10-11` (paginated) | 2026-11-10 | PRIMARY-METADATA | `TD-flagged/activity-2026-10-11_to_2026-11-10.txt` |
| GitHub REST `/repos/{r}/stargazers` and GraphQL `stargazers` | 2026-11-10 | UNVERIFIED (blocked: 404 / totalCount 0, also for a control repo) | noted in the activity file |
| GitHub REST `/repos/{home-assistant/operating-system, beclab/Olares}` (licence field) | 2026-11-10 | PRIMARY-METADATA | none (stable field) |
| https://api.npmjs.org/downloads/point/{last-week,last-month}/{rea-agents,bla-agents} | 2026-11-10 | PRIMARY-METADATA | `TD-flagged/npm-*.txt` |
| https://registry.npmjs.org/{rea-agents,bla-agents} (attestations, install scripts) | 2026-11-10 | PRIMARY-METADATA | `TD-flagged/npm-*.txt` |
| https://github.com/morluto/rea/issues/9317 "[Design] Add bypass for BLA" | 2026-11-10 | PRIMARY | `TD-flagged/rea-issue-9317.txt` |
| https://www.law.cornell.edu/uscode/text/17/1201 (17 U.S.C. §1201(f)) | 2026-11-10 | PRIMARY (statute, via LII) | not archived (stable statute text) |
| https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0024 (Directive 2009/24/EC, Art. 5, 6, 8) | 2026-11-10 | PRIMARY (EUR-Lex) | not archived (official journal text) |
| https://polyformproject.org/licenses/noncommercial/1.0.0/ | 2026-11-10 | not used (HTTP 404); the same licence text was read from umbrel's `LICENSE.md` at a pinned SHA | — |

## Sibling ledgers relied on (not re-verified here)

| Claim | Ledger |
|---|---|
| HAOS signs RAUC bundles and cosign-signs release checksums | C-TD-home-assistant-os-012, -015 |
| umbrelOS 2.1 signed-release trust chain; 2.0.1 runs an unsigned update script | C-TD-umbrelos-010, -013 |
| umbrelOS licence FAQ bars commercial forks | C-TD-umbrelos-045 |
| Olares release integrity is an MD5 sum, no signature | C-TD-olares-004, -006 |

## Prior internal sources

| Source | Accessed | Type |
|---|---|---|
| research/competitors/flagged-repos.md (phase-1 review) | 2026-11-10 | Internal report; facts re-checked above |
| context/03-repo-findings-index.md (REPOS rows, C-38, open items) | 2026-11-10 | Internal index |
| context/05-research-questions.md (Q297) | 2026-11-10 | Internal question bank |
| docs/DECISIONS.md (D-001), docs/ADR-001-foundation.md (D3, security) | 2026-11-10 | Internal decisions |
