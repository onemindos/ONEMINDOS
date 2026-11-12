<!-- SPDX-License-Identifier: Apache-2.0 -->
# Slop audit: documentation

**Date:** 2026-11-12 · **Scope:** `main` at `1c278f5` (after PR #39). **Lens:** claims in `docs/`, READMEs, the contract, the website (`site/`) and `CHANGELOG.md` that the code does not support; stale status rows; contradictions between docs; duplicated docs; broken internal links; inflated wording in technical docs.

> **In plain words.** The code moved faster than the docs. Thirteen pull requests merged on 2026-11-12 without the changelog, the status tracker or the website catching up, so several pages now say "in review" for code on `main` and "planned" for code that exists. The most serious problems: the website says the seed apps and the Hermes demo work today, but five of the nine apps fail their own security scan and the gateway refuses to install them. The website also says every change waits for your yes, but OS security updates install by themselves.

## How this was checked

Each claim was read against the code on `main`, not against other docs. Tools: `git log`, `git grep`, reading the source, a relative-link checker over every tracked Markdown file, and one live check: the gateway's `/openapi.json` was generated at `8c5267a` (before PR #38) and at `1c278f5`, then compared byte for byte. Nothing was installed.

**Severity.** **High:** a public page or the binding contract states something the code contradicts, or the merge record is broken. **Medium:** an internal doc that would send a builder the wrong way. **Low:** a small factual error.

## Summary

| Id | Sev | Where (first line) | Finding |
|---|---|---|---|
| DS-01 | High | `site/src/content/docs/docs/index.md:26` | "Works today" apps and the Hermes demo are blocked by the scan gate |
| DS-02 | High | `site/src/content/docs/docs/index.md:9` | "Every change waits for a human yes": OS security updates install without approval |
| DS-03 | High | `CHANGELOG.md:10` | 13 merged PRs missing; 7 merged branches listed as "not on `main`" |
| DS-04 | High | `docs/leap/STATUS.md:9` | Status tracker stale and contradicts its own rows |
| DS-05 | High | `site/src/pages/index.astro:18` | Website status tables stale ("in review" for merged code, "planned" for code on `main`) |
| DS-06 | Medium | `docs/leap/WORKSTREAMS.md:15` | Stream states and hotspot rules out of date; contradict PLUMBING.md |
| DS-07 | Medium | `docs/leap/dev/API.md:861` | Three different route-registration seams named across specs |
| DS-08 | Medium | `internal/storage/README.md:68` | Merged features are not wired, and their wiring recipes target code that no longer exists |
| DS-09 | Medium | `CHANGELOG.md:60` | "Takes a restic snapshot before every OS update": no shipped config has restic |
| DS-10 | Medium | `docs/leap/core/PLUMBING.md:122` | Event envelope documented (and built) to the superseded draft, not binding §12.8 |
| DS-11 | Medium | `docs/architecture/NETWORKING.md:508` | Contract §12.16 is claimed by networking but is Audit; docs cite superseded draft sections |
| DS-12 | Medium | `site/src/content/docs/docs/concepts/security.md:17` | "CI fails if a file uses a pin not listed": no such check exists |
| DS-13 | Medium | `site/src/pages/index.astro:211` | Present tense for features that are not shipped |
| DS-14 | Medium | `docs/umbrel2/README.md:9` | Lead claims wins its own table marks "None"; "today" column names merged branches |
| DS-15 | Medium | `docs/strategy/core-alignment.md:169` | "Today" blocks and cross-references say merged work is unmerged or empty |
| DS-16 | Medium | `README.md:7` | Root README: "no product code", wrong decision range, ADR-001 contradicts D-007 |
| DS-17 | Medium | `docs/security/HARDENING-BACKLOG.md:42` | Fixed H-25 still listed as an open P0; no status column |
| DS-18 | Low | `sdk/contracts/poc-v0.md:122` | Contract demo names `agent:hermes`; code uses `agent:hermes-agent` |
| DS-19 | Low | `site/src/content/docs/docs/getting-started/install.md:60` | Docs put the owner token on the command line, which `verify.sh` warns against |
| DS-20 | Low | `docs/leap/core/README.md:62` | Two broken internal links |
| DS-21 | Low | `CLAUDE.md:1` | `CLAUDE.md` and `AGENTS.md` are identical copies |
| DS-22 | Low | `apps/README.md:6` | App index lists 3 of 9 apps |
| DS-23 | Low | `docs/leap/DECISIONS-NEEDED.md:26` | F-10 (Hermes licence) still open after the app shipped with a confirmed licence |
| DS-24 | Low | `docs/leap/STATUS.md:183` | Dashboard screen count differs between docs (4, 5) and code (6 pages) |

---

## High

### DS-01 · "Works today" apps and the Hermes demo are blocked by the scan gate
**Claims**
- `site/src/content/docs/docs/index.md:26`: "Seed apps: Uptime Kuma, ntfy, Home Assistant | works today".
- `site/src/pages/index.astro:17`: the "Apps (9)" row is `works` and lists every app.
- `site/src/content/docs/docs/concepts/approvals-and-agents.md:58-63` and `sdk/contracts/poc-v0.md:122`: "the demo we hold ourselves to" is Hermes asking to install ntfy.
- `docs/leap/BACKLOG.md:23` (W2-PIPE acceptance: "Gate passes the 3 seed apps"), `:25` (W2-HERMES: "Passes app-gate"), `:26` (W2-SEEDS: "Each passes app-gate").

**Evidence.** `apps/*/scan.json` on `main`: `result: fail` for `uptime-kuma` (4 fixable critical CVEs), `home-assistant` (4), `hermes-agent` (1), `node-red` (3) and `mosquitto` (licence class `blocked`). The gateway refuses to approve an install whose scan is not `pass`: `core/onemind_core/scan.py:73-74`, `core/onemind_core/actions.py:234-236` (409 `stale_precondition`). The check is on whenever the executor is `kubernetes` (`core/onemind_core/app.py:81`). So on a real hub, 2 of the 3 "works today" seed apps cannot be installed, and neither can Hermes. Only ntfy, Vaultwarden, Actual Budget and Zigbee2MQTT pass. The app READMEs themselves are honest (for example `apps/hermes-agent/README.md:90`).

**Fix**
- Site: list as installable only apps whose `scan.result` is `pass`. Show the others as "blocked by scan" with the reason. Drive the landing-page Apps row from `scan.json` in `site/src/lib/apps.ts` instead of `apps.length`.
- Approvals page and contract §7: mark the Hermes demo "blocked until `hermes-agent` passes the gate (1 fixable critical CVE)", or bump the image digest first.
- STATUS: W2-PIPE, W2-HERMES and W2-SEEDS are "merged, acceptance not met", not `in-progress` or `todo` (see DS-04).

### DS-02 · "Every change waits for a human yes" is contradicted by the updater
**Claims.** `site/src/content/docs/docs/index.md:9` ("**every change waits for a human yes**"); `site/src/pages/index.astro:133-134` ("with every change waiting for your yes").

**Evidence.** `internal/update/README.md:11`: "the security channel installs automatically inside the maintenance window". `:70`: "Gateway approval (REC-DEC-13) is not wired … v0 follows BD-09's 'security auto by default'". The site's own `concepts/updates-and-rollback.md:24` says the same. The pages contradict each other.

**Fix.** Replace with: "Every change a person, app or AI agent asks for waits for your yes. OS security updates install automatically in your maintenance window unless you turn that off." Keep the separate sentence "AI never acts without a human yes" (`approvals-and-agents.md:9`), which is true.

### DS-03 · CHANGELOG is missing 13 merged PRs and lists merged work as unmerged
**Claim.** `CHANGELOG.md:6`: "**Every merge adds an entry here.**" `:10-20`: "Branches with work that is not on `main` yet".

**Evidence.** `git log --merges origin/main`: #23, #24, #25, #26, #28, #29, #30, #31, #32, #36, #37, #38 and #39 merged on 2026-11-12 and have no entry. Seven "Unreleased" rows are already merged: `feat/core-plumbing` (#38), `feat/gateway-agent-mcp` (#24), `feat/app-pipeline` (#25), `feat/deploy-v0` (#26), `feat/core-net` (#37), `feat/ui-leap` (as `feat/ui-leap-squash`, #29) and `feat/app-taxonomy` (#28).

**Fix.** Move the seven rows under `## 2026-11-12` with their PR links. Add entries for #23, #30, #31, #32, #36 and #39. For #31, #32 and #37, say "library code; not wired into `onemindd`/the gateway yet" (DS-08). Leave "Unreleased" empty.

### DS-04 · STATUS.md is stale and contradicts its own rows
**Claims and evidence**
- `docs/leap/STATUS.md:9`: "14 PRs merged … one PR open (OS security pipeline) … all leap build epics are still `todo`". Actually 37 PRs are merged and #14 merged.
- `:13-20` summary: done 1, in-review 2, in-progress 14, todo 163, parked 4. The rows below it say done 11, in-review 0, in-progress 7 (+3 UMB), todo 177, parked 5 (CORE-NET-15 at `:159` is missing from the summary).
- `:24-41` "Already merged" stops at #15.
- Merged but shown `in-progress`: W2-GW `:52` (#24), W2-PIPE `:53` (#25), W2-DEPLOY `:54` (#26), CORE-NET-P1 `:64` (#37), UI-LEAP `:65` (#29), MKT-TAXONOMY `:66` (#28), CORE-BACKUP-2 `:162` (#32), UMB-STOR-3 `:280` (#31).
- W2-HERMES `:55` and W2-SEEDS `:56` say `todo`, branch "(empty)". The apps are on `main` via #25 (`git log --diff-filter=A -- apps/hermes-agent/onemind.app.yaml`), but fail acceptance (DS-01).
- Contract rows C12-A `:74`, C12-H `:75`, C12-B/D/E/G `:133-136` and C12-C/F `:209-210` are `todo`. PR #39 merged §12 as binding and covers conventions and errors (§12.1-12.2), fabric (§12.11), deployments (§12.18), backups (§12.12), notifications (§12.14), automation (§12.17) and MCP (§12.19). C12-G is partial: `approve-options` is in §12, the iOS relay is not. C12-PLG stays `todo` (no `plugin.invoke` in §12).

**Fix.** Regenerate the page from `gh pr list --state all` and `git log --first-parent main`, as `:416` says. Derive the summary table from the rows, or delete it. Replace the "Already merged" table with a link to `CHANGELOG.md`; it duplicates the changelog and both drifted.

### DS-05 · Website status tables are stale
**Claims** (each says "in review", meaning "waiting in an open pull request", `index.md:14`, or "planned", meaning "no code yet", `index.md:16`)
- `site/src/pages/index.astro:18-20` and `site/src/content/docs/docs/index.md:27-29`: developer install, scan gate and MCP, app intake are "in review". They merged as #26, #24 and #25.
- `index.md:32`, `concepts/security.md:20-23`, `concepts/updates-and-rollback.md:37`: nightly security rebuilds "in review". Merged as #14.
- `index.astro:147`, `getting-started/install.md:4,12`, `getting-started/mac.md:4,12`, `concepts/fabric.md:14`: the install script is "in review and not yet on `main`".
- `concepts/approvals-and-agents.md:41`, `concepts/apps-and-trust-cards.md:26,28`, `reference/contract-api.md:88,102`, `reference/app-manifest.md:32`: agents, scan gate, catalog fields and the intake schema are "in review". All are on `main`.
- "Planned = no code yet", but code is on `main`: backups (`index.md:38`, `index.astro:23`; `internal/backup`, #32), fabric mesh and NATS leaf (`index.md:39`, `index.astro:24`; `internal/{mesh,leaf}`, `core/onemind_core/mesh.py`, #37), phone apps (`index.md:41`, `index.astro:26`, `concepts/fabric.md:23`; `mobile/`, #21).
- `concepts/backups.md:10`: "The one piece on `main` is the restic snapshot the update client takes". `internal/backup` (restic agent, schedule, verify, rewind) is on `main`.

**Fix.** Update every row. Add a state "on `main`, not wired" for backups, mesh and leaf (DS-08), so "planned" stays honest. The two tables are maintained by hand in two places (`site/README.md:28`), which is how they drifted. Move the rows to one data file (for example `site/src/data/status.ts`) that both `index.astro` and the docs page import.

## Medium

### DS-06 · WORKSTREAMS.md is out of date and contradicts PLUMBING.md
**Claims and evidence**
- `docs/leap/WORKSTREAMS.md:15-27` (§1 "Active streams"): "Committed here, not pushed", "3 commits, no PR", "Empty (behind `main`)", "**PR #14 open**", "no PR". Every listed branch has merged (#14, #16-#21, #24-#26).
- `:94-99` (§5 merge order) is S0's plan, now done.
- `:85`: `ledger.py`: "One migration file per epic, numbered when merged". `docs/leap/core/PLUMBING.md:91` says per-feature `FeatureSchema` steps "replace" that rule, but WORKSTREAMS was not updated.
- `:80`: after DEV-API-1 "each feature adds one line to `core/onemind_core/routes.py`". The code registers routers in `ROUTERS` in `core/onemind_core/app.py:44-51` (DS-07).
- `:81`: `cmd/onemindd/main.go` "one subcommand line per feature". The registry is now `cmd/onemindd/registry.go:9-15`.
- `:82`: "DEV-CLI-1 reduces `main.go` to `cli.Execute()`". `cmd/onemind/main.go:31` already calls `cli.Run`.

**Fix.** Replace §1 with the branches that are open today. Point §4's `app.py`, `ledger.py`, `onemindd` and `onemind` rows at PLUMBING.md §1 (`ROUTERS`, `FeatureSchema`, `registry.go`, `cli/root.go` `groups`).

### DS-07 · Three different route-registration seams across the specs
**Claims.** `docs/leap/dev/API.md:861,888`, `docs/leap/core/README.md:55` and `docs/leap/BACKLOG.md:42,194,290,298,309,316,389` say features add "one `routes.py` line". BACKLOG `:122,280,315` say "one line in `cmd/onemindd/main.go`".

**Evidence.** PR #38 built a different seam: `core/onemind_core/routers/<feature>.py` with `register(app, gw)`, listed in `ROUTERS` (`core/onemind_core/app.py:44`). `routes.py` does not exist. `onemindd` features go in `cmd/onemindd/registry.go`. DEV-API-1 is still `todo` (`STATUS.md:76`), although its "registration seam" has shipped.

**Fix.** Replace "one `routes.py` line" with "one `ROUTERS` line in `app.py` (PLUMBING.md §1)" and "one line in `cmd/onemindd/main.go`" with "`subcommands` or `optionalServices` in `cmd/onemindd/registry.go`". Rescope DEV-API-1 to the route inventory and conventions only.

### DS-08 · Merged features are not wired, and their wiring recipes target removed code
**Evidence (code)**
- `onemind mesh status` and `onemind storage …` exist as `meshCmd` and `storageCmd` in package `main` (`cmd/onemind/mesh.go:27`, `cmd/onemind/storage.go:38`). Only tests call them. The CLI dispatches through `cli.Run`, whose `groups` are `node`, `update` and `version` (`cmd/onemind/cli/root.go:32-36`). Typing either command prints usage and exits 2.
- `cmd/onemindd/registry.go:9-15`: `subcommands` has only `update`; `optionalServices` is empty. Nothing starts `internal/backup`, `internal/storage`, `internal/leaf` or `internal/mesh`.
- `core/onemind_core/{mesh,proxy,ca}.py` are imported by no other module. `/openapi.json` has no mesh or proxy route (checked).

**Doc claims that are now wrong**
- `internal/storage/README.md:68-75`: "add **one case** to the `switch` in `run`". That switch was removed by #38; `main.go` is now 32 lines.
- `cmd/onemind/mesh.go:25`: "Registered in main.go with one line (§18)". It is not registered.
- `docs/architecture/NETWORKING.md:592` ("already changed on this branch"), `:595` (mesh dispatch in `cmd/onemindd/main.go`) and `:600` (`case args[0] == "mesh"` in `cmd/onemind/main.go`).
- `internal/backup/README.md:55`: "mount `a.Handler(ctx)` … in `cmd/onemindd/main.go`". PLUMBING.md §7 says services go in `optionalServices`.

**Fix.** Rewrite each recipe to PLUMBING.md §6-7: move `meshCmd` and `storageCmd` into `cmd/onemind/cli/{mesh,storage}.go` as groups; add `"mesh": mesh.RunCLI` to `subcommands`; give `internal/backup` a `Service()`. Fix the `mesh.go:25` comment. Say "on `main`, not wired" in STATUS, CHANGELOG and the website until the registry lines land. Wiring them is code work: a follow-up, not part of this docs fix.

### DS-09 · "Takes a restic snapshot before every OS update": no shipped configuration has restic
**Claims.** `CHANGELOG.md:60`: "Before installing it takes a restic snapshot of `/data`". `site/.../concepts/updates-and-rollback.md:29`: "takes a backup snapshot first". `site/.../concepts/backups.md:10`: "the restic snapshot the update client takes before every OS update". `docs/leap/core/BACKUPS.md:27`: restic is pinned in `os/versions.lock.yaml` (`tools`) on `main`.

**Evidence.** `os/versions.lock.yaml` has no restic entry. Neither the image (`os/`) nor `deploy/install.sh` installs restic: `git grep restic -- os deploy` finds only the example `update.conf` and its README. `internal/backup/README.md:58` lists "add restic and rest-server to `os/versions.lock.yaml`" as still to do. `internal/update/README.md:49,51`: `require_snapshot` defaults to false for the security channel, so a security update installs with `snapshot: none` when restic is absent, which is every box today.

**Fix.** Say "takes a restic snapshot of `/data` when restic is configured (not yet in the image); security updates install without one". Correct `docs/leap/core/BACKUPS.md:27` to "not pinned yet; pins live in `internal/backup/pins.go`".

### DS-10 · Event envelope follows the superseded draft, not binding §12.8
**Claims.** `docs/leap/core/PLUMBING.md:129` ("the `onemind.event.v1` envelope of the contract §12.3 draft") and its example at `:122` (`severity="error"`). `core/onemind_core/events.py:8,29` implement exactly that.

**Evidence.** `sdk/contracts/poc-v0.md:450` (binding since #39) defines `onemind.event/v1` with `ts` and `subject`, and severity `info|warning|critical`. The draft (`docs/architecture/CONTRACT-12-DRAFT.md:3`) is marked SUPERSEDED. `events.py:127-131` emits `schema: "onemind.event.v1"`, `instance_id` and `resource`; `severity="error"` is not a §12.8 value.

**Fix.** Update PLUMBING.md §5 to say it emits the draft shape and must move to §12.8, and change the example to `severity="critical"`. Track the `events.py` change (or a contract PR keeping the draft names) as a follow-up, so that feature streams do not copy the draft shape.

### DS-11 · §12 numbering collision and citations of the superseded draft
**Evidence**
- `docs/architecture/NETWORKING.md:5,508,567,614`, `docs/leap/core/NETWORKING.md:28`, `docs/leap/BACKLOG.md:120` and `docs/leap/STATUS.md:154` reserve "contract §12.16" for networking. In the binding contract §12.16 is "Audit: read, verify, checkpoint" (`sdk/contracts/poc-v0.md:588`). The next free number is §12.22.
- These docs cite draft section numbers that differ from the binding contract: `internal/backup/README.md:4` (draft §12.5 → binding §12.12), `:56` (heartbeat "§12.11" → binding §12.10), `docs/architecture/BACKUPS.md:4`, `docs/umbrel2/files-backups.md:6` and `docs/architecture/NETWORKING.md:5` (draft §12.2-§12.4).
- `docs/leap/README.md:90` and `docs/leap/DECISIONS-NEEDED.md:86` say the draft is on branch `docs/core-architecture`, "not merged". It merged in #17 and was superseded by #39. `DECISIONS-NEEDED.md:84`, two lines above, already says "Settled 2026-11-12".

**Fix.** Renumber networking to §12.22 everywhere. Replace each draft citation with the binding section. Delete `DECISIONS-NEEDED.md:86` and reword `leap/README.md:90` to "superseded by contract §12 (#39); see §12.21 for the name choices".

### DS-12 · "CI fails if a file uses a pin that is not listed": no such check
**Claim.** `site/src/content/docs/docs/concepts/security.md:17`: "The Debian base, k3s, RAUC and every CI action are pinned … in `os/versions.lock.yaml`, and CI fails if a file uses a pin that is not listed there."

**Evidence.** The only CI pin check is `deploy/check-pins.py` (run by `.github/workflows/ci-deploy.yml:20-21`). Its docstring scopes it to "a k3s or Debian pin" in `deploy/`. No workflow or script compares the `uses: …@<sha>` lines with `github_actions` in the lock (`git grep -l versions.lock`). All action SHAs happen to be listed today (checked); nothing enforces it.

**Fix.** Either narrow the sentence to "CI checks the installer's k3s and Debian pins against the lock", or add an action-pin check (for example in `scripts/hygiene.py`) and keep the sentence.

### DS-13 · Present tense for features that are not shipped
**Claims and evidence**
- `site/src/pages/index.astro:211-214` ("Updates that prove themselves … Otherwise it rolls back by itself") is in the "What we do differently" grid with no status, while `:21-22` say "Being built". `docs/leap/README.md:20` sets the rule: "No update claim before metal gate G1". The gate has run only in QEMU.
- `index.astro:133-134` and `index.md:9` list "backups" among what OneMind does. `index.astro:228-229` and `site/.../blog/why-onemind.md:44`: "Your backups are plain restic repositories". Backups are not usable (DS-05, DS-08).
- `concepts/apps-and-trust-cards.md:35`: a new critical CVE "alerts owners who have it installed". There is no notification system (CORE-NOTIFY-1 is `todo`).
- `concepts/updates-and-rollback.md:47`: "Security-channel app updates install within your policy". There is no app-update path: the only action types are `app.install` and `app.remove` (`core/onemind_core/actions.py:31`).

**Fix.** Add the status tag to the "different" cards, or move them under a "What we are building" heading. Change the other sentences to the future tense with a link to the status table.

### DS-14 · umbrel2 summary: inflated lead and a stale "today" column
**Claims**
- `docs/umbrel2/README.md:9`: "OneMind matches the look and the features … It wins where you said it matters: every disk, app or account change is a plan you approve, backups count only after a restore has been checked, photos stay on the phone until a checked backup holds them, every person signs in with a passkey". The page's own table marks Files, Rewind, Photos server, accounts and passkeys "None" or planned (`:47-52`, `:43`).
- `:34` defines "Today" as "merged on `main` unless a branch is named", yet `:38,40,42,44,45,46,49,52,72` name `feat/ui-leap`, `feat/app-pipeline`, `feat/core-net`, `feat/gateway-agent-mcp`, `feat/onemindd-storage` and `feat/onemindd-backup`, all merged (#29, #25, #37, #24, #31, #32). `:40` says "3 seed apps"; there are 9.
- Same staleness: `docs/umbrel2/accounts.md:100`, `apps-deploy.md:129,140,172`, `machines.md:124`.

**Fix.** Lead: "OneMind plans to match the look and features … Today it has …". Refresh the column from `main`, marking merged-but-unwired items (DS-08) as such.

### DS-15 · core-alignment "Today" blocks and cross-references are stale
**Evidence.** In `docs/strategy/core-alignment.md`: `:144-148` (install.sh "in flight"), `:169-175` ("No design system yet (that branch is empty)"), `:199-206`, `:252-258` and `:309-315` ("in flight" items, all merged), `:282-285` (backups "None of it is built"; `internal/backup` merged), `:337-343`, `:395-398`, `:434-436` ("The `feat/mobile-shell` branch is empty"; `mobile/` merged in #21), and `:476-478` ("no public changelog"; `CHANGELOG.md` exists). Elsewhere: `docs/design/README.md:17`, `docs/design/PLUGIN-UI.md:3` and `ui/README.md:5` call core-alignment "not yet on `main`" (merged #17). `docs/architecture/README.md:62-64` says the listed branches are "still open". `docs/leap/dev/MCP.md:42` and `docs/leap/dev/API.md:88` cite the `gwmcp` worktree for code that is now `core/onemind_core/mcp.py` on `main`.

**Fix.** Refresh each "Today" block to "on `main`" with file paths. Drop the "not yet on `main`" parentheticals and the "In-flight work" section.

### DS-16 · Root README is out of date and contradicts the decision log
**Claims and evidence**
- `README.md:7`: "No product code lives here yet." The repo has `core/`, `cmd/`, `internal/`, `os/`, `apps/`, `dashboard/`, `ui/`, `mobile/`, `site/`, `deploy/` and `sdk/`. None of them is in the layout table (`:9-27`), and neither are `docs/leap/` and `CHANGELOG.md`.
- `:22`: "D-001…D-006". `docs/DECISIONS.md:46` has D-007 (the base OS), which `AGENTS.md:11-12` calls locked.
- `:18-19`: "ADR-001 wins on base OS, image and updates". ADR-001 is still "PROPOSED" (`docs/ADR-001-foundation.md:3`) and chooses **Rugix** (`:67,106`). D-007 and the code (`os/rauc/`) use **RAUC**.
- `:15`: "333-question research bank". `context/05-research-questions.md` runs to Q335.
- `:3`: sends research agents to start with RESEARCH-MISSION.md, which `AGENTS.md:19` marks done.

**Fix.** State that the repo holds the OS code and its docs. Add the code trees, `docs/leap/` and `CHANGELOG.md` to the layout table. "D-001…D-007". "D-007 wins on base OS and the update tool (RAUC); ADR-001 is superseded where they differ". 335 questions. Point agents at `AGENTS.md` first.

### DS-17 · A fixed hardening item is still listed as an open P0
**Evidence.** `docs/security/HARDENING-BACKLOG.md:42` and `:106-109`, H-25 (P0): the installer writes `ONEMIND_GATEWAY_URL` but the gateway reads `ONEMIND_PUBLIC_URL`. `deploy/install.sh:520-521` now writes `ONEMIND_PUBLIC_URL`. The backlog has no status column, so fixed items cannot be marked.

**Fix.** Add a "Status" column (open, done with commit). Mark H-25 done. Re-check the other P0 rows against `main` in the same pass.

## Low

### DS-18 · Contract demo names the wrong principal
`sdk/contracts/poc-v0.md:122`: "the audit chain records requester `agent:hermes`". The principal is `agent:<app-id>` = `agent:hermes-agent` (`core/onemind_core/actions.py:305`, `core/onemind_core/catalog.py:77`), as the site says (`approvals-and-agents.md:63`). **Fix:** a one-line contract PR changing it to `agent:hermes-agent`.

### DS-19 · Docs show the owner token on the command line; `verify.sh` scope overstated
`getting-started/install.md:59-60` and `getting-started/first-steps.md:39` run `verify.sh … --token "$ONEMIND_TOKEN"`. `deploy/verify/verify.sh:9-11` warns that `--token` "shows in `ps` and in shell history", and the script already reads `ONEMIND_TOKEN`. Also, `install.md:56` ("checks every item of the contract") and `sdk/contracts/poc-v0.md:105` ("everything in this contract") overstate the scope: `verify.sh:4` scopes it to §6 acceptance, and wave-2 features are SKIP. **Fix:** use `deploy/verify/verify.sh http://<hub>:8080` with the variable set, or `--token-file <file>` (under `sudo`, where the variable is not passed); say "checks the contract's §6 acceptance list".

### DS-20 · Two broken internal links
- `docs/leap/core/README.md:62`: `../README.md#shared-rules-every-spec-follows`. The heading is "5. Shared rules every spec follows", so the anchor is `#5-shared-rules-every-spec-follows`.
- `lab-kits/LT-PI5-01/CRITERIA-22.md:4`: `evidence/lab/rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md` resolves inside `lab-kits/`. The file is at `research-output/evidence/lab/rauc-1152/`. The file says it is a verbatim copy ("Do not edit"), so fix the copy step: rewrite the link to `../../research-output/evidence/lab/rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md`, or note the rewrite in its header.

(Site links such as `../updates-and-rollback/` are Starlight routes and resolve; they are not broken.)

### DS-21 · `CLAUDE.md` and `AGENTS.md` are identical copies
Both are 2,850-byte regular files with the same content (`cmp` reports no difference). One edit will make them disagree. `AGENTS.md:19` is already stale ("Output in `research-output/` on branch `research/ultracode-foundation`"; it merged in #1). **Fix:** keep `AGENTS.md` and make `CLAUDE.md` a single line that imports it (`@AGENTS.md`), or a symlink. Correct line 19.

### DS-22 · App index lists 3 of 9 apps
`apps/README.md:6-10` lists ntfy, Home Assistant and Uptime Kuma. `apps/` also has Hermes, Node-RED, Mosquitto, Vaultwarden, Actual Budget and Zigbee2MQTT. **Fix:** add the six rows with each app's scan result, or generate the table with `sdk/tools/app-readme`.

### DS-23 · F-10 still open after the app shipped
`docs/leap/DECISIONS-NEEDED.md:26`: F-10 "Hermes licence: confirm … Ship `apps/hermes-agent` only after it is confirmed". The app is on `main`, and the gate read `MIT`, class L1 (`apps/hermes-agent/README.md:11`). **Fix:** close F-10 with that evidence (or record that the app shipped before the founder confirmed). Drop the F-10 dependency from W2-HERMES (`docs/leap/BACKLOG.md:25`).

### DS-24 · Dashboard screen count differs everywhere
`CHANGELOG.md:81` and contract §5 say four screens. `docs/leap/STATUS.md:183` (CORE-DASH-2 "Move the 5 existing screens"), `docs/leap/WORKSTREAMS.md:50`, `docs/strategy/core-alignment.md:170` and `docs/strategy/umbrel-parity.md:12,305` say five. `dashboard/src/pages/` has six: Home, Nodes, Market, Approvals, SignIn and AppDetail (added in #24). CORE-DASH-2 scoped to "5" would miss AppDetail. **Fix:** name the pages instead of counting them.

---

## Checked and found accurate

These were verified against the code and need no change: heartbeat every 10 s (`internal/agent/agent.go:30`); stale after 30 s and offline after 120 s (`core/onemind_core/nodes.py:28-29`); `/mcp` exposes exactly `list_nodes`, `list_apps` and `request_action` (`core/onemind_core/mcp.py:56,71,86`); the only action types are `app.install` and `app.remove` (`docs/leap/README.md:20`); PLUMBING.md's claim that `/openapi.json` did not change in #38 (byte-identical at `8c5267a` and `1c278f5`); PLUMBING.md's `Gateway` fields (`core/onemind_core/context.py:41-57`); the candidate-list counts in `CHANGELOG.md:25-26` (1,199 = 849 + 59 + 73 + 218); the "no competitor gates on fresh health" claim, backed by `research-output/02-competitors/MATRIX.md:12,73-97`; the operating systems `install.sh` accepts (`deploy/install.sh:133-137`); the health gate logging the failing check (`os/gate/onemind-health-gate:86`); 12 P0 items in `docs/strategy/umbrel-parity.md` §5.

## Follow-ups outside the docs lens

These are code or CI issues found while checking claims. They are listed here, not fixed:
1. Wire the merged-but-idle features (DS-08): CLI groups for `mesh` and `storage`, `onemindd` registry lines for backup, mesh and leaf, and gateway routers for mesh, proxy and CA.
2. Align `core/onemind_core/events.py` with contract §12.8 (DS-10).
3. Add the CI check that the site claims exists (DS-12).
4. Bump the image digests of the five apps that fail their scan, so the seed set and the Hermes demo work on a real hub (DS-01).
5. Add restic to `os/versions.lock.yaml` and the image, so the pre-update snapshot can run (DS-09).
