<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind dashboard (v2)

The web screen you open to see and control your OneMind: a Home launcher, the Market, your
installed apps, the Approvals queue, Activity, Nodes and Settings. It is a React + TypeScript
single-page app built with Vite, drawn entirely with the design system **`@onemind/ui`** (`ui/` in
this repo: shell, home, store, settings, customize). The hub's gateway (`core/`) serves the built
files from `dashboard/dist` at `/` (contract §3 "Static").

**Build steps:** brief 30 **B11 · Dashboard MVP** (v0, PR #8), then **CORE-DASH-2** (move the
screens onto `@onemind/ui`, `docs/leap/core/DASHBOARD.md` §7) with parts of CORE-DASH-1/4/8, against
the binding contract [`sdk/contracts/poc-v0.md`](../sdk/contracts/poc-v0.md) §2, §3, §5, §11.4.
Fixes design CRITIQUE #19–#26 (`docs/design/CRITIQUE.md`).

## What changed in v2 (plain English)

- **One design system.** Every screen is a `@onemind/ui` component; the dashboard only fetches data,
  maps it (`src/data/adapters.ts`) and handles clicks. Light and dark themes, accent, wallpaper and
  density come from Settings → Appearance and are saved **per person** in this browser.
- **One poll of the hub** (`src/data/hub.tsx`) feeds every screen, the bell, the palette and the
  jobs tray, so they always agree. While a request is moving, it is polled every 2 s
  (`GET /v1/actions/{id}`), which is the live install progress.
- **Honest about what the hub cannot do yet.** Widgets and settings whose API is not on `main`
  (backups, updates, mesh, people, tokens, notification routes, logs, restart/stop/update) say which
  work stream brings them and send nothing. Activity says it is built from actions, not the
  hash-chained audit log. Nothing is invented to fill a card.
- **`@onemind/ui` is compiled from source** (`../ui/src`, a Vite and TypeScript alias), so there is
  no separate ui build or publish step yet; React is resolved once, from `dashboard/node_modules`.
  `deploy/install.sh` copies `ui/src` next to the dashboard for the on-box build.

## How to run

Needs Node.js 20.19+ (v2 tested with Node 26.13.0, npm 11.20.0 on macOS arm64).

```sh
cd dashboard
npm ci

# Demo with made-up data, no hub needed:
npm run dev:mock            # http://localhost:5173, sign in with owner-demo / agent-demo / adult-demo

# Against a real gateway on :8080 (dev server proxies /v1 and /healthz to it):
npm run dev

# What the gateway serves:
npm run build               # → dashboard/dist
npm run build:mock && npm run preview   # the built demo on http://localhost:4173

npm test                    # vitest + Testing Library + axe-core (no ui install needed)
npm run lint                # eslint, 0 warnings allowed
npm run typecheck           # tsc --noEmit
```

`VITE_MOCK=1` is read at **build** time, so a mock build and a real build are different bundles.

## Layout

| Path | What |
|---|---|
| `src/api/` | Contract types, `HttpApi` (bearer token, §3 errors → `ApiError`, hub clock from `Date`), `MockApi` + fixtures for `VITE_MOCK=1` (10 apps incl. legacy category slugs; the noop executor steps every 1.5 s in the demo) |
| `src/data/adapters.ts` | Pure mappings: catalog → Market/Home/Installed, actions → approvals, progress, notifications, activity; TAXONOMY legacy slugs |
| `src/data/hub.tsx` | Shared poll of `/v1/instance`, `/v1/nodes`, `/v1/apps`, `/v1/actions`; `request` (idempotency key per app until a definite answer) and `decide` |
| `src/data/prefs.ts` | Per-person localStorage (appearance, Home layout, read notifications, recent commands); switches to the hub store once `/v1/instance` lists the `me.preferences` feature (§12) |
| `src/shell/` | `AppShell`, ⌘K palette, notification bell (fed by actions until the notifications API), jobs tray; ui hash links → routes |
| `src/pages/` | Home, Market (+ app page), Installed (+ manage), Approvals, Activity, Nodes, Settings, Sign-in |
| `src/*.test.ts(x)` | vitest: adapters, routes, API client, mock rules, every screen with axe (58 tests) |

Routes: `/`, `/market`, `/market/<app>`, `/installed`, `/installed/<app>`, `/approvals?highlight=<id>`,
`/activity`, `/nodes`, `/settings/<section>`.

## Roles in the UI

- **owner**: can request installs and approve or deny.
- **agent**: can request, but approve/deny buttons are disabled (the gateway also returns 403).
- **adult / guest**: can look; request and approve buttons are disabled.

Against a real gateway the UI cannot know your role in advance (see gaps). It leaves the buttons
on, the gateway enforces owner-only, and after a `403 permission_denied` the buttons switch off.
The gateway is the security boundary; the UI only avoids offering what will be refused.

## v0 shortcuts (from the contract, listed as required)

- **Auth is a static bearer token** typed into a sign-in field (contract "Deliberate v0 shortcuts").
  Owner passkeys, the recovery-kit step and Kanidm (BD-03) come later.
- **Mock mode** uses fixtures that match §2–§4; it runs the `noop` executor path instantly.
- Nodes publish straight to the hub's NATS (no leaf nodes), so the dashboard just reads `/v1/nodes`.

## Known gaps (each waits on a stream or a contract route)

- **No "who am I" route.** Against a real gateway the UI learns the role only from a 403 (§12 adds `GET /v1/me`).
- **No plan preview or passkey** on approvals: the card says so (§12.3 CORE-SEC-2, §12.4 CORE-SANDBOX).
- **Removal and data.** The v0 executor deletes the app's namespace on `app.remove`; data survives
  only where the storage class retains released volumes. The UI says this. Guaranteed keep-data
  removal (`delete_data: false`) is §12.5 and needs the gateway stream.
- **Install progress** is the action state only (approved → applying → done); the executor reports
  no steps or health in v0. "Installed" is shown, never "Running".
- **No placement plan:** the install review skips the node step and says the hub picks the node.
- **Open** uses `http(s)://<this host>:<web_port>/`; per-app addresses behind the gateway login are §12 / SEC-P2.
- **Notifications** are derived from actions and offline nodes; read state is per browser.
- **Bundle size** is ~530 kB (168 kB gzip) in one chunk; route-level code splitting is a follow-up.
- Colour contrast is not measurable in jsdom (axe's `color-contrast` is off in unit tests); the ui
  package tests token contrast in both themes.

## Design

Original look built on `@onemind/ui`. No assets or code were copied from umbrelOS (PolyForm
Noncommercial) or any other product.
