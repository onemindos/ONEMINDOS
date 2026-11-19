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

## Implementation update

- Draft PR: #369. Gateway implementation and generated SDK models are complete.
- Added durable owner-managed profiles and app classifications through mounted
  `/v1/family/profiles/{user_id}` and `/v1/family/apps/{app_id}` routes.
- Profiles restrict existing sharing with allowlists, age-rating limits, tag
  blocks and local-time weekly windows (including overnight windows). A rating
  limit blocks unclassified apps. Birth dates are private child-profile data.
- Owner management uses existing passkey step-up and CSRF protections. Profile
  reads use `Cache-Control: no-store`; audit records omit private policy values.
- Catalog, direct app routes and proxy decisions use the same restrictions;
  owned agent tokens inherit the owning person's policy and sharing limits.
  Children may open shared `signed_in` apps; adult/owner-only apps stay denied.
- Native Codex subagent review found two access gaps; both were fixed and the
  follow-up review reported no remaining actionable findings.
- Verification so far: 61 family/proxy tests passed; the initial 92-test family,
  identity and proxy run passed before the review fixes; Go SDK tests, 17 Python
  SDK tests, TypeScript typecheck and 15 TypeScript tests passed (one live test
  skipped); lint, fragment validation and hygiene/gitleaks passed.
- Full core suite and repo unit suite are running. Homebrew OpenSSL is required
  for these local certificate tests; system OpenSSL failed existing TLS checks.
- Scope limits: this implements gateway policy and mounted management routes,
  without editing the concurrently owned dashboard lane. App ratings classify
  entire apps; content-item filtering inside third-party apps is not supplied.
  Existing app connections are not forcibly terminated when a window closes;
  subsequent gateway/proxy access checks enforce the current policy.
