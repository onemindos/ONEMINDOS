# OneMind OS: AI-native protocols and UX research

Date of research: 2026-11-10. Rule applied: every claim comes from a page opened this session; URLs inline. Items I could not confirm from a primary source are tagged **UNVERIFIED** or **SECONDARY** (only blogs/news).

---

## 0. Headline findings (read this first)

1. **MCP changed a lot in 2026.** Current spec is **2026-07-28**: stateless, no `initialize` handshake, no `Mcp-Session-Id`, new `server/discover`, tasks moved to an extension, elicitation/sampling replaced by "Multi Round-Trip Requests" (MRTR). Anything the founder has read from 2025 is partly outdated.
2. **MCP is governed by the Linux Foundation's Agentic AI Foundation (AAIF)**, donated by Anthropic 2025-12-09. Verified.
3. **"MHS" is real**: Anthropic's **Model Hardware Standard**, research preview announced **2026-08-27**, built for lab/factory/robot hardware, MCP-accessible. Not open source yet. Details in section 3.
4. **Umbrel 2.0 (released 2026-09-22) already ships an OS-level MCP server** (owner-only, per-agent tokens, permission categories). This is the direct competitor reference. Olares instead ships a CLI plus 12 "Agent Skills" (no MCP mention found on its docs).
5. **Strava forbids feeding its API data to AI** (API Policy effective 2026-06-01, section 5.3 as seen in page text) except through Strava's own MCP, for the subscriber's personal use. The "Strava API key on the dashboard, exposed to AI as context" idea needs redesign (section 8).
6. **Homepage is GPL-3.0, Glance AGPL-3.0**: do not copy code into a closed product. Homarr (Apache-2.0), Heimdall (MIT), Dashy (MIT with an advertising clause), Uptime Kuma (MIT) are safer to learn from.

---

## 1. MCP

### 1.1 Spec revision and date
- Current protocol version: **2026-07-28** ("The current protocol version is 2026-07-28"). Source: https://modelcontextprotocol.io/specification/versioning
- Previous revision: 2025-11-25. Version strings are `YYYY-MM-DD` = date of last breaking change. Same page.
- Key changes in 2026-07-28 (https://modelcontextprotocol.io/specification/2026-07-28/changelog):
  - Protocol-level sessions and `Mcp-Session-Id` removed (SEP-2567). Cross-call state uses server-minted handles passed as normal tool arguments.
  - Stateless: `initialize` handshake removed; every request carries protocol version and client capabilities in `_meta` (SEP-2575).
  - New mandatory `server/discover` RPC (versions, capabilities, identity).
  - `subscriptions/listen` replaces the GET endpoint and `resources/subscribe`.
  - Tasks moved out of core into official extension `io.modelcontextprotocol/tasks` (SEP-2663).
  - MRTR replaces server-initiated requests (roots, sampling, elicitation): server returns `InputRequiredResult`, client retries with `inputResponses` (SEP-2322).
  - Roots, Sampling, Logging **deprecated**; HTTP+SSE transport deprecated; Dynamic Client Registration deprecated in favor of Client ID Metadata Documents (CIMD).
  - `ttlMs` and `cacheScope` on list results (caching); OpenTelemetry trace context keys in `_meta`; required `Mcp-Method` / `Mcp-Name` HTTP headers.
  - SSE stream resumability removed.
- Roadmap (page "last updated 2026-08-22") priorities: agentic messaging primitives (tasks/events/webhooks), HTTP-native transport unification (including HTTP over stdio, ETag caching), agent identity (DPoP, workload identity federation, ID-JAG, RFC 8693), improved primitives (progressive discovery of tools), SDK experience. Source: https://modelcontextprotocol.io/development/roadmap

### 1.2 Transports
- Two standard transports: **stdio** (newline-delimited JSON-RPC over a client-launched subprocess) and **Streamable HTTP** (each message an HTTP POST to a single endpoint; reply is JSON or a request-scoped SSE stream). Custom transports allowed. Source: https://modelcontextprotocol.io/specification/latest/basic/transports
- Roadmap goal: make Streamable HTTP the single binding, also spoken over stdio (HTTP/2 over stdio). Source: roadmap above.

### 1.3 Authorization (OAuth 2.1 resource-server model)
Source: https://modelcontextprotocol.io/specification/latest/basic/authorization
- Authorization is **optional**; for HTTP transports it SHOULD follow the spec; stdio SHOULD NOT (use environment credentials).
- MCP server = OAuth 2.1 **resource server**; MCP client = OAuth 2.1 client; authorization server may be separate.
- MCP servers MUST implement **Protected Resource Metadata (RFC 9728)**; clients MUST use it to discover the authorization server. AS must offer RFC 8414 or OIDC Discovery.
- Client registration: **Client ID Metadata Documents** preferred (SHOULD), pre-registration, or Dynamic Client Registration (deprecated, kept for compatibility).
- Clients MUST send the RFC 8707 `resource` parameter in authorize and token requests; servers MUST validate token audience; token passthrough is forbidden; tokens never in query strings.
- Scope model: `WWW-Authenticate` with `scope`, step-up via 403 `insufficient_scope`. RFC 9207 `iss` validation (mix-up defense).
- Authorization extensions (ext-auth): OAuth Client Credentials (machine-to-machine) and Enterprise-Managed Authorization, both Stable. Source: https://modelcontextprotocol.io/extensions/overview.md
- Security guidance (confused deputy, token passthrough, SSRF in discovery, local-server compromise, scope minimization): https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices.md

**Implication for OneMind:** Authentik (OIDC) can be the authorization server. It must support RFC 8414/OIDC discovery and ideally CIMD. **UNVERIFIED:** whether Authentik supports CIMD or RFC 8707 resource indicators today; test before promising it.

### 1.4 MCP Registry
- Official registry is **in preview** ("Breaking changes or data resets may occur before general availability"). Stores `server.json` metadata that points at npm/PyPI/Docker/remote URLs; reverse-DNS namespaces verified via GitHub/DNS/HTTP; **does not support private servers**; official codebase is **not designed for self-hosting**; host apps are expected to consume aggregators/sub-registries implementing its OpenAPI spec. Source: https://modelcontextprotocol.io/registry/about.md
- Implication: OneMind needs its **own private registry** (app manifest becomes the source) and may optionally implement the registry OpenAPI so MCP hosts can consume it.

### 1.5 Extensions: MCP Apps, Tasks, Skills, Server Cards
Source: https://modelcontextprotocol.io/extensions/overview.md (extensions are always opt-in; IDs like `io.modelcontextprotocol/ui`).
- **MCP Apps** (`io.modelcontextprotocol/ui`): **Stable**. Tools declare `ui://` resources containing HTML, host renders in a **sandboxed iframe**, UI talks to host over MCP JSON-RPC. Supported by ChatGPT, Claude, VS Code, Goose, Postman and others. Source: https://github.com/modelcontextprotocol/ext-apps
- **Tasks**: **Beta, heading to core**. Server returns a durable `taskId`; client polls `tasks/get`; states `working`, `input_required`, `completed`, `failed`, `cancelled`; `tasks/update` supplies input; `tasks/cancel`. Source: https://modelcontextprotocol.io/extensions/tasks/overview.md
- **Skills over MCP**: Beta. Discover Agent Skills and supporting files via MCP resources. **Server Cards**: Beta; HTTP discovery of server metadata before connecting. (Overview page above.)
- **Elicitation** (2026-07-28): form mode (flat primitives only) and URL mode. Servers MUST NOT collect passwords/API keys/tokens in form mode; URL mode is for secrets and third-party OAuth so credentials never pass through the client or LLM. Source: https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation.md

### 1.6 Governance
- Anthropic donated MCP to the **Agentic AI Foundation (AAIF)**, a directed fund under the **Linux Foundation**, co-founded by Anthropic, Block and OpenAI; founding projects MCP, goose (Block), AGENTS.md (OpenAI); announced 2025-12-09; Platinum members include AWS, Anthropic, Block, Bloomberg, Cloudflare, Google, Microsoft, OpenAI. Source: https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation (also https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation)
- Legal entity "Model Context Protocol a Series of LF Projects, LLC"; Apache-2.0 for code and specs; docs CC BY 4.0; Lead Maintainers (BDFL) David Soria Parra and Den Delimarsky; SEP process; working groups. Source: https://modelcontextprotocol.io/community/governance.md

### 1.7 How Umbrel and others expose an OS-level MCP server
- **Umbrel (umbrelOS 2.0, shipped 2026-09-22)** per https://umbrel.com/support/advanced/connecting-ai-agents :
  - Endpoint `http://umbrel.local/mcp` (plain HTTP on LAN); remote via Tailscale IP.
  - Only the **owner** can set up MCP; **agents act as the owner**. One token per agent (shown once), up to 20 agents, "Authorized tokens" list with last-request time, instant revoke, global off switch. Restoring a backup turns MCP off and deletes tokens.
  - Permission categories: always-on basic info; **Apps** (selected or all: data, settings, logs, restart/update/uninstall); **App Store**; **Folders** (deletions go to Trash, no overwrite); **Manage umbrelOS** (updates, restart, logs); **Machines** (VM control).
  - Not accessible: shutdown, factory reset, backups, user management, Wi-Fi/network settings.
  - Page warns MCP is **beta** and agents can make real changes.
  - Release notes: each agent gets its own token limited to approved access. https://github.com/getumbrel/umbrel/releases/tag/2.0.0
  - SECONDARY (not verified at source): one review reports "7 read-only tools by default, 38 when permissions granted". Cited via search result for https://thomaswildetech.com/blog/2026/10/04/umbrelos-20-whats-new-and-can-it-run-vms-inside-a-vm/ (page itself returned 404 when fetched).
- **Olares**: docs say agents operate Olares through the **Olares CLI plus 12 "Agent Skills"** (`SKILL.md` bundles: files, market, settings, dashboard, cluster, doctor, chart, router for AI models, etc.), installed into Claude Code/Cursor/Codex/OpenClaw skill dirs; skills are compiled into the CLI binary so they match the CLI version. Source: https://www.olares.com/docs/developer/cli-agent-skills . The docs overview page did not mention MCP (https://www.olares.com/docs/). **UNVERIFIED** whether Olares has an MCP server elsewhere.
- **Home Assistant** built-in MCP server integration: main URL `/api/mcp`, **OAuth 2.0 + PKCE with CIMD auto-registration**, default admin-only; tool sets ("LLM APIs") selectable; "Device control" only reaches entities the user exposed to voice assistants; "Home Assistant" tool set reads all entities/history and requires admin; **read-only** switch; resources only for Device control; sampling and notifications unsupported. Source: https://www.home-assistant.io/integrations/mcp_server/
- **Backstage** MCP Actions Backend: exposes **Actions Registry** entries as MCP tools over Streamable HTTP at `/api/mcp-actions/v1`; namespaced tool names (plugin-id prefix); named servers with include/exclude glob filters; actions declare hints (read-only, idempotent, destructive) with conservative defaults (destructive unless read-only); auth via static tokens (workaround) or OAuth with CIMD (recommended), DCR deprecated; tracing of tool calls, payload capture off by default. Source: https://backstage.io/docs/ai/mcp-actions
- **Kubernetes MCP server** (containers/kubernetes-mcp-server): Go-native (not kubectl wrapper), **toolsets** enabled selectively (`core`, `config`, `helm`, `kubevirt`, observability...), `read_only` and `denied_resources` described as "best-effort guardrails" with **RBAC on the server identity as the real control**, OAuth/OIDC in HTTP mode. Source: https://github.com/containers/kubernetes-mcp-server

### 1.8 Auto-generating MCP servers from app APIs / OpenAPI
- FastMCP turns OpenAPI endpoints into tools by default; ordered `RouteMap` rules by method/path-regex/tag assign each route to tool, resource, resource-template or exclusion; catch-all exclusion = allow-list mode. Docs state LLMs do "significantly better" with curated servers than with auto-converted ones and recommend using generation as a starting point. Source: https://gofastmcp.com/integrations/openapi
- Backstage's registry pattern (section 1.7) is the better design target: **declare actions once with metadata and hints, project them into MCP**, rather than blind OpenAPI conversion.
- Roadmap "progressive discovery" (large tool catalogs loaded on demand) matters for an OS exposing dozens of apps. Source: roadmap above. Also deterministic `tools/list` order is recommended for caching (changelog above).

---

## 2. Other agent protocols and sandboxing

| Protocol | What it is | Status/governance (verified) |
|---|---|---|
| **A2A** (Agent2Agent) | Agent-to-agent discovery and task delegation between opaque agents; complements MCP (agent-to-tool). Signed Agent Cards in v1.0. | v1.0 first stable spec; Linux Foundation press release 2026-04-09: https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year ; site: https://a2a-protocol.org/latest/ . Move into AAIF reported mid-Aug 2026 by Axios/Techzine (**SECONDARY**: https://axios.com/2026/08/17/a2a-agentic-ai-foundation-open-ai-standards ); a2a-protocol.org banner also says "joining the Agentic AI Foundation". |
| **ACP (IBM, BeeAI)** | Was an agent communication protocol. | **Merged into A2A**, active development winding down: https://lfaidata.foundation/communityblog/2025/08/29/acp-joins-forces-with-a2a-under-the-linux-foundations-lf-ai-data/ |
| **ACP (Agent Client Protocol)** | Different thing: editor-to-coding-agent protocol (LSP analogy). Name collision risk. | https://agentclientprotocol.com/overview/introduction ; remote-agent support "work in progress" |
| **AGNTCY** | Cisco-originated "Internet of Agents" stack: OASF schema, Agent Directory, SLIM messaging, Identity. | Part of Linux Foundation, TSC incl. Cisco, Dell, Red Hat, Google Cloud, Oracle: https://github.com/agntcy |
| **AGENTS.md** | OpenAI's repo-instruction file convention. | AAIF founding project (LF press release above). |
| **OpenAI Apps SDK / plugins** | MCP server + optional UI resources + skills for ChatGPT and Codex. | Page does not say how its UI layer relates to MCP Apps: https://developers.openai.com/apps-sdk/ . Treat relation as **UNVERIFIED**. |

Recommendation: **MCP is the only one OneMind needs in v1.** A2A only when a third-party agent must call a OneMind agent as an opaque peer. Hermes agents inside the cluster can keep NATS.

### Agent sandboxing on Kubernetes
- **Agent Sandbox** (kubernetes-sigs, SIG Apps): CRDs `Sandbox` (single stateful pod, stable identity, persistent storage, pause/resume, scheduled deletion), `SandboxTemplate`, `SandboxClaim`, `SandboxWarmPool` (pre-warmed). It **does not provide isolation itself**: you pick a runtime (gVisor, Kata) via `RuntimeClass`. Apache-2.0; K8s 1.25+ (1.29+ recommended); CRDs still evolving. Source: https://github.com/kubernetes-sigs/agent-sandbox
- **gVisor**: userspace application kernel (Go; Sentry + Gofer); `runsc` OCI runtime; incomplete syscall coverage and higher per-syscall overhead. https://gvisor.dev/docs/
- **Kata Containers**: containers inside lightweight VMs; QEMU, Cloud-Hypervisor, Firecracker; OpenInfra Foundation stewardship; Apache-2. https://katacontainers.io/
- **Firecracker**: minimal KVM microVM VMM, Apache-2.0, used by Kata/Lambda/Fargate. https://github.com/firecracker-microvm/firecracker . Needs KVM (relevant for a box product: nested virtualization or bare metal required).
- **Browser Use**: MIT; agent writes Python in a REPL over Chrome DevTools Protocol; library, CLI, hosted Cloud, and an MCP server; local mode opens an **unauthenticated debug port on 127.0.0.1**; domain allow/block lists are "a guard rather than a sandbox"; run untrusted tasks in a container or VM. https://github.com/browser-use/browser-use

---

## 3. "MHS": result

**A real protocol exists with that abbreviation: Anthropic's Model Hardware Standard (MHS).** The founder's recollection ("a protocol Anthropic is working on for robots/embedded") is substantially correct, with caveats.

Primary source: https://www.anthropic.com/news/model-hardware-standard-research-preview ("Previewing the Model Hardware Standard", 2026-08-27).
- "A shared specification for AI agents to safely operate physical devices"; developed with HHMI Janelia Research Campus; **research preview** for select labs and advanced manufacturers; waitlist at modelhardwarestandard.com.
- Mechanism: a per-device **MHS driver** exposes read/write functions in a discoverable format; users describe hardware in plain language, producing a **device reference file** (measurable values, settings, safety limits, e.g. robot arm weight); agents control devices through **MCP, a CLI, or code files (APIs)**; agents can compile driver calls into scripts that run without LLM reasoning.
- Partners: Genentech, UW labs, Carnegie Mellon, HHMI Janelia, QuEra, Tetsuwan; vendors AWS, Automata, Danaher, Doosan Robotics, MBF Bioscience, QIAGEN, Tecan, Universal Robots; **Raspberry Pi** enabling MHS across several products (embedded relevance); Hugging Face LeRobot mentioned (robotics relevance).
- **Limitations stated by Anthropic:** only devices with a programmable interface; Claude needs expert oversight for physical reasoning; physical safety roadmap in development. **Open-source release is planned after the preview, no date**. Consumer devices not addressed.
- Second source: https://the-decoder.com/anthropic-wants-to-do-for-physical-hardware-what-its-model-context-protocol-did-for-software/ (dated 2026-08-29). SECONDARY claim that auth/authz/audit requirements are not yet published: Enterprise DNA / kingy.ai summaries via search; **UNVERIFIED**.
- Not to be confused with: "Device Context Protocol" (academic paper, arXiv 2605.26159, https://arxiv.org/pdf/2605.26159, seen only as a search result, not opened) and the unrelated third-party repo huzjie/hardmesh (claims an MHS implementation; seen only as a search result, **UNVERIFIED**).

**Recommendation:** Do not build on MHS yet (no public spec, no license). Design OneMind device/robot capabilities so an MHS driver can later appear as just another capability behind MCP/CLI/API. Join the waitlist if robotics is in scope.

---

## 4. "Everything readable by AI": capability registry design

Observed patterns:
- **Umbrel**: permission categories per agent token; owner-only; token per agent. (1.7)
- **Olares**: CLI is the canonical surface; **skills bundles generated with the CLI version** so docs for agents cannot drift. (1.7) Olares also lets apps declare `LLMGatewaySupported`, entrances with `authLevel`, `sharedEntrances` (internal APIs other apps call), middleware, and `permission` flags in the OlaresManifest. https://www.olares.com/docs/developer/develop/package/manifest
- **Home Assistant**: a single **exposure list** (entities exposed to Assist) is the permission primitive reused for MCP. (1.7)
- **Backstage**: **Actions Registry** as one declarative source projected into MCP with allow/deny filters and behavior hints. (1.7)
- **Kubernetes MCP**: toolsets + RBAC as the real guard. (1.7)

Design conclusions (mine, derived from the above):
1. One **capability** record per thing an app can do or read: `id`, JSON-Schema in/out, `effect` (read, write, destructive, idempotent), `scope` (e.g. `app:jellyfin:library.read`), `audience` (human, agent, both), `requiresApproval`.
2. **Project** each capability into: MCP tool/resource, REST/OpenAPI path, CLI subcommand, and an Agent Skill (`SKILL.md`) generated from the same record. Never hand-write the four separately.
3. **Enforce authorization in the capability gateway**, not in the MCP server and not by tool filters. Both Backstage (registry does not enforce permissions, each action must) and Kubernetes MCP (guardrails best-effort, RBAC authoritative) say filters alone are insufficient.
4. Curate: auto-import from OpenAPI is the draft, a human or maintainer reviews names/descriptions (FastMCP guidance).
5. SSH: treat as break-glass admin only; no evidence in sources that peers expose SSH to agents. **UNVERIFIED** as a pattern.

---

## 5. Self-hosted dashboards

| Project | License | Discovery / integrations (verified) | Source |
|---|---|---|---|
| **Homepage** | **GPL-3.0** | Docker label discovery; **k8s discovery from Ingress annotations** (`gethomepage.dev/enabled,name,group,icon,weight,instance,pod-selector`), also Traefik IngressRoute and Gateway API HttpRoute; widgets declared via `widget.type`/`widget.url`/headers annotations; "100+" service integrations; **all backend API calls proxied so keys never reach the browser**; optional OIDC | https://github.com/gethomepage/homepage , https://gethomepage.dev/configs/kubernetes/ |
| **Homarr** | **Apache-2.0** | 80+ integrations, drag-and-drop boards, users/groups/permissions, OIDC and LDAP, "Extensive Kubernetes support with Helm". Auto-discovery of services not confirmed on page (**UNVERIFIED**) | https://github.com/homarr-labs/homarr |
| **Dashy** | MIT plus an advertising-use clause | HTTP status checks, ICMP host checks, per-item polling, OIDC/Keycloak, basic auth with guest read-only, UI config editor, PWA | https://github.com/Lissy93/dashy |
| **Glance** | **AGPL-3.0** | Feeds/RSS/weather/Docker/server stats, `custom-api`, `iframe`, `extension` widgets; single binary under 20 MB; no background polling, fetch on page load with per-widget cache | https://github.com/glanceapp/glance |
| **Heimdall** | MIT | "Enhanced apps" call the app API for live stats; "foundation apps" give icon and color only | https://github.com/linuxserver/Heimdall |
| **Organizr** | GPL-3.0 | Tabbed iframe launcher, multi-user groups, login via Plex/Emby/LDAP, fail2ban and nginx auth_request; maintenance state not shown on README (**UNVERIFIED**) | https://github.com/causefx/Organizr |

What to copy (ideas, not code, where GPL/AGPL):
- Declarative widget metadata attached to the **service definition itself** (Homepage annotations) so install = appears on dashboard.
- Server-side proxying of API keys (Homepage).
- Tiering: foundation (icon/status only) vs enhanced (live stats) (Heimdall).
- Per-widget cache and no background polling for low resource use (Glance).
- Boards + groups + permissions + OIDC (Homarr). Homarr's Apache-2.0 license also makes it a possible fork base. **UNVERIFIED:** code quality and plugin extensibility; evaluate before deciding build vs fork.
- OneMind addition: widgets that render from **capability outputs** (same data AI sees) and optionally as **MCP Apps** `ui://` resources so the same widget appears in Claude/ChatGPT.

---

## 6. Native alerting and push without SaaS

Verified building blocks:
- **Alertmanager**: grouping, routing tree to receivers, inhibition, silences (web UI). https://prometheus.io/docs/alerting/latest/alertmanager/ . Your cluster already has this pattern; reuse the model for the in-app alert center (group, inhibit, silence, ack).
- **ntfy**: HTTP pub/sub (PUT/POST), self-hostable, **Apache-2.0/GPLv2 dual license**, open-source iOS app. https://github.com/binwiederhier/ntfy
  - **iOS limit:** a self-hosted server cannot push instantly alone. It must set `upstream-base-url` (e.g. ntfy.sh) which relays a **poll_request** via Firebase/APNs containing only message ID and a topic hash; the app then fetches content from your server. Without it, delivery can take hours (20-30 min typical when phone in use). Access control via `auth-file`; roles user/admin; per-topic ACLs; tokens grant full account access. UnifiedPush topics (`up*`) need anonymous write on private servers. Source: https://docs.ntfy.sh/config/
  - Consequence: "no external SaaS" is not fully achievable on iOS; the relay sees metadata only (ID and hash), not content. For a product, either operate OneMind's own relay (Firebase/APNs project under OneMind's Apple developer account) or ship a native OneMind iOS app registered with APNs. Android can be fully self-hosted.
- **UnifiedPush**: decentralized push; distributors include ntfy, NextPush (Nextcloud), Sunup, Conversations, KUnifiedPush (Linux). The page does not mention iOS (**iOS support UNVERIFIED**). https://unifiedpush.org/
- **Gotify**: REST in, WebSocket out, web UI, Android client, MIT; page does not mention iOS. https://github.com/gotify/server
- **Apprise**: library/CLI with one URL scheme to many services; BSD-2-Clause; separate **apprise-api** service for HTTP relay. Good as the **outbound fan-out layer** (email, Matrix, Telegram, ntfy). https://github.com/caronc/apprise
- **Uptime Kuma**: MIT; HTTP/TCP/ping/DNS/Docker monitors, 90+ notification services, status pages. https://github.com/louislam/uptime-kuma . Good model for per-app health monitors declared in the manifest.

Pattern for OneMind:
1. Sources (Prometheus/Alertmanager, app health checks, capability events, NATS subjects) emit a normalized **Alert** (severity, app, user scope, dedupe key, runbook link).
2. Alert center stores state (firing, acked, silenced) per household/user; the dashboard and MCP resource `alerts://active` read it.
3. Delivery plugins: in-app, ntfy (self-hosted, iOS via upstream relay), Apprise targets (Matrix/Telegram matches your cluster-hardening plan), email.
4. Kid-scoped alerts routed to guardians (ties to section 7).

---

## 7. Multi-user households and parental controls

Verified facts:
- **Umbrel 2.0**: each person gets own account, home screen, private Home folder; owner shares chosen apps and folders; per-app access settings; MCP is owner-only. https://umbrel.com/support/getting-started/whats-new-in-umbrelos-2 , release notes above. Kid-specific controls: **not found** (UNVERIFIED that any exist).
- **Olares**: three roles: Super Admin, Admin (cannot manage other Admins), Member (personal + granted shared resources, no cluster admin). Isolation mechanism not described on the page. https://www.olares.com/docs/manual/olares/settings/roles-permissions . App manifest has `onlyAdmin`, shared apps in `<app>-shared` namespaces (manifest page above).
- **Jellyfin**: the best parental-controls reference. Per user: maximum parental rating, block unrated items, block/allow by tags, **access schedule** (playback stops outside window), per-library access, per-device approval; admin flag "allow this user to manage the server"; lockout after failed logins; hidden users. https://jellyfin.org/docs/general/server/users/adding-managing-users
- **Home Assistant**: owner account; built-in auth providers (local, trusted networks, command line); command-line provider supports `local_only` and group `system-admin` / `system-users`. The role docs I opened were thin; other role details (read-only users, per-entity restrictions) **UNVERIFIED**. https://www.home-assistant.io/docs/authentication/providers/
- **Nextcloud**: I did not find user-isolation details in a source I opened. **UNVERIFIED**.

Identity options for a box product (verified features):
| IdP | Notes | License |
|---|---|---|
| **Authentik** (you run it) | SAML, OAuth2/OIDC, LDAP, RADIUS; Docker Compose or Helm | MIT core, separate "EE" license in `authentik/enterprise` (https://github.com/goauthentik/authentik) |
| **Kanidm** | Passkeys, OIDC, read-only LDAPS gateway, RADIUS, own DB with 2-node replication, WebUI self-service; Rust | MPL-2.0 (https://github.com/kanidm/kanidm) |
| **LLDAP** | Lightweight LDAP user store with web UI, SQLite default, GraphQL API; not a full IdP | GPL-3.0 (https://github.com/lldap/lldap) |
| **Zitadel** | OIDC (certified), SAML, passkeys, SCIM, orgs/projects multi-tenancy; needs PostgreSQL 14+ | AGPL-3.0 per README (https://github.com/zitadel/zitadel) |
| **Authelia** | 2FA/SSO for reverse proxies; license and OIDC details not on page I fetched (**UNVERIFIED**) | https://www.authelia.com/overview/prologue/introduction/ |
| **Keycloak** | Not opened this session; **UNVERIFIED** |  |

Recommendation: keep Authentik for now (already deployed, covers OIDC/LDAP/RADIUS); evaluate Kanidm as a lighter, self-contained alternative for the single-box SKU (passkeys, own DB, replication). Model households as **groups with roles** (owner, adult, teen, child, guest) and map to capability scopes. Copy Jellyfin's parental model (rating ceiling, tag allow/block, schedule, device approval) as generic **policy primitives** that any app manifest can opt into, and treat **agents as principals** with their own household role (a child's agent inherits the child's limits). That last point is a design inference, not something found in any source.

---

## 8. Cloud-app integration layer, secrets, and the Strava problem

### 8.1 Findings
- **Nango**: managed OAuth/API-key auth, token refresh, credential-injecting proxy, TypeScript "functions", syncs/webhooks, "1,000+ APIs", AI tool calling & MCP; self-hostable with a **limited feature set**; **Elastic License** (not OSI open source). https://github.com/NangoHQ/nango
- **Composio**-style brokers: not opened this session; **UNVERIFIED**. (Your own memory notes a rule against Composio for Notion.)
- **Infisical**: secrets, certs, PKI, KMS, privileged access, and AI-agent credential brokering; self-host; license not stated on the page I fetched (**UNVERIFIED**). https://infisical.com/docs/documentation/getting-started/introduction
- **OpenBao**: MPL-2.0; secrets, dynamic secrets with leases and revocation, encryption as a service; governance mentions OpenSSF, not stated as Linux Foundation on page. https://github.com/openbao/openbao
- MCP pattern for third-party credentials: use **URL-mode elicitation** so the user authorizes the third-party service in the browser; the MCP server stores tokens bound to the user identity; credentials never transit client or LLM; **no token passthrough**; verify the person completing the flow is the one who started it (anti-phishing rule). https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation.md and the security best-practices page above.

### 8.2 Strava (verified from primary pages)
- Strava API Policy (effective 2026-06-01) section "Training, Fine-Tuning, Grounding, Evaluation, Embedding, or Retrieval-Augmented Generation": you **may not use Strava API Materials or Strava Data "in connection with the development, training, evaluation, or operation of any AI Application"**, including derived/aggregated/anonymized data; and may not make Strava Data available to AI Application providers or model developers even with user consent. Source: https://www.strava.com/legal/api_policy (text read by fetching the page; section numbering 5.3 etc. comes from a secondary blog, https://sahha.ai/blog/health-api-ai-restrictions/ , **SECONDARY**).
- Strava operates its own **Strava MCP** as "the sole authorized first-party agent-mediated interface"; subscribers may use it for **personal use of their own data** with their own AI application; it may not enable commercial or third-party access. Same page, section 3.5.
- The separate Strava API Agreement (effective 2026-06-01) says data about a user may be shown only to that user, and other users' data may not be displayed. https://www.strava.com/legal/api
- Garmin and Oura rules differ (Garmin allows AI with consent and disclosure; Oura splits by role and bans training/caching) **SECONDARY**, from the Sahha post above; primary pages not opened.

**Consequence for OneMind:** A dashboard widget that shows the owner's own Strava data is plausible within the Agreement; **piping Strava API data into an agent's context via your own integration is, per the policy text, prohibited**. The compliant AI path is: user connects **Strava's official MCP** to their own agent, and OneMind merely registers/launches that connection (as a remote MCP server entry) without ingesting Strava data into OneMind's own AI context. Get legal review; this is not legal advice. Design the integration layer with a per-provider **`aiPolicy`** field (`allowed`, `consent-required`, `official-mcp-only`, `prohibited`) so the capability gateway can refuse to expose data to agents when a provider forbids it.

---

## 9. Plugin ecosystems: what makes them succeed

- **Home Assistant**: Integration Quality Scale Bronze to Platinum recorded in `manifest.json` (`quality_scale`) and `quality_scale.yaml`; new core integrations must reach Bronze; config-flow UI setup, unique IDs, diagnostics, repairs, >95% test coverage at Silver; hassfest validates. https://contributors.home-assistant.io/core/quality-scale/ . **HACS** custom integrations: one integration per repo, `manifest.json` with `domain, documentation, issue_tracker, codeowners, name, version`, brand icon. https://hacs.xyz/docs/publish/integration/
- **Obsidian**: submission through community.obsidian.md; repo needs README, LICENSE, `manifest.json`; GitHub release assets `main.js`, `manifest.json`, `styles.css`; unique id; automatic review with errors blocking install. https://docs.obsidian.md/Plugins/Releasing/Submit+your+plugin . Developer policies page (network-use disclosure, telemetry, ads, obfuscation) was missing at fetch, so contents **UNVERIFIED**.
- **VS Code**: manifest `package.json` with `publisher`, `engines.vscode`; publisher verification needs a 6-month-old domain with DNS TXT proof. Scanning/signing/workspace-trust not on page (**UNVERIFIED**). https://code.visualstudio.com/api/working-with-extensions/publishing-extension
- **Backstage**: plugin ecosystem under CNCF Incubation; (what-is page gives little architecture detail). You found it too shallow; its useful ideas are the Software Catalog entity model and the Actions Registry. https://backstage.io/docs/overview/what-is-backstage
- **Omarchy** (MIT, basecamp/omarchy): `omarchy plugin add|enable|disable|remove|update|validate|catalog` commands exist in the repo; `manifest.json` requires `schemaVersion: 1`, `id`, `name`, `version`, `kinds`, `entryPoints`; validator rejects symlinks, unsafe paths, and reserved `omarchy.*` ids; comment says the shell "never trusts manifests blindly". Source: https://github.com/basecamp/omarchy/blob/master/bin/omarchy-plugin-validate (read via gh). Secondary descriptions of "explicit enablement after install for auditing" come from instagit.com (**SECONDARY**).
- **MCP extensions** themselves: Experimental, Beta, Stable lifecycle with required reference implementation and two interoperating implementations to go Stable. https://modelcontextprotocol.io/extensions/overview.md . Good template for OneMind's app maturity levels.

Success factors common to these (observed, synthesized): a **small declarative manifest with a validator** (HA, Omarchy, Obsidian), **tiered quality labels** (HA), **verified publisher identity** (VS Code, MCP registry namespaces), **explicit user enablement and permission declaration** (Olares manifest, Umbrel per-app access, MCP extensions opt-in), and **a CLI to scaffold, validate, install** (Omarchy). Sandboxing: only Olares (namespaces, permission flags) and Umbrel (per-app folder access) show concrete per-app restrictions in the sources read; the editors rely on trust/review.

---

## 10. Proposed OneMind capability layer

Goal: **one app manifest drives dashboard, alerts, MCP, CLI, API, permissions, and household policy.**

### 10.1 Manifest (`onemind.app.yaml`, schemaVersion 1)
```yaml
schemaVersion: 1
id: com.example.jellyfin          # reverse-DNS, verified publisher (MCP registry / VS Code pattern)
name: Jellyfin
version: 1.4.0
quality: bronze                    # bronze|silver|gold (HA quality scale pattern)
runtime: { kind: helm|compose, sandbox: standard|gvisor|kata }
entrances:                         # Olares pattern
  - { name: web, port: 8096, authLevel: private, openMethod: iframe }
storage: { appData: true, userData: [Media], externalData: false }   # Olares permission flags
identity: { oidc: true, groups: [adult, teen, child, guest] }
dashboard:                         # Homepage/Heimdall pattern
  tier: enhanced                   # foundation (icon/status) | enhanced (widgets)
  widgets:
    - { id: now-playing, source: capability:media.sessions.list, render: tile|mcp-app }
health:                            # Uptime Kuma pattern
  checks: [{ type: http, url: /health, interval: 60s }]
alerts:
  - { id: library-scan-failed, severity: warning, source: event:library.scan.failed, route: owner }
capabilities:                      # Backstage actions-registry pattern
  - id: media.search
    schema: { in: ./schemas/search.in.json, out: ./schemas/search.out.json }
    effect: read                   # read|write|destructive; idempotent: true|false
    scope: app:jellyfin:library.read
    audience: [human, agent]
    exposure: { mcp: tool, rest: GET /v1/search, cli: "onemind jellyfin search" }
  - id: library.delete_item
    effect: destructive
    scope: app:jellyfin:library.write
    requiresApproval: true         # MCP elicitation / task input_required
policy:                            # Jellyfin parental model as generic primitives
  supports: [ratingCeiling, tagAllowBlock, schedule, deviceApproval]
integrations:                      # cloud apps
  - { provider: strava, auth: oauth, aiPolicy: official-mcp-only }
```

### 10.2 Pipeline
1. **Install** validates manifest (like `omarchy plugin validate`, hassfest), checks publisher and quality tier, requires user to approve declared storage, entrances, scopes.
2. **Registration controllers** (Argo CD-delivered, fits your stack) project the manifest:
   - Dashboard: tile and widgets (server-side proxy for keys).
   - Health/alerts: monitors and alert rules into the alert center (NATS JetStream subjects as the event bus).
   - **Capability registry** (CRD or table): the single source.
   - Projections generated from it: MCP tools/resources (Streamable HTTP, 2026-07-28), OpenAPI REST, CLI subcommands, and Agent Skill `SKILL.md` bundles (Olares approach), plus optional MCP Apps `ui://` widgets.
3. **Capability gateway** (single enforcement point): authenticates via Authentik OIDC; MCP uses RFC 9728 metadata, RFC 8707 audience, scope step-up on 403; authorizes by (principal, household role, agent grant, policy); logs every call to an audit stream and OpenTelemetry (MCP `_meta` trace keys).
4. **Principals**: human users and **agents**, each agent with its own client identity and token, grants per category like Umbrel (apps, folders, system, devices), default minimal, instant revoke, last-used timestamp. Unlike Umbrel, agents do **not** act as owner: they act as the granting user's role, intersected with the grant. (Design choice; Umbrel's owner-only model is documented, the intersection model is my proposal.)
5. **Long-running and approvals**: use MCP Tasks for installs/backups; `input_required` plus URL-mode elicitation for destructive actions and third-party OAuth connect flows.
6. **Isolation for agents and untrusted apps**: Kubernetes Agent Sandbox with gVisor (no KVM needed) as default for agent code/browsers; Kata/Firecracker where KVM is available; NetworkPolicy egress proxy (SSRF guidance from MCP security page).
7. **Secrets and cloud tokens**: OpenBao or Infisical for storage (verify license/ops fit), Nango-style broker or own OAuth service; tokens bound to user identity; never in LLM context; per-provider `aiPolicy` enforced by the gateway.
8. **Discovery**: private OneMind registry exposing manifests (optionally in the official MCP Registry OpenAPI shape and with Server Cards) because the official registry rejects private servers.
9. **Household policy engine**: roles owner, adult, teen, child, guest; primitives from Jellyfin (rating ceiling, tag allow/block, schedule, device approval); alert routing to guardians; kid agents inherit kid limits.
10. **Ecosystem rules**: tiers (Experimental, Beta, Stable like MCP extensions; Bronze to Gold like HA), CLI `onemind app validate|install|enable`, verified publisher namespace, reference implementation plus conformance test before Stable.

### 10.3 Open questions to resolve with evidence before building
- Does Authentik support CIMD and RFC 8707 resource indicators for MCP clients? (UNVERIFIED.)
- Build vs fork Homarr (Apache-2.0) for the dashboard; avoid GPL/AGPL code (Homepage, Glance).
- iOS push: own APNs app or ntfy upstream relay; decide product stance on "no external SaaS" for iOS.
- Strava and other fitness APIs: legal review of AI clauses; read Garmin/Oura/Google Health primary texts (only seen via a secondary blog).
- MHS: monitor for open-source release and published auth/audit requirements.
- Whether Olares exposes MCP (not found), and Umbrel's real tool list (page lists permission categories only).

---

## Sources (all opened unless marked)

MCP: https://modelcontextprotocol.io/specification/versioning · https://modelcontextprotocol.io/specification/2026-07-28/changelog · https://modelcontextprotocol.io/specification/latest/basic/transports · https://modelcontextprotocol.io/specification/latest/basic/authorization · https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation.md · https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices.md · https://modelcontextprotocol.io/extensions/overview.md · https://modelcontextprotocol.io/extensions/tasks/overview.md · https://modelcontextprotocol.io/registry/about.md · https://modelcontextprotocol.io/community/governance.md · https://modelcontextprotocol.io/development/roadmap.md · https://github.com/modelcontextprotocol/ext-apps · https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation · https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation (search result, snippet only)

OS-level MCP and peers: https://umbrel.com/support/advanced/connecting-ai-agents · https://umbrel.com/support/getting-started/whats-new-in-umbrelos-2 · https://github.com/getumbrel/umbrel/releases/tag/2.0.0 · https://reclaimthenet.org/umbrelos-2-cloud-like-self-hosted-server-upgrade · https://www.olares.com/docs/ · https://www.olares.com/docs/developer/cli-agent-skills · https://www.olares.com/docs/manual/olares/settings/roles-permissions · https://www.olares.com/docs/developer/develop/package/manifest · https://www.home-assistant.io/integrations/mcp_server/ · https://backstage.io/docs/ai/mcp-actions · https://github.com/containers/kubernetes-mcp-server · https://gofastmcp.com/integrations/openapi

Other protocols/sandbox: https://a2a-protocol.org/latest/ · https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year · https://lfaidata.foundation/communityblog/2025/08/29/acp-joins-forces-with-a2a-under-the-linux-foundations-lf-ai-data/ · https://agentclientprotocol.com/overview/introduction · https://github.com/agntcy · https://developers.openai.com/apps-sdk/ · https://github.com/kubernetes-sigs/agent-sandbox · https://gvisor.dev/docs/ · https://katacontainers.io/ · https://github.com/firecracker-microvm/firecracker · https://github.com/browser-use/browser-use · SECONDARY: https://axios.com/2026/08/17/a2a-agentic-ai-foundation-open-ai-standards (search result only)

MHS: https://www.anthropic.com/news/model-hardware-standard-research-preview · https://the-decoder.com/anthropic-wants-to-do-for-physical-hardware-what-its-model-context-protocol-did-for-software/ · search-only: https://arxiv.org/pdf/2605.26159 , https://github.com/huzjie/hardmesh

Dashboards: https://github.com/gethomepage/homepage · https://gethomepage.dev/configs/kubernetes/ · https://github.com/homarr-labs/homarr · https://github.com/Lissy93/dashy · https://github.com/glanceapp/glance · https://github.com/linuxserver/Heimdall · https://github.com/causefx/Organizr

Alerting: https://prometheus.io/docs/alerting/latest/alertmanager/ · https://github.com/binwiederhier/ntfy · https://docs.ntfy.sh/config/ · https://unifiedpush.org/ · https://github.com/gotify/server · https://github.com/caronc/apprise · https://github.com/louislam/uptime-kuma

Identity/households: https://jellyfin.org/docs/general/server/users/adding-managing-users · https://www.home-assistant.io/docs/authentication/providers/ · https://github.com/goauthentik/authentik · https://github.com/kanidm/kanidm · https://github.com/lldap/lldap · https://github.com/zitadel/zitadel · https://www.authelia.com/overview/prologue/introduction/

Cloud integration/secrets: https://github.com/NangoHQ/nango · https://infisical.com/docs/documentation/getting-started/introduction · https://github.com/openbao/openbao · https://www.strava.com/legal/api · https://www.strava.com/legal/api_policy · https://sahha.ai/blog/health-api-ai-restrictions/ (SECONDARY)

Plugin ecosystems: https://contributors.home-assistant.io/core/quality-scale/ · https://hacs.xyz/docs/publish/integration/ · https://docs.obsidian.md/Plugins/Releasing/Submit+your+plugin · https://code.visualstudio.com/api/working-with-extensions/publishing-extension · https://backstage.io/docs/overview/what-is-backstage · https://github.com/basecamp/omarchy (bin/omarchy-plugin-validate via gh)
