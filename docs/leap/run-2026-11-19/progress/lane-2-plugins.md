<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lane 2-plugins progress: Plugins

Only PRs from this lane edit this file. Update it in every PR: move the issue's line and add the PR number.
The order comes from [LANES.md](../LANES.md).

## Merged

## In review (ready, needs-review)

- #177: tool-manifest foundation; PR #387. Bounded first-slice Opus review; #175/#336 dependency and remaining #177 slices remain explicit.

## Draft (pushed, not ready yet)

- #178: exact action-type guard and immutable plugin principal; PR #406, stacked on #405. Common checks protect lifecycle, feature and replay paths. HTTP token policy remains read-only.

- #178: installed read-only token policy; PR #405, stacked on #404. Stored grants, exact route operations and live app state; issuer/request paths still disabled.

- #178: read-only installed plugin registry; PR #404. Real app states and Market sharing, with scoped-token/route authorization tests. Built on current main; merge after #177 schema support.
- #177: bounded UI bundle and static markup validation (P7/P8); PR #397, stacked on #396. Includes root SVG icons, settings schema compilation and local script checks.
- #177: typed widget data schema and schema-only CI coverage; PR #396, stacked on #395. Standalone contract consumed by future #179 host.
- #177: tool-update major-version guard; PR #395, stacked on #394. Removed tools, changed effects and changed inputs require a higher major.
- #177: permission-widening comparison (P11); PR #394, stacked on #393. Reports sorted reasons and never approves updates.
- #177: UI declaration validation (P1/P2 and lexical P7); PR #393, stacked on #392. Widgets, alert actions, settings and tiles; no widget runtime.
- #177: egress declaration validation (P9); PR #392, stacked on #389. Offline hostname/public-suffix checks, no runtime network changes.
- #177: event declaration validation (P4/P5); PR #389, stacked on #390. No NATS runtime or registry changes.
- #177: box API compatibility checks; PR #390, stacked on #388. Offline --api-level validates the target version against compat.onemind.
- #177: bundle path safety; PR #388, stacked on #387. Checks existence, types and symlinks through the shared Go validator.

## Next

- Resolve #175 and review the #177 draft stack, then #178, #179, #180, #183, #182, #181, #184, #185.
- #177 coverage limits: tool-backed plugins only; backend-free declarations and the literal older Hello example need alignment with the current App contract. Publisher ownership verification belongs to signing/index work.
- The current App secret name/key format is preserved. The older plugin example differs; do not copy its flat secret shape or omit App-required metadata/updates.
- Workload policy, scans, signatures and owner approval remain mandatory separate gates; the Go bundle check does not replace existing app-gate checks.

## Founder decision recorded

- 2026-11-19: founder approved D10/#140 vocabulary in TAXONOMY.md sections 1/5: the proposed 16 categories, exactly one category and 0–3 category-specific tags. This approval does not unpark robotics/crypto or approve the separate open policy questions. The gate can use this record to settle #140/#175; no category migration is included in lane 2.

## Blocked (waiting on the founder, hardware or another lane)

- #178 depends on #177. Plugin credentials need a deny-by-default policy plus exact-type guards in lifecycle and feature request paths before enabling request capability. Existing identity token rows can store plugin hashes; static token kinds stay unchanged. Pre-dispatch removal revocation is required, not only successful-removal cleanup.

- #175 manifest freeze remains open; #177 retains its dependency label until the gate resolves it.

- #387 CI found a missing sdk/schema copy in image builders; fixed both Go build contexts and the compose allowlist. Local isolated-context builds verify the dependency is present.
