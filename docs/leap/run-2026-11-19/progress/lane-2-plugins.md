<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lane 2-plugins progress: Plugins

Only PRs from this lane edit this file. Update it in every PR: move the issue's line and add the PR number.
The order comes from [LANES.md](../LANES.md).

## Merged

## In review (ready, needs-review)

- #177: tool-manifest foundation; PR #387. Current-main refresh and checks pass; only lane-2 needs-review request. Gate retains #175/#336 dependency ordering.

## Draft (pushed, not ready yet)

- #177: declarative manifest completion; PR #410, stacked on #397. Conditional workload requirements, optional tools, bounded publisher declarations and dual-identity refusal.
- #177: shared Go validator in app CI; PR #412, stacked on #410. Real binary invocation fails closed; native tests exercise valid and invalid bundles.

- #178: scoped HTTP action requests; PR #407, stacked on #406. Real plugin tokens create pending actions only for exact stored types; live origin state is rechecked before filing.

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

- #178: persistent credential retirement; PR #408, stacked on #407. Revokes before removal, before reinstall, after failed install and during startup recovery; no issuer or Secret delivery yet.

- #178: own-action polling; PR #411, stacked on #409. Exact stored actions:read:own permits only known ledger GET routes and the requesting plugin’s own rows. Public manifest actions:read:self maps to this internal grant at issuance; other actors’ details return 404.
- #178: approved-install plugin credential delivery; PR #409, stacked on #408. Hashed grants, atomic installation snapshot, plugin-only Secret variables and persistent dispatch public key. Unsupported grants and plugin updates fail closed pending their runtime support.

- #178: installed registry receipts and plan fingerprints; PR pending, stacked on #411. Declarative plugins appear in registry; immutable receipts survive catalog edits. Settings schemas/UI/icons enter the approval fingerprint with symlink and size bounds.

## Next

- Finish #177/#178 implementation and review first. Founder then requests smallest-to-heaviest work where dependencies allow: #183 scan adapter and #181 init slices are smallest; #180 packaging must land before those full issues, #184 follows #181, while #179/#182/#185 require heavier integration.
- #177 validator covers tool-backed and declarative plugins. The older design Hello example uses an obsolete App shape; current executable tests use the current metadata/updates and structured-secret contract. Publisher verification belongs to signing/index work.
- The current App secret name/key format is preserved. The older plugin example differs; do not copy its flat secret shape or omit App-required metadata/updates.
- Workload policy, scans, signatures and owner approval remain mandatory separate gates; the Go bundle check does not replace existing app-gate checks.

## Founder decision recorded

- 2026-11-19: founder approved D10/#140 vocabulary in TAXONOMY.md sections 1/5: the proposed 16 categories, exactly one category and 0–3 category-specific tags. This approval does not unpark robotics/crypto or approve the separate open policy questions. The gate can use this record to settle #140/#175; no category migration is included in lane 2.

## Blocked (waiting on the founder, hardware or another lane)

- #178 depends on #177 and still needs final tool invocation/settings runtime integration. Issuance, Secret delivery, own-action polling and persistent revocation are drafted; static token kinds stay unchanged.

- #175 manifest freeze remains open; #177 retains its dependency label until the gate resolves it.
