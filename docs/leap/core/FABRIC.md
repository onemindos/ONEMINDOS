<!-- SPDX-License-Identifier: Apache-2.0 -->
# Fabric: many machines, one OneMind (CORE-FABRIC)

**Date:** 2026-11-12 · **Status:** proposal · **Plan epic:** E12 (Fabric v0), parts of E13 · **Deeper docs:** `docs/architecture/FABRIC.md` (architecture stream, branch `docs/core-architecture`, in progress); [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md) §5; research 12 §9–§10 · **Serves:** contract §1–§2; brief 30 D-B6.2, D-B6.5, D-B6.6; core-alignment FAB-P1…P3, FAB-B1…B3; hardening H-06, H-23.

> **Explain it like I am the founder**
> A second machine joins your OneMind by showing a short code; the join appears in Approvals with what the machine is, and you approve it with your passkey.
> On approval the box gives that machine its own identity: a one-hour join ticket for k3s and its own bus credentials that can only speak for itself.
> Apps then run only on machines that can actually run them, and small or remote machines can be "leaves" that keep working when the hub is away.

## 1. Goals and non-goals

| Goals | Non-goals (now) |
|---|---|
| Owner-approved join (`node.join` action), QR or short code, ≤ 1 h single-use credentials | Federation between separate households or sites (research 12 §11.2, later) |
| Per-node identity: NATS nkey user + certificate from the box CA | Storage pooling across nodes (plan §6) |
| Remove and drain a node (`node.remove`) | High-availability control plane (3 servers + etcd) before the single-box path is proven |
| Placement: apps only on nodes whose capabilities match `requires` | Robots and drones as nodes (later; same join path) |
| Leaf nodes (NATS leaf, no k3s) that tolerate the hub being away | Mirror/warm standby (Z-13, year 1) |
| Read-only fleet view; installer-mode nodes labelled honestly | |

## 2. What exists today

| Piece | Where | State |
|---|---|---|
| Heartbeat `onemind.node.<node_id>.status` every 10 s; stale 30 s, offline 120 s | `internal/heartbeat/`, `core/onemind_core/nodes.py` | `main` |
| Board and capability detection | `internal/detect/` | `main` |
| Nodes screen, `onemind nodes` | `dashboard/src/pages/Nodes.tsx`, `cmd/onemind/main.go` | `main` |
| `install.sh --role node --hub … --token …` with an agent-only k3s token | `deploy/install.sh` | `feat/deploy-v0`; token long-lived, printed, no approval |
| Optional `update` object in heartbeat | `internal/heartbeat/` | `feat/onemindd-updater` |

## 3. Design

### 3.1 Join flow (CORE-FABRIC-1)

```
new machine                         hub gateway                         owner phone
onemind fabric join 7KQ4-M2XP-9D --hub https://onemind.local:8443
  └─ POST /v1/fabric/join-requests {heartbeat, pubkey} ─► action node.join (awaiting_approval)
     prints code "K7-4QX"                                  └─ alert ─────────────────────► Approvals card:
                                                                                           board, arch, OS, code
  ◄── poll GET /v1/fabric/join-requests/{id} ────────────── accepted ◄── passkey approve ──┘
  receives: k3s agent token (TTL 1 h, single use), NATS nkey user for this node only, node cert
```

The join code comes from a ticket the owner made with `onemind fabric qr` or the dashboard (`POST /v1/fabric/join-tickets`, [API.md](../dev/API.md) §5.1). It is single-use, lives at most 1 hour and carries the hub CA fingerprint the node pins. Routes and bodies follow API.md §5.1; the short match code (`K7-4QX`) is what the owner compares on the phone.

**On the new machine:**
```console
$ sudo onemind fabric join 7KQ4-M2XP-9D --hub https://onemind.local:8443
Hub         onemind.local (CA pinned)
This node   x86_64-efi · amd64 · Debian 13 · 16 GB
Code        K7-4QX   ← check this matches the card on your phone
Waiting for the owner to approve… approved by person:owner
k3s agent   joined (ticket expired after use)
NATS        connected as node 3f9c2a1b7d4e (publish: own status only)
Done. This node is a worker. Installer mode: no OS rollback on this machine.
```

**The request (contract change: new action type and route):**
```http
POST /v1/fabric/join-requests
{"heartbeat": {"schema": "onemind.node.status/v1", "node_id": "3f9c2a1b7d4e", "board": "x86_64-efi", …},
 "node_pubkey": "UDXU…", "code": "K7-4QX"}
→ 201 {"join_request_id": "jr_81", "action_id": "a_9c", "state": "awaiting_approval", "expires_at": "…+15m"}
```
The join-request route is unauthenticated but rate-limited and capped (H-20); it can only create an `awaiting_approval` action, never credentials. Credentials are fetched once, by the holder of the node's private key, after approval.

**SDK (proposed shapes):**
```python
for n in client.nodes.list(): print(n.node_id, n.status, n.capabilities.gpu)        # Python
```
```ts
const pending = await om.actions.list({ type: "node.join", state: "awaiting_approval" }); // TypeScript
```
```go
nodes, _ := om.Nodes.List(ctx)                                                     // Go
```
**MCP:** agents can read `list_nodes`; they can request `node.remove` (owner approves); they can never create join requests or receive credentials.

### 3.2 Node identity (CORE-FABRIC-2)
Each node has a principal `node:<node_id>`, an nkey user that may publish only `onemind.node.<node_id>.status` (H-06), and a box-CA certificate used for `onemindd` ↔ hub calls. Revoking the node revokes all three.

### 3.3 Remove and drain (CORE-FABRIC-3)
`node.remove` action: cordon, drain with a timeout, delete the k8s Node, revoke identity. Apps with local volumes on that node block removal until the owner chooses "move data" (BACKUPS restore onto another node) or "delete data" (separate destructive action).

### 3.4 Placement (CORE-FABRIC-4)
`onemindd` publishes NodeCapabilities (brief 30 D-B6.6) and the gateway labels nodes `onemind.io/cap.arch`, `cap.mem-gb`, `cap.gpu=nvidia`, `cap.board`. The executor adds node affinity from the manifest's `requires`. The Market shows a verdict per node before install:

| Verdict | Meaning |
|---|---|
| ✓ fits | arch, memory and GPU match on at least one node |
| ! tight | fits but would leave < 15 % memory |
| ✗ no node | name the missing capability ("needs 16 GB GPU memory") |
| ? unknown | node data stale; never shown as fitting |

### 3.5 Leaf nodes (CORE-FABRIC-5)
Machines too small or too remote for k3s run `onemindd` + a NATS leaf (JetStream domain per node) and no k3s. They buffer their own heartbeats and events when the hub is unreachable and sync back (leaf outage test from brief 30 D-B6.5 must pass). The Nodes screen labels them `leaf` and shows the last sync time.

### 3.6 Fleet view (CORE-FABRIC-6)
One read-only screen: every node with role, status, slot and version, update state, backup state and apps. Nothing identifying on screen beyond hostname (no serials, MAC or IP addresses, contract §2). Installer-mode nodes carry a grey "no OS rollback" label.

## 4. Security model

| Risk | Control |
|---|---|
| Leaked join token lets any machine join forever | No standing token; each join is an owner-approved action; k3s ticket TTL 1 h, single use (`k3s token create --ttl 1h`) |
| Node impersonates another on the bus | nkey per node, publish permission only on its own subject |
| Man-in-the-middle at join | CA fingerprint pinned on the command line or from the QR; matching code shown on both screens |
| Agent joins a rogue node | Agents cannot call the join route's credential fetch; `node.join` approval needs a passkey |
| Worker holds cluster admin | Agent-only k3s role; no admin kubeconfig on workers (D-B6.2) |

## 5. Versioning and compatibility
- Heartbeat stays `onemind.node.status/v1`; new optional fields (`capabilities`, `role: hub|worker|leaf`, `update`) are additive.
- Nodes installed with the v0 long-lived token keep working; `onemind fabric join --migrate` re-issues per-node identity, after which the old shared NATS access is refused (one release of overlap).
- New action types `node.join`, `node.remove` and the `/v1/fabric/*` routes go into contract §3 in one PR.

## 6. Test plan and acceptance

| Test | Pass when |
|---|---|
| Three machine classes (x86 mini PC, Pi 5, a VM) join | Each in under 2 minutes from command to "Done" (plan E12) |
| Expired ticket | Join with a ticket older than 1 h fails; reuse after first use fails |
| No approval | A join request without approval never receives credentials; it expires after 15 minutes |
| Impersonation | Node A's credentials publishing as node B → permission violation; hub's entry for B unchanged |
| Placement | An amd64-only app is never scheduled on an arm64 node; verdict ✗ shown |
| Leaf outage | Hub offline 30 minutes → no loss of buffered leaf events after reconnect |
| Privacy | Fleet view screenshot contains no IP, MAC or serial |

## 7. Build steps

| Epic | Step | Effort | Depends on |
|---|---|---|---|
| CORE-FABRIC-1 | `node.join` action, join route, `onemind fabric join`, QR in dashboard | M | SEC-1, SEC-2, SEC-4 |
| CORE-FABRIC-2 | Per-node identity (nkey, cert, principal) and revocation | M | 1 |
| CORE-FABRIC-3 | `node.remove` with drain | S | 2 |
| CORE-FABRIC-4 | Capabilities labels, affinity from `requires`, Market verdict | M | – |
| CORE-FABRIC-5 | Leaf mode in `onemindd` (no k3s) | M | 2 |
| CORE-FABRIC-6 | Fleet view (read-only) | S | 1, UPDATE-3, BACKUP-7 |

## 8. Who owns which files

| Branch (proposed) | Files |
|---|---|
| `feat/fabric-join` | new `core/onemind_core/fabric.py`, new `internal/join/`, `cmd/onemind/cli/fabric.go` (with DEV-CLI-8), `deploy/install.sh` (`k3s_server` token mode) |
| `feat/placement` | `internal/detect/` (capabilities), `core/onemind_core/executors.py` (affinity), `dashboard/src/pages/Market.tsx` verdict |
| `feat/leaf-node` | new `internal/leaf/`, NATS leaf config template under `deploy/` |
| Hotspots (serialized) | `cmd/onemindd/main.go` (`join`, `leaf` subcommands), `core/onemind_core/app.py`, contract §2–§3 |
