<!-- SPDX-License-Identifier: Apache-2.0 -->
# Competitors: home and self-hosted (FB-11, group 4)

**Date:** 2026-11-12. Builds on mission 01's Tier A teardowns (`../../02-competitors/`) and the umbrelOS 2 study (`docs/umbrel2/`).

> **Explain it like I'm the founder.** None of the home operating systems has a real "many machines, many sites" story. Home Assistant is one instance; Umbrel is one box; Olares can add worker nodes to one cluster. For remote access they all lean on a VPN (often Tailscale) or a paid relay. So OneMind's fabric is new ground for the home market, built from patterns that industrial and robotics tools already prove.

| Product | Join model | Identity | Transport | Offline | Update model | AI access | Licence | Multi-site? | Pricing | Fit |
|---|---|---|---|---|---|---|---|---|---|---|
| **Home Assistant** | single instance; devices through integrations | HA users | local; remote via Home Assistant Cloud ("without opening any ports") or a VPN such as Tailscale/ZeroTier [C-FB11-014] | fully local | HAOS RAUC (mission 01) | HA assist / MCP integrations (not re-checked) | Apache-2.0 | **No** native multi-instance (page silent) [C-FB11-014] | Cloud subscription (not re-checked) | **High** as an app (W8-R3), not as a fabric model |
| **umbrelOS** | single box | box account | LAN + Tailscale app | local | OTA (mission 01) | MCP (`docs/umbrel2/mcp-agents.md`) | PolyForm Noncommercial (mission 01) | **No** (`docs/umbrel2/machines.md` §placement: "We build it") | free OS; hardware sold | Patterns only |
| **Olares** | `olares-cli node add/join`, k3s workers with external etcd (FABRIC §4.2; C-STEEL-etcd-every-box-017) | Olares accounts | cluster network | local | 11-stage upgrade (C-TD-olares-010) | built-in agents | AGPL-3.0 [C-FB11-003] | **One cluster, several nodes**; no multi-site | free OS; Olares One hardware | Patterns only (licence) |
| **Tailscale as a "fabric"** | device login or auth key; coordination server hosted by Tailscale | node keys | WireGuard + DERP | peers keep working while connected | client auto-update | — | client BSD-3-Clause (C-LIC-041) | **Yes**, at the network layer only | hosted plans (not re-checked) | Underlay only; OneMind self-hosts the coordinator (Headscale) by default (F-32) |
| **Headscale** | pre-auth keys (lab: single-use, tagged) | node keys | as Tailscale | as Tailscale | — | — | BSD-3-Clause | scope "a single Tailscale network … personal use, or a small open-source organisation" [C-FB3-006] | free | Default per site (lab PASS) |
