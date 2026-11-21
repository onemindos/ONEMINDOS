<!-- SPDX-License-Identifier: Apache-2.0 -->
# Plugin lane handoff — 2026-11-21

The founder requests finishing #177, #178 and #180 before proceeding with the rest of lane 2. This is a technical continuation record, not a claim that all three issues are complete or merged. Claude owns review and every merge; Codex builds. Only #447 is ready/needs-review. Preserve the remaining drafts until the preceding review is merged.

## Current review units

| PR | Branch | Base | Implemented |
| --- | --- | --- | --- |
| [447](https://github.com/onemindos/ONEMINDOS/pull/447) | codex/177-plugin-validator | main | Consolidated manifest/schema, shared Go validator, bundle/UI/events/egress/API/version/update checks |
| [448](https://github.com/onemindos/ONEMINDOS/pull/448) | codex/183-plugin-ci-gate | codex/177-plugin-validator | Shared box validator in CI; actual ClamAV bundle scanning |
| [449](https://github.com/onemindos/ONEMINDOS/pull/449) | codex/178-plugin-registry-fold | main | Installed registry, durable receipt model, sharing, UI/settings approval fingerprints |
| [450](https://github.com/onemindos/ONEMINDOS/pull/450) | codex/178-plugin-principal-fold | codex/178-plugin-registry-fold | Plugin principals, exact grants, approved-install credentials, persistent retirement, own-action reads |
| [452](https://github.com/onemindos/ONEMINDOS/pull/452) | codex/178-plugin-tools-fold | codex/178-plugin-principal-fold | Bounded signed REST dispatch, owner-approved settings, schema migrations and generated clients |
| [451](https://github.com/onemindos/ONEMINDOS/pull/451) | codex/180-plugin-cli-fold | codex/183-plugin-ci-gate | Declarative init, deterministic OCI pack, strict pinned inspection and purpose-bound signing |

[453](https://github.com/onemindos/ONEMINDOS/pull/453), branch `codex/180-plugin-owner-trust-fold` on #452, replaces #421. It preserves the main dashboard's action-response validation and array handling while adding non-retried passkey assertions. API/identity/route checks passed 140 cases (235 unrelated parameters skipped); all 203 active dashboard tests, typecheck, lint and build passed (one skipped). SDK suites and required repository checks passed. No production key was generated.

[427](https://github.com/onemindos/ONEMINDOS/pull/427) contains a genuinely signed, expiring TUF revocation client with persistent metadata and list-version/hash floors. It remains on the old CLI stack: port its isolated `internal/plugin/verify` and revocations command onto #451 before review, retaining the new signature purpose and restricted action grants. Do not merge its old CLI ancestry as a substitute for the consolidated stack.

## Review decisions already applied

The [founder-authorized fold](https://github.com/onemindos/ONEMINDOS/pull/387#issuecomment-7045449756) replaces the small original drafts, uses one fragment per replacement, stops progress-document edits and retains all original branches. Replaced PRs link to their replacements. No force-push, rebase or main push was used.

- The permission schema permits only `actions:request:app.install|remove|start|stop|restart|update|configure`. Regressions reject delete-data, policy creation and unknown action types.
- Before shared-Go CI integration, #447's Python gate rejects any plugin-related declaration. #448 replaces that guard with the real Go binary for all four entry fields: extensions, plugin, permissions and compat.
- Update comparison now includes added subscriptions, alert tool/argument changes and changed workload declarations. It is informational. #178 lifecycle plan fingerprints bind actual workload, image declarations, settings, UI and icon bytes; comparison alone never approves updates.
- UI markup checks are lexical. Runtime opaque-origin sandbox and CSP enforcement remain #179 and must not be represented as implemented here.
- CI installs the real ClamAV engine before unit tests, so EICAR detection is exercised rather than silently skipped.
- #451 checks supplied signatures before extracting layers. The signed message is `onemind.plugin.artifact/v1` + newline + exact digest + newline + raw OCI manifest. Old raw-manifest-only signatures are refused. Ed25519, ECDSA and RSA use the existing Sigstore cryptographic implementation. No production artifacts were signed or published.

## Verification evidence

- #447: Go vet/race suites, 93 SDK-tool tests, lint, stale generation, hygiene and gitleaks passed. GitHub checks subsequently completed; the merge gate initially timed out awaiting ci-apps. Once ci-apps finished, rerunning only the failed gate cleared it. Last inspection showed no failed or pending checks; refresh GitHub before claiming current CI status.
- #448 and #451: 104 SDK-tool tests with the actual built onemind binary and ClamAV passed. #451 also passed all internal/plugin and CLI race suites, including independent OCI-reader interoperability, bounded adversarial extraction, malformed signatures, wrong purpose and pre-extraction signature checks.
- #449: 33 registry/fingerprint/auth tests passed; 214 unrelated parameter cases skipped.
- #450: 159 focused plugin/request/auth tests passed; an additional workload run passed all 13 cases including real approved installation followed by mutable-catalog changes.
- #452: full native gateway run passed 4,995 tests, skipped 655 and had 57 expected failures. Two Go CLI conformance fixture setup errors were local linked-worktree VCS stamping; rerunning exactly those with `GOFLAGS=-buildvcs=false` passed both. Thus all 4,997 executable cases passed across the runs. SDK Go/Python/TypeScript suites passed (one live TS test skipped). PostgreSQL/Kubernetes and hardware integration are not proven by these native runs.
- Each pushed fold ran relevant lint, change-fragment checks, hygiene, generated-SDK checks and gitleaks. API snapshots and clients were regenerated from current main, preserving other lanes' endpoints.

Run Python tests through the isolated core uv environment. On macOS the app path-selection tests require GNU find. Linked-worktree Go builds may require `-buildvcs=false`; set it on the command, not persistent Git configuration. SDK TLS tests use the installed OpenSSL 3 toolchain. Never export GIT_DIR/GIT_WORK_TREE.

## Required next build: complete #180

This is the largest unfinished item among the founder's three priorities. Do not close #180 based on signing or successful inspect.

1. Implement mounted `onemind plugin verify` and digest-pinned install request paths. Arbitrary caller-supplied public keys prove signature validity only; installed trust must come from the active owner-enrolled store. Recheck revocation at use time.
2. Verify a fresh passing artifact-bound scan/referrer, authenticated non-expired rollback-protected revocations, compatibility and exact immutable content. The scanner currently hashes unpacked input; that is not yet a signed OCI digest-bound scan proof.
3. Bind the verified artifact bytes and digest to the owner's reviewed action plan, and have the actual gateway executor consume those exact bytes before kubectl. No install from a mutable tag or later-mutated catalog directory. Preserve existing sandbox, scan, owner-approval and lifecycle guards.
4. Add end-to-end regressions for unsigned, wrong signer, revoked key/plugin, stale/forged scan, expired/rolled-back list, wrong digest, retagging and post-review mutation. Include a successful private-tier approved install with real cryptographic fixtures.
5. Review and merge remain Claude-owned. Production root/store keys, publishing credentials or changes to locked decisions require Zeus; generated in-memory test keys are not production provisioning.

## Remaining lane work after those priorities

| Issue | State and concrete remainder |
| --- | --- |
| #177 | Builder implementation and CI fixes consolidated; needs gate review/merges, not more foundation PRs |
| #178 | Builder implementation consolidated and native-suite verified; needs gate review/merges and integration checks |
| #180 | Packaging/signing and owner trust drafted; trusted verify/install integration above remains |
| #179 | Build immutable verified UI delivery, opaque iframe host, scoped postMessage bridge, CSP and source checks |
| #181 | Settings-only init exists; backend/widget templates and live dev workflow remain |
| #182 | Client drafted; boot/six-hour scheduling, safe stopping, immediate tool/widget denial, audited override and countersignatures remain |
| #183 | Real bundle malware scan drafted; OCI artifact-bound signed scan records and install enforcement remain |
| #184 | Implement conformance harness and plugin test CLI |
| #185 | Implement OIDC publish, public index and review pipeline; no publication/production credentials provisioned |

None of these issue rows is a claim of merged completion. Confirm issues, PR heads and CI on GitHub at resumption. Work only in Codex-owned worktrees, preserve local edits, use signed-off commits, never merge or push main, and never start parked robotics work.
