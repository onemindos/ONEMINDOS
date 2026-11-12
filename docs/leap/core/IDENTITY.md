<!-- SPDX-License-Identifier: Apache-2.0 -->
# Household identity (CORE-SEC-2, CORE-SEC-3, DEV-API-5 part)

**Date:** 2026-11-12 · Part of [the leap](../README.md) · **Branch:** `feat/identity` · **Contract:** [§12.6](../../../sdk/contracts/poc-v0.md) (identity), §12.3 (step-up), §12.4 (`approve-options`) · **Backlog:** H-09 (tokens), H-16 (CSRF), H-21 (role reads) in [`HARDENING-BACKLOG.md`](../../security/HARDENING-BACKLOG.md) · **Code:** `core/onemind_core/identity/`, `core/onemind_core/routers/identity.py`, tests `core/tests/test_identity.py`.

> **Explain it like I am the founder**
> Until now the box knew people only by long passwords written into a file ("static tokens"). Anyone holding one was that person, forever.
> Now the box has **accounts**: you (the owner), adults, guests and children. You create the first owner account with the token the installer printed. Then you invite the others with a one-time link.
> People sign in with a password, plus an authenticator app if they want, or with a **passkey**. A passkey is a key pair kept by the phone or laptop and unlocked by your fingerprint or face. The box stores only the public half, so there is nothing on the box to steal.
> The rule that matters most: **once you have a passkey, every approval needs a fresh passkey signature over that exact action.** A stolen browser cookie, or a stolen token, can no longer approve anything.
> Scripts and agents get **API tokens** that say exactly what they may do, expire, and can be revoked at once.
> Guests and children see only the apps you share with them.

## 1. What a request carries

| Credential | Who uses it | How the box checks it |
|---|---|---|
| Cookie `onemind_session` (`__Host-` prefixed when `Secure`) + header `OneMind-CSRF` | the dashboard and phone web view | session row by sha256; idle 72 h, absolute 30 days; the CSRF header is required on every non-GET (H-16) |
| `Bearer om_ses_…` (1 h) + refresh `om_ref_…` (30 days, rotates on use) | the CLI and apps signing in as a person | session row by sha256 |
| `Bearer om_pat_…` / `om_agt_…` | scripts, personal agents | token row by sha256 (or the previous hash inside a rotation grace period) |
| `Bearer <static token>` | headless setups, the install owner token | `ONEMIND_TOKENS_FILE`, unchanged from contract v0 |

Static tokens are looked up first, then §11.2 app agent tokens, then identity. Only `identity/service.py` reads cookies; a test enforces that (H-16).

## 2. Sign-in flows

```console
# First owner, on a new box, with the token install.sh printed:
$ curl -X POST https://box.local:8443/v1/auth/setup -H "Authorization: Bearer $INSTALL_TOKEN" \
    -d '{"username":"zeus","password":"…","client":"cli"}'
→ 201 {"access_token":"om_ses_…","refresh_token":"om_ref_…","session":{…},"principal":{…}}
```

- **Setup** (`POST /v1/auth/setup`) works only while the box has no accounts. It accepts the install owner token or the contents of `ONEMIND_IDENTITY_SETUP_TOKEN_FILE`.
- **Invite** (`POST /v1/users {display_name, role}`, owner) returns `one_time.enrolment_url`, valid 24 hours and single use. The person opens it, picks a username and password (`POST /v1/auth/enrol`), and can then add a passkey.
- **Password** (`POST /v1/auth/login {username, password, totp?}`). With an authenticator app set up (`/v1/auth/totp/setup` then `/confirm`), the 6-digit code is required; a code is never accepted twice.
- **Passkey** (`POST /v1/auth/login/options` then `POST /v1/auth/login {passkey}`).
- `"client": "browser"` (default) sets the cookie pair; `"cli"` or `"app"` returns bearer tokens.
- 10 failed attempts a minute from one address lock that address out for 15 minutes (`429 rate_limited`, `Retry-After`).
- A minimal page at `/signin` covers setup, enrolment, sign-in and adding a passkey until the new UI ships its own screens.

## 3. Approvals with a passkey (F-2)

```http
POST /v1/actions/7f3c/approve-options          (owner)
→ {"challenge": "…", "action_sha256": "sha256:…", "plan_sha256": null, "expires_at": "…", "publicKey": {…}}

POST /v1/actions/7f3c/approve
{"webauthn": {"id": "…", "clientDataJSON": "…", "authenticatorData": "…", "signature": "…"}}
```

- The challenge is `sha256(action_id ‖ action_sha256 ‖ plan_sha256 ‖ nonce)`, valid 120 s, single use. `action_sha256` covers the action's id, type, params, requester and expiry; if any of them changes, the approval fails with `409 stale_precondition`.
- Once any active owner has a passkey and `ONEMIND_IDENTITY_REQUIRE_PASSKEY_APPROVAL` is on (the default), an approval without an assertion gets `401 unauthenticated`, reason `step_up_required`. A signed-in owner must use their own passkey. A static owner token may approve only with an owner's assertion.
- Before any owner has a passkey, approvals work as in v0. When the approver signed in through identity, the audit records `auth.approval.token` (F-12).
- Creating or changing users, sharing an app more widely, and adding or removing a passkey need a passkey sign-in in the last 5 minutes (`step_up_s`). Disabling a user, revoking a session or a token, and narrowing sharing need no step-up: removing power is always immediate (§12.1).

## 4. Roles, scopes and tokens

- Role defaults (§12.6) apply to identity sessions when `ONEMIND_IDENTITY_ENFORCE_ROLE_SCOPES` is on (default): owner `*`; adult every `:read` except `users:read`, plus `actions:request`, `tokens:self`, `logs:read`, `notifications:write`; guest and child the short lists of §12.6.
- Each route maps to the scopes that grant it in `identity/scopes.py`. A feature adds its own routes with `register_route_scope(methods, path_regex, scopes)` in its `register()`. A `/v1` route with no entry needs `*`, so it fails closed for scoped tokens and non-owners.
- A narrowed scope (`actions:read:own`, `actions:request:app.install`) does not satisfy a route that asks for the broad scope. It takes effect once the owning module filters by owner or type (DEV-API-7, DEV-MCP-2).
- `POST /v1/tokens {name, principal: "self" | {kind: "agent", id: "agent:<name>"}, scopes?, expires_in_days?}` → `201` with `one_time.token`. Person tokens: up to 365 days (default 90), default scopes = the creator's. Agent tokens (F-15): the `reader` bundle, 90 days at most. Nobody can grant a scope they do not hold. `actions:approve`, `*:admin`, `users:*` and `tokens:*` are never minted for an agent (`403`).
- An agent or person token is checked against its owner's **current** role on every request; disabling the person kills their tokens.
- `POST /v1/tokens/{id}/rotate {grace_s ≤ 3600}`, `DELETE /v1/tokens/{id}`. `GET /v1/tokens` lists file tokens read-only (`source: file`) to the owner.
- Guard rails (review of 2026-11-12):
  - Only the person who holds a token may rotate it, because rotating returns a working secret. An owner may still revoke anyone's token (`403` on rotate).
  - A token minting a token cannot give the new one a later expiry than its own.
  - A personal agent id cannot reuse an app's agent principal (`agent:<app-id>`), a static-file principal id or another person's agent id (`409`, `agent_id_taken`). Otherwise its requests would show up as that principal's.
  - Changing your own sign-in credentials needs a signed-in session, not an API token (`403`, `session_required`). This covers adding or removing a passkey, the password and TOTP. With a narrowed owner token you see and revoke only your own sessions; you need a full owner session or token to revoke anyone else's.
  - An approval with a passkey is refused (`409 plan_changed`) when the action's `plan_sha256`, or the one in the body, differs from the hash the challenge was issued for.
  - `POST /v1/auth/login/options` returns `429` once 1,000 unused sign-in challenges are open.

## 5. Per-app sharing

`GET`/`PUT /v1/apps/{id}/access {roles, people, auth}`. With no record, an app is shared with `owner` and `adult`. `owner` is always added. `GET /v1/apps` hides unshared apps from guest and child sessions on the next request. The networking stream's forward-auth calls `IdentityService.can_open(principal, app_id)` (on `app.state.identity`).

## 6. Settings (`ONEMIND_IDENTITY_*`)

| Variable | Default | Meaning |
|---|---|---|
| `RP_ID`, `ORIGINS` | request host; `https://<host>` | WebAuthn relying party and allowed origins (http only for localhost) |
| `COOKIE_SECURE` | `1` | turn off only on a plain-HTTP dev box |
| `REQUIRE_PASSKEY_APPROVAL` | `1` | §12.3 / F-2 |
| `ENFORCE_ROLE_SCOPES` | `1` | §12.6 / F-14 role defaults for identity sessions |
| `SESSION_IDLE_HOURS`, `SESSION_MAX_DAYS`, `ACCESS_TOKEN_MINUTES`, `REFRESH_DAYS`, `STEP_UP_S` | 72, 30, 60, 30, 300 | lifetimes |
| `LOGIN_FAILURES_PER_MIN`, `LOCKOUT_MINUTES` | 10, 15 | back-off (§12.1) |
| `SETUP_TOKEN_FILE` | unset | optional first-boot token for `POST /v1/auth/setup` |

## 7. Choices and limits (see DECISIONS-NEEDED §1.2)

- Passwords: stdlib scrypt, N=2^15, r=8, p=1, parameters stored per hash. TOTP: RFC 6238 SHA-1, 6 digits, ±1 step, replay-protected. TOTP secrets are stored readable (protected by the data-disk encryption of H-11).
- WebAuthn: `webauthn` 3.0.1 (BSD-3-Clause), with user verification required and attestation `none`.
- Static-file tokens keep v0 behaviour: no role scopes and no sharing filter.
- Audit lines (through `publish_event`): `auth.setup.*`, `auth.login.{succeeded,failed}`, `auth.enrol.*`, `auth.session.{revoked,refreshed}`, `auth.logout`, `auth.passkey.*`, `auth.totp.*`, `auth.password.*`, `auth.token.{created,rotated,revoked}`, `auth.step_up.{succeeded,failed,required}`, `auth.approval.token`, `authz.denied`, `user.{created,updated,disabled}`, `app.access.updated`. No line carries a password, token, cookie or code. Successful token use is recorded as `last_used_at` (at most once a minute), not as an audit line per request.

**Not in this branch (follow-ups):** `onemind tokens` CLI (DEV-CLI-9); break-glass rotation of the static owner token after first use; the `approval` field and `approved_via` on the action (DEV-API-7); adults requesting actions (the §3 action rules still allow only owners and agents); the `:own`/`:<type>` narrowing filters; `POST /v1/agents/{id}/suspend` (CORE-SEC-6); Kanidm/OIDC (CORE-SEC-10); dashboard screens (UI stream).
