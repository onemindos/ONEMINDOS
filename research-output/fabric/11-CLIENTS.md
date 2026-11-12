<!-- SPDX-License-Identifier: Apache-2.0 -->
# 11 · Clients (FB-10): phones, desktops and headsets as windows into the fabric

**Date:** 2026-11-12 · **Workstream:** FB-10 (Tier B) · **Status:** builds on research 12 and 15 and the merged mobile shell (PR #21) without changing them; adds the multi-site rules.
**Serves requirements:** UX-1, UX-4, UX-5, UX-6, UX-7, UX-8, UX-9, U-1, U-5, N-1

> **Explain it like I'm the founder.** Your phone, laptop and headset are **remotes**, not parts of the machine. They show the same app everywhere, talk only to a site's gateway (never to the bus or to a robot directly), and are where approvals happen. When you have many sites, the phone shows a list of sites first, then machines; anything not fresh shows its age. A phone can *also* be a field device in the TAK sense (sharing its position and photos), but that goes through the TAK server or the OneMind app, never by turning the phone into a server.

## 1. Rules

| # | Rule | Source |
|---|---|---|
| C1 | One web app, wrapped per platform (Capacitor/Expo on phones, Tauri on desktop), browser panel in XR | REC-W11-01, REC-W11-09, REC-W11-14; mobile shell PR #21; desktop client PR #33 (merged) |
| C2 | Clients never connect to NATS; they use the gateway API and its event stream | contract §12.9 ("Clients … never connect to NATS; they use `/v1/events`") |
| C3 | Remote reach uses the official Tailscale apps against the owner's own Headscale; the OneMind app ships no VPN | NETWORKING N-R9; REC-W11-12 |
| C4 | A phone is not a k3s node; Android's VM feature is a developer convenience | REC-W14-09 |
| C5 | Phone as field device: ATAK through TAK Server (CoT bridged into NATS), or the OneMind app's captures (photos, notes, position) as append-only records | research 09 W8-R8; context/02 §10 (captures append-only) |
| C6 | Approvals are delivered to the *owner of the target site* (`07-…` A5), by Web Push / UnifiedPush / APNs ping-then-fetch | REC-W11-07, REC-W11-08, D-005 |
| C7 | Nothing stale is shown as live; every value carries `observed_at` / `received_at` | contract §3, §12.10; UMB-DESK-12 |

## 2. One view of thousands of nodes

| Screen | At 1–10 nodes | At 1,000+ nodes across sites |
|---|---|---|
| Home | node counts by state | **site** counts by worst state; a line per site that is not healthy, with age |
| Nodes | one card per node (FABRIC §6.3) | Sites list → site → nodes; filters by role, class, ring, update state; never more than one page of cards without a filter |
| Map | — | sites with a position (owner-set), robots/vehicles with live position when fresh, greyed when stale |
| Infrastructure graph (UX-7) | node → apps | site → hub → nodes → adapters → devices, built from the registry (`06-…`) |
| Approvals | all pending | grouped by site; only sites the person may approve for |
| Releases | — | rings and their progress per release (`09-…`) |

The fleet hub serves the multi-site views from site **summaries** (counts, worst state, alerts), not from every heartbeat; drilling into a site asks that site's gateway (`04-…` §3). This keeps the fleet hub small and keeps each site's detail at the site (M-2).

## 3. Push alert routing per owner and role

| Alert | Who gets it by default |
|---|---|
| `node.offline`, `node.degraded`, release halted | owners and operators of that site |
| approval needed (`sensitive`, `destructive`, `actuate`) | principals with `can_approve` on that site; `actuate` only to owners |
| fleet-wide (a release halted in ring 0 everywhere) | fleet operators |
| child / guest roles | never infrastructure alerts (U-2, U-3) |

## 4. What competitors do (constraint-matched)

| Product | Clients | Multi-site | Constraint fit | Take |
|---|---|---|---|---|
| umbrelOS 2 | web + native apps (`docs/umbrel2/clients.md`) | single box | High (home) | Parity baseline (UMB epics) |
| Home Assistant | companion apps; remote via Cloud or VPN [C-FB11-014] | one instance per app connection | High (home) | Same remote pattern |
| Foxglove | web/desktop; standalone licence mode for air-gapped machines (C-TD-tier-c-robotics-030) | Edge Sites, up to 1,000 per org (C-TD-tier-c-robotics-023) | Medium | Site grouping |
| Formant | Chrome-only web app (C-TD-tier-c-robotics-014) | cloud fleet | Low | — |

## 5. Open items

- Proposed **F-22**: "the multi-site views work from summaries alone; a site that cannot be reached is shown with its last summary and age".
- Desktop client (PR #33) and photo backup (PR #34) are merged; the multi-site Sites list is new work (build path P2).

## Glossary

| Term | Meaning |
|---|---|
| EUD | End-user device in TAK: a phone or tablet running ATAK/iTAK |
| CoT | Cursor on Target: TAK's message format for positions and events |
| Summary | A small record per site (counts, worst state, alerts) that the fleet hub keeps instead of every detail |
