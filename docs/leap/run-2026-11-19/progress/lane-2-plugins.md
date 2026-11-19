<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lane 2-plugins progress: Plugins

Only PRs from this lane edit this file. Update it in every PR: move the issue's line and add the PR number.
The order comes from [LANES.md](../LANES.md).

## Merged

## In review (ready, needs-review)

## Draft (pushed, not ready yet)

- #177: permission-widening comparison (P11); PR pending, stacked on #393. Reports sorted reasons and never approves updates.

- #177: UI declaration validation (P1/P2 and lexical P7); PR #393, stacked on #392. Widgets, alert actions, settings and tiles; no widget runtime.

- #177: egress declaration validation (P9); PR #392, stacked on #389. Offline hostname/public-suffix checks, no runtime network changes.

- #177: event declaration validation (P4/P5); PR #389, stacked on #390. No NATS runtime or registry changes.

- #177: box API compatibility checks; PR #390, stacked on #388. Offline --api-level validates the target version against compat.onemind.

- #177: bundle path safety; PR #388, stacked on #387. Checks existence, types and symlinks through the shared Go validator.

- #177: tool-manifest foundation; PR #387. Shared Go validator and CLI; remaining rules tracked in the PR.

## Next

- Finish #177 validation rules, then #178, #179, #180, #183, #182, #181, #184, #185.

## Blocked (waiting on the founder, hardware or another lane)

- #175 manifest freeze remains open; #177 retains its dependency label until the gate resolves it.
