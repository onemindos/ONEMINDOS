<!-- SPDX-License-Identifier: Apache-2.0 -->
# Settings, Activity and Approvals (`ui/src/settings/`)

**Serves:** parity audit `docs/strategy/umbrel-parity.md` §3.8 (Settings), PU-18 (sessions and tokens), PU-19 (diagnostics), PU-27/PU-29 (nodes, agents), PD-04 (plan feeding the approval card); `docs/leap/core/DASHBOARD.md` §3.2 (Approvals plan card, Activity "chain verified", Settings, Agents); `docs/leap/core/SECURITY.md` §3.2–3.7; IA §2.4, §2.5, §2.10, §2.12. Categories and deployment classes come from `docs/design/TAXONOMY.md` (§1, §2, §3.2).
**Demo:** `#/system/<section>`, `#/system/activity`, `#/system/approvals` in `ui/demo` (fixtures only; `?state=loading|error|stale|empty` or the demo chips show each state). **Screens:** `docs/design/screens/settings/`.

## What is here

| File | What |
|---|---|
| `types.ts` | Data shapes, one per gateway response. Contract §3 shapes (principals, actions, errors, audit) plus the PROPOSED endpoints named in the leap docs. `Loadable<T>` is how every panel receives data |
| `taxonomy.ts` | The 16 category labels, 5 deployment classes and 3 node roles of TAXONOMY.md (internal, not exported, so it cannot collide with other areas) |
| `logic.ts` | Pure rules: restore badge, chain badge, token state, quiet hours, effects grouping and plan risk, audit filter and day grouping, usage by category, grouping by deployment class |
| `primitives.tsx` | `Async` (loading skeleton, error with code and Retry, stale "last known" with age, empty), `Group`, `Row(s)`, `Switch`, `CallHint`, `QrCode`, `SetIcon` |
| `SettingsLayout.tsx` | Grouped section list with search; desktop two panes, phone drill-in with "All settings" |
| `Sections*.tsx` | The 11 sections: Account & security, Users & roles, Agents & MCP, Devices & nodes, Network & mesh, Storage, Backups, Updates, Notifications, Automation, About & diagnostics |
| `AuditTimeline.tsx` | Activity: chain verified / broken / old-check banner, actor filter, search, day groups |
| `ApprovalsBoard.tsx` | Approvals: queue with requester filter, the selected request's `ApprovalCard` with the gateway-computed `EffectsCard` |

## Rules the code follows
- **Requests, not changes (P1).** Every control calls `onIntent({type, params, mode, title, call})`. `mode: 'request'` adds power and waits in Approvals; `mode: 'instant'` only takes power away (sign out, revoke, suspend, pause), as SECURITY §3.4 says. `call` is the CLI or API line, and each section ends with "Same thing from a terminal or the API" (P4).
- **Honest state (P2).** Stale data is drawn dashed with "Last known · N min ago", and every control is disabled while stale. Switches show the hub's value, never an optimistic one.
- **The UI renders the plan; it never decides it.** `EffectsCard` shows what `GET /v1/actions/{id}/preview` returns (effects, placement, scan, undo, plan hash). If the gateway cannot compute the plan, the card says so.
- **Categories and deployment classes** label app updates (grouped by class, most vouched-for first), storage use (by category), approvals (category, class, Plugin pill) and About (Core components). Node roles use the TAXONOMY §3.2 wording.

## Local tokens (in `settings.css`, derived from global tokens only)

| Token | Value | Use |
|---|---|---|
| `--om-set-nav-width` | 272 px | settings section list on desktop |
| `--om-set-icon-box` | 34 px | row icon tile |
| `--om-set-skel-base`, `--om-set-skel-shine` | `surface-sunken`, a mix of `border-strong` and `surface-sunken` | loading skeleton shimmer (stops under reduced motion) |
| `--om-set-shift` | 6 px | enter motion distance for a section and the approval detail (off under reduced motion) |
| `--om-set-stack-0…4` | `accent` mixed with `surface` at 100, 72, 50, 32 %, then `border-strong` | storage-by-category bar. One hue, so no category colour reads as a status; the legend always carries the words |

Motion uses `--om-motion-duration-*`, which are 0 ms under `prefers-reduced-motion`, plus explicit `animation: none` for the shimmer and enter animations.

## Deviations and open points
- **Private class pill is neutral**, not the violet TAXONOMY §2 suggests: TOKENS.md reserves the agent colour for AI actions only.
- **Join QR:** the gateway is expected to return the QR module matrix (`JoinCode.qr`); the demo draws a placeholder pattern that is not a scannable code.
- **New endpoints used** (all PROPOSED, none in contract v0): `/v1/auth/*`, `/v1/tokens`, `/v1/users`, `/v1/agents/*`, `/v1/fabric/*`, `/v1/remote`, `/v1/backups`, `/v1/restores`, `/v1/os/*`, `/v1/notifications/*`, `/v1/automation/rules`, `/v1/audit*`, `/v1/actions/{id}/preview`.
