<!-- SPDX-License-Identifier: Apache-2.0 -->
# Home launcher (`ui/src/home/`)

**Serves:** IA §2.1 (Home), parity audit PU-04 (Home as a launcher), PU-12 (system widgets), PLUGIN-UI.md X1/X2 (app tiles, typed widgets), founder direction of 2026-11-12 ("categorize the apps and deployment"). **Screens:** [`docs/design/screens/home/`](../../../docs/design/screens/home/). **Demo:** `#/home`, `#/home/edit`, `#/home/offline`, `#/home/loading`, `#/home/errors`, `#/home/fresh`.

**Plain English.** Home is the first screen. It answers "is everything fine, and does anything need me?" first, then lets you open your apps. It is a launcher like a phone's home screen: a wallpaper, a greeting, a search bar, a grid of widgets you can arrange, your apps, and a dock of favourites. It never pretends: anything that is not live says so.

## What is on it
| Part | Behaviour |
|---|---|
| Wallpaper | Generated CSS gradients (no image files). `wallpaper="host"` turns it off when the appearance layer (`ui/src/customize/`) already paints one behind every screen. |
| Greeting | Name and part of the day in the **hub's** time zone and clock; a one-line summary (requests waiting, unhealthy apps, stale and offline nodes). Weather slot fed by an app widget, labelled with its age when older than 1 h. |
| Search bar | Opens the command palette (`onOpenSearch`, also Ctrl/Cmd+K while Home is shown). The demo wires the shell's `CommandPalette`. |
| Widgets | Built in: **Needs you** (always first, cannot be removed), System (all nodes or one node: CPU, memory, storage, temperature, uptime), Recent activity, Backups, Updates, Network (mesh links, remote access). Plus typed app widgets from `spec.ui.widgets` (`stat`, `stats`, `list`, `progress`, `status`). Sizes S/M/L; up to 12. |
| Edit mode | Drag, arrow keys on the handle, or earlier/later buttons to reorder; S/M/L radio group to resize; remove; "Add widget" gallery; Reset. Each change is announced in a polite live region. In edit mode each widget shows its API equivalent (P4). |
| Your apps | Installed apps with a status dot **and** the state in words. Category chips use the 16 categories of `docs/design/TAXONOMY.md` §1 (legacy slugs on `main` are mapped: `home-automation` → Home & IoT, `notifications` → Automation, `security` → Network & Security). "Where apps come from" filters by deployment class (§2): From the Market (verified + community), Your own (private), System (core). Tiles carry one badge, the deployment kind (Community / Your own / System); "adds a plugin" and "update available" are in the tile's accessible name, and an update shows as a word under the state, not as a second dot. Open goes to the app's own address only when it is running and the hub is live; otherwise to its app page, which shows the true state. |
| Dock | Pinned apps (up to 8), reorderable in edit mode; floats above the phone tab bar. |

## Honest state (P2)
- Hub answer older than 30 s → stale, older than 120 s → offline (contract §3 limits). Then a banner says so, every widget is dashed with a "Last known" pill, app states read "Running (last known)", and Approve/Deny are disabled with the reason.
- Nodes use their own heartbeat freshness; a stale node's meters turn grey and the card says when the last report was.
- App widgets are stale after 2 × `refreshSeconds`, or when the app is not running.
- CPU and temperature are **not** in the contract heartbeat yet: missing values read "Not reported" / "No sensor", never 0.
- Every widget has loading (skeleton), error (contract error code and message), empty and stale states.

## Data (contract vs PROPOSED)
| Data | Source |
|---|---|
| Nodes | contract `GET /v1/nodes` (§2 heartbeat incl. `uptime_s`). **PROPOSED** heartbeat fields `cpu_percent` (0–100) and `temp_c` (°C or null). |
| Apps | contract `GET /v1/apps`; **PROPOSED** `tags`, `deploy_class`, `plugin` (TAXONOMY.md §5), `open_url` (SEC-P2), `update_available`, `widgets` (PLUGIN-UI.md §5). |
| Needs you | contract `GET /v1/actions?state=awaiting_approval`, `POST /v1/actions/{id}/approve|deny`. |
| Activity, Backups, Updates, Network, app widget payloads | **PROPOSED**: `GET /v1/audit`, `/v1/backups/status`, `/v1/updates`, `/v1/fabric/links`, `/v1/apps/{id}/widgets/{widget}`. |
| Layout per person | **PROPOSED** `GET/PUT /v1/people/me/home` storing the `HomeLayout` JSON. `HomeScreen` is controlled (`layout` + `onLayoutChange`); `sanitizeHomeLayout()` validates anything read back. The demo uses `browserHomeLayoutStore()` (per browser, a convenience only). |

## Home tokens
Defined in `homeTokens.ts` (source of truth) and `home.css`; `logic.test.ts` fails if they drift, and checks that `text`, `text-muted` (on the wallpaper) and `text`, `text-muted`, `text-subtle`, `accent` (on glass over the wallpaper) are ≥ 4.5:1 for every wallpaper colour in both themes.

| Token | Value | Use |
|---|---|---|
| `--omh-wall-<id>-{base,a,b,c}` | 4 wallpapers (`tide`, `dusk`, `ember`, `fog`) × light/dark | Gradient stops of the generated wallpaper |
| `--omh-glass-alpha` / `--omh-glass` | 84 % of `surface` | Widget, search, chip and dock panels over the wallpaper |
| `--omh-glass-border` | 70 % of `border-strong` | Their outline |
| `--omh-blur` | 16 px | Backdrop blur of glass panels |
| `--omh-dot` | 10 px | Status dot |
| `--omh-glyph-radius` | 26 % | App glyph corner |
| `--omh-lift` | −2 px (0 under reduced motion) | Hover lift of tiles, search and dock |

Motion uses the `--om-motion-*` tokens only, so `prefers-reduced-motion` sets every duration to 0; the shimmer, entry animation and lift are switched off too.

## Patterns studied (nothing copied)
umbrelOS (PolyForm Noncommercial: study only) has a wallpaper desktop with a greeting, a small widget limit and a dock. OneMind differs: "Needs you" is locked first because approvals are the core rule; widgets and tiles show freshness; the app grid is grouped by our own taxonomy and deployment class; every action maps to an API call. No umbrelOS code, icons, wallpapers or text are used. Category icon paths are OneMind's own (TAXONOMY.md §1.2).

## Screenshots
`npm run build:demo`, then `NODE_PATH=<playwright install>/node_modules node demo/src/home/shoot.mjs` (set `PW_CHANNEL=chrome` to use an installed Chrome instead of the downloaded Chromium).
