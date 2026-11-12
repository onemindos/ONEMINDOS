# OneMind design system

The design of the OneMind dashboard and phone app, and the plan for app-supplied UI.

| File | What it decides |
|---|---|
| [PRINCIPLES.md](PRINCIPLES.md) | Five rules for every screen (approval first, honest about state, calm, headless first, accessible), and what was taken from which competitor |
| [IA.md](IA.md) | Navigation and every screen: purpose, content, actions, states, data (contract or PROPOSED); phone mapping |
| [TOKENS.md](TOKENS.md) | Colour, type, spacing, radius, elevation and motion, light and dark, with tested contrast |
| [COMPONENTS.md](COMPONENTS.md) | Component inventory with states, built vs planned |
| [PLUGIN-UI.md](PLUGIN-UI.md) | Phase-1 extension points (tiles, typed widgets, sandboxed widgets, settings panels, notification actions), manifest proposal, iframe vs module federation |
| [screens/](screens/) | Screenshots of the demo (`ui/demo`): desktop light, desktop dark, phone |

**Code:** [`ui/`](../../ui/) (React + TypeScript library, tokens as CSS variables, demo of every screen).
**Serves:** backlog items 7, 17 and 24 of `docs/strategy/core-alignment.md` (branch `docs/core-architecture`, not yet on `main`) (UX-P1, MOB-P1, PLG-P1/P2/B1); REC-W11-01, -05, -19, -20.
**Next (phase B):** migrate `dashboard/` onto `ui/` once the wave-2 dashboard changes land; it is not touched here.

## Screens
| Screen | Desktop | Dark | Phone |
|---|---|---|---|
| Home | `home.png` | `home-dark.png` | `home-phone.png` |
| Apps / Market | `apps.png` | | |
| App page (installed) | `app-home-assistant.png` | `app-home-assistant-dark.png` | `app-home-assistant-phone.png` |
| App page (cannot install) | `app-immich.png` | | |
| Approvals | `approvals.png` | `approvals-dark.png` | `approvals-phone.png`, `approvals-phone-dark.png` |
| Activity | `activity.png` | | `activity-phone.png` |
| Nodes | `nodes.png` | `nodes-dark.png` | `nodes-phone.png` |
| Backups | `backups.png` | | |
| Updates | `updates.png` | | |
| Alerts | `notifications.png` | | `notifications-phone.png` |
| Settings | `settings.png` | | |
| Components | `gallery.png` | `gallery-dark.png` | |

All data in the screenshots is invented demo data with a frozen clock (12 Nov 2026, 15:00 UTC).
