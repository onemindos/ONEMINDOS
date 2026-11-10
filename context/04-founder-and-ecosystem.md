# 04 - Founder profile and OneMind ecosystem

> **For the research mission, RESEARCH-MISSION.md overrides this file.** Do not touch any live cluster or account. Treat all state described here as *reported*, not verified. The founder's 'I pick the next step' rule does not apply inside the mission — decide and record assumptions. Put learning material in research-output/27-LEARNING-PATH.md, not docs/learning/. The model-tier delegation rule (Sonnet/Haiku/Opus) describes the founder's own setup and is not a requirement for you.

> Source: the founder's AI-assistant memory notes (as of 2026-11-10), condensed for the research agent.
> Architecture and intent only. Credentials, IDs, IPs, internal hostnames, emails and personal
> health/legal/finance/family details were deliberately left out. Where something was removed it is
> marked `[redacted: sensitive]`.
> Facts below are what the founder's prior sessions recorded. Treat them as "reported state", and
> confirm against the live repo/cluster before relying on them (see "How to work with the founder").

---

## 1. Founder profile

**Who:** Zeus, founder and operator of OneMind OS, a sovereign intelligence platform built on NATS,
TAK Server, an in-house AI agent ("Legacy", running on the Hermes agent framework), ClickHouse and
Kubernetes (DigitalOcean Kubernetes, DOKS).

**Strong in:** Kubernetes, NATS JetStream, Python, TAK / Cursor-on-Target (CoT), GitOps with ArgoCD,
ClickHouse, managed model APIs. Reads code, manifests and logs directly.

**Still learning:** Linux, operating-system and platform engineering. As of 2026-11-10 he asked that
OneMind OS work be treated as "an educational process" for him.

### Working style and rules (these apply to the research you produce)

| Rule | What it means for your output |
|---|---|
| **Action-first** | When he says "let's do it", build. Don't ask about obvious implementation details. Short, direct answers, no padding. |
| **Research, don't assume** | Every product fact, version, limit or setup step must come from a primary source (official docs, repo code, release notes). Anything not confirmed is labeled "not confirmed / needs research". A past mistake: a claim that "DOKS has no GPUs" was wrong (DOKS has GPU node pools). |
| **Follow proven competitors** | "Use the proven competitors for real life documentation and use cases. They already figured it out." Before proposing any OS, update, backup, security or dashboard design, show what Home Assistant OS, umbrelOS and Olares actually do, citing docs or repo paths. Default to their pattern; deviate only with evidence and a stated reason. Flag where OneMind's needs (multi-node k8s, NVIDIA Jetson, robotics) go beyond what they cover. |
| **Teach while building** | Explain choices in plain terms with comparisons and the "why". Tie each choice to competitors and to requirement IDs in `docs/REQUIREMENTS.md`. Lessons go in `research-output/27-LEARNING-PATH.md`, each with vocabulary and check-yourself questions. Explain the "why" for any architectural idea he hasn't heard before. |
| **User picks the next step** | Recommend, but don't start the next phase (even read-only extraction) until he names it. "Next" or "move on" is not a choice of target; ask which one. |
| **No deletes without permission** | Never delete files or repos without explicit per-item confirmation. "Already copied elsewhere" does not mean "safe to delete". Move, don't delete. |
| **GitOps only** | Fix things in git and let ArgoCD apply them. Never make imperative-only cluster changes. |
| **Parallel agents for big builds** | Implementation is delegated to worker subagents (Sonnet), quick lookups to Haiku, and one Opus session plans, reviews every diff, runs validation and owns merges and cluster actions. Workers never merge, push to main or run cluster write operations. |
| **Don't drop goals** | He asked that none of the future deployment goals be dropped from plans. |
| **Secrets stay out of repos** | Sensitive material lives in a password manager or a local-only folder, never in a git repo. Secret scanning runs in pre-commit. |

---

## 2. Ecosystem map

### 2.1 Repositories and directories (survey of 2026-07-13, updated through 2026-11)

| Repo / dir | Purpose | Reported state |
|---|---|---|
| Infrastructure monorepo (GitOps) | Terraform + ArgoCD + Kubernetes manifests for the DOKS cluster; also Backstage catalog, apps, docs, reports | Live, mature. All changes go through PRs. |
| Ops-center UI repo | React 19 / Vite / Tauri 2 / Capacitor ops center, NATS-native, 20 modules | Built, but the founder does **not** use it and likely won't (decided 2026-10-11). Don't propose building in it. |
| Legacy agent repo | "Operational genome" of the Legacy AI: agent roster, creed, soul, runbooks | Living doc, partly self-authored by Legacy |
| Voice gateway repo | Python voice gateway (see 2.5) | Ears and mouth proven; brain integration next |
| Homestead RADS repo | Homestead digital twin: soil, irrigation, drones over NATS + ClickHouse | Phases 1-2 done (soil sensors + PX4 SITL drone simulation), Phase 3+ scaffolded |
| Blueprints repo | Static HTML visual specs (NATS fabric, skill trees, migration plan, agent roster) | Planning artifact |
| NEX core repo | NEX (NATS Execution Engine) Go daemon | Source lives in the `Converge code` scratch area; local dir holds runtime data only |
| `Converge code` | 33 research/scratch sub-projects | Mixed. Worth promoting: `agenttap` (Wireshark-style viewer for NATS agent traffic), `heynats` (NATS admin UI, Go + React), `worldwideview` (Next.js + CesiumJS 3D globe with plugin architecture), `osiris` (OSINT dashboard, MapLibre, 16 layers), `tak-server-mcp` (MCP server bridging TAK Server to LLMs) |
| `Convergence docs` | 53 research docs: NATS, TAK, drones, AI, C4ISR, homestead | Reference library. Key: Legacy self-calibration framework, agent "dojo" training (sandbox -> dojo -> production), evolution to C4ISR, 18-domain self-sovereign homestead stack, 16+ protocol-to-CoT converter specs |
| CloudTAK plugin repos | `cloudtak-plugin-ops`, `-hermes`, `-clickhouse`, `-mumble` (scaffolded, not wired); `-nats`, `-legacy-ai` (live) | Follow the `@tak-ps/cloudtak` PluginAPI (`install/enable/disable`). Next step: bundle into the CloudTAK build. |
| This repo | OneMind OS product research: `docs/REQUIREMENTS.md` (82 requirement IDs), `docs/ARCHITECTURE.md`, `research/` | Started 2026-11-10 |

### 2.2 Agent roster (from the Legacy agent repo)

Authority chain: **Zeus -> Legacy Mother -> all agents -> tools.**

| Agent | Role | Where |
|---|---|---|
| Legacy Mother | Sovereign meta-agent (Claude via a managed model API) | DOKS cluster |
| Legacy Daughter / Edge | Edge body of Legacy | Mac |
| Forge | Coding orchestrator (Opus + small coder-model workers) | DOKS |
| Oracle | Intelligence / analytics | planned |
| Guardian | Security sentinel | planned |
| Grid | Infrastructure manager | planned |
| Spartan | Personal performance | planned |
| Haven | Home / Home Assistant manager | planned |
| Heritage | Records keeper | planned |
| Empire | Business admin | planned |
| Eden | Sustainability / RADS homestead | planned |
| Trinity | Cross-system integration | planned |

### 2.3 Interface and task engine

- **Obsidian is the main interface** (decided 2026-10-11) for tasks, projects, greenhouse, robotics and
  infra, on every device. Cluster apps are reached over Tailscale and shown inside Obsidian's web viewer.
- Must work hybrid (cloud cluster + planned home cluster) and **off-grid**. Vault is local-first markdown, backed by git.
- Goal: AI agents read and write the vault; the vault doubles as task engine and approval queue.
- Direction: TaskNotes (one note per task, Obsidian Bases) as the task UI and file-format contract; a
  cluster-side "vault engine" owning events (NATS + webhooks), REST/MCP, indexing, reminders (ntfy / Hermes),
  an ICS feed and git snapshots. Plugin webhooks are desktop-only, so never rely on them.
- Sync bake-off (2026-10-12): verification picked **Syncthing** (no sync plugin) + a cluster vault-git
  sidecar; Self-hosted LiveSync (CouchDB) is the fallback. Work is **paused**, captured in a draft PR.
- Devices: macOS + Android (no iOS), maybe Windows/Linux. Heavy files (video, audio, installers, >20 MB) stay out of the ops vault.
- Plugins/themes distributed privately (BRAT / git) for now.

### 2.4 Knowledge and task tools

The founder uses an Obsidian vault and Todoist (SO/LE/HP/GE pillars) for knowledge and tasks.

### 2.5 Voice pipeline (voice gateway repo)

```
Mumble push-to-talk -> RealtimeSTT (VAD + faster-whisper) -> NATS voice.transcript
                                                              |
                                                     Legacy AI on the NATS bus
                                                              |
                     Mumble <- Piper TTS (local, sovereign) <- NATS voice.say
```

Proven: ~0.36 s speech-to-text latency. Next: Legacy subscribes to `voice.transcript` and replies.
(the ops-center UI also had a LiveKit push-to-talk module.)

### 2.6 NATS subject grammar (locked)

```
tel.{node}.{class}.{metric}          telemetry
det.{domain}.{type}.{id}             detections
evt.{domain}.{entity}.{event}        semantic events
cmd.{domain}.{entity}.{action}       commands
intel.{domain}.{source}.{type}       intelligence
ent.{entity_type}.{entity_id}.state  fused entity state
svc.{service}.{endpoint}             NATS RPC
agents.{verb}.{agent}.{owner}.*      agent fabric
tak.cot.inject / tak.cot.>           CoT wire
voice.transcript / voice.say         voice layer
rad.{site}.{subsystem}.{id}.*        homestead / RADS
```

Plugin-level subjects in use: `agents.prompt|response|tool.*` (Hermes chat), `onemind.inbox.>`,
`onemind.tasks.>`, `onemind.alerts.>` (ops plugin).
Data-plane examples: `intel.weather.noaa.alert.{state}.{event}`, `intel.seismic.usgs.{bucket}.{id}`,
`intel.conflict.acled.{iso3}.{event}`, `intel.fire.nasa.firms.{region}`;
toggles `cmd.etl.sink.tak.{enable|disable}`, `cmd.etl.feed.{feed_id}.{enable|disable}`.

### 2.7 Data plane and ClickHouse "time machine"

Goal: one normalized pipeline (raw world events -> NATS JetStream -> every consumer at once, with
switch-flip control) instead of each platform pulling data on its own.

Five layers:
1. **Feed workers** poll public APIs and publish `intel.*` / `tel.*` (NOAA, USGS live; ACLED and NASA FIRMS present but disabled).
2. **NATS JetStream bus** (exists): e.g. an INTEL stream `intel.>` kept 90 days, a COT stream `tak.cot.>` kept 30 days.
3. **Sink workers** (durable consumers): `sink-tak` forwards to TAK Server; `sink-clickhouse` writes history.
4. **Maps:** TAK Server -> all TAK clients; WorldWideView 3D globe.
5. **Legacy** subscribes to `intel.*`, queries ClickHouse, publishes `cmd.*` to control everything.

ClickHouse table `onemind.events` (live): entity id/type, source, lat/lon, payload, timestamp; 10-year TTL,
partitioned by entity type + month. Legacy uses it for historical analysis. Feed/sink manifests are
managed by an ArgoCD app (push to git, auto-sync). Some sink/doc pieces were still being built when recorded.

Planned **ETL -> NATS** replacement for CloudTAK's AWS-Lambda-based ETL: an ETL-runner controller
reads layer schedules and fires an ETL trigger subject per task; task containers run and post to CloudTAK; a
NATS -> CloudTAK CoT ingest bridge; TAKML vision workers publish CoT the same way. Build order: ingest
bridge -> runner -> port `etl-geojson` -> TAKML vision -> CoT. Not built yet.

### 2.8 CloudTAK at onemindos.dev

- CloudTAK (web TAK client) is **live at `onemindos.dev`**, backed by TAK Server 5.x in the cluster and a PostGIS database.
- CloudTAK uses certificate-based login with passkeys; device enrollment via Authentik.
- **OneMind app shell** (2026-08-26): a top toolbar with an app switcher (Map / Dashboard / Video / Board) driven
  by a one-line-per-app registry; map tools only show on map routes. Future: consolidate the separate SPAs
  into one router with the map kept alive; NATS monitor and Intel feed pages on the roadmap.

### 2.9 Authentik at auth.onemindos.dev

- Authentik identity provider (2026.8.x) **live at `auth.onemindos.dev`**, with its own Postgres and Redis, deployed by ArgoCD.
- Purpose: self-service enrollment of TAK end-user devices (QR code -> certificate -> ATAK/iTAK) and an
  LDAP outpost so TAK Server can map certificates to identities.
- LDAP outpost: **pending** (manual step after first login; token to be sealed with Sealed Secrets).
- A TAK enrollment portal runs in the cluster; device enrollment is handled via Authentik.

### 2.10 Cluster hardening roadmap (started 2026-10-09)

Goal: a self-hosting cluster that is **recoverable, alerting, and portable off DigitalOcean** (home server
soon), with every change as a PR to the GitOps repo.

Decisions (2026-10-10):
- **Alerts -> Matrix (self-hosted) + Telegram.**
- **Off-site backups:** planned as part of the hardening work.
- **TAK over Tailscale:** TAK devices connect over the tailnet; public TAK ports close.

PR roadmap: health quick wins (merged) -> alert delivery -> adopt ~11 Helm-CLI releases (incl. TAK Server,
NATS, monitoring, ArgoCD) into ArgoCD -> off-site backups + **restore drills** -> right-sizing ->
networking (Cloudflare Tunnel, external-dns, TAK via Tailscale) -> repo hygiene/CI ->
**portability (Talos-based home cluster)** -> scoped cluster access for Hermes/Legacy.

### 2.11 Backstage (proof of concept for the platform catalog)

- Backstage runs in the cluster as the service catalog / developer portal (reached over Tailscale, sign-in required).
- It holds ~570 entities with 0 processing errors (verified 2026-10-16): the full "Fabric" infrastructure
  registry (174 entries migrated from Notion) and the 61-tool Tech Stack, with license / platform /
  integration annotations. A home page lists every component that has an "open application" link, grouped by category.
- Gotchas recorded: the inventory generator is not idempotent (rewrites catalog files and drops
  `verified-at` annotations), and the Fabric reconciler rebuilds every `fabric-*` entity on refresh, so hand edits don't survive.
- A read-only Backstage MCP server (catalog queries, health, runbooks) and a read-only Kubernetes MCP server are available to agents.

### 2.12 Content pipeline (idea, not built)

Goal: one YouTube video -> ~100 on-brand posts across the main platforms, posted by AI.
Stack chosen: OBS (record), HyperFrames (HTML -> video, brand templates), an ffmpeg skill (cuts, reframe,
captions, export checks), Postiz (distribution via API/MCP/CLI). Verified constraints (2026-10-29): YouTube
upload quotas, TikTok unaudited apps are private-only with manual consent (human review step required),
Postiz has no comment inbox, EU AI Act Art. 50 labeling obligations. Leaning: Postiz Cloud first, self-host later.
Next step waits on the founder.


### 2.13 Product planning docs and this repo

- The founder's offline planning set (Nov 3-4, 2026): a Unified Vision and Strategy doc,
  the **Architecture and Implementation Blueprint (canonical)**, a Linux desktop + sovereign ATAK devices
  handoff (Dell Latitude 5540 Omarchy pilot, 14 desktop plugins, phone/ATAK candidates), and an
  **outdated** Build Handoff (says no k8s, NATS "later", Letta, ClickUp - do not take architecture from it).
  None of these say anything was built, installed or bought.
- Open decisions at review: whether Google hardware is acceptable, the Dell's current state, the first vertical slice, the active task system.
- This repo's `docs/ARCHITECTURE.md` direction: **k3s everywhere + an immutable Ubuntu 24.04 image, with
  Kairos leading a bake-off**, and a capability layer driven by an `onemind.app.yaml` manifest.
- Licensing facts recorded: umbrelOS is PolyForm Noncommercial and Olares is AGPL, so **neither is forked**.
  Anthropic's Model Hardware Standard (MHS) was in preview as of 2026-08-27. Strava's terms bar its data in AI apps.

---

## 3. How to work with the founder (summary for the research agent)

1. Cite primary sources for every claim; mark unknowns "needs research".
2. Anchor every OS / update / backup / security / dashboard recommendation on HAOS, umbrelOS and Olares, then explain where OneMind needs more (multi-node k8s, Jetson, robotics, drones, off-grid).
3. Explain the "why" in plain language; add vocabulary and self-check questions for lessons.
4. Recommend a next step, but let him choose it (inside the research mission, decide and record assumptions instead).
5. Never include secrets, never propose deleting anything, and express changes as GitOps PRs.
6. Keep every long-term goal in the plan (robotics, drones, homestead/RADS, TAK/C4ISR, voice, agents, off-grid, home cluster).
