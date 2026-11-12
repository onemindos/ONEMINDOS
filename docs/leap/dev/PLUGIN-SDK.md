# Plugin system and Plugin SDK (third-party developers)

**Status:** spec, draft 1 (2026-11-12). Not built. Epic ids `DEV-PLG-n`.
**Serves:** research `29` (extension points E1–E10, trust root E9, validator rules §6, CLI §7, security §8, tiers §9, versioning §10); brief `30` B8 (E-socket status), B9 (D-B9.3 principals, D-B9.8 `/v1/plugins`), B11 (widget slot), REC-W11-17 (SDK surface); `13` §3.4 (manifest fields); `docs/strategy/core-alignment.md` PLG-P1, PLG-P2, PLG-B1…B3 (branch `docs/core-architecture`); D-001 (Apache-2.0 SDK), D-003 (modules are apps), D-005 (push carries no content).
**Builds on:** contract `sdk/contracts/poc-v0.md` §3 (actions, approval), §4 (manifest), §9.4 and §11.1 (scan gate), §11.2 (app principals), §11.3 (`/mcp`), §11.5 (namespaces).
**Core rule kept:** a plugin, like an AI agent, can only **request** a change to the OS or to its own data. A human owner approves. The OS executes. Every step is in the hash-chained audit log.

> **Explain it like I am the founder**
> A **plugin** is an app that also adds something *to OneMind itself*: a card on your Home screen, a settings page, a button on an alert, or a new tool Hermes can use.
> It ships as one signed package. Your box checks two signatures (the developer's and OneMind's), checks the scan is fresh, and shows you exactly what it wants before you approve the install.
> Its screen runs in a locked box inside the dashboard (a sandboxed iframe), so it can never see your login or press "Approve". Anything it wants to change becomes a request in your Approvals list.
> Phase 1 is for *your own* plugins on *your own* box. Phase 2 opens the doors to outside developers.

---

## 1. Goals and non-goals

### Goals
| # | Goal | Measured by |
|---|---|---|
| G1 | A third-party developer can build, test and ship a plugin **without changing OneMind's code** | Hello-plugin (§16) installs on a stock hub with zero edits to `core/`, `cmd/` or `dashboard/` |
| G2 | **One manifest, one install path, one scan gate** for apps and plugins | Plugins are installed by `app.install`, scanned by the §9.4 gate, and live in `app-<id>` |
| G3 | Plugin UI can never act as the owner | Bridge has no approve method; a test widget that tries every trick gets 0 approvals (§12) |
| G4 | Plugin AI tools are **request-only** for writes | A write tool called by Hermes over `/mcp` returns an action id in `awaiting_approval`, never a result |
| G5 | Every byte that runs is pinned and signed | Box installs by digest only; publisher signature and OneMind countersignature both verified; revoked plugin disabled in ≤ 6 h online |
| G6 | A fast local loop | `onemind plugin init` → working widget against a mock hub in < 15 min; `validate` < 10 s (29 §7 DX targets) |
| G7 | Same SDK feel in TypeScript, Python and Go for plugin backends | The Hello tool is implemented in all three in the SDK tests |

### Non-goals (phase 1 and 2)
- **Host plugins** (E3 sysext/confext, E4 driver packs, E8 profiles, E10 boot overlays) from third parties. BD-15 keeps them OneMind-only until LT-VM-01 passes and Z-22 is answered.
- **Host grants** (E2: devices, hostNetwork, hostIPC, GPU, real-time). Third-party plugins run under Pod Security `restricted` only. GPU comes with E2 in phase 3.
- **`effect: actuate`** (robots, drones, relays, TAK). Lab-only until LT-VM-18 passes at G4 (leap plan §1). The validator refuses it outside a lab build.
- **Shell plugins** that run in the dashboard's own JavaScript (module federation, script injection). Rejected in §6.3.
- **Desktop plugins** (Z-26) and the Omarchy client pack (REC-W11-13).
- **Paid plugins, revenue share, the "Certified" tier.** Deferred with D-001's pro/open ADR (leap plan §5 item 11).

---

## 2. Plugin versus app, mapped to E1–E10

**Definition.** An **app** is a workload OneMind installs and runs (contract §4). A **plugin** is an app that also declares `spec.extensions`: things it adds to the OS surfaces (UI, AI tools, events, settings, alerts). A plugin may have no workload of its own when it only adds declarative UI (a tile, a typed widget fed by an external URL is *not* allowed; see §6.2), but any tool, event handler or custom widget needs a backend pod.

| Research 29 type | Example | Extension points | Phase | Notes |
|---|---|---|---|---|
| 1 Market app | Uptime Kuma | E1, E6, E7 | **today** (3 apps on main) | Already works; plugins reuse this path |
| 2 Widget / UI extension | Disk-usage card, backup status card | E5, E6 | **1** | Typed templates first, sandboxed iframe second |
| 3 Shell plugin | Omarchy bar widget | none (in-process) | never for third parties | Cannot be sandboxed (29 §8.1) |
| 4 Device / driver adapter | Modbus bridge, SO-101 adapter | E1, E2, E3, E4, E6, E7 | 3+ | Needs E2 grants and actuate; out of founder focus |
| 5 AI skill / tool | "Summarise my uptime incidents" | E6, E7, E1 | **1** (read + write-as-request) | Projected to `/mcp`, REST and CLI |
| 6 Automation / workflow | "When a backup fails, open a repair" | E6, E7 | **2** | Triggers and targets; policies stay owner-authored |
| 7 OS / image profile | Greenhouse box | E8 (E3, E4, E1) | OneMind-only | BD-15 |

### Phase-1 subset of the ten sockets

| Socket | What a plugin gets in phase 1 | Deferred |
|---|---|---|
| **E1** Market/app controller | Install, update, remove via `app.install` / `app.remove`, now also from an OCI reference | Helm charts (BD-10 controller) |
| E2 Capability broker | Nothing. `restricted` pods only | Phase 3 |
| E3, E4, E8, E10 | Nothing (BD-15) | OneMind-only |
| **E5** UI slot | Tiles, typed widgets, sandboxed iframe widgets, settings panels, notification actions, mobile cards (typed only) | Distinct origin per plugin (needs per-app subdomains, UX-P2); iframe widgets on mobile |
| **E6** Capability registry + approval | Tools with `effect: read`, `write`, `destructive`; projected to REST, MCP, CLI | `actuate`; Agent Skills projection |
| **E7** NATS grants | **Gateway-mediated** subscribe and publish in `evt.app.<id>.*` (webhook delivery) | Direct per-plugin NATS user (phase 2, after NATS auth exists on the hub) |
| **E9** Trust root | Digest pinning, publisher signature, owner-enrolled private key, revocation list | OneMind countersignature for third parties (phase 2) |

---

## 3. What exists today

| Piece | Where | State |
|---|---|---|
| Manifest `onemind.app/v1alpha1`, `kind: App` | `sdk/schema/onemind.app.schema.json`, contract §4, §9.3 | On main. No extension fields |
| Validator | `sdk/tools/validate-apps` (Python) | On main. Branch `feat/app-pipeline` adds `app-scaffold`, `app-gate`, `app-readme` |
| Scan record `scan.json` and 7-day rule | contract §11.1; `core/onemind_core/scan.py` | `scan.py` on branch `feat/gateway-agent-mcp` |
| Actions and approval (owner-only approve, agent 403) | `core/onemind_core/actions.py`, `auth.py`, `audit.py` | On main. Action types: `app.install`, `app.remove` only |
| App principals (`agent:<app-id>`, Secret with token) | contract §11.2 | Branch `feat/gateway-agent-mcp` |
| `/mcp` with `list_nodes`, `list_apps`, `request_action` | `core/onemind_core/mcp.py` | Branch `feat/gateway-agent-mcp` |
| Executor `kubectl apply -k` into `app-<id>` | `core/onemind_core/executors.py` | On main. No resource-kind allowlist yet (leap epic E0S) |
| TUF client (go-tuf), signed index | `internal/update/tuf.go` | Branch `feat/onemindd-updater` (OS updates) |
| `onemind` CLI (`node info`, `nodes`, `version`) | `cmd/onemind/main.go` | On main; `update` commands on the updater branch |
| Dashboard (Home, Nodes, Market, Approvals, SignIn) | `dashboard/src/pages/` | On main; app page and trust card on the gwmcp branch |
| Design system `@onemind/ui` | `ui/` | Branch `feat/design-system` (uncommitted) |
| Mobile shell | `mobile/` (Expo, React Native 0.88) | Uncommitted worktree |
| Plugin anything | — | **Nothing built.** E5 is specified only (30 B8) |

**Conflicts to flag (not decided here):**
1. `docs/strategy/core-alignment.md` MOB-P1 and REC-W11-09 say **Capacitor**; the mobile worktree is **Expo / React Native**. This spec works with either for typed cards (§6.6). Iframe widgets on mobile differ by shell. Founder or the mobile spec owner should settle it.
2. The OS repo's bus subjects today are `onemind.node.<id>.status` and `onemind.audit` (contract §1, §3), outside the `tel./evt./cmd./svc.` grammar that research 29 E7 assumes. Plugin subjects in §8 use `evt.app.<id>.<event>`; the fabric/notifications spec (branch `docs/core-architecture`, in progress) must confirm the grammar for the OS.
3. Research 29 §6 uses a top-level `kind: adapter|widget|skill|…`. Contract §4 fixes `kind: App`. Resolved in §4.1 below: extension *types* live under `spec.extensions`, not in `kind`.
4. `docs/security/THREAT-MODEL.md` (branch `docs/security-threat-model`) uses ids E1–E5 for **exploits**. This spec always means **extension points**. Suggest the threat model rename its ids (e.g. X1–X5).

---

## 4. The manifest

### 4.1 Decision: an App with an `extensions` block, not a new `onemind.plugin` kind

| Option | For | Against |
|---|---|---|
| **A. `kind: App` + `spec.extensions` (chosen)** | One schema, one validator, one install action, one scan gate, one namespace, one review, one catalog. A Market app becomes a plugin by adding a block. Matches D-003 ("every module is also a normal Market app") and 29 §6 ("one manifest for every type"). Additive to contract §4 | The App schema grows; needs care to keep `extensions` optional |
| B. New `apiVersion: onemind.plugin/v1alpha1`, `kind: Plugin` | Clean separation | Two install paths, two gates, two catalogs, and an awkward case for every app that is also a plugin (Home Assistant with a card). The pipeline branch would fork |

Plugin "types" from 29 become **extension types** inside `spec.extensions` (`tiles`, `widgets`, `settings`, `tools`, `events`, `alerts`). The manifest moves to `onemind.app/v1` at the Manifest v1 freeze (leap epic E6); until then every new field is optional under `v1alpha1`.

### 4.2 Full example (Hello plugin)
```yaml
apiVersion: onemind.app/v1alpha1
kind: App
metadata:
  id: hello-plugin                    # <= 59 chars (§11.5); publisher namespace below
  name: Hello Plugin
  version: "0.1.0"                    # semver, required
  description: A greeting card, a greeting tool and a settings panel
  category: developer
  icon: icon.svg
  license: Apache-2.0
  source: https://github.com/example-dev/hello-plugin
  publisher: {id: example-dev, name: Example Dev}   # verified namespace from phase 2
spec:
  archs: [amd64, arm64]
  requires: {gpu: false, minMemoryMb: 64}
  manifests: manifests/               # kustomize; E0S resource-kind allowlist applies
  compat:
    onemind: ">=0.3 <1.0"             # plugin API level range (§13)
  plugin:
    principal: true                   # creates plugin:hello-plugin (§7.1)
    secret: hello-plugin-onemind      # gets ONEMIND_GATEWAY_URL, ONEMIND_PLUGIN_TOKEN, ONEMIND_DISPATCH_PUBKEY
    backend: {service: hello, port: 8080}   # where the gateway sends tool calls and events
  permissions:                        # what the plugin may read or ask for; shown at install
    - nodes:read
    - events:subscribe:onemind.node.*.status
    - alerts:raise
    - actions:request:app.install     # may *ask* to install apps; never approve
  egress: []                          # internet domains the pod may reach; default deny
  storage: {data: {size: 256Mi, backup: true}}
  secrets:
    - {name: greeting_api_key, description: "Optional key for a translation API", required: false}
  extensions:
    tiles:
      - {id: open, label: Hello, opens: web}         # launcher tile; no code
    widgets:
      - id: greeting
        title: Greeting
        render: template                              # template | iframe
        template: stat                                # stat | list | progress | status
        source: {tool: greet, args: {}}               # read tool feeds the template
        refresh: 60s
        surfaces: [dashboard, mobile]
      - id: greeting-live
        title: Greeting (live)
        render: iframe
        entry: ui/index.html                          # inside the signed UI layer
        size: {w: 2, h: 2}
        surfaces: [dashboard]
    settings:
      schema: settings.schema.json                    # JSON Schema; host renders the form
    tools:
      - name: greet
        title: Say hello
        effect: read
        description: Returns a greeting for a name.
        input: {type: object, properties: {name: {type: string, maxLength: 64}}, additionalProperties: false}
        output: {type: object, properties: {text: {type: string}}, required: [text]}
        exposure: {mcp: true, rest: true, cli: true}
      - name: set_greeting
        title: Change the greeting word
        effect: write                                 # write | destructive => always an action
        description: Replaces the greeting word for everyone.
        input: {type: object, properties: {word: {type: string, minLength: 1, maxLength: 32}}, required: [word], additionalProperties: false}
        exposure: {mcp: true, rest: true, cli: true}
    events:
      publish: [greeted]                              # becomes evt.app.hello-plugin.greeted
      subscribe: ["onemind.node.*.status"]            # must also be in permissions
    alerts:
      actions:
        - {id: reset, label: "Reset greeting", tool: set_greeting, args: {word: Hello}}
```

### 4.3 Validator rules added to 29 §6 rules 1–10
| Rule | Check | Failure |
|---|---|---|
| P1 | Every `widgets[].source.tool`, `alerts.actions[].tool` names a declared tool | error |
| P2 | `render: template` widget's tool has `effect: read` | error |
| P3 | `effect: actuate` only in a build with the lab flag | error (release), warning (lab) |
| P4 | Every `events.subscribe` pattern is covered by an `events:subscribe:` permission and is not `>` alone | error |
| P5 | `events.publish` names are `[a-z0-9_-]{1,40}`; the subject prefix is added by the OS, never written by the plugin | error |
| P6 | Any tool, iframe widget or event handler requires `spec.manifests` and `spec.plugin.backend` | error |
| P7 | `entry` paths are inside the UI layer, relative, no `..`, no symlinks (29 rule 2) | error |
| P8 | UI bundle has no remote `<script src>` and no inline event handlers (CSP would block them anyway) | error |
| P9 | `egress` entries are hostnames, no wildcards above the registrable domain, no IP literals | error |
| P10 | Tool `input` and `output` are valid JSON Schema 2020-12 with `additionalProperties: false` at the top level | error |
| P11 | An update whose `permissions`, `egress`, `secrets` or tool effects are wider than the installed version is flagged `widens_grants: true` | info (drives the re-approval in §13) |

One Go package (`internal/plugin/validate`) implements 1–10 and P1–P11; the CLI, the CI gate and the box call the same code (PLG-P2). The Python `validate-apps` keeps checking app-only fields until it is retired in favour of the Go validator (DEV-PLG-1).

---

## 5. Typed capabilities and permission prompts

### 5.1 Two lists, two directions
- **`permissions`**: what the plugin may *see or ask for* from the OS.
- **`extensions.tools`**: what the plugin *offers* to people and agents, each with an `effect`.

### 5.2 Permission vocabulary (phase 1)
| Permission | Lets the plugin backend… | Risk shown |
|---|---|---|
| `nodes:read` | `GET /v1/nodes` | Can see your machines (no IPs, serials or MACs; contract §2) |
| `apps:read` | `GET /v1/apps` | Can see what is installed |
| `actions:read:self` | read actions it requested (implicit) | — |
| `actions:request:<type>` | `POST /v1/actions` for that type only | **Can ask you to** install apps / remove apps / … |
| `events:subscribe:<pattern>` | receive matching events | Can see events about … |
| `alerts:raise` | create alerts in the alert centre | Can notify you |
| `egress` list | reach those internet domains (NetworkPolicy + egress proxy) | **Can talk to** example.com |
| `storage.data` | a volume of that size | Stores up to 256 MiB |
| `secrets` | read the owner-entered values | Uses an API key you give it |

**Effects of offered tools** (29 §6 rule 7, contract §3):
| Effect | Called by a person | Called by an agent or automation |
|---|---|---|
| `read` | runs; result returned | runs; result returned; audited as a read |
| `write` | becomes an action; owner approves | becomes an action; owner approves |
| `destructive` | action + step-up confirmation | action + step-up (passkey) |
| `actuate` | refused outside the lab | refused outside the lab |

Owner-authored approval policies (AUT-B1, automation spec) may pre-approve `write` within bounds later. A plugin can never create, edit or see policies. `destructive` is never pre-approvable.

### 5.3 The permission prompt
The install request is an ordinary `app.install` action. The Approvals card for it renders a deterministic summary of the manifest (the gateway computes it, the plugin cannot style it):
```
Install Hello Plugin 0.1.0 by Example Dev                 Risk: Low
Signed by: publisher ✓  OneMind ✓   Scan: pass, 2 days ago   Digest: sha256:4be1…
Can see        your machines · events about machine status
Can ask you to install apps (you approve each one)
Can talk to    nothing on the internet
Stores         up to 256 MiB, included in backups
Adds           1 Home tile · 2 widgets · 1 settings page · 2 AI tools (1 asks you first)
Requested by   person:owner                                [Deny] [Approve]
```
**Risk** is a pure function of the manifest: Low (reads only, no egress), Medium (any `actions:request`, egress or secrets), High (any `destructive` tool or `actions:request:app.remove`). Phase 3 replaces it with the 1–8 trust rating once E2 grants exist.

---

## 6. UI extension points (E5)

### 6.1 The four surfaces
| Surface | What the plugin declares | Who renders it | Code from the plugin? |
|---|---|---|---|
| **Home tile** | `tiles[]`: label, icon, `opens: web` | Dashboard, mobile | No |
| **Widget, typed** | `render: template` + read tool | Dashboard and mobile natively, with `@onemind/ui` | No (data only) |
| **Widget, custom** | `render: iframe` + `entry` | Dashboard, in a sandboxed iframe | Yes (HTML/JS, sandboxed) |
| **Settings panel** | `settings.schema` (JSON Schema) | Host renders a form | No (phase 1); iframe panel phase 3 |
| **Notification action** | `alerts.actions[]`: label → tool + fixed args | Alert centre, phone notifications | No |
| **Mobile card** | widgets with `surfaces: [mobile]` and `render: template` | Mobile shell natively | No |

The principle: **declarative first.** Most plugins need a number, a list or a status, and typed templates give them that with zero code in the dashboard and one rendering on every surface (PLG-P1, PLG-B2). Custom code is the exception and always sandboxed.

### 6.2 Typed templates
The template's read tool returns one of these shapes (JSON Schema published in `sdk/schema/widget-templates.schema.json`):
```json
{"template": "stat", "value": "Hello, Ada", "label": "Greeting", "trend": null, "observed_at": "2026-11-12T10:00:00Z"}
{"template": "list", "items": [{"title": "beelink", "subtitle": "online", "status": "ok"}], "observed_at": "…"}
{"template": "progress", "value": 0.42, "label": "Backup", "observed_at": "…"}
{"template": "status", "state": "ok|warn|error|unknown", "text": "All checks pass", "observed_at": "…"}
```
`observed_at` is required: the host shows stale data as stale, never as live (dashboard freshness rule, B11). A template may not carry URLs that the host would fetch; images come only from the plugin's signed UI layer.

### 6.3 Decision: sandboxed iframe + postMessage bridge, not module federation
| Option | Isolation | Verdict |
|---|---|---|
| Module federation / dynamic `import()` into the dashboard | **None.** Plugin JS shares the dashboard's realm: it can read the owner's token, call `fetch('/v1/actions/…/approve')`, draw a fake approval dialog, and read every other widget | **Rejected.** It breaks the core rule on day one; it is exactly Omarchy's unsandboxed model (core-alignment PLG-B1) |
| Web components in the same document | Shadow DOM is styling isolation, not security | Rejected for third parties |
| **Sandboxed iframe + postMessage bridge (chosen)** | Separate browsing context; no cookies, storage or DOM of the dashboard; network limited by CSP; all OS access through a narrow message API that the gateway re-checks | **Chosen.** Same as MCP Apps `ui://` (29 E5, C-W19-035) and Olares windows |

**Phase-1 isolation, concretely:**
1. The dashboard renders `<iframe sandbox="allow-scripts" src="/v1/plugins/hello-plugin/ui/sha256:4be1…/index.html" referrerpolicy="no-referrer" allow="">`. **No `allow-same-origin`**: the frame gets an *opaque origin*, so it cannot read the dashboard's cookies, `localStorage` or token, and its requests to the gateway carry no credentials. No `allow-forms`, `allow-popups`, `allow-top-navigation`, `allow-modals`.
2. The gateway serves the UI files only by **digest path**, from the verified UI layer, with:
   `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'`
   `connect-src 'none'` means the widget cannot call anything directly, not even its own backend: all data goes through the bridge.
3. The gateway API never answers CORS for origin `null`, so a widget that tries `fetch` gets nothing even if CSP were bypassed.
4. **Phase 3:** each plugin moves to its own origin (`<id>.plugins.<box-host>`, once per-app subdomains and LAN HTTPS exist, UX-P2/SEC-P2), which adds defence in depth for browsers' opaque-origin edge cases.

### 6.4 The bridge protocol
JSON-RPC 2.0 over `postMessage`, modelled on the MCP Apps host protocol so the same widget can later render as an MCP Apps `ui://` view for agents (PLG-B2). Exact method-name alignment with the MCP Apps extension is checked before the bridge is frozen (**UNVERIFIED** today; DEV-PLG-5).

| Method (widget → host) | Params | Host does | Gateway check |
|---|---|---|---|
| `onemind/initialize` | `{protocol: "1"}` | returns context | — |
| `tools/call` | `{name, arguments}` | `POST /v1/plugins/{id}/tools/{name}` with the widget session token | tool declared by *this* plugin; effect rules (§5.2) |
| `onemind/settings.get` | — | returns settings (never secrets) | plugin id match |
| `onemind/events.subscribe` | `{event}` | streams the plugin's own subscribed events | within manifest `events.subscribe` |
| `onemind/ui.resize` | `{h}` | resizes within the grid limits | — |
| `onemind/ui.openLink` | `{url}` | shows "Leave OneMind?" sheet, then opens in a new tab | URL must be in `metadata.source` or `links` |

| Notification (host → widget) | Payload |
|---|---|
| `onemind/context` | `{theme, locale, viewer: {role}, widget: {id, size}, protocol}` (no ids, no names, no tokens) |
| `onemind/event` | `{event, data, observed_at}` |
| `onemind/actionUpdate` | `{action_id, state}` for actions this widget caused |

**There is no approve, deny, navigate-dashboard, read-token or read-other-plugin method, and none can be added** without changing the gateway, because the gateway, not the host page, enforces the rules. The host checks `event.source === iframe.contentWindow` on every message and drops anything else.

**Write from a widget.** `tools/call` on a `write` tool returns `{action_id, state: "awaiting_approval"}`. The **host** (outside the iframe) shows a toast "Hello Plugin asked to change the greeting word. Review in Approvals." The approval sheet is never drawn over the iframe and never inside it (anti-clickjacking).

### 6.5 Settings panels and notification actions
- **Settings:** the host renders a form from `settings.schema.json` with `@onemind/ui` components. "Save" by the owner creates a `plugin.configure` action and approves it in the same confirmation sheet (both entries audited). Values reach the backend as a mounted ConfigMap `plugin-settings` (reloaded on change) and the widget via `onemind/settings.get`.
- **Notification actions:** an alert raised by the plugin may list `actions` by id from the manifest. Tapping one creates the declared tool call with the **fixed** args from the manifest (the alert cannot supply args), which for a `write` tool is an action that still needs approval (NOT-B3). The push payload carries only an alert id (D-005).

### 6.6 Mobile cards
The mobile shell renders `render: template` widgets natively with the same four templates and the same freshness labels, so a plugin gets a phone card with no extra work. Iframe widgets show "Open on the web" on phones in phases 1–2. Phase 3 may host them in a WebView with the same sandbox and bridge, once the shell choice (Expo vs Capacitor, §3 conflict 1) is settled.

---

## 7. Agent tools through MCP (E6, request-only)

### 7.1 Plugin principal
Extends contract §11.2. When `spec.plugin.principal: true`, install creates principal `{id: "plugin:<app-id>", kind: plugin, role: plugin}` with a hashed random token, stored in Secret `spec.plugin.secret` (`ONEMIND_GATEWAY_URL`, `ONEMIND_PLUGIN_TOKEN`, `ONEMIND_DISPATCH_PUBKEY`), revoked and deleted on `app.remove`. `kind: plugin` is new (contract change, D-B9.3 already lists "workload/plugin"). Like an agent it may request and never approve (`is_owner` is false for any non-person). Unlike an agent it may not call `/mcp`.

### 7.2 How tools appear to agents
The gateway's `/mcp` `tools/list` adds every enabled plugin tool as `<app-id>.<tool>`, with MCP tool annotations derived from `effect`:
```json
{"name": "hello-plugin.set_greeting",
 "title": "Change the greeting word (Hello Plugin)",
 "description": "Replaces the greeting word for everyone. This only creates a request: the owner must approve it.",
 "inputSchema": {"type": "object", "properties": {"word": {"type": "string", "minLength": 1, "maxLength": 32}}, "required": ["word"], "additionalProperties": false},
 "annotations": {"readOnlyHint": false, "destructiveHint": false, "openWorldHint": false}}
```
Calling it:
```json
→ {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
   "params": {"name": "hello-plugin.set_greeting", "arguments": {"word": "Ahoy"}}}
← {"jsonrpc": "2.0", "id": 7, "result": {
     "content": [{"type": "text", "text": "Request act_01JD… created. It waits for the owner's approval."}],
     "structuredContent": {"action_id": "act_01JD…", "state": "awaiting_approval"}}}
```
A `read` tool returns the plugin's output as `structuredContent` (validated against `output`; invalid output → tool error, logged). Tool descriptions are plugin-authored text and so **untrusted**: the gateway prefixes the effect sentence itself and caps descriptions at 500 characters; the Approvals card shows the plugin's text labelled as "from the plugin" (leap plan E2: reason shown as untrusted).

### 7.3 The call path
```
Agent ──/mcp──► Gateway ──(read)──► plugin backend POST /onemind/v1/tools/greet   (dispatch token)
                  │
                  └─(write)─► action plugin.invoke {app_id, tool, args, args_sha256} → awaiting_approval
                                 owner approves ─► Gateway ─► backend POST /onemind/v1/tools/set_greeting
                                                               (dispatch token carries action_id)
                                 result ─► action succeeded/failed ─► audit
```
- **Dispatch token:** an Ed25519-signed JWT from the gateway, `aud: plugin:<id>`, `tool`, `args_sha256`, `action_id` (writes), `exp` 60 s, `jti` single-use. The SDKs verify it with `ONEMIND_DISPATCH_PUBKEY`, reject replays, and **refuse to run a write handler without an approved `action_id`**.
- The plugin's backend never gets the caller's token, and the caller never gets the plugin's.
- New action types (contract change): `plugin.invoke` and `plugin.configure`. Both follow §3 states, expiry and idempotency.

---

## 8. Event subscriptions and automation triggers (E7, phase 2 for most)

**Phase 1–2: gateway-mediated.** The hub's NATS has no per-client auth yet (contract v0 shortcut), so plugins do not connect to NATS. The gateway subscribes on their behalf and POSTs matching events to `POST /onemind/v1/events` on the backend (dispatch-token signed), at most 10 per second per plugin, dropping with a counter beyond that.
```json
{"id": "evt_01JD…", "subject": "onemind.node.3f9c2a1b7d4e.status", "time": "2026-11-12T10:00:00Z",
 "data": {"status": "offline", "node_id": "3f9c2a1b7d4e"}}
```
**Publishing:** `POST /v1/plugins/{self}/events/{name}` with the plugin token; the gateway publishes on `evt.app.<app-id>.<name>` (grammar §3 conflict 2), adds `source: plugin:<id>`, and refuses names not in `events.publish`.
**Phase 3:** a per-plugin NATS user with publish/subscribe permissions generated from the manifest (30 B8 E7), once NATS auth exists.

**Automation triggers.** Every declared `events.publish` name appears in the automation editor (AUT-P2) as a trigger "Hello Plugin: greeted". Every declared tool appears as a step. An automation that calls a `write` tool creates an action; an owner-authored policy may pre-approve it within bounds (AUT-B1). The dry run (AUT-B2) lists the plugin tool calls it would make.

---

## 9. Storage and secrets

| Need | Mechanism | Backup | Phase |
|---|---|---|---|
| Plugin data | PVC `data` in `app-<id>`, size from `storage.data.size`, mounted at `/data`; the retain storage class of the box | `backup: true` → included in the box's restic job with the app's pre/post hooks (backups spec) | 1 |
| Settings | Gateway-stored JSON, delivered as ConfigMap | In the gateway's ledger backup | 1 |
| Small UI-only state | none in phase 1 (widgets are stateless; use settings) | — | — |
| Secrets | Owner enters each declared secret in the settings panel → `PUT /v1/plugins/{id}/secrets/{name}` (**owner-only, direct**, not an action, so the value never enters the ledger or audit) → Kubernetes Secret `plugin-secrets` in `app-<id>`, mounted read-only at `/run/secrets/onemind/<name>` | Excluded from normal backups; included only in the separate encrypted secrets package (D-B9.11) | 1 |

Secret rules: never sent to widgets, never in tool results the gateway logs, never echoed back by the API (only `{"name": "greeting_api_key", "set": true, "updated_at": "…"}`), audit records "secret set" with no value or hash. k3s runs with secrets encryption at rest (hardening backlog). The Vault module (APPS.md) takes over storage later behind the same API.

---

## 10. Packaging as an OCI artifact

`onemind plugin pack` produces one OCI artifact, pushed to any OCI registry (GHCR in examples):

| Part | Media type | Content |
|---|---|---|
| Artifact type | `application/vnd.onemind.plugin.v1` | — |
| Config | `application/vnd.onemind.app.manifest.v1+yaml` | `onemind.app.yaml` with every image rewritten to `repo:tag@sha256:…` |
| Layer | `application/vnd.onemind.plugin.manifests.v1.tar+gzip` | `manifests/` (kustomize) |
| Layer | `application/vnd.onemind.plugin.ui.v1.tar+gzip` | `ui/`, `settings.schema.json`, `icon.svg` |
| Layer | `text/markdown` | `README.md` |
| Referrer | `application/vnd.dev.sigstore.bundle.v0.3+json` | publisher signature (cosign) |
| Referrer | `application/spdx+json` | SBOM per image and for the UI bundle |
| Referrer | `application/vnd.in-toto+json` | SLSA provenance from CI |
| Referrer | `application/vnd.onemind.scan.v1+json` | `scan.json` (§11.1 shape + `ui` section), added by the OneMind gate |

Container images are separate OCI images referenced by digest. **Offline:** `onemind plugin pack --offline` writes `hello-plugin-0.1.0.ompkg`, an OCI image-layout tarball with the artifact, its images, all referrers and the latest revocation list (29 §10).

```console
$ onemind plugin pack
✓ validated (rules 1–10, P1–P11) in 1.8 s
✓ ui bundle 41 KiB, 3 files, no remote scripts
✓ image ghcr.io/example-dev/hello-plugin:0.1.0@sha256:9c0e… (amd64, arm64)
✓ artifact ghcr.io/example-dev/hello-plugin-pkg:0.1.0@sha256:4be1…
next: sign it from CI with `onemind plugin publish` (trusted publishing)
```

---

## 11. Signing and the trust root (E9)

### 11.1 The chain
```
OneMind offline root (K-ROOT, 30 B4)
 ├─ OS release keys (updater)
 └─ K-STORE: plugin targets role (TUF delegation "plugins")
      ├─ countersigns: {id, version, artifact digest, tier, permissions_sha256}
      └─ signs: revocations.json (expiring)
Publisher: Sigstore keyless signature from the publisher's CI (OIDC identity = verified publisher repo)
Owner (private tier): an owner-enrolled public key, stored on the box, logged
```
**Install accepts a plugin only if all hold:**
1. The reference is a **digest**. Tags are resolved by the CLI at publish time, never by the box.
2. The publisher signature verifies and its identity matches `metadata.publisher` (phase 2) **or** the artifact is signed by an owner-enrolled private key (phase 1, private tier; marked "Private" everywhere).
3. **Phase 2:** the OneMind TUF `plugins` targets list has an entry with that exact digest, and `permissions_sha256` matches the artifact's manifest (so a re-signed manifest that widens permissions fails).
4. The scan referrer is `pass` and ≤ 7 days old (contract §11.1 rule, applied to plugins).
5. The revocation list is valid (signature, not expired, version not lower than the last seen) and does not list the id, version or digest.
6. `compat.onemind` includes the box's plugin API level.

Verification is Go code in `internal/plugin/verify`, reusing the TUF client of `internal/update` (go-tuf v2.4.2, sigstore-go v1.4.0 per 30 BD-02). The gateway's executor calls it as `onemind plugin verify --json <ref>` before `kubectl apply`, the same pattern it uses for `kubectl` today.

### 11.2 Revocation list
```json
{"schema": "onemind.revocations/v1", "version": 42, "expires": "2026-11-19T00:00:00Z",
 "entries": [
   {"id": "bad-widget", "versions": "<=1.2.0", "digests": ["sha256:…"], "action": "disable",
    "reason": "Exfiltrated settings to an undeclared domain", "link": "https://onemindos.example/advisories/OM-2026-007",
    "since": "2026-11-12T09:00:00Z"},
   {"id": "hello-plugin", "versions": "0.0.9", "action": "disable-capability", "tool": "set_greeting", "reason": "…", "link": "…"}
 ]}
```
- **Actions:** `delist` (hidden from Market, keeps running), `disable` (scale to 0, tools and widgets hidden), `remove` (uninstall, data kept 30 days), `disable-capability` (one tool off).
- **Fetch:** every 6 h, at boot, and before any plugin install or update. Online boxes apply a new entry within one fetch; the gateway also rejects calls to a revoked plugin's tools within 60 s of the list arriving (A06).
- **Expired list:** running plugins keep running with a banner; new installs and updates are refused until a fresh list arrives (USB `.ompkg` or LAN mirror for offline boxes).
- **Owner override:** the owner may keep a revoked private-tier or self-built plugin running; this is an action, needs step-up, and is audited. Never substitutes another publisher's code (29 §8.4).
- **Self-hostable:** the index and revocation feed are static TUF files; a sovereign owner can mirror or run their own (REC-W19-11).

---

## 12. Security model

| Threat | Control | Test |
|---|---|---|
| Widget reads the owner's token or calls approve | Opaque-origin iframe, CSP `connect-src 'none'`, no CORS for `null`, no approve in the bridge | T-PLG-01 hostile widget suite |
| Fake approval UI inside a widget | Approval UI never inside or over an iframe; the real one shows signer, digest and "Requested by plugin:<id>" | T-PLG-02 |
| Plugin backend changes OS state | Its token can only `POST /v1/actions` for declared types; everything else 403; approve 403 | T-PLG-03 |
| Agent uses a plugin's write tool to bypass approval | Writes become `plugin.invoke` actions; SDK refuses writes without an approved `action_id` | T-PLG-04 |
| Plugin lies that a tool is `read` and mutates its own data | Cannot touch OS state (above); review checks effect honesty; reads are audited and rate-limited; revocation `disable-capability` | Review checklist R4 |
| Manifest escapes its namespace (ClusterRoleBinding, privileged, hostPath) | E0S resource-kind allowlist + PSA `restricted` cluster-wide (hardening backlog H-01) | E0S fixtures |
| Update widens permissions silently | P11 + `permissions_sha256` in the countersignature; widening needs a new owner approval | T-PLG-05 (A05) |
| Tag moved to malicious image | Digest-only installs | T-PLG-06 |
| Compromised publisher | Countersignature, scan, revocation within 6 h | T-PLG-07 |
| Prompt injection via tool descriptions or results | Descriptions capped and labelled untrusted; results are data; writes still need approval | Leap E2 injection fixture |
| Data exfiltration | Default-deny egress; declared domains only; widget has no network | T-PLG-08 |
| Event flood | 10 events/s per plugin, bounded queue | T-PLG-09 |
| Secret leakage | Owner-only direct write, never echoed, never to widgets, not in ledger | T-PLG-10 |

AI-assisted review may help human reviewers but never decides pass or fail (29 rule 10).

---

## 13. Versioning and compatibility

| Thing | Version | Rule |
|---|---|---|
| Manifest | `onemind.app/v1alpha1` → `onemind.app/v1` at the Manifest v1 freeze | Additive fields only within a version; a converter ships with v1 |
| Plugin API level | `ONEMIND_PLUGIN_API` (gateway reports it in `GET /v1/instance`), e.g. `0.3`; equals `SYSEXT_LEVEL` major from 1.0 (29 §10) | Box refuses a plugin whose `compat.onemind` excludes it; an OS update that would break an installed plugin is reported before install (gate G8) |
| Bridge protocol | integer `protocol` negotiated in `onemind/initialize` | Host supports current and previous |
| SDK packages | semver, independent of the OS | Major bump only when the API level's major changes |
| Plugin | semver in `metadata.version` | A changed tool `input` that rejects old args, a removed tool or a changed effect is a **major** bump (validator compares with the previous published version) |
| Deprecation | 2 minor OS releases of overlap for any removed bridge method or permission | Listed in `CHANGELOG.md` |

**Update flow:** a plugin update is an `app.install` of a newer digest. If P11 says it widens grants, the Approvals card shows a diff ("New: can talk to api.example.com") and it never auto-updates. Narrower or equal updates follow the owner's update policy (`spec.updates`, contract §9.3).

---

## 14. Developer experience

### 14.1 CLI
| Command | Does | Phase |
|---|---|---|
| `onemind plugin init [--template hello\|widget\|tool] <dir>` | Scaffold manifest, TS backend, widget, tests, Dockerfile, CI workflow with trusted publishing | 1 |
| `onemind plugin validate [dir]` | Rules 1–10, P1–P11; same Go package as box and CI | 1 |
| `onemind plugin dev [--mock \| --hub <url>]` | Local loop with hot reload (§14.2) | 1 |
| `onemind plugin test` | Conformance suite (§15) | 2 |
| `onemind plugin pack [--offline]` | OCI artifact, optional `.ompkg` | 1 |
| `onemind plugin publish` | From CI only (OIDC); signs, pushes, opens the review | 2 |
| `onemind plugin trust add <pubkey>` | Owner enrolls a private-tier signing key on their box (audited) | 1 |
| `onemind plugin sign --key <file>` | Private-tier signature | 1 |
| `onemind plugin install <ref@sha256> \| --file x.ompkg` | Creates the `app.install` action; prints the approval link | 1 |
| `onemind plugin call <id>.<tool> --arg k=v` | Calls a tool as the signed-in person (read runs; write creates an action) | 1 |
| `onemind plugin disable\|remove\|rollback <id>` | As actions | 1 |

### 14.2 `onemind plugin dev`
```console
$ onemind plugin dev --mock
mock hub      http://127.0.0.1:8090   (contract fixtures: 3 nodes, 4 apps; owner and agent tokens printed below)
harness       http://127.0.0.1:8091   (Home grid, Approvals, Settings, MCP inspector)
backend       npm run dev → http://127.0.0.1:8080   (restarts on change)
widget        vite → hot reload into the sandboxed slot
watching onemind.app.yaml … validated ✓
[12:01:07] tools/call greet {"name":"Ada"} → 200 in 4 ms
[12:01:12] tools/call set_greeting {"word":"Ahoy"} → action act_01JD… awaiting_approval (approve it in the harness)
```
- **`--mock`**: an in-process mock gateway (the Python gateway with the `noop` executor, `ONEMIND_ALLOW_UNSCANNED=1`, and dev plugin mode) plus a harness page that hosts the widget with the **same** sandbox, CSP and bridge as the real dashboard, so "works in dev" means "works on the box". The harness has an approval simulator and an MCP inspector that calls tools as an agent.
- **`--hub <url>`**: against a local dev hub (compose on the Mac, or a Lima/k3d VM). The hub must run with `ONEMIND_DEV_PLUGINS=1`, which (like the scan override) is refused by release builds and shows a red "Developer mode" banner on every screen. The plugin installs as tier `dev`, unsigned, with its backend routed to the developer's machine and its UI served from the Vite dev server through the gateway's UI route.
- Hot reload: UI changes reload the iframe; backend changes restart the process; manifest changes re-validate and re-register tools.

---

## 15. Testing harness and test plan

### 15.1 What developers get
| Language | Package | Gives |
|---|---|---|
| TypeScript | `@onemind/plugin-testing` | `createMockHub()`, `mountWidget()` (jsdom + real bridge host), `callTool()` as person or agent, `approve()`, `dispatchEvent()` |
| Python | `onemind-plugin[testing]` | pytest fixtures `mock_hub`, `dispatch`, `approve` |
| Go | `github.com/onemindos/onemindos/sdk/plugin-go/plugintest` | `httptest` dispatcher with signed tokens |

`onemind plugin test` runs the conformance suite: validate; install on a throwaway k3d hub; ready within 120 s; each `read` tool answers within 2 s with schema-valid output; each `write` tool returns an action and runs only after approval; events deliver; `app.remove` leaves no objects in `app-<id>`, no principal, no Secret.

### 15.2 Acceptance tests for this spec
| Id | Test | Pass when |
|---|---|---|
| T-PLG-01 | Hostile widget tries `document.cookie`, `localStorage`, `parent.document`, `fetch('/v1/actions/x/approve')`, `top.location=`, `window.open`, forged `postMessage` to the host from another frame | 0 successes; each attempt blocked by sandbox, CSP or source check |
| T-PLG-02 | Widget draws a look-alike approval dialog | The real approval is only possible in the host Approvals UI; the e2e test proves clicks in the iframe never reach approve |
| T-PLG-03 | Plugin token calls `POST /v1/actions/{id}/approve`, `/mcp`, `GET /v1/apps` without `apps:read`, `POST /v1/actions` with an undeclared type | 403 `permission_denied` for each; audited |
| T-PLG-04 | Hermes calls `hello-plugin.set_greeting` over `/mcp` | Action `awaiting_approval` with requester `agent:hermes-agent`; backend not called until owner approves; audit has both ids |
| T-PLG-05 | Update adds an `egress` domain | Approvals shows the diff; no auto-update; countersignature mismatch if only the manifest was edited |
| T-PLG-06 | Install by tag, by wrong digest, unsigned, wrong signer, bad schema, stale scan, expired revocation list | Each refused with a specific error (A04) |
| T-PLG-07 | Revocation entry `disable` published | Online box disables within one fetch; tool calls rejected within 60 s (A06) |
| T-PLG-08 | Backend fetches an undeclared domain | Connection refused by NetworkPolicy/egress proxy |
| T-PLG-09 | Plugin publishes 1000 events/s | Gateway stays healthy; excess dropped and counted |
| T-PLG-10 | Secret set, then read via API, widget, logs, ledger, audit | Value appears only in the mounted file |
| T-PLG-11 | Hello tutorial followed on a clean Mac | Working widget against `--mock` in < 15 min (G6) |
| T-PLG-12 | Typed widget on dashboard and mobile | Same data; stale label after 2× `refresh` |

---

## 16. Hello-plugin tutorial (TypeScript)

Goal: a card that greets you, a read tool `greet`, a write tool `set_greeting` that waits for approval, a settings panel, and an event. About 15 minutes.

**1. Scaffold**
```console
$ onemind plugin init --template hello hello-plugin && cd hello-plugin
created onemind.app.yaml, settings.schema.json, src/server.ts, ui/index.html, ui/main.ts,
        manifests/, Dockerfile, test/hello.test.ts, .github/workflows/publish.yml
$ npm install
```
The manifest is the one in §4.2.

**2. `settings.schema.json`**
```json
{"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
 "properties": {"emoji": {"type": "boolean", "title": "Add a wave emoji", "default": false}},
 "additionalProperties": false}
```

**3. Backend: `src/server.ts`**
```ts
import { createPlugin, type ToolContext } from "@onemind/plugin/server";
import { readFile, writeFile } from "node:fs/promises";

const STATE = "/data/greeting.json";

interface Settings { emoji?: boolean }
interface GreetIn { name?: string }
interface GreetOut { template: "stat"; value: string; label: string; observed_at: string }
interface SetIn { word: string }

async function loadWord(): Promise<string> {
  try {
    return JSON.parse(await readFile(STATE, "utf8")).word as string;
  } catch {
    return "Hello";
  }
}

const plugin = createPlugin<Settings>({ id: "hello-plugin" });

// effect: read. Runs directly when a person, widget or agent calls it.
plugin.tool<GreetIn, GreetOut>("greet", async (input, ctx: ToolContext<Settings>) => {
  const word = await loadWord();
  const wave = ctx.settings.emoji ? " 👋" : "";
  return {
    template: "stat",
    value: `${word}, ${input.name ?? "friend"}${wave}`,
    label: "Greeting",
    observed_at: new Date().toISOString(),
  };
});

// effect: write. The SDK only runs this with a dispatch token that carries an
// approved action id, so it can never run on an agent's say-so alone.
plugin.tool<SetIn, { ok: true }>("set_greeting", async (input, ctx) => {
  await writeFile(STATE, JSON.stringify({ word: input.word }));
  await ctx.events.publish("greeted", { word: input.word, action_id: ctx.actionId });
  return { ok: true };
});

// Gateway-mediated subscription (permission events:subscribe:onemind.node.*.status).
plugin.on("onemind.node.*.status", async (event, ctx) => {
  const data = event.data as { status?: string; node_id?: string };
  if (data.status === "offline") {
    await ctx.alerts.raise({
      severity: "warning",
      title: "A machine went offline",
      body: `Node ${data.node_id} stopped sending heartbeats.`,
      actions: ["reset"], // ids from manifest extensions.alerts.actions
    });
  }
});

plugin.listen(8080); // verifies dispatch tokens, serves /onemind/v1/tools/* and /onemind/v1/events, /healthz
```

**4. Widget: `ui/index.html`**
```html
<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><link rel="stylesheet" href="./style.css"></head>
  <body>
    <main>
      <p id="greeting" aria-live="polite">…</p>
      <form id="change"><input id="word" maxlength="32" aria-label="New greeting word"><button>Ask to change</button></form>
      <p id="status" role="status"></p>
    </main>
    <script type="module" src="./main.js"></script>
  </body>
</html>
```

**5. Widget: `ui/main.ts`** (bundled to `main.js` by `onemind plugin pack`)
```ts
import { connect } from "@onemind/plugin/widget";

const bridge = await connect({ protocol: 1 }); // postMessage JSON-RPC to the host
const out = document.getElementById("greeting")!;
const status = document.getElementById("status")!;

async function refresh(): Promise<void> {
  const r = await bridge.tools.call<{ value: string }>("greet", { name: "owner" });
  out.textContent = r.value;
}

document.getElementById("change")!.addEventListener("submit", async (e) => {
  e.preventDefault();
  const word = (document.getElementById("word") as HTMLInputElement).value.trim();
  if (!word) return;
  const r = await bridge.tools.call("set_greeting", { word });
  // A write tool never returns a result here: it returns a pending request.
  if (r.kind === "action") status.textContent = "Sent for approval. Check Approvals.";
});

bridge.on("onemind/actionUpdate", (u) => {
  if (u.state === "succeeded") { status.textContent = "Approved and done."; void refresh(); }
  if (u.state === "cancelled") status.textContent = "The owner said no.";
});
bridge.on("onemind/context", (c) => document.documentElement.dataset.theme = c.theme);

await refresh();
```

**6. Manifests and image**
```yaml
# manifests/kustomization.yaml
resources: [deployment.yaml, service.yaml, pvc.yaml]
```
```yaml
# manifests/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata: {name: hello}
spec:
  replicas: 1
  strategy: {type: Recreate}
  selector: {matchLabels: {app: hello}}
  template:
    metadata: {labels: {app: hello}}
    spec:
      automountServiceAccountToken: false
      securityContext: {runAsNonRoot: true, runAsUser: 10001, seccompProfile: {type: RuntimeDefault}}
      containers:
        - name: hello
          image: ghcr.io/example-dev/hello-plugin:0.1.0   # pack rewrites to @sha256
          ports: [{containerPort: 8080}]
          envFrom: [{secretRef: {name: hello-plugin-onemind}}]
          readinessProbe: {httpGet: {path: /healthz, port: 8080}}
          resources: {requests: {cpu: 10m, memory: 32Mi}, limits: {cpu: 200m, memory: 64Mi}}
          securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}}
          volumeMounts:
            - {name: data, mountPath: /data}
            - {name: settings, mountPath: /run/onemind/settings, readOnly: true}
      volumes:
        - {name: data, persistentVolumeClaim: {claimName: data}}
        - {name: settings, configMap: {name: plugin-settings, optional: true}}
```
`service.yaml` exposes port 8080 as `hello`; `pvc.yaml` claims `data` (256Mi). The Dockerfile is a two-stage Node 22 build ending in a distroless non-root image.

**7. Test: `test/hello.test.ts`**
```ts
import { describe, it, expect } from "vitest";
import { createMockHub } from "@onemind/plugin-testing";

describe("hello-plugin", () => {
  it("greets on read, and only writes after approval", async () => {
    const hub = await createMockHub({ plugin: "." });
    expect((await hub.asPerson().callTool("greet", { name: "Ada" })).value).toBe("Hello, Ada");

    const req = await hub.asAgent("hermes-agent").callTool("set_greeting", { word: "Ahoy" });
    expect(req).toMatchObject({ kind: "action", state: "awaiting_approval" });
    expect((await hub.asPerson().callTool("greet", { name: "Ada" })).value).toBe("Hello, Ada");

    await hub.asOwner().approve(req.action_id);
    expect((await hub.asPerson().callTool("greet", { name: "Ada" })).value).toBe("Ahoy, Ada");
    expect(hub.audit().at(-1)).toMatchObject({ requester: "agent:hermes-agent", approver: "person:owner" });
    await hub.close();
  });
});
```

**8. Run, pack, install on your own box**
```console
$ onemind plugin dev --mock                 # iterate
$ npm test && onemind plugin test           # conformance (phase 2)
$ onemind plugin pack
$ onemind plugin sign --key ./dev.key   # private tier, phase 1
$ onemind plugin install ghcr.io/example-dev/hello-plugin-pkg@sha256:4be1… --hub https://hub.local
action act_01JE… awaiting_approval → approve it in Approvals (shows permissions, signer, scan)
```

### The same tools in Python and Go
```python
# Python: onemind-plugin
from onemind_plugin import Plugin, ToolContext

plugin = Plugin("hello-plugin")

@plugin.tool("greet", effect="read")
async def greet(inp: dict, ctx: ToolContext) -> dict:
    return {"template": "stat", "value": f"Hello, {inp.get('name', 'friend')}",
            "label": "Greeting", "observed_at": ctx.now_iso()}

@plugin.tool("set_greeting", effect="write")   # SDK refuses to run without an approved action_id
async def set_greeting(inp: dict, ctx: ToolContext) -> dict:
    (ctx.data_dir / "greeting.json").write_text(f'{{"word": "{inp["word"]}"}}')
    return {"ok": True}

plugin.run(port=8080)
```
```go
// Go: github.com/onemindos/onemindos/sdk/plugin-go
p := plugin.New("hello-plugin")
plugin.Tool(p, "greet", plugin.Read, func(ctx plugin.Ctx, in GreetIn) (GreetOut, error) {
	return GreetOut{Template: "stat", Value: "Hello, " + in.Name, Label: "Greeting", ObservedAt: ctx.Now()}, nil
})
plugin.Tool(p, "set_greeting", plugin.Write, func(ctx plugin.Ctx, in SetIn) (OK, error) {
	return OK{OK: true}, os.WriteFile(filepath.Join(ctx.DataDir(), "greeting.json"), mustJSON(in), 0o600)
})
log.Fatal(p.ListenAndServe(":8080"))
```

---

## 17. Publishing and review

| Tier | Who | Checks | Installable on | Phase |
|---|---|---|---|---|
| **Dev** | Developer | Validator only | A hub with `ONEMIND_DEV_PLUGINS=1` (never a release build) | 1 |
| **Private** | Owner, for own boxes | Validator + local scan; signed with an owner-enrolled key | The owner's boxes | 1 |
| **OneMind** | First party | Full gate + human review; no exemptions | All | 1 |
| **Community** | Any publisher | Automated review (rules 1–10, P1–P11), scan, provenance, countersigned | All boxes; hidden unless the owner turns community plugins on (leap plan §5 item 8) | 2 |
| **Verified** | Verified publisher (domain + org) | Automated + human review of permissions, effects and egress | All | 2 |
| Certified | Verified + agreement | Lab test on reference hardware | All | later (D-001 ADR) |

**Publishing flow (phase 2).**
1. Developer tags a release; the generated workflow runs `onemind plugin publish` with GitHub OIDC (trusted publishing; no long-lived keys).
2. It packs, signs keyless, pushes the artifact, and opens a PR on the public plugin index repo with `{id, version, digest, publisher}`.
3. The index CI runs the same validator and the §9.4 gate on the artifact (images, UI bundle with ClamAV, gitleaks and osv-scanner on its lockfile, manifests via kubeconform and the E0S allowlist, k3d smoke test with the conformance suite).
4. A human reviewer uses the checklist: R1 description matches behaviour; R2 every permission is used; R3 egress justified; R4 each tool's effect is honest; R5 writes are idempotent or carry an idempotency key; R6 removal guide present.
5. Merge → OneMind signs the TUF `plugins` targets entry (K-STORE). Boxes see it on the next index fetch.
6. Daily rescan; a new CRITICAL or malware hit → revocation `delist` or `disable` and an alert to owners who have it.

---

## 18. Phased build plan

**Phase 1 — the founder's own plugins on his own box** (after leap epics E0, E0S, E2; aligns with Manifest v1 freeze E6)
**Phase 2 — open to developers** (after phase 1 is in daily use and the identity floor E8 lands)
**Phase 3 — deeper sockets** (E2 grants, direct NATS users, distinct origins, mobile iframe widgets, `actuate` after LT-VM-18)

| Epic | Title | Size | Phase | Depends on | Owns (files) | Acceptance |
|---|---|---|---|---|---|---|
| DEV-PLG-1 | Manifest `extensions`, `permissions`, `plugin`, `compat` + Go validator (rules 1–10, P1–P11) | M | 1 | Contract amendment (serialized), leap E6 | `sdk/schema/onemind.app.schema.json` (hotspot), `sdk/schema/widget-templates.schema.json`, `internal/plugin/validate/` | §4.2 validates; each P-rule has a failing fixture; < 10 s |
| DEV-PLG-2 | TS SDK `@onemind/plugin` (`/server`, `/widget`) | M | 1 | 1 | `sdk/plugin-ts/` | Hello backend and widget build; dispatch-token verify and write guard unit-tested |
| DEV-PLG-3 | Gateway plugin registry, `kind: plugin` principal, `plugin.invoke` / `plugin.configure`, `/v1/plugins/*` | M | 1 | 1, gwmcp merged, E0S | `core/onemind_core/plugins.py`; one registration line in `app.py` (hotspot); contract §12 text | T-PLG-03, T-PLG-04 (REST path) |
| DEV-PLG-4 | Tool projection to `/mcp` and CLI | S | 1 | 3 | extension in `core/onemind_core/mcp/catalog.py` (after DEV-MCP-1 turns `mcp.py` into a package); `cmd/onemind/cli/plugin.go` | T-PLG-04 over MCP; `onemind plugin call` |
| DEV-PLG-5 | Widget host: typed templates + sandboxed iframe + bridge + UI route with CSP | L | 1 | 3, design system | `dashboard/src/plugins/`; one route line in `App.tsx` (hotspot); UI route in `plugins.py` | T-PLG-01, T-PLG-02, T-PLG-12 (dashboard) |
| DEV-PLG-6 | Settings panel + secrets API | S | 1 | 3, 5 | `dashboard/src/plugins/Settings.tsx`; `plugins.py` | T-PLG-10; settings round-trip |
| DEV-PLG-7 | OCI pack, private-tier sign, `install` by digest, `onemind plugin verify` | M | 1 | 1 | `cmd/onemind/cli/plugin.go`, `internal/plugin/oci/`, `internal/plugin/verify/` | T-PLG-06 (private tier subset) |
| DEV-PLG-8 | `onemind plugin dev` (mock hub, harness, hot reload) + `init` templates | M | 1 | 2, 5, 7 | `internal/plugin/dev/`, `sdk/plugin/harness/`, `sdk/templates/plugin-hello/` | T-PLG-11 |
| DEV-PLG-9 | Revocation list client + TUF `plugins` delegation + countersignature check | L | 1 (list) / 2 (countersign) | 7, updater merged (shared TUF client), K-STORE | `internal/plugin/verify/`, `os/` TUF repo tooling (with ossec owner) | T-PLG-06 full, T-PLG-07 |
| DEV-PLG-10 | Events (gateway-mediated), alerts with actions, automation triggers | M | 2 | 3, notifications + automation specs | `core/onemind_core/plugin_events.py` | T-PLG-09; alert action → action |
| DEV-PLG-11 | Plugin data volume + backup hooks | S | 2 | 3, backups spec | `plugins.py` (install hook); backups module owns restic | Restore of Hello data on a fresh VM |
| DEV-PLG-12 | Scan gate for plugin artifacts (UI bundle, referrer scan) | M | 2 | 7, pipeline merged | `sdk/tools/app-gate` extension (pipeline owner), `.github/workflows/ci-plugins.yml` | EICAR in UI bundle blocked; stale scan → 409 |
| DEV-PLG-13 | Testing harness (TS, Python, Go) + `onemind plugin test` conformance | M | 2 | 2, 8 | `sdk/plugin-testing-ts/`, `sdk/plugin-py/`, `sdk/plugin-go/`, `internal/plugin/conformance/` | Hello passes in all three languages (G7) |
| DEV-PLG-14 | Publish from CI (OIDC), public plugin index repo, review checklist, tiers in Market | M | 2 | 9, 12 | `cmd/onemind/cli/plugin.go` (publish), index repo, `dashboard/src/pages/Market.tsx` tier filter | A third-party test plugin goes from tag to installable in < 1 day |
| DEV-PLG-15 | Mobile cards (typed templates) | S | 2 | 5, mobile shell | `mobile/src/plugins/` | T-PLG-12 on Android and iPhone |
| DEV-PLG-16 | Docs: tutorial, reference, bridge spec, on the website and served over MCP | S | 2 | 8, 13 | `site/` docs section, `docs/leap/dev/PLUGIN-SDK.md` | A new developer completes §16 from the website alone |

**Critical path (phase 1):** 1 → 2 → 3 → (4, 5) → 6 → 7 → 8 → 9 (list). About 5 M/L-weeks of build at the leap plan's capacity, so it starts after L1 (wk 5) and is usable by the founder around wk 9–10, before phase 2.

## 19. Ownership and no-collision rules

| Area | Owner (branch, when cut) | Rule |
|---|---|---|
| `core/onemind_core/plugins.py`, `plugin_events.py` | `feat/plugins-core` | One module per feature; never edit `actions.py` beyond adding the two action types in one serialized commit |
| `core/onemind_core/app.py` route registration | **hotspot**, serialized | One line per module |
| `core/onemind_core/mcp/` | gwmcp owns until merged, then the MCP stream (DEV-MCP-1) | `feat/plugins-core` adds projection through `mcp/catalog.py` in one PR agreed with the MCP owner |
| `internal/plugin/{validate,verify,oci,dev,conformance}/` | `feat/plugins-sdk-go` | Reuse `internal/update` TUF code by import; extracting a shared package is a separate agreed PR with the updater owner |
| `cmd/onemindd/main.go` | **hotspot** | Not touched by this spec (verification runs in the CLI binary) |
| `cmd/onemind/cli/plugin.go` | `feat/plugins-sdk-go` | Registration is one serialized line in `cmd/onemind/cli/root.go` (CLI stream). These commands deliver DEV-CLI-11 |
| `sdk/schema/*`, `sdk/contracts/poc-v0.md` | **hotspot**, contract PR | A §12 "plugins" amendment PR that every stream adopts |
| `sdk/plugin-ts/`, `sdk/plugin-testing-ts/`, `sdk/plugin-py/`, `sdk/plugin-go/`, `sdk/templates/`, `sdk/plugin/harness/` | `feat/plugins-sdk` | New directories only |
| `dashboard/src/plugins/` | `feat/plugins-ui` | `App.tsx` route line serialized; uses `@onemind/ui` from the design branch |
| `mobile/src/plugins/` | mobile owner | After the mobile shell lands |
| `os/versions.lock.yaml` | **hotspot** | New pins (cosign, sigstore-go, osv-scanner) in one serialized commit |
| `.github/workflows/ci-plugins.yml` | `feat/plugins-sdk` | New file; does not edit `ci-apps.yml` |

---

## 20. Founder decisions this spec needs
1. **Confirm** the manifest choice (§4.1: App + `extensions`, no new kind).
2. **Confirm** iframe + bridge and the rejection of module federation (§6.3).
3. **Confirm** phase 1 = private tier + first-party only; community plugins off by default in phase 2.
4. Add `kind: plugin` principals and the `plugin.invoke` / `plugin.configure` action types to the contract (§7).
5. Settle Expo vs Capacitor for mobile (§3 conflict 1) before DEV-PLG-15.
6. Confirm the OS subject grammar for plugin events (§3 conflict 2).
