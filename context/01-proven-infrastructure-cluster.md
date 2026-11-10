# The Proven Concept: OneMind's existing Kubernetes infrastructure

> **What this file is.** A sanitized summary of the founder's private infrastructure repository
> (the founder's infrastructure repo, read locally and read-only on 2026-11-10). It shows what OneMind has
> already built and run, so the research agent can judge what carries over into an appliance
> operating system (OneMind OS) and what must change.
>
> **Read the evidence labels.** The source repository mixes live observations with plans.
> This file keeps them apart:
>
> | Label | Meaning |
> |---|---|
> | **[Verified YYYY-MM-DD]** | The repo records a read-only check of the live cluster on that date (kubectl/Argo/Helm output, acceptance runs or restore drills). It was true **on that date**. It was not re-checked for this file. |
> | **[Documented]** | Described in manifests or docs as deployed or configured. No dated live check was found. |
> | **[Planned]** | Intent, design or roadmap only. Not deployed. |
> | **[Retired]** | Was deployed, then deliberately removed. |
>
> No claim in this file was re-verified against the live cluster today. Treat every status as
> "as of the date given".
>
> **Redaction.** Credentials, IP addresses, internal tailnet hostnames, bucket and account
> identifiers, cluster identifiers, personal names and family details were left out on purpose.
> Where an omission matters it is marked `[redacted: sensitive]`. The only domains named are the
> public `onemindos.dev` and `auth.onemindos.dev`.

---

## 1. Overview and mission

The repo is the infrastructure-as-code and GitOps source of truth for the OneMind platform.
It holds the cloud Kubernetes hub, platform manifests, NATS stream definitions, the TAK Server
chart and images, first-party service code, bus contracts (schemas) and Terraform for the cloud
foundation. Its own summary: **"a NATS-native C2/ISR system. NATS is the nervous system, TAK is
the tactical display, and Hermes ('Legacy') is the AI agent."**

**Mission** (recorded 2026-10-08), summarized:

- OneMind is to be the main workspace and operational workforce for a technology founder
  building sovereign infrastructure for a homestead. It covers family and personal apps,
  developer work, land management, security, greenhouse and household operations, office
  systems, distributed devices and tactical/field operations.
- The AI must be continuously available across the connected environment. It must observe,
  coordinate and take *authorized* actions through real application and device interfaces.
  "A chatbot or a directory of links alone does not satisfy the mission." TAK and real-time
  operations are central.
- **The home becomes the primary source of infrastructure and authority.** DigitalOcean is
  the current host. Cloud stays useful for public workloads, reachability and recovery.
- Durable requirements (10, abridged):
  1. Kubernetes stays the long-term application substrate. Not every sensor must run Kubernetes.
  2. Local-first: household and site operation must work through cloud/WAN loss, with no
     dependence on a remote dashboard, identity provider or inference service.
  3. One coherent workspace for daily operations and developer work. Prefer established
     open-source capabilities and keep freedom to build custom services.
  4. TAK, live situational awareness, dashboards, agents, events and workflows are first-class.
     "A periodically refreshed inventory is not the live picture."
  5. AI gets authenticated access to app contents and actions, with explicit identities and contracts.
  6. Authenticated use across web, mobile and desktop over the mesh. Offline reading and offline
     control are verified separately. "A native wrapper around a remote URL is not offline autonomy."
  7. Deliberate public exposure of selected apps only. Mesh login is not authorization to operate equipment.
  8. Recovery, export, backups, identity recovery and portability are part of app selection from day one.
  9. Extend the model to communities, multiple sites and small smart cities (a bird's-eye view
     across Kubernetes, AI work, physical assets and live operations).
  10. Long-term direction: robotics, physical AI, drones and autonomy, with useful local
      operation. This does **not** authorize autonomous physical actions or imply Kubernetes
      provides real-time vehicle control.
- The catalog is organized by four mission pillars: **SO** (Sovereign Operations),
  **LE** (Legacy Evolution), **HP** (Holistic Performance) and **GE** (Generational Empire),
  plus technical, system and site views. Pillar classification grants no permissions.

**Operations model:** AI coding agents (Claude Code, Codex and others) write most changes through
reviewed pull requests; humans approve merges.

---

## 2. Hosting

| Item | State | Evidence label |
|---|---|---|
| Provider | DigitalOcean Managed Kubernetes (DOKS), one cluster, HA control plane | [Verified 2026-10-27] |
| Kubernetes version | 1.36.x (DOKS auto-upgrades in a weekly window) | [Verified 2026-10-18/27] |
| CNI / gateway | Cilium (DOKS-managed) with Hubble; Cilium Gateway API classes exist | [Verified 2026-10-18] |
| Node pools | "Hub-core": 3 nodes x 8 vCPU / 16 GiB (TAK, NATS and foundation live here). "Ecosystem": 8 vCPU / 32 GiB nodes, autoscale 1 to 4 (1 node on 2026-10-27). No GPU nodes | [Verified 2026-10-27] |
| Scale | About 250 pods, 43 to 49 namespaces, 59 to 70 Argo CD Applications depending on date | [Verified 2026-10-18 to 10-27] |
| Storage | DigitalOcean block storage CSI. 95 PVs, about 1,182 GiB (a "retain" class for stateful data, a "delete" class for temporary claims) | [Verified 2026-10-09] |
| Object storage | DigitalOcean Spaces (S3-compatible) for every backup, same provider as the cluster | [Verified 2026-10-10] |
| Load balancers | One public DO LB for ingress-nginx. TAK and NATS are exposed only through Tailscale load balancers | [Verified 2026-10-23] |
| Container registry | GitHub Container Registry (GHCR). DigitalOcean's registry is not used; an in-cluster Harbor was removed | [Documented] |
| CI | GitHub Actions plus a self-hosted runner in the cluster (builds TAK images). | [Documented] |
| Terraform | The repo's Terraform describes the VPC and cluster but **has no state and does not match live**. Do not apply | [Documented] |

**DigitalOcean lock-in**: the managed control plane, the
block-storage classes and CSI snapshots (used by VolSync), the DO load balancer, Spaces for
backups, DO firewalls, a node-pool label in about 20 manifest lines, and DO Terraform. There is
no managed database (PostgreSQL is in-cluster via CloudNativePG) and no DO registry. The
portability docs judge a move to k3s or Talos as "a rebuild, not a rewrite".

---

## 3. Component inventory

Status is as documented on the date shown. "Tier 1" is the owner's critical list: if it is
down or loses data, the platform cannot operate or cannot be recovered.

| Component | Role | Status (as documented) |
|---|---|---|
| **Argo CD** (app v3.4.x) | GitOps controller, app-of-apps root | Live, Tier 1. Itself still a Helm-CLI release; self-adoption prepared, manual |
| **NATS JetStream** (3-node, chart 2.14.x) | The authority event bus: pub/sub, RPC, streams, KV | Live, Tier 1. About 38-39 Stream/KV CRs, all R3 file storage, about 150 GiB of PVCs. Helm-CLI release and Argo both touch the StatefulSet (two owners) |
| **NACK** | JetStream controller that reconciles Stream/KV CRs | Live, adopted into Argo |
| **NATS tools** | Web UIs (heynats, nats-dashboard, nats-ui), surveyor, per-leaf exporter | Live; Application defined |
| **TAK Server 5.8** | Tactical server: API, messaging, config, plugins, Ignite, PostgreSQL/PostGIS | Live, Tier 1. Core was a hand-applied Helm release; partial Argo ownership of its StatefulSets/Deployments from 2026-10-26 |
| **NatsBridgePlugin** | TAK Server plugin: CoT to/from NATS | Live |
| **TAK FedHub + LDAP** | TAK federation hub with MongoDB; LDAP for TAK | Live |
| **CloudTAK** | Browser TAK client | Live acceptance [Verified 2026-10-25]: connected to TAK Server, private TLS |
| **tak-portal / OneTAK geo stack** | Root site and enrollment portal; geo apps (tile server, routing, geocoding, WebODM, STAC, Tile38, MediaMTX) | Live; about 150 GiB of PVCs; some heavy apps scaled to zero |
| **TAK-ML** | Vision pipeline (server, worker, DB) | Live [Documented] |
| **TAK mesh gateway** (bridge v0.2.0) | Edge peer on the TAK mesh (SA multicast, TAK Protocol v0/v1) to NATS | Built, **not deployed** (runs on an edge host, not the cloud) |
| **Authentik** (chart 2026.8.x) | Identity provider (OIDC) for the portal, Argo CD and apps | Live, Tier 1 |
| **Tailscale operator** | Tailnet ingress, egress and LB proxies | Live; every admin UI depends on it (proposed Tier 1) |
| **ingress-nginx** | Ingress with a Cloudflare source-range allowlist | Live, single replica |
| **cert-manager** | Certificates (only namespaced self-signed issuers; public TLS ends at Cloudflare, tailnet TLS is Tailscale's) | Live |
| **Sealed Secrets** | All committed secrets are encrypted SealedSecrets | Live, Tier 1 |
| **Backstage** (1.55.3, new frontend/backend) | "OneMind" developer portal and service catalog, custom plugins | Live, 2 replicas, PostgreSQL |
| **Hermes "Legacy"** | Primary AI agent (Nous Research hermes-agent) with its own NATS leaf sidecar | Live, Tier 1, 25 GiB state PVC |
| **Hermes "fresh"** (v0.22.5) | Independent clean Hermes beside Legacy, no imported state | Source prepared; runtime acceptance pending |
| **OneMind MCP** | Small internal MCP server for Legacy: app catalog, NATS stats, Prometheus queries | Live [Verified 2026-10-27] |
| **onemind-core** | Operational core: app relationships, audited mission requests, Dapr workflows | Built; "this source/build PR alone does not activate the core" |
| **Agent fabric** | Agent Console and agent-tap (NATS agent traffic tooling) | Live |
| **LiteLLM** | Model gateway | Live |
| **Ollama** | Local CPU model runtime (20 GiB models) | Live, CPU only |
| **CloudNativePG + Barman** | Shared PostgreSQL cluster (3 instances, 120 GiB) with continuous backup | Live |
| **Dapr, KEDA** | Workflow/runtime sidecars (opt-in); event-driven autoscaling | Live |
| **OpenFGA** | Fine-grained authorization | Live |
| **Kyverno, Falco** | Policy (mostly audit mode) and runtime threat detection | Live |
| **ClickHouse "Time Machine"** | Records bus events for replay and correlation | Live, 20 GiB |
| **Feed workers** | World-intel feeds (aircraft, ships, satellites, hazards, conflict, fire) into NATS; projector to TAK; ClickHouse sink | Live (mission engine scaled to zero) |
| **Redpanda Connect** | Stream bridging/processing | Live |
| **kube-prometheus-stack, Loki, Tempo, OTel collector** | Metrics, alerts, logs, traces | Live, adopted into Argo 2026-10-17 |
| **OpenCost** | Cost metrics | Live |
| **Headlamp** | Break-glass Kubernetes UI (replaced Kubernetes Dashboard) | Live |
| **Velero, VolSync, backup CronJobs** | Namespace backups, PVC copies (restic), logical DB/NATS dumps | Live, Tier 1 |
| **health-keeper** | Read-only cluster observer every 5 min (no repairs) | Live |
| **n8n** | Workflow automation | Live |
| **Matrix (Synapse/Element)** | Chat; candidate alert channel | Live but OutOfSync; Application manual until a secret is sealed |
| **Nextcloud** | Private file sync | Live [Verified 2026-10-23] |
| **Vaultwarden** | Personal password vault | Live [Verified 2026-10-25], restore tested |
| **Karakeep** | Bookmarks/read-later | Live rollout [Verified 2026-10-25] |
| **Paperclip** | Business agent workspace | Deployed 2026-10-24; agent round trip under verification |
| **STAC** | Imagery catalog (PgSTAC) | Live recovery [Verified 2026-10-25] |
| **OpenChoreo** (1.3.1) | Internal developer platform for Layer-3 apps | [Retired] owner approved teardown 2026-10-23 |
| **OpenClaw**, **Kubernetes Dashboard**, **OpenSearch**, **External Secrets** | Various | [Retired] Oct 2026 |
| **Murmur (voice)** | Push-to-talk voice for TAK and the agent voice pipeline | Documented both as an in-cluster TAK overlay and as an older separate VM |

---

## 4. GitOps (Argo CD) and the Backstage portal

### 4.1 Deployment pattern

1. Every workload's manifests live in a layered directory tree. An Argo CD Application in
   the app-of-apps directory applies them. "A path with no Application is not deployed."
2. Third-party charts are pinned (`targetRevision`). Foundation charts are also checksum-locked
   (with a lock file).
3. Images come from GHCR, pinned by version or digest. A read-only check on 2026-10-27 found
   no running container on `:latest`. A Kyverno policy against `:latest` is still audit-only.
4. Secrets are SealedSecrets beside their workload. Never `kubectl create secret` by hand.
5. Every workload needs requests and limits. Stateful claims use a "retain" storage class.
6. New services follow a checklist: pinned image, manifests with limits, an Argo Application,
   a SealedSecret, an ingress class choice (public Cloudflare-restricted or tailnet-only), a
   backup decision, a stack-inventory row and NATS subjects that follow the grammar.

**CI**: YAML lint, ShellCheck, Terraform fmt/validate,
kubeconform, `helm template` on changed charts, and gitleaks (secret scanning against a baseline).
Actions are pinned by commit SHA. Renovate proposes weekly updates.

**GitOps gaps** [Verified 2026-10-17/27]: of 11 Helm releases first installed by hand, 8 were
adopted into Argo. **NATS, TAK Server core and Argo CD itself remained Helm-CLI.** The TAK core
gained partial Argo ownership on 2026-10-26. "The most important workload has no reproducible
rebuild path" was the review's verdict on TAK before that work. A bootstrap script
still upgrades the Helm releases imperatively and must not be run.

### 4.2 Platform layers and AI trust model

| Layer | Contents | AI may |
|---|---|---|
| 3. Apps | Software OneMind writes or runs as products | See and act (restart, scale, roll back) |
| 2. Shared services | Data, messaging, AI plumbing, observability | See, and propose PRs |
| 1. Foundation | Login, reach, secure, back up, rebuild (Argo, Authentik, Tailscale, cert-manager, Velero, policy, portal) | See only; may draft a PR; a human merges |
| 0. Kubernetes | Provider-managed system namespaces, CNI | See only |

Rule: "the thing that fixes problems must not depend on the thing it is fixing."
AI read access uses a dedicated read-only ServiceAccount (built-in `view` plus platform CRDs,
no Secrets) through a read-only Kubernetes MCP server, plus a read-only Backstage MCP.

### 4.3 Roadmap direction for app delivery

- **ADR 0002** (selected target, implementation pending, 2026-10-21): Backstage request or
  authenticated agent, then a reviewed Git PR, then Argo CD, then **KubeVela** (app lifecycle)
  and **Crossplane** (app infrastructure). Terraform keeps clusters/network. NATS carries
  events and projections, "not another desired-state writer". One owner per resource and field.
  KubeVela and Crossplane are **not installed**.
- OpenChoreo was piloted (Phases 2 to 5 done), then retired on 2026-10-23.

### 4.4 Backstage: what it does

Custom Backstage 1.55.3 app ("OneMind"), about 27 OneMind plugins (home, nav, theme,
live operations, missions, services, systems, radar, offline, assistant, permissions,
inventory, events, cost and others). Signed in through Authentik, tailnet-only.

- Catalog of services, systems and resources grouped by the four pillar Domains.
- **Flagship program** (owner request, 2026-10-21): make Backstage "the single front door for
  every OneMind service, Kubernetes and non-Kubernetes", with live problems in real time,
  DigitalOcean at a glance, and add/remove app lifecycle. Waves 1 and 2 shipped 2026-10-22:
  theme, grouped navigation, pillar Domains, alert/notification triage, Live Operations
  (Alertmanager, Argo, workloads, storage, backups), a standard app page with Logs/Cost/Runbook
  tabs, live inventory (175 workloads tracked) [Verified 2026-10-22].
- Still open then: DigitalOcean view, non-Kubernetes apps and health checks, add/retire
  templates, plugin pack, cleanup of a
  7,750-item notification backlog.

### 4.5 Why Backstage is "not deep enough" as the front door

The founder's judgment that Backstage is not deep enough is recorded in the conversation, not
in the repo. The repo's own evidence explains it:

1. **It is a developer/service catalog, not an operations surface.** The 2026-10-08 workspace
   review: "TAK, device actions, mobile/offline and app AI access require integrations." The
   mission explicitly rejects "a directory of links" and "a periodically refreshed inventory".
2. **The signed-in review (2026-10-21) found the reality of a link directory:** 130 directory
   chips in 25 categories, about 70 Systems in three naming schemes, about 280 hash-suffixed
   Resources, only 6 of 69 Argo apps linked to a catalog entity, an empty cost page,
   7,750 unread notifications (every Argo sync success became one), unrequested GitHub
   OAuth pop-ups. Most were fixed by bespoke plugin work, which shows the cost of depth.
3. **Every operational capability is custom code.** Live ops, missions, offline, radar and the
   assistant are all OneMind-written plugins. Backstage provides the frame, not the behavior.
4. **No physical-world, device or hardware layer.** It cannot onboard a robot by QR, show a
   mesh, run on a Pi, or work disconnected. It lives in the cloud cluster, behind the tailnet.
5. **Web only.** No native mobile, desktop, XR or field client. TAK clients remain separate.
6. **Upgrade and maintenance burden.** A pinned plugin cohort, a private access-control adapter
   and a release pipeline per portal image. ADR 0001 itself warns that installing a plugin
   "does not create API contracts, billing inputs, workflow engines or recovery evidence".
7. **It sits above the cluster rather than owning the machine.** It cannot provide updates,
   rollback, hardware detection, backups or first-boot onboarding. Those are OS concerns.

The repo's own 2026-10-08 recommendation was already "Backstage stays the developer/service
workspace; a OneMind operational API/gateway supplies live snapshots, deltas, permission
checks and command results; one product with Today, Operations, Agents, Apps and Build views."

---

## 5. NATS subject doctrine (summary)

Source: the repo's NATS doctrine document (binding canon) and the "locked" grammar block in the repo's
agent-context file. "Never create a new NATS subject pattern outside the grammar."

**Why NATS:** one substrate replaces six (pub/sub, request/reply, durable streams, KV, object
store, service discovery). The same binary runs on a cloud VM, a Mac and a Pi Zero, which
matches the target fleet (house, barn and office nodes; target "hundreds").
"Anything that can't speak NATS gets a bridge."

**Grammar:**

```
tel.{node}.{class}.{metric}          telemetry            tel.drone.x47.position
det.{domain}.{type}.{id}             detections           det.air.visual.track42
evt.{domain}.{entity}.{event}        events (past tense)  evt.so.task.created
cmd.{domain}.{entity}.{action}       commands             cmd.le.light.on
intel.{domain}.{source}.{type}       intelligence         intel.conflict.acled.event
ent.{entity_type}.{entity_id}.state  fused entity state   ent.ship.mmsi123.state
svc.{service}.{endpoint}             NATS RPC             svc.hermes.query
agents.{verb}.{agent}.{owner}.*      agent fabric (Synadia Agent Protocol v0.3, verb-first)
$SRV.PING.agents / $SRV.INFO.agents  agent discovery (never hardcode a roster)
tak.cot.inject / tak.cot.>           CoT into / out of TAK Server
```

- **Domains** map to the pillars: `so`, `hp`, `le`, `ge`, plus `sys` for infrastructure.
- Events are immutable facts; commands may be rejected; never publish a command as an event.
- Design so wildcard filters do the work. More than 300 disjoint filters per consumer means
  the hierarchy is wrong.
- **JetStream rules:** idempotent consumer create; stay far under 100K consumers; republish and
  Direct Get instead of per-device consumers; decide backpressure per stream at design time.
- **Edge patterns:** consume (core pulls a subset), mirror (1:1 replica for audit/DR), merge
  (many edges into one core stream). Each site node runs a leaf with local JetStream;
  store-and-forward at the leaf instead of client retries.
- **Security model:** accounts as security domains (planned SYS, CORE, FABRIC, INTERFACE);
  config-based auth now, operator/JWT mode when the fleet passes about 20 nodes or the first
  non-family device class; auth callout for external identity later.
- **Agent doctrine (locked):** "The harness owns its config. The app never does." No shadow
  configs, no app-side agent database. Discovery by `$SRV.PING.agents` sweeps.
- **Geo-envelope (TACMAP, locked):** every positioned thing publishes a standard JSON envelope
  (`uid`, `type`, `lat`, `lon`, `hae`, `course`, `speed`, `callsign`, `stale`, `t` epoch ms,
  `meta`) on `tel.fleet.{class}.{id}.position` (inner ring: drone, robot, vehicle, node, edge,
  agent, aircraft, vessel) or `evt.world.*` (outer ring: air, sea, conflict, fire, seismic,
  chokepoints, news). "Zero map-code changes" to add an asset class. Agents drive the map
  through `cmd.map.>`; ClickHouse records every geo subject for replay.
- **Open decision §9.8:** live TAK traffic uses `tak.cot.out` / `tak.cot.inject` (stream `COT`),
  while the doctrine's `evt.tak.cot.{uid}` stream (`GEO`) is empty. Proposed: ratify the raw
  wire and add a normalizer projection.
- **Synadia reuse map:** use the open-source NEX (workloads to fleet nodes over the bus),
  Connect/Wombat (bridges), Orbit client libraries, auth callout and the Agent SDK. Replicate the
  closed Control Plane and Insights on public APIs. No Synadia Cloud (sovereignty).
- **Bus authority:** the 3-node in-cluster NATS is the authority. Edge and Mac bridges run a
  local leaf that forwards to it over Tailscale (leaf = forwarding pipe). "When the home server
  arrives, it becomes another leaf (and eventually the authority)."

---

## 6. Agents, MCP and onemind-core

- **Hermes "Legacy"**: the founder's primary agent, built on the
  Nous Research hermes-agent. Designed as one identity with several bodies (cloud pod plus a Mac
  body) on the same Agent Protocol subject, so NATS queue groups route prompts to whichever body
  is alive. Has souls/personas, an agent registry, a doctrine ("Legacy is the
  mother; servant agents defer"), a runbook, a vision plugin and a read-only cluster-observer
  identity. Model provider is chosen at runtime; model-provider credentials are managed via
  SealedSecrets. Known issues: an OOM at its memory
  limit (2026-10-09); runs as a single replica. An independent "fresh" Hermes is being prepared
  beside it.
- **OneMind MCP**: Python, official MCP SDK, Streamable HTTP. Four
  read tools (`apps_list`, `nats_server_stats`, `nats_jetstream_stats`, `prometheus_query`) plus
  an `onemind://apps` resource. Authenticated, anonymous access rejected, no Kubernetes write
  privileges. [Verified 2026-10-27]
- **Read-only operator MCPs:** Backstage MCP (catalog queries, runbooks, health) and a Kubernetes
  MCP server in read-only mode, used by Claude Code on the Mac (Phase 1, done).
- **onemind-core**: Python API with PostgreSQL for requests,
  idempotency keys and results; versioned Dapr workflows; capabilities to inspect infrastructure,
  summarize evidence through LiteLLM, delegate to a discovered agent and request restarts of
  designated workers. Bearer credentials; read credentials cannot mutate. Build exists;
  activation is not claimed.
- **Bridges** (Go, Apache-2.0): one standard contract (subject pattern,
  envelope, process interface) with bridges for MAVLink (drones/autopilots), TAK mesh,
  Home Assistant, MQTT and webhooks, a bridge template and JSON schemas (air position/attitude/
  battery, ground telemetry, home sensor/event, CoT, webhook).
- **Other agent surfaces:** Paperclip (business agents), n8n (workflows), Agent Console.

---

## 7. TAK / CloudTAK and the ADRs

- **TAK Server 5.8** on OneMind hardened images. EUDs (ATAK/iTAK) enroll through the TAK portal.
  Backed up by a verified PostgreSQL dump (restore-checked) and VolSync copies of its volumes.
- **NatsBridgePlugin:** CoT in on `tak.cot.inject`, out on `tak.cot.out`. Alert
  `TAKCoTFlowStopped` watches the stream.
- **CloudTAK:** live browser client [Verified 2026-10-25].
- **ADR 0001 (accepted):** use established Backstage plugins before custom integrations; keep
  Authentik as IdP, Tailscale as private transport and GitOps as the deployment path.
- **ADR 0002 (selected, pending):** Backstage, Git, Argo CD, KubeVela, Crossplane (section 4.3).
- **ADR 0003 (first slice implemented, 2026-10-29), "commo is the key":** OneMind speaks native
  TAK. Edge nodes join the TAK mesh as peers (UDP multicast SA, TCP directed messages, TAK
  Protocol XML v0 and protobuf v1) so mesh traffic works when cloud and TAK Server are down.
  The bus stays the authority. OneMind clients are TAK-kernel clients (ATAK, iTAK, TAKX
  desktop, a OneMind build of VR-TAK for XR); CloudTAK for browsers. The gateway codec was
  written from the wire spec, so no GPL code is copied. Next slices: an entity service
  ("Make Sense") publishing `ent.*.state`, fleet positions projected into CoT, a GPL-3.0
  OneMind XR fork of VR-TAK (Unreal 5.3.2, Windows build host), TAKX for desktop. Note:
  building `takkernel` needs tak.gov artifact credentials.

---

## 8. Identity and access

- **Authentik** is the IdP for the portal, Argo CD (group-based admin), OpenChoreo (when it ran),
  Karakeep and other apps. PostgreSQL + Redis, nightly encrypted dump and VolSync copy. An LDAP
  outpost for TAK is a separate item.
- **Tailscale** is the private transport for admin access and TAK. Tailscale ACLs are managed
  from Git through CI. Admin UIs are tailnet-only; public exposure is deliberate and
  Cloudflare-restricted.
- **Authorization:** OpenFGA deployed; Kyverno policy guardrails (layer labels and image tags
  enforced, the rest audit); NATS accounts planned.
- Security gaps identified in the October 2026 review are tracked privately in the infrastructure repo.

---

## 9. Observability and alerting

- **Stack:** kube-prometheus-stack (Prometheus, Alertmanager, Grafana), Loki, Tempo,
  OpenTelemetry collector, nats-surveyor, a per-leaf NATS exporter, OpenCost, Hubble.
  Grafana dashboards for NATS, logs, services and workloads; Prometheus rules for NATS leaf
  nodes, TAK and OneMind workloads; Falco events forwarded to Alertmanager.
- **Lesson:** Alert delivery, off-site backups and full-rebuild drills were gaps in the cloud
  deployment — OneMind OS must make them built-in (see ADR-001).
- NATS alerting initially covered only "down / quorum lost", not CoT flow or consumer lag
  (since partly addressed by `TAKCoTFlowStopped` and leaf metrics).
- `health-keeper` observes the cluster every 5 minutes (read-only).
- The portal's notification policy (Argo failures, degraded apps, failed backups,
  Alertmanager severities, daily digest) is implemented in source.

---

## 10. Backups and recovery

| Mechanism | What | Status |
|---|---|---|
| Logical PostgreSQL dumps | TAK, Authentik, Backstage, n8n, TAK-ML, Matrix and others. Each run encrypts, uploads, downloads again, checks integrity and restores into an isolated scratch database before writing a "verified" marker | TAK and NATS first verified 2026-10-09 [Verified] |
| NATS stream archive | All 39 streams, restore-verified in a disposable server | [Verified 2026-10-09] |
| VolSync (restic) | 46 PVC sources to object storage | All "Successful" at last check [Verified ~2026-10-09] |
| Velero | Daily namespace backups for core, data and AI namespaces, 30-day retention | [Documented] |
| CNPG Barman | Continuous PostgreSQL backup | [Documented]; a CNPG restore drill exists (2026-10-09) |
| Cluster recovery export | Daily encrypted export of identity/config and active SealedSecrets keys | Verification is decrypt/equality only, "not replay onto a new cluster" |
| App restores | Vaultwarden, Karakeep, STAC, ClickHouse restores tested in isolation | [Verified 2026-10-25] |

**Lesson:** see section 9 (off-site backups and rebuild drills were gaps). A rebuild-from-zero
procedure is documented in the repo: restore keys, bootstrap, restore to new PVCs, recover
identity first, test with WAN disconnected, then cut over.

---

## 11. Edge and leaf nodes

- **Mac leaf** (reference copy, not deployed from Git): a full NATS
  server with JetStream on the founder's laptop, leaf-connected to the cluster over Tailscale,
  plus a NEX node running local workloads (streaming bridge, auth callout, HTTP gateway,
  MAVLink bridge, other bridges) under launchd. If the Mac is offline, the cloud bus keeps
  running.
- **Edge TAK Server**: docker-compose deployment, device manifests
  and loadouts for EUDs, Murmur voice config. Reference material.
- **Home cluster plan**: start with **k3s on Ubuntu
  Server LTS or Debian**, 1 node designed for 3; `local-path` storage on NVMe, Longhorn at 3 nodes;
  UPS mandatory, dual WAN recommended; Tailscale plus Cloudflare Tunnel; Cilium for parity;
  etcd snapshots to S3. Revisit **Talos** at 3 nodes. Avoid k3s-only features in Git so the
  distribution can change. Dormant draft PRs explore k3s with Rook, Forgejo, Tekton, Akri, Envoy,
  and separately GPU serving, OCM and Crossplane.
- **Workspace review placement** (2026-10-08): home core (primary apps, identity, event hub,
  inference), building gateways (sensors, deterministic local rules), tactical edge (independent
  small bus and maps), cloud (public, relay, recovery). Independent clusters at disconnected sites;
  no internet-spanning control-plane quorum. K3s for gateways; KubeEdge to evaluate.
- **GPU:** none in the cluster. "No GPU is requested" in the ecosystem pool. ML compute (Kueue,
  KServe, GPU/ARM64 compatibility) is a future planning item (K10). Ollama runs on CPU.
- **Architecture caveat:** several custom images are amd64-only. Verify every digest on ARM before
  choosing ARM hardware.

---

## 12. Roadmap phases and status (as of 2026-10-27)

| Phase | Goal | Status |
|---|---|---|
| 0 | Blueprint (layers, namespace map) | Done |
| 1 | Claude sees every layer (read-only MCPs) | Done |
| 2 | OpenChoreo foundations | Done (then retired) |
| 3 | Pilot one app as an OpenChoreo component | Done (then retired) |
| 4 | Portal refactor into plugin packages | Done |
| 5 | Capacity fixes, then observability | Done |
| 6 | One portal | In progress |
| 7 | Migrate Layer-3 apps project by project | Not started |
| 8 | Expand: home server data plane, Hermes on the same tools | Not started (only the OneMind MCP slice delivered) |

Decision log highlights: Argo CD stays the GitOps engine; LiteLLM stays the model gateway;
read-only AI ServiceAccount; KubeVela + Crossplane selected as target (2026-10-21); OpenChoreo,
OpenSearch and External Secrets retired (2026-10-23).

---

## 13. Known gaps and risks

1. **Cloud-dependent.** Everything runs in one cloud deployment. The mission says home must
   be primary; no home node exists yet.
2. **Alerting, off-site backups and rebuild drills** were gaps; see the lesson in section 9.
3. **Non-reproducible foundations:** NATS and Argo CD are Helm-CLI releases; NATS has two owners;
   TAK only partly adopted; Terraform does not match live.
4. **Single points of failure:** TAK components, Authentik, ingress-nginx, cert-manager and
   Hermes ran 1 replica at review.
5. **Capacity:** hub-core memory requests at 71% to 96% per node (2026-10-27) while CPU idles.
6. **Doc drift:** dated documents disagree with live state (the repo warns about this itself);
   NATS doctrine vs live TAK subjects (§9.8).
7. **Operational complexity:** about 60 to 70 Applications, many controllers, frequent
   adopt/retire cycles (OpenChoreo installed then retired within a week).
8. **No GPU, no ARM validation, no real-time control path.** Robotics/drone work so far is a
   MAVLink bridge and doctrine, not hardware in the loop.
9. **Portal depth** (section 4.5).

---

## 14. What this proves for OneMind OS

### 14.1 What works (keep)

- **NATS as the spine** (bus, KV, streams, RPC, agent discovery), with a locked subject grammar,
  the geo-envelope and leaf-node edge patterns. It has run in production on a 3-node JetStream
  cluster with verified stream backups.
- **GitOps discipline:** everything in Git, pinned charts and digests, SealedSecrets, CI with
  secret scanning, one owner per resource. Argo CD is proven at about 60 to 70 apps.
- **Backups that restore-verify themselves** before claiming success.
- **Identity + private transport:** Authentik OIDC everywhere, Tailscale for admin and TAK,
  public exposure only by deliberate choice.
- **The AI trust model:** layered permissions, read-only by default, humans merge foundation
  changes, MCP servers with narrow tools.
- **TAK as the tactical display,** including a mesh-native gateway that works without the cloud.
- **Standard bridge contract** for drones (MAVLink), home automation, MQTT and webhooks.

### 14.2 What must change for an appliance OS

| Cloud cluster today | Appliance OS needs |
|---|---|
| Managed control plane, provider storage, LBs, object store | k3s/RKE2 (or similar) on the box; local storage; local S3 (MinIO/Garage) plus an off-box target |
| Operator runs `kubectl`, Helm, Argo by hand | First-boot onboarding, a curated app store, updates the user controls, atomic A/B OS updates with rollback |
| Backstage web portal on the tailnet | A native, offline-capable app shell (web, mobile, desktop, XR) with Simple and Pro modes |
| amd64 cloud nodes, no GPU | x86 and ARM64 builds, NVIDIA Jetson/GPU flavors, hardware auto-detection |
| Operator-run cluster | Multi-user household, parental controls, roles, device enrollment by QR |
| Alert delivery was a gap | A native alert system that reaches people on day one (push, local, mesh) |
| About 70 apps and many controllers | A small, opinionated core with optional modules sized for 8 GB boxes up to large GPU nodes |
| Cloud is primary | Home box is primary and survives WAN loss; cloud becomes an optional relay and backup |
| Secrets sealed against one cluster's key | Per-device keys, TPM/Secure Boot later, a recovery-key story ordinary users can follow |

### 14.3 What can be ported directly

- **Helm charts and Argo Applications** for NATS, Authentik, TAK Server, CloudNativePG, the
  monitoring stack, n8n, Nextcloud, Vaultwarden and others. They are plain Kubernetes; only
  storage-class, load-balancer and node-label overlays change.
- **NATS contracts:** subject grammar, stream/KV CRs, the geo-envelope, Agent Protocol subjects.
  They become the OS's internal API between apps, agents and devices.
- **MCP servers** (OneMind MCP, read-only Kubernetes MCP, Backstage MCP pattern) as the template
  for "every app is readable by AI with permissions".
- **Bridges** (MAVLink, TAK mesh, Home Assistant, MQTT, webhook) as OS-level device adapters.
- **Backup jobs** (encrypt, upload, re-download, verify, restore into scratch) as the OS backup
  engine design.
- **The trust model and Kyverno/OpenFGA policy approach** as the basis for app and agent permissions.
- **Hermes / Legacy and onemind-core** as the agent layer and operational API.
- **The existing cluster itself** as the "Omni"/cloud tier and the reference deployment
  while the home appliance is built. The prior session's ADR-001 draft claimed the DOKS cluster
  can convert to k3s "with three changes"; the research agent should verify that claim against
  the repo's DigitalOcean lock-in document, which lists 13 dependencies.

### 14.4 Questions this raises for the research

1. Which parts of the 60 to 70 app stack form the minimal OS core, and which become optional modules?
2. Can Argo CD stay on a small box (memory), or does the appliance need a lighter reconciler
   (k3s Helm controller, Flux, Fleet) while Argo remains for the cloud and multi-site tier?
3. How does NATS leaf/hub topology change when the home box becomes the authority and the cloud
   becomes a leaf?
4. What is the identity story offline (Authentik on the box, or something lighter), and how do
   NATS accounts map to household users and devices?
5. Should Backstage survive at all in the appliance, as the Pro/developer view only, or be replaced?
6. What is the real-time control boundary for drones and robots (ROS 2, PX4, MAVLink) outside Kubernetes?