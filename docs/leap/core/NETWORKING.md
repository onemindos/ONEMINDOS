<!-- SPDX-License-Identifier: Apache-2.0 -->
# Networking and mesh (CORE-NET)

**Date:** 2026-11-12 · **Status:** proposal · **Founder request:** internal networking and the mesh are core, needed now to replace the founder's cluster · **Deeper doc (the design, tests, budget and integration list):** [`docs/architecture/NETWORKING.md`](../../architecture/NETWORKING.md) · **Serves:** FABRIC (join, NATS leaf), SEC-1 (per-box CA), SEC-4 (NATS auth); hardening H-04, H-05, H-06, H-17, H-23, H-24, H-29; research 09 P0-6, research 12 REC-W11-11/12, mission 02 FB-3.

> **Explain it like I am the founder**
> Every OneMind machine and every phone you add joins one private, encrypted network that your box runs itself (Headscale, open source). Machines connect directly when they can and through your own relay when they cannot, so a Pi in the field and a VM in the cloud reach home without opening router ports.
> At home, `onemind.local` and `<app>.onemind.local` open the dashboard and apps over HTTPS, behind your sign-in. Away, the Tailscale app on your phone talks to your box, not to Tailscale's cloud.
> Adding a machine, a phone or a relay is an approval, like everything else. Removing one is instant.

## 1. What changes

| Today (v0) | After CORE-NET |
|---|---|
| Nodes publish straight to the hub's NATS, no auth or TLS, LAN only | Each node runs a NATS leaf → hub over the mesh, TLS with the box CA, per-node nkey, own subjects only |
| k3s on flannel VXLAN, unencrypted | k3s on mesh addresses, flannel `wireguard-native` on `tailscale0` |
| No reach across sites or NAT | WireGuard mesh coordinated by Headscale on the hub; embedded DERP; optional owner relay VM (hub dials out) |
| Phone remote access: backlog item only | Official Tailscale apps pointed at the box's Headscale, enrolled by an approved `mesh.device.add` |
| Apps at `http://host:port` | `https://<app>.onemind.local` through the hub edge with forward-auth; per-box CA with name constraints |

## 2. Decisions this spec asks for

- **Coordinator:** Headscale (default) vs NetBird vs Nebula vs plain WireGuard. Row F-32 in [DECISIONS-NEEDED.md](../DECISIONS-NEEDED.md).
- Z-34 (Tailscale hosted vs Headscale) stays open; `hosted` is an opt-in reach mode, never the default.

## 3. Epics

CORE-NET-1 … CORE-NET-15 in [BACKLOG.md](../BACKLOG.md) (S2, next to CORE-FABRIC). Part 1 (NET-1…9) adds new modules only and can start in S1 beside CORE-SEC-1; Part 2 (NET-10…14) wires the installer, gateway, `onemindd`, dashboard and contract §12.16; NET-15 (public exposure) is parked. The exact one-line hotspot changes are listed in the architecture doc §18.

## 4. Acceptance in one line each

A leaf reaches only hub 443 and 7422; an owner's phone reaches only hub 443; node A cannot publish as node B; pod traffic is WireGuard on the wire; a node at a NAT'd site joins with no home port open; the LAN keeps working with the internet cut; nothing talks to Tailscale Inc in `lan` mode (tests NT-1…NT-17).
