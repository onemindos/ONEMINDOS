<!-- SPDX-License-Identifier: Apache-2.0 -->
# Slop audit, pass 2: documentation

**Date:** 2026-11-12 · **Audited:** `origin/main` at `ad81f84` · **Item:** Wave G #4 (`QUALITY-SLOP-2`) · **Pass 1:** [slop-audit-docs.md](slop-audit-docs.md) (found at `1c278f5`)
**Lens:** claims in `docs/`, READMEs, `site/` and `CHANGELOG.md` that the code does not support; broken links; stale status. Code and drift: [code](slop-audit-2-code.md), [drift](slop-audit-2-drift.md).

> **Explain it like I am the founder**
> Pass 1's fixes held. The new problem is the same one in a new place: **about twenty more pull requests merged (#33 to #74) and the status pages did not follow.** The website still said "in review" for passkeys, the sandbox, notifications and the desktop app, which are on `main`. The tracker still showed 45 epics as "in progress (local)" for branches that merged. And the apps page listed 9 of the 19 apps. I fixed the text that is mine to fix (separate `fix(docs):` commits, listed below). The CHANGELOG backfill is left alone on purpose: a branch is rewriting it (`docs/changelog-since-23`).

## How this was checked

| Check | Result |
|---|---|
| Relative-link checker over every tracked `.md` outside `research-output/` and `context/` (script, links in code spans and fences skipped) | 103 hits: 5 real (3 in `docs/learning`, 2 historical quotes in the pass-1 audit), 98 are Starlight site routes like `../../guides/apps/` that resolve at build time (false positives; `site.yml` builds the site) |
| Merged PRs (`git log origin/main --merges`) against CHANGELOG, STATUS, NEXT-WAVE, CONTINUE, site status rows | see findings |
| Every site status row (`docs/index.md`, `index.astro`, `reference/cli.md`) against `cmd/onemind/cli/root.go`, `cmd/onemindd/registry.go`, `sdk/openapi/onemind-v1.json`, `dashboard/src/App*` | see DS2-01 |
| `apps/` directory against `apps/README.md`; `scan.json` presence per app | see DS2-04, DS2-07 |
| READMEs of `core/`, `cmd/`, `internal/`, `deploy/` against the code | see DS2-06, DS2-08 |

## Findings

Owner rule: `orchestrator` = file in `dashboard/ ui/ docs/ apps/ site/`; `Hermes` = file in `core/ cmd/ internal/ deploy/ os/ sdk/ mobile/ desktop/` or an open PR. **Fixed here** = high or medium, owner orchestrator, not in `dashboard/` or `ui/`.

| Id | Sev | Owner | Where | Finding | Status |
|---|---|---|---|---|---|
| DS2-01 | High | orchestrator | `site/src/content/docs/docs/index.md:20-52`, `site/src/pages/index.astro:20-27`, `site/src/content/docs/docs/concepts/security.md:26-36`, `guides/apps.md:119`, `reference/cli.md` | Site says "in review" for identity (#41), sandbox (#40), desktop (#51), notifications (#44); lists 4 dashboard screens (v2 has 7, #73); says "New Home screen … the dashboard does not use them yet"; CLI page lists 3 commands (the CLI registers `login`, `status`, `nodes`, `apps`, `actions`, `audit`, `mcp`, `mesh`, `storage`, `update`); "storage not yet part of the CLI" and "backup agent … not switched on" are out of date (`cmd/onemind/cli/storage.go`, `cmd/onemindd/registry.go:17`) | **fixed** (commits "site status rows match main", "backup agent runs only when its settings file exists") |
| DS2-02 | High | orchestrator | `docs/leap/STATUS.md` rows (45), `docs/leap/NEXT-WAVE.md:9-32`, `docs/leap/CONTINUE.md:36-46` | 45 epic rows read `in-progress … (local)` or `review` for branches that merged (#34 #40 #41 #44 #48 #51 #54 #61 #63 #67 #68 #69 #70 #71 #73 #74); the summary counts were hand-stale; NEXT-WAVE and CONTINUE list merged items as open | **fixed** (whole-PR rows now `done`; epic rows say `in-progress (merged in #N; rest unverified)` so nothing is called finished that was not checked; counts recounted) |
| DS2-03 | Medium | orchestrator | `docs/learning/09:6`, `11:114-123`, `12:78`, `README.md:24-28` | 3 broken links (`mcp.py` is now `mcp/`; `cmd/onemind/mesh.go` and `storage.go` moved under `cli/`); "not wired in" claims that the code disproves; "in review" for #40 #41 #44 | **fixed** ("learning lessons 09-14 match main") |
| DS2-04 | Medium | orchestrator | `apps/README.md:7-17` | Table lists 9 of 19 apps; the 10 from market batch 1 (#61) are missing, and the intro says the table shows each scan result | **fixed** (10 rows added, with "no scan record") |
| DS2-05 | High | orchestrator | `CHANGELOG.md:10-34, 36-135` | "Unreleased" lists #61, #73, #74, `spike/machines`, `docs/threat-model-refresh`, `docs/fabric-epics`, `docs/slop-audit` as "not on main yet" (all merged). No dated entry exists for any PR from #24 to #74 (pass 1 DS-03, still open). The `#61` row also says four apps "pass" the gate; the repo has no `scan.json` for them (DS2-07) | **open, deliberately**: branch `docs/changelog-since-23` rewrites this file (97 files); editing it here would only create a conflict. Orchestrator: land that branch, then move the rows above under their merge dates |
| DS2-06 | Medium | Hermes | `deploy/README.md:138-139`, `deploy/verify/verify.sh:19` | Both still say wave-2 checks (`/mcp`, §11.4) **SKIP** and that `--strict` turns SKIP into FAIL; pass 1 (CS-07) made those failures, so the text is wrong | open: `deploy/` |
| DS2-07 | Medium | orchestrator | `apps/{grafana,ollama,searxng,adguard-home}/` (no `scan.json`), `apps/*/README.md` ("No scan yet") vs CHANGELOG `#61` row | The `#61` description says Grafana, Ollama, SearXNG and AdGuard Home "pass" the gate; the manifests say `tier: community` but there is no `scan.json`, so the gateway refuses them (`core/onemind_core/actions.py:258`) | partly fixed: `apps/README.md` now says so. Still open: either commit the passing `scan.json` files from the CI run (CI, `apps-rescan.yml`), or word the CHANGELOG row as "passed in CI run N, record not committed" (goes with DS2-05) |
| DS2-08 | Medium | Hermes | `core/README.md:231, 234` | "no … resources or prompts" (MCP `resources/list` and `resources/read` exist: `core/onemind_core/mcp/server.py:12`), "no SSE stream" (`routers/events.py:27` serves `/v1/events`), and "`tier: blocked` … does not by itself refuse an install" (it does since #67: `catalog.py`, `actions.py`) | open: `core/` |
| DS2-09 | Low | orchestrator | `docs/quality/slop-audit-drift.md:110, 138` | Two links to files that no longer exist (`dashboard/src/components/AppTrust.tsx`, `core/onemind_core/mcp.py`) | not fixed: they quote the code as it was on 2026-11-12 morning; the audit documents a past state |

### What I changed (all separate `fix(docs):` commits, each with evidence in its message)

1. **Site status rows** (DS2-01): `docs/index.md`, `index.astro`, `concepts/security.md`, `guides/apps.md`, `reference/cli.md`. New wording names what is still open (HTTPS is not on, so passkey sign-in works on `localhost` or behind TLS only: `docs/security/THREAT-MODEL.md` line 103; the host firewall for apps; no backup settings file is installed; Matrix and Telegram channels), so the site does not swing from under-claiming to over-claiming.
2. **Backup wording** (DS2-01): the agent runs only if `/data/onemind/backup/agent.json` exists (`internal/backup/service.go:31-33`); nothing creates it.
3. **STATUS, NEXT-WAVE, CONTINUE** (DS2-02): see table above. STATUS counts are recomputed from the rows.
4. **Learning lessons 09, 11, 12 and the learning README** (DS2-03).
5. **apps/README.md** (DS2-04, DS2-07).

### Not changed on purpose

- **Founder decisions D-001 to D-007** were not touched, and no file was found that conflicts with them (Debian 13 base, RAUC A/B, k3s; the site still says Debian 13).
- `CHANGELOG.md` backfill (DS2-05): in flight on another branch.
- `dashboard/`, `ui/`: another worker is editing them.

## Checked and clean

- `docs/security/THREAT-MODEL.md` and `HARDENING-BACKLOG.md` (edition 2) say "built, not wired" only for `ca.py`, `mesh.py`, `proxy.py`, which is still true (code audit CS2-04).
- `docs/architecture/NETWORKING.md:560` (CORE-NET-8 "not registered yet") is still true.
- `docs/testing/TEST-REGISTER.md` TR-104 correctly says NATS has no auth or TLS on a box.
- `site/src/content/docs/docs/concepts/security.md` no longer claims a CI check for pins that does not exist (pass 1 DS-12 held).
- Site internal links: 98 route-style links are Starlight routes that the checker cannot resolve; I did not verify each one (UNVERIFIED), `site.yml` builds the site in CI.
