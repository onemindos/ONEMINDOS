# OneMind dashboard (v0)

The web screen you open to see and control your OneMind: which machines have joined, which apps
are installed, and which changes are waiting for your approval. It is a React + TypeScript
single-page app built with Vite. The hub's gateway (`core/`) serves the built files from
`dashboard/dist` at `/` (contract §3 "Static").

**Build step:** brief 30 **B11 · Dashboard MVP** (REC-B30-12, REC-W11-01), implemented against the
binding contract [`sdk/contracts/poc-v0.md`](../sdk/contracts/poc-v0.md) §5 (screens), §3 (API),
§2 (heartbeat) and §4 (app fields). Language choice follows BD-02 (TypeScript + React for the UI).

## Why it is built this way (plain English)

- **A single-page app (SPA)** is one HTML file plus JavaScript. The browser downloads it once, and
  after that only small JSON requests travel to the hub. The gateway can serve it as plain static
  files, so the dashboard has no server of its own to keep running or patch.
- **It only talks to the §3 API.** Every button here is a normal API call that an AI agent could make
  under the same rules (REC-W11-20). The dashboard has no secret powers of its own.
- **AI never actuates without human approval.** Market "Install" does not install anything. It
  creates an *action* (a request) with a fresh random **idempotency key** (a UUID: if the same
  request is sent twice, for example after a network hiccup, the hub sees the same key and does
  not create a second action). Then it takes you to Approvals, where only the owner can approve.
- **Stale data is never shown as live.** A machine sends a heartbeat every 10 s. The hub marks it
  *stale* after 30 s and *offline* after 120 s without one. The dashboard also re-checks the age
  itself every second, because the hub's last answer gets older while the tab is open. Stale and
  offline cards say "values below are the last report, not live", have a dashed border, and show
  "last seen N ago".
- **Accessibility (WCAG 2.2 AA) from the first screen:** status is always written in words, not just
  colour; every button has a name a screen reader can read; there is a "skip to content" link; tap
  targets are at least 44 px; and the layout works on a 375 px phone, because phones are clients.

## How to run

Needs Node.js 20.19+ (tested with Node 26.5.1, npm 12.0.2 on macOS arm64).

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

npm test                    # vitest + Testing Library + axe-core
npm run lint                # eslint, 0 warnings allowed
npm run typecheck           # tsc --noEmit
```

`VITE_MOCK=1` is read at **build** time, so a mock build and a real build are different bundles.

## Layout

| Path | What |
|---|---|
| `src/api/types.ts` | Types for contract §2 heartbeat, §3 routes/actions/errors, §4 app fields |
| `src/api/client.ts` | `OneMindApi` interface (one method per §3 route) and `HttpApi` (bearer token, §3 error bodies → `ApiError`) |
| `src/api/mock.ts`, `fixtures.ts` | Mock gateway for `VITE_MOCK=1`: hub x86, Raspberry Pi 5, Jetson Orin (stale), DigitalOcean droplet (offline); Uptime Kuma, Jellyfin, Ollama; one pending agent request |
| `src/session.tsx` | Token sign-in, kept in `sessionStorage` (cleared when the tab closes) |
| `src/lib/time.ts` | Freshness rules (30 s / 120 s) and "N ago" text |
| `src/pages/*` | Sign-in, Home, Nodes, Market, Approvals |
| `src/ui.test.tsx`, `src/api/api.test.ts`, `src/lib/time.test.ts` | Tests |

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

## Known gaps

- **No "who am I" route in contract v0.** The UI learns a real principal's role only from a 403.
  Suggested contract change (separate PR, not made here): `GET /v1/me` → `{id, kind, role}`.
- **The action response shape is not fully specified** in §3. The UI expects `requested_by
  {id, kind, role}`, `created_at` and `decided_by`, and shows "Unknown requester" if they are
  missing. The gateway stream should return these, or the contract should name them.
- **App icons:** v0 draws an original monogram tile per app because no §3 route serves the
  manifest's `icon` file yet.
- **Open app links** use `http://<dashboard host>:<web_port>/`; that depends on how apps are exposed
  on k3s (ingress vs NodePort), which the contract does not fix yet.
- The mock fixtures and demo tokens are bundled in the real build too (unused unless
  `VITE_MOCK=1`); they could be split out with a dynamic import.
- Screens from the brief beyond the contract's four (Updates, Backups, Alerts, Agents, Robots,
  Settings, rescue console) are not in this PR.
- Colour contrast cannot be measured in jsdom, so unit tests switch off axe's `color-contrast` rule.
  It was checked by running axe-core 4.14.0 in a real browser against `npm run preview` (mock
  build) on all four screens, at the pane's width and at 375 px: 0 violations of any impact. That
  check is manual today; a Playwright job in CI would make it automatic.
- React prints some "not wrapped in act(...)" warnings in tests from the 1 s clock and the 10 s
  polling; they do not affect results.

## Design

Original look in the spirit of a calm home-server dashboard: a soft gradient "wallpaper", light
glass cards, an app grid with icon tiles and node cards. No assets or code were copied from
umbrelOS (PolyForm Noncommercial) or any other product.
