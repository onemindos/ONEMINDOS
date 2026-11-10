# OneMind OS: Foundation and Architecture (v0.1)

**Date:** 2026-11-10 · **Status:** Recommended direction, pending founder decisions (§10) and a 2-week foundation bake-off (§9).
**Built from:** [REQUIREMENTS.md](REQUIREMENTS.md) (IDs in brackets) and the six research reports in [`research/`](../research/). Facts carry sources in those reports. This document gives the reasoning and the decisions.

> **⚠ Superseded in part by [ADR-001](ADR-001-foundation.md) (2026-11-10):** the base is now **Debian 13** (Jetson flavor on NVIDIA L4T/Ubuntu 24.04), the update tool is **Rugix A/B** (Kairos dropped as lead because its docs say Pi 5 is unsupported), and k3s plus RKE2 serves the hardened tier. Where this document conflicts with ADR-001, ADR-001 wins.

---

## 1. The answer in one paragraph

OneMind OS should be **Kubernetes-native (k3s on every node) on an immutable, image-based Ubuntu 24.04 LTS host**, structured in the same layers as Olares, plus two layers nobody else has: a **Node layer** (everything is a node: QR join, capability detection, mesh) and a **Physical layer** (robots, drones, IoT, TAK, XR). On top sits a **capability layer**: one app manifest (`onemind.app.yaml`) automatically wires every installed app into the dashboard, alert center, permissions, and the AI surfaces (MCP, REST, CLI, Agent Skills, and MHS later). **Don't fork Umbrel or Olares.** Copy their patterns and reuse permissively licensed components.

## 2. Why this foundation (evidence summary)

| Question | Decision | Evidence (see research files) |
|---|---|---|
| Docker or Kubernetes? [N-9] | **k3s everywhere** | k3s runs from a Pi (2 GB server / 512 MB agent) up to clusters. Olares proves k3s works as a consumer product. NVIDIA's whole stack (GPU Operator with K3s support, DRA, KAI, Dynamo) is Kubernetes-native. It is your existing cluster pattern (Argo/NATS). Umbrel and CasaOS are single-node Docker and cannot do multi-node, clusters or GPU fleets. |
| Which host OS? [R-1, R-3, N-2] | **Ubuntu 24.04 LTS base, image-based A/B updates** (build tool chosen in bake-off) | JetPack 7.2 (Jetson Orin/Thor) **is Ubuntu 24.04**. GPU Operator supports Ubuntu. One base distro then spans x86, GPU boxes and Jetson. Umbrel uses Debian 13 with Rugix A/B updates; HAOS uses Buildroot with RAUC. All successful appliances use atomic A/B updates. |
| Image builder | **Kairos is the lead candidate.** Fallbacks: Debian/Ubuntu + Rugix, or Talos for the cluster tier | Kairos (CNCF Sandbox, **Apache-2.0 verified**, v4.4.0 on 2026-10-26) is the only option verified across x86, arm64 and Jetson Orin NX/AGX Orin/Thor, with OCI-image A/B upgrades and a built-in k3s provider. Gaps: Pi 5 and Orin Nano aren't in its docs, and user-timed updates are unverified. That's why there's a bake-off. |
| Fedora CoreOS / bootc? | **Not now** | FCOS is mid-transition to bootc (unification proposal 2026-08-26, no decisions as of October), and Fedora IoT lists only Pi 3/4 officially. Revisit in 2027. |
| Fork Umbrel? | **No** | umbrelOS is **PolyForm Noncommercial**, and its FAQ says you can't sell hardware, hosting or support with it. umbrel-apps has no license file. |
| Fork Olares? | **No. Learn from it and reuse permissive parts.** | Olares is **AGPL-3.0** (since 2025-08-30), with a legacy non-commercial file and "other" licenses in sub-repos. Its multi-node support is thin, its identity is tied to olares.com, and it has no robotics, TAK or XR. |
| Desktop edition [UX-10] | **Optional Omarchy (Arch + Hyprland) edition, later** | Omarchy is MIT-licensed with a good plugin and hooks model, but it is a rolling release with no LTS or atomic updates. It's fine as a desktop client, but not a box base. |

### Why one developer isn't limited by this [M-6]
- **Guard rails:** k3s, an immutable image, one manifest format and GitOps. The box can't drift, and every app follows the same path.
- **No ceiling:** the app layer is plain Helm or Kubernetes, so it runs unchanged on a $300 box, your DigitalOcean cluster, Talos or RKE2 in an enterprise, or a Jetson. Only the OS image recipe differs per tier.

## 3. Layer model

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │ 7 CLIENTS     Web (PWA) · iOS · Android · Mac/Win/Linux · WebXR/     │
 │               Android XR · Omarchy desktop · external AI agents      │
 ├─────────────────────────────────────────────────────────────────────┤
 │ 6 APPS        Built-in (Dashboard, Files, Vault, Market, Settings,   │
 │               Control Hub, Alerts, Family, Nodes) · OneMind apps     │
 │               (finance, wellness, robotics, PM, mesh, OSINT…)        │
 │               · Community/Market apps (Helm + manifest)              │
 ├─────────────────────────────────────────────────────────────────────┤
 │ 5 CAPABILITY  onemind.app.yaml → registry → projections:             │
 │   LAYER       dashboard tiles · health/alerts · MCP · REST · CLI ·   │
 │               Agent Skills · (MHS later) — ONE gateway enforces      │
 │               identity, household role, agent grant, approval, audit │
 ├─────────────────────────────────────────────────────────────────────┤
 │ 4 PLATFORM    Identity (Authentik / Kanidm for box) · Secrets        │
 │               (OpenBao/Infisical) · NATS JetStream (event bus) ·     │
 │               Postgres · object storage · Prometheus/Alertmanager ·  │
 │               ingress + TLS · Headscale/Tailscale · backups          │
 ├─────────────────────────────────────────────────────────────────────┤
 │ 3 NODE LAYER  QR/token join · NodeCapabilities (NFD + GPU feature    │
 │   (new)       discovery + sensors/radios) · NATS leaf + JetStream    │
 │               domain per node · offline autonomy · mirror/sync       │
 ├─────────────────────────────────────────────────────────────────────┤
 │ 2 RUNTIME     k3s · containerd · NVIDIA toolkit/GPU Operator (x86) · │
 │               device plugin + CDI (Jetson) · HAMi GPU sharing ·      │
 │               KubeVirt/libvirt VMs · gVisor/Kata agent sandboxes     │
 ├─────────────────────────────────────────────────────────────────────┤
 │ 1 HOST OS     Immutable Ubuntu 24.04 image, A/B updates, per-tier    │
 │               images: Lite · Pro (+NVIDIA) · Edge(Pi) · Jetson ·     │
 │               Cluster                                                │
 └─────────────────────────────────────────────────────────────────────┘
   PHYSICAL (new): ROS 2 (containers) · MAVLink/PX4 · Matter/Zigbee/Z-Wave/
   ESPHome via HA · LoRaWAN/Meshtastic/Reticulum · TAK/CoT · digital twin
   → all bridged into the NATS subject grammar
```

Layers 1–2 and 4 mirror Olares's Infrastructure and Platform layers. Layer 5 is OneMind's version of Olares's Framework layer, made AI-native. Layers 3 and Physical are the moat [M-7, N-1, N-7].

## 4. The capability layer: "install an app, and AI can use it" [AI-1..AI-4, UX-1..UX-4, A-1]

One manifest per app (full draft in `research/platform/ai-native-protocols-and-ux.md` §10) declares:
- entrances (URLs and auth level)
- storage and folder access
- identity and household groups
- dashboard tiles and widgets
- health checks and alerts
- **capabilities**: each one's id, schema, read/write/destructive effect, scope, audience (human/agent), and exposure (MCP tool, REST route, CLI command)
- parental-policy hooks
- cloud integrations, with a per-provider `aiPolicy`

When an app is installed, controllers turn the manifest into everything above. **A single capability gateway** authenticates every call (OIDC, and for MCP, OAuth 2.1 with RFC 9728/8707), then authorizes it against the user's household role ∩ the agent's grant ∩ policy. Destructive actions require human approval [AI-5]. Every call is audited.

What this adds beyond the competitors:
- **Umbrel 2.0:** owner-only MCP with coarse permission categories.
- **Olares:** a CLI plus Agent Skills.
- **OneMind:** agents act as a *specific user, with limited grants*. One registry projects to every protocol. Physical devices are capabilities too.

**MHS (Model Hardware Standard)** is real: Anthropic announced it as a research preview on 2026-08-27, for agents operating physical hardware. It's reachable via MCP, CLI or code, and Raspberry Pi is among the testers. Its spec isn't public yet and open-sourcing is planned. The registry design means MHS becomes one more projection for device capabilities [AI-2, N-10]. Apply for preview access.

## 5. Node layer: "everything is a node" [N-1..N-6, UX-6, UX-7]

1. **Join:** a QR code containing a short-lived single-use token and a pinned cluster CA hash (the k3s secure-token pattern, with a Matter-style passcode for small devices). Scanning issues one identity per device: NATS credentials, a mesh VPN key, and a k3s join or a lightweight agent-only mode for microcontrollers.
2. **Capabilities:** every node publishes a `NodeCapabilities` record covering CPU/RAM, GPU/VRAM, unified memory, RT cores, JetPack/driver versions, accelerators, radios, buses and sensors. Sources are Node Feature Discovery and NVIDIA GPU feature discovery (now inside k8s-device-plugin). The Market compares app requirements against it: "Your box can run this ✅ / needs 16 GB VRAM ❌ / try the Pro tier" [N-3, A-8].
3. **Offline autonomy:** each node runs a NATS leaf with its own JetStream domain that sources and mirrors to the hub, so robots, greenhouses and field nodes keep working when the link drops. *Outage buffering must be tested; the docs don't guarantee it.*
4. **Many machines, one UI:** the Nodes app shows every node, its health, capabilities and apps. Mirroring is NATS mirroring plus Velero/restic snapshot replication. The infrastructure map is generated from node and network discovery [UX-6, UX-7].

## 6. Physical layer [M-7, N-7, N-8, P-8]

- **ROS 2 runs in containers decoupled from the host OS.** ROS 2 Lyrical is Tier 1 on Ubuntu 26.04 while JetPack is 24.04; Jazzy is supported until 2029 on 24.04. Keep DDS traffic on the robot. PX4's uXRCE-DDS is unauthenticated, so it should only be exposed through gateways into NATS.
- **Gateways are plugins, not core:** MAVLink/PX4, Open-RMF, Matter/Zigbee/Z-Wave/ESPHome (Home Assistant as an app), ChirpStack (LoRaWAN), Meshtastic, Reticulum, Zenoh and TAK/CoT.
- **Digital twin / geo / time-series store:** one source of truth that feeds TAK, dashboards and XR (WebXR over HTTPS with glTF/USD) [UX-9].
- **Simulation tier:** Isaac Sim needs an RTX card with RT cores, minimum RTX 4080 16 GB and 32 GB RAM. A100/H100 and Jetson can't host it; DGX Spark is the only aarch64 host. So simulation is a Pro/Omni capability, enforced by NodeCapabilities.
- **Safety contract (proposal):** anything that moves or controls heat or water gets a device-local safe state, signed commands, command TTLs, and no blind replay after reconnect.
- **NVIDIA [N-8]:** the GPU Operator covers x86 tiers. Jetson isn't supported by the GPU Operator (issue #1453 closed as not planned), so Jetson uses the device plugin with CDI. Apply to NVIDIA Inception.

## 7. Editions and hardware tiers [P-5, P-6, H-1..H-4]

| Edition | Superpower | Reference hardware (sourced in research) | Software profile |
|---|---|---|---|
| **Edge** | Sensor/greenhouse/mesh gateway | Raspberry Pi 5 16GB ($305 board) | k3s agent or single-node, HA, NATS leaf, LoRa/Meshtastic |
| **Lite** | Home cloud | Intel N150/N300 mini PC (the class Umbrel Home/Pro use) | Full OS, no GPU, small models |
| **Pro** | Local AI | RTX box (Olares One class: RTX 5090M 24GB, 96GB; $4,999 on store, prices conflict), or DGX Spark ($4,699, per a secondary source) | + GPU Operator, HAMi sharing, Ollama/vLLM |
| **Robotics** | On-robot brain | Jetson Orin Nano Super ($399), AGX Orin ($3,499), Thor ($5,499) (post-hike prices from a secondary source) | Jetson image, ROS 2 containers, Isaac ROS |
| **Omni** | Simulation/training/multi-user | RTX PRO 6000 workstation, DGX Station | Isaac Sim, Cosmos, fleet scheduling (KAI) |
| **Cluster/Enterprise** | Public safety, warehouses | Multi-node, Talos or Kairos | HA control plane, Dynamo/KAI, federation |

Competitor boxes for reference: Umbrel Home (Intel N150, 16GB) and Umbrel Pro (i3-N300, 4×NVMe up to 32TB, 2.5GbE); Olares One ($4,999); HA Green ($199); ZimaCube 2 ($799–2,499). The hardware path: **start with BYO hardware + certified mini PCs, then a OneMind-branded box, then an OEM program** (copying Olares's "Manufacture with" model).

## 8. Everything else, decided by pattern

| Area | Pattern to adopt | Notes |
|---|---|---|
| App format [A-1, A-2] | **Helm chart + `onemind.app.yaml`**, multi-arch images pinned by digest (Umbrel's rule) | Linter and CI like Olares's OAC linter. A Compose→Helm importer for CasaOS-style apps (check each app's license; umbrel-apps has none) |
| Market [A-1, A-3] | A Git-repo market (Umbrel and Olares both do this), quality tiers (Home Assistant's Bronze→Gold), verified publishers | Seed it with the Olares catalog categories you shared (chat, AI search, agents, coding, automation, design, research, media, local LLMs, observability…) |
| Dashboard [P-2, UX-2] | Build our own; study Homarr (**Apache-2.0**, can fork) | Homepage is GPL and Glance AGPL, so copy their ideas, not their code. Use annotation-driven widgets with a server-side API-key proxy. Backstage remains a developer portal only |
| Alerts [UX-4] | Alertmanager + an in-app alert center + ntfy/UnifiedPush | **Android can be fully self-hosted. iOS instant push requires APNs** (Apple's push service), which is the one unavoidable external hop. Ship our own iOS app with APNs |
| Identity / family [U-1..U-4] | Owner/Adult/Teen/Child/Guest roles; Jellyfin-style parental primitives (rating ceiling, tags, schedules, device approval) | Keep Authentik for clusters. Evaluate Kanidm for single boxes |
| Secrets & cloud apps [UX-3] | OpenBao or Infisical; OAuth broker (Nango pattern); `aiPolicy` per provider | **Strava's API policy (from June 2026, per secondary sources) bars using its data in AI applications.** Strava's own MCP is the likely compliant route, but needs legal review. Check every provider's terms |
| VMs [competitive parity] | KubeVirt (cluster) / libvirt (box) | Umbrel 2.0 "Machines" uses libvirt/KVM + noVNC |
| Updates [R-1] | A/B image + user-chosen windows + channels (stable/beta), signed | Umbrel uses signed Rugix A/B updates. Implement a user-controlled update policy ourselves |
| Agent sandboxes | Kubernetes Agent Sandbox + gVisor (Kata where KVM is available) | For untrusted agent code and browser automation |
| Website [W-1..W-9] | **Astro (site/blog) + Starlight (docs) + Shopify (store) + Circle.so (education) + Discourse (community) + Zoho Forms** | Competitors: Umbrel uses Next.js/Vercel, Olares uses VitePress + WordPress, Zima uses Nuxt; Umbrel, Olares and Zima all use Shopify |
| Offline knowledge | Bundle a N.O.M.A.D.-style pack (Kiwix, Kolibri, offline maps) as apps | Project N.O.M.A.D. is Apache-2.0 (43k stars), so it can be reused |

**The three repos you flagged:** REA (reverse-engineer software with agents, MIT, ~449k stars), Craft Anything (understand and rebuild software, Apache-2.0, Rust) and BLA (defends against REA). Use them as **research tools** to study competitor apps' behavior. Respect licenses: never lift code from PolyForm, AGPL or unlicensed sources into OneMind. Plan BLA-style protection for OneMind's own closed components if any. Details: `research/competitors/flagged-repos.md`.

## 9. Next 30 days

**Weeks 1–2: Foundation bake-off (decide with evidence)**
1. Build a OneMind image with **Kairos + Ubuntu 24.04 + k3s** on: one x86 mini PC, one RTX machine, one Pi 5 and one Jetson (if available).
2. Compare it against **Ubuntu 24.04 + Rugix A/B** (Umbrel-style), and **Talos** on x86 and Pi 5.
3. Measure: install time, idle RAM (Pi 5), GPU Operator on consumer RTX, Jetson device-plugin + CDI, A/B rollback, user-timed updates, and NATS leaf outage buffering.
4. Output: ADR-001 "Host OS and image pipeline".

**Weeks 3–4: Capability layer v0 on your existing cluster**
1. `onemind.app.yaml` schema v0 + linter.
2. A registration controller covering a dashboard tile, health and alert, and MCP tool generation.
3. The capability gateway, authenticated by Authentik, with agent grants and audit.
4. Dashboard v0 (apps, health, alerts, install from a Git market), installable as a phone PWA.
5. Demo: install an app → it appears on the dashboard → its alert fires → Hermes uses it via MCP with a scoped grant.

## 10. Decisions needed from Zeus — ✅ all six decided 2026-11-10, see [DECISIONS.md](DECISIONS.md) (D-001…D-006)

1. **The OneMind code license:** open core (e.g. Apache-2.0 core with commercial add-ons), AGPL, or source-available? This decides whether others can build boxes on it [H-4].
2. **First edition to ship:** Lite (largest market) or Pro (strongest AI story)?
3. **First OneMind internal app:** wellness, PM (ClickUp/Todoist replacement) or family?
4. **Hardware for the bake-off:** which machines do you have? (Pi 5? Jetson? RTX box? The Dell Latitude 5540 can serve as the x86 test.)
5. **iOS:** accept APNs for instant push (recommended) or offer polling only?
6. **Apply for MHS preview access and NVIDIA Inception now?**

## 11. Top risks

| Risk | Mitigation |
|---|---|
| Kubernetes complexity for a sole developer | k3s plus a baked image, and users never see Kubernetes; Olares proves this works |
| Kairos maturity (Sandbox; Pi 5 and Orin Nano gaps) | Bake-off with Rugix and Talos fallbacks; the app layer is OS-independent |
| Jetson outside the GPU Operator | Device plugin + CDI; a dedicated Jetson image |
| Hardware price volatility (Jetson and DGX up 18–101% in 2026) | Capabilities define "supported", not specific SKUs |
| Cloud API terms (Strava, health APIs) | `aiPolicy` enforced at the gateway; legal review |
| Scope explosion | Build the layers in order. Physical-layer gateways are plugins, shipped one at a time |

## 12. Traceability: requirements not covered by a section above

| IDs | Where they land |
|---|---|
| M-1, M-2, U-5 | Local-first by construction: everything runs on the owner's node. Remote access uses Headscale/Tailscale (§3 L4). The cloud is optional and comes later. |
| M-3, A-4, A-5, A-6 | Capability layer (§4) unifies self-hosted, cloud and OneMind apps. OneMind internal apps are first-party Market apps using the same manifest. The plugin system *is* the manifest + Market + quality tiers (§8), and community publishing opens once the linter and verified publishers exist. |
| M-4, P-4, P-7, P-9 | Editions table (§7) spans home lab to enterprise. Surfaces map to layers: Core (L4+L5), Dashboard and apps (L6), Desktop, Mobile and XR (L7), SDK (manifest + linter + generated clients), OS image (L1), Federation (multi-node and NATS cross-site, later). BYO install plus a turnkey box. Existing cluster workloads become Market apps. |
| M-5, M-8 | Strategy. Tracked through the decisions in §10. |
| P-1, P-3 | Dashboard at `onemind.local` (§8). Layer model mirrors Olares (§3). |
| A-7 | Bundles = an edition (§7) + a curated app set + a NodeCapabilities profile, sold or recommended through the Market and website. |
| AI-6 | Biometrics come later as a capability with a dedicated identity factor (Authentik/Kanidm WebAuthn/passkeys first). Not designed yet. |
| AI-7, AI-8, AI-9 | Embedded AI and IoT appear as Physical-layer capabilities (§6). GPU auto-detection via NodeCapabilities (§5). Hermes and NATS agent discovery carry forward as first-party agents behind the gateway. |
| UX-5, UX-8 | The phone PWA is first, then native iOS/Android/Mac/Windows clients (§3 L7). Every operation goes through the same gateway, so a phone can manage enterprise infrastructure. |
| R-2 | Support system: signed images, update channels, diagnostic bundles, a support desk on the website (§8), and Discourse plus Circle for community and education. |
| RS-1..RS-7 | Satisfied by `research/` (sourced reports, UNVERIFIED labels, REA/Craft/BLA reviewed, Olares built-ins reviewed in `research/competitors/olares.md` §2). If source code is needed, ask Zeus. |
