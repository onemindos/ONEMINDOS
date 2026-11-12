<!-- SPDX-License-Identifier: Apache-2.0 -->
# Fabric: several machines, one OneMind

**Status:** design for build agents (2026-11-12). API in [CONTRACT-12-DRAFT.md](CONTRACT-12-DRAFT.md) §12.4.
**Backlog:** core-alignment items 15 (FAB-P1, FAB-P2), 16 (FAB-P3, APP-B3), 23 (OSU-B1); also FAB-B1, FAB-B3.
**Builds on:** contract §1–§3; brief 30 D-B6.2 (agent-only nodes), D-B6.5 (NATS, leaf, JetStream), D-B6.6 (capabilities); research 09 §5.1 and W8-R2 (leaf store-and-forward lab, 600/600); research 12 §9.1 and §10.2 (Nodes app, QR join); hardening backlog H-06 (NATS auth) and H-23 (owner-approved join).

> **In plain words.** You add a machine by showing a QR code on the dashboard and running one command on the new machine. The new machine asks to join; you see exactly what it is and approve it. It then gets its own keys, joins Kubernetes as a worker (or stays a light "leaf" with no Kubernetes), and reports in every 10 seconds. If it goes quiet, the screens say so honestly. Removing it is one approved action that also cancels all its keys.

## 1. Requirements

| ID | Requirement | Source |
|---|---|---|
| F-R1 | A machine joins from the dashboard (QR code) or headless (`onemind node join`), with no long-lived shared secret | FAB-P1, REC-W11-16 |
| F-R2 | Joining needs the owner's approval of the exact machine (board, arch, OS, short code) | H-23 |
| F-R3 | Each node has its own identity: a key pair it generated, a certificate from the box CA, and its own NATS credentials limited to its own subjects | FAB-B3, H-06 |
| F-R4 | Worker nodes join k3s as agents only: no datastore, no admin kubeconfig | D-B6.2 |
| F-R5 | Leaf nodes (small or remote machines) run without k3s and keep working when the hub is unreachable; their events are buffered and synced later | FAB-B1, W8-R2 |
| F-R6 | Nodes show `online`, `stale` or `offline` from heartbeats on the hub's clock (30 s / 120 s, contract §3), plus join, drain and degraded states; nothing stale is shown as live | contract §3, UX-B3 |
| F-R7 | Drain and remove a node through approval; removal revokes every credential | FAB-P2 |
| F-R8 | Apps are placed only on nodes whose capabilities match the manifest's `requires`; the Market says per node why an app does or does not fit | FAB-P3, APP-B3 |
| F-R9 | OS updates can roll out canary first across nodes, gated by each node's health-gate verdict | OSU-B1 |
| F-R10 | All traffic between nodes is authenticated and encrypted | H-06, H-17 |

## 2. Roles

| Role | Runs | Who should have it | Contract §1 value |
|---|---|---|---|
| **hub** | k3s **server**, NATS hub (JetStream), gateway + dashboard, `onemindd` (incl. key custodian) | the always-on box with the most disk | `hub` |
| **worker** | k3s **agent**, `onemindd`, local NATS leaf | other always-on machines that run apps | `node` (kept as an alias of `worker`) |
| **leaf** | `onemindd`, local NATS leaf; **no k3s** | Pi with < 4 GiB, a laptop, a remote or intermittently connected machine | new |

Phase 1 has **exactly one hub**. A second hub is the HA phase (§9), not a role toggle.

**Role changes** (worker ↔ leaf) are an action (`node.set_role`) that runs drain first. Hub ↔ worker is not offered in phase 1; moving the hub is "restore the box onto another machine" (BACKUPS.md §7.3).

## 3. Identity and keys

**Node id:** unchanged from contract §1 (sha256 of `/etc/machine-id`, first 12 hex characters). It is a name, not a credential. Cloned disks share a machine-id. So a join with an id that already belongs to another node's key is refused (`409 conflict`, reason `duplicate_node_id`), and a repair tells the owner to regenerate the machine-id (`systemd-machine-id-setup` after deleting `/etc/machine-id`).

**Keys a node creates itself at first start** (`onemindd`, stored under `/data/onemind/identity/`, mode 0600, root):
- `node.key`: an Ed25519 key. It signs join requests and identifies the node to the hub. Its public half is the node's real identity.
- `tls.key`: an ECDSA P-256 key for TLS. P-256, because every TLS stack and browser accepts it.
- `nats.nk`: a NATS user NKey seed. NKeys are NATS's Ed25519 public-key login (no password on disk).

Private keys never leave the node. The hub signs only public halves. Where `tpm2: true` (heartbeat), sealing the keys to the TPM is phase 3.

**Keys the hub holds** (the **key custodian** in hub `onemindd`, `/data/onemind/custodian/`, 0600, root):
- the **box CA** (ECDSA P-256, 10 years), the same CA that SEC-P2 uses for HTTPS on the LAN;
- the **NATS account signing key**, used from fabric phase F3 on (§5.2);
- the gateway's **job-signing key** (Ed25519). Its public half is given to every node at join (§5.4).

**Why a custodian separate from the gateway:** the gateway faces the network and runs as an unprivileged user. A bug in it should not leak the CA. The gateway asks the custodian over a root-owned Unix socket (`/run/onemind/custodian.sock`, group `onemind`) to sign, and the custodian signs only for a `node.join` or `node.renew` that the ledger shows as approved. The custodian reads the ledger read-only to check that.

**Certificates:**
- Node certificate: 30 days, SAN = `node-<node_id>.onemind.internal` plus the hostname. `onemindd` renews it at two thirds of its life over mutual TLS (`POST /v1/fabric/nodes/{id}/renew`). Renewal is not an action: it changes nothing the owner did not already approve. It is audited.
- **Revocation** is "stop renewing, plus a deny-list entry until expiry". Short lives make a CRL unnecessary.
- The hub's own server certificate has SANs for `onemind.local`, the box name and every hub address the owner adds. Nodes pin the **CA**, not the address, so a hub that changes IP keeps working.

## 4. Joining

### 4.1 Flow

```
 Owner (dashboard / CLI)            Gateway (hub)                       New machine
 ───────────────────────            ─────────────                       ───────────
 "Add node" → POST /v1/fabric/join-tickets {role, ttl}
                                    ticket: 128-bit random, single use,
                                    TTL ≤ 60 min (default 15), stored hashed
 QR: onemind-join:v1?hub=<url>&ca=<sha256 of CA>&t=<ticket>&role=worker
                                                                        onemind node join <qr text or URL>
                                                                        (or scan with the phone app, which shows the text)
                                                                        - TLS to hub, CA pinned from the QR
                                                                        - creates keys (§3)
                                                                        - POST /v1/fabric/join {ticket, node_id, pubkeys,
                                                                          heartbeat snapshot, signature by node.key}
                                    ticket checked and consumed
                                    action node.join created,
                                    requested_by {kind: node}
                                    → awaiting_approval, notify owners
 Approvals card: hostname, board, arch, OS, CPU, memory, disk,
 role, ticket creator, and a 6-digit pairing code
                                                                        console shows the same 6-digit code and waits
 Owner compares the code, approves (passkey when available)
                                    custodian signs certs + NATS creds;
                                    k3s token create --ttl 15m (worker)
                                                                        polls GET /v1/fabric/join/{join_id} (signed),
                                                                        receives bundle once:
                                                                        - node certificate + CA
                                                                        - NATS credentials (public parts signed)
                                                                        - job-signing public key
                                                                        - k3s server URL + bootstrap token (worker)
                                                                        writes config, starts NATS leaf, k3s agent
                                                                        first heartbeat via its leaf
                                    node.join → succeeded when the first heartbeat
                                    and (worker) the k3s Node object are seen
```

- **Pairing code:** `sha256(ticket_id ‖ node public key)`, first 4 bytes read as a big-endian unsigned integer, modulo 1 000 000, shown as 6 digits with leading zeros. Both sides compute it, so the owner can tell that the machine they approve is the one in front of them. This is the Bluetooth pairing pattern. It defends against a leaked ticket being used by another machine first.
- **Why approval and a ticket:** the ticket alone only lets a machine *ask*. That stops strangers on the LAN from filling the Approvals screen. The approval decides. A ticket from a QR code photographed off the screen is harmless without the owner's approval of a matching code.
- **Headless:** `onemind node join --hub https://<hub> --ticket-file <file> --ca-sha256 <hex>`. The ticket is read from a file or stdin, never a command-line argument, so it stays out of shell history and `ps` (H-09). The owner approves with `onemind actions approve <id>` on any machine that has an owner session.
- **k3s bootstrap token:** `k3s token create --ttl 15m --description onemind-node-<node_id>`. k3s's `token create` takes `--ttl` (default 24 h; `pkg/cli/cmds/token.go` in `k3s-io/k3s`, Apache-2.0, read at `f6973cb`). It replaces the long-lived agent token that `feat/deploy-v0` prints today. **UNVERIFIED** until step F2's test: that a bootstrap token created this way is accepted by `k3s agent` on v1.37.2+k3s1. If it is not, the fallback is the agent token sent once inside the approved bundle (still never printed).
- **The node's k3s config:** `node-name: node-<node_id>`, labels `onemind.io/node-id`, `onemind.io/role=worker` and the capability labels (§7), `node-taint` none. The node name is fixed, because local-path volumes are pinned to node names (brief 30 B6, C-W5-019).

### 4.2 What the competitors do, and what we keep

| Who | Join | Licence (as read) | What we take |
|---|---|---|---|
| Olares | `olares-cli node add` / `join`, k3s with external etcd (`cli/cmd/ctl/node/add.go`, `join.go`) | AGPL-3.0 + non-commercial (`beclab/Olares` `e7fe1c96`) | Pattern only: a CLI join that is a first-class command |
| Cosmos | Servers linked by NATS + Nebula VPN (`src/constellation/`) | Apache-2.0 + Commons Clause (`69c5303`) | Pattern only: NATS as the inter-node link |
| k3s | Bootstrap tokens with TTL | Apache-2.0 | We call it; no code copied |
| Proxmox | Any node shows the whole cluster | AGPL-3.0 | Pattern: every hub page shows all nodes |

None of them shows the joining machine to the owner and asks for approval with a pairing code. That is the beat (H-23 + FAB-B3).

## 5. Messaging topology (NATS)

### 5.1 Shape

- The **hub NATS** is the authority bus (contract §1, research 09 §2.2). It runs JetStream for the core streams (CONTRACT-12-DRAFT §12.3).
- **Every worker and leaf runs its own small NATS server as a leaf node** connected to the hub's leaf port 7422 over TLS with the node's credentials. `onemindd` and local apps on that node connect to `nats://127.0.0.1:4222`, never across the network.
- **Why a local leaf on every node:**
  1. When the hub is unreachable, the node keeps its events in a local JetStream stream and syncs them later. The lab showed 600/600 delivered after an outage with this setup, and that plain core-NATS publishes during the outage are lost ([C-W8-050], research 09 §5.1).
  2. The only connection that leaves the machine is one authenticated TLS link.
  3. It is the same shape as the founder's current edge pattern, so nothing new has to be learned.
- **Cost:** a NATS server idles at a few tens of MiB. Step F3's test measures it on a Pi 5 and records the number; if it is too high for leaf-class hardware, a leaf may connect directly with its credentials and lose buffering (labelled in the UI).

### 5.2 Authentication and permissions

**Phase F1 (H-06 as written):** the hub's `nats.conf` gets an `authorization` block with NKey users: `gateway`, `custodian`, and one user per node. The gateway writes `/data/onemind/nats/users.conf` and signals a reload (`nats-server --signal reload`).

**Phase F3 (leaf nodes):** move to NATS **operator/JWT mode** with one `CORE` account. The custodian signs a user JWT for each node, and the leaf remote uses a `.creds` file. Leaf remotes with credential files are NATS's documented path. **UNVERIFIED:** per-user permissions applied to a leaf connection on nats-server v2.15.2. Step F3 starts with a lab test of exactly that, and the fallback is F1's config users (with the leaf's account bound to the node user).

**Node permissions** (both phases; `<id>` is the node id):

| Allow | Subjects |
|---|---|
| publish | `onemind.node.<id>.status`, `onemind.node.<id>.event.>`, `onemind.node.<id>.jobresult.>`; JetStream pull on its own consumer, which is a publish request: `$JS.API.CONSUMER.MSG.NEXT.ONEMIND_JOBS.node-<id>`; acks `$JS.ACK.ONEMIND_JOBS.node-<id>.>` |
| subscribe | `_INBOX.>` (pull replies arrive on the request's inbox) |
| deny | everything else, notably `onemind.audit`, `onemind.event.>`, other nodes' subjects, `onemind.node.<id>.job.>` (only the gateway publishes jobs) |

So node A cannot pretend to be node B, cannot forge audit lines and cannot hand itself work. The gateway re-publishes each validated node event to `onemind.event.<domain>.<name>` with `source_id` set to the node id. Consumers then read one stream and the source cannot be forged.

### 5.3 What travels where

| Subject (CONTRACT-12-DRAFT §12.3) | From → to | Buffered on the leaf during an outage? |
|---|---|---|
| `onemind.node.<id>.status` | node → hub, every 10 s | **No.** It is state, not history; the last one wins. Stale is the honest answer during an outage |
| `onemind.node.<id>.event.<domain>.<name>` | node → hub | **Yes**, stream `ONEMIND_NODE_OUTBOX` on the leaf (domain `node-<id>`), sourced by the hub, limited to 7 days or 256 MiB |
| `onemind.node.<id>.job.<kind>` | gateway → node (stream `ONEMIND_JOBS`) | Held on the hub; each job carries `expires_at` and is dropped, not run, when late (W8-R2 rule 3) |
| `onemind.node.<id>.jobresult.<job_id>` | node → hub | Yes, through the outbox |

### 5.4 Jobs: how the gateway asks a node to do host work

The gateway has the Kubernetes credentials; nodes have the files. Backups, restores, update installs, "leave the fabric" and host checks are **jobs**:

```json
{"schema": "onemind.job/v1", "job_id": "job_01JC…", "action_id": "…", "kind": "backup.run",
 "params": {…}, "params_sha256": "…", "issued_at": "RFC3339", "expires_at": "RFC3339",
 "sig": "<Ed25519 over canonical JSON without sig, by the gateway job key>"}
```

`onemindd` runs a job only if: the signature verifies with the job key it received at join; `expires_at` is in the future (with ≤ 60 s skew allowed); `job_id` is not already in its local done-list (`/data/onemind/jobs/done`, kept 30 days); and `kind` is one it supports. Results go to `onemind.node.<id>.jobresult.<job_id>` with `state: running | succeeded | failed` and a summary. The NATS permissions already stop anyone else from publishing jobs. The signature is a second, independent lock: a misconfigured NATS server alone cannot make a node act.

## 6. Health, states and what the gateway shows

### 6.1 Node states

| State | Meaning | Derived from |
|---|---|---|
| `joining` | `node.join` awaiting approval or not yet first heartbeat | ledger |
| `online` | heartbeat ≤ 30 s old (hub clock) and no degradation | contract §3 |
| `degraded` | online, but at least one of: k3s not ready (worker), disk free < 10 %, certificate expiring in < 7 days, clock skew > 60 s, outbox lag > 0 for > 10 min | heartbeat + Kubernetes Node condition |
| `stale` | last heartbeat 30–120 s ago | contract §3 |
| `offline` | > 120 s | contract §3 |
| `draining` / `drained` | after `node.drain` | ledger + Kubernetes cordon |
| `removed` | after `node.remove`; kept 30 days for the audit trail, then hidden | ledger |

`degraded` comes from the heartbeat itself, so it can only be shown while the node is online. A stale or offline node shows its **last known** values greyed out with their age.

**Kubernetes and heartbeat disagree** (heartbeat online, Node `NotReady`, or the opposite): the card shows both facts side by side, with neither hiding the other. Lying by summarising is the failure the contract's freshness rule exists to prevent.

**Clock:** the hub stamps `received_at` on each heartbeat; skew = `received_at − observed_at`. Ages are always computed from `received_at`.

### 6.2 Heartbeat additions (CONTRACT-12-DRAFT §12.11)

`fabric: {role, leaf_link: up|down|none, outbox_pending, cert_expires_at}`, `backup: {running, last_run_at, last_result}`, and the updater's `update` object (`feat/onemindd-updater`).

### 6.3 What the screens show

- **Nodes:** one card per node: role, board, arch, OS, k3s state, slot, update state, backup state, apps placed on it, state pill with age. Actions: drain, uncordon, remove, change role, "show join QR".
- **Home:** counts per state; any node not `online` is a line with its age.
- **Market / app page:** the per-node fit verdict (§7).
- **Phone (MOB-P1):** the same Nodes list, cached and labelled with its age when offline (MOB-B2).
- **`onemind nodes`** prints the same states.

Alerts (NOTIFICATIONS.md §3): `node.offline` (raised after 120 s, resolved on return), `node.degraded` with the reason (including `clock_skew` and `outbox_full`), `node.cert_expiring`. **Stale alone never alerts**, so a Wi-Fi blip does not page anyone.

## 7. Placement (FAB-P3, APP-B3)

- `onemindd` reports capabilities in the heartbeat (`arch`, `mem_total_mb`, `gpu`, `board`, disk). The gateway mirrors them as Kubernetes node labels `onemind.io/cap.arch`, `onemind.io/cap.mem-mb`, `onemind.io/cap.gpu`, `onemind.io/cap.board` (brief 30 D-B6.6; NFD later).
- **Verdict per node and app**, computed by the gateway: `fits`, `fits_with_warning` (e.g. memory above 75 % after install), `no` with reasons (`arch_unsupported`, `not_enough_memory`, `needs_gpu`, `node_not_ready`, `leaf_has_no_k3s`).
- **Choice at install:** the owner picks a node, or "best fit" (most free memory among `fits`). The chosen node goes into the app's **revision** (DEPLOYMENTS.md §4) as a `nodeAffinity` term, and the approval card shows it.
- **Local volumes pin the app.** An app with data on `onemind-local` lives on its node. Moving it is a **move** = back up, restore on the new node, verify, switch (`app.move`, phase F5). It is never a silent reschedule. A drain that would strand such an app says so before approval.

## 8. Drain, remove, leave

- `node.drain {node_id}`: the gateway cordons the node and evicts pods (`kubectl drain --ignore-daemonsets --delete-emptydir-data --timeout=5m`). The plan lists every app on the node and marks those that **cannot move** (local volumes) as "will be stopped". Result: `drained`, or `failed` with the pods that would not leave.
- `node.uncordon {node_id}`.
- `node.remove {node_id, wipe: bool}`: requires `drained` (or `offline` for more than 24 h, for dead machines). Steps:
  1. revoke: deny-list the certificate, remove the NATS user, delete its job consumer;
  2. `kubectl delete node`;
  3. if `wipe` and the node is reachable, a `node.leave` job makes it delete its credentials and stop k3s and its leaf;
  4. the ledger keeps the node row as `removed`.
- Dead-machine removal never waits for the dead machine.

## 9. Replacing a three-node cluster: what the founder gets, phase by phase

A typical self-run setup has three managed Kubernetes nodes, GitOps (an Argo-style controller), a three-node NATS JetStream cluster, an ingress controller with a tailnet ingress, sealed secrets and backup CronJobs. The honest mapping:

| Today | OneMind phase 1 (this doc + siblings) | Gap until the HA phase |
|---|---|---|
| 3 control-plane nodes | 1 hub (k3s server, SQLite) + 2 workers | **The hub is a single point of control.** If it dies, apps on workers keep running, but nothing is rescheduled or changed, and the dashboard is down until the hub is restored (BACKUPS.md §7.3, RTO target ≤ 4 h on a spare machine, context/02 §15) |
| 3-node NATS JetStream, R3 | hub NATS, R1 streams; leaf outboxes on nodes | Stream data lives on the hub only; protected by backups, not replication |
| GitOps controller | gateway revisions + drift detection (DEPLOYMENTS.md) | — (by design: approval-gated, not auto-sync) |
| Sealed secrets | gateway secret store, k3s secrets encryption (H-12) | — |
| Tailnet ingress | remote access app (backlog item 22) | needs item 22 |
| Backup CronJobs | backup agent, verified restores (BACKUPS.md) | — |

**HA phase (F6, L, after the founder runs phase 1 daily):**
- Three hubs. k3s moves from SQLite to embedded etcd in place by restarting the first server with `--cluster-init` (research W5-R3).
- NATS becomes a three-node cluster with R3 core streams.
- The gateway runs on all three with a database lease, so only one dispatches. This needs the PostgreSQL ledger (BD-04) and leases (`actions.py` `reconcile_interrupted` already notes "several would need leases first").
- Two boxes are not HA: two nodes cannot hold quorum (research 12 §9.2). The UI calls a two-box setup "Mirror" (warm standby through continuous restore), never "HA".

**Founder call:** whether phase 1's single hub is acceptable for his daily services, or whether HA is a precondition for the switch. The recommendation is to switch with phase 1 plus a tested restore onto a spare machine, because that tests the backups for real.

## 10. Failure modes

| Failure | What happens | What the owner sees | Recovery |
|---|---|---|---|
| Hub down | Pods on workers keep running; leaf outboxes buffer; jobs wait | Phone: last state labelled with age; each node's local API (`:7480`, loopback by default, H-24) still answers on that machine | Restart the hub, or restore it onto a spare (BACKUPS.md §7.3) |
| Worker down | Its pods stop; local-volume apps are down | `stale` → `offline` after 120 s, alert `node.offline` listing the affected apps | Bring it back, or `app.move` from backup |
| Network partition (leaf) | Leaf keeps working locally, buffers events | `stale`/`offline`; after reconnect, "syncing (N pending)" until outbox lag is 0 (W8-R2 rule 2) | Automatic |
| Leaked join ticket | Attacker can only request; pairing code differs | A `node.join` request the owner did not expect | Deny; tickets are single use and expire |
| Stolen node | It still has valid credentials until removal | — | `node.remove` (offline path); certificate stops renewing within 30 days and is deny-listed at once |
| Cloned disk | Duplicate node id | Join refused, repair suggests a new machine-id | §3 |
| Clock skew | TLS and expiries break | `degraded: clock_skew` | Repair: enable NTP (`systemd-timesyncd`) |
| Certificate expired (node off > 30 days) | Leaf link refused | Node `offline`, `cert_expired` | Re-join with a new ticket; the node keeps its id, and the old node row is replaced only after approval |
| Hub address changed | Nodes pin the CA, not the address | — | Nodes try every hub URL they know, then `onemind.local` (mDNS, ONB-P2) |
| NATS reload drops connections | Clients reconnect automatically | Brief stale blip, no alert | — |
| Full disk on a leaf | Outbox stream hits its limit and drops the oldest events | `degraded: outbox_full` | Free space; the limits are in the stream config |

## 11. Security summary

- Every link is TLS with a pinned box CA. Nodes log in with keys, never passwords.
- Joining is owner-approved with a pairing code. The ticket only lets a machine ask.
- Nodes can publish only their own subjects. Jobs are signed and expire.
- Workers hold no Kubernetes admin rights (D-B6.2). The gateway's Kubernetes rights shrink to per-app RoleBindings (H-03).
- Pod traffic between nodes is encrypted with flannel's `wireguard-native` backend (H-17).
- All join, drain, remove and renew events go to the audit log.

## 12. Data model (gateway database)

```
join_tickets(id, token_sha256, role, created_by, created_at, expires_at, used_at, used_by_join_id)
joins(id, ticket_id, node_id, node_pubkey, tls_pubkey, nats_pubkey, facts_json, pairing_code,
      action_id, state[requested|approved|delivered|completed|denied|expired], bundle_delivered_at)
fabric_nodes(node_id PK, role, pubkey, cert_serial, cert_expires_at, nats_user, joined_at,
             state[active|draining|drained|removed], removed_at, last_heartbeat_json, received_at)
cert_denylist(serial, node_id, reason, until)
```

The in-memory `NodeRegistry` (`core/onemind_core/nodes.py`) stays the live view. `fabric_nodes` makes membership durable, so a node that has not sent a heartbeat since the gateway restarted still shows as `offline`, not missing.

## 13. Test plan and acceptance criteria

| # | Test | Pass when |
|---|---|---|
| FT-1 | Join a worker VM by QR text (two Debian 13 VMs, as in `deploy/README.md`'s test record) | `node.join` awaits approval with matching facts and pairing code; after approval the node is `online` within 30 s and `Ready` in k3s; the node has no `/etc/rancher/k3s/k3s.yaml` and no `server/` dir |
| FT-2 | Replay a used ticket; use one past its TTL; send a wrong pairing node key | `409 conflict` (`ticket_used`), `409 expired`, and the code on the card differs |
| FT-3 | NATS impersonation (extends H-06's test) | With node A's credentials: publishing `onemind.node.B.status`, `onemind.audit` or `onemind.node.A.job.x` → permission violation; node B unchanged |
| FT-4 | Forged job | A job with a bad signature, an expired one, and a replayed `job_id` are all refused and logged by `onemindd` |
| FT-5 | Hub outage with a leaf (port `evidence/lab/w8-nats-leaf-buffer/`) | 30 min outage, 500 node events published; after reconnect all reach `ONEMIND_EVENTS` in order, no duplicates; UI shows "syncing" until lag is 0 |
| FT-6 | State timing (fake clock, gateway unit tests) | 29 s → online, 31 s → stale, 121 s → offline; a skewed heartbeat is aged by `received_at` |
| FT-7 | Drain with a local-volume app | The plan lists it as "will be stopped"; after approval the node is `drained`; uncordon restores scheduling |
| FT-8 | Remove an offline node | Certificate deny-listed, NATS user gone, Kubernetes Node deleted, audit lines present; the machine, when powered on, cannot connect |
| FT-9 | Placement | An arm64-only app gets `no: arch_unsupported` on an amd64 node; a 2 GiB app on a 1 GiB-free node gets `no: not_enough_memory`; the install revision contains the chosen node's affinity |
| FT-10 | Duplicate machine-id | Second join refused with `duplicate_node_id`, repair alert raised |
| FT-11 | Canary OS update (OSU-B1, with the updater's fake RAUC) | Node 1 installs; nodes 2–3 wait; a `committed` verdict releases them; an `image-bad` verdict stops the rollout and alerts |

## 14. Build steps

| Step | What | Size | Depends on |
|---|---|---|---|
| F1 | NATS auth per H-06: config NKey users for gateway, custodian, one per node; TLS with the box CA; node permissions table §5.2 | M | SEC-P2 (CA), deploy-v0 merged |
| F2 | Join flow: tickets, `POST /v1/fabric/join`, `node.join` action with pairing code, custodian signing, k3s bootstrap token, `onemind node join`; QR on the Nodes page | M | F1, SEC-P1 |
| F3 | Local NATS leaf on workers and leaves, `ONEMIND_NODE_OUTBOX`, event re-publish by the gateway; JWT mode after the lab test | M | F2 |
| F4 | Jobs: `ONEMIND_JOBS` stream, signed job envelope, `onemindd` job runner with done-list; first job kinds `node.leave` and `host.check` | S | F1 |
| F5 | States `degraded`/`draining`/`drained`/`removed`, drain/uncordon/remove actions, alerts; placement labels, verdicts and affinity; `app.move` | M | F2, F4, DEPLOYMENTS D2 |
| F6 | Canary OS rollout across nodes (OSU-B1): gateway sequences `update.apply` jobs and reads each node's gate verdict from its heartbeat | M | F4, updater merged |
| F7 | HA hubs: etcd migration, NATS cluster R3, gateway leases on PostgreSQL | L | founder call (§9), BD-04 |
