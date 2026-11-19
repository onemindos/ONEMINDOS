<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lane 6: apps

Date: 2026-11-19. Owner: Codex. Area: apps.

Build order: #126, #129, #174, #252, #245, #199, #250, #176, #201.
Claim one issue at a time; verify dependencies before beginning each issue.

## #126 — Offline Knowledge (NMD-01 / REC-NOMAD-01)

State: apps implementation built; full app gate queued; Market integration pending.
Branch: `codex/126-offline-knowledge`.
Draft PR: https://github.com/onemindos/ONEMINDOS/pull/368.

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

### Implementation and evidence

- Added straight-line distance measurement and local GeoJSON overlays to the
  shipped map page. Overlay files stay in the tab, have size/position limits,
  discard properties and remote styles, and require no new dependencies.
  Tests cover dateline rendering, invalid geometry and asynchronous selection
  races (old map headers and file reads cannot replace newer selections).
- Fixed the bundle's rejected API payloads: install first, then separately
  owner-approved configuration with manifest setting names and typed values.
  Added live catalogue preflight, optional blocked-app skipping, existing-app
  handling, stable action polling and redirect refusal to protect owner tokens.
- All five constituent apps pass `sdk/tools/validate-apps`. Generated READMEs,
  `make lint`, change-fragment validation and hygiene checks pass. Gitleaks on
  affected app and test directories found no leaks.
- The SDK tool suite initially failed on macOS BSD find; using the already
  installed GNU find and isolated Python environment makes the unchanged suite
  pass. Final integrated suite: 114 tests passed, including 22 offline tests.
- Native full-gate invocation stopped with exit 2 because `clamscan` is missing;
  this is an environment failure, not a scan verdict. No gate code was changed.
  The existing dual-architecture gate was dispatched for all five apps:
  https://github.com/onemindos/ONEMINDOS/actions/runs/44521442686.
  It is queued; no fresh passing scan is claimed.
- Kolibri remains blocked with its existing five fixable critical findings
  documented in its README. Ollama has no committed scan record, so the new
  preflight refuses a required install until a valid scan is available.

### Cross-lane dependency

The Market has individual app requests but no bundle entry or orchestration.
Gateway/dashboard owners need to expose the bundle profiles and sequence
`app.install` then `app.configure`, waiting for owner approval and successful
completion before dependent apps. Surface blocked/failed steps and never
auto-approve. The exact dependency is recorded on #126:
https://github.com/onemindos/ONEMINDOS/issues/126#issuecomment-7008676734.
No gateway/dashboard files were changed. Keep #126 open until its Market
acceptance criterion and full gate evidence are satisfied.
