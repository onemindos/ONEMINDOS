# Olares (beclab/Olares) - Competitor Teardown for OneMind OS

Research date: 2026-11-10. Method: official site, docs (which live in the repo under `docs/`, built with VitePress), GitHub repo files via `gh api`, release list, and the Olares app-market repo. Anything I could not open is marked **UNVERIFIED**. No code was cloned or executed.

Repo paths below are relative to https://github.com/beclab/Olares (main branch as of 2026-11-10) unless stated otherwise.

---

## 0. Key facts table

| Item | Fact | Source |
|---|---|---|
| What it is | "Open-source personal cloud OS you operate in plain language, built to run AI agents and LLMs on hardware you own", "Powered by Kubernetes" | https://github.com/beclab/Olares (README) |
| Repo stats (2026-11-10) | 5,356 stars, 335 forks, primary language Go, created 2024-04-29, ~3,996 commits, pushed same day | `gh repo view beclab/Olares`; commits page count from `gh api repos/beclab/Olares/commits?per_page=1` Link header |
| Language mix (bytes) | Go 20.2M, Vue 4.9M, TypeScript 3.8M, JS 1.3M, Shell 0.25M, Python 0.14M | `gh api repos/beclab/Olares/languages` |
| Latest stable | 1.12.7 (2026-09-24). Pre-releases 1.12.8-rc.1 (2026-11-10) and nightly-style `1.12.9-YYYYMMDD` tags daily | `gh release list -R beclab/Olares` |
| Stable cadence | 1.12.0 2025-08-06; 1.12.1 2025-09-24; 1.12.2 2025-11-06; 1.12.3 2026-01-09; 1.12.4 2026-01-20; 1.12.5 2026-03-26; 1.12.6 2026-07-16; 1.12.7 2026-09-24 (about one stable every 1-2.5 months, slowing in 2026) | `gh api repos/beclab/Olares/releases` |
| License (GitHub-detected, LICENSE) | GNU AGPL v3. Changed to AGPLv3 in commit "Change to GNU Affero General Public License v3 (#1770)" on 2025-08-30 | `gh api repos/beclab/Olares --jq .license`; commit history of `LICENSE` |
| License caveat | Legacy `LICENSE.md` ("Olares License", non-commercial / internal-use only, no commercial redistribution) still sits in repo root and in `apps/packages/core/LICENSE.md`. Conflicting signals. See section 7. | https://github.com/beclab/Olares/blob/main/LICENSE.md |
| Company | Olares Tech Co., Ltd., founded 2022, HQ Singapore, raised "more than $100 million" including a Series A led by SIG (company press release). GitHub org is "BEC Lab" (beclab), location Singapore | https://www.prnewswire.com/news-releases/olares-showcases-private-ai-at-intels-ai-nas--thunderbolt-technology-forum-in-japan-302909516.html ; `gh api orgs/beclab` |
| Kubernetes | k3s by default (Kubernetes optional; minikube on macOS) | `docs/developer/concepts/system-architecture.md` |
| Container runtime | containerd + runc | `infrastructure/README.md` |
| Storage | Local (default single-node), S3, MinIO; JuiceFS for multi-node; OpenEBS | system-architecture.md; `platform/README.md`; `infrastructure/README.md` |
| DB/middleware | PostgreSQL 16 (shared, per-app accounts; also FTS + vectors via pg_vectors; Citus for multi-node, "production readiness still under evaluation"), KVRocks (Redis-compatible), NATS, MongoDB, Argo Workflows, Prometheus, OpenTelemetry (eBPF, "in development"), KubeBlocks | system-architecture.md; `platform/` dir listing |
| Identity | LLDAP (LDAP) + Authelia (MFA, SSO) | system-architecture.md |
| Networking | CoreDNS, Calico, Envoy sidecar, Tailscale client + self-hosted Headscale, Cloudflare Tunnel / Olares Tunnel / FRP reverse proxy | system-architecture.md; `framework/README.md` |
| GPU sharing | NVIDIA only in the install docs; time-slice / memory-slice / exclusive modes; repo ships a Olares-maintained fork of HAMi (CNCF sandbox). Older doc text still says nvshare. | `infrastructure/gpu/README.md`; `docs/manual/olares/settings/gpu-resource.md` |
| App format | Olares Application Chart (OAC): a Helm chart plus `OlaresManifest.yaml` | https://github.com/beclab/apps README |
| Market repo | github.com/beclab/apps (Apache-2.0), 57 stars, 404 app folders (many are model/variant/client/shared packages, not distinct products); marketing says "200+ apps" | `gh api repos/beclab/apps/contents`; PR release above |
| Hardware | Olares One: Intel Core Ultra 9 275HX, RTX 5090 Mobile 24GB GDDR7, 96GB DDR5-5600, 2TB NVMe, TB5, 2.5GbE, Wi-Fi 7, BT 5.4, 330W, 320x197x55mm, 2.15kg (3.1kg with PSU) | https://www.olares.com/docs/one/spec ; https://www.olares.com/one |
| Price | $4,999 on the official Shopify store (HTML shows `"price":"4999.00"`, `available:true`); site advertises Black Friday from Nov 17, "Save $300 per unit". Kickstarter launch price was reported as $2,999. | https://shop.olares.com/products/olares-one ; https://www.olares.com/one ; https://siliconangle.com/2025/12/09/olares-launches-personal-ai-computer-turns-local-files-smart-assistant/ |
| Kickstarter | $2.34M raised, January 2026; company says all backer orders fulfilled | Oct 2026 press release (prnewswire link above) |
| Min specs (BYO hardware) | 4 cores, 8GB RAM, 150GB SSD (HDD install fails), Ubuntu 22.04-25.04 or Debian 12/13, optional NVIDIA Turing+ | https://github.com/beclab/Olares README; `docs/manual/get-started/install-olares.md` |
| Website | olares.com: Vue SPA (hashed `/assets/app-*.js`, `data-v-*` scoped styles) behind Cloudflare; docs: VitePress 1.6.4 | `curl -I https://www.olares.com/`; `docs/package.json` |

---

## 1. Architecture layers (reverse-engineered from the repo)

Olares markets five layers (https://www.olares.com/os): Infrastructure (Kubernetes), Platform, Framework, Built-in apps, Community apps. The repo top level maps directly to this: `infrastructure/`, `platform/`, `framework/`, `apps/`, plus `cli/`, `daemon/`, `vendor/`, `build/`. README describes it as an open-source mirror of the IaaS/PaaS/SaaS public-cloud stack.

### 1.1 Infrastructure layer (`infrastructure/`)
Directory contents (from `infrastructure/README.md`): kubernetes, **k3s**, minikube, apparmor, **calico**, cni, conntrack, socat, **coredns**, **openebs**, **containerd**, runc, cri-tools, **etcd**, cuda, gpu, **helm**, **kubesphere**, **minio**, restic, plus `generic-device-plugin`.

- Distribution: docs say Linux (incl. WSL, PVE, LXC, Raspberry Pi) can use Kubernetes or K3s, "with K3s being the default"; macOS uses minikube in a VM. Olares One's cluster output showed `v1.33.3+k3s1`. (docs/one/connect-two-olares-one.md)
- Container runtime: containerd (+ runc). 
- Helm: "The application management framework in Olares is built on top of Helm."
- KubeSphere: used as a management layer; "some parts of the user management component and the monitoring stack is based on KubeSphere" (a forked KubeSphere tree is vendored at `infrastructure/kubesphere/staging/...`).
- Storage: local by default; S3; MinIO ("When deploying Olares as a distributed service across different machines, MinIO is used as the data storage backend for JuiceFS"); OpenEBS for block storage; restic for backups.
- GPU: `cuda` (driver stack installed automatically when an NVIDIA GPU is detected), `gpu` (README: "Olares maintains its own fork of HAMi to enable users to manage GPU resources across different applications"), `generic-device-plugin`. The architecture doc still says "nvshare" and "Olares GPU support is restricted to deployments with one GPU per node" - this doc text is older than the HAMi fork; treat as partly stale. The current GPU doc (`docs/manual/olares/settings/gpu-resource.md`) describes **Time slice / Memory slice / Exclusive** modes and lists resource types NVIDIA, NVIDIA GB10 (DGX Spark), Apple M-series, AMD Strix Halo, CPU fallback ("AMD GPU and AMD APU devices are not covered in this version").
- Control tools: `olares-cli` (Go, `cli/`) and `olaresd` (daemon in `daemon/`) which "monitors hardware and network changes, while also managing cluster upgrades, restarts".
- Intel support: org also forks `intel-device-plugins-for-kubernetes`, `llm-scaler`, and `vllm` (https://github.com/beclab, repo list). Purpose is not stated in what I read; likely Intel GPU/AI-NAS support (**UNVERIFIED** inference; the Oct 2026 press release does target Intel Core Ultra systems).

### 1.2 Platform layer (`platform/`)
Directory listing: argo, fs-lib, hami, juicefs, kubeblocks, nats, open-policy-agent, open-telemetry, postgresql (citus, pg_vectors), prometheus, redis (kvrocks, predixy, redis-cluster-operator), tapr, velero. (The README also lists mongodb.)

- PostgreSQL 16 shared instance, "each having dedicated accounts for isolation"; also FTS + vector DB; Citus for multi-node.
- KVRocks (Redis-compatible on RocksDB) instead of Redis.
- NATS as messaging.
- JuiceFS for POSIX shared FS across nodes (needs S3/MinIO backend).
- Argo Workflows (used by Olares recommendation engine; "not available to third-party applications").
- Secrets: Vault (own app, based on Padloc) and Infisical.
- **tapr**: "Provides the app run time for Olares. Bundles a curated set of sidecars and Kubernetes operators to solve the 'boring but critical' plumbing required by most self-hosted apps - file uploads, secret storage, event streaming, WebSockets, and turnkey data services." This is the middleware provisioning layer apps request via the manifest.
- KubeBlocks (operators for DBs) and open-policy-agent are present; exact use of OPA **UNVERIFIED** (not read).
- NATS is present as platform messaging. Note: NATS is also OneMind's bus; same choice.

### 1.3 Framework layer (`framework/`)
From `framework/README.md`: app-service, authelia, backup-server, bfl, docker-nginx-headers-more, files, headscale, infisical, kube-state-metrics, l4-bfl-proxy, market, monitor, notifications, osnode-init, reverse-proxy, seahub, search3, system-server, upgrade, vault. Additional dirs in the tree: `app-gateway`, `cm-sidecar`, `integration`, `oac`, `timeoutprofile`.

- **app-service**: app lifecycle and resource allocation. Go + controller-runtime. Packages include `appinstaller`, `applifecycle`, `helm`, `middlewareinstaller`, `workflowinstaller`, `sandbox`, `security`, `webhook`, `tapr`, `kubesphere`, `prometheus`, `compute`, `podhealth`.
- **system-server**: "Manages permissions for inter-application API calls and handles network routing between applications and database middlewares."
- **bfl** ("Backend For Launcher"): aggregates backend interfaces and proxies requests for all system services; per-user.
- **app-gateway**: newer component; contains `linkerdpki` in `pkg/` and app-service has `pkg/security/shared_linkerd_mesh.go`, implying a Linkerd mesh for some traffic. Docs still say Envoy; the repo suggests both. The exact current data-plane split is **UNVERIFIED**.
- **authelia** + LLDAP: SSO, MFA, unified account.
- **headscale** (self-hosted Tailscale control server) + Tailscale clients; **reverse-proxy**: "Cloudflare Tunnel, Olares Tunnel, and self-built FRP."
- **files** + **seahub** (Seafile web frontend; Seafile deeply integrated for sync), **search3** (full-text search for Knowledge and Files), drive server for external clouds, media server with ffmpeg.
- **market**: "A decentralized and permissionless app store".
- **backup-server**: directory/app/cluster backups. **upgrade**: automated system upgrades. **notifications**.
- **oac**: Go library/linter for Olares Application Charts (see section 3).

### 1.4 Isolation and sandbox model (from docs and code)
From `docs/developer/concepts/network.md`:
- Three entrance types: **public** (no auth, "basic security through Cloudflare"), **private** (authentication required), **internal** (no auth when reached through LarePass VPN).
- URL scheme `https://{routeID}.{domain}` e.g. `vault.alice123.olares.com`. System apps get fixed route IDs; community apps get an 8-char random ID + entrance index.
- Layered proxy routing: `cluster -> user -> application -> service component`.
- Namespace isolation per app; apps cannot bind ClusterRole to ServiceAccount; no cross-namespace access.
- Network policy per namespace; incoming requests limited to the user's cluster/system apps; apps isolated between users.
- Pod restrictions: no `hostNetwork`, no `NodePort`; traffic only via declared entrance and system-provided proxy. "The Pod declared as entrance will be forced to join Envoy's sandbox Sidecar to authenticate and authorize incoming traffic."
- Resource limits: chart lint rejects containers without CPU/memory limits (`cli/skills/olares-chart/references/olares-chart-lint.md`, `framework/oac/README.md` section 3.1). Runtime protection: `framework/app-service/controllers/pod_abnormal_suspend_app_controller.go` suspends an app when a Pod is Evicted or stays Pending/Unschedulable past a timeout (default 3 min), and `pkg/appwatchers/suspend.go` suspends the "top application" when cluster CPU/memory exceeds `CLUSTER_CPU_THRESHOLD` / `CLUSTER_MEMORY_THRESHOLD` (annotation `bytetrade.io/suspend-by`). So the "auto-stop under resource pressure" claim is real, in code.
- Identity chain: Olares ID (email-like, bound to a DID; DID metadata registered via smart contracts on an Ethereum L2 optimistic rollup, `docs/developer/concepts/registry.md`) -> LarePass holds keys -> Authelia authenticates each request.

### 1.5 Control plane naming
Cluster CRD is literally named `terminus` (`kubectl patch terminus terminus ...` in the upgrade guide), and the Android app id is `com.terminus.termipass`. This is residue of an earlier product name (Terminus / TermiPass). Rename history itself is **UNVERIFIED** (not seen in a source I opened); only the identifiers are verified.

---

## 2. Built-in apps

Sources: https://www.olares.com/os, `docs/manual/olares/index.md`, `docs/developer/concepts/system-architecture.md`, `apps/packages/` tree.

| App | What it does | Tech notes |
|---|---|---|
| **Desktop** | Main interface. Dock on left, Launchpad, windowed apps embedded in the page, widgets, global search and notifications | Frontend in `apps/packages/app` (Vue 3 + Quasar 2 + Pinia per package.json). Backed by `bfl` |
| **Files** | File mgmt/sync/share across devices; local files, synced data, connected cloud storage, SMB/NFS mounts, backups | Backed by `framework/files`, Seafile (`seahub`), drive/media servers |
| **Vault** | Password/secret manager, 2FA/OTP, autofill, shared vaults, end-to-end encryption claim | "developed by the Olares team based on Padloc" (apps/packages `@didvault/admin` NestJS server, `core`, `sdk`, `server`) |
| **Market** | App store; Global and China sources (`https://api.olares.com/market`, `https://api.olares.cn/market`); custom sources can be added; one-click install; custom chart install | `framework/market` |
| **Wise** | "local-first and AI-native modern reader"; collects content, runs self-hosted recommendation algorithms | Knowledge store; Argo-driven recommender (docs say partly in development) |
| **Settings** | Accounts, security, network, backup, GPU resources, custom app domain/route ID, FRP, appearance | Docs under `docs/manual/olares/settings/` |
| **Control Hub** | "no-CLI Kubernetes console": monitor workloads, containers, middleware, resources | Docs `controlhub/` (manage workload/container/middleware/resource) |
| **Dashboard** | Real-time resource usage and performance (CPU/mem/disk, etc.) | Prometheus + monitor |
| **Studio** | Dev suite to build/test/publish Olares apps in a live environment | Listed as `studio` in the apps repo; details not read |
| **Profile** | Personal homepage at `<name>.olares.com` | docs/manual/olares/profile.md |
| **LarePass** (client) | Creates/holds the Olares ID and keys, activates Olares, VPN (Tailscale-based) to the device, file/knowledge/app management from phone, autofill, 2FA, save web resources | iOS (App Store id6448082605), Android (Play `com.terminus.termipass` + APK), macOS, Windows, Linux (Beta, x86_64 only), Chrome extension (manual install). https://www.olares.com/docs/manual/larepass/ |
| **Router** (new in 1.12.7) | AI gateway: all callers hit Router, which handles auth, access control, quotas, normalizes to one API, routes to local backends (Model Console inference engines, FlowStudio, tool apps) or external providers (OpenAI, ElevenLabs, Google Vertex AI, Tavily) | `docs/use-cases/olares-router.md` |
| **Lares** (AI agent) | Official Olares assistant. Uses models via Router, built-in Olares tools/skills with selectable access level, MCP servers for app-specific actions (Blender, FlowStudio, YuE2 Studio) | `docs/use-cases/lares.md`; Lares 0.26.60 requires Olares 1.12.7+ |
| **Model Console** | Manages local LLM engines (release 1.12.6 highlights "Model Console for local LLMs") | repo beclab/model-console (AGPL-3.0) |

Data suite names on the marketing page: Sync, Browser, Ask (smart search), Store.

---

## 3. App packaging: Olares Application Chart (OAC)

### 3.1 Format
OAC "is an extension of the Helm Chart package" (https://github.com/beclab/apps README). A chart folder contains: `Chart.yaml`, `OlaresManifest.yaml` (the Olares-specific manifest), `values.yaml`, `templates/`, `i18n/`, `owners`, `.helmignore`. (Verified listing of `beclab/apps/n8n`.)

Required manifest top-level keys (from `framework/oac/README.md`, the linter spec): `olaresManifest.version` (required), `olaresManifest.type` (app), `apiVersion` (v1/v2/v3), `metadata`, `entrances` (1 to 10, unique names), `spec`, `permission`, `options`, plus `middleware`, `envs`, `ports`, `tailscale`, `sharedEntrances`, `workloadReplicas` per `docs/developer/develop/package/manifest.md`.

Validation rules include: `metadata.name` 1-30 chars, `title` 1-30, `version` valid SemVer, entrance `authLevel` one of public/private, `openMethod` default/iframe/window, policies need `uriRegex` and `level`, dependencies typed `system` or `application`. For `olaresManifest.version >= 0.12.0`, `spec.resources[]` is required (legacy flat `requiredCpu` etc. forbidden alongside it). The manifest doc instead describes `spec.accelerator[]` with modes `nvidia`, `nvidia-gb10`, `apple-m`, `strix-halo`, `intel`, `amd`, `intel-gpu`, `amd-gpu`, `cpu` (and `mthreads-m1000` in the example comment). These two docs appear to be in transition; the example n8n chart on main still uses the legacy flat fields with `olaresManifest.version: '0.12.0'`.

Helm relationship: `Chart.yaml` is standard Helm v2 chart format; templates render with `.Values` that Olares injects (e.g. `.Values.userspace.appData`, `.Values.admin`, `.Values.bfl.username`, `.Values.GPU.Type`). The linter does a Helm dry-run, collects images, checks container limits, ServiceAccount RBAC, workload naming, upload mount.

### 3.2 Permission, middleware, entrance declarations
- `permission`: `appCache`, `appData`, `appCommon` (shared across apps/nodes, e.g. models), `externalData` (NAS/external disks; off by default from 0.12.0), `userData` (list of Home subdirectories).
- `middleware`: PostgreSQL, Redis, MongoDB, MinIO, RabbitMQ, MariaDB, MySQL (docs also have Elasticsearch pages). App requests a database and receives injected credentials; `distributed: true` option exists.
- `entrances`: `name`, `host`, `port`, `title`, `icon`, `authLevel` (public/private/internal), `openMethod`.
- `options.policies`: per-URI access rules (e.g. `level: public` for `^/(webhook)` on n8n, `two_factor` example for GitLab).
- `options.dependencies`: `olares` system version range, other apps, middleware; `conflicts`; `allowedOutboundPorts`; `allowMultipleInstall`; `shared` (cluster-shared apps like Ollama, installed into `<app>-shared` namespace, `onlyAdmin: true`, apiVersion v3); `LLMGatewaySupported`; `overlayGateway` (L2 overlay LAN discovery); `oidc`; `mobileSupported`; `apiTimeout`.

### 3.3 Real example (beclab/apps `n8n/OlaresManifest.yaml`, abridged by me; stripped long marketing text)
```yaml
olaresManifest.version: '0.12.0'
olaresManifest.type: app
apiVersion: 'v3'
workloadReplicas:
  n8n: 1
metadata:
  name: n8n
  description: n8n is an extendable workflow automation tool.
  icon: https://app.cdn.olares.com/appstore/n8n/icon.png
  appid: n8n
  version: '1.1.8'
  title: n8n
  categories: [Productivity_v112, agents, workspace, homelab]
  tags: [automation]
permission:
  appData: true
  appCache: true
middleware:
  postgres:
    username: n8n
    password: n8n
    databases:
      - name: n8n
        distributed: true
spec:
  versionName: '2.40.7'
  developer: n8n
  website: https://n8n.io/
  sourceCode: https://github.com/n8n-io/n8n
  submitter: Olares
  locale: [en-US, zh-CN, de-DE, es-ES, it-IT, fr-FR, ja-JP]
  requiredMemory: 2Gi
  limitedMemory: 6Gi
  requiredDisk: 128Mi
  limitedDisk: 256Mi
  requiredCpu: 0.5
  limitedCpu: 3
  license:
    - text: Sustainable Use License
      url: https://github.com/n8n-io/n8n/blob/master/LICENSE.md
  supportArch: [amd64, arm64]
  runAsUser: true
options:
  apiTimeout: 0
  dependencies:
    - name: olares
      type: system
      version: '>=1.12.6-0'
  policies:
    - uriRegex: ^/(webhook)
      level: public
      oneTime: false
      validDuration: 3600s
      entranceName: n8n
entrances:
  - name: n8n
    port: 80
    host: n8n
    title: n8n
    icon: https://app.cdn.olares.com/appstore/n8n/icon.png
    authLevel: internal
    openMethod: window
```
Source: https://github.com/beclab/apps/blob/main/n8n/OlaresManifest.yaml and `Chart.yaml` (`apiVersion: v2`, `name: n8n`, `version: 1.1.8`, `appVersion: "2.40.7"`).

Home Assistant manifest (same repo) uses `apiVersion: v3`, categories `Lifestyle, homelab, workspace, developer`, `permission: appData/appCache`, version 2026.10.0, and the upgrade notes mention "Pin pods to control-plane (master) via nodeAffinity" and an `authLevel: internal` entrance so in-cluster apps can reach HA without SSO.

Ollama (`ollamav2`) is an `apiVersion: v2` shared app: a `sharedEntrances` block (`host: sharedentrances-ollama`, `invisible: true`, `authLevel: internal`), a client entrance `terminal`, and `options.appScope.clusterScoped: true` when the installing user is the admin; non-admin users get an app dependency on the admin's instance (Helm templating inside the manifest).

### 3.4 Market curation
- Permissionless protocol; "Olares provides a default indexing service that is based on this repository" (https://github.com/beclab/apps README). Anyone can run another market source (Settings > Market sources > Add source).
- Submission: fork, add chart, open Draft PR titled `[NEW|UPDATE|REMOVE|SUSPEND][FolderName][version]Title`, GitBot validates, owners listed in an `owners` file; one open PR per folder. Test beforehand with Studio or custom install.
- A sister repo `beclab/apps-preview` (406 entries) is for early testing before release.
- Paid apps exist (docs `developer/develop/paid-apps.md`, `market/purchase-paid-apps.md`), details not read.

### 3.5 What is actually in the market (verified against `beclab/apps` folder names, 404 folders)
Confirmed present (folder name in parentheses): Open WebUI (`openwebui`), LobeChat (`lobechat`), Perplexica (`perplexica`), Vane (`vane`), n8n, Dify (`dify`, `difyv2`, `difyv3`, `difyfusion`), OpenCode (`opencode`), DeerFlow (`deerflow`, `deerflowv2`), SearXNG, Firecrawl, ComfyUI (many variants), Hunyuan3D (several), Plane, Otmoic (`otmoiclp`, `otmoicrelay`), Whisper (many), ACE-Step (`acestep*`), Mattermost, AFFiNE, RAGFlow, AnythingLLM, Ollama (dozens of per-model packages), vLLM (`vllm*`), SGLang (`sglang*`), llama.cpp model packages, Grafana, Langfuse, Penpot, Home Assistant, plus FlowStudio, Lares, Router, Claude Code (`claudecode`), Codex (`codex`), Goose, Hermes Agent (`hermesagent`), Context7, Crawl4AI, LiteLLM, Flowise, Immich, Jellyfin, Nextcloud, GitLab, Gitea, Vaultwarden, Syncthing, Frigate, Windows/macOS VM images (`windows`, `macos`, `qemu`), Steam Headless, Palworld, Minecraft, Isaac Lab (`isaaclab`), Blender, Pterodactyl, etc. NemoClaw (`nemoclaw`), `clawdbot`, `trustgraph`, `tradingagents`.

**Not found** in `beclab/apps` or `beclab/apps-preview` folder lists (by name search; may exist under a different folder name, so treat as UNVERIFIED rather than absent): Scira, SurfSense, Void, Suna, OWL (matches were only `knowledgev3`/`prowlarr`), AgenticSeek, OpenManus, Agent TARS, Activepieces, Knative, Browser Use, Infisical-as-app, standalone Prometheus (only `prometheusclient`). Infisical is shipped as a framework component, not a market app.

Categories seen in manifests: `Productivity_v112`, `Utilities_v112`, `agents`, `workspace`, `homelab`, `developer`, `Lifestyle`, `Creativity`, `Developer Tools`. The Market UI describes categories "Agents, Models, Workspace, Homelab, and Developer" (https://www.olares.com/docs/manual/olares/market/market).

Count: 404 folders in the repo, but many are repeated variants (model-specific Ollama/vLLM/llama.cpp packages, `*client`, `*share`, `v2`/`v3` copies). The company press release says Market offers "one-click installs of 200+ apps and supported AI models". Do not read 404 as 404 distinct products.

---

## 4. Multi-node clusters

Source: https://www.olares.com/docs/one/connect-two-olares-one (repo `docs/one/connect-two-olares-one.md`) and `docs/one/upgrade-multi-node-cluster.md`.

**Roles**: one master (control-plane, also schedulable: `ROLES control-plane,master,worker`) and workers. Documented for exactly **two** Olares One units ("two-node Olares cluster"); a general Linux multi-node guide exists (`docs/manual/best-practices/install-olares-multi-node.md`, not read).

**Join procedure (verified)**:
1. Master must be activated and on **Olares 1.12.7 or later** as a single-node system. Back up first.
2. On master: `sudo olares-cli stop`, then `sudo olares-cli node enable-juicefs`. This installs **MinIO** as the JuiceFS backend and migrates the existing root filesystem; can be slow.
3. On master: `sudo olares-cli node join-command` verifies SSH + sudo and prints a one-liner: `export MASTER_AUTH_INFO='<base64>' OLARES_SYSTEM_CDN_SERVICE='<url>' && curl -fsSL '<join-script-url>' | bash`. Docs warn `MASTER_AUTH_INFO` is Base64, **not encrypted**, and contains master SSH credentials.
4. On worker: must be a clean install (`sudo olares-cli uninstall` if Olares is already there), unique hostname required (both units ship as `olares`). Run the join command. Success message names the node; verify with `kubectl get nodes`.

**Upgrade procedure (verified)**: manual and ordered. (1) SSH to both nodes. (2) On both, write `{"version":"<target>","downloadOnly":true}` to `$OLARES_BASE_DIR/upgrade.target` and wait for `upgradingDownloadState: completed` via `curl localhost:18088/system/status`. (3) On both, copy new `olares-cli`, run `olares-cli prepare images` and `olares-cli prepare olaresd`. (4) Master: `sudo olares-cli upgrade` (reboots); then `kubectl patch terminus terminus --type=merge -p '{"spec":{"version":"<source>"}}'` to temporarily reset the version. (5) Worker: `sudo olares-cli upgrade` (reboots). (6) Master: patch the `terminus` CR back to the target version. This is a hack-level procedure; upgrades are not yet seamless for clusters.

**Limits (verified or documented)**:
- Windows/macOS/Raspberry Pi/PVE/LXC installs are labeled "Not for production use"; macOS and Windows "Lack of distributed storage support" and "Inability to add local nodes" (install-mac-script.md, install-windows-script.md).
- Citus (multi-node Postgres) production readiness "still under evaluation".
- Older architecture doc says GPU support restricted to one GPU per node.
- Home Assistant pins to the control-plane node via nodeAffinity (app manifest).

---

## 5. Olares One hardware and BYO hardware

### 5.1 Olares One (https://www.olares.com/docs/one/spec and https://www.olares.com/one)
| Spec | Value |
|---|---|
| CPU | Intel Core Ultra 9 275HX, 24 cores, up to 5.4 GHz |
| GPU | NVIDIA RTX 5090 Mobile, 24GB GDDR7, 175W max TGP |
| RAM | 96GB (2x48GB) DDR5-5600, upgradable to 128GB |
| Storage | 2TB NVMe, PCIe 4.0 per spec page (FAQ says the preinstalled SSD occupies the PCIe 5.0 slot and a PCIe 4.0 slot is free; the two docs conflict) |
| Ports | 1x Thunderbolt 5 (80Gbps), 1x HDMI 2.1, 1x USB-A 3.2 Gen2, 1x 2.5GbE RJ45, power |
| Wireless | Wi-Fi 7, Bluetooth 5.4 |
| Power | 330W adapter; 30W standby; GPU 50-95W Silent, 175W Performance; CPU 55W during combined max |
| Size/weight | 320x197x55mm; 2.15kg (3.1kg with PSU); aluminum shell, plastic base |
| Noise | 19dB idle, 38.8dB full load (lab testing per vendor) |
| Expansion | eGPU over Thunderbolt supported with caveats (docs/one/egpu.md); dual-boot Windows/Ubuntu guides; HDMI direct display |
| Certifications listed | IS 849777, FCC, CE, UKCA, RCM, VCCI (homepage) |

All of the above are vendor claims except where I opened the spec page. Marketing claim "World's fastest AI desktop" (ComfyUI vs Mac M3 Ultra) and "Save 95%" are vendor-computed, unverified.

### 5.2 Price and availability
- Official store https://shop.olares.com/products/olares-one (Shopify): **$4,999.00**, in stock flag true in page JSON on 2026-11-10. (Fetched page with `curl`; the old `one.olares.com` host 301-redirects here.)
- https://www.olares.com/one: "Black Friday starts Nov 17 - Save $300 per unit"; "No membership or subscription"; OS and updates free (FAQ).
- Kickstarter: launched around Nov-Dec 2025 at $2,999 (SiliconANGLE, Dec 2025); raised $2.34M, January 2026; all backer orders fulfilled per the Oct 2026 press release. Third-party review (PromptQuorum) mentions ~2 business-day shipping from US/EU warehouses (unverified by the reviewer).
- Support: hi@olares.com via the FAQ; WhatsApp.
- DGX Spark is a supported alternative target (install-spark-script/iso docs).

### 5.3 "Manufacture with Olares" OEM program
Verified text, from the olares.com/os page HTML: card title "Manufacture with Olares", body "Ship Olares hardware under your brand. Use our reference designs, secure updates, and official images for faster launches." with a "Contact Olares team" button. The Oct 15, 2026 press release says Olares invites "AI NAS manufacturers, original design manufacturers (ODMs), and system integrators" to explore Olares OS on Intel Core Ultra-based systems. **No public terms, pricing, revenue share, volume minimums, or branding rules were found** (it is a contact-sales funnel). The repo `vendor/` dir contains placeholder folders `olares-one` and `olares-zero` (only `.gitkeep`), so "Olares Zero" is a code name that appears in the tree; nothing is known about it (**UNVERIFIED**).

### 5.4 Bring your own hardware (docs/manual/get-started/install-olares.md and sibling guides)
| Target | Requirements | Status |
|---|---|---|
| Linux (ISO, recommended) | x86-64, 4 cores, 8GB RAM, 150GB SSD (HDD fails). Fresh install on physical machine | Recommended for production |
| Linux script `curl -fsSL https://olares.sh | bash -` | Ubuntu 22.04-25.04 or Debian 12/13 | Supported |
| Docker Compose | Ubuntu 22.04-25.04 / Debian 12-13 | Supported |
| GPU (optional) | NVIDIA only, Turing or newer (GTX 16xx, RTX 20/30/40/50), 8GB VRAM recommended | |
| Windows (WSL 2) | 4 cores, 16GB RAM, 150GB SSD, Win 10/11 | Not for production |
| macOS | 4 cores, 8GB, 150GB, macOS Monterey 12+, Docker Desktop + minikube | Not for production |
| Raspberry Pi | Pi 4B/5 with 8GB, Raspbian 12, 150GB SSD | Not for production |
| PVE / LXC | PVE 8.2.2, 200GB SSD, GPU needs passthrough | Not for production |
| DGX Spark | script or ISO, 150GB free | Supported, optimized |

Notes: the CLI package targets arm64 and amd64 for apps (`supportArch`); Jetson is **not mentioned** in anything I read (UNVERIFIED/none). Installing generic ISO on Olares One is explicitly discouraged.

---

## 6. Home Assistant, AI features, MCP, LarePass

- **Home Assistant**: delivered as a Market app (`beclab/apps/homeassistant`, tracks upstream releases monthly, currently Core 2026.10.0). Guide: https://www.olares.com/docs/use-cases/home-assistant (installs from Market, discovers LAN devices, HACS mentioned in keywords, Dahua camera example). There is also a `beclab/hass-cli` repo (1 star, purpose not read). No evidence of deeper OS-level integration (no HA entities for Olares, no Matter/Zigbee stack in the OS). Because pods are in an isolated namespace, LAN device discovery needs the manifest's overlay/network features (`overlayGateway`); details not read.
- **Local LLM features**: Market ships Ollama, vLLM, SGLang, llama.cpp and per-model packages, Open WebUI, LobeChat, AnythingLLM, Dify, RAGFlow, ComfyUI, Whisper. Model Console (repo `model-console`) manages local inference engines; Router exposes them behind one API (OpenAI-compatible per Router doc keywords) with caller auth/quota; manifest flag `LLMGatewaySupported`. GPU scheduling per section 1.1.
- **MCP**: yes, in practice. Lares has **Settings > MCP** to connect app MCP servers; use-case docs show MCP in Context7, DeerFlow, OpenCode, Penpot (MCP plugin/http endpoints), YuE2 Studio (`yue2-studio-mcp-auth.md`). I did not find an Olares-platform-level MCP server for the OS itself; instead `olares-cli` ships compiled-in **Agent Skills** (`cli/skills/`: olares-chart, cluster, dashboard, doctor, files, knowledge, market, publish, router, search, settings, shared) so external agents (OpenClaw, OpenCode, NemoClaw, Claude Code via skills) operate Olares through CLI verbs. README: "agent-native CLI with Agent Skills to install and operate Olares". Install: `npx @olares/cli@latest install`.
- **OpenClaw / agents**: many use-case guides (openclaw*.md); marketing calls Olares One "the world's best desktop to run OpenClaw locally".
- **LarePass**: see section 2. VPN uses Tailscale protocol against self-hosted Headscale; when VPN is off, traffic goes via Cloudflare or FRP tunnels.
- **Cloud dependence**: default Olares ID domain is `*.olares.com`; DID registry on an Ethereum L2; Olares Space (cloud) for activation/domain; custom-domain Olares IDs are documented (`best-practices/set-custom-domain.md`, not read). Fully offline sovereignty is therefore not the default path. Market source defaults to api.olares.com.

---

## 7. License, company, activity

### 7.1 License (conflicting signals)
- `LICENSE` in root = full GNU AGPL v3 text; GitHub reports `agpl-3.0`; README badge "License AGPL-3.0"; `cli/README.md` says AGPL-3.0-or-later. Commit "Change to GNU Affero General Public License v3 (#1770)" dated 2025-08-30 made the switch (verified via `gh api` commit list).
- `LICENSE.md` ("Olares License", last touched 2024-11-11 "docs: update license title to Olares (#621)") is still in the root and says: use or modify "only for your own internal business purposes or for non-commercial or personal use"; distribution only "free of charge for non-commercial purposes". `apps/packages/core/LICENSE.md` carries the same text. `apps/packages/admin/package.json` says `"license": "UNLICENSED"`. Several sub-repos (app-service, desktop, backup-server, notifications, headscale-api-wrapper...) show GitHub license "other" (https://github.com/beclab). The apps market repo is Apache-2.0; `model-console` AGPL-3.0; HAMi fork Apache-2.0.
- **Interpretation (mine, not legal advice)**: the main repo is AGPLv3 as of Aug 2025, which allows commercial use and commercial forks if you comply with AGPL (publish corresponding source, including for network-served modifications; keep notices). The leftover `LICENSE.md` and per-component "other" licenses create ambiguity for components that were not relicensed. Trademarks (Olares name/logo, `olares.com` domain) are not licensed by AGPL. Before any fork, get counsel to review each sub-repo's license, especially app-service, bfl, system-server, files, desktop, which pull from separate `beclab/*` repos. Also note upstream dependencies carry their own licenses (e.g., KubeSphere fork, Padloc-derived Vault, Infisical, MinIO, Seafile): **UNVERIFIED** for license compatibility; I did not open those.

### 7.2 Company
- Olares Tech Co., Ltd., founded 2022, Singapore HQ; >$100M raised incl. Series A led by SIG (Oct 2026 press release, self-reported). Founder quoted: Peng Peng (SiliconANGLE). GitHub org "BEC Lab", 111 public repos, Singapore. Terminus/TermiPass naming in code (section 1.5); the "Terminus" brand history itself is **UNVERIFIED**.
- Also shows interest in desktop-software "craft" repos: `wordcraft`, `gridcraft`, `deckcraft`, `pdfcraft`, `photocraft`, `filmcraft`, `cadcraft`, etc., Apache-2.0 Rust "clean-room" re-implementations of Office/Adobe/AutoCAD-class tools, all pushed 2026-10-15 with 0 stars. Product intent **UNVERIFIED** (no README read).

### 7.3 Activity
- Main repo: pushed daily; 5,356 stars; 335 forks. Daily `1.12.9-YYYYMMDD` pre-releases (Nov 2-9, 2026) plus alpha/beta/rc for 1.12.8. Stable releases roughly every 1-2.5 months. Release highlights: 1.12.6 "Agent Skills, Model Console for local LLMs, and more reliable shared apps"; 1.12.7 "Router, Lares, and a broader local AI model catalog" (README).
- Stars are modest relative to Umbrel/CasaOS-class projects (I did not collect those numbers, so no comparison is claimed).

---

## 8. Website and docs stack

- https://www.olares.com/: response headers `server: cloudflare`, `x-frame-options: SAMEORIGIN`, HSTS; HTML is a Vue SPA (scoped `data-v-*` attributes, single module bundle `/assets/app-<hash>.js`, `/ol-src.js`). The hashed `app-*.js` naming is also how VitePress emits its bundle, but I did not find VitePress markers in the home page, so the marketing site's framework is **UNVERIFIED** beyond "Vue". Shop at shop.olares.com is Shopify. Wiki/blog/forum exist under /blog and /forum.
- Docs: **VitePress 1.6.4** (verified: `docs/package.json` has `vitepress: 1.6.4`, `vitepress-plugin-mermaid`, OG-image generation via resvg; docs page shows "VitePress v1.6.4"). Docs are in the GitHub repo and `vercel.json` is present, implying Vercel hosting for the docs build (**UNVERIFIED**, inferred from the file). Languages: en + zh. Navigation sections: Manual (get started, system apps, LarePass, settings, best practices), Olares One, Developer (concepts, install, develop/package, CLI), Use cases.
- Marketing site nav: Home, Products (Olares One, Olares OS), Scenes, Ecosystem (Market, Space, LarePass), Support, Community, Store, plus Docs/Blog/Articles/Changelog, About, Brand kit.
- Messaging evolution to note: tagline in README now "Your AI Agent. Your Data. Your Hardware." and "Open-Source Personal Cloud OS for Always-On Agents" (GitHub description); earlier docs called it a personal cloud / Web3-ish with DID.

---

## 9. Strengths, weaknesses, lessons, fork feasibility

### 9.1 Strengths
1. Real, deep product: a full multi-tenant app OS on k3s with SSO, per-app namespaces/network policies, secrets vault, per-app DB provisioning, VPN, backups, upgrades, and a store, shipping since 2024; Go codebase of ~20 MB.
2. Strong packaging story: OAC (Helm + manifest) with a linter library (`framework/oac`), GitBot-checked PR submissions, resource-limit enforcement, entrance auth levels and dependency/conflict declarations. 400+ chart folders, many AI apps.
3. AI-native pivot executed: Router (single AI gateway), Model Console, Lares agent with MCP + access levels, compiled-in Agent Skills in `olares-cli`, GPU modes via HAMi fork. The agent-operates-the-OS story is concrete, not slideware.
4. Hardware flywheel: Olares One shipped to Kickstarter backers ($2.34M), shop listing, OEM "Manufacture with Olares" funnel, DGX Spark support.
5. Documentation depth (VitePress, 7 UI locales, versioned guides, use cases) and daily release engineering.
6. Funding claimed (>$100M) and fast release cadence.

### 9.2 Weaknesses / risks
1. Complexity: Kubernetes plus KubeSphere fork, Helm, Authelia, LLDAP, Seafile, JuiceFS, MinIO, KubeBlocks, Citus, Argo, Linkerd/Envoy; high resource floor (8GB RAM min, 150GB SSD) and a heavy upgrade path (manual multi-step multi-node upgrade with a CR patch hack).
2. Docs lag the code in places: nvshare vs HAMi, `spec.accelerator` vs `spec.resources[]`, Envoy vs Linkerd, SSD PCIe 4.0 vs 5.0 on One.
3. Multi-node is thin: formally two Olares One; MinIO-backed JuiceFS migration required; workers need a clean OS; non-Linux hosts "not for production"; one-GPU-per-node language remains in the architecture doc.
4. NVIDIA-centric GPU story for self-installs (AMD GPU/APU "not covered in this version"; Intel via fork only).
5. Identity coupled to Olares ID/DID, olares.com domains, Olares Space activation, Ethereum L2 registry, LarePass phone as root of trust: not truly offline-first by default; adds vendor dependency.
6. License hygiene unclear (AGPL root plus legacy non-commercial `LICENSE.md` plus "other" licensed sub-repos).
7. Market thin on named agent apps from the prompt list (Scira, SurfSense, Void, Suna, OWL, AgenticSeek, OpenManus, Agent TARS, Activepieces, Knative, Browser Use were not found by folder name). Roster rotates quickly toward OpenClaw/Claude Code/Codex/Hermes-style agents and model packages.
8. Price: $4,999 for Olares One (up from $2,999 Kickstarter) is a niche prosumer price.
9. Stars (5.4k) are modest for the funding claimed; community size beyond Discord/forum not measured.
10. No IoT/robotics/TAK/XR story seen; Home Assistant is just a containerized app; hardware is a single x86+NVIDIA box.

### 9.3 Lessons for OneMind OS
1. **Copy the packaging idea, not the schema**: a manifest layered on Helm with permission/middleware/entrance/resource declarations, a public linter library, and a PR-bot-gated registry is the right pattern. Make agent-facing capability declarations (tools, MCP endpoints, GPU, hardware devices, TAK/CoT topics, NATS subjects) first-class manifest fields; Olares only has `LLMGatewaySupported` and `overlayGateway`.
2. **One AI gateway**: Router (callers -> gateway with auth/quota -> local engines or cloud providers) is the same shape as a OneMind "model router". Build it early; expose OpenAI-compatible and MCP surfaces.
3. **CLI-with-embedded-skills for agent operability**: `olares-cli` bundling `olares-*` skills versioned with the binary is the best-practice for AI-native ops. OneMind's agent roster could use identical idea: skills and verbs from the same release.
4. **Access levels for agents** (Lares chooses read-only vs more) plus per-app MCP credentials is a good least-privilege default.
5. **Runtime guardrails**: copy auto-suspend on pod eviction/unschedulable and cluster CPU/memory thresholds; per-user namespaces; no hostNetwork/NodePort; mandatory resource limits at lint time.
6. **GPU pooling UX**: time-slice / memory-slice / exclusive per-GPU modes with assignment on install and resume. Use HAMi (Apache-2.0 upstream; Olares forks it) as a baseline.
7. **Avoid their traps**: do not couple identity to a vendor domain/DID chain; do not require Kubernetes on small edge devices unless you must (k3s is fine); keep docs generated from the schema so they do not drift; version the upgrade path so multi-node upgrades are one command.
8. **Differentiate where Olares is empty**: TAK/CoT situational awareness, robotics (ROS 2), IoT/Matter/MQTT as OS services (not just a Home Assistant container), XR, and multi-GPU/multi-vendor hardware. Also sovereign/offline identity (LDAP/OIDC without cloud), and an honest hardware story beyond one x86+NVIDIA SKU.
9. **Hardware business**: they proved a $3-5k "personal cloud + local AI" box can crowdfund ($2.34M) and pair with an OEM funnel ("Manufacture with Olares": reference designs, secure updates, official images). OneMind's OEM plan should publish terms; Olares does not.
10. **Distribution**: daily pre-release builds, curated store with i18n listings, and use-case guides per app (openclaw*, lares*, home-assistant) are a strong adoption engine.

### 9.4 Could OneMind fork or build on Olares?
- **Legal**: root license is AGPL-3.0 since 2025-08-30, which allows commercial forks and hardware sales, provided you publish source of modified network services and preserve notices. You cannot use Olares trademarks/domains. A proprietary-core OneMind (e.g., closed agent layer in the same process) would conflict with AGPL; keep proprietary parts as separate network services/apps with clear boundaries and get counsel. The stray `LICENSE.md` (non-commercial) and "other"-licensed sub-repos (app-service, desktop, backup-server, notifications) must be resolved per component before relying on them. The market repo (Apache-2.0) is freely reusable, including OAC charts, but each app has its own license (n8n's example lists the Sustainable Use License).
- **Technical fit**: OneMind already runs on DOKS with NATS (per memory notes), so the cluster-side pieces overlap: k8s, NATS, Postgres, Helm. The best option is likely **adopt the ideas and selected components** (OAC/`framework/oac` linter, HAMi GPU layer, Router/Model Console pattern, Headscale/Tailscale access, Authelia+LLDAP) rather than fork the whole OS, because: (a) Olares assumes a single-user-home appliance, Olares ID/`olares.com` domain routing, bfl/system-server/app-service coupling and a KubeSphere fork; (b) multi-node is immature; (c) upstream cadence (daily builds) means a fork would carry heavy merge debt (~4,000 commits, 20 MB of Go); (d) NVIDIA-centric. A full fork would make sense only if OneMind wants to ship the same "home Kubernetes appliance" product and accepts diverging the identity/network layers.
- **Lower-risk path**: ship OneMind OS as a layer that can also install **on top of** an Olares box (as an OAC chart in an own market source: Olares explicitly supports custom market sources) to inherit its install base, while building the TAK/robotics/IoT/XR differentiators in-house. This needs verification of how far a custom source can go (e.g., system-level privileges) - **UNVERIFIED**.

---

## Sources

- Repo: https://github.com/beclab/Olares (README, LICENSE, LICENSE.md, commit history; `gh repo view`, `gh api .../languages`, `gh release list`)
- `framework/README.md`, `infrastructure/README.md`, `platform/README.md`, `platform/hami/README.md`, `infrastructure/gpu/README.md`: https://github.com/beclab/Olares/tree/main/framework , /infrastructure , /platform
- `framework/oac/README.md` (OAC linter and manifest rules): https://github.com/beclab/Olares/blob/main/framework/oac/README.md
- `framework/app-service/controllers/pod_abnormal_suspend_app_controller.go` and `pkg/appwatchers/suspend.go`: https://github.com/beclab/Olares/tree/main/framework/app-service
- `cli/README.md` and `cli/skills/`: https://github.com/beclab/Olares/tree/main/cli
- Docs (in-repo, published at https://www.olares.com/docs/): `docs/developer/concepts/system-architecture.md`, `network.md`, `account.md`, `olares-id.md`, `registry.md`; `docs/developer/develop/package/manifest.md`; `docs/manual/get-started/install-olares.md`, `install-mac-script.md`, `install-windows-script.md`, `install-raspberry-pi.md`, `install-pve-script.md`, `install-lxc.md`; `docs/manual/olares/*` (desktop, market, settings/gpu-resource, controlhub); `docs/manual/larepass/*`; `docs/one/spec.md`, `faq.md`, `connect-two-olares-one.md`, `upgrade-multi-node-cluster.md`, `configure-gpu-mode.md`; `docs/use-cases/lares.md`, `olares-router.md`, `home-assistant.md`; `docs/package.json`
- Market repo: https://github.com/beclab/apps (README; `n8n/`, `homeassistant/`, `ollamav2/` manifests; folder listing), preview repo https://github.com/beclab/apps-preview
- Org: https://github.com/beclab (repo list; `gh api orgs/beclab`)
- Website: https://www.olares.com/ , https://www.olares.com/os , https://www.olares.com/one (fetched pages and `curl` headers/HTML)
- Store: https://shop.olares.com/products/olares-one (HTML price JSON); old host https://one.olares.com/products/olares-one (301)
- Press: https://www.prnewswire.com/news-releases/olares-showcases-private-ai-at-intels-ai-nas--thunderbolt-technology-forum-in-japan-302909516.html (Oct 15, 2026)
- Press: https://siliconangle.com/2025/12/09/olares-launches-personal-ai-computer-turns-local-files-smart-assistant/
- Search snippets only (not opened in full): https://www.notebookcheck.net/Mini-PC-with-RTX-5090-Mobile-GPU-arrives-with-eye-watering-price-tag.1159783.0.html ; https://www.promptquorum.com/power-local-llm/olares-one-local-ai-review
