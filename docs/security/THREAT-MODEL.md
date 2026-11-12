<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind OS core: threat model (edition 2)

**Status:** edition 2, 2026-11-12. Written from the code on `main` at `ad557c6` (merge of PR #63), not from the plans. Edition 1 (PR #18, written when the code was still on wave-2 branches) is in git history; this edition replaces it.
**Serves:** brief 30 B6 (D-B6.1, D-B6.2, D-B6.5), B4.5 (SB-1…SB-10), B9 (gateway), SEC-01…SEC-12 in [`research-output/07-security-compliance.md`](../../research-output/07-security-compliance.md) §10, Wave G item 3 of [`docs/leap/NEXT-WAVE.md`](../leap/NEXT-WAVE.md), and the founder focus of 2026-11-12: replace the founder's own Kubernetes cluster with OneMind OS and use it every day.
**Companion:** [`HARDENING-BACKLOG.md`](HARDENING-BACKLOG.md) holds the ranked fixes (`H-xx`) this document refers to.

Line references such as `core/onemind_core/actions.py:238` point at `main` plus this PR. Re-check a cited line before you act on it.

> **Explain it like I am the founder**
> A threat model is a list of ways the box can be attacked, what stops each one today, and what is still missing.
> Since edition 1 most of the big holes were closed: apps can no longer run privileged pods, the gateway no longer has cluster-admin, sign-in is passkeys with real sessions, and notifications cannot be aimed at your LAN by a guest.
> This edition re-reads everything that arrived since, checks the six promises you care about one by one (agents never approve; an approval is bound to what runs; every route checks who you are; no server-side request tricks; secrets are protected on disk; nothing deletes your data by surprise), and finds **one real hole in the "agents never approve" promise** (fixed in this PR) plus a short list of work still open. Two things are still wide open: the box talks plain HTTP on your LAN and its message bus (NATS) has no passwords.

---

## 1. How to read this

**STRIDE** is the checklist used for each component. Each letter is one kind of attack:

| Letter | Attack | Plain words | The property it breaks |
|---|---|---|---|
| **S** | Spoofing | pretending to be someone or something else | authentication |
| **T** | Tampering | changing data or code you should not change | integrity |
| **R** | Repudiation | doing something and being able to deny it | audit |
| **I** | Information disclosure | reading what you should not read | confidentiality |
| **D** | Denial of service | stopping the system from working | availability |
| **E** | Elevation of privilege | getting more power than you were given | authorization |

**Severity:** **Critical** = one step from full control of the box or the cluster; **High** = a realistic attacker on the home network, or a malicious app, gets owner-level power or a secret; **Medium** = needs a second weakness, or leaks something useful; **Low** = hygiene.
**Backlog tier:** **P0** = before the box holds anything the founder cares about; **P1** = before daily use with real secrets and more than one node; **P2** = before anyone else runs it.

**How this edition was produced.** Every claim below was read in the code on `main`. Where a claim is also pinned by a test, the test is named. Three things were run, not just read: (1) a **scripted route inventory** (`core/tests/test_route_authz.py`, §5.3) that walks every route the app registers; (2) a role matrix that called every route as agent, guest and adult; (3) a new regression test for the one hole found (§5.1). Components that are built but **not yet wired into the running gateway** (reverse proxy, mesh, CA) were read but could not be attacked; §4.7 says so per item.

---

## 2. The system and its trust boundaries

A **trust boundary** is a line where data passes from something we trust less to something we trust more. Every boundary is a place to check identity and input.

```
 Home LAN / tailnet (untrusted: phones, laptops, IoT, guests)
 ─────────────────────────────────────────────────────────────── B1
   browser / phone / desktop ─HTTP :8080─► gateway (FastAPI, core/)  ──kubectl──► k3s API :6443
        sign-in: passkey / password+TOTP         │ sessions, tokens, ledger, audit      │
   AI agent        ──HTTP /mcp ──►               │ notifications ──HTTPS──► ntfy / webhook / SMTP / push (B5)
   other nodes     ──NATS :4222──► NATS (hub, no users) ◄──heartbeats── onemindd      ▼
                                                                      app pods in app-<id>
 ─────────────────────────────────────────────────────────────── B2 (pod ↔ host)
   app pods (untrusted code from the Market): restricted PSA, default-deny NetworkPolicy
 ─────────────────────────────────────────────────────────────── B3 (supply chain)
   GitHub repo, CI secrets, app images, TUF/RAUC keys ──► what every box installs
 ─────────────────────────────────────────────────────────────── B4 (physical)
   console, USB, disk removal
 ─────────────────────────────────────────────────────────────── B5 (outbound)
   anything the box fetches or sends on someone's behalf (notification channels, push)
```

Built but **not on the wire yet**: the app reverse proxy (`core/onemind_core/proxy.py`), the per-box CA (`ca.py`), the mesh/Headscale client (`mesh.py`). None of them is imported by `app.py` (`grep` of `core/onemind_core` finds no import). Their findings are "before wiring" items.

### 2.1 Assets (what we protect)

| Asset | Where it lives | Why it matters |
|---|---|---|
| Static owner token | sha256 only in `tokens.yaml` (`core/onemind_core/auth.py:88-96`), 0640 root:onemind (`deploy/install.sh:491-500`); plain text shown once on the terminal (`install.sh:570`) | Break-glass owner. Approves every action while no passkey exists. |
| Household accounts, sessions, API tokens | SQLite `onemind.db` in `/var/lib/onemind` (0750, `install.sh:407`): scrypt password hashes, sha256 of session and token secrets, **TOTP seeds in clear** (`identity/models.py:44-45`) | Who may approve, and what each credential may do. |
| Owner passkeys | public keys in the same database | Approval step-up (§5.1). |
| Notification secrets and push endpoints | AES-256-GCM sealed with `secret.key` (0600, `notify/crypto.py:38-45, 49-70`) | Webhook secrets, SMTP passwords, ntfy tokens, device endpoints. |
| Box CA key (built, not wired) | `ca.key` 0600 in a 0700 folder (`ca.py:95-137`) | Would let its holder impersonate the box. |
| Gateway's Kubernetes identity | ServiceAccount `onemind-system/onemind-gateway`: create namespaces, per-app RoleBinding to `onemind-app-deployer` only (`deploy/k8s/gateway-rbac.yaml`, SECURITY.md §7a H-03) | Was cluster `admin` in edition 1; no longer. |
| k3s server state | `/data/k3s`; developer install encrypts Secrets (`install.sh:247-251`); **the OS image does not yet** (`os/rootfs/layers/base/usr/lib/systemd/system/k3s.service:17`) | Cluster CA keys, join tokens, every Secret. |
| Audit chain | `data/audit.jsonl`, hash-chained (`audit.py`) | The record that an agent asked and a human approved. |
| App agent tokens | hashed in the ledger; plain in Secret `<name>` in `app-<id>` (`executors.py:73-100`) | Let an app's AI request actions. |
| Backup repositories and keys | restic repo, `DeviceKeyFile` (`internal/backup/restic.go:135-193`) | All user data, copied off the box. |
| Signing keys (RAUC, TUF online keys) | GitHub repository secrets, **no protected environment** (`.github/workflows/security-nightly.yml:151, 217-219, 293-295, 392-394`) | Whoever reads them can push an OS image to every box (H-07). |
| User data (`/data`) | ext4, not encrypted (`os/boards/x86_64-efi/layout.yaml:13`, "LUKS2 planned") | Photos, home data, app volumes. |

### 2.2 Attackers we design for

| ID | Attacker | Example |
|---|---|---|
| A1 | **A device on the home network** | a compromised smart TV or IoT bulb, a guest laptop, malware on a family PC |
| A2 | **A malicious or compromised app** | a Market app whose image or manifests were swapped upstream, or an app with an exploitable bug |
| A3 | **A tricked AI agent** | Hermes reads a web page or email that tells it to install or remove something (prompt injection) |
| A4 | **A thief of a token or device** | a lost phone, a token pasted into a chat, a stolen browser session |
| A5 | **The supply chain** | a compromised GitHub account, a CI secret leak, a poisoned npm or PyPI package, a swapped upstream image |
| A6 | **A rogue node** | a machine that joins with a leaked join token |
| A7 | **Physical access** | someone with the box, a keyboard and a USB stick |
| A8 | **A household member with less power** | a guest or child account, or an adult, trying to do owner things (new in edition 2: accounts now exist) |

Not modelled now (founder focus): robots, drones, physical actuation, TAK. Their rules (SEC-12 items 4-6, D-B6.4) stay in `research-output/07-security-compliance.md` §7.

---

## 3. Where we stand: findings of edition 1

Edition 1 ranked ten findings. Status on `main` today (evidence is in the backlog, [`HARDENING-BACKLOG.md`](HARDENING-BACKLOG.md) "Status of edition 1"):

| # | Edition 1 finding | Now | Backlog |
|---|---|---|---|
| 1 | Executor applied any manifest (privileged pods, `hostPath`, cluster kinds) | **Closed** in the gateway and developer install: the box renders, checks every object against `sdk/policy/app-objects.yaml` and applies the checked bytes (`executors.py:296-330`, `policy.py:145-470`). **Open in the OS image** (no PSA, no secrets encryption in `k3s.service:17`). | H-01 partial, H-02 done |
| 2 | Gateway was cluster `admin` | **Closed**: namespaces + per-app RoleBinding + admission policy (`gateway-rbac.yaml`). | H-03 done |
| 3 | Owner token in clear text on the LAN | **Open**: still `ONEMIND_HOST=0.0.0.0`, plain HTTP (`deploy/install.sh:29, 524`). Cookies are `Secure`/`__Host-` so the dashboard session only works on `localhost` or behind TLS. The CA exists (`ca.py`) but is not wired. | H-05 open (P0) |
| 4 | NATS has no authentication | **Open**: `deploy/install.sh:314-320` ("no auth/TLS"), `bus.py:50-58`. | H-06 open (P0) |
| 5 | Signing keys are plain repo secrets | **Open**: no `environment:` in any workflow. | H-07 open (P0) |
| 6 | Scan record not bound to what is installed | **Partly closed**: the box now renders and checks the bytes it applies and records `rendered_sha256` (`executors.py:316`), but `scan.json` still holds only date and `pass` (`scan.py:35-51`). | H-08 partial |
| 7 | Audit chain proves order, not authorship | **Open**: no signed checkpoints (`audit.py`). | H-10 open |
| 8 | Secrets at rest not encrypted | **Partly closed**: k3s Secrets encrypted on the developer install; notification secrets sealed; TOTP seeds and `/data` are not. | H-11, H-12 partial |
| 9 | Tokens never expire | **Closed** for household tokens (`identity/service.py:766-830`: expiry, rotate, revoke, prefix, last-used). Static file tokens still never expire. | H-09 done (static: P1) |
| 10 | On-box builds run third-party code as root | **Open**. | H-15 open |

---

## 4. STRIDE for what is new since PR #18

Format as in edition 1: threat, control today (with evidence), gap, backlog id. "None" means nothing in the code stops it. Components whose edition-1 table still stands (executor, tokens file, audit chain, `onemindd`, OS image, install script, dashboard) are not repeated; see the status table above.

### 4.1 Household identity (`core/onemind_core/identity/`, `routers/identity.py`)

What it is: owner, adult, guest and child accounts; password + TOTP or passkey sign-in; cookie sessions with CSRF; bearer sessions with refresh tokens for apps; API tokens; per-app sharing; passkey step-up for approvals and administration.

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| S | Guessing a password, TOTP or refresh token | Per-source limiter, 10 failures a minute then 15-minute lockout (`service.py:95-124`); scrypt; TOTP replay blocked by `last_step`; unknown user costs one hash (`crypto.py:44-52`) | Limiter key is `request.client.host`: behind the future proxy every user shares one source | H-33 |
| S | Stolen session cookie used cross-site | `__Host-` cookie, `Secure`, CSRF header compared by hash for every unsafe method (`service.py:215-238`) | none | — |
| S | Forged passkey assertion or replay of an approval | Real WebAuthn verification with user verification required (`passkeys.py:60-103`); challenge single-use, 120 s, bound to the action (`service.py:420-440, 944-1000`); tested in `test_identity.py` (`test_owner_approval_needs_passkey_once_registered`) | none | — |
| S | Anonymous setup of a second owner | Setup needs an owner token or the first-boot token and refuses once any account exists (`service.py:471-503`) | The "no accounts yet" check and the insert are not atomic: two simultaneous setups with the token could both succeed (needs the install token) | H-37 (P2) |
| T | Account takeover by changing credentials with a stolen API token | Password, TOTP and passkey changes need a **session**, never a token (`_account`, `service.py:547-553`) | none | — |
| T | A stolen session mints a long-lived API token (persistence) | Minted token is capped by the minter's scopes and never outlives a minting token (`service.py:790-805`) | `create_token` needs **no passkey step-up**: a stolen owner cookie can mint a 365-day token with all scopes (`service.py:766`; compare `create_user` at `:681`, which does step up). That token cannot approve once passkeys are on (§5.1) but can read everything and file requests | H-35 (P1) |
| R | Who did what | `auth.*`, `authz.denied`, `user.*`, `app.access.*` events in the audit | `login.failed` writes the typed username (64 chars, `service.py:384`): people paste passwords into that box | H-38 (P2) |
| I | Sessions listed across users | Non-owners see only their own (`service.py:330-338`) | none | — |
| I | Enrolment link leaks | 192-bit one-time code, 24 h, stored hashed (`service.py:687-701`) | The link is built from the request's Host header when `public_url` is unset (`service.py:700`); the requester is the owner, so impact is a wrong-looking link | — |
| D | Anonymous flood of sign-in challenges | At most 1000 open login challenges, then 429 (`service.py:424-431`) | Fills the table for 2 minutes, locking out real sign-ins | H-33 |
| E | A narrowed token acts beyond its scope | Scope table enforced per route for every household credential; unknown routes need `*` (`scopes.py:127-164`); person-only scopes never go to agents (`scopes.py:44, 99-108`) | **Two handlers accepted more than their route scope** (alert `fix` with `approve`): fixed (§5.1). All other owner-only handlers re-check `is_owner` themselves | fixed |
| E | Static-file tokens are unscoped | By design v0: a static `guest` token reads what `guest` may, and the owner token is `*` | These tokens never expire, are not listed per use, and bypass step-up for everything except approvals | H-36 (P1) |

### 4.2 Action ledger and approval (`actions.py`, `routers/actions.py`)

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| S | An agent approves | `_approve` and `_cancel` raise 403 unless `is_owner` = person with role owner (`actions.py:223, 238`; `auth.py:45`); no approve route or MCP tool exists (§5.1) | none | — |
| T | Approve something other than what was requested | Params are only `{app_id}`, validated; challenge is bound to `sha256(id, type, params, requested_by, expires_at)` (`service.py:937-942`) | **No plan is stored or bound**: `plan_sha256` is read everywhere but nothing ever sets it, so it is always `null` (grep: only `identity/service.py:951-992`). What runs is whatever the catalog renders at dispatch time (`executors.py:296-330`) | H-13 (P1) |
| T | Approval while the world changed | Preconditions re-checked and the app claimed atomically at approval (`actions.py:237-280`); scan freshness re-checked (`:254`) | none | — |
| R | Denying a request | `action.requested/approved/dispatched/*` with requester and approver ids | The ledger result keeps kubectl tails; fine | — |
| I | Any signed-in principal lists every action and its kubectl output | `GET /v1/actions` is open to guest and agent (role matrix, §5.3) | `result.steps` show argv and stdout tails | H-21 (P2) |
| D | Approval fatigue | Pending cap 10 per non-owner requester (`actions.py:197-212`), MCP cap 10 and 10 requests an hour (`mcp/limits.py:24-27`) | none | — |
| E | Replaying an idempotency key to read someone else's action | Replay only if type, params, requester and expiry match (`actions.py:211-226`) | none | — |

### 4.3 MCP endpoint (`core/onemind_core/mcp/`, `routers/mcp.py`)

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| S | A person's token used on `/mcp` | Agents only, else 403 + `authz.denied` (`mcp/server.py:64`) | none | — |
| S | DNS rebinding | `Origin` must equal `Host` when present (`server.py:65-68`) | none | — |
| T | Prompt injection through app text, node names, audit text | Fields from third parties are wrapped as untrusted and the agent is told never to follow them (`mcp/untrusted.py`, `tools.py:180-190`, `server.py:42-47`); the agent's own `reason` is cleaned (`tools.py:380-386`) | The owner's card shows the reason; a persuasive reason still reaches a human | H-13 label, H-14 done |
| T | Duplicate or flooding requests | Same pending request returns the existing card; caps (`tools.py:368-378`) | none | — |
| I | Agent reads other agents' requests or audit | `get_action` and `list_actions` filter to the requester; audit view is own records plus own actions (`tools.py:326-340`, `auditread.py:97-111`) | none | — |
| E | Agent self-approves | No approve/deny/grant/token tool in the catalogue (`tools.py`, `mcp/__init__.py`); `Services` has no such function | none | — |
| E | Scoped agent gets `/mcp` without `actions:request` | Route needs `actions:request`; reader-grant agents are refused (`scopes.py:150-152`) | MCP tools are not scope-aware per tool (DEV-MCP-2) | H-22 (P2) |

### 4.4 Notifications and push (`notify/`, `routers/notifications.py`)

This is the first outbound path from the box (boundary B5), so it gets the SSRF review (§5.4).

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| S | An app agent sends fake alerts | Agents may send only under their own topic `plugin.<id>` (`notify/service.py:544-545`), rate limited | The text is attacker-controlled and shows in the owner's inbox | H-39 (P2) |
| T | Alert `fix` used to approve | Fixed in this PR (§5.1) | — | fixed |
| I | Another person's channel destination (an ntfy topic is a capability) | Non-owners see only their own; owners see others' channels without `config` (`routers/notifications.py:253-262`) | none | — |
| I | Secrets in logs or the database | Sealed per row with the row id as AAD (`notify/crypto.py:49-70`); never returned; control characters refused (`:97-103`) | none | — |
| D | Test button as an outbound request cannon | 5 tests a minute per person (`routers/notifications.py:345-356`) | An adult can still aim up to that rate at any public host | H-40 (P2) |
| E | A guest aims the box at the LAN or the cloud-metadata address | Non-owners: https only, public addresses only, checked at save and again on the connected peer (`channels.py:86-136`); link-local, multicast, reserved refused for everyone; IPv4-mapped IPv6 unwrapped; no redirects; no proxies | A channel keeps `lan: true` forever if its owner is later demoted (`routers/notifications.py:292, 317`) | H-40 (P2) |

### 4.5 Monitoring, logs, events, audit read (`monitoring/`, `routers/monitoring.py`, `eventstream.py`, `routers/audit.py`)

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| I | App logs leak secrets to anyone | Only owner and adult people read logs; apps hidden by sharing are 404; every line passes `Redactor` (tokens, JWTs, PEM blocks, URL credentials, key=value secrets, emails, IPs) (`routers/monitoring.py:106-160`, `redact.py`) | A safety net: a secret logged under an innocent name is not caught | — |
| I | Audit and event streams show more than they should | Full audit for owner and adult only; agents see own records; guests 403 (`auditread.py:97-111`, `routers/audit.py:56-96`); event filters per role (`eventstream.py:112-140`) | none | — |
| D | Many open log or event streams | 5 per principal, 429 above (`routers/events.py`, `monitoring.py`) | none | — |
| E | Reading logs of an app you cannot open | `app_entry` runs every registered app filter (`monitoring.py:78-87`) | none | — |

### 4.6 Go components on the box (`internal/backup`, `internal/storage`, `internal/mesh`, `internal/update`, `internal/mcpbridge`, `cmd/onemind*`)

These are local tools the owner runs; none of them listens on the network except `onemindd` (loopback by default since H-24, `internal/agent/agent.go:31`).

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| T | A backup restore overwrites live data | Restores go to a temp name, then rename; an existing directory is moved aside first, symlinks in the parent refused (`internal/backup/rewind.go:248-330`) | The moved-aside copy is deleted right after (`rewind.go:312`), relying on the pre-restore snapshot | — |
| T | `forget` deletes snapshots of other units | `forget` without a tag filter is refused; prune runs only in the weekly verify (`restic.go:331-343`) | none | — |
| I | Restic password handling | Password files, never argv (`restic.go:164-193`) | The device key file protects every backup; losing it is losing the backups (documented, BACKUPS.md) | — |
| D/E | Storage plan wipes the wrong disk | The planner is plan-only; a disk to be wiped must be unused, writable, not the system disk and not critical SMART (`internal/storage/plan.go:105-125`) | Execution is a later slice; re-review when it lands | — |
| S/T | Update tampering | TUF-verified index, RAUC bundle signed (`internal/update/tuf.go`, `download.go`) | Signing-key custody is H-07 | H-07 |
| I | MCP bridge forwards an agent token to a hub | Bridge speaks to the configured hub only (`internal/mcpbridge/bridge.go:194`) | Plain HTTP to a hub on the LAN (same as H-05) | H-05 |

### 4.7 Built but not wired: reverse proxy, CA, mesh (`proxy.py`, `ca.py`, `mesh.py`)

Findings here are conditions to meet **before** these modules are imported by `app.py`.

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| S | App session cookie handling | The proxy strips the gateway cookie named `onemind_session` and refuses to let an app set it (`proxy.py:61, 298`) | Identity names its cookies `__Host-onemind_session` and `onemind_csrf` (`identity/service.py:133-135`), so **the proxy would pass them to the app**. The default sign-in resolver also knows only static tokens (`proxy.py:87-101`), not household sessions or per-app sharing | H-34 (P1, before wiring) |
| S | An agent token on an app host | Refused: only people are allowed (`proxy.py:164-170`) | none | — |
| E | Open proxy | Upstream is never taken from the request: the app's Service in `app-<id>`, for an installed app, on its declared port (`proxy.py:234-262`); unauthenticated callers always get 401 | none | — |
| E | Path routes put an app on the dashboard's origin | Off by default (`proxy.py` docstring, `path_routes=False`) | Keep off | — |
| T | CA key theft | 0600 in 0700; refuses to replace an incomplete CA (`ca.py:95-137`) | Not wired; pairing QR with fingerprint is still to do | H-05 |
| I | Mesh API key | Read from a file that must be 0600 or stricter (`mesh.py:138-150`) | Outbound HTTP goes to the configured coordinator only (`mesh.py:105-135`); no user-supplied URL | — |

### 4.8 Phone and desktop apps (`mobile/`, `desktop/`)

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| I | Token at rest on the phone | Keychain / Keystore via `expo-secure-store`, "this device only", never AsyncStorage (`mobile/src/storage.ts:23-57`); desktop keeps tokens in the OS keychain, and its window has no shell, filesystem or HTTP permission (`desktop/src-tauri/capabilities/default.json`, `store.rs:3, 71`) | none | — |
| S | Token on plain HTTP | Phone allows cleartext to the hub (`mobile/app.json:67`, `usesCleartextTraffic`) | Same as H-05; remove once HTTPS ships | H-05 |
| T | The approval card shows less than what will run | Cards send `plan_sha256` and a passkey assertion (`mobile/src/lib/approvals.test.ts`) | The server never produces a plan hash (§4.2), so the "bound to the plan" wording in client docs is stronger than the server | H-13 |

### 4.9 Gateway as a whole (`app.py`, `guard.py`)

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| T | Path traversal through the SPA fallback | `resolve()` then `is_relative_to(dist)` (`routers/static.py:27-33`) | none | — |
| I | Script injection from app metadata | `javascript:` and `data:` URLs are never rendered: `source` must be https in the built-in check (`catalog.py:130-132`), links pass `_http_url` (`catalog.py:31`) and `safeHttpUrl` in the dashboard (`AppTrust.tsx:15`) | none | — |
| D | Large bodies, floods, token spraying | 256 KiB body cap; token buckets per principal; 10 wrong tokens a minute from a source starts a 15-minute back-off (`guard.py`, SECURITY.md §7a H-20) | Bucket table is bounded to 10,000 keys, so 10,000 bogus tokens evict real principals' buckets (they refill to full) | H-33 |
| D | Anyone on the LAN invents node ids on NATS | **Fixed here**: the registry holds at most 256 nodes and only makes room by dropping one already offline (`nodes.py`, `test_registry_is_bounded_against_invented_node_ids`) | The spoofing itself (publishing as a real node id) needs NATS users (H-06) | H-06 |

---

## 5. The six promises, checked one by one

### 5.1 Agents can never approve

**Result: held everywhere except one handler, which is fixed in this PR.**

Every code path that moves an action to `accepted`:

| Path | Who may call | Gate |
|---|---|---|
| `POST /v1/actions/{id}/approve` | owner persons only | `_approve` → `is_owner` (`actions.py:238`); household credentials also need scope `actions:approve` (`scopes.py:149`) and, once an owner has a passkey, a passkey assertion (`approval_guard`, `identity/service.py:964-1000`, hooked at `routers/actions.py:64`) |
| `POST /v1/alerts/{id}/fix` with `{"approve": true}` | owner persons only | **Hole found.** The handler called `ActionService.approve` directly (`routers/notifications.py:240` before this PR), so it skipped both the passkey step-up and the `actions:approve` scope check (its route needs only `actions:request`, `notifications.py:53`). Effects: (a) once an owner enrolled a passkey, a stolen owner session, API token or the static owner token could approve through this route with no passkey; (b) an owner API token minted with `actions:request` only could approve. Agents were already refused (`:212`). |
| MCP | agents | no approve tool exists (`mcp/tools.py`, `mcp/__init__.py`) |
| `onemind actions approve` (CLI) | whoever holds the token | calls the REST route above |

**Fix (this PR).** `fix` with `approve=true` now (1) requires the `actions:approve` scope for household credentials, and (2) runs the same approval guards as the approve route, so with a passkey on the box it answers `401 step_up_required` and leaves the fix as an ordinary pending request. Tests: `core/tests/test_identity_notify.py::test_fix_with_approve_cannot_skip_the_approval_gates` (fails on the old code, passes now) and `::test_fix_with_approve_still_works_without_passkeys`.

Also checked: `ActionService.approve` has exactly one other caller in the tree (the REST route); `executor.run` has exactly one (`actions.py:292`, after `accept_and_claim`); an agent kind cannot be role `owner` (`auth.py:45, 76-79`); API-token principals of kind agent get `Principal(kind="agent", role="agent")` and never `is_owner` (`service.py:271-273`); app agent tokens are created only at install and revoked at remove or failed install (`actions.py:316-352`).

### 5.2 Plan and approval binding

**Result: partly held. Binding to "what was requested" is real; binding to "what will run" is not.**

- Real: the action's type, params, requester and expiry are hashed into `action_sha256`; the passkey challenge is `sha256(action_id ‖ action_sha256 ‖ plan_sha256 ‖ nonce)`, single use, 120 s; a challenge for action A cannot approve B; changing the action after the challenge gives `409 plan_changed` (`identity/service.py:937-1000`, tests in `test_identity.py`).
- Real: at approval the install is re-checked (catalog entry, scan freshness, app state) and the rendered manifests are checked against the sandbox rules before one byte reaches the cluster, and exactly the checked bytes are applied (`executors.py:296-330, 256`).
- **Not real:** `plan_sha256` is never set by the server (§4.2). The owner approves "install `hermes`", not "install these objects with these images and these egress rules". The sandbox is the safety net, not the owner's eyes. An app whose manifests change between request and approval is approved as the new version (it must still pass the sandbox and a fresh scan). Backlog **H-13 (P1)**: render and store the plan at request time, show it on the card, bind its hash, refuse approval if the rendered plan differs.
- Not a hole: the catalog folder is root-owned on the box; changing it needs root already.

### 5.3 Authorization on every route

Method: a script walked every route of the app, called it without credentials, then as the static agent, guest and adult tokens (the output is the data behind this section). It is now a test, `core/tests/test_route_authz.py`, so a new route that forgets `Depends(principal)` fails CI.

- **77 method/path pairs.** 9 answer without a token, all on purpose and listed in the test: `/healthz`, `/openapi.json`, `/signin`, the dashboard files, and the five sign-in endpoints (`/v1/auth/setup`, `/login/options`, `/login`, `/enrol`, `/refresh`), each with its own proof (install token, one-time code, refresh token, passkey) and rate limit.
- **Every other route returns 401 without a credential** (68 of 68).
- **Owner-only operations refuse agent, guest and adult** (tested): approve, deny, approve-options, list/create/update/disable users, change app access, resolve alerts.
- **Everything else is gated by role in the handler or by scope:** sessions/passkeys/password/TOTP need a person (and a session for credential changes); channels, preferences, inbox and push need a person and are per person; logs need owner/adult; audit needs owner/adult (agents: own); events and metrics are filtered per role.
- **By design open to every signed-in principal** (v0 behaviour, F-14): `GET /v1/instance`, `/v1/nodes`, `/v1/apps`, `/v1/actions`, `/v1/monitoring/summary`, `/v1/alerts` (audience-filtered). The one with sensitive content is `GET /v1/actions` (kubectl tails): H-21.
- **Fail closed:** a household credential on a route with no scope entry needs `*` (`scopes.py:157-164`).
- Residual: static-file tokens skip the scope table; that is why H-36 (retire or expire them) matters.

### 5.4 SSRF and any outbound fetch

Every place the code can make a request to a URL it did not hard-code:

| Outbound | Target comes from | Control | Verdict |
|---|---|---|---|
| Notification channels, push devices (`notify/channels.py`) | a person's saved URL | Non-owners: https, globally routable only; everyone: no link-local/multicast/reserved/unspecified (so cloud metadata and `fe80::` are out), IPv4-mapped IPv6 unwrapped; resolved at save **and checked again on the connected peer** (DNS rebinding); no redirects; no env proxies; response read capped at 64 KiB; no URL credentials; SMTP plain only to loopback | Sound. Owner channels may reach the LAN on purpose (`lan: true`). Residual: stale `lan` after demotion (H-40). |
| Mesh coordinator client (`mesh.py:105-135`) | `ONEMIND_*` settings, not a request | Fixed destination | Sound; not wired |
| Reverse proxy upstream (`proxy.py:234-262`) | catalog + ledger, never the request | ClusterIP of the app's own Service only | Sound; not wired |
| `kubectl` (executor, monitoring) | fixed argv | App ids validated by `APP_ID_RE`; kustomize remote refs and root escapes refused before render (`policy.py:145`) | Sound |
| Go `onemind`/`onemindd`/updater clients | config and TUF index | TUF-verified downloads (`internal/update/download.go`) | Sound |
| CI tools (`sdk/tools/applib/common.py:79`, `os/update/*.py`) | https URLs in manifests/pins | Run in CI, not on the box | Out of scope |

### 5.5 Secrets at rest

| Secret | At rest | Verdict |
|---|---|---|
| Static owner token | sha256 in `tokens.yaml` 0640; plaintext on the install terminal once | OK; terminal scrollback is the weak point (H-36) |
| Passwords | scrypt, per-user salt (`crypto.py:35-38`) | OK |
| Session, refresh, API-token secrets | sha256 only (`service.py:300-315`) | OK (high-entropy) |
| TOTP seeds | **clear text** in `users.totp_secret` | P2 (H-41): seal with the notify `SecretBox` |
| Passkeys | public keys only | OK |
| Notification secrets, push endpoints | AES-256-GCM, key file 0600 in a 0700 folder; `chmod 0700` is applied to the key's **parent** folder, which defaults to the audit log's folder (`notify/crypto.py:38-45`) | OK; note the side effect |
| App agent tokens | hashed in the ledger; the plain token lives in a Kubernetes Secret applied server-side so it stays out of `last-applied-configuration` (`executors.py:252`) | OK; any pod in `app-<id>` can read it (by design); k3s Secrets encryption is on in the developer install only |
| k3s Secrets in the OS image | not encrypted (`k3s.service:17`) | **P0 for the image line** (H-12 image half) |
| `/data` | ext4, no encryption | P1 (H-11) |
| Backup repository | restic encrypts; key file on the box | OK |
| Signing keys | repo secrets, no protected environment | P0 (H-07) |
| Phone / desktop | Keychain / Keystore | OK |

### 5.6 Data-loss paths

| Path | What can be lost | Control | Verdict |
|---|---|---|---|
| `app.remove` | `kubectl delete namespace app-<id>` deletes the app's volumes (`executors.py:253-264`) | Needs owner approval; the card says "remove" | **No pre-removal snapshot and no warning that data goes with it**: H-42 (P1) |
| `app.install` over `failed` | Re-applies; PVCs persist | n/a | OK |
| Restore | Live data replaced | Temp copy + atomic rename; old copy removed only after success (`rewind.go:248-330`) | OK |
| Backup `forget`/`prune` | Old snapshots | Tag filter required; prune weekly only after a verified restore | OK |
| Storage plan | Disk contents | Plan-only today; "unused, not system, healthy" checks (`plan.go:105`) | Re-review at execution |
| Audit rotation | Evidence | None: file grows without bound (D) | H-20 remainder |
| Gateway crash mid-install | Unknown app state | `reconcile_interrupted` marks `outcome_unknown` and never retries (`actions.py:354-372`) | OK |

---

## 6. The ten things that matter most now

| # | Finding | Severity | Attacker | Evidence | Fix |
|---|---|---|---|---|---|
| 1 | **Plain HTTP on every interface**; bearer tokens and (without TLS) sessions are readable on the LAN. | High | A1, A4 | `deploy/install.sh:29, 524`; `core/onemind_core/__main__.py:19`; `ca.py` unwired | H-05 (P0) |
| 2 | **NATS has no users**: any LAN device can publish as any node, read the audit stream, flood the bus. | High | A1, A2, A6 | `deploy/install.sh:314-320`; `bus.py:50-58` | H-06 (P0) |
| 3 | **Signing keys readable by any workflow on any branch.** | High | A5 | `security-nightly.yml:151, 217-219, 293-295, 392-394` | H-07 (P0) |
| 4 | **OS image k3s has no PSA admission and no Secrets encryption** (the developer install has both). | High | A2, A7 | `os/rootfs/layers/base/usr/lib/systemd/system/k3s.service:17` | H-01/H-12 image half (P0) |
| 5 | ~~Alert `fix` + `approve` skipped passkey step-up and the approve scope~~ | High | A4, A8 | `routers/notifications.py:240` (old) | **Fixed in this PR** |
| 6 | The approval card does not show, and the passkey does not sign, the rendered plan. | Medium | A2, A3 | `identity/service.py:951`; no setter for `plan_sha256` | H-13 (P1) |
| 7 | A stolen owner session can mint a 365-day all-scope API token without a fresh passkey. | Medium | A4 | `identity/service.py:766` | H-35 (P1) |
| 8 | Removing an app deletes its data with no snapshot and no warning. | Medium | A3, owner error | `executors.py:253-264` | H-42 (P1) |
| 9 | Proxy would forward the gateway's cookies to apps and ignores household sessions. | Medium (before wiring) | A2 | `proxy.py:61, 87-101` vs `identity/service.py:133-135` | H-34 (P1) |
| 10 | Static-file tokens never expire, bypass scopes, and the owner one is printed to a terminal. | Medium | A4 | `auth.py:100-144`; `install.sh:570` | H-36 (P1) |

---

## 7. Assumptions, limits and UNVERIFIED items

- Edition 2 was read from `main` at `ad557c6`. Agent A's open branches (feat/dashboard-v2, feat/automation, feat/files, feat/app-secrets, feat/photos-server, feat/migrate-kit, feat/deploy-port27, feat/backups-on, feat/storage-actions and PRs #42 #47 #49 #55 #56 #57 #61 #62 #64) were **not** read or touched; anything they add (automation actions, file sharing, app secrets, photo server, migrate kit, backups-on, storage execution) needs its own pass when it merges. See the "for Agent A" list in the PR body.
- Not executed here: the OS image, QEMU battery, k3s admission behaviour and the Go test suites; their claims rest on reading the code and on CI. PostgreSQL was not started locally.
- One test, `test_notify.py::test_owner_listing_hides_other_peoples_destinations`, needs working DNS and fails in a sandbox without it; it passes in CI.
- UNVERIFIED: that Kubernetes `ValidatingAdmissionPolicy` as shipped in `deploy/k8s/gateway-rbac.yaml` rejects every non-`app-*` write on a live cluster (it is exercised by the e2e/k3d jobs, not by core tests).
- The competitor patterns of edition 1 §6 (Home Assistant OS, umbrelOS, Olares) are unchanged and not repeated; no code was copied from any competitor.
