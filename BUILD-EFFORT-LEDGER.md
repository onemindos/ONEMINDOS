# OneMind OS build effort ledger

How much AI work has gone into building OneMind OS: every Claude Code **dynamic workflow** run (one run = one orchestrated job of many agents), with its agents, time, tokens and purpose. Keep adding to it so the full-scale effort stays on record.

- **Source:** the Dynamic workflows list in the Claude desktop app (screenshots taken 2026-11-27). The list header said *167 completed*; **164 rows** were readable, so about 3 runs are missing at the screenshot edges.
- **Purpose:** taken from each workflow script's own `meta.description`, shortened.
- **Rounding:** the app rounds tokens (`1.5m` = 1.5 million), so totals are close, not exact.
- **Time is per run, not calendar time.** Many runs ran at the same time, so summed hours are *agent-orchestration hours*, not days on the clock.

## Totals

| What | Amount |
|---|---|
| Workflow runs recorded | **164** (134 different workflows) |
| Finished OK / failed or stopped | 143 / 21 |
| Agents started | **2,060** |
| Workflow run time, summed | **283h 13m** (about 11.8 days of non-stop running) |
| Tokens | **185.5 million** |
| Average run | 12.6 agents, 1h 43m, 1.1M tokens |
| Biggest run by tokens | `landing-crew-2`: 5.7m tokens |
| Longest run | `sprint-wave-4`: 8h2m4s |
| Most agents in one run | `landing-crew-2`: 98 agents |

## By kind of work

| Kind | Runs | Agents | Run time | Tokens | Share of tokens |
|---|--:|--:|--:|--:|--:|
| Building features (waves) | 56 | 1,062 | 183h 01m | 93.3M | 50% |
| Research, design, audits and planning | 46 | 459 | 18h 14m | 51.0M | 28% |
| Merging and landing | 25 | 397 | 50h 12m | 25.8M | 14% |
| Fix rounds on PRs | 27 | 95 | 24h 34m | 10.7M | 6% |
| CI, runners and machines | 10 | 47 | 7h 10m | 4.7M | 3% |

## Every workflow and what it was for

Runs of the same workflow are added together. Sorted by tokens.

| Workflow | Kind | Runs (failed) | Agents | Run time | Tokens | Purpose |
|---|---|--:|--:|--:|--:|---|
| `sprint-wave-4` | Building features (waves) | 12 | 218 | 42h 48m | 19.7M | Hardware-ready sprint wave 4: must-fix work from the lab tests, security re-review, plugin security review and UI review, plus merge unblockers; draft PRs, independent review,… |
| `v1-wave-runner` | Building features (waves) | 9 (8) | 181 | 22h 38m | 7.6M | Run one wave group of the 1.0 plan: build the wave's issues as PRs, independent Opus review, fix rounds, merge into release/next. |
| `landing-crew-2` | Merging and landing | 1 (1) | 98 | 6h 33m | 5.7M | Looping crew v2: each round finds approved PRs that cannot land (conflict, red required check, visual diff), fixes or judges them in parallel, then watches main until a merge… |
| `ui-gaps-build` | Building features (waves) | 1 | 29 | 2h 10m | 5.6M | Build the UI/CLI gaps from the 1:1 parity audit (issue #1232): security account screens, permissions screens, verification table + owner writer screens, missing-area screens (2… |
| `sprint-wave-1` | Building features (waves) | 1 | 56 | 2h 27m | 5.2M | Hardware-ready sprint wave 1: fix 12 open PRs to green, Opus security review of plugin stacks, build 11 issues as draft PRs; independent review + up to 2 fix rounds each |
| `sprint-wave-3` | Building features (waves) | 1 | 56 | 1h 39m | 4.7M | Hardware-ready sprint wave 3: hardware kits + acceptance harness (draft PRs), sequential R530 lab test cycle on throwaway hubs, and an adversarially verified security re-review… |
| `wave2-settings-flathub` | Building features (waves) | 1 | 25 | 6h 31m | 4.6M | Wave 2: time zone, SSH keys, static IP/DNS, storage housekeeping, keyboard, firewall allow rules, Flathub; each image+API+UI+CLI; stacked on the PRs they need; smaller test… |
| `ready-now-wave` | Building features (waves) | 2 (1) | 37 | 5h 12m | 4.5M | Build every 1.0 issue that had no unmet dependency ("ready now") as PRs, with independent review and fix rounds. |
| `supersede-and-design` | Research, design, audits and planning | 1 | 26 | 0h 54m | 4.5M | Beat the competitors: a sourced scorecard per competitor from the foundation report and the screenshots, then four design studios each build a complete brand and desktop system… |
| `overlap-and-done-audit` | Research, design, audits and planning | 2 | 54 | 0h 26m | 4.4M | Check every open release/next issue live: is it already done, are its dependencies really in, and is anybody doing the same work twice. Fixes stale labels; reports overlaps… |
| `review-the-rest` | Merging and landing | 1 | 63 | 3h 07m | 4.0M | Independent review of the 23 open PRs that are in no train yet, so they can join the release branch: review, one fix round if needed, re-review; approved PRs are appended to… |
| `design-addendum-round` | Research, design, audits and planning | 1 | 16 | 1h 19m | 3.7M | Design addendum in the founder's chosen look: fix the ten consistency errors, add the shared realtime and notification components, then four teams add screens (realtime and… |
| `security-and-settings-wave1` | Building features (waves) | 1 | 22 | 4h 24m | 3.5M | Security (NATS machine-local sign-in, recovery dead ends) + settings that do not depend on unmerged PRs (hostname, log viewer, firewall view, OS rollback); smaller test set;… |
| `landing-crew` | Merging and landing | 1 (1) | 60 | 0h 32m | 3.4M | Looping crew that keeps approved PRs landable: each round finds approved PRs that conflict with main or have a red required check, fixes them in parallel, then waits for merges… |
| `wave3-gateway-nats-apps` | Building features (waves) | 1 | 22 | 6h 06m | 3.3M | Overnight wave 3: gateway safety PRs 1, 3-4, 5-6, NATS N0+N3, custom apps from Git (#252), work port part 2; smaller test set; Opus review; no merges |
| `step2-debian-bones` | Building features (waves) | 1 | 18 | 4h 35m | 2.9M | Build the Step 2 Debian-bones PRs in parallel (Sonnet builds, Opus reviews), tested on big-1/R530, no merges |
| `finish-audit` | Research, design, audits and planning | 1 | 28 | 0h 14m | 2.9M | Deep review for the finish phase: digest the foundation report, audit the desktop, brand, plugins, API/SDK/CLI/MCP wiring, power-user depth, AI stack, image security and speed,… |
| `premium-design-directions` | Research, design, audits and planning | 1 | 20 | 0h 56m | 2.9M | Design a premium OneMind OS look: three complete visual directions rendered as real screenshots of the real dashboard, critiqued against umbrelOS 2.0 and for accessibility,… |
| `foundation-flow` | Building features (waves) | 1 (1) | 38 | 2h 21m | 2.7M | Foundation layers 2-4 (10 shared-contract issues) as a dependency flow instead of layer barriers: each issue starts as soon as the issues it depends on are merged into… |
| `map-intel-xr-connectors` | Research, design, audits and planning | 2 (1) | 23 | 0h 20m | 2.7M | Founder direction: a native OneMind map (MapLibre and/or Cesium, OpenStreetMap, offline), open-source intelligence and feeds as plug-and-play layers, NATS as an engine in the… |
| `landing-train-1` | Merging and landing | 2 (1) | 31 | 6h 56m | 2.6M | Landing train: combine 80 independently approved PRs into eight cars (merge, resolve conflicts, test on the build worker), review every hand-resolved merge, join the cars into… |
| `sprint-wave-5a` | Building features (waves) | 1 | 26 | 0h 47m | 2.6M | Wave 5 early starts: dashboard screen registry (conflict-proofing) first, then seven big screens stacked on it, plus three independent backend builds; independent review and up… |
| `foundation-wave` | Building features (waves) | 1 (1) | 16 | 7h 39m | 2.4M | Build the foundation that unblocks Codex's 95 issues: 14 shared-contract issues in four dependency layers on release/next (subject tree, built-in descriptor, manifest v1,… |
| `premium-polish` | Building features (waves) | 1 | 23 | 1h 43m | 2.3M | Shared premium polish for the OneMind desktop (colour-independent): four focused PRs stacked on the screen registry, each with before/after screenshots, a code review and a… |
| `fast-s3-gateway-engine` | Building features (waves) | 1 | 8 | 4h 24m | 2.1M | Section 3 gateway series: lane A engine PRs 7-10 then 12-13 stacked; lane B verification levels PR 11 + UI controls PR 15 + sign-in keys screen PR 17; Opus builders + Opus… |
| `step2b-step3-linux-native` | Building features (waves) | 1 | 14 | 6h 10m | 2.1M | Box-care + desktop-hardware Debian features in 4 PRs (Sonnet builds, Opus reviews, one fix round); no merges |
| `behind-prs-prep` | Merging and landing | 1 | 16 | 1h 53m | 2.1M | Bring the 40 built-but-unmerged PRs up to date with release/next, test them, Opus review; no merges |
| `fast-s4-nats-and-ceremony` | Building features (waves) | 1 | 8 | 4h 33m | 1.8M | Section 4 NATS series stacked on #1165, plus the Step 5 key-ceremony path: YubiKey signing in the ceremony script, rehearsal, and an end-to-end signed-update test (TUF + RAUC)… |
| `fast-s3-recovery` | Building features (waves) | 1 | 7 | 5h 21m | 1.8M | Section 3 recovery set: lane A 25a kit + 25b data-first + 25c in-person recovery; lane B 25d contacts + 25e assisted recovery with waits + 25f legacy + 25g vault spike; Opus… |
| `lane-6-finish` | Building features (waves) | 1 | 23 | 3h 40m | 1.7M | Finish lane 6 (Atlas desktop shell, handed back by Codex Astra-3) before the pause: hand in and gate #840 window manager and #842 fix-a-problem, gate the Atlas design tokens PR… |
| `os-completeness-realtime-notifications` | Research, design, audits and planning | 1 | 18 | 0h 09m | 1.7M | What OneMind OS still needs to stand beside the operating systems people use today: a feature and page inventory against macOS, Windows, ChromeOS, GNOME/KDE and the phone… |
| `design-final-round` | Fix rounds on PRs | 1 | 9 | 1h 01m | 1.7M | The founder picked the design. One more round: build the final OneMind OS design from his picks (Atlas base with the asset map, Sovereign colours, today's logo, Console… |
| `post-step2-fixes-and-cli` | Building features (waves) | 1 | 12 | 7h 15m | 1.6M | After Step 2: fix #1099 security/should-fix items, storage follow-up (LUKS token for factory reset + layout paths), fix release/next unit reds, and the CLI polish PR; smaller… |
| `onboarding-motion` | Research, design, audits and planning | 1 | 9 | 0h 59m | 1.6M | Founder ask: an animated, more dynamic onboarding for OneMind OS. Two scouts (what first run does today; how today's operating systems animate onboarding and the rules for… |
| `land810-reds` | Merging and landing | 1 | 18 | 1h 51m | 1.5M | Fix the 7 red workflows on landing PR #810 (e2e golden path, xr spatial, cli-packages build paths, onemind CLI plugin test, perf-smoke budget, api-fuzz 500 as agent, restore… |
| `audit-step1-wiring` | Research, design, audits and planning | 1 | 12 | 0h 44m | 1.5M | Audit Step 1: W1 power controls reach the box, W2 front ends for existing backends, W3/W4 CLI for existing routes; Opus review; no merges |
| `repo-coverage-audit` | Research, design, audits and planning | 1 | 18 | 0h 09m | 1.4M | Audit every open issue, all 15 project boards, the milestone and the plan requirements against the sprint: what is covered, what is done and can close, what is missing before… |
| `bigger-plan-wave-a` | Research, design, audits and planning | 1 | 10 | 1h 29m | 1.3M | Core integration round (gateway 5-6, logs, work part 2), Dell install kit, NATS N2 groundwork (job.pub at join + job envelope v2), Kanidm decisions (1.12.1 bump, passkeys-only… |
| `leftover-fixes` | Fix rounds on PRs | 1 | 12 | 4h 40m | 1.3M | Second fix round for PRs still at "changes" (video+console #1114, firewall view, gateway PRs 3-4 and 5-6, work part 2), then rebuild P-11 keyboard on the fixed #1114; Opus… |
| `backstage-front-door` | Research, design, audits and planning | 1 | 11 | 0h 25m | 1.3M | Detailed plan to replace the onemind-portal Backstage deployment (the front door) with OneMind OS: inventory every capability, map to OneMind, design the front door, migration… |
| `stable-live-step1` | Building features (waves) | 1 | 13 | 5h 22m | 1.2M | Step 1 of the stable-live sprint: fix first-boot reds, land #1013, get a green release/next image, boot it as R530 VM 501 and test it as a new user, then land on main |
| `final-stretch-plan` | Research, design, audits and planning | 1 | 10 | 0h 21m | 1.2M | Founder ask: plan the final stretch. Review the whole private CONTEXT folder for anything missed, review tonight's ideas and every open issue, pick an ambitious finish line… |
| `iot-lora-edge-and-app-sdk` | Research, design, audits and planning | 1 | 10 | 0h 14m | 1.2M | Founder direction: OneMind OS IoT native and Meshtastic and MeshCore (LoRa) native, an edge image for devices that run models and send telemetry back, tested on real hardware;… |
| `native-clients-and-sync` | Research, design, audits and planning | 1 | 13 | 0h 11m | 1.2M | Founder ask: native OneMind clients on every operating system (Finder sidebar and true file sync like Dropbox on Mac, the same on Windows and Linux, iPhone and Android with… |
| `app-suite-and-desktop-apps` | Research, design, audits and planning | 1 | 12 | 0h 12m | 1.2M | Founder asks: a first-party OneMind app suite that replaces daily apps (built in, cannot be removed, can be switched off), desktop apps in a window (Obsidian, Hermes desktop,… |
| `repo-clutter-audit` | Research, design, audits and planning | 1 | 15 | 0h 17m | 1.2M | Find what the repo no longer needs (dead code, unused files, stale docs, leftover binaries, unused dependencies, obsolete scripts, stale branches and PRs, mergeable local… |
| `sprint-wave-2` | Building features (waves) | 1 | 36 | 2h 58m | 1.2M | Hardware-ready sprint wave 2: 16 builds (network, AI, clients/CI, OS, apps) with heavy tests on the R530 build worker; independent review + up to 2 fix rounds; draft PRs |
| `post810-prep-cache-1155-1156` | Building features (waves) | 1 | 5 | 2h 53m | 1.1M | CI/build-machine Docker cache PR (Opus builder) and final Opus rounds for #1155 power-cut recovery and #1156 static IP; Opus reviews; no merges |
| `behind-prs-fixes` | Fix rounds on PRs | 1 | 14 | 0h 27m | 1.1M | Fix the 10 prepped PRs Opus sent back (plus #374 body), then Opus re-review; no merges |
| `surface-structure-audit` | Research, design, audits and planning | 1 | 11 | 0h 06m | 1.1M | Founder ask: make sure everything is structured for every product surface: Core, Dashboard, Desktop, SDK, Mobile, CLI, MCP, API, OS image, Federation. One auditor per surface… |
| `release-next` | Merging and landing | 1 | 9 | 4h 59m | 1.1M | Fast merge pipeline: one release branch that takes every reviewed PR (train 1, train 1b, the plugin train, train 3 and the rest), judged by our own machines in parallel instead… |
| `first-party-apps-doctrine` | Research, design, audits and planning | 1 | 9 | 0h 14m | 1.1M | Founder direction: OneMind's moat is built-in first-party apps that come wired (like Apple's Notes, News, iCloud), including a native open-source intelligence map. Four scouts… |
| `codex-pr-gate` | Merging and landing | 6 | 16 | 1h 40m | 1.0M | Gate for Codex draft PRs on release/next: independent Claude review of each; approved ones are merged into release/next, the others get a review:changes label with the list of… |
| `fast-s1-s2-followups-ci` | Building features (waves) | 1 | 7 | 4h 01m | 1.0M | Sections 1+2: CI speed (core shards, Secure Boot step), flaky harness #1159/#1150, review follow-ups, the 6 unlanded landing commits; Opus/Sonnet builders, Opus reviews; no merges |
| `premium-polish-round-2` | Building features (waves) | 1 | 11 | 1h 49m | 987k | Premium polish round 2: fix the design and code blockers on the three polish PRs (with new after-screenshots a design critic looks at), and add an optional display name to the… |
| `opus-builders-1126-powercut` | Fix rounds on PRs | 1 | 6 | 2h 44m | 962k | Opus builders (founder rule 2026-11-25) continue the NATS sign-in fix #1126 and the power-cut k3s fix from their branches; separate Opus review; no merges |
| `overnight-chain` | Merging and landing | 1 (1) | 20 | 6h 39m | 955k | Overnight: finish Step 1 (wait for the image, VM 501 test, full build, land #810), then the big merge train into release/next in batches with image checks, then a second… |
| `ci-gates-faster` | CI, runners and machines | 1 | 7 | 0h 43m | 881k | Founder-approved CI gate changes: api-fuzz fixed seed on PRs/landings + random nightly that files issues; ci-apps only changed apps on PRs, all apps nightly and on landings;… |
| `lora-messenger-plan` | Research, design, audits and planning | 2 | 6 | 0h 35m | 866k | Plan the 1.0 LoRa messenger (Android app plus hub) on the founder's own radios: check the existing LoRa issues and code live, verify protocol licences and firmware facts from… |
| `w0-land-rescue-secure` | Building features (waves) | 1 | 18 | 3h 03m | 863k | Wave W0 of the 1.0 "Atlas" plan: land #621 on its own; make release/next correct (merge the train branch, re-verify the 7 Codex PRs including their own CI, fix the core-3 test,… |
| `nats-fabric-agents-omni` | Research, design, audits and planning | 1 | 7 | 0h 12m | 836k | Founder direction: a deep study of NATS as the native fabric (the hub as the internal server, every added machine a leaf node, telemetry that survives disconnection, automatic… |
| `clients-wave` | Building features (waves) | 1 | 30 | 0h 09m | 836k | Client apps everywhere: desktop (macOS/Windows/Linux) release + auto-update + parity, Android signed dev builds, iPhone ready-to-ship pipeline, mobile parity with the… |
| `ci-second-runner` | CI, runners and machines | 1 | 7 | 2h 54m | 830k | Double the self-hosted CI pool without new machines: a second, fully separate GitHub runner on each droplet. Pilot on one droplet, independent safety check, roll out to the… |
| `design-chooser-data` | Research, design, audits and planning | 1 | 10 | 0h 02m | 799k | Gather verified data for the founder's design chooser: per studio the palette with computed contrast, an "editable and accessible" table checked against the renders, the same… |
| `gateway-permissions-design` | Research, design, audits and planning | 1 | 6 | 0h 17m | 783k | Review the capability gateway, compare native/standard authorization tools, design permission modes and standing approvals (read-only, design doc) |
| `codex-leftovers` | Merging and landing | 2 (2) | 33 | 5h 17m | 761k | Finish the work handed back by the last Codex chat (Astra-1): make release/next green, finish and gate its open PRs, then the built-but-waiting branches, the Atlas design stack… |
| `image-explainer-facts` | Research, design, audits and planning | 1 | 7 | 0h 12m | 750k | Verified facts for the founder's education page: how the OneMind OS image works (from the repo), fully open versus firmware-included with competitors and sources, and read-only… |
| `add-build-workers` | CI, runners and machines | 1 | 8 | 0h 42m | 748k | Turn four idle DigitalOcean CI-runner droplets into build and test workers (fleet-7 to fleet-10): stop each runner when idle, resize to 8 CPU / 16 GB, install the worker setup,… |
| `where-we-stand-os` | Research, design, audits and planning | 1 | 6 | 0h 05m | 744k | Read-only survey of OneMind OS: what landed, build and boot health, open PRs, core OS features, file system, machines |
| `os-integration-round` | Building features (waves) | 1 | 2 | 5h 38m | 735k | Opus integrator combines the ~17 skipped OS PRs on one integration branch (central first-boot ID assignment, btrfs layout updates, combined-test fixes), full tests + image;… |
| `stable-live-speedup` | Building features (waves) | 1 | 5 | 1h 02m | 723k | Run the release/next image + boot battery on om-big-1 alongside CI, and research which Debian-native tools should form the OS bones for Step 2 |
| `physical-bridge` | Research, design, audits and planning | 1 | 7 | 0h 11m | 715k | Founder direction: OneMind OS as the bridge between the physical and digital world: a hardware protocol AI can use ("the MCP of hardware"), how robots connect (see what a robot… |
| `beyond-umbrelos-ux` | Research, design, audits and planning | 1 | 6 | 0h 05m | 710k | Benchmark OneMind UI screen-by-screen against the 65 umbrelOS captures plus Olares/Home Assistant OS patterns, and define where OneMind goes beyond them |
| `stable-live-step1b` | Building features (waves) | 1 | 10 | 0h 19m | 675k | Second pass on Step 1 of the stable-live sprint: finish first-boot fixes and the green release/next image test. |
| `onemind-mcp-two-doors` | Research, design, audits and planning | 1 | 5 | 0h 07m | 604k | Founder idea: a OneMind OS MCP that outside AIs can use to deploy apps and manage the box (umbrelOS 2.0 has an example), and an internal MCP for agents inside the OS. Two… |
| `resolve-stacked-conflicts` | Merging and landing | 1 | 10 | 0h 35m | 591k | Five approved PRs that were stacked on the screen registry now conflict with main: merge main into each, resolve the conflicts keeping both sides, re-run the dashboard checks,… |
| `github-tracking` | Research, design, audits and planning | 1 | 3 | 1h 04m | 575k | Make GitHub the single place to see the 1.0 "Atlas" status: a milestone, the project board kept in step, a status issue with the live standing, and one sync script the check-in… |
| `gw-levels-final` | Fix rounds on PRs | 1 | 2 | 2h 22m | 566k | Final Opus round on verification levels #1184/#1186 (grace latch L2 bypass, warning text, N-1 grace option b per founder) + independent Opus re-review; no merge |
| `repo-tidy-and-ui-parity` | Research, design, audits and planning | 1 | 5 | 0h 11m | 519k | Small, light: audit the repo layout and the UI/backend parity (read-only), then one tidy PR (README, CLAUDE.md, AGENTS.md, stale pointers, proven-dead bloat) and one UI parity… |
| `nats-role-research` | Research, design, audits and planning | 1 | 4 | 0h 14m | 519k | How NATS works in OneMind today, what NATS can do (security, JetStream, auth callout, leafnodes), and how to leverage it with the gateway (read-only) |
| `fix-621-ci` | Fix rounds on PRs | 1 | 6 | 1h 55m | 517k | Landing PR #621 (69 reviewed PRs) failed five CI job groups. One fixer per failing group in parallel on the train branch, then one integrator merges the fixes and pushes so CI… |
| `founder-calls-2026-11-25` | Research, design, audits and planning | 1 | 6 | 0h 35m | 516k | Rework #953 into a Market app, port #798 pieces onto the #1018 work engine, point the apps-rescan bot at release/next; Opus review; no merges |
| `logo-loading-screens` | Research, design, audits and planning | 1 | 4 | 0h 29m | 516k | Founder ask: loading screens with the logo, used only when a wait really needs one. A scout finds every real wait in the OS and the rules for when to show a loader; a designer… |
| `native-features-audit` | Research, design, audits and planning | 1 | 5 | 0h 10m | 513k | Audit Linux/Debian-native OS features: in the image? API? dashboard UI? CLI? -> one gap matrix and PR plan (read-only) |
| `wave2-second-round` | Fix rounds on PRs | 1 | 6 | 0h 11m | 490k | Second fix round for wave-2 PRs still at changes: Flathub, SSH keys (P-06), firewall allow rules (P-09b); Opus re-review; no merges |
| `issue-factory` | Research, design, audits and planning | 1 | 3 | 0h 54m | 486k | Turn tonight's designed build slices into tracked, agent-ready GitHub issues on the Roadmap board, split into lanes so Codex and Claude swarms can build in parallel onto the… |
| `three-asks-specs` | Research, design, audits and planning | 1 | 6 | 0h 02m | 483k | Turn three founder asks into build-ready specs with evidence: virtual machines for other operating systems, browsers as apps (for people and for AI agents), and plug-and-play… |
| `add-ci-capacity` | CI, runners and machines | 1 | 3 | 1h 27m | 481k | Add GitHub CI runner capacity right now without new machines: more runner slots on the idle Mac, and one CI runner on each build-worker droplet next to its test runs. Then an… |
| `ci-unblockers-noon` | CI, runners and machines | 1 | 7 | 0h 26m | 474k | Four merge unblockers: independent review of the smoke time-limit PR #569, land the screen registry #535 (update, fix red checks, judge the visual diff), fix the WebKit… |
| `v1-cut-board` | Research, design, audits and planning | 1 | 7 | 0h 07m | 463k | Sort the 235 open 1.0 issues into "Last run" or "Later (1.1)" with a one-line reason each, and show it on the GitHub project board for the founder. |
| `landing-train-2-plugins` | Merging and landing | 1 | 6 | 2h 21m | 423k | Landing train 2: the plugin platform stack (eight independently approved PRs in two chains) combined onto main, tested, the combination security-reviewed, and one landing PR… |
| `final-push-capacity` | CI, runners and machines | 1 | 5 | 0h 16m | 401k | Final push: the droplet limit is now 100. Add 6 big build workers (32 dedicated CPUs each) for the agents' test runs and 10 CI runner droplets, set up exactly like the existing… |
| `xr-priority-track` | Research, design, audits and planning | 1 | 4 | 0h 13m | 400k | Founder decision: XR, VR and AR are a priority track in OneMind OS 1.0 ("huge market, massive attention, do not leave it behind"). He owns an older Meta Quest Pro. Research… |
| `project-boards-refresh` | Research, design, audits and planning | 1 | 3 | 2h 08m | 373k | Founder ask: GitHub project boards that track everything being built and planned. The organisation already has 15 private boards (Roadmap #2 with 167 items and 13 area boards):… |
| `post810-train-1` | Merging and landing | 1 | 5 | 3h 42m | 367k | Merge train into release/next (now decoupled from the landing): batch docs (#1158 #1160), batch core (#1166 + node-taint fix, #1163, #1165, #1181, #1164), batch OS (#1157,… |
| `finish-241-snapshots` | Building features (waves) | 1 | 5 | 2h 53m | 358k | Finish issue #241 (scheduled snapshots and restore a previous version) on Codex rescue PR #833 in the Claude lane: fix the systemd unit path, add the Files restore and the… |
| `verification-finish` | Fix rounds on PRs | 1 | 3 | 0h 14m | 348k | Founder go: fix the owner role check in #1246/#1265 (+ Opus re-review), and the final independent Opus review of verification levels #1184-#1186 that never ran; no merges |
| `opus-escalate-p06` | Fix rounds on PRs | 1 | 2 | 2h 00m | 340k | Auto-escalation (founder rule): Opus builder takes P-06 SSH keys (#1146) after 2 Sonnet rounds; Opus re-review; no merge |
| `land-fuzz-clean` | Merging and landing | 1 | 1 | 2h 52m | 327k | Make api-fuzz clean on the landing branch for good: fix every current finding, loop schemathesis locally over many seeds until clean; Opus builder + Opus review + merge into… |
| `fix-powercut-k3s` | Fix rounds on PRs | 1 (1) | 1 | 3h 14m | 311k | Fix: a power cut in the first minute after first boot leaves k3s broken for good (unsynced /data writes); auto-recover; Opus review; no merge |
| `land-reds-2` | Merging and landing | 1 | 4 | 0h 41m | 291k | Fix the new red checks on landing PR #1192: ui-quality (webkit Atlas paints + visual), ci-deploy e2e-systemd (--dry-run changed a file); Opus fix + review, merge into… |
| `docs-reapprove-merge-and-nats-fix` | Merging and landing | 1 | 3 | 0h 19m | 288k | Re-approve and merge the 6 decision/founder-note PRs skipped for post-approval nit commits; second fix round for NATS N0/N3 (#1129, #1135) |
| `polish-567-round-4` | Fix rounds on PRs | 1 | 3 | 0h 12m | 276k | Last round on PR #567 (Home polish): the floating jobs pill must never cover content (sits on the dock row on desktop, directly above the dock with reserved space on phones)… |
| `fix-621-visual-and-fuzz` | Fix rounds on PRs | 1 | 2 | 0h 05m | 268k | Landing PR #621: two remaining failures besides the end-to-end test. A visual judge looks at every screenshot difference (all browsers) and only then accepts or fixes; a fixer… |
| `tips-app-design` | Research, design, audits and planning | 1 | 3 | 0h 07m | 266k | Founder idea: a built-in Tips app that shows people how to use OneMind OS (like Apple's Tips), which the founder can manage himself with his own videos and lessons. One scout,… |
| `registry-535-visual-fix` | Fix rounds on PRs | 1 | 3 | 0h 34m | 258k | Fix round on PR #535 (screen registry): the visual judge found the floating jobs pill missing and pages 24 px taller; find the cause, fix it so every screen matches main, then… |
| `fix-621-smoke-and-fuzz2` | Fix rounds on PRs | 1 | 2 | 1h 06m | 248k | Landing PR #621: the image boot smoke test failed, and the API fuzz job failed again after its first fix. One fixer each, in parallel, on the train branch. |
| `final-stretch-revise` | Research, design, audits and planning | 1 | 2 | 0h 08m | 245k | Apply the skeptic's fixes to the 1.0 "Atlas" finish line and build plan: must and stretch tiers, real ordering, two workflows at a time, the key ceremony early, smaller… |
| `polish-567-round-3` | Fix rounds on PRs | 1 | 3 | 0h 06m | 240k | Final small round on PR #567 (Home and shell polish): the phone greeting must show the whole name, a neutral disabled button, the avatar initial; merge the fixed… |
| `ci-image-tiers` | CI, runners and machines | 1 | 3 | 0h 03m | 238k | Follow-up to #1109: every change builds tier 1+2 (x86, installer, arm64, proxmox, vm); tier 3 (clouds, vm-do, rpi5) only on manual full=true; Opus review; merge |
| `wave-e-early-ci-reliability` | Building features (waves) | 1 | 12 | 1h 51m | 228k | Early start of 1.0 wave E: CI and test reliability (flaky checks, cheap checks on drafts, the Ubuntu hedge, forced-bad update soak) picked live from issues with no unmet… |
| `docs-reapprove-merge-v2` | Merging and landing | 1 | 2 | 0h 06m | 224k | Founder-authorized: Opus re-reviews the 6 decision/founder-note PRs (full re-review for #1100 #1121 #1122 #1084), then merges the approved ones into release/next |
| `fleet-capacity` | CI, runners and machines | 1 | 2 | 0h 21m | 215k | The Mac is overloaded (load over 100) because test shards and builders fall back to it. Turn some idle CI droplets into extra build and test machines, move the fleet test and… |
| `tidy-parity-fix` | Fix rounds on PRs | 1 | 2 | 0h 06m | 215k | Fix the two Opus must-fixes on #1233 (informational CI wording) and #1231 (wrong notification row + method caveat, re-check must-have gaps by SDK method), then one Opus… |
| `ci-image-slim` | CI, runners and machines | 1 | 3 | 0h 03m | 215k | Slim image.yml on PRs and release/next to x86 + proxmox + vm (+ x86 battery); full matrix nightly, on main and on demand; Opus review; merge |
| `ux-and-cluster-review` | Research, design, audits and planning | 1 | 18 | 0h 07m | 213k | UI/UX sprint review (backend↔frontend parity + experience review from real screenshots) and a plan to replace the DigitalOcean omos-cloud cluster with OneMind OS |
| `review-gh-shim` | CI, runners and machines | 1 | 2 | 0h 10m | 195k | Two independent reviewers try to break a small gh wrapper script before it is switched on for every build agent. |
| `fix-621-e2e` | Fix rounds on PRs | 1 | 2 | 0h 49m | 192k | Landing PR #621: the end-to-end golden-path job still fails after the first fix round. Diagnose from the newest run, fix on the train branch, push, keep auto-merge on. |
| `fix-1102-cli` | Fix rounds on PRs | 1 | 2 | 0h 04m | 188k | Second fix round for PR #1102 (gateway CLI part 1) and Opus re-review; no merge |
| `dell-kit-final` | Fix rounds on PRs | 1 | 2 | 0h 08m | 186k | Final Opus fix round for #1164 Dell install kit (btrfs counter PASS only on positive evidence) + Opus re-review; no merge |
| `wave-p-android` | Building features (waves) | 1 | 37 | 1h 50m | 186k | Wave P of 1.0 "Atlas": a working Android app for full daily use and control from the phone. Audit and plan, build in two rounds (independent items first), independent review… |
| `fix-1102-cli-r3` | Fix rounds on PRs | 1 | 2 | 0h 05m | 174k | Third fix round for PR #1102 and Opus re-review; no merge |
| `fix-1098-work-port` | Fix rounds on PRs | 1 | 2 | 0h 22m | 171k | Fix the Opus findings on PR #1098 (work port) and re-review; no merge |
| `wave-b1-shell-and-codex-settings` | Building features (waves) | 1 (1) | 1 | 0h 08m | 166k | Early start of 1.0 wave B1: file the Atlas shell issues (Claude) and the Settings issues (handed to Codex), then build the shell pieces that have no unmet dependency, with… |
| `wave-a-b2-early` | Building features (waves) | 1 | 20 | 3h 44m | 160k | Start the parts of 1.0 waves A (foundation rest) and B2 (services) that have no unmet dependency: pick them from live GitHub data, build each in its own worktree, independent… |
| `lane-4-finish` | Building features (waves) | 1 | 11 | 2h 38m | 157k | Finish lane 4 (handed back by Codex Astra-2) before the pause: machine console #688 (PR #862), Market licence classes #173 (reopen PR #867) then quality tiers #174, browser… |
| `ceremony-guide-final-fix` | Fix rounds on PRs | 1 | 2 | 0h 04m | 157k | One focused fix on PR #580 (the guided signing-key ceremony script): the signing step must work when two holders follow the instructions with real USB sticks; then an… |
| `image-scan-final-fix` | Fix rounds on PRs | 1 | 2 | 0h 28m | 154k | One focused fix on PR #587 (the on-box image scanner): a failed scan job must return at once, not hold the scan lock until the timeout; then an independent security re-review |
| `codex-pr-gate-v2` | Merging and landing | 1 | 2 | 0h 01m | 137k | Gate for Codex draft PRs on release/next: independent Claude review of each; approved ones are merged into release/next, the others get a review:changes label with the list of… |
| `webkit-flake-fix-round` | Fix rounds on PRs | 1 | 2 | 0h 02m | 116k | One fix round on PR #570 (WebKit ResizeObserver flake): apply the first measurement synchronously, then an independent re-review that also checks the WebKit job in CI |
| `fix-1126-nats` | Fix rounds on PRs | 1 (1) | 1 | 1h 15m | 100k | Third round for the NATS machine-local sign-in PR #1126 (security): unit sandbox score + services card + image re-run; Opus re-review; no merge |
| `b1-issues-for-codex` | Research, design, audits and planning | 1 | 1 | 0h 00m | 95k | File the 1.0 wave B1 shell and Settings issues so Codex builds them (window manager, workspaces, quick settings, fix-a-problem, Settings pages, lock screen and theme packs);… |
| `fix-621-unit` | Fix rounds on PRs | 1 | 1 | 0h 07m | 71k | Landing PR #621: the required "unit" check fails on the newest run. Diagnose from the CI log, fix on the train branch, push, re-apply the visual label if no screen code changed. |
| `fix-621-hygiene-hit` | Fix rounds on PRs | 1 | 1 | 0h 00m | 56k | Landing PR #621: the hygiene check fails on one new hit (a test file line that looks like a home path). Fix it on the train branch and push. |

## Run log (as listed, newest first)

`ok` finished, `fail` failed, `stopped` stopped while running. Add new runs at the top of this table and update the totals.

| # | Status | Workflow | Run time | Agents | Tokens |
|--:|---|---|--:|--:|--:|
| 1 | ok | `verification-finish` | 14m25s | 3 | 347.7k |
| 2 | ok | `ui-gaps-build` | 2h10m44s | 29 | 5.6m |
| 3 | ok | `tidy-parity-fix` | 6m0s | 2 | 215k |
| 4 | ok | `repo-tidy-and-ui-parity` | 11m54s | 5 | 519.4k |
| 5 | ok | `land-reds-2` | 41m35s | 4 | 291k |
| 6 | ok | `gw-levels-final` | 2h22m40s | 2 | 565.9k |
| 7 | ok | `ci-gates-faster` | 43m0s | 7 | 880.7k |
| 8 | ok | `land-fuzz-clean` | 2h52m59s | 1 | 327.2k |
| 9 | ok | `post810-train-1` | 3h42m0s | 5 | 366.9k |
| 10 | ok | `land810-reds` | 1h51m43s | 18 | 1.5m |
| 11 | ok | `fast-s4-nats-and-ceremony` | 4h33m3s | 8 | 1.8m |
| 12 | ok | `fast-s3-recovery` | 5h21m10s | 7 | 1.8m |
| 13 | ok | `fast-s3-gateway-engine` | 4h24m24s | 8 | 2.1m |
| 14 | ok | `fast-s1-s2-followups-ci` | 4h1m51s | 7 | 1m |
| 15 | ok | `dell-kit-final` | 8m26s | 2 | 186.1k |
| 16 | ok | `bigger-plan-wave-a` | 1h29m38s | 10 | 1.3m |
| 17 | ok | `os-integration-round` | 5h38m28s | 2 | 735.1k |
| 18 | ok | `post810-prep-cache-1155-1156` | 2h53m50s | 5 | 1.1m |
| 19 | fail | `overnight-chain` | 6h39m17s | 20 | 954.6k |
| 20 | ok | `opus-escalate-p06` | 2h0m30s | 2 | 340.1k |
| 21 | ok | `opus-builders-1126-powercut` | 2h44m58s | 6 | 961.9k |
| 22 | ok | `wave2-second-round` | 11m40s | 6 | 490.1k |
| 23 | ok | `docs-reapprove-merge-v2` | 6m57s | 2 | 223.5k |
| 24 | ok | `docs-reapprove-merge-and-nats-fix` | 19m6s | 3 | 288.2k |
| 25 | fail | `fix-1126-nats` | 1h15m51s | 1 | 100.5k |
| 26 | ok | `leftover-fixes` | 4h40m21s | 12 | 1.3m |
| 27 | ok | `wave2-settings-flathub` | 6h31m59s | 25 | 4.6m |
| 28 | fail | `fix-powercut-k3s` | 3h14m22s | 1 | 311.4k |
| 29 | ok | `wave3-gateway-nats-apps` | 6h6m37s | 22 | 3.3m |
| 30 | ok | `security-and-settings-wave1` | 4h24m26s | 22 | 3.5m |
| 31 | ok | `post-step2-fixes-and-cli` | 7h15m43s | 12 | 1.6m |
| 32 | ok | `ci-image-tiers` | 3m59s | 3 | 238.4k |
| 33 | ok | `ci-image-slim` | 3m5s | 3 | 214.9k |
| 34 | ok | `stable-live-step1b` | 19m11s | 10 | 674.8k |
| 35 | ok | `fix-1102-cli-r3` | 5m30s | 2 | 173.8k |
| 36 | ok | `fix-1102-cli` | 4m33s | 2 | 188.1k |
| 37 | ok | `nats-role-research` | 14m59s | 4 | 518.8k |
| 38 | ok | `fix-1098-work-port` | 22m29s | 2 | 171.1k |
| 39 | ok | `audit-step1-wiring` | 44m54s | 12 | 1.5m |
| 40 | ok | `gateway-permissions-design` | 17m41s | 6 | 783.3k |
| 41 | ok | `native-features-audit` | 10m4s | 5 | 513.3k |
| 42 | ok | `step2b-step3-linux-native` | 6h10m31s | 14 | 2.1m |
| 43 | ok | `founder-calls-2026-11-25` | 35m25s | 6 | 516k |
| 44 | ok | `behind-prs-fixes` | 27m27s | 14 | 1.1m |
| 45 | ok | `behind-prs-prep` | 1h53m39s | 16 | 2.1m |
| 46 | ok | `step2-debian-bones` | 4h35m28s | 18 | 2.9m |
| 47 | ok | `stable-live-speedup` | 1h2m55s | 5 | 722.6k |
| 48 | ok | `stable-live-step1` | 5h22m47s | 13 | 1.2m |
| 49 | ok | `where-we-stand-os` | 5m17s | 6 | 744.4k |
| 50 | stopped | `v1-wave-runner` | 40m24s | 6 | 532.9k |
| 51 | ok | `final-push-capacity` | 16m34s | 5 | 401k |
| 52 | ok | `v1-cut-board` | 7m20s | 7 | 463.3k |
| 53 | fail | `v1-wave-runner` | 2h7m56s | 12 | 113.3k |
| 54 | fail | `v1-wave-runner` | 3h19m27s | 21 | 609.2k |
| 55 | fail | `v1-wave-runner` | 3h19m35s | 45 | 1.3m |
| 56 | fail | `v1-wave-runner` | 2h38m2s | 43 | 1.4m |
| 57 | fail | `v1-wave-runner` | 2h8m21s | 17 | 955.8k |
| 58 | fail | `v1-wave-runner` | 2h8m26s | 15 | 855.4k |
| 59 | fail | `v1-wave-runner` | 2h38m14s | 10 | 369.8k |
| 60 | fail | `codex-leftovers` | 2h38m34s | 17 | 312.2k |
| 61 | fail | `codex-leftovers` | 2h38m35s | 16 | 448.9k |
| 62 | ok | `lane-4-finish` | 2h38m36s | 11 | 157.4k |
| 63 | ok | `wave-p-android` | 1h50m23s | 37 | 186.1k |
| 64 | ok | `wave-a-b2-early` | 3h44m2s | 20 | 160k |
| 65 | fail | `foundation-flow` | 2h21m41s | 38 | 2.7m |
| 66 | ok | `review-gh-shim` | 10m26s | 2 | 194.7k |
| 67 | ok | `v1-wave-runner` | 3h38m1s | 12 | 1.5m |
| 68 | ok | `github-tracking` | 1h4m22s | 3 | 575k |
| 69 | ok | `overlap-and-done-audit` | 14m59s | 32 | 2.6m |
| 70 | ok | `ci-second-runner` | 2h54m34s | 7 | 830.1k |
| 71 | ok | `add-ci-capacity` | 1h27m36s | 3 | 480.6k |
| 72 | ok | `add-build-workers` | 42m15s | 8 | 747.5k |
| 73 | ok | `overlap-and-done-audit` | 11m43s | 22 | 1.8m |
| 74 | ok | `finish-241-snapshots` | 2h53m52s | 5 | 358.3k |
| 75 | ok | `lane-6-finish` | 3h40m28s | 23 | 1.7m |
| 76 | ok | `wave-e-early-ci-reliability` | 1h51m55s | 12 | 227.8k |
| 77 | ok | `codex-pr-gate-v2` | 1m7s | 2 | 136.8k |
| 78 | ok | `b1-issues-for-codex` | 0m5s | 1 | 95.1k |
| 79 | fail | `wave-b1-shell-and-codex-settings` | 8m56s | 1 | 166.5k |
| 80 | ok | `lora-messenger-plan` | 30m44s | 4 | 606.4k |
| 81 | ok | `lora-messenger-plan` | 4m39s | 2 | 259.8k |
| 82 | ok | `w0-land-rescue-secure` | 3h3m46s | 18 | 863.1k |
| 83 | ok | `codex-pr-gate` | 4m20s | 2 | 137.7k |
| 84 | ok | `xr-priority-track` | 13m29s | 4 | 399.5k |
| 85 | ok | `final-stretch-revise` | 8m8s | 2 | 244.6k |
| 86 | ok | `final-stretch-plan` | 21m22s | 10 | 1.2m |
| 87 | ok | `surface-structure-audit` | 6m0s | 11 | 1.1m |
| 88 | ok | `codex-pr-gate` | 12m44s | 2 | 130.9k |
| 89 | ok | `fix-621-smoke-and-fuzz2` | 1h6m14s | 2 | 248.3k |
| 90 | ok | `fix-621-unit` | 7m6s | 1 | 71.2k |
| 91 | ok | `codex-pr-gate` | 13m32s | 4 | 255.1k |
| 92 | ok | `fix-621-visual-and-fuzz` | 5m51s | 2 | 268k |
| 93 | ok | `fix-621-e2e` | 49m26s | 2 | 192.2k |
| 94 | ok | `codex-pr-gate` | 1h2m19s | 2 | 131.6k |
| 95 | ok | `fix-621-hygiene-hit` | 24s | 1 | 55.5k |
| 96 | ok | `codex-pr-gate` | 5m46s | 4 | 254.7k |
| 97 | ok | `ready-now-wave` | 5h4m9s | 29 | 3.3m |
| 98 | ok | `codex-pr-gate` | 2m13s | 2 | 125.2k |
| 99 | ok | `fleet-capacity` | 21m47s | 2 | 215.2k |
| 100 | fail | `ready-now-wave` | 8m36s | 8 | 1.2m |
| 101 | fail | `foundation-wave` | 7h39m41s | 16 | 2.4m |
| 102 | ok | `fix-621-ci` | 1h55m25s | 6 | 517.3k |
| 103 | ok | `review-the-rest` | 3h7m44s | 63 | 4m |
| 104 | ok | `issue-factory` | 54m47s | 3 | 486.5k |
| 105 | ok | `release-next` | 4h59m34s | 9 | 1.1m |
| 106 | ok | `tips-app-design` | 7m31s | 3 | 265.9k |
| 107 | ok | `onemind-mcp-two-doors` | 7m4s | 5 | 603.7k |
| 108 | ok | `nats-fabric-agents-omni` | 12m17s | 7 | 836.1k |
| 109 | ok | `physical-bridge` | 11m12s | 7 | 715.4k |
| 110 | ok | `iot-lora-edge-and-app-sdk` | 14m17s | 10 | 1.2m |
| 111 | ok | `first-party-apps-doctrine` | 14m4s | 9 | 1.1m |
| 112 | ok | `map-intel-xr-connectors` | 18m11s | 17 | 2m |
| 113 | ok | `project-boards-refresh` | 2h8m11s | 3 | 372.8k |
| 114 | fail | `map-intel-xr-connectors` | 2m3s | 6 | 660k |
| 115 | ok | `image-scan-final-fix` | 28m56s | 2 | 154.4k |
| 116 | ok | `logo-loading-screens` | 29m40s | 4 | 515.6k |
| 117 | ok | `onboarding-motion` | 59m48s | 9 | 1.6m |
| 118 | ok | `image-explainer-facts` | 12m7s | 7 | 749.5k |
| 119 | ok | `native-clients-and-sync` | 11m24s | 13 | 1.2m |
| 120 | ok | `ceremony-guide-final-fix` | 4m51s | 2 | 157k |
| 121 | ok | `design-addendum-round` | 1h19m22s | 16 | 3.7m |
| 122 | ok | `sprint-wave-4` | 8h2m4s | 8 | 1.1m |
| 123 | ok | `app-suite-and-desktop-apps` | 12m35s | 12 | 1.2m |
| 124 | ok | `sprint-wave-4` | 4h12m59s | 12 | 1.2m |
| 125 | ok | `three-asks-specs` | 2m57s | 6 | 483.3k |
| 126 | ok | `os-completeness-realtime-notifications` | 9m51s | 18 | 1.7m |
| 127 | ok | `design-final-round` | 1h1m47s | 9 | 1.7m |
| 128 | ok | `sprint-wave-4` | 1h18m29s | 18 | 1.9m |
| 129 | ok | `design-chooser-data` | 2m39s | 10 | 798.9k |
| 130 | ok | `landing-train-2-plugins` | 2h21m8s | 6 | 422.7k |
| 131 | ok | `sprint-wave-4` | 2h41m15s | 20 | 1.9m |
| 132 | ok | `supersede-and-design` | 54m45s | 26 | 4.5m |
| 133 | ok | `sprint-wave-4` | 3h47m26s | 38 | 3.5m |
| 134 | ok | `landing-train-1` | 6h56m34s | 31 | 2.6m |
| 135 | fail | `landing-train-1` | 0s | 0 | 0 |
| 136 | ok | `finish-audit` | 14m58s | 28 | 2.9m |
| 137 | ok | `polish-567-round-4` | 12m36s | 3 | 276.5k |
| 138 | ok | `resolve-stacked-conflicts` | 35m11s | 10 | 591k |
| 139 | ok | `polish-567-round-3` | 6m5s | 3 | 239.5k |
| 140 | ok | `registry-535-visual-fix` | 34m29s | 3 | 257.9k |
| 141 | ok | `webkit-flake-fix-round` | 2m25s | 2 | 116.2k |
| 142 | ok | `ci-unblockers-noon` | 26m54s | 7 | 474.5k |
| 143 | ok | `premium-polish-round-2` | 1h49m1s | 11 | 987.3k |
| 144 | ok | `premium-polish` | 1h43m38s | 23 | 2.3m |
| 145 | ok | `premium-design-directions` | 56m43s | 20 | 2.9m |
| 146 | ok | `sprint-wave-4` | 32m13s | 4 | 237.6k |
| 147 | ok | `repo-clutter-audit` | 17m50s | 15 | 1.2m |
| 148 | ok | `sprint-wave-4` | 2h3m47s | 10 | 708.1k |
| 149 | fail | `landing-crew-2` | 6h33m32s | 98 | 5.7m |
| 150 | ok | `repo-coverage-audit` | 9m46s | 18 | 1.4m |
| 151 | ok | `sprint-wave-4` | 1h48m40s | 10 | 956.5k |
| 152 | ok | `sprint-wave-5a` | 47m41s | 26 | 2.6m |
| 153 | fail | `landing-crew` | 32m7s | 60 | 3.4m |
| 154 | ok | `sprint-wave-4` | 4h56m44s | 8 | 667.8k |
| 155 | ok | `sprint-wave-4` | 3h10m43s | 10 | 804.4k |
| 156 | ok | `sprint-wave-4` | 4h48m4s | 38 | 3.3m |
| 157 | ok | `sprint-wave-4` | 5h25m39s | 42 | 3.4m |
| 158 | ok | `clients-wave` | 9m37s | 30 | 835.9k |
| 159 | ok | `ux-and-cluster-review` | 7m13s | 18 | 212.7k |
| 160 | ok | `sprint-wave-2` | 2h58m11s | 36 | 1.2m |
| 161 | ok | `backstage-front-door` | 25m30s | 11 | 1.3m |
| 162 | ok | `beyond-umbrelos-ux` | 5m18s | 6 | 709.9k |
| 163 | ok | `sprint-wave-3` | 1h39m43s | 56 | 4.7m |
| 164 | ok | `sprint-wave-1` | 2h27m43s | 56 | 5.2m |

## How to update

After a batch of new workflow runs, open the Dynamic workflows list, add each new run to the top of the run log (status, name, time, agents, tokens), add a purpose row for any new workflow, and recompute the totals. Ask Claude: *"update BUILD-EFFORT-LEDGER.md from these screenshots"*.
