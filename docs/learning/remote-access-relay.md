<!-- SPDX-License-Identifier: Apache-2.0 -->
# Remote access with your own relay (founder-requested learning entry, 2026-11-21)

**Decision this builds on (Zeus, 2026-11-21).** Remote access is our own mesh and our own relay, with no dependence on outside services. OneMind is local first and must work off grid. Design: [NETWORKING.md](../architecture/NETWORKING.md) §4.3 and §4.4. Issue: #234.

## Words first
- **Mesh:** a private encrypted network between your machines and phones (WireGuard tunnels, set up by Headscale on the hub, which only hands out keys and rules and never sees traffic).
- **Relay:** a OneMind machine of yours that has a public internet address. It exists so a phone away from home can find the hub, which sits behind your home router.
- **SNI:** the server name a browser or app puts, unencrypted, at the start of an HTTPS connection ("I want control.example.org"). The relay reads only this.
- **Default deny:** anything not explicitly allowed is refused.

## How a connection is made
**At home.** The phone or laptop is on the same network as the hub. The join bundle lists the hub's home address first, so the connection never leaves the house. This works with the internet cable pulled out.

**Away.** The same bundle lists your relay's address second. The device opens an HTTPS connection to the relay asking for the hub's control name. The relay looks at that name, opens a connection to the hub, and copies bytes both ways. The device and the hub then do their TLS handshake with each other through it. Once the mesh is up, devices try a direct path first and use the relay as the road only when they cannot.

**Off grid.** With no internet and no relay, the local network and the LAN mesh keep working: names like `onemind.local` come from the box itself, and nothing needs a company's server. Without a relay the box says so in plain words (`GET /v1/mesh` returns `relay.state = "none"` and an explanation) instead of failing. If the relay is a second box on the same off-grid network, it works the same way.

## What the relay can and cannot see
| Can see | Cannot see |
|---|---|
| That a connection arrived, its size and timing | Anything inside it: pages, passwords, files, app names |
| The server name asked for (it is sent in the clear) | The hub's TLS key: the relay has none for any hub name |
| The sender's IP address (the relay's own log leaves addresses out) | Which user or app the traffic belongs to |

The relay can refuse service or slow it down. It cannot read or change traffic, and it cannot serve a page: its config has only exact names, no wildcard and no catch-all, so a dashboard on the relay is impossible by construction. Names not on its list are closed (tested).

## When a network blocks UDP
Mesh tunnels normally use UDP. Hotel and office networks often block it. The relay speaks HTTPS on port 443 (TCP), which nearly every network allows, so the connection to the hub still works. Tor is not a dependency: it stays an optional Market app (NET-TOR-01, #284) for people who want it.

## What exists now, and what is left
**Built in this first slice:**
- `onemindd relay init|serve|status` (`internal/relay`): the relay role. `init` makes the config and prints the pairing text once, keeping only a hash of the one-time code; `serve` is the SNI router; `status` says plainly when the machine is not a relay.
- Gateway: `ONEMIND_MESH_RELAY_ADDR` (a public IP, validated), the relay shown in `GET /v1/mesh`, and the relay address advertised after the LAN address in the join bundle (`control_addrs`).
- Tests: Go (traffic through the relay verifies the hub's own certificate, unknown names and non-TLS are closed, config refuses wildcards) and Python (no-relay message, bundle order, address validation).

**Follow-ups, in order:**
1. `mesh.relay.add`: the owner pastes the pairing text on the dashboard (Network, Relay), the approved action pins the relay's setup certificate, sends the hub's WireGuard public key, and stores the relay address (today it is set in the environment). Critical action, owner only.
2. The link: the hub dials out to the relay (`PersistentKeepalive`), so no router port is ever opened; the relay's upstream becomes the hub across that link.
3. `derper` on the relay, headscale `derpmap.yaml` region 900, and `-verify-client-url-fail-open=false` (NETWORKING R6).
4. Public control name with ACME through the passthrough, and the CAA `accounturi` record so the relay cannot get a certificate for the hub's name.
5. Image: a `onemind-relay.service` unit and the cloud image role switch; phone join QR carrying the relay.
6. Dashboard card for Network, Relay.

## Test plan for hub, relay and client (QEMU or compose)
Extends `test/net/two_vm.py` (its criteria file is preregistered and is not changed here; new criteria go in a new file with a new hash):
1. Three guests: hub, relay (the same image with `onemindd relay init`), client on a third network that cannot reach the hub directly.
2. Client reaches the hub's control name only through the relay: the TLS certificate it sees is the hub's box CA certificate, never one made by the relay.
3. Relay with the hub powered off: the client gets a clean failure; the relay stays up.
4. A connection asking for any other name, no name, or plain HTTP is closed; port scan of the relay shows only 443.
5. Home path: on the hub's LAN with the relay stopped, enrollment still works.
6. Block UDP between client and hub: the mesh still comes up through the relay over TCP 443.
First run is CI's `image` workflow; they cannot run on the build worker.
