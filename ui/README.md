# @onemind/ui: the OneMind design system

Design tokens (as CSS custom properties) and accessible React components for the OneMind dashboard, plus a demo of every screen. Design docs: [`docs/design/`](../docs/design/).

**Serves:** backlog item 7 (UX-P1, design system v0) in `docs/strategy/core-alignment.md` (merged in #17); REC-W11-01 (one React + TypeScript web UI), REC-W11-19 (WCAG 2.2 AA). Language follows BD-02 (TypeScript + React for the UI).

## Why it is a separate package (plain English)
The dashboard (`dashboard/`) is being changed by another work stream right now. Building the design system next to it, as a small library, means both can move at once. Phase B moves the dashboard onto these components. The native phone app can read the same values from `dist/tokens.json`.

## Commands
```sh
npm ci
npm run dev        # demo of every screen at http://localhost:5173 (fixtures only, no gateway)
npm test           # vitest: token drift, WCAG contrast in both themes, component behaviour, axe checks
npm run typecheck
npm run lint
npm run build      # library -> dist/ (onemind-ui.js, ui.css, tokens.json, types) and demo -> dist-demo/
npm run tokens     # after editing src/tokens/tokens.ts: regenerate src/tokens/tokens.css
```
Demo URLs: `#/home`, `#/apps`, `#/app/<id>`, `#/approvals`, `#/activity`, `#/nodes`, `#/backups`, `#/updates`, `#/notifications`, `#/settings`, `#/gallery`. Add `?theme=dark` or `?theme=light` to force a theme.

**Screenshots** (`docs/design/screens/`): Playwright is not a dependency. Install it outside the repo and run:
```sh
npm i --prefix /tmp/pw playwright && npx --prefix /tmp/pw playwright install chromium
npm run build && NODE_PATH=/tmp/pw/node_modules node scripts/screenshots.mjs
# PW_CHANNEL=chrome uses an installed Google Chrome instead of downloading Chromium
```

## Using it
```tsx
import '@onemind/ui/ui.css';
import { AppShell, ApprovalCard, NodeCard, TrustCard, ToastProvider } from '@onemind/ui';
```
Components never fetch. Domain components take props shaped like the contract (`sdk/contracts/poc-v0.md` §2, §3, §11.4) and a `now` (the hub's clock), so the caller owns data and time.

## Layout
```
src/tokens/      tokens.ts (source of truth) -> tokens.css (generated), contrast tests
src/components/  AppShell, Button, Card, StatusPill, Meter, NodeCard, TrustCard, ApprovalCard,
                 EmptyState, Table, Dialog, Toast, ThemeSwitch, Icon
src/lib/         time, freshness (stale/offline rule), trust (install gate), theme
src/styles/      base and component CSS (tokens only)
demo/            static mocks of every screen in docs/design/IA.md
scripts/         token generator, tokens.json writer, screenshot script
```

## v0 limits
- No third-party code or assets; the icon set is original.
- Form inputs, tabs, sheets, the command palette and the widget frame are planned (COMPONENTS.md).
- Contrast is tested on tokens; a rendered-page axe pass with Playwright is the next step.
