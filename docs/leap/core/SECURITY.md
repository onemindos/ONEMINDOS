<!-- SPDX-License-Identifier: Apache-2.0 -->
# Core security (CORE-SEC)

**Date:** 2026-11-12 · **Status:** proposal · **Plan epics:** E2 (audit verify, checkpoint, kill switch), E3 (HTTPS + owner passkey), E8 (identity floor) · **Deeper docs:** [`docs/security/HARDENING-BACKLOG.md`](../../security/HARDENING-BACKLOG.md) (H-01…H-30) and [`THREAT-MODEL.md`](../../security/THREAT-MODEL.md) (branch `docs/security-threat-model`); the install sandbox is in [SANDBOX.md](SANDBOX.md) · **Serves:** brief 30 B4.5 (SB-5), B6, B9 (D-B9.1…D-B9.7); research 07; contract §3.

> **Explain it like I am the founder**
> Today the box signs you in with a long password-like token sent over plain HTTP on your home network. Anyone who sees it is you.
> This spec fixes that in order: HTTPS on the LAN, a passkey on your phone as the owner credential, tokens that expire and can be revoked, a locked-down message bus, an encrypted data disk, and an audit log that cannot be quietly rewritten.
> The approval rule stays the centre: an approval is a passkey signature over the exact thing you approve.

## 1. Goals and non-goals

| Goals | Non-goals (now) |
|---|---|
| HTTPS on the LAN by default; plain HTTP only on loopback | A OneMind cloud DNS or certificate service |
| Owner passkey (WebAuthn) on the gateway; approvals signed by it | Full household identity in Kanidm with child roles (E8 later; BD-03) |
| Token lifecycle: create, list, expire, revoke, rotate; prefixes for leak scanners | OAuth 2.1 authorization-server façade for MCP (D-B9.2, later) |
| NATS users with per-subject permissions + TLS | NATS operator/JWT accounts for third-party plugins (E7, later) |
| LUKS2 data partition with a recovery key shown once | Secure Boot enforcement on every board (SB-6/SB-7 follow their own gates) |
| Audit: `onemind audit verify`, signed checkpoints kept off the box, agent kill switch | FIPS, CJIS or government claims (plan §6) |

## 2. What exists today

| Piece | Where | State |
|---|---|---|
| Static bearer tokens from YAML, roles owner/adult/guest/agent | `core/onemind_core/auth.py`, `config.py` | `main` |
| Owner-only approve, agent → 403 | `core/onemind_core/actions.py` | `main` |
| Hash-chained JSONL audit + `verify()` | `core/onemind_core/audit.py` | `main`; no CLI, no checkpoint |
| Agent principals with hashed tokens; `/mcp` with no approve tool | `core/onemind_core/auth.py`, `mcp.py` | `feat/gateway-agent-mcp` |
| NATS with no auth; gateway on `0.0.0.0:8080` | `deploy/install.sh` | `feat/deploy-v0` |
| Signing keys as repo secrets in one job | `.github/workflows/security-nightly.yml` | `feat/os-security-pipeline` (H-07) |
| Ranked backlog with acceptance tests | `docs/security/HARDENING-BACKLOG.md` | `docs/security-threat-model` |

## 3. Design

### 3.1 HTTPS on the LAN (CORE-SEC-1, H-05)
- At first start the gateway creates a per-box CA (ECDSA P-256) and a server certificate for `<hostname>`, `<hostname>.local` and `onemind.local`, renewed yearly, stored under `/data/onemind/tls/` (0600).
- HTTPS on `:8443`; `:8080` binds `127.0.0.1` for local tools and the health gate.
- Pairing: console and dashboard show a QR with `{url, ca_sha256}`, **never a token**. The phone app pins that fingerprint (MOBILE).
- When remote access is on, a Tailscale certificate may serve the tailnet name (founder decision F-1). Warn that tailnet certificate names appear in public certificate-transparency logs (research 12 §8.1).

```console
$ onemind tls show
CA fingerprint  sha256:4be1…c09a
Serves          https://onemind.local:8443  (valid to 2027-11-16)
Pair a phone    onemind tls qr        # prints a QR: URL + fingerprint, no secret
```

### 3.2 Owner passkey and signed approvals (CORE-SEC-2, SEC-P1, SEC-B2)
- First boot (or `onemind init` headless) registers the owner's passkey. The static owner token becomes a **break-glass** credential: console-only, single use, then rotated.
- Routes (contract change):

| Method and path | Who | Does |
|---|---|---|
| `POST /v1/auth/passkeys/register/options` · `/register` | owner (first boot or signed in) | WebAuthn registration |
| `POST /v1/auth/login/options` · `/login` | anyone | returns a session (web: `HttpOnly; Secure; SameSite=Strict` cookie + CSRF header, H-16; apps and CLI: bearer) |
| `GET /v1/auth/sessions`, `DELETE /v1/auth/sessions/{id}` | owner | list and revoke sessions |
| `GET /v1/me` (defined in [API.md](../dev/API.md) §5.8, DEV-API-5) | any principal | `{id, kind, role, scopes}` (fixes the "role unknown until 403" gap in the dashboard and mobile) |

- **Approval with step-up:** the client asks the gateway for a challenge bound to the action, then signs it.
```http
POST /v1/actions/7f3c/approve-options
→ 200 {"challenge": "b64…", "action_sha256": "c1d2…", "plan_sha256": "9a1e…", "expires_at": "2026-11-16T10:05:00Z"}

POST /v1/actions/7f3c/approve
{"plan_sha256": "9a1e…", "webauthn": {"id": "…", "clientDataJSON": "…", "authenticatorData": "…", "signature": "…"}}
→ 200 {"id": "7f3c", "state": "accepted", "approved_by": "person:owner", "approval": "passkey"}
```
The challenge is `sha256(action_id ‖ action_sha256 ‖ plan_sha256 ‖ nonce)`, valid 120 s, single use. A stolen session cookie cannot approve.

### 3.3 Tokens (CORE-SEC-3, H-09)
Tokens become ledger rows `{id, hash, principal, kind: person|agent|device, created_at, expires_at, last_used_at, revoked_at}`; the YAML file is bootstrap only. Format `om_<kind>_<32 random bytes, base64url>` so gitleaks and GitHub secret scanning can match `om_`.

```console
$ onemind tokens create --kind agent --name hermes-agent --expires 30d
id        tok_5d1e
token     om_agent_EXAMPLEONLY…      (shown once)
expires   2026-12-16
$ onemind tokens list
ID        PRINCIPAL            KIND   EXPIRES     LAST USED
tok_5d1e  agent:hermes-agent   agent  2026-12-16  2 min ago
$ onemind tokens rotate tok_5d1e     # new secret, old one fails on the next request
```
Same calls: `POST /v1/tokens`, `GET /v1/tokens`, `POST /v1/tokens/{id}/rotate`, `DELETE /v1/tokens/{id}` (owner only; each audited).

```python
tok = client.tokens.create(kind="agent", name="hermes-agent", expires="30d")   # Python
```
```ts
const tok = await om.tokens.create({ kind: "agent", name: "hermes-agent", expires: "30d" }); // TypeScript
```
```go
tok, err := om.Tokens.Create(ctx, onemind.TokenSpec{Kind: "agent", Name: "hermes-agent", Expires: "720h"}) // Go
```

### 3.4 Agent kill switch (CORE-SEC-6, plan E2)
`POST /v1/agents/{id}/suspend` (owner) revokes all of that agent's tokens and cancels its pending actions at once. **Reducing power is instant; adding power is an action**, so `resume` is an action the owner approves with a passkey. Acceptance: after suspend, the next MCP call returns 401.

### 3.5 NATS auth (CORE-SEC-4, H-06)
`nats.conf` with nkey users: `gateway` (sub `onemind.node.*.status`, pub `onemind.audit`, `onemind.alert.>`), one user per node issued at approved join (pub only `onemind.node.<node_id>.status`), deny all else; TLS with the box CA. Seeds in `/etc/onemind/nats.nk` (0600).

### 3.6 Data at rest (CORE-SEC-5, H-11, H-12, H-17)
- LUKS2 on `onemind-data` at install or first boot; TPM2 unlock (PCR 7 + signed PCR 11 policy, systemd initrd, SB-5) where present, passphrase otherwise; recovery key shown once and part of the emergency kit (BACKUPS).
- k3s `secrets-encryption: true`; `flannel-backend: wireguard-native` for multi-node. Both are cluster-creation settings: set them **before** the founder moves data.
- Developer installs (stock Debian) do not get LUKS from OneMind; the installer says so.

### 3.7 Audit you can check (CORE-SEC-6, H-10)
```console
$ onemind audit verify
chain       ok   1..48211
checkpoints ok   last seq 48200 signed 2026-11-16T09:00Z (ed25519 key a3f1…)
external    ok   phone holds checkpoint 48200; NATS stream replica on node 2 agrees
```
Every N lines and hourly the gateway appends a signed `audit.checkpoint {seq, head_hash}`; the key lives outside the audit directory. Checkpoints are published to JetStream (replicated when nodes exist) and stored by the phone app, so a full rewrite or a cut tail is caught.

### 3.8 Pending-request cap and plan card (CORE-SEC-7, H-13, H-14)
At most 10 `awaiting_approval` actions per agent (a setting; plan E3: the 11th gets 429 `rate_limited`). H-14 proposed 5 and 409; this spec follows the plan's number and uses 429 because the limit is about rate, not state. Owners are not capped. The agent's `reason` is always shown as "written by agent <id>", never as the OS's words.

## 4. Security model (summary)

| Asset | Attacker | Control | Epic |
|---|---|---|---|
| Owner session | LAN sniffer | HTTPS, passkey, cookie flags | SEC-1, SEC-2 |
| Approval | stolen session, prompt-injected agent | passkey-signed challenge bound to plan hash; agents have no approve path | SEC-2 |
| Tokens | leaked file or log | expiry, revoke, rotate, `om_` prefix scanning | SEC-3 |
| Bus | pod or LAN device | nkeys + per-subject permissions + TLS | SEC-4 |
| Disk | theft | LUKS2, secrets encryption | SEC-5 |
| Audit | root on the box | signed checkpoints stored elsewhere | SEC-6 |
| Release keys | malicious branch workflow | GitHub environments, split signers (H-07) | SEC-8 |

## 5. Versioning and compatibility
- Static tokens keep working through contract v0.x; new installs mint `om_` tokens; v1 drops plain static tokens except break-glass.
- `/v1/auth/*`, `/v1/tokens`, `/v1/agents/*` are additive routes (contract §3 PR). Error set adds `rate_limited` (429).
- Approve without `webauthn` stays accepted in v0 with audit flag `approval: token`; a setting `require_passkey_approval` (default on for new installs, F-2) turns it off.
- `:8080` on loopback is a breaking change for LAN clients; the installer prints the HTTPS URL and the phone app migrates on next pairing.

## 6. Test plan and acceptance
The acceptance tests are those of H-05, H-06, H-09, H-10, H-11, H-12, H-14, H-17 in the backlog, plus:

| Test | Pass when |
|---|---|
| Replay | A replayed approval link or challenge without a fresh passkey assertion fails (plan E3) |
| Step-up | A session cookie without passkey assertion cannot approve when `require_passkey_approval` is on |
| Kill switch | Suspend → next MCP call 401; pending actions of that agent → `cancelled` |
| Audit | One changed byte fails at that seq; full rewrite caught by checkpoint signature; cut tail caught against the phone's checkpoint |
| Phone | Approve in under 10 s on a real Android phone over HTTPS (plan E3) |

## 7. Build steps

| Epic | Step | Effort | Depends on | Backlog ids |
|---|---|---|---|---|
| CORE-SEC-1 | HTTPS per-box CA, loopback HTTP, pairing QR | M | – | H-05, H-25 |
| CORE-SEC-2 | Owner passkey, sessions, whoami, passkey-signed approvals | M | 1 | SEC-P1, SEC-B2 |
| CORE-SEC-3 | Token lifecycle + CLI | M | – | H-09 |
| CORE-SEC-4 | NATS nkeys + TLS | M | 1 | H-06 |
| CORE-SEC-5 | LUKS2 + k3s secrets encryption + WireGuard pod traffic | M | image stream | H-11, H-12, H-17 |
| CORE-SEC-6 | `onemind audit verify`, signed checkpoints, kill switch | S | 3 | H-10, E2 |
| CORE-SEC-7 | Pending cap, plan card fields, agent-written label | S | SANDBOX-2 | H-13, H-14 |
| CORE-SEC-8 | Signing keys in GitHub environments, split jobs | S | – | H-07 |
| CORE-SEC-9 | CSP and security headers, body and rate limits | S | – | H-18, H-20 |
| CORE-SEC-10 | Identity floor: on-box IdP (Kanidm), roles, retire v0 tokens | L | 2 | E8, D-B9.1 |

## 8. Who owns which files

| Branch (proposed) | Files |
|---|---|
| `feat/gateway-tls` | new `core/onemind_core/tls.py`, `config.py`, `__main__.py`, `deploy/systemd/onemind-gateway.service` |
| `feat/passkeys` | new `core/onemind_core/passkeys.py`, `sessions.py`; `dashboard/src/pages/SignIn.tsx` |
| `feat/tokens` | new `core/onemind_core/tokens.py`, `ledger.py` (token table), `cmd/onemind/cli/tokens.go` (with DEV-CLI-9) |
| `feat/nats-auth` | `deploy/install.sh` (`nats_install`), `core/onemind_core/bus.py`, `internal/agent/agent.go` |
| `feat/audit-verify` | `core/onemind_core/audit.py`, `cmd/onemind/cli/audit.go` (with DEV-CLI-5), new `core/onemind_core/agents.py` (suspend) |
| image stream | `os/boards/*/layout.yaml`, `os/assemble/assemble.py`, initrd units, `k3s.service` |
| `feat/os-security-pipeline` follow-up | `.github/workflows/security-nightly.yml` |
| Hotspots (serialized) | `core/onemind_core/app.py` (one `include_router` per module), contract §3, `cmd/onemind/cli/root.go` (one line per command group) |
