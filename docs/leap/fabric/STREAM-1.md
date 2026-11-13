<!-- SPDX-License-Identifier: Apache-2.0 -->
# Fabric stream 1: "prove the site" (FAB-1, FAB-2, FAB-3)

**Date:** 2026-11-12 · **Status:** ready for a builder · **Epics:** [EPICS.md](EPICS.md) FAB-1, FAB-2, FAB-3 (FAB-4 may follow) · **Phase/gate:** F1, FG1, 180-day plan P3 / G4 · **Serves:** FB-R1, FB-R2, FB-R5, N-6, M-2; D-007; open Z-34/F-32, ZF-05, ZF-11 · **Branch (proposed):** `feat/fabric-gate`

> **Explain it like I am the founder**
> The join, the private network and the leaf code already exist. What is missing is **proof** and **a small shared vocabulary**. This stream does three things: (1) adds the words every later step needs (`site_id`, a node's role in its heartbeat) without changing anything that exists; (2) writes one test suite proving a machine can join only with your approval and can never speak as another machine; (3) runs the machine-to-hub link for a week under the exact permissions we ship, because the research found open bugs near that code and one unproven case (stream copying under restricted permissions). Nothing new for you to see; the result is a green gate that lets us say "supported" honestly.

## 1. Scope
**In:** FAB-1 (contract text plus two additive fields), FAB-2 (conformance suite, positive and negative), FAB-3 (leaf soak harness and result record).
**Out:** FDO, adapters, fleet hub, rings (later epics); new UI; changing any subject that exists today; installer mode (FAB-4, the next stream).

## 2. What exists (reuse, do not rewrite)
Read from `origin/main` and `origin/feat/net-part2` on 2026-11-12.
| Piece | Where | State |
|---|---|---|
| Heartbeat, detection | `internal/heartbeat/`, `internal/detect/`, `core/onemind_core/nodes.py` | `main` |
| Mesh client (enroll, status, no addresses in heartbeat) | `internal/mesh/` (`TestHeartbeatCarriesNoAddresses`, `TestEnrollWritesKeyFileOnlyDuringUp`) | `main` |
| NATS leaf config render, supervise, TLS + nkey tests | `internal/leaf/` (`TestLeafConnectsOverTLSWithNodeNkey`, `TestLeafRefusedWithoutValidCredentials`) | `main` |
| Per-node NATS accounts, golden hub config, leaf monitor | `internal/leaf/accounts_test.go` (`TestPerNodeAccountsIsolateNodes`, `TestNodeKeyIsLeafOnly`), `monitor.go`, `testdata/hub-accounts.golden.conf`; `core/onemind_core/natsconf.py` | `feat/net-part2` |
| Join: tickets, requests, approval, credential delivery, rate limit | `core/onemind_core/fabric.py`, `routers/net.py`, `internal/fabric/join.go`, `cmd/onemind/cli/fabric.go`; `core/tests/test_net.py` (end to end, denied, expired, agent cannot file `node.join`, restart during approval) | `feat/net-part2` (no PR open when checked) |
| Lima lab: hub + node, owner-approved join to an HTTPS app | commit `8922521` | `feat/net-part2` |

**Precondition:** `feat/net-part2` is merged (or this branch is cut from it). Do not duplicate its tests; the suite below wires them to requirement tags and adds what they lack.

## 3. Contract changes (FAB-1, additive only)
1. Heartbeat `onemind.node.status/v1` gains optional `fabric: {role: "hub"|"worker"|"leaf", site_id: string}`. Heartbeats without it stay valid; the gateway shows a missing role as `worker`.
2. `site_id`: generated once on the hub at first boot (random, 12 hex), stored in box state, returned by `GET /v1/fabric/site` (owner and agents may read), included in the join bundle so a joining node pins it.
3. Reserved, not used yet: subject prefix `onemind.site.<site_id>.` and the address grammar `site/node/device/capability`, written into contract §12 (naming). No publisher or subscriber is added.
4. `node.join` (risk `sensitive`) and `node.remove` (`destructive`) listed in the action-type table if net-part2 has not already done so.
Files: contract draft, `sdk/contracts/` schema, `core/onemind_core/nodes.py` (accept field), `internal/heartbeat/` (emit field), OpenAPI snapshot. Hotspot edits are one line each ([NEXT-WAVE.md](../NEXT-WAVE.md) §1).

## 4. Tests
### 4.1 Conformance suite (FAB-2)
Location: `core/tests/fabric_gate/` (Python, SQLite, fake clock and fake Headscale as in `test_net.py`) and `internal/fabric/gate_test.go` (Go, embedded `nats-server` as in `internal/leaf`). Test names carry the requirement tag (`FBR1_`, `FBR2_`).
| Test | Pass when | Reuses |
|---|---|---|
| FBR2_no_approval_no_credentials | Request waits; no credentials in any response, file or log until approval; expires after 15 min | `test_unapproved_request_expires`, `test_denied_join_gets_nothing` |
| FBR2_agent_cannot_join_or_collect | An agent principal cannot create a join request, approve one or fetch credentials | `test_agents_cannot_file_node_join` |
| FBR2_ticket_single_use_and_ttl | Reuse and past-TTL refused (`ticket_used`, `expired`) | `test_revoked_ticket_cannot_join` |
| FBR2_wrong_ca_pin | Node refuses credentials from a hub whose CA fingerprint differs | `TestPinRefusesAnotherCA` |
| FBR2_node_key_mismatch | Credential fetch by a holder of a different private key fails | new |
| FBR1_node_cannot_speak_as_other | With node A credentials, publishing to `onemind.node.B.status`, `onemind.audit` or `onemind.node.A.job.x` is a permission violation; B's entry unchanged | `TestPerNodeAccountsIsolateNodes` (extend with these subjects) |
| FBR1_leaf_without_credentials_refused | Refused | `TestLeafWithoutCredentialsIsRefused` |
| FBR1_class_rows | One parametrized test per supported join-matrix row (1 mini PC/Pi, 2a cloud VM image, 2b stock Debian/Ubuntu, 3 company server): join, then heartbeat `fabric.role` is correct. Rows needing real VMs are marked `vm` and run in the existing VM CI tier | new |
| FBR1_heartbeat_compat | Heartbeat without `fabric` parses; with it, `site_id` equals the hub's | new (FAB-1) |
| FBR2_privacy | Node and mesh views hide IP, MAC and serial by default | `test_mesh_view_hides_addresses_by_default` |
| FBR1_duplicate_machine_id | Second join refused, repair alert raised (FT-10) | new if absent |

### 4.2 Leaf soak (FAB-3)
A harness (`scripts/lab/fabric-leaf-soak.sh` plus a Go driver in `internal/leaf/soak/`; short mode in CI, full mode by hand on Lima or the Pi 5 kit) that:
1. renders the **production** hub and leaf config from `natsconf.py` and `internal/leaf` (no relaxed test permissions);
2. publishes node events and heartbeats continuously, plus **request/reply across the leaf** (untested so far under per-node permissions);
3. records the `$JS.*` subjects JetStream sourcing from leaf to hub needs and whether it works under the permissions (NT-6 extension);
4. cuts the link for 30 minutes at intervals, then checks events arrive in order with no duplicates;
5. writes `research-output/evidence/lab/fabric-leaf-soak/RESULT.md`, with pass/fail written before the run (pre-registration, as the other labs).

CI short mode: 10 minutes, one cut. Full mode: 7 days (founder-run). Pass: zero permission violations from legitimate traffic; zero lost or duplicated events; request/reply works; the sourcing question is answered either way. If sourcing fails, write the gap as an ADR and a ZF-11 note for Zeus; never widen permissions silently.

## 5. Security review points for the builder
- `site_id` is not a secret and never authorizes anything; no endpoint treats it as a credential.
- No credential, nkey seed, join code or ticket in logs, test output or committed lab logs (public repo; run gitleaks; mask addresses).
- Negative tests must fail closed when the fake Headscale or NATS is down.
- The soak driver uses generated keys only, deleted after the run.
- Agents can list nodes and request removal; they never create join requests or receive credentials.

## 6. Done when
Suite green in CI; STATUS rows for FAB-1, FAB-2, FAB-3 updated; `docs/testing/TEST-REGISTER.md` has a row per test tag; CHANGELOG entry; soak short mode green and the full-run instructions in the lab README; contract §12 text merged with the additive fields; any net-part2 defect found filed as a fix PR.

## 7. Order of work (about 3 weeks, one builder)
1. Days 1 to 2: FAB-1 fields and contract text. 2. Days 3 to 8: conformance tests (4.1). 3. Days 9 to 13: soak harness and CI short mode. 4. Day 14: hand the 7-day run to Zeus's kit and write up. Next stream: FAB-4 (installer mode).
