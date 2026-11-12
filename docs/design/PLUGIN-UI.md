# Plugin UI: extension points, phase 1

**Serves:** backlog item 24 (PLG-P1, PLG-P2, PLG-B1, later PLG-B2/B3) in `docs/strategy/core-alignment.md`; socket **E5** "UI slot" in [`research-output/29-PLATFORM-ECOSYSTEM-MARKETPLACE.md`](../../research-output/29-PLATFORM-ECOSYSTEM-MARKETPLACE.md) and brief 30 (E5 = v1-beta: "separate origin per widget, CSP from declared domains, no inherited credentials"); one manifest schema (BD-14).
**Status:** design. Nothing here is in `sdk/schema/onemind.app.schema.json` yet. The manifest fields below are a **proposal** for a contract amendment PR, which all streams adopt (contract preamble).

**Plain English:** an *extension point* is a place in the dashboard where an app may add its own piece of UI, such as a tile on Home or a settings panel. Phase 1 gives apps three such places, with strict limits, so that a badly written or malicious app cannot read your other apps, act without approval, or make the dashboard slow.

## 1. Phase 1 extension points
| # | Point | Where it shows | Rendered by | v0 |
|---|---|---|---|---|
| X1 | **App tile** | Home app grid, Apps list, phone Home | Host, from manifest metadata (name, icon, status, open URL) | already implied by §4 |
| X2 | **Typed widget** | Home "Widgets from your apps", phone Home | **Host**, from a JSON payload the app serves | first |
| X3 | **Custom widget** | Home, app page | **Sandboxed iframe** on the app's own origin | after SEC-P2 (per-app subdomains) |
| X4 | **App settings panel** | App page → Settings | Host form from JSON Schema; iframe only if the schema cannot express it | first (schema form) |
| X5 | **Notification actions** | Alerts, push notifications, phone lock screen | Host; each action creates a request | with NOT-P1 |

Phase 2 (not now): desktop windows and docks (umbrelOS/Olares desktop pattern), Omarchy shell plugins (bar widget, panel; Omarchy `shell/services/PluginRegistry.qml`, MIT), app-contributed pages, theme packs.

## 2. Typed widgets (X2): data only, host renders
Pattern: umbrelOS widgets (apps fill typed templates; small per-person limit) (`packages/umbreld/source/modules/widgets/routes.ts`, PolyForm NC, **study only**). OneMind's own templates:

| Template | Payload |
|---|---|
| `stat` | `{value, unit?, label, tone?, updated_at}` |
| `stats` | up to 4 × `{value, label}` + `updated_at` |
| `list` | up to 5 × `{text, detail?, at?}` + `updated_at` |
| `progress` | `{label, value, max, text}` + `updated_at` |
| `status` | `{tone, label, detail?}` + `updated_at` |

- The gateway fetches the payload from the app's in-cluster service (path declared in the manifest), validates it against the template schema, and serves it to the dashboard. The browser never talks to the app directly, and the app never gets the person's token.
- `updated_at` is required. The host applies the freshness rule (P2): a widget older than `2 × refresh` is shown stale.
- Why first: no app code runs in the dashboard, it renders identically on web and in the native phone app, and it inherits the design system for free.

## 3. Settings panel (X4)
- Default: the app declares a **JSON Schema** for its settings (with titles, descriptions, enums, `format: secret` for credentials). The host renders the form with design-system inputs. Saving creates an `app.configure` **request** with the diff; secrets are written to the app's Secret by the gateway, never shown again (gap list: owner-entered secrets).
- Escape hatch: an iframe panel (same rules as X3) for settings a schema cannot express.
- Pattern: umbrelOS splits app settings into credentials, environment, storage and advanced (`app-page/app-settings-*.tsx`, study only); StartOS drives service config from a spec (`routes/services/routes/actions.component.ts`, MIT).

## 4. Notification actions (X5)
An app may declare actions that appear on its alerts, for example "Restart the backup job". Each maps to a **declared capability** (E6) and pressing it creates a request through the normal approval flow, unless an owner policy auto-approves it (backlog AUT-B1). Phone notifications show at most two actions; Approve/Deny on a pending request is the host's own action (NOT-B3).

## 5. Manifest declaration (PROPOSED)
```yaml
apiVersion: onemind.app/v1alpha1
kind: App
metadata: { id: uptime-kuma, name: Uptime Kuma, ... }
spec:
  web: { port: 3001 }
  ui:
    widgets:
      - id: monitors
        title: Monitors
        template: stats                 # stat | stats | list | progress | status
        source: { path: /api/onemind/widgets/monitors, refreshSeconds: 30 }
      - id: status-page
        title: Status page
        kind: iframe                    # X3, custom widget
        entry: /onemind/widget.html     # served by the app on its own origin
        size: { cols: 2, rows: 2 }
        connectDomains: []              # CSP connect-src beyond the app's origin; empty = none
        grants: [theme, resize]         # host messages the widget may use
    settings:
      schema: settings.schema.json      # X4; JSON Schema shipped in the app folder
    notificationActions:
      - id: pause-checks
        label: Pause checks for 1 hour
        capability: uptime-kuma.monitors.pause   # E6 capability with effect: write
```
Validation (PLG-P2): one Go package used by `onemind plugin validate`, the Market CI gate (§9.4) and the box, as Omarchy's validator refuses what its shell would refuse (`bin/omarchy-plugin-validate`, MIT). Rules: ids unique; templates known; `source.path` relative; iframe `entry` on the app origin; `connectDomains` are full hostnames, no wildcards; at most 4 widgets per app; refresh ≥ 10 s.

## 6. Decision: sandboxed iframe, not module federation
For code that an app supplies (X3, and the X4 escape hatch), OneMind uses **sandboxed iframes on a separate origin**. Module federation is rejected for third-party code.

| | Sandboxed iframe (chosen) | Module federation / remote JS modules |
|---|---|---|
| Isolation | Browser-enforced: the frame is served from the app's own subdomain, never the dashboard's origin, so it cannot read the dashboard's DOM, storage or cookies; `sandbox="allow-scripts allow-forms allow-same-origin"` (same-origin here means *the app's* origin, which lets it reach its own backend; without per-app subdomains `allow-same-origin` must be dropped); no `allow-top-navigation` or `allow-popups-to-escape-sandbox`; CSP `frame-ancestors` and `connect-src` from the manifest | **None**: remote code runs in the dashboard's JS realm with the person's session and can call any API, read any page, change any button |
| Approval-first (P1) | The widget can only `postMessage` a *request*; the host turns it into an action awaiting approval | A plugin could call approve itself with the owner's token |
| Credentials | None inherited; the widget talks to its own app backend only | Inherits everything |
| Look and feel | Host sends tokens (`theme` grant) so the widget can match; may still feel slightly foreign | Native |
| Performance | One extra document per widget; cap widget count | Cheapest |
| Versioning | Independent: any framework, any version | Shared React/runtime versions must match; one plugin can break the host |
| Phone app | Works in a WebView; typed widgets render natively instead | Web only |
| Standard | MCP Apps `ui://` resources use the same model (spec 2026-01-26; research 29 [C-W19-035]), so one widget can serve the dashboard, the phone and agents (PLG-B2) | No cross-surface standard |

**Trade-off accepted:** iframes cost a little performance and visual fit. Typed widgets (X2) cover most needs natively, so iframes are the minority. Module federation remains acceptable only for **OneMind's own first-party modules** inside the dashboard build (D-003 "one app shell hosting modules"), because that code is reviewed and signed with the dashboard.

**Host ↔ widget messages (v0, minimal):** host → widget `{type: 'theme', tokens}` and `{type: 'size', w, h}`; widget → host `{type: 'resize', h}`, `{type: 'open', path}` (navigate within its own app page), `{type: 'request', capability, params, reason}` (becomes an action awaiting approval; the widget is told the action id, never the result of a decision it could fake). Every message is checked against the widget's `grants`; unknown messages are dropped and logged.

## 7. Safety summary
- Plugins ship only through the scan-gated Market (§9.4) with pinned digests (PLG-B3), or as the owner's own deployment.
- No plugin UI code runs in the dashboard's origin. No plugin receives the person's token.
- Every action a plugin offers is a request.
- A widget that fails, is slow or is stale shows a fallback; it never blocks Home.
