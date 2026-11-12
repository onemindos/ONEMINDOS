<!-- SPDX-License-Identifier: Apache-2.0 -->
# Household accounts: umbrelOS study and the OneMind design

**Date:** 2026-11-12 · **Status:** study and proposal. It changes no decision in [`docs/DECISIONS.md`](../DECISIONS.md) and does not edit the contract [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md); the contract changes it needs are listed in §5 as their own PR.
**Area:** accounts for the whole household: roles, sign-in, two-factor, sessions and devices, per-app sharing, single sign-on into apps, children and guests.
**Builds on:** contract §3 (principals and roles), [API.md](../leap/dev/API.md) §5.8, §5.9, §8, [SECURITY.md](../leap/core/SECURITY.md) (CORE-SEC-2, CORE-SEC-10), [MCP.md](../leap/dev/MCP.md) §5, BD-03 and D-B9.1 to D-B9.4 in [research 30](../../research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md), the forward-auth design in `docs/architecture/NETWORKING.md` §9.3 (branch `feat/net`, not merged), requirements U-2 and U-3 in [`docs/REQUIREMENTS.md`](../REQUIREMENTS.md).

> **Explain it like I am the founder**
> umbrelOS now has one owner plus "members". The owner makes each member's password, picks which apps and folders they can open, and can see and end their logins. Members can add an authenticator code. It works and it is polished, but it is passwords only, the owner knows everyone's password, there are no children or guests, and apps behind the login do not learn who you are, so the whole house shares each app's single login.
> OneMind will sign people in with **passkeys** (Face ID or a fingerprint on the phone), give each person a role (**owner, adult, child, guest**), let the owner pick which apps each person sees, and pass the person's identity into apps so Immich, Jellyfin and the rest show *your* library, not one shared account. Children get an allow-list, time windows and an "ask a parent" button. Agents never act as the owner; they act for one person, inside a grant, and still need an owner's approval.

**Licence rule followed in this document.** umbrelOS is PolyForm Noncommercial 1.0.0 (checked at tag `2.1.0-beta.1`, commit `6f357e18d0a4`). This page describes its architecture and cites file paths; it copies no code, strings, assets or UI text. Every OneMind piece in §4 is our own code on components whose licences are recorded with a pinned version.

---

## 1. How umbrelOS does it (commit `6f357e18d0a4`)

All paths are relative to the umbrelOS repository root. `D:` = `packages/umbreld/source/modules/`, `U:` = `packages/ui/src/`.

### 1.1 Architecture in one picture

```
 browser / native app                       umbreld (Node, one process)
 ───────────────────                        ─────────────────────────────────────────────
 login screen (account picker) ──tRPC──►    user.login ──► User.validateAccountLogin (bcrypt + TOTP)
                                                        └─► Auth.createSession → 4 credentials
                                                            (dashboard bearer, app-gateway cookie,
                                                             browser-session cookie, URL token)
 dashboard calls ──Bearer + cookie──►       isAuthenticated / isOwner middleware (trpc)
 app port (e.g. :2283) ──────────────►      AppGateway.isAuthorized → Auth.authorizeApp
   no cookie → app-auth page (own port)        owner/system: every app; member: shared apps only
   → login → one-shot handoff POST  ───►    /umbrel_/api/v1/auth/handoff sets the app cookie
 native app ── loginNative ──►              device token (no expiry) + 1-hour access token
 MCP client ──►                             mcp server runs as the owner account
```

State lives in two places: the main YAML store (`user` object for the owner, `members` array, `appMemberShares`) and `secrets/auth/sessions.yaml` (mode 0700 directory) for sessions.

### 1.2 Accounts and roles (`D:user/`)

| Topic | What the code does | Where |
|---|---|---|
| Roles | Exactly two: **owner** (fixed id `'0'`) and **member**. No admin, child or guest role. The API reports `role: 'owner' \| 'member'` | `D:user/constants.ts`, `D:user/routes.ts` (`get`) |
| Owner record | Top-level `user` object: name, bcrypt hash (cost 12, `$2b$`), optional `totpUri`, wallpaper, language, temperature unit, avatar hash. Name, hash and language are mirrored into the RAID config store for recovery; the owner hash is also synced to the Linux `umbrel` user with `chpasswd` | `D:user/user.ts` (`setPassword`, `syncSystemPassword`, `#setOwnerHashedPassword`) |
| Member record | Entry in `members`: slug id derived from the name at creation and never changed (a second "Alice" becomes `Alice-2`), display name (renamable, unique across accounts), bcrypt hash, optional `totpUri`, optional **plaintext Samba password** (needed for NT auth, documented in a comment), per-member wallpaper, language, widgets, favorites, view preferences | `D:user/user.ts` (`Member` type, `createUser`) |
| Creation | Owner only. Owner types the member's name and password (min 6 characters); the server makes a private home folder and a per-account onboarding notification | `D:user/user.ts` `createUser`; route `createUser` is `privateProcedure` (owner-only) |
| Deletion | Two-phase and crash-safe: the record becomes a **tombstone** `{id, deleted: true}` under the store write lock, so sign-in stops at once and the id is reserved forever; cleanup then revokes sessions, removes cloud-drive and Samba state, Photos sources, the private home, file and app shares and the avatar, each attempted even if another fails; `finishPendingDeletions` resumes after a restart | `D:user/user.ts` `deleteUser`, `#finishDeletion`, `finishPendingDeletions` |
| Recovery | The owner can reset a member's password; this also **clears the member's 2FA** so a lost authenticator does not force deleting the account. The owner's own password has no reset path in this module | `D:user/user.ts` `resetMemberPassword` |
| Authorization default | Every authenticated route is **owner-only unless it opts in** with `privateProcedureWithMembers`; `isOwner` re-checks `accountId === '0'` | `D:server/trpc/trpc.ts`, `D:server/trpc/is-authenticated.ts` |

### 1.3 Sign-in, 2FA and the session model (`D:auth/`)

- **Login.** `validateAccountLogin(userId, password, totp?)` checks bcrypt, then TOTP if the account has a secret, and returns a `sessionIssuanceRevision`. `createSession` commits only if that revision is unchanged and no credential change is in flight (`beginAccountCredentialChange` brackets every password or 2FA write). This closes the race where a login checked against the old password lands after a password change. (`D:user/user.ts`, `D:auth/auth.ts` `sessionIssuanceRevision`, `#storeNewSession`.)
- **TOTP.** `notp` with `thirty-two` base32; 32-byte secret, SHA-1, 6 digits, 30 s, verified with `window: 10` (about ±5 minutes). The secret is stored as the full `otpauth://` URI in the account record. We found no record of the last accepted code, so a code can be reused inside its window. (`D:utilities/totp.ts`.)
- **Credentials per session.** One session carries several credentials, each with an **audience**: `dashboard` (bearer), `app-gateway` (cookie for app ports), `browser-session` (cookie), `http-api-token` (URL token for downloads and thumbnails, derived with HMAC from the system token so it is never stored), plus `native-access`, `native-device` and `photo-backup` for native clients. Tokens look like `umbrel_<id>_<secret>`; only sha256 of the secret is stored and compared in constant time. (`D:auth/auth.ts` `CredentialAudience`, `#createCredential`, `#createDerivedCredential`.)
- **Lifetimes.** Browser sessions: 7 days, sliding (`renewSession`). Native: a device token that never expires until revoked, exchanged for a 1-hour access token (`refreshNativeAccess`). WebSocket tickets and app hand-offs: 30 s, single use. Photo-backup grants survive app exit and are bound to one photo source. (`D:auth/auth.ts` constants, `issuePhotoBackupGrant`.)
- **Revocation is a security boundary.** Revoking a session terminates its WebSockets and app sockets at once rather than closing them politely (`#closeSessionConnections`). A change of app sharing bumps `#appAccessRevision` and re-checks every open app socket (`appAccessChanged`). An expiry timer re-checks wall time so a clock jump cannot keep a socket open.
- **Native clients** describe themselves (`id`, `platform`, `deviceClass`, versions) with a schema that is an identifier format, not an allow-list (`D:auth/native-client.ts`). The Apple clients keep the device credential in the Keychain (`clients/apple/UmbrelKit/Tests/UmbrelKitTests/KeychainTests.swift`, `clients/README.md`).
- **Restore.** On the first start after a backup restore, all sessions and the system token are wiped (`D:auth/auth.ts` `start`).
- **Throttling.** We found no login attempt limiter in `D:user/`, `D:auth/` or `D:server/app-auth.ts` (searched for rate limiting; the only hits are in `lan-ingress` and `files/cloud`).
- **Pre-login exposure.** `user.listAccounts` and the app-auth `/v1/account/accounts` route are public, so anyone on the network can list every account's name, avatar and wallpaper (`D:user/routes.ts`, `D:server/app-auth.ts`).

### 1.4 Sessions and devices screen

`listSessions`, `revokeSession`, `revokeOtherSessions` for one's own account; the owner additionally gets `listAccountSessions`, `revokeAccountSession`, `revokeAllAccountSessions` for any member. Each row carries the client kind (browser with user agent, or native with platform and device class), created and last-seen times, and a `current` flag. Client metadata is labelled descriptive: the credential kind decides whether a session is native. (`D:user/routes.ts`, `D:auth/auth.ts` `#activeSessionsForAccount`; UI `U:routes/settings/sessions.tsx`, user-agent parsing in `U:modules/auth/vendored-ua-parser.ts`.)

### 1.5 Per-app sharing and the app gateway

- **Data.** `appMemberShares: [{appId, sharedWith: 'all' | memberId[]}]`; `appId: '*'` shares every app including future installs. Owner-only routes `apps.memberShares`, `addMemberShare` (upsert), `removeMemberShare`. (`D:apps/apps.ts` §"Member shares", `D:apps/routes.ts`.)
- **Effect.** `apps.list` and `apps.state` return only shared apps to a member; members can browse a sanitised registry but cannot install. (`D:apps/routes.ts`.)
- **Folder shares** are the same shape on paths and always **read-write** (comment on `MemberShare` in `D:files/member-shares.ts`).
- **Gate.** Each app port is fronted by the in-process `AppGateway`. It strips umbrel's own cookies before proxying (so an app cannot steal them), honours the manifest's auth allow/deny path lists, and calls `Auth.authorizeApp`. Only `x-forwarded-*` headers are added; **no identity header reaches the app**. (`D:app-gateway/app-gateway.ts` `isAuthorized`, `stripAppGatewayCookies` in `D:auth/app-gateway-cookie.ts`.)
- **App login flow.** Without a cookie the browser lands on a separate app-auth page (own port, own Vite entry `U:app-auth.tsx`). The person picks an account and signs in; the server creates a session, issues a 30 s single-use **hand-off** token, and the page form-POSTs it to `/umbrel_/api/v1/auth/handoff` on the app's port, which sets that port's cookie. CSP `form-action` is widened to exactly the LAN host on another port or the app's onion name. If the app is not shared with that account, the new session is revoked at once and a 403 is returned. (`D:server/app-auth.ts`, `D:app-gateway/app-gateway.ts` `acceptHandoff`.)

### 1.6 MCP and agents

The MCP server authenticates its caller as the **owner account** and describes itself to agents as controlling the owner account; tools resolve paths as the owner (`D:mcp/server.ts`, `D:mcp/mcp.ts`). There is no agent principal distinct from the owner, no per-member agent and no approval step.

### 1.7 What the person sees

1. **Lock screen:** a dock-like strip of account avatars with the owner in the middle and members alternating left and right; the background switches to the selected person's wallpaper; password, then a 6-digit code if 2FA is on (`U:modules/auth/account-dock.tsx`, `use-account-picker.ts`, `login-form.tsx`, `two-factor-form.tsx`, `U:routes/login.tsx`).
2. **Settings → Users (owner):** list of accounts; **create** form (name, password, avatar, apps: all or picked, folders, external and network storage, Samba) → a "created" card with a ready-made invite message that includes the password; **edit** view per member (app and folder shares, storage and Samba access, reset password, manage sessions, delete with confirmation). New users inherit everything currently shared with "everyone" (`U:routes/settings/users.tsx`, `U:modules/user-sharing/index.tsx`, `new-user-access.ts`).
3. **Sharing from the object:** "share with users" dialogs on an app and on a folder (`U:features/files/components/dialogs/share-users-dialog/`, `U:hooks/use-app-member-shares.ts`).
4. **Account settings (anyone):** name, password, avatar, wallpaper, language, 2FA enable (QR from a generated URI, confirm with a code) and disable (needs a code), sessions (`U:routes/settings/2fa*.tsx`, `change-password.tsx`, `sessions.tsx`).
5. **Opening a shared app:** app-auth page with the same account strip → app opens; an unshared app shows a "not shared with this account" error.

### 1.8 Assessment

Strong: the session engine (audiences, derived URL tokens, issuance revision, immediate socket kill, tombstoned deletion, owner-managed sessions) and the polish of the picker and sharing screens. Weak for a household: passwords only; the owner sets and sees member passwords; a single irreplaceable owner; no child, guest or second-admin role; read-write-only folder shares; apps learn nothing about the person, so in-app accounts are shared; agents act as the owner; a wide TOTP window with no replay record; no visible login throttling; account names public before sign-in.

---

## 2. What OneMind has today

| Piece | Path | State |
|---|---|---|
| Principals `{id, kind: person\|agent, role: owner\|adult\|guest\|agent}` from a hot-reloaded YAML file, sha256 lookup, `is_owner` false for any agent | `core/onemind_core/auth.py`, `core/examples/tokens.example.yaml` | `main` |
| Only a person owner approves; agents get 403 | `core/onemind_core/actions.py`, contract §3 | `main` |
| Hash-chained audit log | `core/onemind_core/audit.py` | `main` |
| Agent principals per app (`agent:<app-id>`, hashed tokens, revoked at removal), `/mcp` with no approve tool | `core/onemind_core/{auth,mcp}.py` | branch `feat/gateway-agent-mcp`, not merged |
| Users API shape (`/v1/me`, `/v1/users`, enrolment link, disable), token lifecycle, scopes and role defaults, step-up | [API.md](../leap/dev/API.md) §5.8, §5.9, §8 | spec |
| Owner passkey, sessions, passkey-signed approvals | [SECURITY.md](../leap/core/SECURITY.md) §3.2, CORE-SEC-2 | spec |
| Kanidm v1.12.0 on the box, household roles owner/adult/child/guest/operator | BD-03, D-B9.1 in research 30 | decision, not built |
| Agent rights = owning person ∩ grant | [MCP.md](../leap/dev/MCP.md) §5.1, DEV-MCP-2 | spec |
| Edge with forward-auth, `X-OneMind-Principal`/`X-OneMind-Role` headers, per-app `access` (owner only, adults, everyone) | `docs/architecture/NETWORKING.md` §9.3, CORE-NET-5, CORE-NET-8 | branch `feat/net`, design only |
| Dashboard sign-in by pasting a token; People mock in Settings | `dashboard/`, `ui/demo/src/screens/Settings.tsx` | `main` |
| Phone keeps hub URL and token in the OS secure store | `mobile/src/storage.ts` (`expo-secure-store` 58.0.3) | `main` |
| UI parity gaps PU-09 (real login), PU-18 (sessions and tokens), PU-28 (multi-user) | `docs/strategy/umbrel-parity.md` | branch `feat/uileap` |
| Requirements: children use it (U-2), parental controls (U-3) | `docs/REQUIREMENTS.md` | `main` |

Nothing yet implements people, sessions, 2FA, app sharing or SSO.

---

## 3. Match and beat

### 3.1 Where OneMind matches umbrelOS (keep these ideas, written our own way)

| umbrelOS behaviour | OneMind equivalent |
|---|---|
| Credentials split by audience (dashboard, app cookie, URL token, native device) | Gateway session with separate credentials: web cookie + CSRF, edge app cookie, short download tickets, native refresh token (§4.5) |
| Issuance revision so a login cannot land on stale credentials | Every session row stores the person's `credential_revision`; a credential change bumps it and kills older sessions |
| Revocation closes live sockets at once; share change re-checks open app streams | Gateway publishes `auth.session.revoked` and `access.changed` on the bus; edge drops its cache and connections immediately |
| Tombstoned deletion, resumable cleanup, ids never reused | Disable → delete with a tombstone; Kanidm person UUID is the permanent id |
| Owner can list and end anyone's sessions | Same, plus the person sees when the owner did it (audit) |
| Per-person wallpaper, language, widgets, favourites, avatar | Per-person Home profile (PU-03, PU-28) |
| Shared-with-everyone defaults applied to new people | "Household" access mode on an app automatically covers new adults |
| Sessions wiped after a restore | Same; passkeys survive because Kanidm's database is restored |

### 3.2 Where OneMind beats umbrelOS

| # | Beat | Why it matters |
|---|---|---|
| B1 | **Passkeys first**, TOTP only as a fallback, password optional | Phishing-proof; nothing for a child to forget |
| B2 | **Nobody learns anyone's password.** Invite = one-time enrolment link or QR; recovery = a new enrolment link | umbrelOS has the owner choose the member's password and put it into an invite message |
| B3 | **Roles that fit a family:** owner (more than one allowed), adult, child, guest, plus agent | umbrelOS has one fixed owner and flat members |
| B4 | **Real SSO into apps:** OIDC clients for apps that support it, trusted identity headers for apps that read them; each person gets their own account inside Immich, Jellyfin and the rest | umbrelOS gates the port but passes no identity, so the house shares one in-app login |
| B5 | **Per-app roles and read-only access** (viewer, user, admin inside the app; read-only folders) | umbrelOS shares are all-or-nothing and folders are read-write |
| B6 | **Children:** allow-list only, time windows, "ask for an app" that becomes an approval, guardian view of the child's access log, which the child can see too | Absent in umbrelOS; our requirement U-3 |
| B7 | **Guests that expire** and have no private storage | Absent in umbrelOS |
| B8 | **Agents never act as the owner**: each agent belongs to a person, rights = person ∩ grant, it requests and an owner approves | umbrelOS MCP runs as the owner |
| B9 | **Hardening:** login throttling per person and per source, TOTP window ±1 step with replay record, no public account list unless the owner turns on the picker | Gaps seen in §1.3 |
| B10 | **Step-up for dangerous changes:** inviting an owner, changing roles, widening access and approving destructive actions need a fresh passkey assertion | umbrelOS uses the 7-day session for everything |
| B11 | **Every sign-in and access change in the hash-chained audit log**, readable by owners and adults (own entries) | umbrelOS has logs only |
| B12 | **Sign-in works when k3s is down and offline** (identity runs on the host, §4.1) | Required by `docs/architecture/DEPLOYMENTS.md` |

---

## 4. OneMind design

### 4.1 Components and licences

| Component | Role | Licence (pinned) | Notes |
|---|---|---|---|
| **Kanidm** `v1.12.0` (commit `a52b723ce8ef`) | Identity provider: persons, groups, passkeys, TOTP fallback, OAuth2/OIDC provider for the gateway, the phone and OIDC-capable apps | MPL-2.0, file-level copyleft; shipped as a separate component, notices kept (`research-output/evidence/license-matrix.csv`) | Runs as a **host service on the hub** (systemd), not in k3s, so sign-in survives a k3s failure. Needs a placement decision (ACCT-D2) because research 30 lists a `kanidm` chart |
| OneMind gateway (FastAPI `0.162.5`, MIT) | Sessions, roles → scopes, app access policy, forward-auth decisions, step-up, audit; the MCP authorization façade (D-B9.2) | our code, Apache-2.0 | New modules in §5 |
| `onemind-edge` (Go `1.26`, standard library) | TLS front door, calls `/v1/auth/forward`, injects identity headers, strips client copies | our code, Apache-2.0 | CORE-NET-5 (branch `feat/net`) |
| WebAuthn verifier in the gateway | Passkey-signed approvals bound to `plan_sha256` (Kanidm cannot sign an arbitrary challenge) | chosen by CORE-SEC-2; candidate `py_webauthn` (BSD-3-Clause per upstream) | **Version not pinned yet;** pin in `os/versions.lock.yaml` on adoption |
| `expo-secure-store` `58.0.3` | Phone keeps the refresh token | MIT | Already in `mobile/package.json` |
| Phone OIDC sign-in | Auth code + PKCE in the system browser (passkeys work there without a native passkey library) | candidate `expo-auth-session` (MIT per upstream) | **Not installed; pin on adoption** |
| Headscale (from CORE-NET) | Mesh accounts named after the person | BSD-3-Clause, per NETWORKING.md | Later: OIDC login against Kanidm |

Nothing from umbrelOS is used. The capability claims for Kanidm in this table come from its v1.12.0 README (`research-output/evidence/sources/BRIEF30/kanidm-v1.12.0_README.md.txt`: passkeys, OAuth2/OIDC, Unix integration with TPM offline auth, replication). Group-based OAuth2 scope maps, credential-reset links and account expiry come from Kanidm's documentation and are **to be confirmed at v1.12.0 in ACCT-1**.

### 4.2 Roles and what they can do

Contract v1 roles are `owner`, `adult`, `guest`, `agent`; this design adds **`child`** as a new enum value, which API.md §5.8 already allows. `operator` (D-B9.1) is out of scope here.

| Capability | owner | adult | child | guest | agent (for its person) |
|---|---|---|---|---|---|
| Approve actions | yes (step-up for `destructive`) | no | no | no | never |
| Request actions | yes | yes (own scope) | only `access.request` | no | yes, ∩ grant |
| Invite, change roles, disable people | yes, step-up | no | no | no | never |
| Change app access | yes | no; may request | no; may ask | no | may request |
| Open apps | all | apps with mode `household` or `adults`, or named | allow-listed apps, inside time windows | named apps until expiry | no app UIs (agent tokens are refused on app hosts) |
| Own sessions, passkeys, tokens | yes | yes | sessions only | sessions only | n/a |
| Read audit | all | own entries | own entries | no | no |
| Private storage | yes | yes | yes (guardians can see size, not content) | no | no |

Roles are **Kanidm group memberships** (`onemind_owners`, `onemind_adults`, `onemind_children`, `onemind_guests`); exactly one per person, enforced by the gateway. The last active owner cannot be demoted or disabled (API.md §5.8). The role-to-scope table of API.md §8.2 gains a `child` row: `instance:read`, `apps:read` (filtered to allowed apps), `notifications:read`, `actions:request:access.request`.

### 4.3 Data model

Kanidm holds identity and credentials; the gateway database holds everything about OneMind behaviour. No password or TOTP secret is ever in the gateway database.

```
Kanidm                           gateway database (ledger migrations, one per epic)
──────                           ───────────────────────────────────────────────────
person {uuid, name,              person_profile {person_id = kanidm uuid, display_name, role,
  displayname, passkeys[],         state: active|disabled|deleted, created_at, disabled_at,
  totp?, password?,                guest_expires_at?, credential_revision, picker_visible}
  account_expire?}               session {id, person_id, kind: web|native|cli, client{platform,
group onemind_{owners,adults,      device_class, app_version}, created_at, last_seen_at,
  children,guests}                 expires_at, credential_revision, step_up_at?, revoked_at?}
group app_<id>_users,            app_access {app_id, mode: owner|adults|household|people,
  app_<id>_admins (OIDC apps)      people[], children_allowed: bool, app_roles{person_id: viewer|
oauth2 client per OIDC app         user|admin}, revision, updated_by, updated_at}
  (scope map → app_<id>_users)   child_policy {person_id, guardians[person_id], windows[{days,
                                   from, to, tz}], allowed_apps[], request_policy: ask|never,
                                   paused_until?}
                                 access_request {id, person_id, app_id, reason, action_id}
                                 tombstone {person_id, deleted_at, cleanup: {sessions, tokens,
                                   storage, app_accounts, mesh}, cleanup_complete}
```

Rules: `app_access.mode = household` covers owners and adults, never children or guests unless `children_allowed` or named. Every write bumps `revision` and publishes `access.changed`. Profile and preference data for the Home screen (wallpaper, widgets) belongs to the UI stream (PU-03) and is keyed by `person_id`.

### 4.4 Flows

**First boot (owner).** Console or setup page shows a QR; the owner's phone opens the setup page, registers a passkey in Kanidm, and the gateway shows a **recovery kit** once (one-time recovery code, printable). The v0 owner token becomes break-glass (SECURITY.md §3.2). Works with no internet.

**Invite.** Owner → People → Invite → name, role, apps (pre-ticked from `household` apps; for a child, nothing pre-ticked) → step-up passkey → a one-time **enrolment link and QR** valid 24 h. The invitee registers their own passkey (or, if their device cannot, a password with TOTP). The owner never sees a credential.

**Sign-in.** `https://onemind.local` → the gateway redirects to Kanidm (auth code + PKCE) → passkey → back with a gateway session. The account picker on the sign-in page is **off by default**; the owner can turn it on for a shared household tablet. Hybrid sign-in (scan a QR with your phone) covers TVs and guests' laptops.

**Open an app (forward-auth).**
```
browser → edge (photos.onemind.local) → GET /v1/auth/forward {host, method, path, cookie}
  gateway: session valid? credential_revision current? role → app_access → child window?
  204 + X-OneMind-Principal: person:<uuid>, X-OneMind-Role, X-OneMind-User, X-OneMind-App-Role
  401 → redirect to sign-in with next=   ·   403 → "no access" page with a Request access button
edge → app (client-sent X-OneMind-* stripped; app pods reachable only from the edge by NetworkPolicy)
```
For apps that speak OIDC, the manifest asks for an OIDC client; the gateway creates it in Kanidm at install with a scope map limited to `app_<id>_users`, writes the client secret to the app's Secret, and the app shows its own "Sign in with OneMind" which completes silently because the person already has a Kanidm session. For apps that read trusted headers, the manifest names the header mapping. Apps that do neither stay behind the gate with their own login (as umbrelOS does today), and the app page says so.

**Change access.** Owner on an app page → Access card → mode and people → saved as a direct owner write, audited; open connections that lose access are cut within one second through `access.changed`. An adult, a child or an agent who wants access creates an `access.grant` (or `access.request`) action that waits in Approvals.

**Child.** Guardian sets the allow-list and windows. Outside a window forward-auth returns 403 with the next allowed time; the child's Home shows the apps greyed with that time. "Ask for an app" creates an `access.request` action; v1 approval is owner-only (contract P1). Guardian approval limited to their own child's `access.request` is decision ACCT-D3.

**Guest.** Owner creates a guest with an expiry (default 7 days, maximum 90). At expiry Kanidm's account expiry and the gateway both refuse sign-in; sessions are revoked.

**Recover.** Lost phone: another device or the recovery code → revoke the lost device's sessions → new passkey. A person who lost everything: owner issues a new enrolment link (step-up), which also removes old credentials and bumps `credential_revision`. Lost owner with no second owner: recovery kit; without it, console break-glass on the box.

**Delete.** Disable (reversible, revokes sessions and tokens) → delete after the owner confirms with step-up, offering a data export first → tombstone and resumable cleanup (sessions, tokens, mesh devices, OIDC app accounts by unlinking, private storage).

### 4.5 Sessions and credentials

| Client | Credential | Lifetime |
|---|---|---|
| Dashboard | `HttpOnly; Secure; SameSite=Strict` cookie on `onemind.local` + `OneMind-CSRF` header (H-16) | 7 days idle, 30 days absolute |
| App hosts | separate edge cookie on `.onemind.local`, `SameSite=Lax`, never forwarded upstream | same session; checked by forward-auth |
| Phone app | OIDC refresh token in secure store; access token 10 minutes | refresh 90 days, revocable |
| CLI | `om_pat_` personal token (API.md §5.9) or device login flow | token expiry |
| Downloads | 60 s single-use ticket bound to session and path | 60 s |

Step-up: assertion within 5 minutes, recorded as `step_up_at` on the session (API.md §8.4). Sign-in throttling: 5 failures per person per 15 minutes, then exponential delay; per source address 20 per minute; every failure audited without the attempted secret.

### 4.6 API surface (contract style of API.md)

Kinds: R read, W direct owner write (audited), Q request (creates an action).

| Method and path | Kind | Scope | Who | Does |
|---|---|---|---|---|
| `GET /v1/me` | R | any | any | already in API.md §5.8; adds `role: child`, `guardians`, `allowed_apps` for children |
| `GET /v1/users` | R | `users:read` | owner | people with role, state, last seen, sign-in methods (kinds only), app count |
| `POST /v1/users` | W | `users:admin` | owner + step-up | `{display_name, role, apps?, guest_expires_at?}` → `201` with enrolment link (shown once) |
| `PATCH /v1/users/{id}` | W | `users:admin` | owner + step-up | role or display name |
| `POST /v1/users/{id}/enrolment-link` | W | `users:admin` | owner + step-up | new link; removes old credentials; bumps revision |
| `POST /v1/users/{id}/disable` · `/enable` | W | `users:admin` | owner | disable revokes sessions and tokens |
| `DELETE /v1/users/{id}` | W | `users:admin` | owner + step-up | must be disabled first; tombstone + cleanup; `409` for the last owner |
| `GET /v1/auth/sessions` | R | `sessions:self` | any person | own sessions; `?person=<id>` for owners |
| `DELETE /v1/auth/sessions/{id}` · `POST /v1/auth/sessions/revoke-others` | W | `sessions:self` | own; owner for anyone | revocation is immediate (bus event) |
| `GET /v1/apps/{id}/access` | R | `access:read` | owner; adult for apps they can open | mode, people, child flag, app roles |
| `PUT /v1/apps/{id}/access` | W | `access:admin` | owner (+ step-up when widening to `household` or adding a guest) | replaces the access row, `If-Match: <revision>` (API.md §7.4) |
| `POST /v1/actions` `access.grant` / `access.revoke` | Q | `actions:request` | adult, agent | owner approves; the card shows person, app and in-app role |
| `POST /v1/access-requests` | Q | `actions:request:access.request` | child, adult | creates `access.request`; rate-limited 5 per day for children |
| `GET` / `PUT /v1/users/{id}/child-policy` | R / W | `users:read` / `users:admin` | owner; guardian reads | windows, allow-list, pause |
| `GET /v1/auth/forward` | internal | loopback only, edge credential | edge | 204 / 401 / 403 as §4.4 |

Errors use API.md §6: `permission_denied`, `step_up_required` (in `details`), `conflict` (last owner, stale revision), `expired` (guest, enrolment link). Scopes `access:read`, `access:admin`, `sessions:self` are added to API.md §8.2 by the contract PR; `users:admin`, `access:admin` join the never-grantable list for agent, plugin, automation and node tokens.

**CLI** (`cmd/onemind/cli/{users,access,sessions}.go`):
```console
$ onemind users invite --name "Sam" --role child --apps photos,khan-academy
step-up: confirm with your passkey in the browser … ok
Enrolment link (24 h, shown once):  https://onemind.local/enrol/…   [QR printed below]
$ onemind access show photos
MODE        PEOPLE           CHILDREN  APP ROLES
household   +sam             yes       sam=viewer
$ onemind access set photos --mode people --add alex --role alex=user
$ onemind sessions list --person sam
ID        CLIENT              LAST SEEN     CURRENT
ses_91c2  iPad · OneMind app  2 min ago     no
$ onemind sessions revoke ses_91c2
```

**MCP** (DEV-MCP stream; tools generated from the same operations): `list_people` (names and roles only, needs `users:read` which only owner-owned agents can hold), `get_app_access`, and `request_action` with `access.grant` / `access.revoke`. No tool creates people, changes access directly, issues enrolment links or reads sessions of others. An agent owned by an adult can at most request what that adult could request.

### 4.7 Screens (dashboard, phone, design system)

| Screen | Content | Owner |
|---|---|---|
| Sign-in | Passkey button, "use a phone" hybrid, password + code fallback, optional account picker (owner setting) | security stream (`SignIn.tsx`) |
| First boot | Owner passkey, recovery kit with a "I saved it" check | security + dashboard |
| Settings → People | List: avatar, name, role pill, sign-in methods, last seen, state; Invite | dashboard (`Settings*.tsx`) |
| Person detail | Role, apps they can open (with in-app role), folders, devices and sessions with Revoke, recovery link, Disable, Delete; for children the policy card | dashboard |
| Invite sheet | Name, role, apps, guest expiry → QR and link once | dashboard |
| App page → Access card | Mode selector, people chips, children toggle, app roles; the API and CLI line under it (UX-B2) | dashboard (`AppDetail.tsx`) |
| Child Home | Only allowed apps; greyed outside windows with the next time; "Ask for an app" | dashboard + UI (`ui/**`) |
| Approvals card for access | "Sam asks for Minecraft server" with role and reason; approve with passkey | dashboard |
| My account | Passkeys (add, name, remove), sessions, personal tokens, fallback code | dashboard |
| Phone | Same sign-in through the system browser; approvals; child Home | mobile |

### 4.8 Security notes

| Threat | Control |
|---|---|
| Forged identity header to an app | Edge strips `X-OneMind-*` from clients; app pods accept traffic only from the edge (NetworkPolicy); test NT-15 |
| App steals the gateway cookie | Separate cookie for app hosts; edge never forwards either cookie upstream (umbrelOS does the same stripping) |
| Login race after credential change | `credential_revision` check at session creation |
| Brute force, code replay | Throttling §4.5; TOTP ±1 step and last-used counter (Kanidm behaviour to confirm in ACCT-1) |
| Owner lock-out | Second owner recommended at setup; recovery kit; console break-glass |
| Child bypass | Policy enforced at forward-auth and at the gateway API, not in the UI; windows evaluated in the box's time zone with a monotonic clock check |
| Agent escalation | Agent rights = owning person ∩ grant; `users:admin`, `access:admin`, `actions:approve` never grantable |
| Account enumeration | Picker off by default; sign-in errors do not say whether a name exists |
| Identity on backup and restore | Kanidm online backup inside the system backup (D-B7.4); sessions wiped on restore; passkeys survive only if the identity domain is unchanged (ACCT-D1) |

**Open decisions (to add to `docs/leap/DECISIONS-NEEDED.md` by its owner):**
- **ACCT-D1 · Identity domain.** A passkey is bound to one domain. `onemind.local` (LAN) and `*.onemind.internal` (mesh, NETWORKING.md §10) are different domains, so one passkey would not work on both. Options: (a) one canonical sign-in host reachable on LAN and mesh; (b) owner domain with split-horizon DNS when relay or direct mode is on; (c) register a passkey per domain. **UNVERIFIED:** whether phones resolve `.local` over unicast DNS on the mesh. Lab test ACCT-T1 decides. Kanidm's documentation warns that changing its domain invalidates passkeys, so this must be fixed before the first owner enrols.
- **ACCT-D2 · Kanidm placement:** host service (proposed, for sign-in with k3s down) vs the `kanidm` chart named in research 30.
- **ACCT-D3 · Guardian approval:** may an adult guardian approve their own child's `access.request`? Needs a contract change to P1 ("only an owner approves").

---

## 5. Epics

Sizes: S ≤ 2 days, M ≤ 1 week, L > 1 week. Paths follow [WORKSTREAMS.md](../leap/WORKSTREAMS.md): the security and identity stream owns `core/onemind_core/{passkeys,sessions,tokens,agents}.py` and `SignIn.tsx`; hotspots change only in their own small PRs; `forward_auth.py` belongs to CORE-NET-8 and this design adds its policy through `access.py`.

| ID | Title | Size | Owner paths | Depends on | Acceptance |
|---|---|---|---|---|---|
| ACCT-1 | Kanidm spike: host service, offline first boot, groups, OIDC client with group scope map, credential-reset link, account expiry, TOTP replay, backup and restore | M | `research-output/evidence/lab/acct-kanidm/**`; packaging later via image stream (`os/**`) and `deploy/**` owners | ACCT-D2 | Report with commands and outputs; owner passkey enrolled with the network cable out; restored box accepts the same passkey; reused TOTP code refused |
| ACCT-2 | Contract PR: role `child`, scopes `access:*` and `sessions:self`, action types `access.grant`, `access.revoke`, `access.request`, forward-auth headers, manifest `spec.auth` | S | `sdk/contracts/poc-v0.md`, `sdk/schema/onemind.app.schema.json` (hotspots, one PR) | BACKLOG S1 order | Contract and schema merged; schema tests pass with `spec.auth: {mode: oidc\|headers\|gate-only}` |
| ACCT-3 | Identity module: Kanidm client, sign-in (auth code + PKCE), sessions with `credential_revision`, throttling, bus events | L | `core/onemind_core/identity.py`, `sessions.py` (with CORE-SEC-2), one ledger migration | ACCT-1, ACCT-2, CORE-SEC-1, CORE-SEC-2 | Login after a concurrent credential reset fails; 6th failed login in 15 min delayed; revoked session's WebSocket closed within 1 s; k3s stopped → sign-in still works |
| ACCT-4 | People API: `/v1/users` with enrolment links, disable, tombstoned delete, last-owner rule | M | `core/onemind_core/users.py`, ledger migration | ACCT-3, CORE-SEC-10 | Owner never receives a credential; deleting the last owner → `409`; crash mid-delete resumes on restart; deleted id never reused |
| ACCT-5 | App access and forward-auth policy | M | `core/onemind_core/access.py`; one hook in `forward_auth.py` through CORE-NET-8 | ACCT-3, CORE-NET-8 | Guest on adults-only app → 403; client-sent `X-OneMind-Principal` stripped; access removed → open stream cut within 1 s; agent token on an app host → 401 |
| ACCT-6 | OIDC clients for apps at install, header mapping for header apps | M | `core/onemind_core/oidc_clients.py`; one hook in `executors.py` through the sandbox owner | ACCT-5, CORE-SANDBOX-2 | Two people sign into the same seed OIDC app and see separate libraries; removing the app deletes its Kanidm client; secret only in the app Secret |
| ACCT-7 | Child policy and access requests | M | `core/onemind_core/household.py`, ledger migration | ACCT-5, ACCT-2 | Child outside window → 403 with next time; child cannot reach any non-allowed app even by URL; 6th request in a day → 429; request appears in Approvals |
| ACCT-8 | CLI groups `users`, `access`, `sessions` | S | `cmd/onemind/cli/{users,access,sessions}.go`, one line in `root.go` | ACCT-4, ACCT-5, DEV-CLI-1 | Golden-output tests; step-up opens the browser; secrets printed once |
| ACCT-9 | MCP tools for people and access requests | S | `core/onemind_core/mcp/**` (MCP stream) | ACCT-5, DEV-MCP-2 | Agent owned by an adult cannot request beyond that adult; no tool returns sessions or credentials; MCP conformance passes |
| ACCT-10 | Dashboard: sign-in, first boot, People, person detail, Access card, child Home, My account | L | `dashboard/src/pages/SignIn.tsx` (security), `Settings*.tsx` and `AppDetail.tsx` (dashboard), components in `ui/**` | ACCT-4, ACCT-5, ACCT-7, PU-28 | Playwright: invite → enrol on a second browser profile with a virtual authenticator → app opens; child Home hides other apps; axe clean |
| ACCT-11 | Phone: OIDC sign-in in the system browser, refresh token in secure store, approvals with passkey, child Home | M | `mobile/**` | ACCT-3, ACCT-10 | Revoked phone session signs out on next refresh; token never in logs or plain storage |
| ACCT-12 | Identity in backups and restore | S | `core/onemind_core/backups.py` hook (CORE-BACKUP-8 owner), `internal/backup/**` | ACCT-1, CORE-BACKUP-8 | Restore into a clean box: people and passkeys work, all sessions invalid, audit shows the restore |
| ACCT-T1 | Lab test: passkey across LAN and mesh names, hybrid sign-in from a TV browser | S | `research-output/evidence/lab/acct-domain/**` | ACCT-1, CORE-NET-5 | Pre-registered result decides ACCT-D1 |
