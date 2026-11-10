# OneMind Dashboard: How It Works (design v0.1)

**Built from:** competitor research (`research/competitors/umbrel.md`, `olares.md`, `landscape.md`), `research/platform/ai-native-protocols-and-ux.md`, ADR-001, and REQUIREMENTS (P-1, P-2, UX-1..10, U-1..5, AI-1..5, A-1, A-8, N-3, N-4).

## 1. What competitors put on screen (proven patterns)

| Area | umbrelOS 2.0 | Olares | Home Assistant | OneMind takes |
|---|---|---|---|---|
| Entry | Browser → `umbrel.local`; desktop-like home with app icons + widgets | Browser "Desktop" with app windows; LarePass phone app | Browser → `homeassistant.local:8123`; customizable dashboards | `onemind.local` home **+** phone app |
| App store | One-click App Store, ~300+ apps, community stores | Market (200+), Helm-based, permissions shown | Add-ons/Apps store + HACS | Market + bundles + "can my box run this?" |
| Files | Files app, point any app at any folder | Files app | Media browser | Files with per-app folder grants |
| Users | Household accounts (2.0) | Admin/Member roles | Users + admin flag | Owner/Adult/Teen/Child/Guest |
| System | Settings: updates (stable/beta), backups, storage (FailSafe), Wi-Fi, Tailscale | Settings + **Control Hub** (k8s-level resources) | Settings → System: updates, backups, hardware, logs | Settings (simple) **+ Control Hub (pro)** |
| VMs | "Machines": Linux/Windows/Android in browser | — | — | Machines (later, libvirt/KubeVirt) |
| AI | MCP server, per-agent tokens + permission categories | Lares agent + Router, CLI agent skills | MCP server, exposed entities | AI & Agents: grants, approvals, audit |
| Alerts | Notifications | Notifications | Repairs + notifications | **Native Alert Center** |
| Multi-node | No | Limited (2 Olares One) | No | **Nodes app: every machine/robot/sensor** |
| Customization | Widgets | Desktop layout | Fully custom dashboards (cards) | Homarr/HA-style editable grid + widgets |

**Gaps nobody fills:**
- many machines, robots and sensors in one UI
- a built-in alert center for infrastructure
- TAK and maps
- per-family-member AI permissions
- a pro mode for operators (Control Hub exists only in Olares)

## 2. Two kinds of users, one dashboard

| | **Household user** (spouse, kids, most customers) | **Operator** (Zeus, home-labbers, enterprise admins) |
|---|---|---|
| Sees | Home grid, apps, files, family, alerts meant for them | All of that **+ Control Hub, Nodes, Infrastructure, logs, GitOps** |
| Language | "Photos is updating", "Backup done ✅" | Pods, nodes, k3s versions, Argo sync, NATS streams |
| Mode | **Simple** (default) | **Pro** (toggle, role-gated) |

The same data is shown at two depths. Umbrel and HAOS cover only Simple, and Olares leans Pro. OneMind does both.

## 3. Screens (MVP)
1. **Home:** customizable grid. App tiles come automatically from each app's `onemind.app.yaml`. Plus link tiles, API widgets (keys proxied server-side), cloud-app stats where the provider's terms allow, and the AI assistant bar.
2. **Market:** browse/search/bundles. Each app shows its required CPU/RAM/GPU vs **your nodes' capabilities** (✅/⚠/❌), the permissions it requests, and its quality tier.
3. **Files:** per-user spaces, folder grants to apps.
4. **Alerts:** one inbox for app health, node down, backup failed, update ready, security events. Severity, owner routing, "AI investigate" (needs approval). Push: self-hosted on Android, a minimal-data Apple push on iOS (D-005).
5. **Nodes:** every machine/robot/sensor with health, capabilities and apps. "Add node" shows a QR code to scan. Mirror and infra map come later.
6. **Family & Users:** roles, kid limits, schedules, device approval.
7. **AI & Agents:** agents, their grants (per app/category), approval queue, audit log, model/GPU status.
8. **Settings:** updates (channel, "update now", last pre-update backup), backups (schedule, destinations, **last verified restore**), storage, network/remote access, security.
9. **Control Hub (Pro):** workloads, logs, resource use, k3s/RKE2 version, NATS, Argo status.

## 4. How it works under the hood

```
Phone app / browser / Omarchy desktop / XR
        │  (HTTPS, OIDC login)
        ▼
OneMind Gateway ── authenticates every request (user or agent), checks role + grant + policy, audits
        │
        ├── App Controller ─ installs/updates/removes apps (OneMindApp resources → Helm on k3s)
        ├── Registry ─────── turns each app manifest into tiles, alerts, MCP/REST/CLI capabilities
        ├── Node Service ─── node joins (QR), capabilities (NFD), health via NATS
        ├── Alert Service ── Alertmanager + app/node events from NATS → inbox + push
        ├── Backup Service ─ restic + k3s snapshots, schedules, restore tests
        └── Update Service ─ OS image (Rugix A/B), k3s upgrades, app updates, pre-update backups
```

**Your existing cluster:** in cluster mode, Argo CD stays the GitOps engine. The OneMind App Controller writes `OneMindApp` resources that Argo can own, so the Market and Git never fight over the same app (one manager per object, as in the Blueprint).

## 5. User flows (acceptance targets)
- **Install an app:** Market → see "✅ runs on your Lite box" → Install → approve folders and permissions → the tile appears, health checks start, and its capabilities become available to AI (only for users and agents granted access).
- **Update the OS:** alert "Update 1.2 ready" → Update → automatic backup → A/B install → reboot → marked good only after k3s + core apps are healthy, else automatic rollback plus an alert explaining why.
- **Restore:** Settings → Backups → pick a snapshot → restore app, folder or whole box (onto new hardware too).
- **Add a robot/sensor:** Nodes → Add → scan QR → node appears with its capabilities → install its gateway app.
- **Kid account:** Family → add child → choose allowed apps + schedule → the child's AI agent inherits those limits.
