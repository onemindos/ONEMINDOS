<!-- SPDX-License-Identifier: Apache-2.0 -->
# Wave 1: close-out and core builds

**Parts:** plugin platform, apps, core features, pipeline. **State:** done on 2026-11-21. Merging is the gate's job and is pending.
PR links: `https://github.com/onemindos/ONEMINDOS/pull/<n>`.

## Stuck PRs that were fixed (merge main in, fix the real cause)

| PR | Cause found | Review |
|---|---|---|
| #423 apps daily rescan | Conflict with the privatebin image PR #437. The red app check was a network flake pulling an image layer. | APPROVE |
| #386 CI-16 SDK generated in CI | No real failure. Only the known WebKit screenshot diff on the Market screen. | APPROVE |
| #351 | An earlier main merge had deleted three generated SDK files (about 21k lines), so every SDK job failed. Restored. | APPROVE |
| #358 kill switch | Same deleted SDK files. Restored. | not yet re-reviewed |
| #444 restore from another box | gitleaks flagged a fake test key. Test literal changed. | APPROVE |
| #336 manifest validator | Import conflict in `core/onemind_core/catalog.py`. Both sides kept. | APPROVE |
| #333 kiosk | Missing module-level scope for `/v1/instance/kiosk`; stale merge base. | CHANGES: CI `unit` red, cause to confirm |
| #355 system controls | No code defect. Runner loss on the local runners. | APPROVE |
| #441, #442, #443 | Conflicts only, from the Automation screen landing in the same nav lists. Both sides kept. | APPROVE |

## New builds

| PR | Issue | What it does | Review |
|---|---|---|---|
| #474 | #163 | Whole-box restore drill: a judge, an in-VM scenario and a two-VM driver, plus a monthly informational workflow. Not yet run end to end. | APPROVE |
| #480 | #168 | Taint ledger. An agent that read third-party text is tainted for 1 hour and its requests carry a note. | CHANGES: dashboard approve sends no `plan_sha256`, so tainted approvals fail with 409 |
| #484 | #117 | Re-checked blocked apps. Gitea and Node-RED move from blocked to community. | APPROVE |
| #490 | UMB-P02 | Open apps at their own name behind the OneMind sign-in. | APPROVE |
| #489 | #284 | Gateway path to the dashboard for the Tor app. | CHANGES (two rounds): the Tor listener is plain HTTP bound to all interfaces on every hub |
| #493 | #146 | Gateway link to the host executor (`host.sock`). Restart, shutdown and reset wait for #355. | not yet reviewed |
| #494 | api-fuzz | Fixes the red main run (the documented 503 on onboarding restore). | APPROVE |
| #479 | #323 | Ratchet test: every live route must register a scope. 102 routes are baselined. | APPROVE |

Skipped because a PR already existed: #164 (PR #382), #133 (PR #380), #132 (PR #384), #327 (done by #342).

## Security re-review of the plugin stacks (Opus)

- **Stack A, #447 then #448 then #451:** CHANGES. One confirmed gate bypass in #448: a plugin with an undeclared `manifests/` folder skips the workload checks, so a pod with host networking passes the gate. Fixed upstream blockers from #387 (the open `actions:request` pattern, Go and Python validators disagreeing).
- **Stack B, #449, #450, #452, #453:** CHANGES. #450 does not show the grants a plugin receives in the install plan. #452 runs "read" tools without approval, so a mislabelled tool can change things with no human tap.
- **#427 revocations:** CHANGES. Root rotation can be rolled back (`internal/plugin/verify/revocations.go`), which allows an un-revoke.

## What is left

- Merge decisions for every PR above, in the gate's order.
- The fixes for the three security CHANGES verdicts, then a second Opus pass.
- #333 `unit` failure, #480 dashboard approve fix, #489 listener fix.
- #163 drill has no end-to-end run yet.
