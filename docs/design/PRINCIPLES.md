# OneMind design principles

**Serves:** backlog item 7 (UX-P1, design system v0) in `docs/strategy/core-alignment.md` (branch `docs/core-architecture`), REC-W11-01/05/19/20 in [`research-output/12-dashboard-clients-xr.md`](../../research-output/12-dashboard-clients-xr.md), and the founder focus of 2026-11-12: a core OS stable, usable and well designed enough to replace the founder's own cluster.
**Implemented in:** [`ui/`](../../ui/) (tokens, components, demo). **Read next:** [IA.md](IA.md), [TOKENS.md](TOKENS.md), [COMPONENTS.md](COMPONENTS.md), [PLUGIN-UI.md](PLUGIN-UI.md).

OneMind runs a home or a small fleet: several machines, apps, backups, updates and an AI agent. The UI is where a person sees that state and makes decisions. Five principles decide every screen. When two conflict, the earlier one wins.

## P1 · Approval first
Nothing on the box changes until a person approves it. This is the core rule: **AI never actuates without human approval** (CLAUDE.md; contract §3).
- Every button that changes something creates a **request** (an *action*) and leads to Approvals. It never changes state directly. In the UI it is labelled "Request install", not "Install".
- A request always shows: **who asked** (person, agent or the system itself), **why** (an agent must say), **what will happen** in plain words, the **exact parameters**, and **when it expires**.
- Agents can ask. They can never approve. A disabled Approve button always says why it is disabled.
- Risky decisions (remove, restore, expose to the internet) open a confirmation dialog that names the consequence ("its data is kept").

*Why:* umbrelOS and Home Assistant let an owner install with one click, and only add MCP permissions for agents (MATRIX §5; `research-output/02-competitors/umbrelos.md`). OneMind's selling point is that a household, or an AI, can propose anything and nothing happens behind the owner's back. The approval card is therefore the most important component in the system.

## P2 · Honest about state
A value is shown as live only while its source is still reporting. **The UI never shows a cached green.**
- Nodes follow the contract rule: **stale after 30 s, offline after 120 s** without a heartbeat (contract §3). A stale card keeps its last values but has a dashed border, a "Stale" pill and the sentence "The values below are its last report from N ago, not live."
- The same rule applies everywhere (backlog UX-B3): backups say "last *verified* restore 1 d ago", not "backups OK"; scans say "passed 3 Nov 2026", not "secure"; updates say which slot is booted.
- Colour is never the only signal (WCAG 1.4.1): every pill carries a word.
- Unknown is a state. If the UI does not know, it says "unknown", never a default.
- Demo or mock data is labelled on screen ("Demo data").

*Why:* this is the dashboard's existing rule (`dashboard/README.md`, freshness section), and the gap competitors leave. HA shows "unavailable" per entity but has no fleet view; umbrelOS shows one box. A wrong green on a backup or a node is worse than no UI.

## P3 · Calm
The default screen is quiet. Attention is spent only on what needs a person.
- **Home answers two questions:** "is everything fine?" and "does anything need me?". Requests and open alerts come first, then apps, then widgets and activity.
- Neutral surfaces with one accent colour (teal). Status colours (green, amber, red, blue, violet for agents) are used only for status.
- No spinners on idle screens, no auto-playing motion. Motion is short (120–320 ms) and switched off under `prefers-reduced-motion`.
- Plain language first, detail on demand: "Home Assistant restarts (about 1 minute)", then "Exact request and API equivalent" in a disclosure. Kubernetes terms appear only in detail views (REC-W11-05: no global "Pro" toggle, progressive detail per screen).
- Toasts confirm what just happened; they never carry the only copy of important news (that goes to Alerts).

*Why:* Omarchy's tone (`omacom/omarchy` `themes/*/colors.toml`: a small, named palette per theme; keyboard first) and umbrelOS's desktop (calm wallpaper, few elements) show that self-hosting does not need a NOC look. The person using this every day is a household member as often as an operator.

## P4 · Headless first; the UI is a window
Everything the UI does is an API call that the CLI and agents can make under the same rules (REC-W11-20). The UI is one window onto the system, never the only way in.
- Each approval card shows its **API equivalent** (`POST /v1/actions/{id}/approve`) (backlog UX-B2). Where a CLI verb exists it is shown too; planned verbs are labelled as planned.
- Empty states name the command that does the same thing (`onemind node join`).
- The box never needs the phone app or a browser to work (backlog MOB-B3; unlike Olares, which requires LarePass to activate: `research-output/02-competitors/olares.md`).
- The UI holds no state of its own beyond conveniences (theme, a remembered filter). It is safe to close at any time.

## P5 · Accessible and portable by default
- **WCAG 2.2 AA** from the first screen (REC-W11-19). Text contrast ≥ 4.5:1 and focus ring ≥ 3:1 in both themes are **unit-tested** on the tokens (`ui/src/tokens/tokens.test.ts`). Components are checked with axe-core in tests.
- Touch targets ≥ 44 px. Every interactive element has a visible focus ring. Dialogs trap focus and return it.
- One codebase, three widths: sidebar on desktop, bottom tab bar plus "More" on phones (≤ 720 px), and the same tokens exported as JSON for the native mobile shell.
- Light and dark follow the system by default; a person can force either.

## What we took from whom (patterns only)
| Pattern | From | Licence at the commit read | Used as |
|---|---|---|---|
| Core → semantic token layering; a font-size scale variable; named space/radius steps | Home Assistant frontend `src/resources/theme/{core,semantic,typography}.globals.ts` @ `9caad65` | Apache-2.0 | TOKENS.md structure (no code copied) |
| Repairs: issue with severity and "fixable", fix runs a flow | HA frontend `src/data/repairs.ts`, `src/panels/config/repairs/` @ `9caad65` | Apache-2.0 | Alerts with a fix action that becomes a request (backlog NOT-B1) |
| Pre-install review as a stepped dialog, one concern per step; app settings split into credentials, environment, storage, advanced | umbrelOS `packages/ui/src/modules/app-store/install-review-dialog.tsx`, `.../app-page/app-settings-*.tsx` @ `c43beed` | **PolyForm Noncommercial 1.0.0**: study only | Install review flow in IA §2.3; app settings panel slot |
| Typed widget templates filled by the app; small widget limit | umbrelOS `packages/ui/src/modules/widgets/`, `packages/umbreld/source/modules/widgets/routes.ts` @ `c43beed` | PolyForm NC: study only | PLUGIN-UI.md typed widgets |
| Progress "island" for long jobs; command palette; "What's new" after update | umbrelOS `modules/floating-island/`, `routes/settings/cmdk-entries.ts`, `routes/whats-new-modal.tsx` @ `c43beed` | PolyForm NC: study only | IA backlog (UX-P3, UX-P5) |
| Service page = status + health checks + actions + instructions + interfaces + logs; diagnostic screen when the core is down | StartOS `projects/start-os/web/ui/src/app/routes/portal/routes/services/`, `routes/diagnostic/` @ `246876d` | MIT | App page layout (IA §2.3); rescue console note (IA §3) |
| System widgets on the home screen (CPU, disks, network, clock) | CasaOS-UI `src/widgets/{Cpu,Disks,Network,Clock}.vue` @ `400a22c` | Apache-2.0 | Home "storage" widget (no code copied) |
| Theme = a handful of named semantic colours, light or dark | Omarchy `themes/*/colors.toml` @ `ceb30ed` | MIT | Theme overrides map to our semantic roles (TOKENS.md §6) |
| Constellation (multi-server), cron, OpenID screens | Cosmos `client/src/pages/` @ `69c5303` | Apache-2.0 **with Commons Clause**: not Apache-compatible, study only | Confirms Nodes, Automation and Identity as first-class screens |
| App store with categories, dark mode screenshots | Runtipi `packages/frontend/src/modules/`, `screenshots/` @ `a8f22ed` | GPL-3.0: study only | Market filters |
| Permissions shown at install; Control Hub for operators | Olares (`research-output/02-competitors/olares.md`) | AGPL-3.0 + Olares licence: study only | TrustCard "It will be able to" list |
| ZimaOS | `IceWhaleTech/ZimaOS` @ `8bc1599` holds release notes and scripts only, **no licence file** | none: study only | Nothing taken |

**No third-party code, icons, assets or text were copied into `ui/`.** The icon set is drawn for OneMind. The repository has no `NOTICE` file yet, and this work does not need one. If a later change reuses Apache/MIT code (for example Homarr integrations, REC-W11-06), that PR creates `NOTICE` with the attribution.
