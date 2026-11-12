<!-- SPDX-License-Identifier: Apache-2.0 -->
# umbrelOS 2 study: the browser desktop UI, and OneMind's answer

**Date:** 2026-11-12 · **Status:** study and proposal for the founder. Changes no decision in [`docs/DECISIONS.md`](../DECISIONS.md) and not the contract [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md); the new routes in §4.3 go through a contract PR first ([WORKSTREAMS.md](../leap/WORKSTREAMS.md) §4).
**Source studied:** `getumbrel/umbrel` tag `2.1.0-beta.1`, commit `6f357e18d0a4` (2026-11-03). Paths below are shortened: **U:** = `packages/ui/src/`, **D:** = `packages/umbreld/source/modules/`, both at that commit. **OM:** = this repository.
**Builds on:** [`docs/strategy/umbrel-parity.md`](../strategy/umbrel-parity.md) (branch `feat/ui-leap`, gap ids PU-xx; it read the earlier commit `c43beed`), [`docs/design/`](../design/) (PRINCIPLES, IA, TOKENS, COMPONENTS, PLUGIN-UI), [`docs/leap/core/DASHBOARD.md`](../leap/core/DASHBOARD.md), [`docs/leap/dev/API.md`](../leap/dev/API.md), [`MCP.md`](../leap/dev/MCP.md), [`CLI.md`](../leap/dev/CLI.md).

> **Licence rule (hard).** umbrelOS is PolyForm Noncommercial 1.0.0 (`LICENSE.md` at `6f357e18d0a4`). OneMind is sold commercially. This page **reads and describes** umbrelOS's architecture and flows and cites file paths. It copies **no** code, strings, UI text, assets, icons, wallpapers or screenshots, and does not paraphrase code line by line. Everything in §4 is OneMind's own design, built only on components with permissive licences recorded at a pinned version (§4.1).

> **Explain it like I am the founder**
> **Yes: umbrelOS 2 has a real "desktop" in the browser, and it is the main reason it looks better than us.** It is not a window manager (no overlapping windows). It is a phone/macOS-style home screen: a full-screen wallpaper, a "Good morning, Name" greeting, a paged grid of app icons with up to three widgets on top, a macOS-style dock at the bottom that magnifies under the mouse, a right-click menu (add shortcut, edit widgets, change wallpaper, log out), and apps that open as a large rounded **sheet** sliding up over the desktop. Long jobs (installs, backups, uploads) show as small floating "islands" above the dock. The wallpaper you pick also re-tints every accent colour in the UI.
>
> OneMind today has a good design system (`ui/`) and mock screens, but they look like an admin dashboard: sidebar, tiles, tables. None of the desktop layer exists yet, not even on the `feat/ui-leap` branch (it holds only the parity audit).
>
> The plan in §4–§5: build a **Home desktop** of our own (our own generated wallpapers, our own dock, grid, widgets, jobs tray, sheets, command palette), stored **per person on the box** so the phone and every browser match. Then beat umbrelOS where it is weak: approvals and "needs you" live on the desktop, everything shows honest freshness, the jobs tray is tied to the audited action, live usage covers every machine in the house, every customization is also an API/CLI call, and it passes WCAG 2.2 AA including over every wallpaper.

---

## 1. How umbrelOS does it

### 1.1 Architecture in one picture

```
                          createBrowserRouter  (U:router.tsx)
 "/" ─ EnsureNoRaidMountFailure ─ EnsureLoggedIn
        ├─ <Wallpaper/>                     fixed layer, per-account image or video   (U:providers/wallpaper.tsx)
        ├─ <Notifications/>                 system notices as alert dialogs           (U:routes/notifications.tsx)
        ├─ AppsProvider / AvailableAppsProvider / AppStatePolling
        │   ├─ <DesktopContextMenu><Desktop/></…>   Home: greeting, widgets, app grid, Search pill   (U:layouts/desktop.tsx)
        │   ├─ <CmdkMenu/> + <NavigationShortcuts/>  ⌘K palette, Alt+letter jumps            (U:components/cmdk*.tsx, U:modules/desktop/navigation-shortcuts.tsx)
        │   ├─ <Outlet/>                    child routes: edit-widgets, machines, and a SheetLayout
        │   │     SheetLayout ─ files, photos, app-store, community-app-store, settings         (U:layouts/sheet.tsx)
        │   ├─ <GlobalDialogs/>             URL-driven dialogs (?dialog=live-usage, logout, …)    (U:modules/global-dialogs.tsx)
        │   ├─ <FloatingIslandContainer/>   progress islands                                      (U:modules/floating-island/)
        │   └─ <DockBottomPositioner><Dock/>                                                      (U:modules/desktop/dock.tsx)
 "/" bare layout ─ login, factory-reset (blurred wallpaper, no card)
 "/raid-error", "/confirm-static-ip", "/onboarding/*"  (own full-screen flows)
```

Stack (from `packages/ui/package.json`): React with React Router 6, tRPC 11 over TanStack Query 5 (queries, mutations, an event-bus subscription), Tailwind 4 with custom variants and CSS variables, Radix primitives (context menu, dialog, popover, tabs, tooltip…), `motion` 12 for springs and layout animation, `zustand` for small UI stores, `cmdk` for the palette, `vaul` for drawers, `sonner` for toasts, `i18next` for 29 locales, `colorthief` for image colours, `@dnd-kit` for drag and drop.

**Data flow.** Every screen reads the daemon over tRPC (`trpcReact.<router>.<proc>.useQuery`), and live progress arrives either by polling (`refetchInterval`) or through `eventBus.listen` subscriptions. UI preferences that must follow the account (wallpaper, widgets, shortcuts, language, temperature unit) are stored **on the box per account** by `umbreld` (D:`user/`, D:`widgets/routes.ts`, D:`shortcuts/routes.ts`); purely local conveniences (last Files path, closed welcome tips) live in session or local storage. Dialogs are **URL-addressed** (`?dialog=<key>&<key>-for=<appId>`), so a link, the palette or a keyboard shortcut can open any of them.

### 1.2 Home (the "desktop")

| Piece | What it does | Key files |
|---|---|---|
| Desktop frame | Decides between the **welcome desktop** and the real one, prefetches route chunks on idle (`requestIdleCallback`, timeout fallback for Safari), locks page scroll, mounts the URL-driven app dialogs (launch, settings, share). | U:`layouts/desktop.tsx` |
| Desktop content | One column: greeting header → widget row + app grid → Search pill → dock spacer. Merges **installed apps, web shortcuts and pinned virtual machines** into one list sorted by name with numeric collation. Three presentation variants keyed to the route: shown on `/`, lifted and faded under `/edit-widgets`, hidden instantly under a sheet. Icons enter with a staggered scale-and-fade. | U:`modules/desktop/desktop-content.tsx` |
| Greeting | Morning / afternoon / evening by the browser's local hour, with the first name; logo above it, or inline on short screens. | U:`modules/desktop/greeting-message.ts`, `header.tsx` |
| Fit maths | A pure function decides phone scale, "low" (short) screens, inline header and tight widgets from width, height and whether the pointer is touch. Column and row fitting shrink cells and gaps before dropping a column. Unit-tested. | U:`modules/desktop/home-fit.ts` (+ `.test.ts`) |
| App grid and pages | Measures the first page, then chunks widgets and apps into pages; horizontal `scroll-snap` pager with pills and arrow buttons (arrows only on wide fine-pointer screens); edge gradient masks appear only while scrolling; a "not enough room" message when nothing fits. | U:`modules/desktop/app-grid/{app-grid,paginator,app-pagination-utils}.tsx` |
| App icon | Shows install/update progress and state labels; click launches a ready app (members get an explanation dialog for stopped ones); right-click: start/stop, restart, settings, troubleshoot, share with users, go to store page, uninstall. | U:`modules/desktop/app-icon.tsx`, `member-app-unavailable-dialog.tsx`, `app-share-users-dialog.tsx` |
| Desktop context menu | Right-click on the wallpaper: add web shortcut, edit widgets, change wallpaper (a popover picker), log out. The shortcut popover can also be opened from the palette through the URL. | U:`modules/desktop/desktop-context-menu.tsx` |
| Web shortcuts | Bookmark tiles. The **daemon** fetches the page head and picks an icon (touch icon → manifest icon → meta image → `rel=icon` → `/favicon.ico`), 3 s timeout; owner-only routes. The browser then samples the **edge pixels** of the icon on a canvas to pick a square background colour, or pads it on black when the edges are transparent; results cached per URL; first-letter fallback. | U:`modules/desktop/{shortcut-dialog,shortcut-icon,shortcut-icon-image,sample-edge-color}.ts(x)`, D:`shortcuts/{routes,fetch-page-metadata}.ts` |
| Machine icons | A VM pinned to Home looks like an app icon with a small badge of the Machines app; its menu turns the VM on, shuts it down, force-stops, retries an install, or unpins it. | U:`modules/desktop/machine-icon.tsx` |
| Welcome desktop | On a fresh account with no apps while an `onboarding-complete` notification exists: greeting, the real widget row, and a **bento** of animated tip cards (Files, Photos, App Store, remote access), each closable; closing all clears the notification; animations pause when covered. Members see a variant without install copy. | U:`modules/desktop/welcome-desktop.tsx` |
| Search pill | Opens the ⌘K palette; on phones it moves into the islands' row as an orb. | U:`modules/desktop/desktop-misc.tsx`, U:`modules/floating-island/lane.ts` |
| Keyboard | Alt/Option + letter jumps that mirror the dock (Files, Photos, Store, Machines, Settings, Live usage, Home); ignored in text fields and while the palette is open; reads the physical key so macOS's Option characters still work. | U:`modules/desktop/navigation-shortcuts.tsx` |
| iPhone Safari | Lets the wallpaper run under Safari's floating bottom bar on Home only and snaps back accidental page scrolls; a transient empty strip stops Safari tinting that band. | U:`modules/desktop/wallpaper-under-browser-bar.ts` |

### 1.3 Dock and dock tuck

- **Fixed contents, not customizable:** Files, Photos, App Store, Machines (owner only), Settings, Live usage. Badges: app updates on the Store (hidden from members), a settings notification count on Settings. Files reopens the last folder. U:`modules/desktop/dock.tsx`.
- **Magnification:** the pointer's x is a motion value; each item maps its distance from the pointer to a width between rest and zoomed sizes through a spring; the icon is **laid out** at the larger size rather than CSS-scaled (sharper in Safari), only the badge scales. Hover label anchored to the dock baseline; a short CSS bounce on click and an "open" pill under the active item. U:`modules/desktop/dock-item.tsx`.
- **Sizing:** desktop and phone presets; icons shrink so six items always fit; bottom padding honours the safe-area inset (measured with a probe element). The dock is a **glass** surface (see §1.9).
- **Tuck:** on short landscape screens, inside a sheet, the dock slides away when you scroll down and returns when you scroll up (slop and top-zone thresholds; a small global store). U:`modules/desktop/dock-tuck.ts` (+ tests).
- **Prefetch:** pointer entering the dock warms the route chunks. U:`modules/desktop/prefetch-route-chunks.ts`.

### 1.4 Wallpaper and accent

- 25 built-in wallpapers, each declaring one brand colour as HSL in the daemon (D:`user/wallpapers.ts`); one is a video. The provider renders AVIF sources by size tier with a JPG fallback, fades in when loaded, pauses video when a sheet covers Home or the tab is hidden. U:`providers/wallpaper.tsx`.
- **The wallpaper sets the theme:** on change it writes `--color-brand`, lighter variants and a ramp of settings tones as CSS variables on the root, and sets the browser `theme-color`. Picking a wallpaper therefore re-tints buttons, progress rings, focus rings and settings cards.
- Image colours elsewhere (app pages, galleries) come from `colorthief` palettes, run when the image is visible (U:`hooks/use-color-thief.ts`). "Wallpaper sampling" in shortcuts is the edge-pixel method in §1.2.
- Picker: in Settings and from the desktop context menu (U:`routes/settings/_components/wallpaper-picker.tsx`).

### 1.5 Widgets and edit-widgets

- **Typed templates, host-rendered:** `four-stats`, `three-stats`, `two-stats-with-guage`, `text-with-progress`, `text-with-buttons`, `list`, `list-emoji` (U:`modules/widgets/shared/constants.ts`, one component per template in U:`modules/widgets/`). Apps declare widgets in their manifest with an endpoint and a refresh interval (default 5 min); the payload may change the interval.
- **Data path:** browser → `widget.data` (tRPC) → daemon resolves the app container's IP and fetches the declared endpoint, returns the JSON (D:`widgets/routes.ts`, `apps/app.ts` `getWidgetData`). System widgets (CPU, memory, storage, files) are built in (D:`system/system-widgets.ts`, D:`files/widgets.ts`).
- **Per account, limit 3** (`MAX_ALLOWED_WIDGETS` in D:`widgets/routes.ts`, mirrored in the UI). Defaults apply until the account changes them; members only see widgets of apps shared with them (filtered at read time, not persisted).
- **Editing:** `/edit-widgets` is a route; the desktop lifts and fades, and a selector lists each app with its widgets as live previews; selecting a fourth shows a "too many" state. U:`routes/edit-widgets/{index,widget-selector}.tsx`, U:`hooks/use-widgets.ts`.
- Widgets are glass cells laid out by the same pager as apps (U:`modules/widgets/shared/{widget-row,widget-shell,glass-cell}.ts(x)`); a widget for an app that is not ready shows the app's state instead.

### 1.6 Floating islands (progress)

- One container renders an island per kind of long work: Files transfers and operations, audio playback, cloud sync, Photos uploads, backups, disk formatting, RAID operations, VM installs. Each is a pill (150 × 40) that expands to a card (371 × 180); auto-expanded islands settle back to the pill after a delay; some are non-dismissable or forced open (imminent reboot). U:`modules/floating-island/{container,bare-island}.tsx`.
- **Progress ring:** a gradient arc with a blurred twin as glow, indeterminate pulse when there is no percent, 700 ms eased steps. U:`modules/floating-island/progress-ring.tsx`.
- **Lanes:** the islands share the row above the dock with Home's Search pill; one critically-damped spring keeps the pair centred so they never overlap, and on phones the row becomes a single sideways-scrolling strip with Search first. Reduced motion makes the springs jump. U:`modules/floating-island/lane.ts`.
- Note: app installs show progress **on the icon and the install button**, not in an island; scrub results arrive as toasts.

### 1.7 Sheets, immersive dialogs and pickers

- **Sheet layout:** Files, Photos, App Store, community stores and Settings render inside one persistent bottom sheet that zooms up over the desktop with margins showing wallpaper; closing waits for the 200 ms exit animation, then navigates to `/`; scroll position is restored per route; the dock tucks on scroll; a sticky header target and a fixed target are portals for pages. U:`layouts/sheet.tsx`, `sheet-scroll-restoration.ts`, U:`components/ui/sheet.tsx`.
- **Immersive dialog:** a full-screen glass dialog used for Live usage, What's new, terminal, troubleshoot (U:`components/ui/immersive-dialog.tsx`); islands raise above it.
- **Immersive picker:** for dialogs that can target "the system" or "one app" (Troubleshoot, Terminal), the target lives in the URL; with no target the dialog first shows a picker. U:`modules/immersive-picker/{index.tsx,target.ts}` (+ tests).

### 1.8 Routes around the desktop

| Route | What it does | Files |
|---|---|---|
| Onboarding | Start → create account (name, password, warning that it cannot be reset) → storage choice (internal, external drive, SSD/HDD RAID with SSD health and recovery of an existing install) → optional restore from backup → account created. Animated background. | U:`routes/onboarding/**`, U:`components/onboarding-background.tsx` |
| Live usage | Immersive dialog: CPU, memory, storage, GPU and temperature, with a per-app list and actions on heavy apps. | U:`routes/live-usage.tsx` |
| Notifications | System notices rendered as dialogs (backups failing, Thunderbolt device authorization, cloud accounts, app changes), driven by queries and an event-bus subscription. Not an inbox. | U:`routes/notifications.tsx`, D:`notifications/` |
| What's new | Carousel of media shown once when the previous OS version is below a cutoff; hard-coded per release. | U:`routes/whats-new{.ts,-modal.tsx}` |
| Settings | Catalogue and taxonomy of rows, mobile layout, wallpaper, users, 2FA, sessions, MCP, terminal, troubleshoot, Wi-Fi, updates, restart/shutdown, migration. | U:`routes/settings/**` |
| Factory reset | Bare layout over the blurred wallpaper: review what will be lost (accounts, apps, disk use), confirm with password, progress. | U:`routes/factory-reset/**` |
| RAID error | Full-screen page when the storage pool fails to mount: lists devices, offers factory reset. Guards the whole desktop (`EnsureNoRaidMountFailure`). | U:`routes/raid-error/index.tsx` |
| App Store | Discover feed, categories, app page, **stepped install review** (required apps with alternatives → folder access → GPU; steps that do not apply vanish), updates, OS-update-required guard, per-app settings (credentials, environment, storage, advanced). | U:`modules/app-store/**`, U:`features/app-store/**` |
| Community stores | Add a store by Git URL; its apps carry a "community" badge and live under `/community-app-store/:storeId`. | U:`modules/app-store/community-app-store-dialog.tsx`, U:`modules/community-app-store/`, U:`routes/community-app-store/` |

### 1.9 Motion, material and theming

- **Motion:** springs from `motion` for physical things (dock magnification, tuck, islands, lane, icons entering), CSS keyframes for anything that must stay smooth while React mounts a route (dock bounce, sheet in/out, palette, store reveal). Durations are short (150–400 ms). `useReducedMotion` and `prefers-reduced-motion` media blocks collapse animations; the welcome bento pauses when hidden.
- **Glass material:** a shared `Glass` component draws a refractive lens (SVG displacement map, or a WebGL fallback that refracts the wallpaper image) on Chromium and frosted blur elsewhere; it turns solid under `prefers-reduced-transparency` and `prefers-contrast: more`. U:`components/ui/glass.tsx`, `lib/glass-webgl`.
- **Theme:** dark only, white text over wallpaper with drop shadows; the accent is the wallpaper's colour (§1.4); Tailwind custom variants for short screens, two-pane widths, compact widgets and Firefox; `--home-*` clamp variables scale the header with viewport height. U:`index.css`, `packages/ui/tailwind.config.ts`.

### 1.10 Observations (weak spots)

1. The **dock is fixed**: a person cannot pin their own apps to it.
2. **Widgets are capped at 3** and refresh on a timer; a widget shows no age, so a dead app's last numbers look current.
3. The **shortcut icon fetcher** disables TLS certificate checks and has no visible private-address filter (D:`shortcuts/fetch-page-metadata.ts`); it is owner-only, which limits but does not remove the server-side request risk.
4. **App widgets are plain JSON from the container**, rendered by the host: good. But the daemon trusts the payload shape at fetch time.
5. **Notifications are dialogs**, not an inbox with history.
6. **Dark only**; the accent comes from 25 hand-set colours with no visible contrast test.
7. **One box**: live usage and islands describe this machine only.
8. **No approvals**: everything the owner (or an MCP agent with the owner's grants) does happens at once; the desktop has no "needs you" place.

---

## 2. What OneMind has today

| Area | Where | State |
|---|---|---|
| Design system: tokens (light and dark), 14 components with axe tests, ThemeSwitch (System/Light/Dark, per browser) | OM:`ui/src/{tokens,components,lib}/`, docs in OM:`docs/design/{TOKENS,COMPONENTS,PRINCIPLES}.md` | Built on `main`; package `@onemind/ui`, React 19 peer, no runtime dependencies |
| Shell: sidebar on wide screens, bottom tabs + More on phones, top bar with freshness pill | OM:`ui/src/components/AppShell.tsx`, OM:`docs/design/IA.md` §1 | Built |
| Mock screens on fixtures: Home (static greeting, stat tiles, "Needs you", app tiles, activity), Apps, App page, Approvals, Activity, Nodes, Backups, Updates, Notifications, Settings, Gallery | OM:`ui/demo/src/screens/*.tsx` | Mock only |
| Live dashboard (5 screens: SignIn with token, Home counts, Market with Request install, Approvals, Nodes) | OM:`dashboard/src/pages/` | Live, MVP |
| App trust and detail in the dashboard | branch `feat/gateway-agent-mcp`: `dashboard/src/{components/AppTrust.tsx,pages/AppDetail.tsx,lib/useAppRequest.ts}` | In flight |
| Typed widgets (5 templates, gateway fetches and validates, `updated_at` required) | OM:`docs/design/PLUGIN-UI.md` §2 | Specified, not built |
| Motion tokens (120/200/320 ms, two easings, all 0 under reduced motion) | OM:`docs/design/TOKENS.md` §5 | Built as tokens |
| App categories and deployment classes | branch `feat/app-taxonomy`: `docs/design/TAXONOMY.md` | In flight |
| Per-app URL behind the gateway login, per-box CA, edge | branch `feat/core-net`: `docs/architecture/NETWORKING.md` §9 | In flight |
| Parity audit with gap ids PU-01…PU-34 | branch `feat/ui-leap`: `docs/strategy/umbrel-parity.md` | In flight; the branch has **no UI code** yet |
| Desktop client | branch `feat/desktop-client` | Empty |
| Dashboard redesign epics CORE-DASH-1…8 | OM:`docs/leap/core/DASHBOARD.md` §7 | Specified |

### 2.1 Exactly what the UI leap still lacks (against §1)

Nothing in this list exists in `ui/`, `dashboard/` or any in-flight branch at the time of writing.

| # | Missing piece | umbrelOS reference | Our gap id |
|---|---|---|---|
| L1 | Wallpaper layer (image/gradient, fade-in, size tiers, pause when covered) and a wallpaper catalogue of our own | §1.4 | PU-03 |
| L2 | Accent derived from wallpaper or chosen, applied as tokens, with a contrast gate | §1.4 | PU-03 |
| L3 | Appearance settings stored **per person on the hub** (today theme is `localStorage` only) | §1.4 | PU-03 |
| L4 | Personal greeting with name and time of day (mock is static) | §1.2 | PU-04 |
| L5 | Home fit maths and paged launcher grid (pills, arrows, snap, masks) | §1.2 | PU-04 |
| L6 | App tile with live state, progress and a context menu (open, logs, restart as request, settings, pin, remove as request) | §1.2 | PU-04, PU-07 |
| L7 | Desktop context menu (add shortcut, edit widgets, change wallpaper, sign out) | §1.2 | PU-04 |
| L8 | Dock: pinned items, magnification, badges, open indicator, safe-area sizing, tuck on scroll | §1.3 | new (PU-04 said "no dock"; see D-1 in §4.7) |
| L9 | Web shortcuts with server-fetched icons and edge-colour backgrounds | §1.2 | PU-13 |
| L10 | Pinned nodes and pinned automations as Home tiles (our analogue of pinned VMs) | §1.2 | new |
| L11 | Welcome desktop for a new person (tips that close one by one) | §1.2 | PU-05 |
| L12 | Widget frame, the five templates, system widgets, edit-widgets screen | §1.5 | PU-12, CORE-DASH-8 |
| L13 | Jobs tray (our islands): one entry per running action, progress ring, lanes beside Search | §1.6 | PU-06 |
| L14 | Sheet layout (route opens as a sheet over Home, scroll restore, exit then navigate) | §1.7 | PU-32 |
| L15 | Immersive dialog and a target picker ("the box" or "one app") for logs and troubleshoot | §1.7 | PU-19 |
| L16 | Command palette and Alt+letter navigation | §1.2 | PU-10 |
| L17 | Live usage across nodes and apps | §1.8 | PU-17 |
| L18 | Notifications inbox (we planned it; umbrel has dialogs) | §1.8 | PU-30 |
| L19 | What's new, from signed release notes, once per person | §1.8 | PU-25 |
| L20 | Onboarding wizard (passkey owner, wallpaper and accent pick, emergency kit) | §1.8 | PU-05 |
| L21 | Factory reset and storage-failure screens | §1.8 | PU-26, new |
| L22 | Store: categories rail, install review steps, community sources with badge | §1.8 | PU-02, PU-06, PD-12 |
| L23 | Motion beyond fixed durations: springs for dock and tray, layout animation for grid edits | §1.9 | new |
| L24 | A material ("glass") that degrades to solid under reduced transparency and high contrast | §1.9 | new |
| L25 | Route prefetch, safe-area and mobile-Safari handling | §1.2, §1.3 | PU-34 |

---

## 3. Where OneMind will match, and where it will beat umbrelOS

| Area | Match | Beat |
|---|---|---|
| Home look | Full-screen wallpaper, greeting, paged grid, widgets row, Search pill, right-click menu | **Our own** wallpaper set in light **and** dark, each with an accent that passed a WCAG contrast test in both themes; accent can also be picked independently of wallpaper |
| Dock | Magnifying dock with badges and tuck | **Customizable**: the person pins up to 8 items (apps, nodes, system screens); an **Approvals** item with the waiting count is always present for owners; per-person, synced to the phone's tab bar order |
| Layout choice | – | Per-person **layout mode**: `desktop` (dock and grid) or `classic` (today's sidebar shell). Both render the same routes |
| Widgets | Typed templates rendered by the host | Limit 4 (6 on wide screens), **freshness on every widget** (age label, stale after 2 × refresh, P2), widgets from nodes and backups, not only apps; payload schema-validated by the gateway |
| "Needs you" | – | Approvals and open alerts appear on Home first, with Approve/Deny in place; the passkey prompt fires from there |
| Progress | Islands with a ring | **Jobs tray** bound to the action id: each entry links to the approval, the plan and the audit record; survives reload (rebuilt from `/v1/events`), lists every node |
| Live usage | Per-app CPU/memory/storage | **Fleet-wide**: per node and per app, with freshness, placement and "why it runs there" |
| Shortcuts | Bookmark tiles with icons | Icon fetch by the gateway with TLS verification, private-address and size limits, re-encoded to PNG; never fetched by the browser |
| Personalization sync | Per account on the box | Same, plus every change is an API call (`/v1/me/home`), visible to CLI and SDK, and audited |
| Accessibility | Reduced motion and transparency | WCAG 2.2 AA tested in rendered pages (Playwright + axe), keyboard reachable grid and dock (roving focus), screen-reader labels with state and age, contrast checked for every wallpaper × accent × theme |
| Agents | – | An agent may **request** a Home change (for example "pin Immich") via MCP; the owner approves it like any action |
| Release notes | Hard-coded carousel | Built from the signed release notes the updater already verifies; shown once per person per version |
| Failure screens | RAID error page, factory reset | Storage and rescue screens that say what is still safe (last verified backup) before offering anything destructive; reset requires passkey and shows the backup state |

---

## 4. OneMind design for this area

### 4.1 Components and licences

Default: **our own code on our tokens**, no Tailwind and no runtime UI kit, matching `@onemind/ui` today (zero runtime dependencies). Each third-party piece below is optional, chosen only where writing our own would be worse, and enters through the owning PR with its version locked in `package-lock.json` and a `NOTICE` line. Versions are the pins proposed for adoption; the adopting PR confirms each one against the registry and records the licence file it shipped with.

| Need | Choice | Licence | Pin (proposed) | Notes |
|---|---|---|---|---|
| Rendering, routing | React, react-router (already used) | MIT | 19.3.1, 7.18.5 (as in `dashboard/package.json`) | No change |
| Springs and layout animation (dock, tray, grid reflow) | Own `useSpring` (rAF, critically damped) for dock and tray; **Motion** only if grid edit needs FLIP layout animation | MIT | `motion` 12.23.12 | Prefer own code first: dock magnification is about 80 lines; decide in DESK-4 |
| Context menu, popover | Own on WAI-ARIA menu pattern; fallback **Radix** primitives | MIT | `@radix-ui/react-context-menu` 2.2.16, `@radix-ui/react-popover` 1.1.15 | Own first, matching existing Dialog |
| Command palette | **cmdk** | MIT | 1.1.1 | Or own combobox; small |
| Drag to reorder (dock, grid, widgets) | **@dnd-kit** core + sortable | MIT | `@dnd-kit/core` 6.3.1, `@dnd-kit/sortable` 10.0.0 | Keyboard sensor included, which we need for a11y |
| Wallpapers | **Generated by us** (SVG/CSS gradients and patterns, a small script under `ui/scripts/`), optional CC0 photographs with source and licence recorded per file | Ours (Apache-2.0) / CC0 | – | No umbrelOS asset, ever |
| Icons | Existing OneMind 24 px set (`ui/src/components/Icon.tsx`), extended | Ours | – | No umbrelOS icons |
| Image formats | AVIF + WebP + PNG produced at build time with `sharp` (dev-only) | Apache-2.0 | 0.34.4 | Dev dependency only |
| Rendered a11y tests | Playwright + axe-core | Apache-2.0 / MPL-2.0 | `@playwright/test` 1.56.1, `axe-core` 4.14.0 (already used) | axe-core is MPL-2.0 file-level, test-only |

Not adopted: `colorthief` (accent is declared per wallpaper and checked at build time, so no runtime extraction); `vaul` (our Sheet is built on the existing Dialog focus rules); glass refraction via SVG displacement (we use a plain frosted surface with a solid fallback; cheaper on a Pi and easier to keep accessible).

### 4.2 Data model (per person, stored on the hub)

One document per person, owned by the gateway, served at `/v1/me/home`. The browser keeps a `localStorage` copy only as a first-paint cache.

```json
{
  "version": 3,
  "layout": "desktop",
  "appearance": {
    "theme": "system",
    "wallpaper": "om-dusk-01",
    "accent": "wallpaper",
    "density": "comfortable",
    "reduce_transparency": false,
    "reduce_motion": "system"
  },
  "dock": ["sys:approvals", "app:immich", "app:home-assistant", "sys:apps", "node:hub", "sys:settings"],
  "grid": {
    "order": ["app:jellyfin", "shortcut:9f2c", "app:immich"],
    "hidden": ["app:mosquitto"]
  },
  "widgets": [
    {"id": "sys:fleet-usage", "size": "regular"},
    {"id": "app:immich:library", "size": "regular"},
    {"id": "sys:last-backup", "size": "regular"}
  ],
  "shortcuts": [
    {"id": "9f2c", "title": "Router", "url": "https://router.example", "icon": "asset:7a1e", "bg": "#1f2a44"}
  ],
  "seen": {"whats_new": "0.4.0", "welcome_tips_closed": ["files", "market"]},
  "updated_at": "2026-11-12T10:00:00Z"
}
```

Rules:
- Item ids are typed: `sys:<screen>`, `app:<app_id>`, `node:<node_id>`, `shortcut:<id>`, `automation:<id>`. Unknown or no-longer-visible ids are dropped **at read time** (an app un-shared from a person disappears without rewriting the stored document), as umbrelOS does for widgets.
- `dock` ≤ 8 items; `sys:approvals` is forced first for owners and cannot be removed (it is how agents' requests reach the person). `widgets` ≤ 4, or ≤ 6 when `layout` is `desktop` on a wide screen (the server stores up to 6; the client shows what fits).
- `accent` is `"wallpaper"` or one of the preset accent names. Wallpapers live in a catalogue file shipped with the UI: `{id, kind: "svg"|"image", accent_light, accent_dark, text_on: "light"|"dark", credit, licence}`; a build test rejects any entry whose accent fails 4.5:1 against its surfaces in either theme, or whose text tone fails 4.5:1 over the wallpaper's sampled luminance.
- Defaults are computed, not stored, until the person changes something (so improving defaults reaches everyone).
- Stored in the gateway's SQLite ledger (one migration, `ledger.py` rule in WORKSTREAMS §4); included in backups as part of the gateway state.

### 4.3 API, CLI and MCP surface

Style follows [`dev/API.md`](../leap/dev/API.md): `/v1/...`, snake_case, problem+json errors, `If-Match` on writes, events carry ids only. Writing one's own Home is a **direct self write** (API.md P3: low-risk settings a person may change directly; audited). Changing **another person's** Home is not offered.

| Route | Who | Behaviour |
|---|---|---|
| `GET /v1/me/home` | any person | Resolved document (defaults filled, invisible ids dropped), with `ETag` |
| `PUT /v1/me/home` | the person | Whole document; `If-Match` required (`412` on a stale tag); validated against `sdk/schema/home.schema.json`; limits enforced (`422 validation_failed` with the field path); audited as `home.updated` with a diff summary, no URLs in the audit text |
| `GET /v1/wallpapers` | any person | The catalogue (ids, kinds, accents, credits, licences) |
| `POST /v1/me/shortcuts/preview` | the person | `{url}` → `{title, icon_asset, bg}`. The gateway fetches with TLS verification on, 3 s timeout, 512 KiB cap, **no private, loopback or link-local destinations unless the URL's host is a OneMind app or node name**, at most 3 redirects re-checked each hop; icon re-encoded to a 128 px PNG and stored as an asset; `bg` computed server-side by edge sampling (our own implementation) |
| `GET /v1/widgets/{widget_id}/data` | any person who can see the source | Gateway fetches the app's declared in-cluster path, validates against the template schema (PLUGIN-UI §2), returns `{template, payload, updated_at, fetched_at}`; stale or invalid payloads come back with `status: "stale"|"invalid"` instead of an error, so the frame can say why |
| `GET /v1/usage?scope=fleet|node:<id>|app:<id>` | any person (apps filtered by visibility) | CPU, memory, disk, temperature, GPU, each with `measured_at` |
| `GET /v1/events?types=action.*,home.updated` | as API §10 | The jobs tray and multi-tab sync use `action.progress` (`{id, step, percent?}`) and `home.updated` (`{person_id, etag}`) |

CLI (one new group file `cmd/onemind/cli/home.go`, per WORKSTREAMS §3):

```
onemind home show [--json]
onemind home wallpaper list | set <id>
onemind home accent set <wallpaper|name>
onemind home dock pin <item> [--at N] | unpin <item>
onemind home widgets list | add <widget_id> | remove <widget_id>
onemind home shortcut add <url> [--title T] | remove <id>
onemind usage [--node ID | --app ID] [--watch]
```

MCP ([`dev/MCP.md`](../leap/dev/MCP.md) naming: snake_case, verb first):
- `get_usage` (read; scope `usage:read`): fleet, node or app usage with timestamps.
- No direct write tools for Home. An agent that wants a change calls the existing `request_action` with type `home.change` (`{person_id, patch}`; risk class `write`). The person whose Home it is approves it (owner approval for another person's Home is not allowed: only the person themself, or the owner for a `guest`). The executor applies the patch as a self write on that person's behalf and the audit names the agent as requester.

### 4.4 UI screens and components

New components go in `ui/` (design-system stream), wired screens in `dashboard/` (dashboard stream). Every one has gallery entries for all states, tests, and axe checks.

| Component (`ui/src/components/`) | States | Notes |
|---|---|---|
| `Wallpaper` | loading (solid tone), ready, failed (solid tone), paused | Fixed layer; SVG wallpapers render inline (no fetch); images use `<picture>` with AVIF/WebP/PNG tiers; respects `reduce_transparency` by dimming behind content |
| `Greeting` | – | Name and part of day from the **hub's** time zone (P2: never the browser clock for anything stateful; the greeting may use the browser's local hour, the summary line uses hub data) plus one summary line: "Everything is fine" or "2 things need you" |
| `Launcher` (grid + pager) | empty, one page, many pages, not enough room, edit mode | Pure fit function (unit-tested) like §1.2 but our own; roving tab index; arrow keys move focus; PageUp/PageDown change page; edit mode allows drag (dnd-kit keyboard sensor) |
| `Tile` | app (state from `/v1/apps`: running, starting, stopped, stale, failed), node (online, stale, offline), shortcut, automation | Progress ring for an app with a running action; context menu items are **requests** where they change state (Restart → creates `app.restart`), with the plan in the confirm dialog |
| `Dock` | rest, magnified, tucked, edit | Own spring; laid-out size, not transform (same reason as §1.3); badge text for screen readers ("3 waiting"); `Approvals` first for owners |
| `ContextMenu` | – | WAI-ARIA menu; opens with right click, long press and Shift+F10 |
| `WidgetFrame` + 5 templates (`stat`, `stats`, `list`, `progress`, `status`) | loading, live, stale (age shown), invalid, source hidden | Host-rendered text only; links only to the source app's own URL |
| `JobsTray` | empty, collapsed pill, expanded card, finished (stays 5 s), failed (stays until closed) | One entry per action from `/v1/events`; rebuilt from `GET /v1/actions?state=dispatched` on load; ring + step text; link to the approval and audit entry |
| `Sheet` | opening, open, closing | Built on Dialog focus rules; route-driven; scroll restore per route; desktop shows wallpaper margins; phones get full height with a grab handle |
| `ImmersiveDialog` + `TargetPicker` | picker, target chosen | For Logs, Troubleshoot, Live usage; target in the URL (`?dialog=logs&target=app:immich`) |
| `CommandPalette` | idle, results, no results, "request …" commands | Sources: screens, apps, nodes, settings, actions; commands that change state create a request and show its card |
| `AppearancePicker` | – | Wallpaper grid, accent chips, theme, density, reduce transparency/motion; live preview; every swatch labelled with its name |

Screens (`dashboard/src/pages/`, routes per IA):

| Screen | What is new |
|---|---|
| Home (`/`) | `layout: desktop`: Wallpaper → Greeting → "Needs you" strip (only when non-empty) → widgets row + Launcher → Search pill + JobsTray lane → Dock. `layout: classic`: today's AppShell with the same pieces as cards |
| Edit Home (`/home/edit`) | Widgets picker with live previews and the limit, dock and grid reorder, hide tiles; Save is one `PUT /v1/me/home` |
| Welcome (`/` for a new person) | Greeting, default widgets, 3–4 tip cards of our own (Market, Backups, Phone pairing, Approvals), closable one by one; state in `seen` |
| Appearance (`/settings/appearance`) | AppearancePicker; also reachable from the Home context menu |
| Live usage (immersive dialog) | Fleet → node → app drill-down with freshness |
| What's new (immersive dialog) | From signed release notes; once per person per version (`seen.whats_new`) |
| Onboarding, reset, storage failure | Owned by their streams (security, updates, backups); they reuse Wallpaper, Sheet and ImmersiveDialog |

Motion: tokens extended with three spring presets (`spring-snappy` for tray and lane, `spring-dock` for magnification, `spring-gentle` for grid reflow), each also expressed as a CSS `linear()` easing fallback; all collapse to 0 under reduced motion (TOKENS §5). Material: one `--om-surface-glass` role (translucent fill + blur) that becomes the solid `surface` role under `reduce_transparency`, `prefers-reduced-transparency` or `prefers-contrast: more`.

### 4.5 Security

- **Per-person scope.** `/v1/me/home` reads and writes only the caller's document; ids the caller cannot see are dropped at read and rejected at write (`422`), so a stored id never leaks the existence of an app not shared with that person.
- **No app code in the desktop.** Widgets are typed data rendered by the host; payload strings are text, never HTML; numbers are clamped; links must resolve to the source app's own gateway URL.
- **Server-side fetches are fenced** (shortcut preview, widget data): allow-listed destinations, TLS verified, size and time caps, redirects re-checked, results re-encoded. This closes the gap noted in §1.10 item 3.
- **State changes from the desktop are requests.** Restart, stop, remove, pin-by-agent all go through `/v1/actions` and the approval path; the tile's menu shows who can approve.
- **Audit.** `home.updated` is recorded with the person and a field-level summary; shortcut URLs are stored but not copied into audit text.
- **CSP.** Wallpapers are same-origin assets or inline SVG produced at build time (no `foreignObject`, no script; checked by a test). Shortcut icons are served from the gateway asset store with `Content-Type: image/png` and `X-Content-Type-Options: nosniff`.
- **Keyboard shortcuts** never fire inside inputs, editors or an app's embedded console, and never override browser or OS combinations other than bare Alt+letter.
- **Cache.** The `localStorage` copy holds no secrets and is ignored if its `etag` differs from the hub's; it exists only to avoid a blank first paint.

### 4.6 Performance budget

Home's first paint from cache under 1 s on a Pi 5 over LAN; the shell's initial JS at most 200 KB gzip (PU-34); wallpaper first tier at most 120 KB; route chunks prefetched on idle and when the pointer enters the dock; magnification and tray springs run on transforms or laid-out sizes only, no layout of other elements per frame.

### 4.7 Decisions for the founder

| Id | Question | Proposed default |
|---|---|---|
| D-1 | The parity audit (PU-04) said "no dock". The founder wants the umbrelOS look. | Ship `layout: desktop` (dock + grid) as the default on wide screens and `classic` on phones; each person can switch |
| D-2 | Widget limit | 4 (6 on wide screens in desktop layout) |
| D-3 | Dark-only like umbrelOS, or light and dark | Both; each wallpaper has a light and dark accent |
| D-4 | May an agent request Home changes? | Yes, as `home.change` requests approved by that person |

---

## 5. Epics

Ids `DESK-n`. Owner paths follow [WORKSTREAMS.md](../leap/WORKSTREAMS.md): `ui/**` and `docs/design/**` belong to the design-system stream (`feat/design-system`, later `feat/ui-leap`); `dashboard/src/{components,api}/**`, Home and pages no other stream names, and `Settings*.tsx` belong to the dashboard stream; route modules belong to gateway core, adding one line to `routes.py`; `ledger.py` gets one migration file; the contract and `sdk/schema/*` change only in a contract PR; CLI group files in `cmd/onemind/cli/`; MCP in `core/onemind_core/mcp/**`. Size: S ≤ 2 days, M ≤ 1 week, L > 1 week.

| Id | Title | Size | Owner paths | Acceptance (tests) | Depends on |
|---|---|---|---|---|---|
| DESK-0 | Contract PR: `/v1/me/home`, `/v1/wallpapers`, `/v1/me/shortcuts/preview`, `/v1/widgets/{id}/data`, `/v1/usage`, events `action.progress` and `home.updated`, action type `home.change`, `home.schema.json` | S | `sdk/contracts/poc-v0.md`, `sdk/schema/home.schema.json` (hotspot, contract stream) | Schema validates the §4.2 example and rejects: 9 dock items, 7 widgets, unknown id prefix, non-http(s) shortcut URL. Contract lint passes | C12-A, DEV-API-5 (`/v1/me`) |
| DESK-1 | Home document store and routes | M | `core/onemind_core/home.py` (new), one line in `routes.py`, one migration in `ledger.py` | `GET` returns defaults for a new person; `PUT` without `If-Match` → 428, stale tag → 412; a second person cannot read the first's document (403/404 test); an app un-shared from an `adult` disappears from `GET` without a write; every `PUT` creates one `home.updated` audit entry; `home.updated` event emitted with id and etag only | DESK-0, DEV-API-1 |
| DESK-2 | Wallpapers and accents of our own | M | `ui/scripts/gen-wallpapers.ts` (new), `ui/src/assets/wallpapers/**`, `ui/src/tokens/**`, `docs/design/TOKENS.md` | At least 12 generated wallpapers, each with `credit` and `licence` fields; build test computes contrast for accent and text over each wallpaper in light and dark and fails below 4.5:1; a test asserts no file under `ui/src/assets/` matches a hash list of umbrelOS asset files; SVGs contain no `script` or `foreignObject` | – |
| DESK-3 | `Wallpaper`, `Greeting`, `AppearancePicker`, glass role and spring tokens | M | `ui/src/components/{Wallpaper,Greeting,AppearancePicker}.tsx`, `ui/src/styles/**`, `ui/src/tokens/**`, `ui/demo/**` | Gallery shows every state; axe passes; under `prefers-reduced-transparency` and `prefers-contrast: more` the glass role resolves to a solid surface (computed-style test); all springs resolve to 0 ms under reduced motion | DESK-2 |
| DESK-4 | `Launcher`, `Tile`, `ContextMenu`, `Dock` | L | `ui/src/components/{Launcher,Tile,ContextMenu,Dock}.tsx`, `ui/src/lib/home-fit.ts` | Unit tests for the fit function (columns and rows at 360×640, 768×1024, 1440×900, 1920×1080, landscape phone 844×390); keyboard: Tab reaches the grid then the dock, arrows move focus, Shift+F10 opens the tile menu, Escape closes it; Playwright: magnification follows the mouse and settles; dock tucks on scroll in a short viewport and returns at the top; edit mode reorders with keyboard only | DESK-3 |
| DESK-5 | `WidgetFrame`, five templates, widget data route | M | `ui/src/components/widgets/**`; `core/onemind_core/widgets.py` (new; agreed with the plugins stream, DEV-PLG) | Payload failing the template schema renders `invalid` with the reason; a payload older than 2 × refresh renders `stale` with its age; HTML in a string renders as text; a widget for an app the person cannot see returns 404; system widgets (fleet usage, last backup, waiting approvals) render from fixtures and live | DESK-0, DESK-3 |
| DESK-6 | `JobsTray` and `action.progress` | M | `ui/src/components/JobsTray.tsx`; executor progress events through the sandbox owner (`executors.py` hook, WORKSTREAMS §3) | Starting an install shows a tray entry within 1 s of `dispatched`; reloading the page mid-install restores it from `GET /v1/actions`; a failed action stays until closed and links to its audit entry; tray and Search never overlap at 360, 768 and 1440 px (Playwright screenshot assertions) | DESK-0, CORE-SANDBOX-2 |
| DESK-7 | `Sheet`, `ImmersiveDialog`, `TargetPicker` | M | `ui/src/components/{Sheet,ImmersiveDialog,TargetPicker}.tsx` | Focus moves into the sheet and returns to the opener on close; Escape and the close button navigate to `/` after the exit animation; scroll position restored when returning to the same route; target in URL opens the right target directly | DESK-3 |
| DESK-8 | `CommandPalette` and Alt+letter navigation | S | `ui/src/components/CommandPalette.tsx`, `dashboard/src/components/Shortcuts.tsx` | Combobox pattern passes axe; ⌘K / Ctrl+K opens; "restart Immich" produces a request card, never an immediate change; Alt+letter ignored inside inputs and while the palette is open; physical-key fallback test for macOS | DESK-4 |
| DESK-9 | Home and Edit Home wired to the hub | M | `dashboard/src/pages/{Home,HomeEdit}.tsx`, `dashboard/src/api/**`, route lines in `App.tsx` (hotspot) | With the gateway in test mode: change wallpaper in one browser, a second open browser updates within 2 s via `home.updated`; reorder dock, reload, order kept; `classic` and `desktop` layouts both pass axe and the IA screen-state checklist (IA §4); offline hub: Home renders from cache with a "last known" label | DESK-1, DESK-4, DESK-5, CORE-DASH-2 |
| DESK-10 | Shortcuts with fenced icon fetch | S | `core/onemind_core/shortcuts.py` (new), `ui/src/components/Tile.tsx` (shortcut variant) | Preview of `http://127.0.0.1`, `http://169.254.169.254`, a private-range address and a redirect into one all return `422 destination_not_allowed`; an invalid certificate fails; a 2 MiB page is cut at 512 KiB; the icon is stored as PNG ≤ 128 px; edge-colour background computed by our own code (test with transparent and opaque fixtures) | DESK-1 |
| DESK-11 | Welcome desktop | S | `dashboard/src/pages/Home.tsx` (welcome state), `ui/src/components/TipCard.tsx` | New person sees tips; closing all sets `seen.welcome_tips_closed` and the next load shows the normal Home; tips are our own copy; reduced motion stops tip animations | DESK-9 |
| DESK-12 | Live usage (fleet, node, app) | M | `core/onemind_core/metrics.py` (dogfood stream, `feat/app-metrics`), `dashboard/src/pages/Usage.tsx` | Every number shows `measured_at`; a node that stopped reporting shows stale, not zero; an `adult` sees only apps shared with them; `onemind usage --json` equals the API output | DESK-0, CORE-DOGFOOD app metrics |
| DESK-13 | CLI `onemind home` and `onemind usage` | S | `cmd/onemind/cli/home.go`, one line in `root.go` (hotspot) | Golden tests for `show`, `dock pin`, `widgets add` in table and `--json`; pin on a stale etag retries once then exits with the conflict code from CLI.md | DESK-1, DEV-CLI-1 |
| DESK-14 | MCP `get_usage` and `home.change` requests | S | `core/onemind_core/mcp/**` (MCP stream), action type registry entry | An agent calling `request_action` `home.change` gets an `awaiting_approval` action; approval by the owner for an `adult`'s Home is refused; approval by that person applies the patch and the audit names the agent as requester; `get_usage` honours `usage:read` | DESK-1, DESK-12, DEV-MCP-1 |
| DESK-15 | What's new from signed release notes | S | updates stream (`core/onemind_core/os_updates.py` exposes notes), `dashboard/src/pages/Updates.tsx` owner adds the dialog | Shown once per person per version; content comes only from the verified release metadata; dismissal written to `seen.whats_new` | CORE-UPDATE-2, DESK-7 |
| DESK-16 | Rendered accessibility and performance gate | S | `ui/tests/e2e/**`, new workflow file `.github/workflows/ui-e2e.yml` | Playwright + axe over Home (both layouts, light and dark, three wallpapers), Edit Home, Sheet and palette with zero violations; bundle budget check fails the build above 200 KB gzip initial JS | DESK-9 |

Suggested order: DESK-0 → DESK-2/3 (in parallel with DESK-1) → DESK-4 → DESK-5/6/7 → DESK-9 → DESK-8, 10, 11 → DESK-12–16. DESK-2 to DESK-4 need no contract change and can start at once on the design-system stream.

---

## 6. Licence ledger for this page

- **umbrelOS** (`getumbrel/umbrel@6f357e18d0a4`, PolyForm Noncommercial 1.0.0): read for architecture, data flow and interaction patterns only. No code, string, UI text, icon, wallpaper, asset or screenshot was copied into this repository; names of umbrelOS files are cited as references. Implementations in §4–§5 must be written from this description and OneMind's own specs, not from umbrelOS source.
- Components proposed in §4.1 are MIT or Apache-2.0 (axe-core MPL-2.0, test-only); each adopting PR records the exact version and licence file and adds a `NOTICE` line if any code is vendored.
- Wallpapers, tip illustrations and icons are generated or drawn for OneMind, or CC0 with source recorded per file.

## 7. Limits of this page

- umbrelOS was read at source level, not run; behaviour is inferred from code, comments and tests at `6f357e18d0a4`.
- Proposed component versions are pins to confirm at adoption, not verified in this repository's lock files.
- Effort sizes assume one engineer with an agent and the contract PR (DESK-0) accepted first.
