<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lane 4-core progress: Core features

Only PRs from this lane edit this file. Update it in every PR: move the issue's line and add the PR number.
The order comes from [LANES.md](../LANES.md).

## Merged

## In review (ready, needs-review)
- #204 FAM-01 family roles and parental controls: PR #369 (Codex build, taken over by Claude for the lane). Updated from main on 2026-11-19 to pick up the apps rescan (#365), which fixes the red e2e-systemd check (expired ntfy scan, not this PR's code).

## Draft (pushed, not ready yet)
Drafts run only the fast CI checks; each needs a full green CI run before it leaves draft. Nothing in this lane was merged by an agent.
- #237 FILES-02 expiring share links: PR #381 (supersedes the plan-only draft #375). Reviewer fixed two missing PUBLIC route rows. Live relay delivery cannot be tested in this repo. Open founder question: the owner can list every person's links, including file paths from an adult's private Home.
- #132 NMD-07 update policy knobs: PR #384. Reviewer fixed operation ids (updates.policy.*).
- #133 NMD-08 offline-aware cleanup and disk budget: PR #380. Reviewer fixed a bug where docker.io/redis and redis were treated as different images, which could prune a stopped app's image. Not yet tried on hardware (k3s crictl under the unit's sandbox).
- #171 CORE-FABRIC-4 capability labels and placement verdict: PR #400. Placement is advisory: the executor does not yet set a nodeSelector. The route needs nodes:read so children cannot read machine details.
- #156 CORE-UPDATE-9 fleet-staged updates (gateway side): PR #383. Reviewer closed a hole where the static guest token could read fleet and rollout state. The node-side update.apply consumer in onemindd is still open.
- #127 NMD-02 content manager for offline libraries: PR #398. Built on main; does not need #368's code. Adds the Library dashboard page. Every download or update waits for owner approval.
- #164 BAK-03 optional size-aware content backup tier: PR #382. Review found nothing to fix.

## Next
- Full CI on every draft above, then undraft and hand to the admin for review and merge.
- #171 follow-up: make the executor honour placement (nodeSelector and node labels).
- #156 follow-up: node-side update.apply consumer in onemindd.

## Blocked (waiting on the founder, hardware or another lane)
- #236 SEC-SSO-01 single sign-on (OIDC + forward-auth): needs founder decision F-34 (where Kanidm runs), the Kanidm lab test UMB-ACCT-1, and #139 (draft PR #347). Kanidm is not in the repo yet. Explainer: docs/learning/founder/07-kanidm-and-single-sign-on.md (PR #399).

## Notes
- 2026-11-19: Codex built #204 (PR #369) and claimed #237 (draft #375). Zeus then moved the whole lane to Claude, which built the rest with parallel agents, one worktree and one draft PR per issue, each followed by a reviewer.
- #204 scope as built: owner-managed per-person profiles (app allowlists, age-rating limits, tag blocks, weekly schedules including overnight windows, private child birth dates) through /v1/family/profiles/{user_id} and /v1/family/apps/{app_id}. The same checks apply to the catalog, app routes and the proxy, and an agent token inherits its owner's limits. Roles stay owner, adult, guest and child; the issue's Teen role was not added, following the lane instructions. Content filtering inside third-party apps is not provided.
