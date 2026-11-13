<!-- SPDX-License-Identifier: Apache-2.0 -->
# Dashboard wiring pass (HANDOFF B5, CORE-DASH-5/-7/-9)

**Why this exists, in plain words.** The dashboard v2 (#73) looked right but still asked for a
static token and showed "coming" for things the hub can already do. This pass connects every screen
to an API that is really on `main`, and says "Coming soon" (with the work item that brings it) for
the rest. Nothing is faked: a placeholder never shows sample data or a control that does nothing.

## What is wired (all in `sdk/openapi/onemind-v1.json` on main)

| Screen | Where | Routes |
|---|---|---|
| Sign in: passkey, account (+ authenticator code), access token | signed-out screen | `POST /v1/auth/login/options`, `/v1/auth/login`, `/v1/instance` |
| First-run setup (owner) then the wizard | signed-out "First time on this box?" | `POST /v1/auth/setup`; wizard = `@onemind/ui` `Onboarding`; passkey step = `/v1/auth/passkeys/register*` |
| Join with an invite code | signed-out "Have an invite code?" (also `#enrol=CODE`) | `POST /v1/auth/enrol` |
| Account and security | Settings > Account | `GET /v1/me`, `/v1/auth/passkeys`, `/v1/auth/sessions`, `DELETE` of both, `POST /v1/auth/logout` |
| People (owner) | Settings > Users | `GET/POST /v1/users`, `PATCH /v1/users/{id}`, `POST …/disable` |
| API tokens and agents | Settings > Agents | `GET/POST /v1/tokens`, `POST …/rotate`, `DELETE` |
| Notifications inbox and channels | Settings > Notifications | `GET /v1/notifications`, `POST …/read`, `…/read-all`, `GET/POST/DELETE /v1/notifications/channels`, `POST …/test` |
| Alerts and monitoring | Alerts (nav) | `GET /v1/monitoring/summary`, `GET /v1/alerts`, `POST …/ack`, `…/resolve`, `…/fix` |
| Activity | Activity (nav) | `GET /v1/audit/events`, `GET /v1/audit/verify` (owner); others fall back to the requests list and say so |
| Nodes, apps, approvals | existing | `/v1/nodes`, `/v1/apps`, `/v1/actions*` |

## Coming soon (no API on main; labelled, no data, no controls)

Automation, Files, Secrets, Photos, app lifecycle (start/stop/update/delete data), Network/QR/Add a
device, **Storage and disk health, Backups, OS updates**. The last three have daemons in `internal/`
but the gateway does not expose them yet (no `/v1/storage`, `/v1/backups`, `/v1/os`), so their
Settings sections are placeholders too. The list lives in `dashboard/src/pages/Coming.tsx`.

## Safety rules this pass keeps

- **AI never actuates.** "Ask to fix" calls `POST /v1/alerts/{id}/fix` with `approve: false` only
  (`api.askToFix` has no way to send `true`): the fix becomes a request in Approvals and waits for a
  person. Install and remove were already requests. Account, people, token and channel screens are
  the signed-in person's own acts; the gateway enforces owner-only, passkey step-up and the
  last-owner guard, and an agent token cannot reach them.
- **Tokens stay out of `localStorage`.** A sign-in gives a bearer access token (client `app`, one hour)
  held in `sessionStorage` only, as before. A token the hub shows once (API token, invite code) lives
  in component state until the dialog closes.
- **No `innerHTML`.** Everything from the hub (alert text, notification text, audit data) is rendered
  as React text.
- **Service worker** (`public/sw.js`) caches static files and the page shell only. It never handles
  `/v1/*`, `/healthz`, `/mcp`, requests with an `Authorization` header, other origins or non-GET.
  It registers only in a production build, not in the demo. `pwa.test.ts` checks these rules.
- **Step-up.** If the hub answers `step_up_required`, the toast says to sign in again with a passkey.

## i18n scaffold

`dashboard/src/i18n/en.ts` holds the English strings of the screens added here under stable keys;
`t('key', {vars})` looks them up. A test fails if code uses a missing key or a key is dead. No
translations ship. Older screens move over one at a time.

## Not done here, on purpose

- The wizard's box name, time zone and backup choice have no gateway route, so they are not saved
  (starter apps become real install requests; the passkey is real).
- Access token refresh: an account sign-in lasts one hour, then you sign in again (no refresh token
  is kept in the browser).
- PWA manifest is generated from `brand/brand.json` by `scripts/brand-sync.py`; icons are the brand marks.
- No per-app proxy URLs (the proxy is not mounted on main).
- Visual baselines: screens changed, so ui-quality baselines must be regenerated after #42 merges.

## Also in this PR: contract §12.21 names in `ui/`

Draft route names in `ui/src/settings`, `ui/src/shell` and `ui/src/home` hints now use the binding
names (`/v1/users`, `/v1/notifications/channels`, `/v1/notifications/preferences`,
`/v1/automation/rules`, `/v1/tokens`, `/v1/os/status`, `/v1/fabric`, `/v1/fabric/join-tickets/{ticket_id}`,
`/v1/actions/{id}/preview`). Appearance paths (`/v1/me/preferences`) have no contract name yet and stay marked pending.
