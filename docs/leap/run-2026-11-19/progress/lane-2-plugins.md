<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lane 2-plugins progress: Plugins

Only PRs from this lane edit this file. Update it in every PR: move the issue's line and add the PR number.
The order comes from [LANES.md](../LANES.md).

## Merged

## In review (ready, needs-review)

- #177: tool-manifest foundation; PR #387. Current-main refresh and checks pass; only lane-2 needs-review request. Gate retains #175/#336 dependency ordering.

## Draft (pushed, not ready yet)

- #182: TUF-delegated revocation client; PR #427 (draft), stacked on #422. Real signed-repository tests cover the plugins delegation, target hash, metadata/list expiry, metadata rollback and persistent list-version/equivocation floors. CLI is diagnostic; gateway stopping/tool enforcement and phase-2 countersignatures remain next.

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
- #178: approved-install plugin credential delivery; PR #409, stacked on #408. Hashed grants, atomic installation snapshot, plugin-only Secret variables and persistent dispatch public key. Unsupported runtime grants fail closed; unchanged-grant updates are implemented in the settings completion slice.

- #178: installed registry receipts and plan fingerprints; PR #413, stacked on #411. Declarative plugins appear in registry; immutable receipts survive catalog edits. Settings schemas/UI/icons enter the approval fingerprint with symlink and size bounds.

- #178: signed REST tool invocation; PR #414, stacked on #413. Read tools are bounded and audited; mutation requests retain declared risk, require owner approval and serialize against app removal. Destructive approvals require a real action-bound passkey.

- #178: installed-schema plugin settings; PR #415, stacked on #414. Owner-approved plugin.configure applies fixed plugin-settings ConfigMap; schema/value bounds, sharing and receipt checks precede execution.

- #183: unpacked plugin malware scan adapter; PR #416, stacked on #412. Real ClamAV scans frozen bundle files, including UI. EICAR blocks the app gate/tier; errors, symlinks and byte limits fail closed. Full OCI/referrer/scan-attestation binding remains dependent on #180.

- #181: safe settings scaffold; PR #417, stacked on #412. onemind plugin init requires a source URL, validates output before publication and never replaces existing paths. Backend templates/dev runtime follow packaging.

- #180: deterministic local OCI packing; PR #418, stacked on #417. Content-addressed config/workload/UI/README layers, no root-file globbing, no overwrites. Unsigned only; image pin resolution, remote transport, verification and install follow.

- #180: exact-digest OCI content inspection; PR #419, stacked on #418. Bounded blob verification/extraction rejects paths, links, duplicate/reserved entries and trailing payloads, then reuses the shared validator. Content integrity is explicitly not publisher trust.

- #180: candidate private signature inspection; PR #420, stacked on #419. Existing Sigstore verifier checks detached signatures over the exact artifact manifest (Ed25519/ECDSA/RSA), reports a public-key fingerprint and never claims owner enrollment or overall trust.

## Next

- Finish #177/#178 implementation and review first. Founder then requests smallest-to-heaviest work where dependencies allow: #183 scan adapter and #181 init slices are smallest; #180 packaging must land before those full issues, #184 follows #181, while #179/#182/#185 require heavier integration.
- #177 validator covers tool-backed and declarative plugins. The older design Hello example uses an obsolete App shape; current executable tests use the current metadata/updates and structured-secret contract. Publisher verification belongs to signing/index work.
- The current App secret name/key format is preserved. The older plugin example differs; do not copy its flat secret shape or omit App-required metadata/updates.
- Workload policy, scans, signatures and owner approval remain mandatory separate gates; the Go bundle check does not replace existing app-gate checks.

## Founder decision recorded

- 2026-11-19: founder approved D10/#140 vocabulary in TAXONOMY.md sections 1/5: the proposed 16 categories, exactly one category and 0–3 category-specific tags. This approval does not unpark robotics/crypto or approve the separate open policy questions. The gate can use this record to settle #140/#175; no category migration is included in lane 2.

## Blocked (waiting on the founder, hardware or another lane)

- #178 depends on #177 and has signed tool invocation and installed-schema settings drafted for final review in #414/#415. Issuance, Secret delivery, own-action polling and persistent revocation are drafted; static token kinds stay unchanged.

- #175 manifest freeze remains open; #177 retains its dependency label until the gate resolves it.

- #387 CI checkpoint: code/image workflows passed; merge-gate timed out waiting for ci-apps. Do not rerun the broad suite while that dependency is still pending. Gate review and merges remain Claude-owned.

- #418 review corrections: preserve empty directories, canonicalize archive aliases before deduplication and partition overlapping workload/UI paths so produced layouts round-trip through the strict reader.

- #415 schema upgrade fix is pushed: v1 registry databases migrate to plugin schema v2 without losing receipts. Two upgrade/idempotence/fresh-database tests and the settings suite passed (16 total).
- #420 integrated packaging corrections passed artifact/CLI race tests, including empty workload directories, shared workload/UI icons and canonical path aliases. Next implementation: owner-approved private key enrollment, then complete verification/installation and dev workflow.

- Next concrete #180 slice (E9 private tier): owner-only signing-key enrollment/revocation actions with stored canonical SPKI public keys and SHA-256 fingerprints, step-up when passkeys are active, real upgrade/auth tests and a generated-SDK dashboard screen. Parse/reject private PEM before filing/auditing; only approved actions activate trust. This does not create production root/store keys or grant publisher trust from a caller-supplied key.

- #180 owner-key enrollment slice: PR #421 (draft), stacked on #415. Canonical public-key fingerprints enter trust only after owner-approved actions; enrollment/revocation require action-bound passkeys when active. Mounted Settings screen uses generated SDK and the real approval challenge flow. Artifact verification/install integration remains next.

- #180 local signing: PR #422 (draft), stacked on #420. `plugin sign` signs only a digest-pinned, fully parsed local artifact, using an existing owner-readable PKCS8 key. Detached output is exclusive; key bytes are never logged or copied into the layout. Signing does not establish owner trust or installation approval.
