<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lane 2-plugins progress: Plugins

Only PRs from this lane edit this file. Update it in every PR: move the issue's line and add the PR number.
The order comes from [LANES.md](../LANES.md).

## Merged

## In review (ready, needs-review)

## Draft (pushed, not ready yet)

- #177: bounded UI bundle and static markup validation (P7/P8); PR #397, stacked on #396. Includes root SVG icons, settings schema compilation and local script checks.

- #177: typed widget data schema and schema-only CI coverage; PR #396, stacked on #395. Standalone contract consumed by future #179 host.

- #177: tool-update major-version guard; PR #395, stacked on #394. Removed tools, changed effects and changed inputs require a higher major.

- #177: permission-widening comparison (P11); PR #394, stacked on #393. Reports sorted reasons and never approves updates.

- #177: UI declaration validation (P1/P2 and lexical P7); PR #393, stacked on #392. Widgets, alert actions, settings and tiles; no widget runtime.

- #177: egress declaration validation (P9); PR #392, stacked on #389. Offline hostname/public-suffix checks, no runtime network changes.

- #177: event declaration validation (P4/P5); PR #389, stacked on #390. No NATS runtime or registry changes.

- #177: box API compatibility checks; PR #390, stacked on #388. Offline --api-level validates the target version against compat.onemind.

- #177: bundle path safety; PR #388, stacked on #387. Checks existence, types and symlinks through the shared Go validator.

- #177: tool-manifest foundation; PR #387. Shared Go validator and CLI; remaining rules tracked in the PR.

## Next

- Resolve #175 and review the #177 draft stack, then #178, #179, #180, #183, #182, #181, #184, #185.
- #177 coverage limits: tool-backed plugins only; backend-free declarations and the literal older Hello example need alignment with the current App contract. Publisher ownership verification belongs to signing/index work.
- The current App secret name/key format is preserved. The older plugin example differs; do not copy its flat secret shape or omit App-required metadata/updates.
- Workload policy, scans, signatures and owner approval remain mandatory separate gates; the Go bundle check does not replace existing app-gate checks.

## Blocked (waiting on the founder, hardware or another lane)

- #175 manifest freeze remains open; #177 retains its dependency label until the gate resolves it.

- #177: completion slice prepared on codex/177-plugin-manifest-completion (PR pending): declarative extensions without tools/workloads, P6 runtime requirements, bounded publisher declarations and plugin/agent identity separation. Literal older Hello example still needs current App metadata/updates, closed tool output and structured App secrets; no docs example or secret contract is changed here. Shared-validator CI invocation is a separate integration slice.
