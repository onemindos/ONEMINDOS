<!-- SPDX-License-Identifier: Apache-2.0 -->
# AI agents over MCP: umbrelOS 2.1 study and the OneMind design

**Study id:** U2-AGT · **Date:** 2026-11-12 · **Status:** proposal · **Epics:** U2-AGT-1 … U2-AGT-11
**Compared:** umbrelOS `2.1.0-beta.1`, commit `6f357e18d0a4` (read-only source), and OneMind `main` at `a26f6ba` plus the in-flight branches `feat/gateway-agent-mcp` (gwmcp), `feat/core-net` (net) and `feat/ui-leap` (uileap).
**Builds on, does not replace:** [`docs/leap/dev/MCP.md`](../leap/dev/MCP.md) (DEV-MCP-1 … -12). This page adds what the umbrelOS comparison shows is missing from that spec. Where the two overlap, MCP.md is the source of truth and this page points at it.

> **Explain it like I am the founder**
> Yes, umbrelOS 2.1 lets AI agents (Claude Code, Codex, Cursor, OpenClaw, Hermes and their own Hermes app, Murmur) run the box over MCP. It looks great, and it is fast to set up: pick your agent, tick what it may touch, copy one line. But once you say yes, **the agent acts immediately and as you**. It can install and uninstall apps, delete virtual machines, restart the box and install OS updates with no second question. Every agent you connect shares **one** set of permissions. The setup flow even suggests pasting the secret key into the agent's chat.
> OneMind keeps the part people love (one-minute setup, an agent that can actually do things, a live "your agent just connected" moment) and changes the rule underneath: **each agent is its own identity with its own limits, it asks, and you approve on your phone with the facts the box worked out, not the agent's words.** The key never goes through a chat. Everything an agent did is in the tamper-evident log, and one tap pauses all of them.

**Legal boundary.** umbrelOS is licensed PolyForm Noncommercial 1.0.0 (checked at the commit above, `LICENSE.md`). This page describes its behaviour and cites file paths. Nothing here, and nothing built from this page, copies its code, UI text, icons, images or translations. Every OneMind component below is our own code or a dependency with a permissive licence recorded at a pinned version (§4.1).

---

## 1. How umbrelOS does it

### 1.1 Architecture

```
 Agent (Claude Code, Codex, Cursor, OpenClaw, Hermes, Murmur, any MCP client)
   │  HTTP (the UI recommends plain http on the LAN), Authorization: Bearer <MCP token>
   ▼
 lan-ingress ──► umbreld Express app ── app.use('/mcp', mcp.router)
                    │
                    ├─ authorize: bearer → token id (sha256 compare); disabled == invalid (401)
                    ├─ /mcp/files/download, /mcp/files/upload   (raw HTTP side channel, re-authenticated)
                    └─ JSON-RPC: re-authenticate after body read → record client identity →
                       build a fresh McpServer per request (stateless) with tools registered
                       from the ONE global permission set → tool → internal tRPC caller
                       running as the owner account
```

| Piece | Where (at `6f357e18d0a4`) | What it does |
|---|---|---|
| Mount | `packages/umbreld/source/modules/server/index.ts` (line 255) | Mounts the MCP router at `/mcp` on the main umbreld HTTP app |
| Module | `packages/umbreld/source/modules/mcp/mcp.ts` | Settings store (`enabled`, `tokens`, `permissions`), token minting and checking, permission checks, file-grant hygiene, in-memory activity, background app-operation tickets |
| Endpoint | `packages/umbreld/source/modules/mcp/server.ts` | Express router, bearer auth, file transfer guard, per-request `McpServer` with dynamic `instructions`, JSON-RPC error mapping, 4 MB body cap |
| Owner API | `packages/umbreld/source/modules/mcp/routes.ts` | tRPC for the dashboard: `getSettings`, `listTokens`, `enable`, `createToken`, `revokeToken`, `disable`, `setPermissions` (all `privateProcedure`) |
| Tools | `packages/umbreld/source/modules/mcp/tools/{system-info,apps,files,machines,system-management,shared}.ts` | 40+ tools, each a thin call into the internal tRPC router or the machines module |
| SDK | `packages/umbreld/package.json` | `@modelcontextprotocol/server`, `/node`, `/client` 2.0.0, `legacy: 'stateless'` handler |
| Restore hook | `packages/umbreld/source/index.ts` (around line 312) | On the first start after a backup restore, `mcp.reset()` wipes tokens and grants so restored credentials never work on new hardware |
| Settings UI | `packages/ui/src/routes/settings/mcp/{index,intro,pitch-replay,constellation,magic-rings,access,connect,status-card,agents}.tsx/ts` | Animated intro, agent picker, permission grants, show-once token, connect ceremony, steady-state agent list |
| Machine console | `packages/umbreld/source/modules/machines/machines.ts` (agent control, 60 s timeout); `packages/ui/src/features/machines/components/{machine-agent-presence,machine-agent-overlay,agent-pointer}.tsx`, `agent-access/` | Shows which agent drives a VM, its pointer, and asks before a person takes over |
| Shortcuts | `packages/umbreld/source/modules/shortcuts/{routes,fetch-page-metadata}.ts` | Home-screen links with fetched title and icon. **Not agent-related**: no MCP tool reads or writes shortcuts |
| `.agents/` | `.agents/skills/umbreld-vm-test-authoring/SKILL.md` | A developer skill that teaches coding agents to write umbreld VM tests. It ships nothing to users. `packages/os/skills` does not exist at this commit |

### 1.2 Credentials

- A token is `umbrelmcp_<32 hex id>_<64 hex secret>`. Only the sha256 of the secret is stored, compared in constant time. At most 20 tokens. Each has a label and an optional agent type; it is shown once.
- MCP has one on/off switch. Turning it off keeps tokens and grants. Off and wrong-token give the same 401, so a scanner cannot tell whether MCP is on.
- Authentication runs twice: before the body is read and again after, so a token revoked during a slow upload cannot dispatch.
- Activity (last request, and up to 10 client identities per token taken from MCP `clientInfo` or the 2026-07-28 `_meta` identity) is **memory only**. It drives the "connected a moment ago" line and is lost on restart.
- No expiry, no rate limit, no pending cap (none exist because nothing is pending), no persistent per-call audit. Tool calls are written to the service log with field **names** only.

### 1.3 Permissions

One permission object for the whole device, **shared by every token** (`McpPermissions` in `mcp.ts`; the UI states the grants apply to every agent):

| Grant | Values | Unlocks |
|---|---|---|
| `apps` | `all` or app ids | full control of those apps: status, details, logs, start, stop, restart, update, settings, move or reset data, **uninstall** |
| `appStore` | bool | search the store and **install** (the new app is then auto-granted) |
| `files` | `all` or folders under Home, or the External or Network roots | list, create folder, copy, move, rename, trash; search only with full Home access; download and upload over `/mcp/files/*` |
| `manageSystem` | bool | **install OS update**, **restart device**, set hostname, set release channel, network settings, system logs |
| `machines` | `all` or machine ids | start, stop, force stop, restart, settings, **delete** (and its disk), screenshot, keyboard and mouse control |
| `createMachines` | bool | create a VM from a catalog image or an ISO (then auto-granted) |

Always available while MCP is on: device info and resources, OS update check, notifications, the installed app list and the machine list.

How the checks work:
- **Tool list follows the grants.** Tools for ungranted areas are not registered at all, and the server `instructions` (rebuilt per request) list what is and is not granted, tell the agent that missing access can be turned on in Settings, and that new tools appear after a reconnect.
- **Every tool re-checks** with an `assert…Access` call at run time, so a grant removed mid-session takes effect on the next call.
- **Files are path-contained after symlink resolution.** App root entries and the app `hooks` directory are read-only through MCP (hooks run on the host). Uploads must stay inside the grant, including the temporary upload file. Deleting a granted Home folder removes its grant through a file watcher. No file is ever replaced: name clashes are "keep both" or the agent must ask the user.
- **Destructive operations are irreversible and immediate**: uninstall deletes app data (not recoverable from Trash), `delete_machine` deletes the disk, `install_os_update` and `restart_device` act at once. Tool annotations (`destructiveHint` and friends) are set, but they are hints for the client; the server asks no one.
- **Agents act as the owner.** File and tool calls run with the owner account id and `actor: 'system'` (`server.ts`, `mcpFilesGuard`). Household members cannot connect an agent limited to their own rights.

### 1.4 What agents get (tools at this commit)

| Area | Tools | Gate |
|---|---|---|
| System info | `get_system_info`, `get_system_resources`, `check_os_update`, `get_notifications` | always |
| Apps | `list_apps`, `get_app_status` | always |
| | `get_app_details`, `get_app_logs` (≤ 500 lines, clipped), `start_app`, `stop_app`, `restart_app`, `update_app`, `uninstall_app`, `set_app_settings`, `move_app_data`, `reset_app_data` | `apps` |
| App Store | `search_app_store`, `get_app_store_details`, `install_app` | `appStore` |
| Files | `list_directory`, `create_directory`, `copy`, `move`, `rename`, `trash`, `search_files`; HTTP download and upload | `files` (+ app folders via `apps`) |
| System | `install_os_update`, `get_os_update_status`, `restart_device`, `set_hostname`, `set_release_channel`, `get_network_settings`, `get_system_logs` | `manageSystem` |
| Machines | `list_machines` (always), `get_machine_details`, `start/stop/restart/force_stop_machine`, `retry_machine_install`, `eject_machine_install_media`, `update_machine_settings`, `delete_machine`, `get_machine_screenshot`, `control_machine` | `machines` |
| | `list_os_images`, `create_machine` | `createMachines` |

Long app operations return `{accepted: true}` at once and run in the background; the last failure per app is kept in memory (10 at most) and surfaced through status. Errors have the data directory path replaced with a placeholder.

### 1.5 User-visible flow, and the "ask an agent to set it up" path

1. **Settings → AI agents (MCP).** First visit plays an animated pitch: agents orbiting the box, scripted chat demos (install an app, organise a media folder, troubleshoot from logs, drive a Windows or Android VM). A beta warning says agents make real changes.
2. **Pick an agent.** Tiles: Murmur, Hermes Agent, OpenClaw, Claude Code, Codex; Cursor and "any other agent" as chips (`routes/settings/mcp/agents.ts`).
3. **Choose access before any token exists.** Apps, folders, App Store, system management, machines. The screen says these apply to every agent.
4. **Enable.** A short "enabling" beat, then the token is minted and shown once.
5. **Connect ceremony** (`connect.tsx`). For the chosen agent: a ready snippet with the token inside (a `claude mcp add` line, a Codex TOML block, a Cursor JSON block and one-click deeplink, an OpenClaw CLI line, a Hermes YAML block). For agents that edit their own config, **a plain-language message to paste into the agent's chat that contains the endpoint and the bearer token** and asks the agent to add it to its global MCP config. This is the "ask an agent to set it up" path: the agent configures itself, but the secret now sits in the chat transcript and in whatever the model provider logs.
6. **Live hello.** The dashboard polls; as soon as the token makes its first request, the card flips to connected and names the agent from its `clientInfo` (`matchAgent` maps names to known agents; OpenCode is recognised but not featured).
7. **Steady state.** A list of agents, one token each, with last request time and the client names seen; remove = revoke. Below, the shared permission grants. Turn MCP off keeps everything for later.

**Hermes and OpenClaw integration.** Both exist as App Store apps (`hermes-agent`, `openclaw`), and umbrelOS ships its own Hermes host app, **Murmur**, listed first. When the chosen agent is installed on the same box, the connect view swaps the endpoint for a fixed Docker-bridge gateway address that containers can reach (mDNS names do not resolve inside containers). Hermes is told to edit its `config.yaml` through the Files app; OpenClaw gets a CLI line to run in its app terminal; Murmur gets a one-tap link that hands the token to Murmur's settings page **in the URL fragment**, and a key made for Murmur is still shown as Murmur when its embedded Hermes says hello. A Tailscale tip covers agents off the LAN.

**Machine presence.** When an agent drives a VM, the console shows the agent's name and pointer and asks the person before letting them interfere; control returns after 60 s of agent silence. This is the most polished "agent is acting" UI in the product.

### 1.6 Strengths and weaknesses (as observed in source)

| Strengths to match | Weaknesses to beat |
|---|---|
| One-minute setup with per-client snippets and a live first-connection status | **No approval step**: install, uninstall, delete VM, OS update, restart run immediately |
| Tool list and instructions follow the grants; agents explain missing access | **One shared grant set** for all agents; no per-agent limits |
| Path containment after symlinks; hooks read-only; trash-only deletes; no overwrite | Agents always act as the **owner**; no household scoping |
| Re-auth after body read; same 401 for off and invalid | **Bearer token pasted into chat** and passed in a URL fragment |
| Restored backups cannot revive tokens | **Plain http** recommended on the LAN, so the token crosses the network in clear |
| Agent presence on the VM console | No expiry, no rate limits, **no persistent audit**; activity lost on restart |
| Background operations with recorded failures | Third-party text (app descriptions, logs) returned to the model unmarked |
| Logs for troubleshooting (app and system) | Tool hints are the only "danger" signal, and the server ignores them |

---

## 2. What OneMind has today

| Piece | Where | State |
|---|---|---|
| Rule "an agent requests, a person approves" | `sdk/contracts/poc-v0.md` §7, §11.2–§11.3 | On `main` |
| Principals with `kind: agent`; agents can never be owner | `core/onemind_core/auth.py` lines 30–50 (`is_owner`) | On `main` |
| Actions with create, approve, deny | `core/onemind_core/actions.py` (`create` 122, `deny` 127, `approve` 130) | On `main` |
| Hash-chained audit with requester and approver | `core/onemind_core/audit.py` | On `main`; no signed checkpoint (H-10) |
| Approvals page with an agent badge | `dashboard/src/pages/Approvals.tsx` (line 42) | On `main` |
| Phone approvals with "an AI agent asked" note | `mobile/src/screens/ApprovalsScreen.tsx` (line 48) | On `main` |
| Settings "Agents and tokens" mock | `ui/demo/src/screens/Settings.tsx` (line 41) | Demo only, fixtures |
| `POST /mcp` Streamable HTTP 2025-06-18, stateless, agents only, Origin check, 256 KiB cap; tools `list_nodes`, `list_apps`, `request_action`; no approve tool | gwmcp: `core/onemind_core/mcp.py`, `core/tests/test_mcp.py` (official Python SDK client) | Branch, no PR |
| App agent principals `agent:<app-id>`, token hashed, delivered as a Secret, revoked on remove | gwmcp: `actions.py`, `ledger.py`, `executors.py` | Branch |
| Full MCP plan: scopes and bundles, owner ∩ grant, kill switch, limits, untrusted marking, `plan_sha256`, stdio bridge, conformance, revisions | `docs/leap/dev/MCP.md` | Spec (proposed) |
| Threat model for `/mcp` and tokens | `docs/security/THREAT-MODEL.md` §4.2–§4.3; `HARDENING-BACKLOG.md` H-09, H-13, H-14, H-20, H-22 | On `main` |
| Passkey-signed approvals | `docs/leap/core/SECURITY.md` §3.2 | Spec |
| Per-box CA with name constraints; agent tokens never accepted on app hosts | net: `docs/architecture/NETWORKING.md` §9.3–§9.4 | Branch |
| Umbrel parity row for AI/MCP (PU-29 Agents page) | uileap: `docs/strategy/umbrel-parity.md` | Branch |

**Not present anywhere yet:** log tools, file tools, app lifecycle request types beyond install/remove, a connect wizard, pairing without pasting a secret, persistent client identity, agent activity view, household-scoped agents, a restore-time token wipe.

---

## 3. Where OneMind matches and where it beats

| Topic | umbrelOS 2.1 | OneMind target | Verdict |
|---|---|---|---|
| Setup time | Snippet or chat message, about a minute | Connect wizard with per-client setup and a pairing code; in-box Hermes is zero-touch (§11.2 Secret) | **Match**, then beat on safety |
| Secret handling during setup | Token in snippet, in chat, in URL fragment | Token never enters a chat or URL: pairing code exchanged by `onemind mcp pair` into the OS keychain; client config holds no secret (bridge); browser consent later (DEV-MCP-12) | **Beat** |
| Transport | Plain http advised on LAN | HTTPS with the pinned box CA through the bridge; http refused for `/mcp` outside loopback | **Beat** |
| Identity | One token per agent, shared grants | One principal per agent, own scopes, own limits, own expiry, owned by a person | **Beat** |
| Household | Agent = owner | Effective rights = owning person ∩ agent grant; adults can connect their own agents | **Beat** |
| Writes | Immediate | Request → owner approval with passkey over gateway-computed effects; low-risk types may use owner-defined standing approvals (CORE-AUTO-3) | **Beat** (the core rule) |
| Missing access | "Ask the owner to change Settings" | `request_access` tool returns a deep link that opens the exact grant change for the owner; nothing changes until the owner saves it with a passkey | **Beat** |
| Activity | Memory only, last seen | Persistent client identities, per-agent activity timeline from the hash chain, identity-change alert | **Beat** |
| Kill switch | Global off (keeps tokens), per-token revoke | Revoke, pause one, pause all, expiry; paused agents' pending requests stay visible | **Beat** |
| Restore safety | Tokens wiped on restore | Same: personal and static agent tokens wiped on restore, app principals re-minted on first reconcile | **Match** |
| Troubleshooting | App and system logs | `get_app_logs`, `get_node_logs` with secret redaction and `<untrusted>` marking | **Match**, beat on redaction |
| Files | Grants, path containment, trash-only, no overwrite, HTTP transfer | Read tools on granted folders; writes as one batched **file plan** request with snapshot-backed undo (needs the backups stream) | **Match** on reads, **beat** on writes |
| App lifecycle | start/stop/restart/update/settings/uninstall immediately | Same verbs as request types; uninstall keeps data by default, data delete is a separate destructive request | **Beat** |
| OS update, restart | Immediate | `os.update.apply`, `node.restart` as requests, owner + passkey | **Beat** |
| VMs and computer use | Create, drive with screen, keyboard and mouse | Not planned in this cycle (no VM layer in OneMind); record as a gap | **Gap** (accepted) |
| Prompt injection | None specific | `<untrusted>` marking, agent note box on cards, facts-only approvals (MCP.md §6) | **Beat** |
| Protocol coverage | SDK 2.0, stateless, 2026-07-28 identity in `_meta` | 2025-06-18 today; 2025-11-25 and 2026-07-28 planned (MCP.md §8); read `_meta` identity now | **Match** after U2-AGT-4 |
| Conformance | Unit and VM tests | Official SDK clients in Python, TS and Go plus the official conformance suite in CI (DEV-MCP-8) | **Beat** |
| Agent presence on screen | VM console overlay | "Agent at work" strip on Home and the app page, from live requests and reads | **Match** in our own form |

---

## 4. OneMind design for this area

Everything in MCP.md stands. This section adds the pieces the comparison shows we lack, in the same contract style (snake_case tools, `/v1` REST, the §3 error envelope, one service function behind REST, CLI and MCP).

### 4.1 Components and licences

| Component | Use | Version pinned | Licence (checked 2026-11-12) |
|---|---|---|---|
| OneMind gateway MCP package (our code) | `core/onemind_core/mcp/**` | — | Apache-2.0 (repo) |
| `mcp` (official Python SDK) | Test client only (dev group) | 1.30.0 (`core/uv.lock` on gwmcp) | MIT |
| `@modelcontextprotocol/sdk` (official TypeScript SDK) | Conformance client in `test/mcp-conformance/ts` | 1.32.2 | MIT |
| `github.com/modelcontextprotocol/go-sdk` | Conformance client in `test/mcp-conformance/go` only; the bridge stays standard library | v1.8.0 | MIT, with new contributions under Apache-2.0 (project relicensing notice in its `LICENSE`) |
| `github.com/zalando/go-keyring` | OS keychain for `onemind mcp pair` and `login` | v0.2.8 | MIT |
| FastAPI | Existing gateway framework | 0.162.5 (`core/uv.lock` on gwmcp) | MIT |

Pins go into `os/versions.lock.yaml` (add-only hotspot) when each epic lands. No umbrelOS package, asset or text is used. Agent logos are **not** shipped: the client list shows a name and a generic glyph from `ui/src/components/Icon.tsx`, so no third-party trademark art enters the repo.

### 4.2 Data model (ledger migrations, one per epic)

```
agents            id "agent:<slug>" PK · kind plugin|personal|static · owner_person_id
                  label · scopes[] · limits{reads_per_min, requests_per_hour, pending_max}
                  expires_at? · paused bool · created_via app_install|pairing|cli|static
                  created_at · revoked_at?
agent_tokens      agent_id FK · prefix "om_agt_<8>" · sha256 · created_at · last_used_at · revoked_at?
agent_clients     agent_id FK · client_name (≤ 80) · client_version (≤ 80) · first_seen · last_seen
                  (max 10 per agent, oldest dropped; written at most once a minute per row)
agent_pairings    id · device_code_sha256 · user_code (8 chars, no look-alikes) · requested_bundle
                  client_hint · state pending|approved|denied|expired|consumed · expires_at (10 min)
                  decided_by? · agent_id?
```

- `agent_clients` makes the "who is behind this key" fact persistent. If a key labelled for one client starts identifying as a different client, the gateway raises an `agent.identity_changed` alert (NOTIFICATIONS) but does not block: client names are self-declared and only a signal.
- No secret is ever stored in plain text; `device_code` and tokens are sha256 only (same rule as gwmcp `agent_tokens`).
- **Restore rule:** on the first start after a restore, `agents` of kind `personal` and `static` are revoked and their tokens deleted; `plugin` agents are re-minted by the executor when it reconciles the app. Audit records `agent.revoked_on_restore` per agent.

### 4.3 Pairing: "ask your agent to set it up" without a secret in the chat

Shape follows OAuth 2.0 Device Authorization Grant (RFC 8628), so DEV-MCP-12 can later serve the same flow from the OAuth façade.

```
Agent (has a shell)                 Gateway                                Owner's phone
 onemind mcp pair --hub https://onemind.local --client claude-code
   ─ POST /v1/agent-pairings {client_hint, requested_bundle: "reader"} ─►
   ◄─ {pairing_id, user_code "K7QM-2HXP", verification_uri, interval: 5, expires_in: 600}
   prints: "Approve code K7QM-2HXP in OneMind"        ─ push: "An agent wants to connect" (no code, no names) ─►
                                                                     card: client hint, source address,
                                                                     requested bundle in plain words;
                                                                     owner picks name, scopes (≤ owner's), expiry;
                                                                     passkey
   ─ POST /v1/agent-pairings/{id}/token {device_code} (polls) ─►
   ◄─ 428 authorization_pending … then {token} once
   stores token in OS keychain; writes the client's MCP config to run `onemind mcp` (no secret in it);
   prints only "Connected as agent:laptop-claude"
```

- The **agent** can start this itself: the setup message the wizard offers says "run `onemind mcp pair --client <name>`". It contains no secret. The token goes from the gateway into the keychain inside one process, never through the model's context.
- Pairing endpoints are unauthenticated by necessity: 5 open pairings per box, 20 attempts per minute per source address, codes expire in 10 minutes, a denied or expired code cannot be reused.
- The card shows the **gateway-observed** source address and the self-declared client hint marked as "said by the agent, not checked".
- **Agents without a shell** (chat-only clients) use the browser consent flow from DEV-MCP-12 when it lands. Until then the wizard shows a direct-HTTP config block for those clients and says plainly that the key will be stored in that client's config file. It never offers a "paste this into the chat" message with a key.
- **Hermes installed as a OneMind app** needs no pairing: §11.2 already mints `agent:hermes-agent` and writes the Secret; the app's default config points at `/mcp`. The wizard shows it as "Connected automatically" with its grant.

### 4.4 API, CLI and MCP surface

REST (gateway core owns routes; contract amendment first):

| Route | Who | Purpose |
|---|---|---|
| `POST /v1/agent-pairings` | anyone (rate-limited) | Start pairing; returns codes |
| `POST /v1/agent-pairings/{id}/token` | holder of `device_code` | Poll; 428 `authorization_pending`, 410 `expired`, 403 `denied`, 200 once |
| `POST /v1/agent-pairings/{id}/approve` · `/deny` | owner or adult, passkey | Decide; body sets `name`, `scopes`, `expires_at` |
| `GET /v1/agents` · `GET /v1/agents/{id}` | owner; adults see their own | List with scopes, limits, clients, last used, paused |
| `PATCH /v1/agents/{id}` | owner or owning adult | Narrow scopes (no passkey) or widen (passkey) |
| `POST /v1/agents/{id}/pause` · `/resume`, `POST /v1/agents/pause-all` | owner | Kill switches (MCP.md §5.3) |
| `DELETE /v1/agents/{id}` | owner or owning adult | Revoke |
| `GET /v1/agents/{id}/activity` | owner or owning adult | Page of audit entries for this principal |

CLI (MCP.md §7 commands plus):

```console
$ onemind mcp pair --hub https://onemind.local --client claude-code   # agent side, see §4.3
$ onemind mcp setup claude-code|claude-desktop|codex|cursor|hermes    # write that client's config to run the bridge
$ onemind agents list | show <id> | pause <id> | pause --all | resume <id> | revoke <id>
$ onemind agents grant <id> --add logs:read:app:ntfy                  # widening asks for the owner passkey
$ onemind agents activity <id> --since 24h
```

`onemind mcp setup` writes only the stdio bridge command into the client's own config file (with a backup of the old file) and never a token. The client config formats are each client's public documented format; we write them from our own templates.

MCP tools added by this study (scopes and naming as in MCP.md §4.1):

| Tool | Input | Output | Scope | Kind |
|---|---|---|---|---|
| `get_app_status` | `{app_id}` | state, health, last operation and its failure | `apps:read` | read |
| `get_app_logs` | `{app_id, lines ≤ 500, since?}` | `{lines[], truncated, dropped}`; secrets redacted; lines wrapped as `<untrusted source="app:<id>:logs">` | `logs:read:app:<id>` or `logs:read:apps` | read |
| `get_node_logs` | `{node_id, unit: gateway|onemindd|k3s|nats, lines ≤ 500}` | same | `logs:read:nodes` | read |
| `get_system_health` | – | per node: disk, memory, temperature, update and backup badges | `nodes:read` | read |
| `list_folder` | `{path, cursor?}` | entries with size, type, mtime | `files:read:<folder>` | read |
| `search_files` | `{query, under?}` | names only, capped | `files:read:<folder>` | read |
| `preview_file_plan` | `{ops: [{op: move|rename|mkdir|trash, from, to?}] ≤ 500}` | `{effects, plan_sha256, conflicts[]}`; files nothing | `files:plan:<folder>` | read |
| `request_action` (new types) | `app.start`, `app.stop`, `app.restart`, `app.update`, `app.settings`, `files.apply_plan`, `node.restart`, `os.update.apply` | as MCP.md §4.3 | `actions:request:<type>` | request |
| `request_access` | `{scopes[], reason?}` | `{link, expires_at}`: a dashboard deep link that opens this agent's grant page with the scopes pre-selected; **nothing is filed or changed** | always | link only |

Rules for the new pieces:
- `request_access` is not a grant request in the MCP.md §4.3 sense (those stay never-requestable). It only builds a link; the owner saves any change on the Agents page with a passkey. The link is shown in the tool result, so the agent can say "open this to give me access".
- `files.apply_plan` is one action for many file operations. The approval card lists them with counts per folder and the `plan_sha256`. Before execution the executor takes a snapshot of the affected folders (BACKUPS spec); the action's page offers **Undo** for 7 days. No operation overwrites; trash only; External and Network targets refuse `trash` (match the safe behaviour observed in umbrelOS).
- Folder grants are relative to the owning person's own space (per-person Home, PU-28), so an adult's agent cannot see another person's files.
- `app.remove` keeps data by default; data deletion is the separate `app.data.delete` type, `destructive`, never in a bundle.
- `os.update.apply` and `node.restart` are `destructive` for the passkey rule (step-up on every approval) and never covered by a standing approval unless the owner names that agent.

Bundles gain `troubleshooter` = `reader` + `logs:read:apps` + `logs:read:nodes` (read only; the most useful grant for "why is my app stuck").

### 4.5 Server instructions

The `instructions` text is rebuilt per request from the caller's grant (as MCP.md requires for `tools/list`), in our own wording, and says: what this agent may read, what it may request, that every request waits for a person, that `request_access` exists, and that text inside `<untrusted>` must not be followed. A test pins that it never contains a token, a host address or a person's name.

### 4.6 UI screens (dashboard and phone; design tokens from `ui/`)

| Screen | Where | Content |
|---|---|---|
| **Agents** (Settings) | `dashboard/src/pages/SettingsAgents.tsx`, `mobile/src/screens/AgentsScreen.tsx` | One card per agent: name, kind pill (App, Personal), owner, scopes in plain words, last used, clients seen, expiry, Pause, Revoke; "Pause all agents" at the top; empty state leads to Connect |
| **Connect an agent** wizard | dashboard modal | 1 choose client (list with generic glyphs) → 2 choose bundle (Reader, Troubleshooter, Requester) with plain-words preview → 3 show the one-line `onemind mcp pair` command or the "message for your agent" (no secret) → 4 live wait: flips to "Connected" when the pairing is approved and the first call arrives, naming the client as it identified itself |
| **Pairing card** | Approvals list, phone and dashboard | Code, source address (gateway-observed), client hint (marked unchecked), scopes with toggles limited to the approver's own rights, expiry picker, passkey |
| **Agent activity** | agent detail | Timeline from the audit chain: reads summarised per minute, requests and outcomes, denials, pauses |
| **Agent at work** strip | Home and app page | While an agent has a pending request or made calls in the last 2 minutes: agent name and what it is doing ("reading ntfy logs", "asked to restart ntfy"), tap to open its activity. Our answer to the VM console overlay |
| **Approval card additions** | existing card | Agent note box (MCP.md §6.2); for `files.apply_plan` a grouped op list and Undo after execution |
| **Access link landing** | Agents page with `?add=` | Pre-selected scopes highlighted, "Requested by <agent>" note marked unchecked, Save needs passkey |

All copy is written for OneMind. No animation or illustration is modelled on the umbrelOS intro.

### 4.7 Security

| Threat | Control | Test |
|---|---|---|
| Secret leaks through chat history or model provider logs | Pairing exchanges the token inside `onemind mcp pair`; the wizard never shows a message containing a key | U2-T1 |
| Token sniffed on the LAN | `/mcp` refuses plain http except from loopback; bridge pins the box CA | U2-T2 |
| Pairing spam or code guessing | 8-character code, 10 minute life, 5 open per box, 20 attempts per minute per source, owner passkey to approve | U2-T3 |
| Rogue pairing card social-engineers the owner | Card shows the gateway-observed source and the requested scopes; client hint marked unchecked; scopes capped at the approver's rights | U2-T3 |
| Agent self-escalates | No grant-change tool; `request_access` only returns a link; widening needs a passkey | U2-T4 |
| Restored backup revives keys on new hardware | Restore wipe (§4.2) | U2-T5 |
| Mass file damage by a confused agent | One plan, owner-approved, snapshot first, Undo for 7 days, no overwrite | U2-T7 |
| Secrets in logs reach the model | Log redaction (token prefixes, `KEY=` style pairs, PEM blocks, URLs with credentials) before return; MCP-T9 scan over fixtures | U2-T6 |
| Key reused by a different client | `agent.identity_changed` alert | U2-T8 |
| A household member's agent sees another person's data | Owner ∩ grant (MCP.md §5.1) applied to folders and logs | U2-T9 |

---

## 5. Epics

IDs are new and do not reuse DEV-MCP numbers; each names the DEV-MCP epic it extends. Owner paths follow [WORKSTREAMS.md](../leap/WORKSTREAMS.md): the MCP stream owns `core/onemind_core/mcp/**`, `grants.py`, `ratelimit.py`, `internal/mcpbridge/**`, `cmd/onemind/cli/mcp.go`, `test/mcp-conformance/**`; security owns `tokens.py` and `agents.py`; hotspots (`sdk/contracts/poc-v0.md`, `ledger.py` migrations, `routes.py`, `cli/root.go`, `os/versions.lock.yaml`, `App.tsx`) change in their own small serialized PRs.

| Epic | Title | Size | Owner paths | Acceptance | Depends on |
|---|---|---|---|---|---|
| U2-AGT-1 | Contract amendment for agents, pairings, new request types, `request_access`, `troubleshooter` bundle, `rate_limited` and `authorization_pending` errors | S | `sdk/contracts/poc-v0.md`, `sdk/schema/onemind.app.schema.json` (contract owner, `contract/12-*`) | Amendment merged; schema validates `spec.agent.scopes` with the new bundle; no feature code in the PR | DEV-MCP-2 design agreed |
| U2-AGT-2 | Agents registry and token lifecycle: `agents`, `agent_tokens`, `agent_clients` tables; `/v1/agents*` routes; pause, pause-all, revoke, expiry; owner ∩ grant | M | `core/onemind_core/{agents,tokens}.py`, one `ledger.py` migration (security stream, `feat/tokens`) | Revoke → next `/mcp` call 401; pause-all → 403 and pending requests unchanged; adult sees only own agents; tokens stored as sha256 only (fixture scan) | U2-AGT-1, H-09 |
| U2-AGT-3 | Pairing (RFC 8628 shape): `/v1/agent-pairings*`, limits, passkey approval, audit | M | `core/onemind_core/agents.py` (security), approve hook via gateway-core owner | U2-T1: full pair run leaves no token in stdout, stderr, chat fixture or client config; U2-T3: 21st attempt per minute → 429, expired code → 410, denied code cannot be reused, approver cannot grant above own rights | U2-AGT-2, CORE-SEC-2 passkeys |
| U2-AGT-4 | Persistent client identity: read `clientInfo` and 2026-07-28 `_meta` identity, `agent_clients` writes capped, `agent.identity_changed` alert | S | `core/onemind_core/mcp/transport.py` (MCP stream) | U2-T8: a key used by client A then client B raises one alert; 11th distinct name drops the oldest; restart keeps the list | U2-AGT-2, DEV-MCP-1 |
| U2-AGT-5 | `onemind mcp pair` and `onemind mcp setup <client>`; keychain storage; config writer with backup | M | `internal/mcpbridge/**`, `cmd/onemind/cli/mcp.go` (`feat/cli-mcp`); `root.go` one line, serialized | U2-T1 and U2-T2: setup writes a config with no secret for each listed client; bridge refuses a hub whose cert does not chain to the pinned CA; MCP-T15 still passes | U2-AGT-3, DEV-MCP-7, net box CA |
| U2-AGT-6 | Troubleshooting tools: `get_app_status`, `get_app_logs`, `get_node_logs`, `get_system_health`; redaction; `troubleshooter` bundle | M | `core/onemind_core/mcp/catalog.py`, `core/onemind_core/mcp/untrusted.py`; log source functions in gateway core via one PR | U2-T6: planted secrets in fixture logs never appear in output; lines wrapped in `<untrusted>`; 600 requested lines → 500 with `truncated`; MCP-T1 parity with the matching REST routes | DEV-MCP-1, DEV-MCP-5 |
| U2-AGT-7 | App lifecycle request types `app.start/stop/restart/update/settings`, `app.data.delete`; remove keeps data | M | `core/onemind_core/action_types.py` (gateway core), executor hook through the sandbox owner | Each type files `awaiting_approval` from MCP and executes only after approval; `app.remove` leaves the PVC; `app.data.delete` requires passkey step-up; agents cannot approve (MCP-T2) | U2-AGT-1, CORE-SANDBOX-2, APP-P1 |
| U2-AGT-8 | Files read tools and `files.apply_plan` with snapshot and Undo | L | `core/onemind_core/mcp/catalog.py` (MCP), `core/onemind_core/files.py` (new, files owner), snapshot via `internal/backup/**` (backups stream) | U2-T7: a 200-op plan is one card; approval with a stale `plan_sha256` → 409; after execution Undo restores every path byte-for-byte; no op overwrites; trash on External refused; path escape via symlink refused | U2-AGT-1, CORE-BACKUP snapshots, PU-28 per-person Home |
| U2-AGT-9 | `request_access` deep links and the access landing on the Agents page | S | `core/onemind_core/mcp/catalog.py`; `dashboard/src/pages/SettingsAgents.tsx` (dashboard) | U2-T4: calling it changes no grant and files no action; link expires in 24 h; saving a widening without passkey → 403 | U2-AGT-2, U2-AGT-10 |
| U2-AGT-10 | UI: Agents page, Connect wizard, pairing card, agent activity, "Agent at work" strip (dashboard and phone) | L | `dashboard/src/pages/SettingsAgents.tsx`, `dashboard/src/components/{PairingCard,AgentStrip}.tsx`, `mobile/src/screens/AgentsScreen.tsx`; route lines in `App.tsx` (hotspot) | Playwright and Jest: wizard reaches "Connected" against a fake gateway with no secret rendered anywhere in the DOM; pairing card caps scopes; strip appears within 5 s of a request; axe clean; light and dark | U2-AGT-2, U2-AGT-3, PA-UI tokens |
| U2-AGT-11 | Restore wipe and conformance additions | S | restore path in `internal/backup/**` (backups), `test/mcp-conformance/**` (MCP) | U2-T5: after a restore drill, every personal and static token → 401 and the app principal works with a new token; conformance job runs the pairing and new tools through Python 1.30.0, TS 1.32.2 and Go v1.8.0 clients | U2-AGT-2, CORE-BACKUP restore, DEV-MCP-8 |

**Order:** U2-AGT-1 → 2 → (3, 4, 6 in parallel) → 5 and 7 → 10 → 9 → 8 (waits for snapshots) → 11. U2-AGT-2, -3, -5 and -10 belong with the Governed Agents demo (plan E2/E3) because they are the visible lead over umbrelOS; -8 is the largest and waits for the backups stream.

**Accepted gap:** VM creation and screen, keyboard and mouse control. OneMind has no VM layer this cycle; revisit only if the founder asks for desktop VMs.

---

## 6. Open questions for the founder

| # | Question | Proposed default |
|---|---|---|
| 1 | May adults (not only the owner) pair their own agents? | Yes, capped at their own rights; owner sees all agents |
| 2 | Should `troubleshooter` be the default bundle in the Connect wizard instead of `reader`? | Yes: logs are the most common first use, and it stays read-only |
| 3 | Undo window for `files.apply_plan` | 7 days, limited by snapshot space; the card says when Undo will expire |
| 4 | Should the wizard offer direct-HTTP setup (key in the client's config file) for chat-only clients before DEV-MCP-12? | Yes, with a visible warning and expiry forced to 30 days |
