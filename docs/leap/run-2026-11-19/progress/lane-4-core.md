<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lane 4: core — 2026-11-19

Workstream: FAM-01 (#204), followed by #237, #236, #132, #133, #171,
#156, #127 and #164, in that order. Locked decisions D-001–D-014 apply.

## Current claim

- Issue: #204, family roles and parental controls.
- Builder: Codex, leap:4-core (area:core).
- Branch: `codex/204-family-controls`.
- Status: claimed; planning complete; implementation not started.
- Listed the lane with `gh issue list -R onemindos/ONEMINDOS -l leap:4-core`.

## Implementation plan

1. Inspect existing identity persistence, authorization, app access and tests,
   and the dashboard role views in PR #354 before extending them.
2. Preserve the existing owner, adult, guest and child roles. The issue's older
   Teen-role request is superseded by the founder's lane instructions.
3. Persist per-person app visibility, rating/tag restrictions, schedules and
   child birth dates through the existing identity model. Keep private profile
   data out of public responses and audit payloads.
4. Expose controls through authenticated gateway routes; enforce restrictions
   at the relevant access boundaries, with owner-approved management and no
   agent bypass. Register route scopes once at module level, following
   `core/onemind_core/routers/machines.py`, never inside `register()`.
5. Add role, authorization and schedule tests, including denied access and
   boundary cases; verify existing role views remain compatible. Regenerate
   SDK artifacts if the gateway contract changes.
6. Run checks for touched areas plus fragment validation, hygiene and gitleaks;
   add the required change fragment, sign off commits, push and hand the PR
   to the independent review gate. Only this file receives doc/progress edits.

## Scope notes

The initial claim contains this progress plan only. No application code has
been written. Dashboard changes, if required, must respect the concurrently
owned dashboard lane; prefer a complete gateway implementation reachable by
mounted routes and the generated SDK.
