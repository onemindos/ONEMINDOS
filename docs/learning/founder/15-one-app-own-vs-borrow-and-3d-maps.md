<!-- SPDX-License-Identifier: Apache-2.0 -->
# Founder note 15: one app on every device, own vs borrow, and the 3D map

**For:** Zeus · **Date:** 2026-11-26
**Status:** founder-requested learning entry ("this is key, make sure to document this"). It builds on **D-003** (one unified OneMind app with modules) and **D-023** (OneMind-built on-box copies of upstream projects) and changes neither. The "own vs borrow" rules and the 3D split below are **recommendations waiting on Zeus**, tracked as issues, not decisions.
**Feeds:** D-003, D-026 (custom apps first-class), #641 (typed screen schema + web renderer), #642 (phone renderer + offline cache), #653 / #656 (Map screens), #606 (live assets), founder note [14](14-onemind-internal-apps.html) (the app inventory).

Zeus asked three questions about OneMind's own apps, which are one of the main reasons people will want OneMind:

1. Build every app with our own code, or use open-source projects as the backend?
2. For the 3D map, with TAK Server coming: three.js or Cesium?
3. One OneMind app on every device, or separate apps?

The answers, most important first.

---

## 1. One app on every device (the key piece)

**Already decided: one OneMind app with modules (D-003).** Not a separate app per feature, and not a separate app per platform per feature. The real question is how one app keeps up with 40+ modules on every platform without a team per platform. Three layers:

### Layer 1: one shell per platform, owned by OneMind

| Shell | Runs on |
|---|---|
| Web desktop (the dashboard) | Any browser; Mac and Windows through the desktop app (`desktop/`, Tauri) |
| Phone app (`mobile/`, Expo) | Android first (D-021), then iPhone |
| Headset app | Quest (the XR wave) |

Each shell does the same five jobs: **sign-in, the tabs, notifications, approvals with passkeys, and offline caching.** It knows nothing about any one module.

### Layer 2: server-driven module screens (this is what makes one app possible)

- A module describes its screens **as data**, not code: lists, cards, details, forms, stats, timelines, map layers, actions. That is the typed screen schema in **#641**.
- The box sends those screens; each device draws them **in its own native style** with one renderer: the web renderer (#641) and the phone renderer with an offline read-cache and write queue (**#642**).
- The schema has **no script and no raw URL fields**, so a module cannot run its own code on your phone. Data comes only through the module's declared tools, through the gateway.
- **Adding or updating a module needs no new app release on any platform.** Install the module on the box and it appears on every device that same minute.

"Server-driven UI" just means this: the server decides what the screen shows, the app decides how it looks.

### Layer 3: hand-built native screens only where it matters

Four places get hand-built screens on each platform because they need the device itself (camera, passkey, maps, file system) or are safety-critical:

- **Approvals** (hold to approve, passkey signing; AI never actuates without a person).
- **Map** (MapLibre on web and phone).
- **Photos and camera.**
- **Files.**

Everything else uses the shared screen format.

### Engine apps with their own web interface

Some apps come with a full interface of their own, for example an office editor or Home Assistant. These open **in a window (desktop) or an in-app web view (phone)**, signed in through OneMind with a short-lived token. The person never leaves the OneMind app and never signs in twice.

### The payoff

OneMind maintains **about 3 shells and 2 renderers (web and phone)**, not 40 modules × 4 platforms. And every module reaches **AI agents the same way people do: through the gateway** (`/mcp` tools, request-only for anything that changes things, a person approves).

```text
 Module on the box ──screens as data──▶ gateway ──▶ web renderer  (browser, Mac, Windows)
   (onemind.app.yaml,                          ├──▶ phone renderer (Android, iPhone)
    declared tools)                            ├──▶ headset shell (Quest)
                                               └──▶ /mcp tools    (AI agents, request-only)
```

### What builds it

1. **#641** typed screen schema + web renderer (move Work v0 onto it as the first proof).
2. **#642** phone renderer with offline cache and replay queue.
3. Move each new module onto the schema as it is built, instead of writing app-specific React.

Without #641 and #642, every new module means hand-built screens on every platform. That is the road to "one app per feature".

---

## 2. Own code or open-source backends? Own the experience, borrow the engine

OneMind owns **the screens, the data model, identity, permissions and approvals, and how apps reach AI.** Where a strong open-source project already does the hard, specialised work, it runs **underneath as a sandboxed service** behind the gateway. OneMind already works this way:

- Photos is OneMind's own viewer; Immich stays an optional Market app.
- D-023: OpenVitals becomes a OneMind copy with the cloud parts removed.
- The Offline Maps app runs `go-pmtiles` as its engine.
- Video goes through MediaMTX (#662).

**Build it ourselves when:**
- it is the **trust core**: Approvals, Files, identity, Settings, Updates. These are the product; nobody else's code decides who can do what;
- the app is **thin over plain files**: Notes (a Markdown folder), Work and tasks, Tips, Dashboards. An outside engine would add more upkeep than it saves;
- the open-source option **sends data off the box or can't run offline** (the D-023 rule).

**Use an open-source engine when** the hard part is deep, specialised work a large community maintains:

| App | Engine underneath (examples, not chosen) | What OneMind adds |
|---|---|---|
| Video and cameras | MediaMTX (chosen, #662), Frigate | Screens, approvals, gateway tokens, the Map |
| Documents | An office suite such as Collabora | The window, saving into Files, versions |
| Offline knowledge | Kiwix, Kolibri | Search, the Market bundle |
| Maps | MapLibre, PMTiles | The Map screen, live assets |
| Backups, sign-in | restic, Kanidm | All the screens and policies |
| Translate, local AI | A local model runtime | Prompts, limits, approvals |

**Rules that keep upkeep low:**
1. **One thin adapter per engine.** Screens talk to OneMind's SDK, never to the engine. An engine can be swapped without rewriting a screen.
2. **Engines run in their own containers.** That keeps GPL engines (TAK Server, OpenTAKServer) legally separate from OneMind's Apache-2.0 code. Never copy their code into ours.
3. **Pick healthy engines:** active project, no cloud dependency, pinned version, scanned by the same app gate Market apps pass.
4. **Data lives in Files or OneMind's own stores,** not locked inside the engine, so switching engines never loses anyone's data.

**Why this scales:** rebuilding video, an office suite or an offline library ourselves would sink a small team. Owning the screens and adapters keeps the cost near one screen set plus one adapter per app, and the screen set comes almost free once #641/#642 exist.

**Waiting on Zeus:** record these rules as a decision so builders stop choosing case by case (#1234).

---

## 3. The 3D map: three.js or Cesium? Both, each for its own job

| Job | Engine | Why |
|---|---|---|
| Everyday 2D map, desktop and phone | **MapLibre** (in use) | Fast, offline with PMTiles, has a phone version |
| **Outdoor 3D:** globe, terrain, buildings, TAK tracks, drones later | **CesiumJS** (recommended) | Built for real-world geography: a true globe, terrain, the 3D Tiles format, time playback. Apache-2.0 |
| **Indoor 3D:** rooms, racks, the greenhouse twin, the headset view | **three.js** (in use: `dashboard/src/screens/spatial/`) | Lighter; better for small built spaces and XR |

**Why not one engine for everything:** three.js alone means building a globe, terrain and Earth coordinates yourself; Cesium alone is heavy for an indoor plan and weak on phones and headsets.

**How TAK fits:** TAK Server speaks **CoT** (Cursor on Target) messages. The research already plans a bridge from CoT into NATS (`tak.cot.inject`, [`research-output/09-iot-mesh-offgrid-tak.md`](../../../research-output/09-iot-mesh-offgrid-tak.md)). From there TAK positions join OneMind's live asset stream (#606) like any other asset, so **MapLibre, Cesium and three.js all draw the same assets.** The 3D engine choice does not change the TAK connection.

**Caveats (why this is not a decision yet):**
- **Cesium's cloud service (Cesium ion) must not be a dependency.** Terrain and 3D buildings would be hosted on the box, like our PMTiles map packs: an offline terrain pack is extra work.
- **"TAK connects to Cesium" is UNVERIFIED.** Which TAK tools use Cesium has not been checked against primary sources. Cesium's size in the dashboard bundle is also unmeasured.
- A short sourced check (#1235) settles these before the choice is recorded.

---

## Words you need

- **Shell:** the part of an app that is always there (sign-in, tabs, notifications), into which modules plug.
- **Module:** one feature area (Photos, Work, Cameras) packaged as a Market app with `onemind.app.yaml`.
- **Server-driven UI / screen schema:** screens sent as data from the box and drawn by the device.
- **Renderer:** the code on each device that turns screen data into real buttons and lists.
- **Engine / backend:** the open-source program doing the heavy work underneath an app.
- **Adapter:** the thin piece of OneMind code between an engine and the gateway.
- **CoT:** Cursor on Target, the XML message format TAK uses for positions and events.

## Check yourself

1. Why does adding a module not need a new phone app release?
2. Which four kinds of screen are still hand-built, and why?
3. Why do GPL engines run in their own container?
4. Why does choosing Cesium not change how TAK connects to OneMind?
