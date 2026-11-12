<!-- SPDX-License-Identifier: Apache-2.0 -->
# App Store and app management (`@onemind/ui` store)

**Serves:** founder direction of 2026-11-12 ("categorize apps and deployment"; umbrelOS-level polish or better), parity gaps PU-02, PU-06, PU-07, PU-08, PU-11 and PD-01 to PD-09, backlog APP-P1 to P3, APP-B1, APP-B3. **Taxonomy:** `docs/design/TAXONOMY.md` (16 categories, deployment classes, placement facets). **Screens:** `docs/design/screens/store/` (light and dark, desktop 1280 px and phone 390 px). **Demo:** `npm run dev`, then `#/store`.

**Plain English.** The Market is where a person finds apps by what they are for (category and sub-tags) and sees, before clicking, how far OneMind vouches for each one (its deployment class) and whether any of their machines can run it (the hub's fit verdict). Every button that changes something creates a *request* that waits in Approvals; the UI never installs, restarts or deletes on its own.

## What is here

| Part | File | What it does |
|---|---|---|
| Data shapes | `types.ts` | `CatalogApp` (contract §3/§4/§9.3/§11.4 + PROPOSED taxonomy fields), `AppPlan`, `InstalledApp`, `StoreJob`, `LoadState` |
| Taxonomy | `taxonomy.ts` | The 16 categories with closed sub-tag lists, the five deployment classes with label, tone and sentence, licence classes, device and exposure wording |
| Rules | `logic.ts` | Search and filters, chip counts, the one primary action per app, request building with API and planned CLI equivalents, job progress |
| Market | `Market.tsx` | Search, category rail with counts, sub-tag row, filters (class, fit, arch, licence class, tier, plugin, GPU), Featured hero, Needs-you rail, Discover collections, one rail per category, results grid, "N hidden" line |
| App page | `AppDetail.tsx` | Hero, screenshot carousel slot, trust card (class, licence class, scan date and result, vulnerabilities, malware, signature, smoke test, links), requirements and per-node fit verdict, permissions, release notes, install button with live progress |
| Install review | `InstallReview.tsx` | Stepped dialog generated from the facets: community acknowledgement, node, devices, network, storage, exposure, review; sends one `app.install` |
| Progress | `Jobs.tsx` | Four-step track (awaiting approval → pulling image → starting → healthy, or rolled back) and the floating jobs tray |
| Installed | `Installed.tsx`, `LogViewer.tsx` | List with honest state; per-app page with open, restart, stop/start, update with release notes, settings form, logs, history, credentials with reveal and copy, first-run steps, remove that keeps data by default |

Every component takes data and a `LoadState` and renders loading (skeleton plus a status line), error (the contract error code), stale (dashed banner, requests disabled) and empty states. Components never fetch; the dashboard passes API objects in.

## Token extension
The store uses only the design tokens, plus one extension in `storeTokens.ts`: **eight app-tile hues** (teal, blue, violet, green, amber, red, slate, plum; each a gradient pair). `AppTile` picks a hue from the app id and passes it as the inline custom properties `--om-store-a`, `--om-store-b` and `--om-store-fg`, so the hue values exist in one place. Tiles keep their colour in both themes, like an app icon. `logic.test.ts` checks white monogram text against both stops of every hue (≥ 4.5:1). `store.css` declares three layout values on `:root` (`--om-store-card-min`, `--om-store-rail-card`, `--om-store-lift`) and no raw colours.

Motion: hover lift, filter and job panels fade in, skeleton shimmer, progress flow, hero orbs drift. All of it stops under `prefers-reduced-motion: reduce`.

## Contract status (what the gateway serves today)
- **Contract:** `GET /v1/apps` fields, `tier`, `scan`, `links`; actions `app.install` and `app.remove`; approve and deny.
- **PROPOSED** (TAXONOMY §5 and parity audit): `category` enum, `tags`, `deploy_class`, `plugin`, `licence_class`, `placement`, `storage`, `fit`, `tagline`, `gallery`, `release_notes`; `GET /v1/apps/{id}/plan` (PD-04); lifecycle actions `app.start`, `app.stop`, `app.restart`, `app.update`, `app.configure`, `app.delete_data` (PD-03, PD-06), with executor step and percent; per-app URL behind the gateway login (PD-02); credentials sealed on the box (PD-07); logs (PD-08); settings schema (PD-09). The request disclosure marks proposed action types as such, and every CLI line is labelled "planned".

## Rules the code keeps
- Community apps are hidden by default; core apps never appear in browsing; list-only apps offer only "Get it upstream".
- Install is disabled, with the reason as the button's description, when the scan is missing, failing or older than 7 days, the tier is blocked, no node fits, the hub is stale, or a request is already in flight.
- A node with a stale report is never shown as a live fit. An installed app's state older than 30 s shows "Stale · last known running …"; older than 120 s shows "Unknown".
- Remove keeps data by default. Deleting data is a second `app.delete_data` request and needs the app name typed.
- Credentials are shown only to the owner, masked until revealed.

## Patterns studied (nothing copied)
umbrelOS (PolyForm Noncommercial 1.0.0, study only): category rail, Discover sections, install review steps, the floating progress island. No code, assets, icons, wallpapers or text were taken. Icons are drawn for OneMind (TAXONOMY §1.2 plus nine store glyphs in the same style in `CategoryIcon.tsx`). Screenshot slots without an image show a CSS illustration labelled "Illustration · not a real screenshot".
