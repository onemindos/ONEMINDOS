<!-- SPDX-License-Identifier: Apache-2.0 -->
# Dashboard redesign onto `ui/` (CORE-DASH)

**Date:** 2026-11-12 · **Status:** proposal · **Plan epics:** E2 (Audit page, kill switch), E3 (PWA, approvals over HTTPS) · **Deeper docs:** [`docs/DASHBOARD.md`](../../DASHBOARD.md) (design v0.1), `docs/design/PLUGIN-UI.md` (design stream, branch `feat/design-system`, in progress), research 12 §1 (REC-W11-01…20) · **Serves:** P-1, P-2, UX-1…UX-4; brief 30 B11; core-alignment UX-P1…P5, UX-B1…B3, PLG-P1, PLG-B1.

> **Explain it like I am the founder**
> The dashboard works but looks like a prototype: five screens and a handful of colours.
> The redesign moves it onto one shared design system (`ui/`: colours, type, dark mode and accessible components), so the web, the phone and future plugins look and behave the same.
> It adds the screens a daily-use box needs (Activity, Alerts, Updates, Backups, Agents, Settings) and keeps the house rules: never show stale data as live, show who asked (person or agent), and every button maps to an API call an agent could also request under the same rules.

## 1. Goals and non-goals

| Goals | Non-goals (now) |
|---|---|
| Consume `@onemind/ui` (tokens + components) from `ui/`; light and dark themes | A desktop-style window manager |
| New screens: Activity (audit), Alerts, Updates, Backups, Agents, Settings, App detail, Automations | Native desktop apps (Tauri, later) |
| Approval card with plan, requester kind, agent-written reason label, passkey step | XR views (REC-W11-14, year 2) |
| PWA over HTTPS (installable, Web Push) | Homarr/Homepage importers (later) |
| Role-gated detail (no global Pro toggle, REC-W11-05) | Custom sandboxed widgets beyond the typed templates (PLG-B1 phase 2) |
| WCAG 2.2 AA (axe-core in CI, 0 serious/critical) | |

## 2. What exists today

| Piece | Where | State |
|---|---|---|
| Screens: Home, Nodes, Market, Approvals, SignIn; freshness rules; WCAG tests | `dashboard/src/pages/`, `dashboard/src/ui.test.tsx` | `main` |
| 18 CSS custom properties, no dark mode | `dashboard/src/styles.css` | `main` |
| App page + trust card (links, licence, tier, scan date) | `dashboard/src/pages/AppDetail.tsx`, `components/AppTrust.tsx` | `feat/gateway-agent-mcp` |
| Design tokens (CSS + TS) | `ui/src/tokens/tokens.css`, `tokens.ts`; package `@onemind/ui` | `feat/design-system` (uncommitted, components not yet written) |
| Phone screens that mirror the dashboard | `mobile/src/screens/` | `feat/mobile-shell` |

## 3. Design

### 3.1 Package wiring
```jsonc
// dashboard/package.json (one line added)
"dependencies": { "@onemind/ui": "file:../ui" }
```
```tsx
import "@onemind/ui/ui.css";
import { Card, StatusPill, Button, Dialog } from "@onemind/ui";

<Card title="uptime-kuma">
  <StatusPill status={fresh ? "online" : "stale"} since={lastSeen} />
  <Button onClick={requestInstall}>Ask to install</Button>
</Card>
```
`ui/` owns tokens and generic components; `dashboard/` owns screens and data. The phone app reads `@onemind/ui/tokens.json` so colours match (MOBILE).

### 3.2 Screens

| Screen | Content | API |
|---|---|---|
| Home | instance, node counts by status, installed apps (open via gateway proxy), pending approvals, alerts, widgets (typed: stat, list, progress) | `/v1/instance`, `/v1/nodes`, `/v1/apps`, `/v1/actions`, `/v1/alerts` |
| Approvals | plan card: objects by kind, images with digests, ports, volumes, egress, scan, requester (person/agent), expiry; agent reason in a "written by agent" block; passkey approve | `/v1/actions/{id}`, `approve-options`, `approve` |
| Activity | timeline from the audit chain, filter by node/app/agent, "chain verified" mark | `/v1/audit?after=<seq>` (new), `/v1/audit/verify` |
| Alerts | inbox, ack, resolve, fix | `/v1/alerts` |
| Market + App detail | catalog, trust card, per-node fit verdict, update available, logs, restart | `/v1/apps`, `/v1/apps/{id}/plan` |
| Nodes | cards, add node (QR + code), remove, fleet view | `/v1/nodes`, `/v1/fabric/*` |
| Updates | booted slot, available release + CVEs fixed, window, postpone, history | `/v1/os/status` |
| Backups | last backup, last verified restore (badge), destinations, emergency kit status, restore | `/v1/backups` |
| Agents | agent principals, scopes, recent requests, approval rate, suspend | `/v1/tokens`, `/v1/agents` |
| Automations | automations, standing approvals with limits and expiry, dry run | `/v1/automations`, `/v1/policies` |
| Settings | sessions, passkeys, tokens, TLS pairing QR, notification routes, remote access, export | `/v1/auth/*`, `/v1/notify/routes` |

### 3.3 "Show the equivalent call" (UX-B2)
Every action button has a small "API" toggle that shows the same request in curl, CLI, Python, TypeScript, Go and MCP:
```text
CLI     onemind app install ntfy
curl    curl -X POST https://onemind.local:8443/v1/actions -H "Authorization: Bearer $ONEMIND_TOKEN" \
          -d '{"type":"app.install","params":{"app_id":"ntfy"},"idempotency_key":"…","expires_at":"…"}'
Python  client.actions.request("app.install", app_id="ntfy")
TS      await om.actions.request({ type: "app.install", params: { app_id: "ntfy" } })
Go      om.Actions.Request(ctx, onemind.Action{Type: "app.install", Params: map[string]any{"app_id": "ntfy"}})
MCP     tools/call request_action {"type": "app.install", "app_id": "ntfy"}
```

### 3.4 House rules (kept from v0, extended)
- Freshness: age computed on the hub's clock; stale values are labelled "not live" with their time (also for backups, updates, scans; UX-B3).
- Requester kind on every action; approve buttons hidden for non-owners (using `/v1/me`) but the gateway still enforces.
- Status reducer hides Kubernetes words from household roles (REC-W11-05).
- App UIs open on per-app subdomains behind the gateway's sign-in (H-29, REC-W11-03), never `http://host:port`.

## 4. Security model
- CSP `default-src 'self'` and headers from the gateway (H-18); no inline scripts; no third-party fonts or analytics.
- Web session: `HttpOnly; Secure; SameSite=Strict` cookie + CSRF header (H-16); the token no longer lives in `sessionStorage`.
- Widgets (E5): typed templates fed by a gateway proxy now; custom widgets later in iframes on their own origin with CSP from declared domains (research 29 §8.1).
- The plan card renders agent text as plain text, never HTML or Markdown links.

## 5. Versioning and compatibility
- `@onemind/ui` uses semver; the dashboard pins an exact version once `ui/` is published; until then `file:../ui`.
- Mock mode (`VITE_MOCK=1`) fixtures follow the contract and are shared with the phone through `sdk/ts` (planned) instead of copies.
- New routes appear behind feature checks (`GET /openapi.json` lists them), so a newer dashboard degrades gracefully on an older gateway.

## 6. Test plan and acceptance

| Test | Pass when |
|---|---|
| axe-core | 0 serious or critical issues on every screen, light and dark |
| Freshness | Fixtures with stale and offline nodes never render a live badge |
| Plan card | Changing the plan between load and approve shows a refresh prompt; agent reason is in the labelled block |
| PWA | Installs on Android Chrome over HTTPS with the box CA; Web Push received |
| Phone width | Every screen usable at 375 px without horizontal scroll |
| Equivalent call | Each shown CLI/API call, run as-is against the mock gateway, creates the same action |

## 7. Build steps

| Epic | Step | Effort | Depends on |
|---|---|---|---|
| CORE-DASH-1 | `ui/` components v0 (card, list, table, dialog, toast, status pill, progress, icon set) + dark mode | M | `feat/design-system` |
| CORE-DASH-2 | Move the 5 existing screens onto `@onemind/ui` | S | 1 |
| CORE-DASH-3 | Approvals plan card + passkey approve | M | SANDBOX-2, SEC-2 |
| CORE-DASH-4 | Activity (audit) + Agents (suspend) | S | SEC-6 |
| CORE-DASH-5 | Alerts, Updates, Backups screens | M | NOTIFY-1, UPDATE-2, BACKUP-8 |
| CORE-DASH-6 | Settings (sessions, tokens, pairing, routes) + Automations | M | SEC-2, SEC-3, AUTO-4 |
| CORE-DASH-7 | PWA + per-app subdomain launcher | M | SEC-1, H-29 |
| CORE-DASH-8 | Typed widgets on Home (PLG-P1); "equivalent call" toggle | M | 1 |

## 8. Who owns which files

| Branch | Files |
|---|---|
| `feat/design-system` (exists) | `ui/**` only |
| `feat/dashboard-redesign` (proposed) | `dashboard/src/pages/*`, `dashboard/src/components/*`, `dashboard/package.json` |
| Feature branches | each adds **one** page file (`Backups.tsx`, `Alerts.tsx`, …) and one route line |
| Hotspots (serialized) | `dashboard/src/App.tsx` (route table), `dashboard/src/api/types.ts` (until `sdk/ts` replaces it) |
