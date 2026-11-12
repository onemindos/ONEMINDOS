# Component inventory

**Serves:** backlog item 7 (UX-P1). **Code:** [`ui/src/components/`](../../ui/src/components/). **Visual test page:** `ui/demo` → Components (`screens/gallery.png`, `gallery-dark.png`). **Tests:** `ui/src/components/components.test.tsx` (behaviour + axe-core).

Status: **built** = in `ui/` with tests; **planned** = specified here, not built yet.

| Component | Status | Purpose | States and variants | Accessibility |
|---|---|---|---|---|
| **AppShell** (+ `PageHeader`) | built | Frame: sidebar (desktop), top bar, bottom tab bar + More sheet (phone), skip link, one `<main>` | current item (`aria-current="page"`); badges with words ("3 waiting"); More expanded/collapsed | Skip link; two labelled nav landmarks ("Main", "Main (compact)"), only one visible; `main` focusable for route changes |
| **Button** | built | Every command | `primary`, `secondary`, `ghost`, `danger`; `sm`; `busy` (spinner, `aria-busy`, blocks clicks); disabled | 44 px target (32 px `sm`); focus ring; disabled buttons that matter get a reason via `aria-describedby` |
| **Icon** | built | One original 24 px stroke set (26 icons) | sizes; decorative or labelled | Decorative icons `aria-hidden`; labelled icons `role="img"` |
| **Card** | built | Grouping with title, subtitle, aside, body, footer | `default`, `attention` (amber edge: needs a person), `stale` (dashed: last report, not live), `sunken` | `<section>` labelled by its title; heading level settable (2–4) |
| **StatusPill** (+ `FreshnessPill`) | built | State in one word with a tone | 6 tones; `detail` text; `pulse` (in progress, stops under reduced motion); no-dot variant for identity pills | Always text; colour is never the only signal |
| **Meter** | built | Resource use (memory, disk) | ok / warn ≥ 80 % / bad ≥ 92 %; `stale` (grey fill) | `role="meter"` with value text |
| **NodeCard** | built | One machine (contract §2/§3) | online; stale (dashed + note + "last seen"); offline; k3s not ready; no A/B slot | Freshness as text; meters labelled |
| **TrustCard** | built | Can I trust this app, can it run here (§9.3, §11.1, §11.4) | can install; cannot install (scan missing/failed/stale, invalid date, blocked tier); placement fits / no node + "why not" list; links filtered to http(s) | Verdict first in a polite live region; external links say "opens in a new tab" |
| **ApprovalCard** | built | One request (contract §3 actions) | waiting; expired; running (`dispatched`, pulse); done; failed / outcome unknown (hub message); denied; viewer not allowed (disabled + reason); highlighted | Heading per card; Approve disabled with the reason as its description; exact JSON and API equivalent in `<details>` |
| **EmptyState** | built | Why it is empty and what next | icon, body, action, CLI command | `role="note"` |
| **Table** | built | Lists with columns | sortable columns; empty state; `secondary` columns hidden on phones; rows become stacked label/value cards on phones | Real `<caption>` (can be visually hidden); `aria-sort`; sort buttons inside `th` |
| **Dialog** | built | Decisions and forms on top of a page | `dialog` / `alertdialog`; `sm`/`md`/`lg` | Focus moves in, Tab is trapped, Escape closes, focus returns to the opener; `aria-modal`, labelled and described |
| **Toast** (`ToastProvider`, `useToast`) | built | Confirm what just happened | tones; optional action ("View"); errors stay until closed; others leave after 6 s, paused on hover/focus | Polite `role="status"` region, assertive `role="alert"` region for errors (WCAG 2.2.1) |
| **ThemeSwitch** | built | System / Light / Dark | — | Radio group in a fieldset with a legend |
| Tabs | planned | Sections inside a page (app page on phones) | — | WAI-ARIA tabs pattern |
| Input, Select, Switch, Checkbox, Form field | planned | Settings and dialogs (demo uses plain styled inputs) | error, hint, disabled | Labels, `aria-invalid`, error text linked |
| Sheet | planned | Phone bottom sheet (More, filters) | detents | Same focus rules as Dialog |
| Progress / jobs tray | planned | Long actions in progress (UX-P3; umbrelOS "island" pattern) | determinate / indeterminate | `role="progressbar"` |
| Command palette | planned | Search apps, nodes, settings, actions (UX-P3) | — | Combobox pattern |
| Timeline entry | planned (demo has a list) | Activity row with actor, result, sequence | — | `<time datetime>` |
| Widget frame | planned | Host for typed and sandboxed widgets (PLUGIN-UI.md) | loading, error, stale, permission missing | Title, size and a fallback text |
| Alert card | planned (demo composes Card) | Severity, source, fix action | critical / warning / info; acknowledged | — |

## Rules for new components
1. Tokens only: no raw colour, size or duration in component CSS (`ui/src/styles/components.css` starts with this rule).
2. A component that shows age takes `now` from the caller (the hub's clock), never `Date.now()` inside.
3. Every state above has a gallery entry and a test; anything interactive gets an axe check.
4. Class names are prefixed `om-`; components accept `className` where a wrapper is likely.
5. Domain components (NodeCard, TrustCard, ApprovalCard) take **structural** props that match the contract shapes, so the dashboard can pass API objects straight in. They never fetch.

## Known gaps (v0)
- The `onemind` CLI has no `actions` verb yet, so ApprovalCard shows the REST call (`POST /v1/actions/{id}/approve`) as the equivalent. Add the CLI line when the verb exists.
- The `system:*` requester shown as "System" is a proposal; the contract has person and agent principals only.
- Colour contrast is tested on the tokens, not in rendered pages (axe's contrast rule needs real layout; jsdom has none). A Playwright + axe pass over the demo is the next step.
