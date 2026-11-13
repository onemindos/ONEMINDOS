<!-- SPDX-License-Identifier: Apache-2.0 -->
# Design critique: `@onemind/ui` against umbrelOS-level polish

**Date:** 2026-11-12 · **Serves:** founder brief of 2026-11-12 ("the UI is major for me: it must look good and have customizations"; match and beat umbrelOS polish; **categorize apps and deployment**), parity items PU-02/03/04/06/07/10 in [`docs/strategy/umbrel-parity.md`](../strategy/umbrel-parity.md), principles P1–P5 in [PRINCIPLES.md](PRINCIPLES.md).
**Method:** every PNG under [`screens/`](screens/) was reviewed, then the demo was built (`cd ui && npm ci && npm run build`) and re-rendered in Chrome at 1280 px and 390 px, light and dark. umbrelOS was **not** run or copied; the bar is the polish described in the parity audit (PolyForm NC: study only).

> ### In plain words
> The design system is strong where OneMind is different (approvals, honest stale states, trust card), but the first-impression surfaces had small, visible cracks: titles cut to "Up…", two navigation bars on phones, cards that stretched into banners, a jobs pill floating over dialogs, and a requester shown as "Agent" when it was the box itself. Twelve of the defects below are fixed in this change; the rest are listed as follow-ups with their owner area.

## How to read the table
**Rank:** 1 = most visible or most damaging to trust. **Sev:** H = breaks a principle or a layout; M = visibly unpolished; L = nit. **Status:** Fixed (this change) or Open.

## 1. Ranked defects

| # | Screen | Defect | Sev | Status |
|---|---|---|---|---|
| 1 | Appearance (all 24 shots) | The committed screenshots were half blank with a second app shell painted at the bottom: the capture grew the viewport and shot before re-layout. The founder's "customizations" screen looked broken. | H | **Fixed**: capture waits two frames after resizing; all shots re-taken |
| 2 | Home, phone | Small widgets ran two per row at 390 px, so titles read "Up…", "Back…", "Netw…" and a number read "3…" ms. | H | **Fixed**: one widget per row under 560 px |
| 3 | Home, phone | A floating dock sat above the bottom tab bar: two navigation bars, the dock covering content. The parity audit (PU-04) says no dock. | H | **Fixed**: dock hidden on phones; bottom tabs remain |
| 4 | Command palette | Requests from `system:updates` were labelled "Agent updates". P1 says every request shows **who asked**; calling the box an agent is wrong. | H | **Fixed**: same rule as ApprovalCard (`system:` → System); test added |
| 5 | Installed apps | Rows had no category and no deployment kind, so the list did not answer the founder's "categorize apps and deployment". | H | **Fixed**: each row shows category (with icon) and kind pill (Verified / Community / Private / Part of OneMind, plus Plugin); test added |
| 6 | Installed apps | Backup agent showed a disabled "Open" with no reason (P1: a disabled button always says why). | M | **Fixed**: "No web page" instead; a stopped app's Open has a tooltip naming the fix |
| 7 | Store, install review | The jobs pill floated above the dialog scrim and, on phones, over the dialog's buttons. | M | **Fixed**: tray hidden while any dialog is open |
| 8 | Store, Discover | Category rails with one or two apps stretched a card across the whole row (Synapse, Hermes Agent as banners). | M | **Fixed**: rail columns capped at a third of the row |
| 9 | Store, cards | The fit line ("Fits on office-laptop") wrapped above the button on some cards, so footers did not line up across a rail. | M | **Fixed**: footer stays on one line; the fit text ellipsizes |
| 10 | Home, desktop | Widget titles cut to "Uptime Kuma ·…", "ntfy · Last mes…", "Home Assista…", because the word "Open" took the space. | M | **Fixed**: titles wrap to two lines; small widgets show the chevron only (the link still reads "Open <widget>" to screen readers) |
| 11 | Home, app tiles | Each tile had two coloured dots (status, and a blue update dot that matched the blue "Starting" dot) and up to two stacked pills ("Community" + "Plugin"). | M | **Fixed**: one status dot; "update" as a word under the state; one pill (the deployment kind) |
| 12 | Store, Home | "Plugin" and "Your own" used the violet tone that P3 reserves for agents. | M | **Fixed**: info (blue) tone |
| 13 | App page (manage) | "Remove…" was in the accent colour like a normal link, and nothing said Restart/Stop/Update are requests. | M | **Fixed**: Remove in the danger tone; one line under the bar says each action is a request an owner approves |
| 14 | Appearance, theme cards | Auto and Scheduled thumbnails split diagonally and read as a black wedge; onboarding used a clean vertical split. | M | **Fixed**: vertical split with a hairline, matching onboarding |
| 15 | Store, install review | The helper sentence touched the step bar. | L | **Fixed**: spacing below the step bar |
| 16 | App detail, screenshots | The "Illustration · not a real screenshot" label was clipped at the page edge, and slides stretched unevenly. | L | **Fixed**: label on the left; fixed slide width |
| 17 | Home, phone, System widget | Node names wrapped ("office-/laptop") beside the numbers. | L | **Fixed**: numbers on their own line under 560 px |
| 18 | Home, category chips | The chip row scrolled sideways with the last chip cut flat ("Network"), so the scroll was invisible. | L | **Fixed**: fade on the right edge |
| 19 | Store, Discover | Discover lists every category in full under the editorial rails: 6,900 px at 1280 px. umbrelOS-style Discover is a few curated rows, with "All apps" one tap away. | M | Fixed (`feat/dashboard-v2`): editorial rails + the 4 fullest category rails; the other categories are chips under "More categories" (`DISCOVER_RAILS`) |
| 20 | Home vs Store | App icons differ: pastel single-letter glyphs on Home, saturated two-letter gradient tiles in the Store. One app looks like two brands. | M | Fixed (`feat/dashboard-v2`): `components/AppIcon.tsx`; `AppTile` and Home's `AppGlyph` render it; test checks the same hue and monogram |
| 21 | Dialogs on phones | Install review and other dialogs are centred modals at 390 px; the COMPONENTS "Sheet" (PU-32) is still planned. | M | Fixed (`feat/dashboard-v2`): every `Dialog` is a bottom sheet under 720 px (grabber, full-width stacked actions, safe-area padding) |
| 22 | Manage, phone | Action buttons wrap into ragged rows (Open / Restart / Stop, then Update alone). | L | Fixed (`feat/dashboard-v2`): Open + "More actions" disclosure under 720 px |
| 23 | Approvals, phone | The waiting list scrolls sideways with cards cut at the edge and no hint; Recent decisions put each pill on its own line. | L | Fixed (`feat/dashboard-v2`): vertical queue under 720 px; decision pill stays inline |
| 24 | Home, edit mode | Every widget gets its own toolbar (drag, arrows, S/M/L, remove) and its API line wraps mid-path. Busy, though complete. | L | Fixed (`feat/dashboard-v2`): toolbar shows on the hovered or focused widget (always on touch); API line is one truncated row with Copy |
| 25 | Demo-only | State switchers differ per area (underlined links on Appearance, pills elsewhere). Not product UI, but it shows in every screenshot. | L | Fixed (`feat/dashboard-v2`): Appearance uses the same chip switcher as the other demo screens |
| 26 | Docs | `ui/src/*/README.md` and the store commit cite `docs/design/TAXONOMY.md`, which is not in this tree. | M | Fixed: `docs/design/TAXONOMY.md` is in the tree; the README links resolve |

## 2. Before and after

| # | Before | After |
|---|---|---|
| 1 | `customize/appearance-custom-desktop-light.png`: Theme and Accent, then ~1,500 px blank, then a second top bar | Full page: Theme, Accent, Wallpaper (13 generated wallpapers), Layout and text, Motion and effects |
| 2, 3, 17 | `home/home-phone.png`: 2-up widgets with "Up…" / "3…", dock over the tab bar | One widget per row, readable titles and numbers, node rows on two lines, no dock |
| 4 | `shell/palette.png`: "Agent updates · expires in 5 d" | "System updates · expires in 5 d" |
| 5, 6 | `store/installed.png`: name, version, node; disabled "Open" on Backup agent | Adds "Home & IoT · Verified", "Monitoring · Verified · Plugin", "Files & Photos · Part of OneMind"; "No web page" |
| 7, 15 | `store/install-review*.png`: jobs pill over the dialog; text against the bar | No pill while the dialog is open; spaced header |
| 8, 9 | `store/discover.png`: one-app rails as full-width banners; ragged footers | Card-sized cards in every rail; footers aligned |
| 10, 11, 12 | `home/home.png`: truncated titles; two dots and two pills per tile | Two-line titles, chevron links; one dot, "· update", one kind pill |
| 13 | `store/manage.png`: teal "Remove…" | Red "Remove…" and "sent as requests; an owner approves each one first" |
| 14 | Appearance theme cards with a diagonal wedge | Light-left / dark-right split |

## 3. Where OneMind already beats umbrelOS (kept intact)
The approval card with "what will happen" and the signed plan hash, the requester pill, dashed stale widgets with "last report N ago", the trust card verdict, keep-data remove, and the API/CLI equivalents in edit mode and on every request. None of these were simplified away; fixes 4–6 and 13 make them more consistent.

## 4. Verification
- `npm ci`, `npm run lint`, `npm test` (11 files, **252 tests**, including axe checks), `npm run build` (library + demo): all pass.
- New tests: palette labels a `system:` principal "System" (`src/shell/shell.test.tsx`); installed rows show category, kind and "No web page" (`src/store/store.test.tsx`).
- Screenshots re-taken with the area scripts: `demo/src/home/shoot.mjs`, `demo/src/customize/screenshots.mjs`, `demo/src/shell/screenshots.mjs`, and the new `demo/src/store/screenshots.mjs` (discover, installed, updates, manage, app page, install review; light/dark, desktop/phone). Other store shots (filters, search, uninstall, jobs tray, states) still come from the original run and do not show fixes 5–9.

## 5. Licence note
No umbrelOS code, assets, icons, wallpapers or text were used. All changes are CSS and TSX written for OneMind.
