<!-- SPDX-License-Identifier: Apache-2.0 -->
# Shell (`src/shell`)

Shell-wide pieces every screen shares: the command palette, the notification centre, toasts, the first-run wizard and the state system (loading, empty, error, stale, offline, forbidden).

**Serves:** UX-P3 (command palette), NOT-P1 and NOT-B3 (notification centre, deep links), ONB-P1, ONB-B1 and ONB-B2 (first run, headless twin, emergency kit), IA §4 (screen states), and parity items PU-05 and PU-10. **Design rules:** [PRINCIPLES.md](../../../docs/design/PRINCIPLES.md) P1–P5. **Screens:** `docs/design/screens/shell/` (light and dark, desktop and phone). **Demo:** `#/shell/<palette | palette-search | notifications | toasts | states | onboarding-1…6>`.

## Pieces

| Piece | What it does | Rules kept |
|---|---|---|
| `CommandPalette`, `PaletteTrigger`, `usePaletteHotkey` | Cmd-K / Ctrl-K from anywhere. Groups: Approvals, Recent, Apps, Requests, Nodes, Settings, Go to. Prefixes: `>` requests only, `@` nodes, `#` a category | WAI-ARIA combobox and grouped listbox; arrow keys, Ctrl Home/End, Enter, Esc clears then closes; focus returns to the opener. Requests are labelled **Request** and create an action that waits in Approvals (P1). The footer shows the API or CLI call for the active row (P4). Link-only and core apps are never offered as installs. A row the viewer cannot run stays visible and reads its reason (IA §4 Forbidden). Results from stale data say so |
| `NotificationBell`, `NotificationCentre` | Bell with an unread badge (amber when something needs you), popover on desktop and a bottom sheet on phones. Filters All, Unread, Needs you; day groups (UTC, the hub's day); mark read or unread; mark all read; one deep link per item | Only in-app links are followed (`safeDeepLink`). When the hub is stale or offline the list stays, labelled with its age, and read state cannot change |
| `toastForNotification`, `toastForRequest`, `useNotificationToasts` | Toasts on top of the library `ToastProvider` | A request toast says it is waiting, not done. Only new unread arrivals toast (at most 3, then "N more"); the first load never toasts. Critical ones use the error tone and stay until closed. The centre keeps the copy (P3) |
| `Onboarding` | Six steps: name the box and time zone, owner and passkey, theme and accent, starter apps by category, backup destination and emergency kit, summary | The kit and the passkey cannot be skipped (ONB-B2). Starter apps become `app.install` requests, never installs (P1). Memory asked for is compared with the hub's free memory. The summary shows the headless twin, `onemind init …` (ONB-B1, planned verb). The accent re-tints the wizard live |
| `StateView`, `Skeleton`, `viewState` | One component and one rule for every panel state, with copy for each empty list in `EMPTY_PRESETS` and plain words for each contract error code | Data already held is never thrown away on an error: it is shown as stale or offline. `permission_denied` is "forbidden" with the reason. Loading says what is slow after 10 s |

## Data

Types follow the contract where it defines them (`ActionSummary`, `NodeSummary`, contract §2 and §3). The notification record follows backlog NOT-P1 plus `kind`, `read` and `href`; its endpoints are **PROPOSED**:

| UI action | API (PROPOSED unless noted) |
|---|---|
| Open the centre | `GET /v1/notifications` |
| Mark read / unread | `POST /v1/notifications/{id}/read`, `…/unread` |
| Mark all read | `POST /v1/notifications/read-all` |
| Run a palette request | `POST /v1/actions` (contract §3) |
| Review an approval from the palette | `GET /v1/actions/{id}` (contract §3) |
| Finish onboarding | `onemind init …` (planned CLI) and one `POST /v1/actions` per starter app |

Categories and deployment classes come from `src/store/taxonomy.ts` (docs/design/TAXONOMY.md §1–§2), so the palette, the wizard and the Market use the same names. Accent presets come from `src/customize/accents.ts`, so a colour picked during setup is one Appearance settings knows; contrast for every preset in both themes is tested there.

## Tokens

Only design tokens are used. Shell-only additions, all layout or derived from tokens:

| Token | Value | Use |
|---|---|---|
| `--oms-palette-width` | 680px | Palette panel width |
| `--oms-palette-top` | 12vh | Palette offset from the top on desktop |
| `--oms-pop-width` | 420px | Notification popover width |
| `--oms-onb-side` | 300px | Wizard progress column |
| `--oms-onb-content` | 680px | Wizard form width |
| `--oms-glass` | `surface-raised` at 97% | Palette panel over a blurred page |
| `--oms-ring-soft` | `accent` at 28% | Soft selection ring around chosen cards |

The wizard's side panel and the empty-state emblem are drawn with CSS gradients and inline SVG made for OneMind. No third-party code, icons, images or text were used. umbrelOS (PolyForm Noncommercial) was studied for flows only: the onboarding route list and the cmdk entries.

## Bundling note

`package.json` marks only `*.css` as side-effectful, so bundlers skip barrel files that only re-export. Each component therefore imports `shell.css` itself; a stylesheet imported only from an `index.ts` is dropped from the demo bundle.
