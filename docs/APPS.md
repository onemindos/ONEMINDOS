# OneMind OS: App Suite Scaffold (D-003)

**Model:** one **OneMind app shell** (dashboard/desktop, on web, mobile and XR) hosts **modules**. Every module is also a standalone Market app with its own `onemind.app.yaml`. That means it can be installed alone, its capabilities are registered for AI (MCP/REST/CLI), its alerts flow into the alert center, and its tiles appear on the dashboard.

**Status:** scaffold only, meaning purpose, MVP scope and integrations. No code yet. "Replaces / learns from" names products to study, not code to copy (license rules in D-001).

---

## A. Built-in system apps (ship with every install)

| Module | Purpose | MVP | Learns from |
|---|---|---|---|
| **Home (Dashboard)** | The front door: tiles, widgets, external links, cloud-app stats | Customizable grid, app tiles from manifests, link tiles, API widgets via server-side proxy | Umbrel home, Olares Desktop, Homarr (Apache-2.0), Homepage (ideas only) |
| **Market** | App store + bundles + "can my box run this?" | Git-backed catalog, one-click install, NodeCapabilities check, quality tiers | Umbrel App Store, Olares Market, HA quality scale |
| **Files** | Storage, folders, per-app folder access, sharing | Browse/upload, mount folders into apps, per-user spaces | Umbrel Files, Olares Files |
| **Vault** | Passwords, secrets, API keys, cloud-app tokens | Secret store UI over OpenBao/Infisical, OAuth connect flows | Olares Vault, Infisical |
| **Alerts** | Native alert center (D-005) | Alertmanager-backed inbox, routing, push (ntfy/UnifiedPush, minimal APNs) | Uptime Kuma, Alertmanager |
| **Nodes (Control Hub)** | Every machine/robot/sensor as a node; health; QR join; mirror; infra map | Node list, capabilities, join via QR, k3s + NATS status | Olares Control Hub, Umbrel settings |
| **Family & Users** | Accounts, roles (owner/adult/teen/child/guest), parental controls | Users, roles, per-app access, schedules | Olares roles, Jellyfin parental model |
| **AI & Agents** | Agent roster (Hermes/Legacy + others), grants, approvals, audit, models | Agent tokens + scopes, approval queue, model/GPU status | Umbrel MCP agents, Olares Lares/Router |
| **Settings** | Updates (channels, user-timed A/B), backups, network, domains, remote access | Update scheduler, backup targets, Tailscale/Headscale | Umbrel settings, Olares Settings |
| **Studio** (developer) | Build/test/publish OneMind apps and plugins | Manifest editor + linter, local dev install | Olares Studio, Omarchy plugin validate |

## B. OneMind domain modules (internal apps that replace outside tools)

| Module | Purpose | MVP scope | Data / integrations | Replaces / learns from |
|---|---|---|---|---|
| **Projects & Tasks** | PM and tasks, AI-native, tied to the knowledge vault | Projects, tasks, sections, due dates, agent-created tasks, Obsidian links; SO/LE/HP/GE pillars | Obsidian vault, Todoist import, calendar | ClickUp, Todoist, Plane (Olares market) |
| **Knowledge (Codex)** | Notes, docs, research, Legacy Codex | Markdown vault view/search, AI retrieval with citations | Obsidian (portable files), RAGFlow/AnythingLLM-style RAG | Obsidian, AFFiNE |
| **Wellness** | Health, habits, fitness, sleep, nutrition | Habit tracker, manual + device data, daily brief | Health APIs **only where terms allow AI use** (Strava bans AI use of its data; use its official MCP or exclude); local-only by default | Strava/Garmin dashboards, Apple Health |
| **Finance** | Budgets, accounts, net worth, business books | Accounts, transactions import (CSV/OFX), budgets, reports; sensitive-data handling | Bank exports; self-hosted ledgers to study (Actual, Firefly III; check licenses) | Mint-style apps |
| **Family** | Household ops: calendar, chores, school, kids' learning | Shared calendar, chores, kid profiles, learning links | Family & Users roles; Kolibri/Kiwix for education | Cozi-style apps, N.O.M.A.D. education packs |
| **Situational Awareness (TAK)** | Maps, positions, CoT, field ops | CloudTAK embed, TAK server status, positions on map, geofence alerts | TAK Server/CoT via NATS (`tak.cot.*` doctrine) | ATAK/CloudTAK |
| **Mesh & Networking** | Network map, VPN, mesh radios, Wi-Fi | Tailscale/Headscale peers, Meshtastic node list, network map | Headscale, Meshtastic MQTT, batman-adv | UniFi-style controllers |
| **IoT & Home** | Devices, automations, greenhouse | Home Assistant as engine; OneMind views + AI capabilities; greenhouse template | HA (Matter/Zigbee/Z-Wave/ESPHome), MQTT | HA dashboards |
| **Robotics & Drones** | Robots and drones as nodes: status, missions, sim | Robot node registry, telemetry, MAVLink/ROS 2 gateway status, Isaac Sim launch (Pro/Omni only) | ROS 2 containers, PX4/MAVLink, Open-RMF; MHS adapter when available | Fleet tools, Open-RMF |
| **Infrastructure** | Advanced ops for clusters/enterprise | Workloads, GitOps (Argo) status, logs, metrics | k8s API, Argo CD, Prometheus/Grafana | Backstage (stays a dev portal), Portainer |
| **OSINT & Intel** | Open-source intelligence feeds and analysis | Feed ingest → NATS, search, alerts | Existing OneMind data plane (ClickHouse "time machine" plans) | Custom |
| **Education** | Learn self-hosting and the OS, in-product | Guided setup, tutorials linked to Circle.so courses | Circle.so (website), Kolibri offline | Umbrel/Olares docs |

## C. Build order (proposal; Zeus can reorder)
1. **Shell + system apps**: Home, Market, Alerts, Nodes, Family & Users, AI & Agents, Settings. Without these, no module can be installed or used.
2. **Projects & Tasks + Knowledge**: used daily, so they get tested hard and show "everything is AI context".
3. **IoT & Home + Situational Awareness**: built on what Zeus already runs (HA, TAK).
4. **Wellness, Family, Finance**: the consumer value.
5. **Mesh, Robotics & Drones, OSINT, Infrastructure, Education**: the moat modules, tied to the hardware tiers.

## D. Scaffold checklist per module (to create when coding starts)
- `apps/<module>/onemind.app.yaml` (id, entrances, storage, roles, capabilities, alerts, widgets)
- `apps/<module>/README.md` (purpose, MVP, data ownership, offline behavior)
- capability list with read/write/destructive effect and which need human approval
- NATS subjects used (following the existing NATS doctrine)
- data export format
