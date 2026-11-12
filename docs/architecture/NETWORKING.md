<!-- SPDX-License-Identifier: Apache-2.0 -->
# Networking: one private network across every OneMind machine

**Status:** design for build agents (2026-11-12). Founder request: internal networking and the mesh are core, needed now, so the founder can replace his own cluster.
**Leap spec:** [`docs/leap/core/NETWORKING.md`](../leap/core/NETWORKING.md) (CORE-NET). **API:** §15 below is proposed text for contract §12.16.
**Builds on:** [FABRIC.md](FABRIC.md) (join, identity, NATS leaf, jobs), [CONTRACT-12-DRAFT.md](CONTRACT-12-DRAFT.md) §12.2–§12.4, contract §1–§3; hardening H-04, H-05, H-06, H-17, H-23, H-24, H-29 ([HARDENING-BACKLOG.md](../security/HARDENING-BACKLOG.md)); research 09 §5 (P0-6: "WireGuard/Headscale + NATS leaf"), research 12 §8 (REC-W11-11, REC-W11-12), mission 02 FB-3; lab W8-1 (`research-output/evidence/lab/w8-nats-leaf-buffer/`, 600/600).
**Open founder questions it touches:** Z-34 (Tailscale or Headscale default), F-1 (phone HTTPS), and the new coordinator decision in [DECISIONS-NEEDED.md](../leap/DECISIONS-NEEDED.md).

> **In plain words.** Today the machines talk to the hub over the home network in clear text, with no passwords, and only when they are on the same LAN.
> After this design, every OneMind machine and every phone you add joins one **private, encrypted network (a "mesh")** that the box runs itself. Machines find each other directly when they can, and through your own relay when they cannot, at home, in the cloud or in the field, without opening ports on your router.
> On the home network you type `onemind.local` or `photos.onemind.local` and get the dashboard or the app over HTTPS, behind your OneMind sign-in. Away from home, the Tailscale app on your phone connects to *your* box, not to anyone's cloud.

**Terms.** *WireGuard*: a small, fast, encrypted tunnel built into the Linux kernel. *Tailscale client*: open-source software (BSD-3) that sets up WireGuard tunnels between many devices automatically. *Headscale*: an open-source (BSD-3) **coordinator** for Tailscale clients; it hands out addresses and keys and enforces access rules. It never sees traffic. *DERP*: a relay that forwards already-encrypted WireGuard packets when two devices cannot reach each other directly (both behind strict NAT). *mDNS*: how `.local` names are found on a LAN with no DNS server. *Forward-auth*: a proxy asks the gateway "is this person signed in and allowed?" before passing a request to an app.

---

## 1. Requirements

| ID | Requirement | Source |
|---|---|---|
| N-R1 | Every link between OneMind machines is encrypted and mutually authenticated, on the LAN and across sites | H-06, H-17, FABRIC F-R10 |
| N-R2 | Machines at different sites, behind NAT or CGNAT, reach each other with **no inbound port opened at home** | founder 2026-11-12, FB-3 |
| N-R3 | Nothing depends on a third-party company's servers by default: coordinator and relays are owner-run (BSD-3 code) | target design, research 12 §8.2, M-1 |
| N-R4 | A machine joins the mesh **only** through the owner-approved fabric join; no standing shared secret | H-23, FABRIC §4 |
| N-R5 | Access between machines, phones and apps follows OneMind roles; a node or app reaches only what its role needs | target design, H-04 |
| N-R6 | Each node's NATS link is a local leaf, TLS with the box CA, per-node credentials, own-subject permissions | H-06, FABRIC §5, W8-R2 |
| N-R7 | k3s nodes talk over mesh addresses; pod traffic between nodes is encrypted (`wireguard-native`) | H-17, D-B6.2 |
| N-R8 | LAN names: `onemind.local` for the box and `<app>.onemind.local` per app, HTTPS with a per-box CA, behind OneMind sign-in | H-05, H-29, REC-W11-11 |
| N-R9 | Phones and laptops reach the box remotely with the **official Tailscale apps** pointed at the owner's coordinator; the OneMind app ships no VPN | REC-W11-12, research 12 §7 (no VPN entitlement) |
| N-R10 | The LAN keeps working when the internet is down; the mesh keeps working between machines that can see each other | FABRIC F-R5, research 09 §5 |
| N-R11 | Every state change that **adds** reach (device, relay, public exposure) is an approved action; removing reach is instant | contract §3, SEC §3.4 ("reducing power is instant") |
| N-R12 | Screens never show a value as live when it is stale; no IP, MAC or serial on default screens | contract §2, §5, CORE-FABRIC-6 |
| N-R13 | Fits a Raspberry Pi 5 (4 GB worker, 2 GB leaf) with a measured budget | D-004, §13 |

## 2. Design in one picture

```
                         Internet (optional; only for off-site reach)
                                        │
             ┌──────────────────────────┴───────────────────────────┐
             │  OneMind relay (optional, owner's small cloud VM)      │
             │  public 443/tcp + 3478/udp only                        │
             │  • SNI router: control/join/derp names (TLS passthrough)│
             │  • derper (DERP + STUN), verifies clients via Headscale│
             └───────────▲───────────────────────────▲──────────────┘
      hub dials OUT a    │ static WireGuard link      │ phones / field nodes
      (no home port)     │ (systemd-networkd)         │ (Tailscale client)
 ┌───────────────────────┴───────────────────────┐    │
 │ HUB  (home LAN 192.0.2.0/24, example)          │    │
 │  onemind-edge :443  ── SNI/Host router, TLS    │    │
 │     onemind.local, <app>.onemind.local → gateway forward-auth → app Service
 │     control.onemind.internal → Headscale (127.0.0.1)                 │
 │     join.onemind.internal    → gateway /v1/fabric/join* only         │
 │  Headscale (coordinator, embedded DERP, SQLite)│    │
 │  tailscaled  mesh IP 100.64.0.1 (example)      │    │
 │  NATS hub :4222 loopback · leaf :7422 on mesh  │    │
 │  k3s server, node-ip = mesh IP, flannel wireguard-native on tailscale0
 │  avahi: onemind.local, <app>.onemind.local     │    │
 └───────▲──────────────────────────▲─────────────┘    │
         │ WireGuard (direct on LAN)│                   │
 ┌───────┴───────────┐     ┌────────┴──────────┐  ┌─────┴───────────┐
 │ WORKER (Pi / mini) │     │ LEAF (Pi, laptop) │  │ Owner phone     │
 │ tailscaled         │     │ tailscaled        │  │ official        │
 │ NATS leaf → hub    │     │ NATS leaf → hub   │  │ Tailscale app   │
 │ k3s agent          │     │ no k3s            │  │ → hub :443 only │
 └────────────────────┘     └───────────────────┘  └─────────────────┘
```

Three layers, each with one job:
1. **Mesh (WireGuard, coordinated by Headscale).** Addresses, encryption, NAT traversal, access rules between machines and devices.
2. **Fabric services over the mesh.** NATS leaf links (§7), k3s (§8), `onemindd` → hub calls (renew, join bundle).
3. **Edge on the hub.** One TLS front door on `:443` for people: dashboard, per-app names, coordinator, join (§9).

### 2.1 Refinements to the target design (each with its evidence)

The target design (founder brief 2026-11-12) is kept. These points refine it where evidence showed a gap; none changes a founder decision.

| # | Target said | This design | Why (evidence) |
|---|---|---|---|
| R1 | Hub runs a self-hosted DERP (`cmd/derper`) | Hub runs Headscale's **embedded** DERP; `cmd/derper` runs on the optional **relay** | Headscale v0.29.7 ships an embedded DERP + STUN (`config-example.yaml` `derp.server`, `docs/ref/derp.md`). A DERP behind home NAT cannot help two remote peers; a relay only helps where it has a public address |
| R2 | "No open ports", hub is the coordinator | Adds **reach modes** (§4.3). Off-site reach without opening a home port uses a relay VM that forwards TLS by SNI over a WireGuard link **the hub dials out**. TLS still ends on the hub | A coordinator behind NAT/CGNAT is unreachable from LTE. Every Tailscale client must reach the coordinator's HTTPS URL (`docs/ref/registration.md`) |
| R3 | Nodes enroll against "the hub's Headscale" | Nodes always use `https://control.onemind.internal`, resolved LAN-first by `onemindd` (§5.4) | One stable URL, so a reach-mode change never re-enrolls nodes, and the mesh keeps its coordinator on the LAN during an internet outage |
| R4 | "Gateway reverse proxy with login" | A small Go edge (`onemind-edge`) that the gateway configures and that asks the gateway for forward-auth on every request | Keeps Python out of the streaming data path on a Pi; the gateway still decides who may open which app. H-29 allows "the gateway (or an ingress it controls)" |
| R5 | Default DERP map | `derp.urls: []`, so Tailscale Inc's DERP servers are **never** in the map | Headscale's default config points at `https://controlplane.tailscale.com/derpmap/default` (`config-example.yaml` line 131); `docs/ref/derp.md` says to clear it to use only your own |
| R6 | derper verifies clients | `-verify-client-url https://control.onemind.internal/verify` **and** `-verify-client-url-fail-open=false` | derper's fail-open default is `true` (`cmd/derper/derper.go:85` at v1.104.6); an unreachable Headscale would otherwise let anyone relay through the box owner's VM |
| R7 | k3s joins over the mesh | `onemindd` enrolls the mesh; k3s only gets `node-ip` and `flannel-iface`. k3s's own `--vpn-auth` is **not** used | k3s passes the join key on the command line and runs `tailscale up --reset` (`pkg/vpn/vpn.go:69` at v1.37.2+k3s1): the key shows in `ps` (H-09) and our prefs would be wiped |
| R8 | NATS leaf with per-node credentials | Works in NATS **config mode** (FABRIC phase F1) without JWT accounts | nats-server v2.15.3 source: with no `leafnodes.authorization` block, a leaf is authenticated against the main `authorization.users` (nkeys + permissions) (`server/auth.go` `isLeafNodeAuthorized` → `isClientAuthorized`), and permissions are reversed for the leaf direction (`server/leafnode.go:2451-2460`). Confirmed by reading, still to be confirmed by test NT-6 |
| R9 | Gateway mints pre-auth keys after owner approval | The gateway calls Headscale's **REST API** (`/api/v1`, pinned to v0.29.7) on loopback with an API key from a 0600 file (`core/onemind_core/mesh.py`), instead of asking the custodian to run the `headscale` CLI. §13 S7 changes accordingly | The gateway already decides every approval, so a compromised gateway could have the custodian mint keys anyway; one REST client is simpler than a second process boundary. Endpoints and field names checked against `gen/openapiv2/headscale/v1/headscale.swagger.json` at v0.29.7 (sha256 `08f9b761…30b7`). The Go adapter (CORE-NET-1) keeps the CLI path for `onemindd` hub bootstrap |
| R10 | Gateway reverse proxy | Until `onemind-edge` (CORE-NET-5) lands, the gateway proxies apps itself (`core/onemind_core/proxy.py`, an ASGI middleware). Its `AppProxy.decide()` is the forward-auth decision the edge will call through `/v1/auth/forward` (§9.3), so both paths share one rule | Gives working `<app>.onemind.local` and `/apps/<id>/` now; R4 still holds for the streaming path on a Pi |
| R11 | Per-box CA location | `core/onemind_core/ca.py` keeps the CA under the data dir (`<data>/tls/`, key 0600, dir 0700), as CORE-SEC §3.1 places it. The same module can run in the custodian if CORE-SEC-1 settles on FABRIC §3 (§19 item 6) | Founder brief: "create on first start under the data dir"; the key still never leaves the box and no function returns it |

## 3. Addressing and names

| Thing | Value | Notes |
|---|---|---|
| Mesh IPv4 | `100.64.0.0/10`, allocated sequentially by Headscale | The hub enrolls first, so it is normally `100.64.0.1`. All mesh addresses in this doc are **examples** |
| Mesh IPv6 | `fd7a:115c:a1e0::/48` (Headscale default) | Not used by OneMind services in phase 1 |
| Mesh DNS (MagicDNS) | base domain `onemind.internal`; nodes named `node-<node_id>` | `.internal` is reserved for private use (ICANN, 2024). Matches FABRIC §3's cert SAN `node-<node_id>.onemind.internal` |
| Fixed mesh names | `hub.onemind.internal`, `control.onemind.internal`, `join.onemind.internal`, `<app>.apps.onemind.internal` | Written by the gateway to Headscale's `dns.extra_records_path` (Headscale reloads the file by checksum, `docs/ref/dns.md`) |
| LAN names | `onemind.local`, `<box>.local`, `<app>.onemind.local` | mDNS via avahi (§9.1) |
| Relay link | a per-box random IPv6 ULA `/64` (RFC 4193), hub `::1`, relay `::2` | Generated at relay setup; never committed |
| Pod / service CIDRs | k3s defaults `10.42.0.0/16`, `10.43.0.0/16` | Unchanged |
| DNS on nodes | `accept-dns=true`, Headscale `override_local_dns: false`, no global nameservers | MagicDNS answers only `onemind.internal`; the LAN resolver keeps everything else |

**Ports** (hub unless noted; "mesh" = only on `tailscale0`; the host firewall of H-04 enforces the binding column):

| Port | Service | Bound to |
|---|---|---|
| 443/tcp | `onemind-edge` (dashboard, apps, coordinator, join) | LAN + mesh |
| 8443/tcp | gateway HTTPS (H-05) | kept for compatibility; redirects to `:443` once the edge lands |
| 8080/tcp | gateway HTTP | loopback (H-05) |
| 3478/udp | STUN (embedded DERP) | LAN + mesh (and public when reach mode is `direct`) |
| 41641/udp | WireGuard (tailscaled, every machine) | all interfaces (direct paths) |
| 4222/tcp | NATS client (every machine) | loopback |
| 7422/tcp | NATS leaf listener | mesh + loopback |
| 6443/tcp | k3s API / supervisor | mesh + loopback |
| 10250/tcp | kubelet (hub and workers) | mesh |
| 51820/udp | flannel `wireguard-native` (hub and workers) | mesh |
| 7480/tcp | `onemindd` local API (every machine) | loopback (H-24) |
| Relay | 443/tcp (SNI router), 3478/udp (STUN), 51821/udp (hub link) | public |

## 4. The coordinator: Headscale and DERP on the hub

### 4.1 What runs where

| Component | Version (pinned) | Licence | Runs on | Unit |
|---|---|---|---|---|
| Headscale | v0.29.7 (tag commit `c9cf210b8bc8`); `headscale_0.29.7_linux_amd64` sha256 `e827fc9b12d958bc95b081c4401dd63f8e0471d025b45b508535a920532150a8`, `_linux_arm64` sha256 `4357b38ac63c1e425f190819fd2ee078f13e01a6d7559b15811154e2475df5e4` (release `checksums.txt`, read 2026-11-12) | BSD-3-Clause | hub | `onemind-headscale.service` |
| Tailscale client (`tailscale`, `tailscaled`) | v1.104.6 (commit `c54807352ae1`); `tailscale_1.104.6_amd64.tgz` sha256 `82a85429f733e52fd1a95dedb2c8dd8cd46d6603504e566a56b1779c9a7a4809`, `_arm64.tgz` sha256 `d0e4f297da3c428d02162c6235b9948e4ddc245c64502b7b05647da9b96a0971` (`pkgs.tailscale.com/stable/*.sha256`, read 2026-11-12) | BSD-3-Clause | every machine | `tailscaled.service` (upstream unit from the tarball) |
| derper | `tailscale.com/cmd/derper` at v1.104.6, built from source in a separate pinned Go module (`third_party/derper/go.mod` + `go.sum`), so the main `go.mod` gains no Tailscale dependency | BSD-3-Clause | relay only | `onemind-derper.service` |
| avahi-daemon, libnss-mdns | Debian 13 packages (snapshot-pinned in the image) | LGPL-2.1+ (separate processes, not linked) | every machine | Debian units |

Static tarballs from `pkgs.tailscale.com` are used instead of Tailscale's apt repository, so the image does not trust a third-party apt key and the sha256 sits in `deploy/pins.env` and `os/versions.lock.yaml` like k3s and NATS. Renovate tracks both.

### 4.2 Configuration (rendered by `onemindd` on the hub; key fields)

```yaml
# /data/onemind/mesh/headscale/config.yaml (generated; never edited by hand)
server_url: https://control.onemind.internal        # §5.4; the public name in relay/direct mode (§4.3)
listen_addr: 127.0.0.1:8085                         # only onemind-edge reaches it
metrics_listen_addr: 127.0.0.1:9091
grpc_listen_addr: 127.0.0.1:50443
unix_socket: /run/onemind/headscale/headscale.sock  # root:onemind-custodian 0770
noise: {private_key_path: /data/onemind/mesh/headscale/noise_private.key}
prefixes: {v4: 100.64.0.0/10, v6: fd7a:115c:a1e0::/48, allocation: sequential}
derp:
  server:
    enabled: true
    region_id: 999
    region_code: onemind-hub
    verify_clients: true
    stun_listen_addr: "0.0.0.0:3478"
    private_key_path: /data/onemind/mesh/headscale/derp_server_private.key
    automatically_add_embedded_derp_region: true
  urls: []                                          # R5: never Tailscale Inc's DERP map
  paths: [/data/onemind/mesh/headscale/derpmap.yaml]  # the relay's region 900, when a relay exists
  auto_update_enabled: false
disable_check_updates: true                         # no phone-home; updates come with the image
database: {type: sqlite, sqlite: {path: /data/onemind/mesh/headscale/db.sqlite, write_ahead_log: true}}
policy: {mode: file, path: /data/onemind/mesh/headscale/policy.json}
dns:
  magic_dns: true
  base_domain: onemind.internal
  override_local_dns: false
  extra_records_path: /data/onemind/mesh/headscale/extra-records.json
logtail: {enabled: false}
node: {expiry: 0}                                   # tagged machines do not expire; removal is explicit (§6.4)
```

`onemind-edge` terminates TLS for `control.onemind.internal` (and the public control name) and proxies to `127.0.0.1:8085`, including the `Upgrade` used by the Tailscale control protocol and DERP-over-HTTPS. **UNVERIFIED:** Headscale's embedded DERP and the control protocol behind a Go `httputil.ReverseProxy`; Headscale documents reverse proxies, test NT-2 checks ours.

### 4.3 Reach modes (owner setting; changing it is the action `mesh.reach.set`, risk critical)

| Mode | Who can reach the coordinator | Home router | Extra machine | Default |
|---|---|---|---|---|
| `lan` | Machines on the hub's LAN | nothing | none | **yes**, at first boot |
| `relay` | Anyone on the internet who has mesh credentials | nothing (the hub dials out) | a small public VM running the OneMind relay (§4.4) | recommended for phones and remote sites |
| `direct` | as `relay` | owner forwards 443/tcp and 3478/udp to the hub (fails under CGNAT) | none | for owners with a public IP |
| `hosted` | Tailscale Inc's coordinator instead of Headscale | nothing | none | **off**; the Z-34 "simplest" option, behind the coordinator decision |

`lan` mode still gives every machine on the LAN an encrypted, access-controlled mesh. Remote sites, phones away from home and field kits need `relay` or `direct`.

### 4.4 The OneMind relay (optional)

A minimal Debian VM with a public address (any provider; the contract already knows the `vm-do` board). It is **not** a fabric node: it runs no k3s, no NATS and no apps, and holds no OneMind secret beyond its own keys.

- **Setup:** `onemind relay init` on the VM prints a one-time pairing text `onemind-relay:v1?addr=<public ip>&fp=<sha256 of its setup certificate>&code=<one-time>` (QR on the dashboard side). The owner pastes it into Network → Relay. That creates `mesh.relay.add` (critical, owner only, never policy-approved). On approval the custodian generates the hub's WireGuard key, sends the public half to the relay's setup endpoint (TLS pinned to `fp`, authenticated by `code`), and writes a systemd-networkd `.netdev`/`.network` pair; the **hub dials out** with `PersistentKeepalive=25`.
- **What the relay forwards:** an SNI router (OneMind Go code, stdlib only) reads the TLS ClientHello name **without decrypting** and passes the connection: `control.onemind.internal`, `join.onemind.internal` and the public control name → the hub's edge across the link; the DERP name → local `derper`. Anything else is closed. The relay never holds a key for any hub name.
- **derper:** `derper -a 127.0.0.1:4443 -hostname <derp name> -certmode letsencrypt -stun -http-port -1 -verify-client-url https://control.onemind.internal/verify -verify-client-url-fail-open=false`. Headscale publishes it as DERP region 900 through `derpmap.yaml`.
- **Certificates for a public control name:** the hub's edge obtains them with ACME TLS-ALPN-01 through the passthrough (`golang.org/x/crypto/acme/autocert`, BSD-3, already in `go.sum` at v0.58.0). The owner adds a **CAA record with `accounturi`** (RFC 8657) bound to the hub's ACME account, so the relay itself cannot obtain a certificate for that name.
- **Without a domain:** nodes need none (they use `control.onemind.internal` with the box CA). Phones need a name their Tailscale app trusts; see §10.

### 4.5 State and backup

| Path (on `/data`, the writable partition) | What | Lost means |
|---|---|---|
| `/data/onemind/mesh/headscale/db.sqlite` (+ WAL) | users, machines, keys, IPs, pre-auth keys | every machine and phone must re-enroll; mesh IPs change, so k3s on the hub breaks (§8) |
| `…/noise_private.key` | coordinator's Noise identity | clients re-handshake (**UNVERIFIED:** whether they need re-login; NT-11) |
| `…/derp_server_private.key` | embedded DERP identity | regenerated; harmless |
| `…/policy.json`, `extra-records.json`, `derpmap.yaml`, `config.yaml` | generated | regenerated by the gateway and custodian |
| `/data/onemind/mesh/tailscale/` (`tailscaled --statedir`, every machine) | the machine's mesh private keys | that machine re-enrolls (new join) |
| `/data/onemind/relay/` (relay VM) | relay WireGuard key, derper certs | redo `mesh.relay.add` |

- **Backups (BACKUPS.md unit `system`):** a pre-hook copies the database consistently with `sqlite3 -readonly db.sqlite ".backup /run/onemind/backup/headscale.db"` (Debian `sqlite3`, public domain), then restic includes the copy, the keys and the hub's `tailscale/` state. The restic repository is encrypted; these files hold private keys, so they never go into a plaintext export.
- **Restore onto a spare machine** (BACKUPS.md §7.3) restores the database and the hub's mesh state together, so the hub keeps `100.64.0.1` and every node keeps its address. Nodes find the new hub on the LAN by mDNS plus the pinned CA (§5.4).

## 5. Enrollment: tied to the owner-approved fabric join

### 5.1 Machines (worker, leaf)

The mesh adds one block to the FABRIC §4.1 bundle and two steps to the node's start sequence. Nothing about the ticket, pairing code or approval changes.

```
 Owner                     Gateway + custodian (hub)                 New machine
 approves node.join ─────► custodian signs certs + NATS creds (FABRIC)
 (pairing code matches)    custodian: headscale preauthkeys create
                             --tags tag:onemind-<role>[,tag:onemind-k3s]
                             --expiration 15m   (single use, not reusable, not ephemeral)
                           records the pre-auth key id against join_id
                                                       ◄──── GET /v1/fabric/join/{join_id} (signed)
                           bundle.mesh = {control_url: https://control.onemind.internal,
                             control_addrs: [<hub LAN addr>, <relay addr>?], ca_sha256,
                             auth_key (once), hostname: node-<id>, hub_mesh_ip}
                                                             writes auth key to a 0600 file in /run
                                                             tailscale up --login-server <control_url>
                                                               --auth-key file:<path> --hostname node-<id>
                                                               --accept-routes=false --ssh=false
                                                               [--shields-up on leaves]
                                                             deletes the key file; waits ≤ 60 s for its mesh IP
                           Headscale node registered ──────► custodian checks: registered with OUR key id,
                                                             hostname node-<id>, tags as minted; else deletes it
                                                             NATS leaf → tls://<hub mesh ip>:7422 (§7)
                                                             k3s agent → https://<hub mesh ip>:6443 (§8)
                                                             first heartbeat via its leaf
 node.join → succeeded when: first heartbeat, Headscale node bound, and (worker) k3s Node Ready
```

- `tailscale up --auth-key file:<path>` reads the key from a file (`cmd/tailscale/cli/up.go:102` at v1.104.6), so it never appears in argv or shell history (H-09).
- Tags are set **only** by the pre-auth key (`docs/ref/registration.md`, tagged keys). `tagOwners` lists no person for any OneMind tag, so no phone or laptop can claim a machine role. **UNVERIFIED:** Headscale accepts empty `tagOwners` lists (NT-4); fallback is a dedicated `custodian` user as the only tag owner.
- Fabric `node_id` ↔ Headscale node id ↔ mesh IP are stored in `fabric_nodes` (`mesh_node_id`, `mesh_ip`; FABRIC §12). The custodian matches by the pre-auth key id it minted (Headscale's node record carries its pre-auth key).

### 5.2 The hub itself

At install, before k3s starts: `onemindd` renders Headscale's config, starts it, mints a hub pre-auth key over the local socket (`--tags tag:onemind-hub,tag:onemind-k3s`), and runs `tailscale up` against `https://control.onemind.internal` (resolved to `127.0.0.1` on the hub). k3s then starts with the hub's mesh IP (§8). The order is fixed by systemd: `k3s.service` gets `After=tailscaled.service` and `ExecStartPre=onemindd mesh wait-ip --timeout 120s`.

### 5.3 Role changes and removal

- `node.set_role` (worker ↔ leaf, FABRIC §2) also re-tags: `headscale nodes tag -i <id> -t tag:onemind-leaf` (drops `tag:onemind-k3s`), then regenerates the policy.
- `node.remove` adds, to FABRIC §8 step 1: `headscale nodes delete -i <id>`, then policy regeneration. The machine loses mesh reach within one netmap update (seconds), before its certificate even expires.

### 5.4 Finding the coordinator: LAN first

`onemindd` keeps one line in `/etc/hosts` for `control.onemind.internal` and `join.onemind.internal` (and, on the hub, `127.0.0.1`):
1. Try each hub LAN address it knows, then `onemind.local` by mDNS. Use the first that presents a certificate chaining to the **pinned** box CA.
2. Else use the relay address (reach mode `relay`), or the public address (`direct`).
3. Re-check every 60 s and on link change. A change is logged, never silent.

So a power cut with the internet down still brings the LAN mesh back: every node finds the coordinator on the LAN. Because the name never changes, switching reach mode never re-enrolls a machine.

### 5.5 Phones and laptops (owner devices)

People's devices are **user-owned** Headscale nodes (one Headscale user per OneMind person, `person-<id>`), never tagged. Adding one adds reach, so it is the action `mesh.device.add` (high, owner only, never policy-approved; F-2 passkey step-up applies).

| Client | How it connects | OneMind flow |
|---|---|---|
| Android (Play or F-Droid) | Settings → Accounts → ⋮ → *Use an alternate server*, then *Use an auth key* (`docs/usage/connect/android.md`) | Owner taps **Add a device** → approves → the dashboard shows a QR with the server URL and a **10-minute, single-use** auth key for that person |
| iOS / iPadOS | Account → *Log in…* → options → *Use custom coordination server* (`docs/usage/connect/apple.md`); web registration | The phone shows Headscale's registration page with an auth id; the owner enters it under **Add a device** (or scans it) → the approval card shows the device name and OS from Headscale's pending registration → on approval the custodian runs `headscale auth register --user person-<id> --auth-id <id>` |
| macOS, Windows, Linux | `tailscale login --login-server <url>` or the GUI's custom login server (`docs/usage/connect/apple.md`, `windows.md`) | Either flow above |

- Removing a device (`DELETE /v1/mesh/devices/{id}`) is **not** an action: it only reduces reach. It is audited and takes effect at once.
- **Later (with SEC-P1 / Kanidm BD-03):** Headscale's OIDC login against the box, so a phone signs in with the owner's passkey instead of an auth id. Not in phase 1.

## 6. Access rules generated from OneMind roles

### 6.1 Model

| OneMind role | Mesh identity | May reach | Never |
|---|---|---|---|
| hub | `tag:onemind-hub`, `tag:onemind-k3s` | workers: 10250/tcp, 51820/udp | leaves (nothing listens there) |
| worker | `tag:onemind-worker`, `tag:onemind-k3s` | hub: 443, 6443, 7422/tcp; other k3s machines: 10250/tcp, 51820/udp | owner devices; leaves |
| leaf | `tag:onemind-leaf` | hub: 443 and 7422/tcp only | anything else |
| owner device | user `person-<id>`, `group:owners` | hub: 443/tcp (dashboard, apps, coordinator) | node ports (4222, 6443, 7422, 10250, 7480); SSH unless `mesh.ssh` is on |
| adult / guest device | user `person-<id>`, `group:adults` / `group:guests` | adults: hub 443/tcp; guests: nothing by default | as above |
| app | **not a mesh identity** | apps are reached through the edge on hub 443, and forward-auth decides per person and app (§9.3) | pods never use the node's mesh identity (§12, H-04 addition) |

The gateway is the only writer of the policy: it renders `policy.json` from the ledger (people, roles, devices, nodes) on every change, the custodian runs `headscale policy check` and writes it, then reloads Headscale (SIGHUP; `docs/ref/policy.md`). A policy that fails the check is not applied, and the alert `mesh.policy_rejected` is raised.

### 6.2 Generated policy (example, two owners' devices, one worker, one leaf)

```jsonc
{
  "groups": {
    "group:owners": ["person-owner@"],          // OneMind person ids; never emails or names
    "group:adults": ["person-ab12@"],
    "group:guests": []
  },
  "tagOwners": {                                  // no person may claim a machine tag (§5.1)
    "tag:onemind-hub": [], "tag:onemind-worker": [], "tag:onemind-leaf": [], "tag:onemind-k3s": []
  },
  "grants": [
    {"src": ["group:owners", "group:adults"], "dst": ["tag:onemind-hub"], "ip": ["tcp:443"]},
    {"src": ["tag:onemind-worker", "tag:onemind-leaf"], "dst": ["tag:onemind-hub"], "ip": ["tcp:443", "tcp:7422"]},
    {"src": ["tag:onemind-worker"], "dst": ["tag:onemind-hub"], "ip": ["tcp:6443"]},
    {"src": ["tag:onemind-k3s"], "dst": ["tag:onemind-k3s"], "ip": ["tcp:10250", "udp:51820"]}
  ]
  // No other grant: Headscale denies everything not granted. Exit nodes and subnet routes are
  // not offered (no autoApprovers), so a node cannot route the household's traffic.
}
```

Grants are what Headscale recommends over legacy ACLs (`docs/ref/policy.md`). Replies to an allowed connection flow back automatically, so `udp:51820` in both directions between k3s machines is one rule.

### 6.3 Optional grants (each an approved owner setting)

| Setting | Grant added | Action |
|---|---|---|
| Owner SSH to machines | `group:owners` → `tag:onemind-k3s`, `tag:onemind-leaf`: `tcp:22` (OpenSSH, not Tailscale SSH) | `mesh.ssh.set {enabled}` (high) |
| An app that needs raw TCP from leaves (e.g. MQTT 1883) | `tag:onemind-leaf` → `tag:onemind-hub`: `tcp:<port>`, plus an edge L4 forward | from the app manifest `spec.network.mesh` (phase 2; shown in the approval plan) |

## 7. NATS over the mesh: leaf auth, TLS and permissions

This is FABRIC §5 with the transport fixed. It retires the v0 shortcut ("nodes publish straight to the hub's NATS, no auth/TLS", contract header).

**Hub `nats.conf` (key parts):**
```
listen: 127.0.0.1:4222
http: 127.0.0.1:8222
jetstream { store_dir: /data/onemind/nats, domain: hub }
tls { cert_file: /data/onemind/nats/tls/server.pem, key_file: …/server.key,
      ca_file: /data/onemind/nats/tls/ca.pem, verify: true }        # local clients present custodian-issued certs
leafnodes {
  listen: "100.64.0.1:7422"                                        # hub mesh IP (example); also 127.0.0.1
  tls { cert_file: …/server.pem, key_file: …/server.key, ca_file: …/ca.pem,
        verify: true, timeout: 5 }                                 # node certificate from FABRIC §3 required
  # no authorization block: leaf logins use the users below (R8)
}
include /data/onemind/nats/users.conf                             # written by the gateway, reloaded with --signal reload
```

**Generated `users.conf` (one entry per approved node; FABRIC §5.2 table):**
```
authorization { users = [
  { nkey: <gateway public nkey>,   permissions: { … gateway set … } },
  { nkey: <custodian public nkey>, permissions: { … } },
  { nkey: <node 3f9c2a1b7d4e public nkey>, permissions: {
      publish:   { allow: ["onemind.node.3f9c2a1b7d4e.status", "onemind.node.3f9c2a1b7d4e.event.>",
                           "onemind.node.3f9c2a1b7d4e.jobresult.>",
                           "$JS.API.CONSUMER.MSG.NEXT.ONEMIND_JOBS.node-3f9c2a1b7d4e",
                           "$JS.ACK.ONEMIND_JOBS.node-3f9c2a1b7d4e.>"] },
      subscribe: { allow: ["_INBOX.>", "$JS.node-3f9c2a1b7d4e.API.>"] } } }
] }
```
In NATS terms these are the permissions *of the leaf connection as seen from the hub*; the server reverses publish and subscribe for the leaf direction (R8). The `$JS.node-<id>.API.>` entry lets the hub's `ONEMIND_NODE_OUTBOX` source reach the node's JetStream domain. **UNVERIFIED:** the exact set of `$JS` delivery and flow-control subjects that cross-domain sourcing needs under these permissions; NT-6 records them with `nats --trace` and the list is fixed in contract text then (never `>`).

**Node leaf `leaf.conf`:**
```
server_name: node-3f9c2a1b7d4e
listen: 127.0.0.1:4222                                             # onemindd and local services only
jetstream { store_dir: /data/onemind/nats, domain: node-3f9c2a1b7d4e, max_file_store: 256MB }
leafnodes { remotes: [ {
  urls: ["tls://100.64.0.1:7422"]                                  # hub mesh IP from the bundle
  nkey: "<seed>"                                                   # the node's own seed; file mode 0600
  tls { cert_file: /data/onemind/identity/tls.crt, key_file: /data/onemind/identity/tls.key,
        ca_file: /data/onemind/identity/ca.pem }                   # pins the box CA
} ] }
```
The node's `ONEMIND_NATS_URL` becomes `nats://127.0.0.1:4222` (contract §1 keeps the variable). Outbox stream, limits and the "syncing until source lag = 0" rule are FABRIC §5.3 and W8-R2 unchanged.

**Defence in depth:** NATS refuses a leaf without a valid node certificate (TLS `verify`), without the node's nkey, and from any address that is not on the mesh (port bound to the mesh IP, H-04 firewall). The mesh policy (§6) refuses 7422 from anything but worker and leaf tags.

## 8. k3s over the mesh

**Hub `/etc/rancher/k3s/config.yaml` (cluster-creation settings, set before data moves):**
```yaml
node-ip: 100.64.0.1                 # hub mesh IP (example), from `tailscale ip -4`
advertise-address: 100.64.0.1
tls-san: [hub.onemind.internal]
flannel-backend: wireguard-native   # H-17
flannel-iface: tailscale0
node-name: node-<node_id>           # FABRIC §4.1
```
**Worker:** `server: https://100.64.0.1:6443` (mesh IP from the bundle, not a name, so DNS cannot break joins), `node-ip: <own mesh IP>`, `flannel-iface: tailscale0`, the FABRIC labels, bootstrap token from the approved bundle.

- **Why mesh addresses even on one LAN:** the same config works at home, across sites and after a hub restore; the k3s API and kubelet are never reachable from the LAN; and the mesh policy decides who may talk to them.
- **Double encryption:** pod traffic is WireGuard (flannel) inside WireGuard (Tailscale). H-17's acceptance (no VXLAN on the LAN interface) passes. The cost is CPU on Pis and a smaller pod MTU: flannel subtracts 80 bytes from `tailscale0`'s 1280, so pods get 1200. **UNVERIFIED:** the throughput hit on a Pi 5; NT-9 measures it. If cross-node pod throughput on a Pi 5 is below 200 Mbit/s, the fallback is flannel `vxlan` on `tailscale0` (still encrypted by the mesh, one layer less), recorded as a founder call before it is used.
- **Firewall interplay:** tailscaled, flannel and kube-router all program netfilter on Debian 13 (nftables). **UNVERIFIED** that they coexist without rule fights; NT-8 runs the H-04 and H-17 acceptance tests with all three active.
- **Existing v0 clusters:** `flannel-backend`, `node-ip` and `advertise-address` cannot be changed safely on a running cluster. Boxes installed by `feat/deploy-v0` before this lands are rebuilt (`install.sh --role hub --rebuild-cluster`, after a backup) **before** the founder moves data (HARDENING-BACKLOG ordering note).

## 9. LAN: names, the edge, sign-in and the per-box CA

### 9.1 mDNS names

- avahi publishes the box as `<box>.local` and adds `onemind.local` plus one name per installed app with a web UI, `<app>.onemind.local`, through `/etc/avahi/hosts` (address = the hub's LAN address). `onemindd` on the hub rewrites that file from the edge route table when apps are installed or removed. RFC 6762 allows multi-label names under `.local`.
- **Conflicts:** if another device already answers `onemind.local` (a second OneMind box, or a renamed one), avahi does not publish it; `onemindd` detects this with `avahi-resolve` and raises `lan.name_conflict`. The box stays reachable as `<box>.local`, apps as `<app>.<box>.local`, and the dashboard shows the names in use. The edge's certificate covers both forms.
- Nodes resolve `.local` through `libnss-mdns`. **UNVERIFIED:** multi-label `.local` resolution on Android, Windows and some Linux desktops (NT-13). Fallback for those: path routes `https://onemind.local/apps/<app>/` (apps that break under a sub-path say so in the catalog).
- Over the mesh the same apps are `<app>.apps.onemind.internal` (Headscale extra records → the hub's mesh IP).

### 9.2 The edge (`onemind-edge`, Go, hub only)

One process, `:443` on LAN and mesh addresses, started by systemd with `CAP_NET_BIND_SERVICE` as an unprivileged user. It holds server certificates and keys, never the CA key. Routes come from the gateway (`/run/onemind/edge/routes.json`, written atomically, read-only to the edge).

| Host (SNI) | Goes to | Sign-in |
|---|---|---|
| `onemind.local`, `<box>.local`, `hub.onemind.internal` | gateway `127.0.0.1:8080` (dashboard + API) | the gateway's own |
| `<app>.onemind.local`, `<app>.<box>.local`, `<app>.apps.onemind.internal` | the app's `ClusterIP` Service | forward-auth (§9.3) |
| `control.onemind.internal`, the public control name | Headscale `127.0.0.1:8085`, **except** `/api/` (Headscale's REST API, which shares that listener) → 404 | Headscale's (machine keys) |
| `join.onemind.internal` | gateway, **only** `POST /v1/fabric/join` and `GET /v1/fabric/join/{id}` | the join ticket and node signature (FABRIC §4) |
| anything else | TLS alert, connection closed | – |

- WebSockets and HTTP upgrades are passed through (`net/http/httputil.ReverseProxy`). Request bodies and timeouts follow H-20.
- Security headers on gateway routes are the gateway's (H-18). Edge adds `Strict-Transport-Security` only for public names.
- **Not** a general ingress controller: apps cannot add routes; only the gateway writes `routes.json`, from manifests that passed the app gate (H-02). `NodePort` and `hostPort` stay forbidden.

### 9.3 Forward-auth (H-29)

For every app request the edge calls the gateway on loopback: `GET /v1/auth/forward` with the original host, method and path, and the session cookie (the cookie is scoped to `.onemind.local`, `HttpOnly`, `Secure`, `SameSite=Lax` for top-level navigation between app names; H-16).

| Gateway answer | Edge does |
|---|---|
| 204 + `X-OneMind-Principal: person:<id>` | proxies to the app, adding `X-OneMind-Principal` and `X-OneMind-Role` and stripping any such header the client sent |
| 401 | redirects to `https://onemind.local/login?next=<url>` |
| 403 | shows "You do not have access to <app>" (the app's `access` setting: owner only, adults, everyone signed in; default adults) |

Decisions are cached by the edge for 30 s per session and app, so a revoked session stops working within 30 s. Agent tokens are never accepted on app hosts.

### 9.4 Per-box CA and how phones trust it (H-05, F-1)

- The box CA is the FABRIC §3 custodian CA (ECDSA P-256, 10 years). This design adds one requirement: the CA certificate carries **X.509 name constraints** (RFC 5280 §4.2.1.10) permitting only `onemind.local`, `.onemind.local`, `<box>.local`, `.<box>.local`, `onemind.internal`, `.onemind.internal`, and the mesh ranges as IP constraints. A phone that trusts this CA therefore cannot be fooled for any other site if the CA key leaks. **UNVERIFIED:** enforcement of name constraints on user-installed roots by iOS, Android Chrome and Firefox (NT-14); if a platform ignores them, the risk is stated in the pairing screen.
- The edge certificate (1 year, auto-renewed by the custodian): SANs `onemind.local`, `*.onemind.local`, `<box>.local`, `*.<box>.local`, `hub.onemind.internal`, `control.onemind.internal`, `join.onemind.internal`, `*.apps.onemind.internal`.
- **iPhone/iPad:** the pairing QR (URL + CA fingerprint, never a token, CORE-SEC-1) opens a page that offers the CA as a configuration profile; the owner installs it, then turns on full trust under Settings → General → About → Certificate Trust Settings (Apple's documented step for manually installed roots). The OneMind app pins the fingerprint as well.
- **Android:** apps targeting API 24+ trust only system CAs unless they opt in (Android network security configuration). The OneMind app opts in for the box CA only. Chrome uses the user store; **UNVERIFIED** for every browser (NT-14).
- **Desktop:** `onemind tls trust` installs the CA into the OS store (macOS Keychain, Windows, Debian `update-ca-certificates`) with a confirmation prompt.
- **Tailscale apps and the box CA:** a node never needs it in the system store (it pins the CA itself). A phone's Tailscale app talks to the coordinator over HTTPS with the **system** trust store. **UNVERIFIED** whether the official iOS and Android apps accept a user-installed root (NT-12). Until that passes, phones use a **public control name with a publicly trusted certificate** (§4.4, relay or direct mode), which needs an owner domain. This is why `lan` mode does not offer **Add a device**.

## 10. Remote access for phones and laptops

1. Owner sets reach mode `relay` (or `direct`) with a public control name, e.g. `control.example.org` (owner's domain; example name).
2. Network → **Add a device** → the flow in §5.5 → the device appears under the owner's name.
3. Away from home, the phone opens `https://onemind.local` … which does not resolve off-LAN. So the dashboard and app links use **the mesh names** when the app detects it is not on the box's LAN: `https://hub.onemind.internal`, `https://<app>.apps.onemind.internal` (MagicDNS in the Tailscale app). Same edge, same sign-in, same certificate (box CA).
4. The phone reaches only hub 443 (§6). Traffic is end-to-end WireGuard; the relay, when used, sees encrypted packets only.

Tailscale's own certificates (`tailscale cert`) are **not** used with Headscale in phase 1. Research 12 §8.1 notes that those names land in public certificate-transparency logs, and Headscale's support for them was not checked.

## 11. Exposing an app publicly (parked)

Making an app reachable from the open internet is the reserved action family `exposure.*` (CONTRACT-12-DRAFT §12.2: critical, owner only, **never** policy-approved), owned by CORE-DOGFOOD-3's exposure review. With the relay and the edge in place it is mechanically small: the relay's SNI router passes `<app>.example.org` to the hub; the edge gets an ACME certificate and keeps forward-auth on unless the owner chooses "public, no OneMind sign-in" with typed confirmation. It stays **parked** until the exposure review defines rate limits, an app-level security rating (H-19) and an automatic expiry. Nothing in Part 1 or Part 2 builds it.

## 12. Failure modes and what the UI shows

| Failure | What happens | What the owner sees (Network page, Home, alerts) | Recovery |
|---|---|---|---|
| Internet down, LAN up | LAN mesh unaffected (coordinator on the LAN, §5.4); remote phones and sites lose reach | Reach pill "LAN only (internet down)"; remote nodes go `stale` → `offline` (FABRIC §6), leaf outboxes buffer | Automatic on return; nodes show "syncing" until source lag is 0 |
| Headscale down | Existing tunnels keep working with the last network map; no new joins, devices, or policy changes | `mesh.control_down` alert after 2 min; join and device actions return 503 `unavailable` (`reason: mesh_control_down`) | systemd restarts it; else restore its database |
| Relay VM down | Remote phones and sites lose reach unless a direct path exists; LAN unaffected | "Relay unreachable since …"; alert `mesh.relay_down` | Fix or replace the relay (`mesh.relay.add` again) |
| A pair of machines cannot connect directly | Traffic goes through DERP (embedded or relay); slower, still encrypted | Node card: "relayed" path badge; alert only if relayed for > 24 h on the same LAN (`mesh.path_relayed`) | Check router UDP; nothing to do across sites |
| `tailscaled` down on a worker | Its NATS leaf and k3s links drop; local apps keep running | Node `degraded: mesh_down` while heartbeats still arrive; else `stale`/`offline` | `system.restart_unit` gains `tailscaled` in its allowlist |
| `tailscaled` down on the hub at boot | k3s waits up to 120 s for the mesh IP, then fails | Console and local status page: "mesh not up: k3s not started"; Repairs offers the fix | Restart tailscaled; check Headscale; restore if the database is lost |
| Headscale database lost, no backup | All machines must re-join; hub mesh IP may change, breaking k3s | Repair `mesh.state_lost` | Restore (BACKUPS.md); otherwise rebuild the cluster and re-join |
| Mesh IP conflict with another VPN on a laptop (`100.64.0.0/10` also used by CGNAT or another tailnet) | That laptop cannot route | Device card: "address conflict" when the Tailscale app reports it | Owner uses one Tailscale account at a time on that laptop |
| Policy rejected | Old policy stays in force | Alert `mesh.policy_rejected` with Headscale's message | Fix the role change that caused it |
| `onemind.local` taken on the LAN | Box answers on `<box>.local` | Network page shows the names in use; `lan.name_conflict` | Rename the other box, or keep `<box>.local` |
| Public certificate renewal fails | Phones fail TLS after expiry | `mesh.cert_expiring` 14 days ahead | Check DNS and CAA; relay reachable |
| Clock skew > 60 s | TLS and NATS fail | `degraded: clock_skew` (FABRIC §6) | NTP repair |

**Network page (owner):** reach mode and its health (coordinator, relay, DERP regions with last check); machines with mesh state `up|down`, path `direct|relayed`, last handshake age; devices per person with OS, last seen and Remove; names in use. **No IP addresses by default** (contract §2); "Show addresses" is an owner-only toggle that is not remembered.

Heartbeat addition (§15): `fabric.mesh: {state: up|down|none, path: direct|relayed|none}`. Mesh IPs are not in the heartbeat; the gateway reads them from Headscale.

## 13. Security

| # | Threat | Mitigation | H-item |
|---|---|---|---|
| S1 | LAN sniffing of tokens, NATS, pod traffic | HTTPS on the edge; NATS TLS; pod traffic in WireGuard; NATS and k3s bound to the mesh | H-05, H-06, H-17 |
| S2 | A LAN device impersonates a node on NATS | TLS client cert + per-node nkey + own-subject permissions; 7422 on mesh only | H-06 |
| S3 | A stranger joins the mesh | Pre-auth keys only after an approved `node.join`, 15 min, single use, delivered once to the key holder; tags only from keys | H-23 |
| S4 | A phone claims a machine role | `tagOwners` empty for all OneMind tags; devices are user-owned and reach hub 443 only | – |
| S5 | A compromised app pod uses the node's mesh identity to reach hub 7422/6443 | **H-04 addition:** default egress NetworkPolicy also denies `100.64.0.0/10` and `fd7a:115c:a1e0::/48`, and the host nftables table drops forwarded pod-CIDR traffic to `tailscale0` | H-04 |
| S6 | Compromised relay VM | Sees metadata and ciphertext only; TLS ends on the hub; CAA `accounturi` stops it from getting a certificate for the control name; derper verifies clients with fail-open off (R6); removing the relay is instant | – |
| S7 | Compromised Headscale (hub root), or a stolen Headscale API key | Same blast radius as hub root today. Headscale is local-only (`127.0.0.1`). Since R9 the gateway holds a Headscale API key (0600 file, gateway user; `mesh.py` refuses a group- or world-readable file and any non-loopback URL), so **a compromised gateway can mint keys**: the same trust the gateway already has as the approver. The key is never logged or audited; the edge never proxies `/api/` (§9.2). Rotate with `headscale apikeys expire` + a new file | – |
| S8 | Unauthenticated app UIs on the LAN | Apps only through the edge with forward-auth; no NodePort/hostPort | H-29, H-02 |
| S9 | Leaked CA key used against the owner's phone for other sites | Name constraints on the CA (§9.4); custodian-only key | H-05 |
| S10 | `onemindd` API exposed | Loopback only; mesh policy grants no access to 7480 | H-24 |
| S11 | Join key in process listings | `--auth-key file:`; k3s `--vpn-auth` not used (R7) | H-09 |
| S12 | Dependency on Tailscale Inc | `derp.urls: []`, `disable_check_updates`, `logtail` off; clients use only the owner's control URL; `hosted` mode is opt-in | – |
| S13 | DoS on the join route through the relay | `join.onemind.internal` passes only two routes; FABRIC's `rate_limited` 10/min per source | H-20 |
| S14 | Exit-node or subnet-route hijack | No `autoApprovers`; the gateway rejects advertised routes (custodian disables any route Headscale lists) | – |

Assumptions: hub root is trusted (as in THREAT-MODEL §2); WireGuard and the Tailscale client are not independently audited by this project.

## 14. Resource budget (Raspberry Pi 5)

Numbers below are **targets**, not measurements. NT-10 measures RSS and idle CPU on a Pi 5 (4 GB) and records them in `research-output/evidence/lab/net-pi-budget/`.

| Machine | Added by this design | Target RSS | Target idle CPU |
|---|---|---|---|
| Hub | Headscale + embedded DERP, tailscaled, `onemind-edge`, avahi | ≤ 250 MiB together | ≤ 3 % of one core |
| Worker (Pi 5, 4 GB) | tailscaled, NATS leaf, avahi | ≤ 120 MiB | ≤ 2 % |
| Leaf (Pi 4/5, 2 GB) | tailscaled, NATS leaf (256 MiB file store cap), avahi | ≤ 100 MiB | ≤ 2 % |
| Relay VM | derper, SNI router, WireGuard | ≤ 80 MiB (fits a 512 MiB VM) | – |
| Pod network, Pi 5 ↔ Pi 5 on wired LAN | WireGuard in WireGuard | ≥ 200 Mbit/s cross-node pod throughput | – |

If a target is missed by more than 25 %, the step stops and the number goes to the founder with options (e.g. leaf without local JetStream, FABRIC §5.1; flannel `vxlan` on `tailscale0`, §8).

## 15. Contract §12.16 networking (proposed text, adopted in Part 2)

> **12.16 Networking.** Additive.
> **Action types** (added to §12.2's registry): `mesh.device.add {person_id, method: auth_key|register, auth_id?, label}` — risk high, may request O, policy **never**, runs on G (custodian), result carries `one_time: {control_url, auth_key?}`; `mesh.relay.add {pairing}` — critical, O, never, G; `mesh.relay.remove {}` — medium, O, yes, G; `mesh.reach.set {mode: lan|relay|direct|hosted, public_name?}` — critical, O, never, G; `mesh.ssh.set {enabled}` — high, O, no, G. `node.join`'s bundle gains `mesh` (below). `system.restart_unit`'s allowlist gains `tailscaled`, `onemind-headscale`, `onemind-edge`.
> **Routes:** `GET /v1/mesh` (any principal) → `{mode, control: {state, checked_at}, relay: {state, checked_at} | null, derp: [{region, state}], nodes: [{node_id, state: up|down, path: direct|relayed|none, last_handshake_at}], devices: [{id, person_id, label, os, online, last_seen}], names: {lan: [...], mesh: [...]}}`; with `?addresses=1` (owner only) each node and device adds `mesh_ip`. `GET /v1/mesh/devices` (owner: all; person: own). `DELETE /v1/mesh/devices/{id}` (owner, or the device's person) → 204, audited, not an action. `GET /v1/auth/forward` (loopback only; the edge) → 204 with `X-OneMind-Principal` / 401 / 403.
> **Join bundle** (§12.4) gains `mesh: {control_url, control_addrs: [..], ca_sha256, auth_key, hostname, hub_mesh_ip, tags}`; `auth_key` is a one-time output.
> **Heartbeat** (§12.11) gains `fabric.mesh: {state: up|down|none, path: direct|relayed|none, hub_path: direct|relayed|none, peers, direct, relayed, last_handshake}` (counts are integers, `last_handshake` RFC 3339 or null) and `fabric.leaf: {state: up|down|no_server, rtt?}`; never an address or a peer name (the local `onemind mesh status` shows those; implemented as `mesh.Heartbeat` and `leaf.Health`).
> **Catalog** (§11.4) gains `urls: {lan, mesh}` per app with a web UI; the dashboard links to them instead of `http://host:port`.
> **Events:** `mesh.control_down`, `mesh.relay_down`, `mesh.path_relayed`, `mesh.policy_rejected`, `mesh.cert_expiring`, `mesh.state_lost`, `lan.name_conflict`; reasons `mesh_control_down`, `mesh_lan_only`.
> **Env** (§1): `ONEMIND_MESH` (`on` / `off`, default `on` for new installs), `ONEMIND_EDGE_ADDR` (default `:443`).

## 16. Test plan and acceptance

Lab rules: Lima VMs under the lab folder only, deleted after each run; generated keys only; masked addresses in committed logs; pass/fail written before the run (as in `evidence/lab/PREREGISTRATION.md`). Topology for NT-1…NT-9: VM `hub`, VM `worker`, VM `leaf` on one Lima network ("home"), VM `field` on a second network behind nftables masquerade (NAT), VM `relay` with a reachable address, NAT between "home" and the relay too.

| # | Test | Pass when |
|---|---|---|
| NT-1 | Fresh hub install with `ONEMIND_MESH=on` | Hub has `100.64.0.1`; k3s node InternalIP is the mesh IP; `ss` shows 6443, 7422, 10250 not bound to the LAN interface (or dropped by nftables); `curl https://onemind.local` with the box CA → 200 |
| NT-2 | Headscale behind `onemind-edge` (control protocol + embedded DERP over the proxy) | `tailscale up` through the edge succeeds; `tailscale debug derp onemind-hub` passes |
| NT-3 | Worker and leaf join through the FABRIC flow | Bundle has `mesh`; both get mesh IPs; Headscale nodes carry the minted tags and hostnames; auth key file gone; key reuse fails; a key past 15 min fails; worker `Ready` in k3s with mesh InternalIP |
| NT-4 | Role isolation (policy §6.2) | From the leaf: hub 7422 and 443 open, hub 6443 and worker 10250 closed. From an owner device: hub 443 open, 7422/6443/22 closed. A device advertising `tag:onemind-hub` is refused or untagged |
| NT-5 | Field node behind NAT, reach mode `relay` | Field node joins via `join.onemind.internal` through the relay; path `direct` or `relayed`; nothing listens on the "home" network's router side; relay `tcpdump` shows only TLS and WireGuard |
| NT-6 | NATS leaf auth and permissions (extends H-06's test and FABRIC FT-3, FT-5) | Leaf without node cert → refused; with node A's nkey publishing `onemind.node.B.status`, `onemind.audit`, `onemind.node.A.job.x` → permission violations; outbox sourcing works under the generated permissions (W8-1 replayed: 500 events across a 30-min hub outage, all delivered, in order); the `$JS` subject list is recorded |
| NT-7 | Internet cut at "home" (relay unreachable) | LAN mesh, NATS leaves and k3s keep working; a worker rebooted during the cut rejoins the mesh via LAN-first resolution |
| NT-8 | H-04 + H-17 with tailscaled active | H-17's tcpdump: no VXLAN on the LAN interface; H-04's pod tests pass, plus: a pod's connection to `100.64.0.1:7422` and `:6443` times out |
| NT-9 | Pod throughput (Pi 5 pair, wired; VMs for a smoke run) | iperf3 pod ↔ pod across nodes ≥ 200 Mbit/s on Pi 5 (recorded with CPU %) |
| NT-10 | Pi resource budget (§14) | Measured RSS and idle CPU within targets, recorded |
| NT-11 | Hub restore onto a new VM from restic | Hub keeps `100.64.0.1`; nodes reconnect without re-joining; Noise-key loss case recorded |
| NT-12 | Official Tailscale apps (Android, iOS, macOS) against Headscale: public LE name; box CA name | Public name: enrolls via §5.5 and reaches only hub 443. Box-CA case: pass/fail recorded per platform (decides whether `lan` mode can ever add devices) |
| NT-13 | mDNS names (`onemind.local`, `<app>.onemind.local`) from macOS, iOS, Android, Windows, Debian | Resolution recorded per OS; path-route fallback works where it fails |
| NT-14 | Name-constrained CA | A leaf cert for `example.com` signed by the box CA is rejected on each platform that claims support; results recorded |
| NT-15 | Forward-auth | No session → redirect to sign-in; guest on an adults-only app → 403; revoked session fails within 30 s; client-sent `X-OneMind-Principal` is stripped |
| NT-16 | Removal | `node.remove` and device removal: mesh reach gone within 10 s; Headscale node deleted; audit lines present |
| NT-17 | No third-party contact | 24 h packet capture on hub and nodes in `lan` mode: no traffic to any Tailscale Inc address or `controlplane.tailscale.com` / `log.tailscale.com` |

Unit tests (Part 1, in CI): config and policy renderers (golden files), the SNI router (ClientHello parsing, unknown names closed), the edge router and forward-auth (httptest), LAN-first resolver (fake dialer + fake CA), Headscale adapter against a fake `headscale` binary, NATS users and leaf configs loaded by the in-process `nats-server` (already a test dependency in `go.mod` at v2.15.3) with real permission checks.

## 17. Build steps

Sizes as the leap: S ≤ 1 day, M 2–4 days, L 1–2 weeks. **Part 1** adds new modules only and touches no hotspot file, so it can run in parallel with the in-flight gateway, deploy and pipeline branches. **Part 2** wires them in, after those branches merge.

### Part 1: new modules

| Id | Step | Size | Depends on | New paths |
|---|---|---|---|---|
| CORE-NET-1 | Headscale adapter (`Coordinator` interface; exec `headscale -o json` over the local socket: users, pre-auth keys, nodes, tags, register, policy check/set); config + DERP-map renderer | M | – | `internal/mesh/coord/` |
| CORE-NET-2 | Policy generator from roles (§6), golden tests | S | – | `internal/mesh/policy/` |
| CORE-NET-3 | Node enrollment (auth key file, `tailscale up`, wait-ip, bind check), LAN-first coordinator resolver (§5.4), mesh state for the heartbeat | M | NET-1 | `internal/mesh/` (**built**: enroll, wait-ip, status, heartbeat object, `onemindd mesh` CLI; drives the system tailscale CLI, no tsnet, reasons in the package doc); still to do: `internal/mesh/resolve/` (§5.4) and `hub-init` (§5.2) |
| CORE-NET-4 | NATS config renderers: hub users + leaf listener, node leaf; tests with the in-process server; lab NT-6 | M | – | `internal/leaf/` (**built**: node `leaf.conf` renderer, 0600 per-node nkey include file, atomic apply + reload, `/leafz` health; in-process test proves TLS-pinned, nkey-authenticated leaf with per-node publish permissions and refusals for unknown nkey, foreign CA, missing node cert); still to do: hub `users.conf` + leaf listener renderer in `internal/natsconf/` |
| CORE-NET-5 | `onemind-edge`: SNI cert selection, host routes, forward-auth client, upgrades, optional ACME | M | – | `internal/edge/`, `cmd/onemind-edge/` |
| CORE-NET-6 | LAN names: avahi hosts renderer, conflict check, Headscale extra-records renderer | S | – | `internal/lan/` |
| CORE-NET-7 | Relay: SNI router, setup endpoint, systemd-networkd renderer, `onemind-relay` binary; derper build module | M | – | `internal/relay/`, `cmd/onemind-relay/`, `third_party/derper/` |
| CORE-NET-8 | Gateway modules (not registered yet). **Done in Part 1:** Headscale REST client + `MeshService` (approved-only key minting, expiry, bind check, removal, role re-tag, policy render/check/apply, all audited); app reverse proxy with forward-auth decision; per-box CA. **Left:** `/v1/mesh` routes, `/v1/auth/forward` endpoint, routes.json writer, `mesh.*` action handlers | M | NET-2 | `core/onemind_core/mesh.py`, `core/onemind_core/proxy.py`, `core/onemind_core/ca.py` (+ tests) |
| CORE-NET-9 | Lab: NT-1…NT-8 and NT-17 in Lima (scripts + preregistration + results) | M | NET-1…NET-7 | `research-output/evidence/lab/net-mesh/` |

### Part 2: wiring (hotspots, serialized)

| Id | Step | Size | Depends on |
|---|---|---|---|
| CORE-NET-10 | Contract PR §12.16 (text in §15) | S | NET-9 |
| CORE-NET-11 | Installer and image: pins, packages, units, hub bootstrap order, k3s mesh config, NATS leaf config, `--rebuild-cluster` | M | NET-10, W2-DEPLOY merged, CORE-SEC-1 |
| CORE-NET-12 | Gateway and onemindd registration; join bundle `mesh` block; FABRIC join/remove/set_role hooks | M | NET-10, CORE-FABRIC-1, W2-GW merged |
| CORE-NET-13 | Dashboard: Network page, Add a device, relay pairing, app links to `urls` | M | NET-12, CORE-DASH (design system) |
| CORE-NET-14 | Pi measurements and phone matrix: NT-9…NT-14 on hardware | S | NET-11, F-25 hardware |
| CORE-NET-15 | Public exposure (§11) | – | **parked** (CORE-DOGFOOD-3) |

Critical path for the founder's cluster switch: CORE-SEC-1 (CA) → NET-1/3/4/5 → NET-9 lab → NET-10 → NET-11/12. Recommended start: NET-1…NET-7 in S1 next to CORE-SEC-1, because flannel backend and node IPs are cluster-creation settings.

## 18. Integration: every one-line hotspot change Part 2 makes

Part 1 must not edit these files. Line references are to the in-flight branches named.

| File | Change | Where |
|---|---|---|
| `core/onemind_core/app.py` | `app.include_router(mesh.router(settings, ledger, custodian))` | before the SPA catch-all `@app.get("/{full_path:path}")` (`feat/gateway-agent-mcp`, ~line 238) |
| `core/onemind_core/app.py` | `app.include_router(forward_auth.router(settings, sessions))` | same place |
| `core/onemind_core/app.py` | `box_ca = BoxCA(data_dir / "tls", settings.box_name); box_ca.ensure_gateway_cert(); box_ca.ensure_wildcard_cert()` | in `create_app`, after `settings.check()` |
| `core/onemind_core/app.py` | `app_proxy = AppProxy(catalog, lambda i: (st := repo.get_app_state(i)) and st.status, token_session_resolver(tokens), KubectlServiceResolver(settings.kubectl), box_domains=("onemind.local", f"{settings.box_name}.local", "apps.onemind.internal"), audit=audit.append)` | after `tokens`/`repo`/`catalog` are built |
| `core/onemind_core/app.py` | `app.add_middleware(AppProxyMiddleware, proxy=app_proxy)` | right after `install_handlers(app)` (a middleware, so it sees app hosts and `/apps/<id>/` before any route, HTTP and WebSocket) |
| `core/onemind_core/app.py` | `mesh_service = MeshService(HeadscaleClient.from_key_file("http://127.0.0.1:8085", settings.headscale_key_file), audit, clock) if settings.mesh_enabled else None` | after `audit` is built; handed to the `node.join` / `mesh.*` handlers |
| `core/onemind_core/app.py` | `GET /v1/tls/ca.crt` → `Response(box_ca.ca_der(), media_type="application/x-x509-ca-cert")` and the fingerprint in `/v1/instance` | with the instance routes. Phones fetch it before they can sign in, so it is the second open route after `/healthz`: needs the contract §3 change (§15) |
| `core/onemind_core/app.py` | add `"mesh"` to `API_EXACT`-style prefixes so `/v1/mesh` never falls to the SPA | `API_EXACT` (~line 35) |
| `core/onemind_core/actions.py` | register `mesh.device.add`, `mesh.relay.add`, `mesh.relay.remove`, `mesh.reach.set`, `mesh.ssh.set` in the type registry | `ActionType` |
| `core/onemind_core/config.py` | settings `mesh_enabled` (`ONEMIND_MESH`), `edge_routes_path`, `headscale_key_file` (`ONEMIND_HEADSCALE_KEY_FILE`), `box_name` (`ONEMIND_BOX_NAME`, a DNS label), `data_dir` (`ONEMIND_DATA_DIR`, today read only inside `from_env`) | `Settings` |
| `core/pyproject.toml` + `uv.lock` | **already changed on this branch:** runtime deps `cryptography>=50.0.2,<51` (Apache-2.0 OR BSD-3; pulls `cffi` MIT, `pycparser` BSD-3), and `h11>=0.16,<1` (MIT) and `websockets>=15,<18` (BSD-3), which were already installed through `uvicorn[standard]` and are now declared because `proxy.py` imports them. `httpx` was **not** made a runtime dependency because it requires `certifi` (MPL-2.0). `feat/gateway-agent-mcp` also edits both files: whichever merges second re-runs `uv lock` | `[project] dependencies` |
| `deploy/install.sh` (hub) | `headscale apikeys create --expiration 90d` → `/etc/onemind/headscale.key` (0600, owner = the gateway's user), set `ONEMIND_HEADSCALE_KEY_FILE` | `mesh_install`, after Headscale starts |
| `core/onemind_core/catalog.py` | each entry gains `urls: {lan, mesh}` | catalog builder |
| `cmd/onemindd/main.go` | `if len(os.Args) > 1 && os.Args[1] == "mesh" { os.Exit(mesh.RunCLI(os.Args[2:], os.Stdout, os.Stderr)) }` (`enroll`, `wait-ip`, `status` exist in `internal/mesh/cli.go`; `resolve`, `hub-init` added there later) | next to the `update` dispatch |
| `cmd/onemindd/main.go` | `agent.Config{…, MeshReport: mesh.Reporter(log)}` (when `ONEMIND_MESH=on`) | `agent.New(...)` call |
| `cmd/onemindd/main.go` | on nodes with a join bundle: `sup := &leaf.Supervisor{ConfPath: "/etc/onemind/nats/leaf.conf", Config: cfg, Reload: leaf.SystemdReload("onemind-nats-leaf.service"), Log: log}; go sup.Run(ctx)` and `agent.Config{…, LeafReport: sup.Last}`; `cfg` comes from the bundle (hub URL `tls://<hub_mesh_ip>:7422`, CA, node cert, `leaf.WriteNkeyFile` beside `leaf.conf`) | after `agent.New(...)` |
| `internal/agent/agent.go` | `Config` gains `MeshReport func() *mesh.Heartbeat` and `LeafReport func() leaf.Health`; `collect` sets `c.st.Fabric` when either is set (same pattern as `UpdateReport`) | `Config`, `collect` |
| `internal/heartbeat/heartbeat.go` | optional `Fabric *Fabric` (JSON `fabric,omitempty`) with `Mesh *mesh.Heartbeat` and `Leaf *leaf.Health` (§15) | heartbeat struct |
| `cmd/onemind/main.go` | `case args[0] == "mesh": err = meshCmd(args[1:], stdout)` (in `cmd/onemind/mesh.go`) and one usage line `onemind mesh status [--json] [--leaf-monitor ADDR]` | `run` switch, `usage` |
| `deploy/pins.env` | `HEADSCALE_VERSION`, `HEADSCALE_SHA256_{amd64,arm64}`, `TAILSCALE_VERSION`, `TAILSCALE_SHA256_{amd64,arm64}` (values in §4.1) | new block |
| `deploy/install.sh` | `apt_setup` pkgs += `avahi-daemon libnss-mdns sqlite3 nftables` | `apt_setup` |
| `deploy/install.sh` | hub main: `mesh_install` before `k3s_server`; node main: `mesh_install` before `k3s_agent` | `# Main` |
| `deploy/install.sh` | `k3s_server` config += `node-ip`, `advertise-address`, `tls-san`, `flannel-backend: wireguard-native`, `flannel-iface: tailscale0` | `k3s_server` `new_cfg` |
| `deploy/install.sh` | `k3s_agent`: `K3S_URL=https://<hub mesh ip>:6443`, `node-ip`, `flannel-iface` | `k3s_agent` |
| `deploy/install.sh` | `nats.conf`: `listen 127.0.0.1:4222`, leafnodes on the mesh IP with TLS, `include users.conf` (replaces "no auth/TLS") | `nats_install` heredoc |
| `deploy/install.sh` | `onemindd_install`: node `ONEMIND_NATS_URL=nats://127.0.0.1:4222` (local leaf) | `nats_url=` line |
| `deploy/install.sh` | banner: stop printing the k3s agent token; print the join QR instructions (FABRIC) | hub `printf` of `--token` |
| `deploy/systemd/` | new `onemind-headscale.service`, `onemind-edge.service`, `onemind-nats-leaf.service`, `k3s.service.d/onemind-mesh.conf` | new files |
| `os/versions.lock.yaml` | `headscale`, `tailscale`, `derper` entries with sha256 | new keys |
| `os/rootfs` package list | `avahi-daemon`, `libnss-mdns`, `sqlite3` | base layer |
| `dashboard/src/pages/Home.tsx` | app link `http://host:port` → `app.urls.lan` (or `.mesh` off-LAN) | ~line 83 |
| `dashboard/src/App.tsx` (router) | add the Network route | routes list |
| `sdk/contracts/poc-v0.md` | §12.16 from §15 | new section |
| `sdk/schema/onemind.app.schema.json` | `spec.web.access: owner|adults|signed_in` (default adults); later `spec.network.mesh` | `spec.web` |
| `docs/security/HARDENING-BACKLOG.md` | H-04: default egress also denies `100.64.0.0/10` and the mesh ULA; nftables drops pod → `tailscale0` | H-04 change text |

## 19. Open items

1. **Coordinator choice** (founder): Headscale (default here) vs NetBird vs Nebula vs plain WireGuard; row in DECISIONS-NEEDED. The `Coordinator` interface (NET-1) keeps a later switch contained to one module plus re-enrollment.
2. **Z-34** stays open: `hosted` mode exists as an opt-in, not a default.
3. **Phones without an owner domain:** NT-12 decides whether box-CA trust is enough for the official apps. If not, `relay` mode needs a domain name (any registrar) or the owner keeps phones LAN-only.
4. **Double encryption on Pis** (§8): fallback needs a founder call only if NT-9 fails.
5. **Naming alignment:** FABRIC/CONTRACT-12-DRAFT use `/v1/fabric/join` + tickets, the leap's FABRIC spec uses `/v1/fabric/join-requests` + join codes; the edge's `join.onemind.internal` allowlist follows whichever C12-B adopts (DECISIONS-NEEDED §2).
6. **CA location:** CORE-SEC §3.1 puts the CA in the gateway (`/data/onemind/tls/`), FABRIC §3 in the custodian. This design follows FABRIC (custodian), because the edge and NATS certificates must not depend on the network-facing gateway. Settle in CORE-SEC-1.
