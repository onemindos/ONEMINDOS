<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lane 6: apps

Date: 2026-11-19. Owner: Codex. Area: apps.

Build order: #126, #129, #174, #252, #245, #199, #250, #176, #201.
Claim one issue at a time; verify dependencies before beginning each issue.

## #126 — Offline Knowledge (NMD-01 / REC-NOMAD-01)

State: claimed; implementation not started.
Branch: `codex/126-offline-knowledge`.

PR #124 is merged and supplies Kiwix, Kolibri, Offline Maps, Library Chat,
profiles and a command-line bundle installer. Existing manifests mark Kiwix
and Offline Maps verified, and Kolibri blocked. These are historical claims,
not fresh gate results.

Plan before implementation:

1. Audit current main against the acceptance criteria and existing tests:
   Kiwix library management, Kolibri, PMTiles, point-to-point distance,
   custom overlays, Market bundle installation and the off-grid profile.
2. Complete missing behavior within apps ownership. If Market installation
   needs another lane's gateway or dashboard files, report the exact interface
   dependency and coordinate ownership before changing those files.
3. Keep owner approval on every install. Retain digest-pinned images and
   verify declared architectures. Use Apache-compatible sources for any
   copied patterns; keep software and content licence notes explicit.
4. Run the unchanged `sdk/tools/app-gate` for affected apps. Failed apps stay
   `tier: blocked` with the concrete reason in their README. Never present
   unavailable tooling or historical scans as a fresh pass.
5. Add regression tests for new behavior, run app validation and the SDK tool
   suite, add a change fragment, run hygiene and gitleaks, and hand the PR to
   the review gate. Do not merge it as the builder.

Coordination: #173 is claimed in lane 1; do not change its licence-class work.
Progress documentation changes are confined to this file under Rule 3.
