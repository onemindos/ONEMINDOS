# OneMind OS - Competitive Landscape (Part A)

Research date: 2026-11-10. Method: GitHub API (`gh`), vendor sites fetched/curled, vendor store JSON feeds. Rule: every claim is from a source opened in this session; anything else is marked **UNVERIFIED**. Star counts and release dates are live API values as of the research date. Numbers in `[S#]` refer to the Sources list at the bottom.

---

## 0. Headline findings

1. **The two direct competitors (Umbrel and Olares) have both already shipped AI-agent features in 2026.** umbrelOS 2.0 ships a built-in MCP server (per-agent tokens, revocable) and one-click OpenClaw/Hermes agents [S1][S2][S3]. Olares positions itself as "Open-Source Personal Cloud OS for Always-On Agents", built on Kubernetes, with Agent Skills and a CLI usable by AI agents [S4][S5]. "AI-agent-native access via MCP" is therefore **not** a unique differentiator by itself; it is table stakes within about a year.
2. **Home Assistant also ships an MCP server** (since 2025.2) [S6].
3. **Hardware pricing anchors (live store feeds):** Umbrel Home $499-$949, Umbrel Pro $699 (no SSD) to $1,899 (8TB) [S7]; Olares One $4,999 on its Shopify feed (the vendor page and press have shown $2,899-$3,999 at other times - see section 1.5) [S8][S9]; ZimaCube 2 $799-$2,499, ZimaBoard 2 $339-$399 board-only [S10]; Home Assistant Green $199 [S11]; ClawBox EUR 749 [S12].
4. **Licensing is a live battleground.** umbrelOS is PolyForm Noncommercial 1.0.0 (cannot be used to sell servers without a deal) [S3]. Olares is AGPL-3.0 [S4]. StartOS MIT [S13]. CasaOS Apache-2.0 [S14] but ZimaOS (its commercial successor) has no license file in its public repo and is distributed as test images [S15].
5. **Project N.O.M.A.D. is confirmed**: Crosstalk Solutions/project-nomad, Apache-2.0, TypeScript, 43,120 stars, v1.35.1 (2026-10-05), "offline-first knowledge and education server" [S16].
6. **Nobody in the set ships TAK / situational awareness, robotics (ROS), mesh networking, or XR as first-class OS features** (see section 4; absence claims are limited to what I searched and are marked as such).

---

## 1. Product profiles

### 1.1 Umbrel / umbrelOS (closest consumer competitor)

| Field | Finding |
|---|---|
| What | "A beautiful home server OS for self-hosting"; sold as Umbrel Home / Umbrel Pro hardware plus free OS download [S3] |
| Base OS / runtime | README says it is "a standalone operating system that installs directly onto your device. It can't be installed on top of an existing Linux distribution" [S3]. Third-party source (cnx-software headline) calls it Debian-based - **UNVERIFIED by first-party doc** [S17]. Apps are Docker Compose (each app dir holds `docker-compose.yml`, `umbrel-app.yml`, `hooks`) [S18] |
| App format / catalog | `umbrel-app.yml` manifest (manifestVersion 1.1, storage/folderAccess keys) + compose [S18]. README: "over 300 apps"; `getumbrel/umbrel-apps` repo has 406 top-level entries (includes non-app files) - treat as 300-400 [S3][S19] |
| Multi-user | Yes, new in 2.0: separate account, home screen, private home folder, share chosen apps/folders [S2] |
| Remote access | Umbrel for Mac supports remote over Tailscale [S3]. Other remote methods **not verified** |
| AI / MCP | 2.0: "connect any AI agent to the built-in MCP server to install apps, organize files, or troubleshoot", per-agent token, revocable [S2][S3]. Product page: one-click OpenClaw or Hermes agent, sandboxed; "Ask an AI agent to set it all up" (Beta); GPU auto-detect for Ollama [S20]. Product page itself does not use the word MCP [S20] |
| Other 2.0 features | Photos app + iPhone backup, Machines (run Windows/Ubuntu/Debian/Android VMs in browser), Storage Manager with FailSafe RAID, GPU acceleration (NVIDIA/AMD/Intel incl. eGPU), cloud import, Mac app [S3] |
| Hardware | **Umbrel Home**: Intel N150 quad-core, 16GB DDR5, 1/2/4TB NVMe, 3x USB 3.0, GbE, 6W TDP, 1-yr warranty [S21]. **Umbrel Pro**: Intel Core i3-N300 8-core, 16GB LPDDR5, 4x M.2 2280 NVMe (up to 32TB claimed), 64GB onboard for OS, 2.5GbE, 2x USB-C 3.2 Gen2, HDMI 2.1, WiFi 6, BT 5.2 [S20] |
| Price (store feed) | Home 512GB $499 / 1TB $599 / 2TB $699 / 4TB $949. Pro (no SSD) $699 / 2TB $999 / 4TB $1,299 / 8TB $1,899. "Umbrel Protect" add-on $39-$99 (per-SKU) [S7]. Home launched at $699 in 2023 per press [S22] |
| License | PolyForm Noncommercial 1.0.0; commercial use (e.g. selling plug-and-play servers with umbrelOS) requires contacting partner@umbrel.com [S3] |
| Activity | getumbrel/umbrel 12,547 stars, latest release 2.0.1 (2026-11-01), pushed 2026-11-03 [S23] |
| Business model | Hardware sales + Umbrel Protect add-on [S7]; OS free [S3] |
| Website tech | umbrel.com on **Next.js on Vercel** (`/_next/static`, `server: Vercel`); store.umbrel.com **Shopify** (`powered-by: Shopify`, products.json); community.umbrel.com **Discourse**; apps.umbrel.com Next.js/Vercel; analytics scripts for Plausible/Umami referenced [S24][S7] |
| Strengths | Best-in-class UX, big catalog, hardware + software loop, polished 2.0 feature set, MCP shipped |
| Weaknesses | Noncommercial license blocks white-labeling/OEM; single-node only (no k8s/multi-node found); no robotics/TAK/mesh features found |

### 1.2 Olares (closest "k8s + AI" competitor)

| Field | Finding |
|---|---|
| What | "Open-source personal cloud OS you operate in plain language, built to run AI agents and LLMs on hardware you own"; repo tagline "Open-Source Personal Cloud OS for Always-On Agents" [S4] |
| Base OS / runtime | Installs on Ubuntu 22.04-25.04 or Debian 12/13 via `curl -fsSL https://olares.sh \| bash -`; also ISO and Docker Compose install [S4]. **Kubernetes**: K3s default (or standard k8s), containerd, Calico, Envoy, etcd; platform includes PostgreSQL 16, KVRocks, NATS, JuiceFS, Argo Workflows, Vault/Infisical, Prometheus; LLDAP + Authelia for users/SSO [S25] |
| App format | "Application chart" + `OlaresManifest` (named in docs nav; format internals **not read**) [S26]. Market: Olares Market (count **UNVERIFIED**) |
| Multi-user | LLDAP user accounts, Authelia MFA/SSO, per-user isolation via `bfl` [S25]. Marketing: "individual users to small teams" [S4] |
| Remote access | Built-in private VPN, reverse proxy, public/private/internal entrances, LarePass client [S4][S27] |
| AI / MCP | 1.12.6: Agent Skills, Model Console for local LLMs; 1.12.7: Router, Lares (official AI assistant), broader local model catalog; supports OpenClaw agents with local LLMs; GPU pooling with time-slicing/memory-slicing [S4]. Architecture page lists "Agent & workflow orchestration", model serving and RAG as *in development*; MCP is **not mentioned** on that page [S25] |
| Hardware | **Olares One**: RTX 5090 Mobile (24GB GDDR7 per press), Core Ultra 9 275HX, 96GB DDR5-5600, 2TB PCIe 4.0 NVMe, 320x197x55mm (3.5L) [S27][S9] |
| Price | Shopify feed shows $4,999 (published 2026-04-01) [S8]. Press/vendor have shown $2,899 (early), $2,999 Kickstarter, $3,999 MSRP, VIP $2,799 [S9]. Vendor home page announces Black Friday from Nov 17 with $300 off per unit [S27]. **Current true price unclear** |
| License | AGPL-3.0 [S4] |
| Activity | beclab/Olares 5,356 stars, 1.12.7 (2026-09-24), pushed 2026-11-10 [S4] |
| Business model | Hardware (Olares One, Kickstarter raised "over $2.3 million" per vendor page via search snippet [S9]); free OS; Olares Space/LarePass ecosystem [S27] |
| Website tech | www.olares.com: Vue-style SPA (Vite module bundle, `data-v-*` scoped attributes) behind Cloudflare; docs: **VitePress v1.6.4**; blog: **WordPress** (generator meta 7.0.8, PHP); store: **Shopify** (one.olares.com products.json); community: **Discourse** [S28] |
| Strengths | Real k8s foundation (GPU scheduling, multi-node-capable stack components), agent story, AGPL (forkable), heavy-GPU flagship |
| Weaknesses | 8GB RAM / 150GB SSD minimum, installer assumes Ubuntu/Debian [S4]; flagship hardware expensive; price/messaging inconsistent; no TAK/robotics/mesh found |

### 1.3 CasaOS and ZimaOS (IceWhale)

| Field | Finding |
|---|---|
| What | CasaOS: "simple, easy-to-use, elegant open-source Personal Cloud system" [S14]. ZimaOS: "evolved from CasaOS", a Buildroot-based NAS OS with OTA updates, for Zima hardware and generic x86-64 UEFI [S15] |
| Base OS / runtime | CasaOS is an overlay on an existing Linux (third-party statement [S29], consistent with repo being Go services). ZimaOS: Buildroot, OTA + offline updates [S15]. Docker/Compose apps |
| App format / catalog | Compose file with an `x-casaos` extension block (architectures, main service, port_map, title, etc.) - verified in repo [S30]. Official `CasaOS-AppStore` has 182 entries; ZimaCube page claims "500+ Apps" [S30][S31] |
| Multi-user | **UNVERIFIED** (not checked) |
| Remote access | "Zima Client" for remote access (vendor page) [S31] |
| AI | ZimaOS 1.8.0 (2026-10-15) adds Gallery with natural-language photo search, memories, map browsing [S32]. No MCP found |
| Hardware / price (Shopify feed) | ZimaBoard 2 board-only $339 (832: 8GB/32GB eMMC) / $399 (1664: 16GB/64GB); ZimaBoard SE kits $159-$229; ZimaBlade $49-$160; ZimaCube (N100) $649-$679; ZimaCube 2 $799 (i3-1215U/8GB) / $1,299 (i5-1235U/16GB) / $2,499 (64GB + RTX Pro 2000); ZimaCube Pro $1,099-$1,999; accessories incl. OCuLink GPU dock $179.90 [S10] |
| License | CasaOS Apache-2.0 [S14]. ZimaOS repo: **no LICENSE file** and described as "just for releasing test images" [S15] |
| Activity | CasaOS 37,620 stars but **last release v0.4.15 on 2024-12-19** (pushed 2026-11-09) [S14]. ZimaOS repo 3,103 stars, 1.8.0 on 2026-10-15 [S15] |
| Business model | Hardware via Shopify store with affiliate program page (`/pages/affiliate-program`) [S10][S33] |
| Website tech | zimaspace.com **Nuxt** (`__NUXT__`, `/_nuxt/`) on Cloudflare; shop.zimaspace.com **Shopify** (`powered-by: Shopify`); community.zimaspace.com **Discourse** [S33][S10][S34] |
| Strengths | Cheapest x86 hardware entry points (ZimaBoard/Blade), large CasaOS user base, hardware breadth (GPU dock, firewall kits, PCIe cards) |
| Weaknesses | CasaOS appears stalled in releases; ZimaOS closed/unlicensed; no clear AI-agent story |

### 1.4 Home Assistant OS (HAOS)

| Field | Finding |
|---|---|
| What | OS to host Home Assistant and its Apps [S35] |
| Base OS / runtime | Buildroot-based (not a regular distro), Docker engine; Supervisor runs as a container and controls Core and Apps in separate containers; OTA + offline updates; SBCs and x86-64 UEFI [S35] |
| Terminology | Docs now say "apps" instead of older "add-ons" [S36] |
| App catalog | Official `home-assistant/addons` repo has 33 top-level entries (official set only; community stores not counted) [S37]. Total ecosystem count **UNVERIFIED** |
| Multi-user | Yes (HA user accounts; admin vs non-admin evident in MCP docs [S6]) - detail not further verified |
| Remote access | Home Assistant Cloud, being renamed **Home Assistant Link** on Dec 2; $6.50/mo or $65/yr; 31-day trial; includes remote access, offsite backups, Alexa/Google voice, STT/TTS [S38] |
| AI / MCP | MCP server integration since 2025.2: Device-control tool set (Assist tools on exposed entities) and an admin "Home Assistant" set (all entities, logs, history, any action); OAuth with Client ID Metadata Documents; cloud agents need internet-reachable instance; sampling/notifications unsupported [S6]. Release blog historically has AI posts (2024.6, 2025.8 titles) [S39] |
| Hardware | **Green** $199 / EUR 179: Rockchip RK3566 quad A55 1.8GHz, 4GB LPDDR4X, 32GB eMMC [S11]. **Voice Preview Edition**, **Connect ZBT-2** (Zigbee/Thread), **Connect ZWA-2** (Z-Wave) current; **Yellow and Blue discontinued** [S40] |
| License | Apache-2.0 (OS, Supervisor, Core) [S41] |
| Activity | core 92,125 stars, release 2026.11.1 (2026-11-09); OS 7,650 stars, release 18.5 (2026-11-06) [S41] |
| Business model | Nabu Casa (cloud subscription + hardware) funding Open Home Foundation project [S35][S38] |
| Website tech | home-assistant.io **Jekyll** (generator meta) on Cloudflare with Plausible; nabucasa.com **Astro** (generator Astro v7.4.7); developers.home-assistant.io Astro-signature; community on Discourse (403 to curl, Discourse inferred from page strings - moderate confidence) [S42] |
| Strengths | Unmatched IoT/device integration breadth, huge community, MCP shipped, mature add-on/app model |
| Weaknesses | Scope is home automation, not a general personal cloud; no multi-node |

### 1.5 Project N.O.M.A.D. (confirmed: Crosstalk Solutions)

| Field | Finding |
|---|---|
| What | "Offline-first knowledge and education server"; "Knowledge That Never Goes Offline" [S16] |
| Verification | Repo `Crosstalk-Solutions/project-nomad`; website projectnomad.us; Discord crosstalksolutions. (Creator identity as Chris/Crosstalk Solutions YouTube channel is **UNVERIFIED** beyond the org name matching.) |
| Runtime | Debian-based install script (Ubuntu 26.04 LTS recommended; 24.04 and Debian 12 supported); a management UI ("Command Center") + API that orchestrates Docker containers; also Docker Compose template [S16] |
| Bundled | Ollama + Qdrant RAG chat, Kiwix (offline Wikipedia), Kolibri (Khan Academy), ProtoMaps offline maps, CyberChef, FlatNotes, benchmark with public leaderboard, "Supply Depot" one-click app catalog + custom Docker containers [S16] |
| Requirements | ~5GB disk and <1GB RAM for NOMAD itself; AI assistant drives RAM [S16] |
| License / activity | Apache-2.0; 43,120 stars; v1.35.1 (2026-10-05); pushed 2026-11-09 [S16] |
| Website tech | projectnomad.us **Next.js on Vercel** [S24] |
| Business model | Not stated in README (**UNVERIFIED**) |
| Relevance | Closest to OneMind's education/offline/emergency angle; notably star-heavy for a niche. Shows demand for offline knowledge + local AI + maps. No TAK/mesh found in README |

### 1.6 Start9 / StartOS

| Field | Finding |
|---|---|
| What | StartOS is an open-source Linux distribution for a personal server; monorepo also holds StartWRT (router OS), StartTunnel, start-sdk, start-cli, registry, patch-db [S13] |
| Runtime | Rust core (`start-core`); services run in a container runtime; Angular UI [S13]. Package format via start-sdk (TypeScript) - details not read |
| Hardware / price | **Server One 6600H**: AMD Ryzen 5 6600H 6c/12t, Radeon iGPU, 16 or 32GB LPDDR5-6400, 2 or 4TB NVMe, GbE, 2x HDMI, 4.5x4.2x1.6 in; price not on page (configurator) [S43]. RISC-V router running StartWRT; Wi-Fi sold separately [S44]. Premium Support $200/yr (1 yr included with Server One and router) [S44] |
| AI | "Dux" AI support agent only [S44]. No MCP found |
| License / activity | MIT; 1,996 stars; start-sdk v4.1.0 (2026-11-10); StartOS 0.4.0 described as ground-up rewrite [S13][S44] |
| Business model | Hardware + Premium Support subscription [S44] |
| Website tech | start9.com is an **Angular** app (`ng-c*` attributes, Taiga UI `tui-*` classes) served by Express; community on **Discourse**; docs.start9.com static page [S45] |
| Strengths | Privacy/Tor/sovereignty positioning, security-first design, own router |
| Weaknesses | Small catalog (count **UNVERIFIED**), niche audience |

### 1.7 YunoHost, FreedomBox, Runtipi, Cosmos Cloud, Sandstorm

| Product | Base / runtime | Format & catalog | Multi-user / remote | License | Activity | Notes |
|---|---|---|---|---|---|---|
| **YunoHost** | Debian-based server administration OS ("operating system aiming to simplify... administration of a server") [S46] | App packages in `YunoHost/apps` repo (266 stars) [S46]; count **UNVERIFIED** | SSO/LDAP **UNVERIFIED** from fetched content | AGPL-3.0 | 2,991 stars, debian/12.1.41.2 (2026-09-03) | Site static, nginx; donation/volunteer model (**UNVERIFIED**) [S46] |
| **FreedomBox** | Debian (official Debian part), supported by FreedomBox Foundation [S47] | Services: file sharing, messaging, VPN server, proxy, wiki/blog, calendar/contacts, backups | Single-box focus | Listed "other" on GitHub (read-only mirror of Debian Salsa) [S47] | 210 stars (mirror), pushed 2026-11-03 | Hardware: Libre Crafts pre-built, Olimex Pioneer Edition [S47] |
| **Runtipi** | Any 64-bit Linux, one-command install; Docker per app [S48] | 271 entries in `runtipi-appstore/apps`; site says "nearly 300" [S48][S19] | Compose editing, backups | GPL-3.0 | 9,731 stars, v4.12.0 (2026-10-31) | Free; GitHub sponsors; site Next.js (static on GitHub Pages) [S48][S24] |
| **Cosmos Cloud** | Go; install by script or Docker [S49] | "250+" apps; SSO + MFA, built-in VPN (Constellation), reverse proxy, SmartShield anti-DDoS [S49] | Pro tier adds **cluster management across multiple servers** and RBAC; from $16/mo (16GB RAM, 20 users) [S49] | **Commons Clause** (source-available) per site; GitHub: NOASSERTION [S49] | 6,200 stars, v0.23.4 (2026-08-30) | Closest to "multi-node + SSO" among Docker-style panels; website Next.js [S24] |
| **Sandstorm** | Self-hostable web app package manager with per-document "grain" sandboxes [S50] | Apps like Wekan, Etherpad, Rocket.Chat [S50] | n/a | NOASSERTION (GitHub) | 7,082 stars, pushed 2026-11-01, **no GitHub releases** | sandstorm.io is now an archive page: "historical, from when Sandstorm was a startup"; project moved to sandstorm.org [S50] |

### 1.8 Storage-centric UX benchmarks

| Product | Facts |
|---|---|
| **TrueNAS (SCALE/Community)** | Apps moved from Kubernetes to **Docker** in 24.10 (Electric Eel) per release notes search result; 25.04 replaced libvirt with Incus for VMs [S51]. Apps catalog repo `truenas/apps`: trains community=487, stable=17, enterprise=4 entries (counted in repo), LGPL-3.0, "Docker-Compose based App catalog" [S52]. Middleware repo 2,617 stars [S52]. Website WordPress + HubSpot [S24] |
| **Unraid** | Perpetual licenses: Starter $49 (6 devices, 1 yr updates), Unleashed $109 (unlimited, 1 yr updates), Lifetime $249; 30-day free trial; includes Docker, VMs, Community Apps, Tailscale [S53]. Site generator SEOmatic (Craft CMS) on Cloudflare [S24] |
| **HexOS** | Built on TrueNAS (announced first-on-TrueNAS July 2024), curated one-click apps, VMs and Buddy Backups in open beta (Oct 2026), Ollama "AI Assistant" app, Nov 2026 notes mention "Local AI" and app collections; pricing not shown on page [S54]. Site **Nuxt** on Cloudflare/Caddy [S24] |
| **Synology DSM** | DSM 7.4 "available now" with "AI-powered productivity" wording; packages for Photos, Drive, Hyper Backup, VMM etc.; (QuickConnect not on the fetched page) [S55]. Site behind CloudFront/APISIX [S24] |

### 1.9 Developer PaaS (brief)

| Product | Facts |
|---|---|
| **Coolify** | 65,899 stars, Apache-2.0, PHP, v4.7.5 (2026-11-10); "360+ one-click services" in repo description. Self-hosted free; Cloud $5/mo for 2 servers + $3/mo each extra, 20% off annual (you bring servers) [S56][S57]. Site **Astro** [S24] |
| **Dokploy** | 38,394 stars, v0.31.0 (2026-11-05). LICENSE: copyright Dokploy Technology, Inc., with "/proprietary" directories under a separate license (GitHub reports Other/NOASSERTION). Cloud: Hobby $4.50/server/mo, Startup from $15/mo; Swarm and multi-server listed as features. Site **Next.js** [S58][S24] |
| **CapRover** | 15,205 stars, v1.16.0 (2026-11-03); LICENSE header Apache-2.0, copyright BigZee Ventures LLC (GitHub API reports NOASSERTION) [S59] |

### 1.10 Other entrants found

| Entrant | Finding |
|---|---|
| **Puter** | "Open-Source Internet Computer", self-hostable; AGPL-3.0; 44,130 stars; release 26.11 (2026-11-02); web desktop with app store, AI builder, dev APIs (AI, KV, object storage, serverless workers); Plausible + Sentry on site. A browser-OS UX reference, not a home-server OS [S60] |
| **Cloudron** | Self-hosted app platform; pricing Free (2 apps) / Pro EUR 15 (or 30) / Max EUR 25 (or 50) per month (page ambiguous on monthly vs yearly); SSO, firewall, email; directory server + groups on Max; license not stated on page [S61]. Site nginx + Drupal strings (weak signal) |
| **ClawBox** (ID Robots OOD) | "Home AI server" appliance: Jetson Orin Nano Super 67 TOPS, 8GB, 512GB NVMe, 20-25W, Ubuntu + OpenClaw pre-installed, local models (Qwen2.5 3B, Whisper, Kokoro, LLaVA 7B, CodeLlama 7B) + optional Claude/GPT, messaging bridges; EUR 749. Vendor marketing only; no license stated [S12] |
| **DIY stack pattern** | Ollama + Open WebUI + Caddy + Tailscale, plus NVIDIA DGX Spark mentioned at roughly $3,000-5,000 (from low-quality aggregator posts; treat as UNVERIFIED) [S62] |
| **Umbrel/Olares-adjacent agent runtimes** | OpenClaw and Hermes appear as first-class installable agents on umbrelOS and OpenClaw on Olares and ClawBox [S20][S4][S12] - a de-facto "agent app" category is forming |

---

## 2. Comparison table

| | Umbrel | Olares | ZimaOS/CasaOS | HAOS | N.O.M.A.D. | StartOS | YunoHost | Runtipi | Cosmos | Unraid | TrueNAS/HexOS | Coolify |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Runtime | Docker Compose | **K3s/k8s** | Docker | Docker (Supervisor) | Docker | Containers (Rust) | Native Debian pkgs (**UNVERIFIED**) | Docker | Docker | Docker + VMs | Docker (24.10+) | Docker/Swarm |
| App catalog | ~300+ | n/v | 182 official / 500+ claimed | 33 official + community | ~8 built-in + custom | n/v | n/v | ~271-300 | 250+ | Community Apps | 487 community train | 360+ services |
| Multi-user | Yes (2.0) | Yes (LLDAP/Authelia) | n/v | Yes | Kolibri multi-user | n/v | n/v | n/v | SSO/MFA | n/v | Yes (NAS) | Cloud teams |
| Multi-node | No found | k8s-capable | No | No | No | No | No | No | Pro only | No | No | Yes (servers) |
| MCP | **Yes** | Agent skills, MCP n/v | No found | **Yes** (2025.2) | No found | No (AI support agent) | No found | No found | No found | No found | No found | No found |
| Local AI | Ollama + GPU | Model console, GPU pooling | Photo AI only | Voice/Assist | Ollama + RAG | No | No | AI apps in store | n/v | via apps | Ollama app (HexOS) | n/a |
| Own hardware | Home, Pro | One | ZimaBoard/Blade/Cube | Green, VoicePE, adapters | None | Server One, router | None | None | None | None | None | None |
| Entry hardware price | $499 | $4,999 (feed) | $339 board / $649 cube | $199 | n/a | n/v | n/a | n/a | n/a | n/a | n/a | n/a |
| License | PolyForm NC | AGPL-3.0 | CasaOS Apache / ZimaOS none | Apache-2.0 | Apache-2.0 | MIT | AGPL-3.0 | GPL-3.0 | Commons Clause | Proprietary (paid) | LGPL-3.0 | Apache-2.0 |
| Stars | 12.5k | 5.4k | 37.6k / 3.1k | 7.7k OS / 92k core | 43.1k | 2.0k | 3.0k | 9.7k | 6.2k | n/a | 2.6k (middleware) | 65.9k |
| Business model | HW + add-on | HW | HW + affiliate | Cloud sub + HW | n/v | HW + support | donations (n/v) | sponsors | Pro sub | License $49-$249 | Sub/HW (n/v) | Cloud sub |
| Site stack | Next.js/Vercel + Shopify | Vue SPA + VitePress + WP + Shopify | Nuxt + Shopify | Jekyll | Next.js/Vercel | Angular | static | Next.js | Next.js | Craft | WP / Nuxt | Astro |

n/v = not verified in this session.

---

## 3. What this means for positioning (derived, not sourced)

- Compete on **what Umbrel's license forbids** (OEM/white-label by third parties) and **what Olares' price/min-spec excludes** (cheap edge nodes).
- Table-stakes to match by launch: multi-user, MCP server with revocable per-agent tokens, GPU support, VM support, one-click agent apps, remote access without port forwarding.

---

## 4. Gaps no one fills (from this sample)

Method note: "not found" means I searched vendor READMEs/pages and ran web searches; it is **not** proof of absence.

1. **Robotics / physical AI.** Search for ROS 2 integration across Umbrel, ZimaOS, Olares found nothing; results were robot-side app stores (OpenMind, Unitree beta, Hugging Face Reachy Mini 200+ apps) [S63]. No home-server OS advertises a robotics app category or ROS bridge. Hardware-side exceptions: ZimaOS added touchscreen/GPIO config for select Intel platforms in 1.8.0 [S32] and ClawBox uses a Jetson [S12], but neither is robotics orchestration.
2. **TAK / situational awareness.** A targeted search for TAK/ATAK with Umbrel/CasaOS/StartOS/Olares returned nothing relevant [S64]. Offline maps exist only in N.O.M.A.D. (ProtoMaps) [S16]. No competitor offers TAK Server, CoT routing, or tactical map as a first-class app.
3. **Mesh networking (Meshtastic/Reticulum/LoRa/Wi-Fi mesh).** Not found in any README or page I read. Nearest: Tailscale remote access (Umbrel), private VPN (Olares), Constellation VPN (Cosmos Pro), Tor (Start9, via nav link) [S3][S4][S49][S44].
4. **Multi-node Kubernetes for the home.** Only Olares builds on k8s (K3s default) [S25]; Cosmos Pro offers multi-server clusters [S49]; PaaS tools do Swarm/multi-server [S58]. No consumer-polished "add a second box and the cluster grows" story was found. **UNVERIFIED** whether Olares exposes multi-node join in UI.
5. **Agent-native access as an OS-level contract.** MCP exists at Umbrel (install apps/files/troubleshoot) and HAOS (device control), but I found no cross-app MCP *registry* where every installed app auto-exposes MCP tools with per-app scoping. (Umbrel docs fetched give no tool list [S2].)
6. **XR / spatial computing.** No mention in any product page or README reviewed.
7. **Education.** N.O.M.A.D. covers offline learning (Kolibri/Khan) [S16]; nobody pairs a hardware+OS with structured curricula, classroom multi-user, or credentialing. OneMind's Circle.so education idea is open ground.
8. **Sovereign comms + emergency use.** N.O.M.A.D. targets it as software only; no vendor sells ruggedized/field kits [S16].

---

## Sources

- [S1] https://github.com/getumbrel/umbrel (README)
- [S2] https://github.com/getumbrel/umbrel/releases/tag/2.0.0 (MCP, multi-user)
- [S3] https://github.com/getumbrel/umbrel README (license PolyForm NC, devices, features)
- [S4] https://github.com/beclab/Olares (README, license, release)
- [S5] https://www.olares.com/docs/developer/concepts/ (nav: "Use Olares CLI with AI agents")
- [S6] https://www.home-assistant.io/integrations/mcp_server/
- [S7] https://store.umbrel.com/products.json
- [S8] https://one.olares.com/products.json
- [S9] Web search results: https://www.techradar.com/pro/worlds-fastest-mini-pc-doesnt-run-windows-11-usd2899-gets-you-a-core-ultra-9-cpu-96gb-of-ram-rtx-5090m-2tb-ssd-and-yes-it-is-all-about-ai ; https://olares.com/pages/thank-you-for-your-interest-in-olares-one ; https://www.notebookcheck.net/Mini-PC-with-RTX-5090-Mobile-GPU-arrives-with-eye-watering-price-tag.1159783.0.html (prices from search snippets, not opened pages)
- [S10] https://shop.zimaspace.com/products.json
- [S11] https://www.home-assistant.io/green/
- [S12] https://clawbox.com/home-ai-server
- [S13] https://github.com/Start9Labs/start-os
- [S14] https://github.com/IceWhaleTech/CasaOS
- [S15] https://github.com/IceWhaleTech/ZimaOS
- [S16] https://github.com/Crosstalk-Solutions/project-nomad ; https://www.projectnomad.us
- [S17] https://www.cnx-software.com/2026/04/12/umbrelos-a-debian-based-personal-home-cloud-os-with-a-slick-user-interface/ (headline only, search result)
- [S18] https://github.com/getumbrel/umbrel-apps/tree/master/jellyfin
- [S19] https://github.com/getumbrel/umbrel-apps ; https://github.com/runtipi/runtipi-appstore (directory counts via `gh api`)
- [S20] https://umbrel.com/umbrel-pro
- [S21] https://umbrel.com/umbrel-home
- [S22] https://bitcoinmagazine.com/business/umbrel-announces-new-umbrel-home-plug-and-play-server (search result snippet)
- [S23] `gh repo view getumbrel/umbrel`
- [S24] Response headers/HTML of umbrel.com, home-assistant.io, start9.com, zimaspace.com, coolify.io, dokploy.com, runtipi.io, cosmos-cloud.io, hexos.com, unraid.net, truenas.com, projectnomad.us, puter.com, synology.com (curl, 2026-11-10)
- [S25] https://www.olares.com/docs/developer/concepts/system-architecture
- [S26] https://www.olares.com/docs/developer/concepts/
- [S27] https://www.olares.com
- [S28] https://www.olares.com/docs (VitePress meta), https://www.olares.com/blog (WordPress meta), one.olares.com (Shopify), community.olares.com (Discourse meta)
- [S29] https://maketecheasier.com/best-home-server-os-for-self-hosted-apps (search snippet re CasaOS overlay)
- [S30] https://github.com/IceWhaleTech/CasaOS-AppStore
- [S31] https://www.zimaspace.com
- [S32] https://github.com/IceWhaleTech/ZimaOS/releases (1.8.0 notes via API)
- [S33] https://www.zimaspace.com (HTML: shop links, affiliate page)
- [S34] https://community.zimaspace.com (Discourse generator meta)
- [S35] https://github.com/home-assistant/operating-system
- [S36] https://www.home-assistant.io/installation/
- [S37] https://github.com/home-assistant/addons
- [S38] https://www.nabucasa.com/link/
- [S39] https://www.home-assistant.io/blog/categories/release-notes/
- [S40] https://www.nabucasa.com/hardware/
- [S41] `gh repo view home-assistant/core|operating-system|supervisor`
- [S42] home-assistant.io (Jekyll meta), nabucasa.com (Astro meta), developers.home-assistant.io
- [S43] https://start9.com/server-one
- [S44] https://start9.com/
- [S45] start9.com HTML (Angular/Taiga signatures), community.start9.com (Discourse meta)
- [S46] https://github.com/YunoHost/yunohost ; https://github.com/YunoHost/apps
- [S47] https://freedombox.org ; https://github.com/freedombox/freedombox
- [S48] https://runtipi.io ; https://github.com/runtipi/runtipi
- [S49] https://cosmos-cloud.io ; https://github.com/azukaar/Cosmos-Server
- [S50] https://sandstorm.io ; https://github.com/sandstorm-io/sandstorm
- [S51] https://www.truenas.com/docs/scale/25.04/gettingstarted/scalereleasenotes (via search summary)
- [S52] https://github.com/truenas/apps ; https://github.com/truenas/middleware
- [S53] https://account.unraid.net/buy
- [S54] https://hexos.com
- [S55] https://www.synology.com/en-us/dsm
- [S56] https://github.com/coollabsio/coolify
- [S57] https://coolify.io/pricing
- [S58] https://dokploy.com/pricing ; https://github.com/Dokploy/dokploy (LICENSE.MD)
- [S59] https://github.com/caprover/caprover
- [S60] https://github.com/HeyPuter/puter
- [S61] https://www.cloudron.io/pricing.html
- [S62] https://clawbox.com/home-ai-server ; https://www.digitalapplied.com/blog/home-ai-server-build-self-hosted-llm-2026-guide (search results; low quality)
- [S63] Web search "ROS 2 robotics home server OS app store personal cloud physical AI": https://www.eweek.com/news/unitree-launches-robot-app-store/ ; https://www.pulse.bot/robotics/news/openmind-unveils-robot-app-store-510dd510-5d13-4b14-a7ec-9bf69f058118
- [S64] Web search "self-hosted TAK server ATAK home server app ..." (no relevant results)
