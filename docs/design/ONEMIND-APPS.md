<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind's own apps: architecture, engines and licences

**For:** Zeus and every builder · **Date:** 2026-11-26 · **Status:** founder-requested design review. The **Decisions for Zeus** at the end are proposals until he records them. Nothing here reopens D-003 (one app with modules), D-021 (Android first), D-023 (OneMind copies of upstream projects) or D-026 (custom apps are first-class).
**Feeds:** D-003, #641, #642, #1234 (own vs borrow), the "OneMind Everyday" app wave, founder notes [14](../learning/founder/14-onemind-internal-apps.html) and [15](../learning/founder/15-one-app-own-vs-borrow-and-3d-maps.md).

Founder brief, 2026-11-26:
- These apps are ours to improve and maintain forever, and they are one of OneMind's main moats.
- Any engine or backend we use must have a solid licence and leave room to keep adding features, the way Apple keeps improving its own apps.
- Someone using the OneMind app on Android, iOS or anywhere else gets **the full app, 100% inside the OneMind app**.
- The architecture must be right before the apps are built.

## 1. What we found (release/next, 2026-11-26)

| Check | Today | Problem for "100% inside the app" |
|---|---|---|
| Shared screen format (#641) and phone renderer (#642) | Not built | Every new app would be hand-built separately for web, Android and iOS |
| Offline store and write queue on the phone | None | Notes, Reminders or Recorder stop working without a connection |
| Phone device features | Camera, files, notifications, background tasks | No microphone, location or local database yet |
| Phone screens | Hand-built system screens only (Home, Approvals, Apps, Files, Settings, Agents...) | No app screens (Notes, Calendar...) |
| Web views of engines inside the phone app | None | Good: keep it that way for OneMind's own apps |

**Conclusion:** build the foundation (§3) first, then the apps on top of it. Without it, each app is built three times and the phone versions only half work.

## 2. Principles

1. **We own everything a person touches:** the screens, the data model, sync, permissions and approvals, the AI tools. All of it is in this repo under Apache-2.0.
2. **Engines are replaceable parts, never the product.** An engine runs behind a thin OneMind adapter. If it is swapped, no screen and no stored data has to change.
3. **The data is the person's, in open formats** (Markdown, iCalendar, vCard, PDF, Opus/M4A) and stored in Files or OneMind's own stores, never locked inside an engine.
4. **Every app is complete inside the OneMind app on every platform:** web and desktop (Tauri), Android, iOS, and the headset later.
   - It works offline for everything the person already has, and changes made offline are sent when the connection comes back.
   - It uses the device properly: camera, microphone, location, notifications, share sheet, background sync, widgets later.
   - No engine web page is ever shown for a OneMind app.
5. **AI reaches each app only through the gateway:** read tools, and request-only tools for anything that changes something, which a person approves (AI never actuates without approval).
6. **Standard protocols are an extra door, not the main experience.** CalDAV, CardDAV and WebDAV let the phone's own apps and other tools sync, but the OneMind app is the full experience.

## 3. The architecture: five layers per app

```text
 ┌ Device (web/Tauri · Android · iOS · headset) ─────────────────────────────────────┐
 │  Screens: native components (ui/ tokens), hand-built for rich apps;               │
 │           schema-driven (#641/#642) for simple lists, forms and settings          │
 │  App kit: one shared TypeScript package per app — domain logic, validation,       │
 │           local store + outbox (offline), used by web AND phone                   │
 │  Device bridge: Expo modules — camera, mic, location, SQLite, background, share   │
 └──────────────── @onemind/sdk (generated from OpenAPI) + OneMind Sync ─────────────┘
 ┌ Box ──────────────────────────────────────────────────────────────────────────────┐
 │  App module (core/onemind_core/<id>/): typed REST API, events, MCP tools,         │
 │  descriptor (signed list), backup units, switch-off via BuiltinGate               │
 │  Adapter → Engine container (only where an engine is worth it), never exposed     │
 │  Doors: CalDAV/CardDAV/WebDAV etc. for outside apps                               │
 └───────────────────────────────────────────────────────────────────────────────────┘
```

| Layer | What it is | Exists? | Who builds it |
|---|---|---|---|
| **F1 OneMind Sync** | One sync contract for every app: a changes feed with a cursor, idempotent writes, a conflict rule that keeps both copies, and the age of every cached item. The phone keeps a local SQLite store per app and an outbox. | No (new issue) | Claude (sync protocol is security-core) |
| **F2 Screen schema + web renderer** | #641: screens as typed data, with no scripts and no raw URLs | Claimed, not built | Claude |
| **F3 Phone renderer + offline cache** | #642, built on F1 | Not built | Codex, after F1 and F2 |
| **F4 Device bridge** | Add microphone, location and SQLite to the phone app as Expo modules, plus a permissions screen that explains each one | Partly | Codex |
| **F5 App kit template** | `onemind app new --builtin` makes the module, descriptor, app kit, screens and tests for a new app in one go, so every app has the same shape | No (it extends #638) | Codex |

**Which apps get hand-built screens:** Notes (editor), Calendar (day and month grids), Map, Recorder, Scanner, Approvals and Photos. Settings pages, lists and forms in every app use the schema (F2/F3), so they appear on every platform without new client code.

**iOS:** the same Expo app (D-021: Android first, then iPhone). Nothing in the design is Android-only. Native modules ship in Kotlin and Swift pairs.

## 4. Engines and licences

### The rules (proposed)

1. **Inside the app binaries (phone, desktop): only permissive licences.**
   - That means MIT, BSD, Apache-2.0, or MPL-2.0 at file level.
   - Never GPL or AGPL, because they would bind our app code and clash with App Store distribution.
2. **Engines we expect to change deeply: permissive only.**
3. **GPL or AGPL engines are allowed only if all of these hold:**
   - they run in their own container, unmodified, or with our changes published in a public fork repo;
   - they sit behind a standard protocol, so they can be swapped;
   - none of their code is copied into ours.
4. **Never depend on any of these:**
   - a non-commercial-only API;
   - a "testing only" build;
   - features locked to an enterprise or open-core edition;
   - someone else's trademark.
5. **Every engine goes in one register:** SPDX id, source, pinned version, adapter, swap plan. CI keeps it current alongside `deploy/check-pins.py`.

### Each planned app against the rules

Licences were checked from each project's own repository or terms on 2026-11-26.

| App | Plan | Engine and licence | Verdict |
|---|---|---|---|
| Notes | Our own: a Markdown folder in Files | none (Memos, MIT, as a reference only) | ✅ ours |
| Reminders | Our own, on the Work engine | none | ✅ ours |
| Calendar, Contacts | Our UI and data model; the sync door is a **Radicale** container, unmodified, storing plain `.ics`/`.vcf` files in a OneMind-owned folder | Radicale GPL-3.0 (sabre/dav is BSD-3, but a PHP library) | ✅ allowed by rule 3: the data is standard files and the engine can be swapped |
| Weather | Our card and an on-box proxy | **Open-Meteo's free API is non-commercial only** ✗; MET Norway is CC BY 4.0, but commercial use is UNVERIFIED | ⚠️ decision: MET Norway once its terms are checked, or a paid source |
| Translate | Our own small service on **Argos Translate** | Argos MIT ✅ (LibreTranslate, which wraps it, is AGPL); model licences UNVERIFIED | ✅ go with Argos, skip LibreTranslate |
| Recorder | Our own; transcription later with **whisper.cpp** | whisper.cpp MIT ✅; model licences UNVERIFIED | ✅ |
| Scanner | Our own edge detection and PDF; text recognition later with **Tesseract** | Tesseract Apache-2.0 ✅ | ✅ |
| Map | Our screen on **MapLibre** + **PMTiles**, with **CesiumJS** for outdoor 3D later | BSD-3, BSD-2, BSD-3, Apache-2.0 ✅; OpenStreetMap data is ODbL (attribution) | ✅ (never use Cesium ion) |
| Find My Devices | Our own | none | ✅ |
| Passwords (#994) | Was planned on **Vaultwarden** | Vaultwarden AGPL-3.0 + the risk of using Bitwarden's name; Bitwarden clients are GPL-3.0 plus proprietary folders | ⚠️ decision: rethink before building |
| Documents | Was planned on **Collabora CODE** | MPL-2.0, but CODE is "not recommended for production" and the supported edition is paid | ⚠️ decision |
| Music, Podcasts, Books, TV | Our screens over Navidrome, Audiobookshelf, Calibre-Web or Komga, Jellyfin, through their standard APIs (Subsonic, Jellyfin API) | GPL-3.0 / GPL-3.0 / GPL-3.0 or MIT / GPL-2.0 | ✅ by rule 3 (Komga is MIT) |
| Mail | later | Stalwart AGPL-3.0 + an enterprise tier | later |
| OpenVitals | stays out of this wave (founder) | five unrelated repos share the name: which one is meant is UNVERIFIED | name the repo before depending on it |

## 5. One repo or several: one repo (confirmed), with one exception

**All of OneMind's own code stays in this monorepo:** the box modules, the shared app kits, the dashboard, the phone app, the desktop app and the SDK.
- **One contract:** OpenAPI generates `@onemind/sdk` for every client in the same commit as the API change (CI-16). Separate repos would drift.
- **Atomic changes:** a feature that touches the box, the web and the phone lands in one PR with its tests.
- **One CI and one release train:** built-ins ship with the OS (`update: os`), signed together.

**The exception:** if we ever fork an engine, the fork lives in **its own repo** under the onemindos org.
- **Licence boundary:** GPL or AGPL code never sits in an Apache-2.0 tree.
- **Upstreaming:** our fixes can go back to the original project.
- **How it ships:** CI builds the fork into a signed, pinned image, and only the adapter lives in this repo.

**Proposed layout addition:** shared app kits under `clients/<id>/` (TypeScript, no UI). The dashboard and the phone both import them, the same way they import `@onemind/sdk` today.

## 6. How we keep improving the apps (the "Apple pipeline")

- **One spec per app:** `docs/apps/<id>/SPEC.md` says what it does, its roadmap, its engine and licence, its data model and its AI tools. Issues carry an `app:<id>` label.
- **One release train:** built-ins improve with each OS release. Beta features sit behind a per-app flag in Settings ("Try new features").
- **Quality gates on every PR:**
  - the conformance tests (`test_builtin_conformance.py`);
  - screenshot tests per platform;
  - an emulator launch test of the release APK, which would have caught the 2026-11 crash;
  - and, on hardware, the `android-live-test` steps.
- **Feedback without tracking:** "Report a problem" (#842) and the founder's own daily use. There is no analytics.
- **New apps start from the template (F5),** so every app gets the same sync, permissions, backup and AI wiring for free.

## 7. Order

1. **Foundation:** F1 OneMind Sync, then F2 (#641), then F3 (#642) and F4 (device bridge), then F5 (template).
2. **Proof app: Reminders.** It is the smallest app, and it exercises sync, offline, notifications and AI tools end to end on web and Android.
3. **The Everyday wave for Codex, one PR at a time:** Find My Devices, Map, Weather, Scanner, Recorder, Translate, Notes. Calendar and Contacts come after the sign-in door (#994).
4. Media screens and Whiteboard.

## 8. Decisions for Zeus

1. Adopt the **five-layer architecture** and build the **foundation before the apps** (§3, §7).
2. Adopt the **engine licence rules** (§4): permissive only in app binaries; GPL/AGPL only unmodified, in their own container, behind a standard protocol.
3. **One repo** for everything we write; engine forks in their own repos (§5).
4. **Weather source:** MET Norway (after checking its commercial terms), a paid source, or self-hosted Open-Meteo. The Open-Meteo free API is out (non-commercial only).
5. **Passwords:** keep Vaultwarden behind a door (AGPL plus trademark care), or build our own vault.
6. **Documents:** pay for Collabora, pick another engine, or wait.
7. **Reminders** as the proof app.
8. **Theme name** for the set, for example "OneMind Everyday".
