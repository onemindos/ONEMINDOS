# Lab spike LAB-fb3-mesh-nat: self-hosted WireGuard mesh across two NATs, with NATS leaves over it

**Status:** PRE-REGISTERED. Goal, hypotheses, design and pass/fail criteria were written 2026-11-12, before any VM was created, any binary downloaded or any test run. The sha256 of this file at that moment is in `../PREREGISTRATION.md` and `PREREGISTRATION.sha256`. Results are added below the line "Results" after the run; nothing above that line is changed afterwards except the Status line and typo fixes, and any other change is logged in the deviations section.

**Serves:** fabric mission 02 (`RESEARCH-MISSION-02-ONE-MIND-FABRIC.md`) §5 lab spike 1 ("Hub + leaf across a NAT") and workstream FB-3 (Tailscale vs Headscale vs WireGuard, NAT traversal with no open ports); hardening backlog H-06 (NATS TLS + per-node credentials) and H-17 (encrypted node-to-node traffic, the mesh half); `docs/architecture/FABRIC.md` F-R5 and the "leaf on every node" rule; research 09 §5.1 (W8-R2).

> **Explain it like I'm the founder.** Today a OneMind node talks to the hub's NATS in plain text on the LAN, and a node in another building, at a friend's house or in the field cannot reach the hub at all unless someone opens a port on a router. The plan is a private encrypted network (a WireGuard "mesh") that every OneMind machine and your phone join, run entirely from your own hub: Headscale is the address book and gatekeeper, DERP is a relay for when two machines cannot talk directly, and the Tailscale app is the client. This spike builds a fake "cloud" hub and two fake "homes", each behind its own router that lets **nothing** in, and checks that: the homes join with a one-time key; they find each other directly through the routers; if the routers block the fast path they still talk through the hub's relay; the event bus survives a 30-minute outage without losing or duplicating anything; the access rules really block what they say; and it all fits on a Pi-sized machine.

## 1. Goal

Answer, with a run rather than documentation, whether the TARGET DESIGN in `docs/architecture/NETWORKING.md` (Headscale coordinator + self-hosted DERP on the hub, Tailscale client on every node, pre-auth-key enrollment, role-based ACLs, NATS leaf per node over the mesh with TLS and per-node credentials) works across two separate NATs with **no inbound port** on either home router, and what it costs on a Pi-5-sized arm64 machine.

## 2. Hypotheses

- **H1 (enrollment, no open ports)** A node behind a NAT that drops every new inbound connection enrolls into a self-hosted Headscale with a single-use pre-auth key and reaches the hub and the other home node; a used key cannot enroll a second machine.
- **H2 (NAT traversal)** Between two Linux masquerade NATs (endpoint-independent mapping, conntrack filtering), the two home nodes establish a **direct** WireGuard path by UDP hole punching; when outbound UDP is blocked at one NAT, traffic falls back to the **self-hosted DERP relay** over TCP 443 and keeps working.
- **H3 (bus over the mesh)** A NATS leaf on each home node connects to the hub's leaf port over the mesh with TLS and its own credentials; JetStream outbox streams on the leaves (the W8-R2 pattern, as specified in FABRIC.md: domain `node-<id>`, stream `ONEMIND_NODE_OUTBOX`) deliver every event published during a 30-minute hub-link outage to the hub, in order and without duplicates, after the link returns.
- **H4 (ACL)** A Headscale policy generated from OneMind roles enforces per-port rules between nodes: home A reaches the allowed service on home B and not the denied one.
- **H5 (footprint)** `tailscaled` plus a NATS leaf with JetStream idle within a leaf-class budget on a 4 vCPU / 4 GiB arm64 VM.

## 3. Pass / fail criteria (frozen before the run)

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| T0 | Build and pins | Every download inside the VM matches a pinned sha256 that equals the upstream checksum file: Headscale v0.29.7 `linux_arm64` (`checksums.txt`), Tailscale v1.104.6 `arm64.tgz` (pkgs.tailscale.com `.sha256`), nats-server v2.15.2 and natscli v0.5.1 (the w8 pins), Go 1.27.4 `linux-arm64` (go.dev); `derper` built from Tailscale tag `v1.104.6` with that Go (module checksums verified by `go.sum`); `--version` of each printed | A hash mismatch, an unpinned download, or a version other than the pinned one |
| T1a | Enrollment | Hub node, home A and home B each enroll with their own **single-use** pre-auth key minted by a stand-in "gateway" script (`headscale preauthkeys create`, not reusable, 1 h expiry, role tag); `headscale nodes list` shows the three nodes online with the expected tags; a **fourth** `tailscaled` given home A's already-used key does **not** enroll within 60 s | Any node fails to enroll, or the reused key enrolls a node |
| T1b | Reachability | Over the mesh (100.64.0.0/10 addresses): A→B allowed service (TCP 9001) returns its banner, B→A likewise, A→hub and B→hub TLS handshake on the hub's leaf port 7422 succeeds; `tailscale ping` A→B reports a **direct** path ("via <ip:port>", not "via DERP") within 30 pings | Any of these fails, or A↔B never goes direct while UDP is allowed |
| T1c | No inbound port | On both NAT routers, `nft list ruleset` has no `dnat`/`redirect`/port-forward rule and no accept of `ct state new` from the WAN; a TCP SYN scan of ports 1–1024 plus 41641 and a UDP probe of 41641 from the cloud namespace and from the other NAT's WAN address get **no** answer; the routers' "WAN new inbound dropped" counters are recorded; `conntrack -L` on each router shows every flow of the home node's tailscaled with an **inside** source as the original direction; a `tcpdump` on each router's WAN shows the direct WireGuard/disco UDP between the two NAT public addresses | Any port answers from the outside, a forward or new-inbound accept exists, or a tailscaled flow was originated from outside |
| T2 | DERP fallback | With every UDP packet from home A's LAN to the WAN dropped at NAT A: A↔B and A→hub traffic still works (allowed service banner; leaf TLS handshake); `tailscale ping` A→B reports "via DERP(…)" naming the self-hosted region; NAT A's WAN capture shows no UDP from A and TCP to the hub's port 443. Median `tailscale ping` latency of 20 pings is recorded for direct and DERP paths (observation; links shaped by `netem`, §4). After the block is removed, the return to a direct path and its time are recorded (observation) | A↔B or A→hub fails with UDP blocked, or the relay used is not the self-hosted one |
| T3 | NATS leaf over the mesh | Hub leaf listener bound **only** to the hub's mesh address on 7422 with TLS required (`ss -ltn`); leaf users `leaf-home-a` / `leaf-home-b` with random passwords generated at run time; negative checks: a leaf with no TLS, and a leaf with a wrong password, are refused (hub log); each home leaf runs JetStream domain `node-home-a` / `node-home-b` with stream `ONEMIND_NODE_OUTBOX` (`onemind.node.<id>.event.>`), and the hub stream `NODE_EVENTS` sources both. Publish 100 events per node (payload seq 1–100), then cut the hub's WAN link (cloud namespace link down) for **30 minutes**; during the outage each home node publishes 500 events (seq 101–600), spread evenly, each acknowledged by its **local** leaf's JetStream; restore the link. **PASS if** within **300 s** of restore `NODE_EVENTS` holds exactly 1200 messages and, for each node, the payload sequence read in stream order is exactly 1..600 (no gap, no duplicate, strictly increasing) | Any local publish not acknowledged, fewer or more than 1200 at the hub after 300 s, or any gap, duplicate or reordering per node |
| T4 | ACL | Policy (generated by the lab's role→policy script) allows `tag:leaf`→`tag:hub:7422`, `tag:leaf`→`tag:leaf:9001`, `tag:hub`→`tag:leaf:*`, nothing else. Home B listens on TCP 9001 and 9002 (both answer locally on B), the hub runs a test service on 9002. **PASS if** in 3 of 3 attempts A→B:9001 returns the banner while A→B:9002 and A→hub:9002 return **no** bytes (timeout or reset) | A receives any byte from B:9002 or hub:9002, or the allowed path fails |
| T5 | Footprint | On a 4 vCPU / 4 GiB arm64 VM (Pi 5 4 GB sizing), home A's `tailscaled` and its NATS leaf (JetStream on, stream present, leaf connected, no publishing) measured over a 10-minute idle window after a 2-minute settle: **PASS if** combined PSS ≤ **128 MiB** and their combined mean CPU ≤ **2 %** of one vCPU. RSS, PSS and CPU seconds of each process are recorded | Above either budget |

**Spike verdict:** PASS if T0–T5 all pass in one full run. A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. A failure caused by a lab-script bug is logged as such, the bug is fixed and the whole run repeated; the failed run's logs are kept.

**Exploratory, not pass/fail (labelled E-x in the results):**
- **E1 hard NAT:** NAT B switched to `masquerade random` (a new random source port per destination, i.e. endpoint-dependent mapping, like many carrier-grade NATs): does A↔B still go direct, or fall back to DERP?
- **E2 leaf permissions:** FABRIC.md marks "per-user permissions applied to a leaf connection on nats-server v2.15.2" UNVERIFIED. Give `leaf-home-a` a permission set that allows only its own subjects and observe whether a message leaf A publishes on `onemind.node.home-b.event.x` reaches a hub subscriber.

## 4. Design and fidelity choice

**Choice: one Lima VM with Linux network namespaces and nftables NAT routers**, over several Lima VMs. Reason: Lima's `vz` VMs on this host sit on one shared NAT with no per-VM router, and putting each VM behind its own NAT would need a root-installed `socket_vmnet` on the Mac plus a router VM per home. Namespaces give each "home" a real, separate Linux NAT router (kernel conntrack, nftables masquerade, per-router counters, UDP blocking and link cuts on demand), which is exactly what the tests must control and observe. Tailscale's own NAT test lab (`tstest/natlab`) takes the same approach of simulated routers.

```
            ns cloud  203.0.113.10 (public, no firewall: the "VPS")
            headscale :8443 TLS · derper :443 TLS + STUN :3478/udp · tailscaled (tag:hub) · nats-server hub (leaf port on mesh IP only)
                 |
   ns inet (bridge, 203.0.113.0/24 "internet", netem delay on each link)
        |                                   |
   ns nat-a 203.0.113.21                ns nat-b 203.0.113.22        nftables: masquerade out, drop ct new in (counted)
        | 192.0.2.0/24                      | 198.51.100.0/24
   ns home-a 192.0.2.10                 ns home-b 198.51.100.10
   tailscaled (tag:leaf), nats leaf     tailscaled (tag:leaf), nats leaf, test services :9001 :9002
```

- **Host isolation:** everything downloaded runs inside a disposable Lima VM `fb3lab` (`template:debian-13`, arm64, `vz`, **4 vCPU / 4 GiB**, Pi 5 4 GB sizing), whose only host mount is the lab work folder `<lab-dir>/fb3-mesh-nat`. The VM is deleted when the spike ends.
- **Addresses:** documentation ranges only (RFC 5737) for the simulated internet and LANs; the mesh uses Headscale's default 100.64.0.0/10 pool. TLS for Headscale, DERP and NATS uses a throwaway lab CA generated at run time inside the VM (never committed); the hub's name `hub.lab.example` (RFC 2606) resolves through per-namespace hosts files.
- **Links:** `netem` adds 10 ms one way on each home router's WAN and 20 ms on the cloud's link, so direct and relayed paths have different, measurable latencies.
- **Enrollment stand-in:** a script plays the gateway's role after owner approval: it mints one single-use, tagged, 1-hour key per node and hands it to that node's `tailscale up --login-server https://hub.lab.example:8443 --authkey …`. No Tailscale Inc. coordination or DERP server is used: Headscale's DERP map contains only the self-hosted region, and `derp.urls` is empty.
- **Outage method (T3):** `ip link set` down on the cloud namespace's link, so both homes lose the hub (control plane, DERP and NATS) at once for 30 minutes, and Headscale is unreachable during it.
- **Footprint method (T5):** PSS from `/proc/<pid>/smaps_rollup`, RSS from `/proc/<pid>/status`, CPU from `utime+stime` in `/proc/<pid>/stat` sampled at the start and end of the 10-minute window.

## 5. Fidelity limits (written before the run)

| This lab shows | It does not show |
|---|---|
| Hole punching and DERP fallback through Linux masquerade NATs that admit no new inbound connection | Behaviour behind real consumer routers, carrier-grade NAT, symmetric NATs from other vendors, IPv6-only links, or captive portals (E1 only approximates a hard NAT) |
| The full control plane, relay and bus running only on self-hosted components | Real internet latency, loss and jitter (only fixed `netem` delay); Headscale or DERP at scale |
| Buffering and replay across a 30-minute total hub outage with clean link loss | Half-open links, flapping links, days-long outages, disk-full on a leaf (w8's limits still apply) |
| Idle cost of `tailscaled` + a NATS leaf on an arm64 VM sized like a Pi 5 4 GB | Pi 5 CPU speed: the Mac's cores are faster than a Cortex-A76, so CPU % is a **lower bound**; all namespaces share one kernel, so per-process numbers are measured, whole-machine numbers are not |
| The phone/laptop path only by analogy: the same client and protocol as the official apps | The official iOS/Android apps against this Headscale (needs real devices) |

## 6. Glossary

| Term | Meaning |
|---|---|
| NAT | A router that shares one public address among many inside machines and, by default, lets nothing start a connection from outside |
| Hole punching | Two machines behind NATs send to each other at the same time, so each router sees an "outgoing" flow and lets the reply in |
| DERP | Tailscale's encrypted relay over HTTPS, used when a direct path is impossible; here self-hosted on the hub |
| Headscale | An open-source (BSD-3) server that does the job of Tailscale's coordination service: keys, addresses, ACLs |
| Pre-auth key | A one-time code that lets a machine join the mesh without a login screen |
| NATS leaf | A small NATS server on a node that forwards to the hub and keeps working when the hub is unreachable |
| JetStream domain / source | A leaf's own local store, and a hub stream that copies from it when the link is up |
| PSS | Memory a process uses, with shared pages divided among the processes sharing them |

---

## Results
