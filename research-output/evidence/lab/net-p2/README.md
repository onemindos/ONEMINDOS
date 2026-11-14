<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lab NET-P2: networking part 2 on a hub + node VM pair

**Serves:** CORE-NET-11 (installer), CORE-NET-12 (gateway + onemindd wiring), CORE-NET-13 (UI) on
branch `feat/net-part2`; contract §12.7 (HTTPS), §12.9 (NATS auth), §12.11 (fabric join); NETWORKING.md
tests NT-1, NT-3, NT-4, NT-6, NT-8 (parts), NT-15 (parts); FB-3 follow-ups (per-node NATS accounts,
leaf liveness).

> **In plain words.** Two fresh Debian 13 virtual machines on one virtual LAN. One becomes the hub
> with `deploy/install.sh --role hub`. The owner makes a one-time join code on it. The other machine
> runs `deploy/install.sh --role node --join '<code>'`, shows a short match code and waits. The owner
> approves. The test then checks every layer: the private mesh, k3s over the mesh with encrypted pod
> traffic, the node's NATS link (TLS, its own account, cannot speak for anyone else), the access
> rules between machines, and an installed app (Vaultwarden) opened at
> `https://vaultwarden.box1.local` through the hub's sign-in.

## 1. Setup

- Host: Apple-silicon Mac, Lima 2.3.0, `vmType: vz`, both VMs `template:debian-13` aarch64
  (Debian 13.7 genericcloud), hub 4 vCPU / 6 GiB, node 2 vCPU / 3 GiB, no host mounts.
- Network: Lima `user-v2` (one virtual switch for both VMs; `vzNAT` isolates VMs from each other,
  checked: ARP fails). In committed logs the switch subnet is masked to `192.0.2.0/24` (TEST-NET-1).
- Software: this branch's tree copied into each VM; `onemindd` and `onemind` cross-compiled for
  linux/arm64 on the host (`go build`, no install); the dashboard is the core test fixture (the
  lab is about networking). Everything else is downloaded **inside the VMs** by `install.sh` with
  its sha256 pins (k3s, NATS, Headscale, Tailscale, uv/Python, the gateway's locked dependencies).
- Script: `scripts/lab.sh` (runs on the host, drives `limactl`, deletes both VMs at the end).

## 2. Tests and pass criteria (written before the recorded run)

| ID | Test | PASS when |
|---|---|---|
| NP-1 | Hub install | `install.sh --role hub` exits 0; k3s node InternalIP is the hub's mesh IP (`100.64.0.0/10`); `flannel-wg` exists and no VXLAN link; NATS clients listen on `127.0.0.1:4222` only and the leaf listener on the mesh IP only; `:443` presents a certificate issued by the box CA; `http://box1.local/` answers 308 to `https://`; no Traefik Service |
| NP-2 | Owner-approved join | the node's request appears with a match code that equals the one the node printed; before approval the poll carries no credentials; after `onemind fabric approve` the node install exits 0; reusing the join code is refused (`401`, `code_used`) |
| NP-3 | Mesh | the node has a mesh IP; Headscale lists it as `node-<node_id>` with exactly `tag:onemind-worker` and `tag:onemind-k3s`; the hub's heartbeat view shows mesh `up` |
| NP-4 | NATS leaf | the hub's `/leafz` shows one leaf, account `NODE_<node_id>`, from the node's mesh IP; a message the node publishes on its own subject reaches a hub subscriber and messages on another node's subject and on `onemind.audit` do not; a TLS client without a node certificate cannot complete a leaf handshake on `:7422` |
| NP-5 | k3s worker | the worker is `Ready` with its mesh IP as InternalIP; `node.join` is `succeeded`; the k3s bootstrap token Secret is gone afterwards; a pod on the worker reaches a pod on the hub (cross-node, over `flannel-wg`) |
| NP-6 | App through the proxy | Vaultwarden installed by an approved `app.install`; from the node, `https://vaultwarden.box1.local/` with the box CA: `401` without sign-in, `200` with the owner's token and with the app-session cookie; TLS fails without the box CA |
| NP-7 | Mesh access rules | from the worker to the hub's mesh IP: `443`, `7422`, `6443` open; `22`, `8444`, `4222` closed |
| NP-8 | Leaf liveness | after the node's leaf traffic to the hub is dropped, the hub's `/leafz` shows no leaf within 90 s (FB-3 saw 405 s with default pings) |
| NP-9 | Names | the hub resolves its own published mDNS names (`box1.local`, `onemind.local`, `vaultwarden.box1.local`); cross-VM mDNS is recorded, not judged (Lima `user-v2` does not forward multicast) |

**Verdict rule:** PASS = NP-1 … NP-8 pass in one full run on fresh VMs. NP-9 is informative.

## Results

**Verdict: PASS** (run 2, 2026-11-12, fresh VMs, tree at commit `ac55dd751ba5` plus the lab files). Data:
`run-2/` (`results.json`, one file per test). Run 1 (`history/attempt1/`) failed NP-4 on a lab-script
bug, not on the product (see §4).

> **Explain the result like I'm the founder.** On two brand-new machines, the hub installed itself,
> started its own private network and put Kubernetes and the event bus on it. The second machine
> asked to join with a one-time code, showed the code **WH-V9AJ**, and the hub's approval card
> showed the same code. After approval it joined the private network, its bus link came up
> encrypted and logged in with its own key, and Kubernetes accepted it as a worker. When that
> machine tried to post as another machine, or into the audit log, nothing arrived at the hub. The
> worker could reach only the hub's web, bus and Kubernetes ports, not SSH or the coordinator.
> Vaultwarden, installed through an approved action, opened at **https://vaultwarden.box1.local**
> with the box's own certificate: refused when signed out, open when signed in. When the link
> was cut, the hub noticed in about a minute (64 s), not the 3 to 7 minutes the earlier lab saw.

## 3. Results (run 2)

| ID | Result | Evidence (`run-2/`) |
|---|---|---|
| NP-1 | **PASS** | k3s InternalIP = hub mesh IP `100.64.0.1`; `flannel-wg`, no VXLAN; `127.0.0.1:4222` and `100.64.0.1:7422` only; `:443` issuer `O=OneMind box`; `http://box1.local/` → 308; no Traefik Service (`np1-hub.txt`, `hub-install.log`) |
| NP-2 | **PASS** | node printed `WH-V9AJ`, the hub's request had `WH-V9AJ`; no fabric state on the node before approval; `onemind fabric approve` → node install exit 0; reused code → 401 (`node-install.log`, `approve.txt`) |
| NP-3 | **PASS** | Headscale node `node-ebc2df567332`, tags exactly `tag:onemind-k3s`, `tag:onemind-worker` (`np3-headscale.txt`) |
| NP-4 | **PASS** | `/leafz`: one leaf, account `NODE_ebc2df567332`, from `100.64.0.2`; the hub got the node's own subject 5/5 and none of its forged payloads (marker in `np4-forged-marker.txt`) on another node's subject or on `onemind.audit`; a TLS client without a node certificate was refused (`np4-*`) |
| NP-5 | **PASS** | worker `Ready` with InternalIP `100.64.0.2`; `node.join` succeeded only after k3s was ready; 0 bootstrap-token Secrets left; busybox pod on the worker fetched a page from a pod on the hub (`np5-*`) |
| NP-6 | **PASS** | `app.install` vaultwarden approved; `https://vaultwarden.box1.local`: 401 signed out, 200 with bearer, app-session cookie set (204) then 200, TLS fails without the box CA (`np6-*`) |
| NP-7 | **PASS** | worker → hub mesh: 443, 7422, 6443 open; 22, 8444, 4222 closed (`np7-ports.txt`) |
| NP-8 | **PASS** | hub dropped the dead leaf after **64 s** (run 1: 67 s); FB-3 measured 405 s with default pings (`np8-liveness.txt`) |
| NP-9 | info | the hub resolves `box1.local`, `onemind.local`, `vaultwarden.box1.local`, `vaultwarden.onemind.local` (avahi, multi-label `.local` works); the node gets no mDNS answer across Lima's user-v2 switch, which forwards no multicast. Cross-machine mDNS stays NT-13 on real hardware |

## 4. Deviations, failed attempts and fixes

| # | What | Effect |
|---|---|---|
| 1 | Debug runs before the recorded ones (same day, not counted) found three installer bugs and one gateway bug: k3s's ServiceLB DNATs LAN :80/:443 to Traefik in front of the gateway; upstream's k3s `install.sh` does not restart for a config-only change; a Traefik Service left from an earlier install keeps a ServiceLB finalizer and rejects :443 on the mesh IP; the gateway deleted the worker's 1-hour k3s token at the first heartbeat, before the agent used it | All fixed before run 1 (commits `b484fd0`, `adf54dd`): Traefik and ServiceLB disabled, `INSTALL_K3S_FORCE_RESTART`, finalizer cleared, `node.join` waits for k3s ready |
| 2 | Lima `vzNAT` gives each VM its own network (ARP between VMs fails) | Switched to `user-v2` before any counted run |
| 3 | **Run 1** NP-4 FAIL: the hub-side subscriber also listened on `onemind.audit`, where the gateway itself publishes every audit line, and the check treated any message there as forged. The node's forged 5-byte payloads did not arrive (the three messages were 350–478-byte gateway lines) | Lab-script bug. The check now looks for a random marker in the forged payloads. Run 2 is the counted run; run 1 is kept in `history/attempt1/` (all other tests passed there too, NP-8 67 s) |
| 4 | The masking regex used `\b`, which macOS `sed` ignores, so the lab's owner token (of VMs already deleted) and the CA fingerprints were left in `hub-install.log` and `ticket.json` | Re-masked in place before commit, `SHA256SUMS` regenerated; `lab.sh` fixed |
| 5 | One full counted run, not two | The pre-registered verdict needs one |

## 5. What this means

1. The developer install now builds the networking design of NETWORKING.md end to end on Debian 13
   arm64: mesh first, k3s on mesh addresses with WireGuard pod traffic, NATS leaves with TLS and one
   account per node, HTTPS with the box CA, owner-approved joins.
2. Per-node NATS accounts give the isolation FB-3 E2 asked for; the same file is checked in CI
   against an in-process nats-server (`internal/leaf/accounts_test.go`).
3. `ping_interval: 20s` and `ping_max: 2` bring dead-link detection to about a minute.
4. Still to test on hardware: mDNS from phones and laptops (NT-13), Pi 5 budget and pod throughput
   with WireGuard in WireGuard (NT-9, NT-10), phones through a relay (NT-12), 24-hour no-third-party
   capture (NT-17).

## 6. Reproduce

On an Apple-silicon Mac with Lima and Go: `research-output/evidence/lab/net-p2/scripts/lab.sh run-N`.
It creates `omos-netp2-hub` and `omos-netp2-node`, writes `run-N/` and deletes both VMs (`KEEP=1`
keeps them). Downloads happen inside the VMs only.
