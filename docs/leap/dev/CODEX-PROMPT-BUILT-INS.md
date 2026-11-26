<!-- SPDX-License-Identifier: Apache-2.0 -->
# Prompt for Codex: register OneMind's built-and-working apps as built-ins

Founder-requested (2026-11-26). Paste everything below the line into Codex, run from a clone of `onemindos/ONEMINDOS`.

---

You are registering OneMind OS apps that are already built and working as **built-ins**. A built-in is an app that ships with the OS: it is on the signed system list, has one on/off switch, Settings pages, backup units, request-only AI tools and a phone entry (D-003). The app code exists; your job is the wiring. Work through five issues **in this order, one branch and one PR each, and open the next only after the previous one is merged** (they all touch the same list file and test):

1. **#1261 `builtins-everyday`**: Work, Dashboards, Search (Search declares no backup units with an explicit `none` reason; see the gate's comment on the issue).
1b. **#1277 `builtins-browser`**: Browser, including closing the browser proxy when it is off.
2. **#1262 `builtins-ai`**: Agents, Agent browser, Automation.
3. **#1263 `builtins-system-people`**: Machines, Sharing, Family, Care, World sources.
4. **#1264 `builtins-fold-into-settings`**: Control Hub, Usage, Storage, Network, Troubleshoot and Migrate go under the existing Settings built-in. They do **not** go on the signed list.

## Read first, in this order
1. `CLAUDE.md`, `docs/leap/BUILDER-BRIEFING.md`, `docs/leap/AGENT-QUEUE.md` (claiming, definition of done, sign-off).
2. The issue you are on: `gh issue view <n> -R onemindos/ONEMINDOS`. Its table gives each app's id, class, update, disable and a starting list of the prefixes it owns. **These are founder-proposed defaults.** Build with them unless Zeus has commented otherwise on the issue.
3. `core/onemind_core/systemlist.py` (the signed list and the never-off floor) and `core/onemind_core/builtins.py` (descriptors, `BuiltinGate`, MCP tools, GET /v1/builtins).
4. `sdk/schema/onemind.builtin.schema.json` and two working descriptors to copy: `core/onemind_core/tips/onemind.app.yaml` and `core/onemind_core/photos/onemind.app.yaml`.
5. `core/tests/test_builtin_conformance.py`: the checks every built-in must pass.
6. The app's own code: `core/onemind_core/routers/<app>.py`, its module folder, and its dashboard screen in `dashboard/src/screens/`.

## What each app needs
1. **A row** in `os/rootfs/layers/onemind/usr/lib/onemind/system-apps.json`: `{"id", "name", "class", "update", "disable"}` exactly as the issue's table says.
2. **A descriptor** `core/onemind_core/<id>/onemind.app.yaml` (an `__init__.py` too if the folder is new):
   - `spec.routes.owns`: only the prefixes this app alone serves. Find them in the router, not from the issue's starting list alone. **No prefix may belong to two built-ins**; the conformance test fails on overlap.
   - `spec.routes.calls`: every route its screens use; each must exist in the public OpenAPI.
   - `spec.backup.units`: the tables it owns (check the models).
   - `spec.actions` with `mcp: true` only for request-only actions that already exist. **Never add a tool that acts without a person approving.**
   - `spec.settingsPages`, `spec.notifications` (topics in the notify catalogue), `spec.data`, `spec.search`, `spec.cards`, `spec.mapLayers` where the app already has them.
   - `spec.phone`: `native` with the screen name if `mobile/` has a screen for it, otherwise match what the phone does today.
3. **Tests:** add the new ids to the expected list in the conformance test and parametrise the existing switch-off tests over them. Do not weaken any existing test.
4. If GET /v1/builtins changes shape, run `make -C sdk gen` and commit only `sdk/openapi/onemind-v1.json`.

## Hard rules
- **AI never actuates without human approval.** Registering an app adds no power to any agent.
- Switching an app off must never block a person from approving, denying, stopping an agent, signing in, or repairing the box. Agents and Family are `disable: never` for this reason. Approval rules (`/v1/approval-policies`) stay with Approvals, not Automation.
- Do not change `NEVER_DISABLE` in `systemlist.py` and do not move any route. If an app needs a route change to register cleanly, **stop and ask**.
- Real data only; no mocks, no fixtures outside tests.
- Smallest change that meets the issue, under about 600 changed lines.

## Before you open each PR (all must pass)
```bash
make -C core test
make -C sdk check-stale
make lint
python3 -I scripts/changes.py check
make hygiene
```
- One change fragment `changes/<branch-with-dashes>.md` (`pr: pending`). Never edit `CHANGELOG.md` or `docs/leap/STATUS.md`.
- Every commit `git commit -s`. Branch from `origin/release/next`: `git fetch origin release/next && git switch -c feat/<key> origin/release/next`.
- Claim first: comment `claim: codex, branch feat/<key>` on the issue and add the `claimed` label.
- Open the PR against `release/next` with `.github/pull_request_template.md`, `Refs #<n>` (never "Closes"), labels `builder:codex` and `needs-review`. The Opus gate reviews and merges; do not merge yourself.

## Stop and ask instead of building around it
- A prefix is shared with another built-in and splitting it needs a route change.
- An app is really a container workload (a container built-in may only live in `apps/_system/<id>/`).
- An issue's default (class, update or disable) looks wrong once you read the code. Say why in the issue and wait.
- Messages is **not** part of this work: it joins the list with its read path (#856).

When a PR is open, report its link and wait for it to merge before starting the next issue. At the end, report each PR, what is done, what is not, and every place you stopped to ask.
