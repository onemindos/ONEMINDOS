<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind's own apps: architecture, engines and licences

**For:** Zeus and every builder · **Date:** 2026-11-26 · **Status:** founder-requested design review, **accepted as D-035 on 2026-11-26** ("lets do it"). §8 lists what is still open. Nothing here reopens D-003 (one app with modules), D-021 (Android first), D-023 (OneMind copies of upstream projects) or D-026 (custom apps are first-class).
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

### Measured on a Samsung S24 Ultra, 2026-11-26 (release build 957, throwaway box over USB)

| Test | Result | What it means |
|---|---|---|
| Cold start to first screen | 135–199 ms (3 runs) | Fast; the framework is not the problem |
| Smoothness while switching tabs and scrolling | 1,550 frames, 1.6% janky, typical frame 9 ms, 95% of frames at or under 18 ms | Smooth. Long lists (10,000 items) are not proven yet (spike 3). |
| Memory | about 270 MB (PSS) | Normal for a React Native app; watch it as apps are added |
| Box unreachable, then app opened | **Home is blank:** no cached data, and the box name is gone. A raw `java.net.ConnectException` message is shown. Approvals correctly refuses to approve or deny. | **Confirms the offline gap.** F1 must cache every read with its age and show plain words, not exceptions. |
| iOS (iPhone 18 Pro Max simulator, iOS 27.2, release build) | Builds (`expo prebuild` + CocoaPods 1.17 + `xcodebuild`), opens, connects to the box and shows the same live Atlas home | **The iOS path works today.** One fix: it asks for notification permission at first launch, and should ask only when needed (#1290). |

## 2. Principles

1. **We own everything a person touches:** the screens, the data model, sync, permissions and approvals, the AI tools. All of it is in this repo under Apache-2.0.
2. **Engines are replaceable parts, never the product.** An engine runs behind a thin OneMind adapter. If it is swapped, no screen and no stored data has to change.
3. **The data is the person's, in open formats** (Markdown, iCalendar, vCard, PDF, Opus/M4A) and stored in Files or OneMind's own stores, never locked inside an engine.
4. **Every app is complete inside the OneMind app on every platform:** web and desktop (Tauri), Android, iOS, and the headset later.
   - It works offline for everything the person already has, and changes made offline are sent when the connection comes back.
   - It uses the device properly: camera, microphone, location, notifications, share sheet, background sync, widgets later.
   - No engine web page is ever shown for a OneMind app.
5. **AI reaches each app only through the gateway:** read tools, and request-only tools for anything that changes something, which a person approves (AI never actuates without approval).
6. **Every app is API, CLI and MCP native** (founder, "period"). Each app ships, in the same PR:
   - a typed REST API in the public OpenAPI, which also generates the SDK;
   - an `onemind <app>` CLI group;
   - MCP tools: reads, plus request-only tools for changes.

   A feature that only has a screen is not done.
7. **Standard protocols are an extra door, not the main experience.** CalDAV, CardDAV and WebDAV let the phone's own apps and other tools sync, but the OneMind app is the full experience.

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
| **F5 App kit template** | `onemind app new --builtin` makes, in one go:<br>• the module and descriptor<br>• the API routes and the `onemind <app>` CLI group<br>• the MCP tools (read and request-only)<br>• the app kit, screens and tests<br>so every app has the same shape | No (it extends #638) | Codex |

**Which apps get hand-built screens:** Notes (editor), Calendar (day and month grids), Map, Recorder, Scanner, Approvals and Photos. Settings pages, lists and forms in every app use the schema (F2/F3), so they appear on every platform without new client code.

**iOS:** the same Expo app (D-021: Android first, then iPhone). Nothing in the design is Android-only. Native modules ship in Kotlin and Swift pairs.

## 3a. Technology choices: what could limit us, and what we do instead

Founder, 2026-11-26: "I don't want to build on top of something that will limit us."

**Keep:** React Native with Expo on phones, React on web and desktop (Tauri), and the Python gateway on the box.
- **Why not fully native (Swift and Kotlin separately):** it doubles every app. Expo modules already let us write native Swift or Kotlin wherever it matters (we ship three).
- **Why not Flutter:** it would throw away the shared TypeScript: the SDK, the dashboard, the design tokens and the app kits.

The real limits are in our own architecture, so these are the rules:

| Risk | Rule |
|---|---|
| Data that lives only on the server | **Local-first:** each app's data lives on the device (SQLite) and syncs. This is the most important choice. |
| A sync engine we don't own (paid tiers, tied to one database) | **Our own small, documented sync protocol (F1):** a changes feed with a cursor, an outbox, idempotency keys, and conflicts kept as copies. Libraries under it must be small, permissive and swappable. |
| Screens built only from server data | The screen schema (#641/#642) is for simple screens only. Rich apps get native screens. The schema speeds us up; it is never a ceiling. |
| App logic tied to one screen or platform | One shared TypeScript **app kit** per app (`clients/<id>/`) for web, Android and iOS |
| The framework can't reach the device | Expo native modules (Kotlin and Swift) through the device bridge (F4) |
| An app outgrows the gateway | Each app module owns its tables, events and API. It can move into its own service later without any client change. |
| The API, CLI and AI tools drift apart | One declaration per operation generates the OpenAPI spec, the MCP tools (`surfaces/core.py` already does this) **and the CLI**. |

**Two specialised areas:**
- **Content several people edit (Notes, Docs, Whiteboard):** a **CRDT** (edits from everyone merge automatically, nothing is lost), with **Yjs** or **Automerge**. They are expected to be MIT; confirm from their own licence files before use (UNVERIFIED here). Plain records (Reminders, Calendar, Contacts) use F1's record sync.
- **The rich-text editor:** native rich-text editing is weak in React Native. The likely answer is **our own editor, bundled offline in the app and drawn with web technology inside one component**. That is our code with no network page, so it keeps "100% inside the app". The editor spike decides.

**Spikes before the app wave** (days each, results recorded here), then **Reminders** built fully on the result:
1. **Sync:** F1 plus SQLite on the S24. Airplane mode, edits on two devices, reconnect: nothing lost or doubled.
2. **Editor:** a Notes editor on Android and iOS, offline, with two editors merging through the CRDT.
3. **Speed:** a list of 10,000 items and the map scroll smoothly on the S24.

## 3b. Sync: use what the OS already has, add only the phone layer

Founder, 2026-11-26: "sync is a massive thing for us … see if Debian has something native." Rule from now on: **check for a Debian package or a Linux feature first, and build only what is missing.**

Debian 13 (trixie) packages checked 2026-11-26 on packages.debian.org:
- `nats-server` 2.10.27, `syncthing` 1.29.5, `radicale` 3.5.3, `restic` 0.18.0, `sqlite3` 3.46.1, `samba` 4.22, `rclone` 1.60.1, `unison` 2.53, `libreoffice-core` 25.2.3, `tesseract-ocr` 5.5.0;
- `whisper.cpp`: the page did not show a package, so UNVERIFIED.

**Four kinds of sync, one design:**

| Between | Use | Native? | Why |
|---|---|---|---|
| **Machine and machine** (hub, workers, leaf nodes) | **NATS JetStream**, already the bus (D-029, FABRIC.md): streams and KV with revisions and watch, and leaf store-and-forward (lab: 600/600 delivered after an outage) | ✅ `nats-server` in Debian, already chosen | Nothing new to build |
| **Box and the OneMind app** (phone, tablet, laptop, headset) | **OneMind Sync (F1):**<br>• each app's change log on the box is kept in JetStream (or the app's own tables)<br>• the gateway serves a changes feed with a cursor, over HTTPS and websocket<br>• the device keeps SQLite plus an outbox; writes use idempotency keys; conflicts are kept as copies | Built on JetStream and SQLite. Only the gateway feed and the client kit are new. | The gateway decides who sees what (D-029). Phones do not join NATS in 1.0. Because the feed is plain, the transport can move to NATS later (the D-029 auth callout) without touching apps. |
| **Files** (folders on computers) | Files on the box. **Samba** (D-017) and WebDAV for computers, **Syncthing** for whole folders on computers. The phone gets Files through OneMind Sync, downloading on demand. | ✅ samba, syncthing | Proven tools, no custom file sync |
| **Content several people edit** (Notes, Docs, Whiteboard) | **CRDT** updates (Yjs or Automerge) carried by OneMind Sync and stored in the app's log | Library (licence to confirm) | Edits merge, none are lost |

**Calendar and Contacts** also get the standard CalDAV/CardDAV door through **Radicale** (a Debian package), so the phone's own calendar app syncs too. The OneMind app reads the same store.

**Why this lasts:**
- Machines use the bus we already run, devices get one plain protocol we own, files use tools Linux has had for years, and shared editing uses an open format.
- Every layer can be swapped without changing any app's screens or data.

### Spike results

**Spike 3: long lists. Measured on the S24 Ultra, 2026-11-26** (release build 959, 10,000 rows, 24 hard flings each way):

| | Frames | Janky | Median | 95% | 99% | Slow UI-thread frames |
|---|---|---|---|---|---|---|
| **FlashList 2.3.2** (MIT, the version Expo 58 pins) | 566 | **0.18%** | 5 ms | **9 ms** | 13 ms | **0** |
| FlatList (React Native's built-in list) | 580 | 1.55% | 6 ms | 18 ms | 29 ms | 7 |

- **Live search** over 10,000 rows ("receipt 1"): 139 matches. 4 of 27 frames were janky, during the keyboard animation; the slowest was 22 ms, and no frame was slow on the app's main thread.
- **Decision: FlashList for every long list** (Reminders, Notes, Files). Real lists filter in SQLite (F1), not in JavaScript.
- **Agent run:** Managed Agent, Sonnet builder, $0.30. Branch `spike/long-list`, not for merge as is (dev-only screen; the lock file needs regenerating with the repo's npm).

**Spike 2: the Notes editor. Measured on the S24 Ultra, 2026-11-26** (release build 960; ProseMirror in one bundled offline web view, plus Yjs):
- **Opens and runs** with no crash and no network page. Headings, checklists and bold all render.
- **Typing with the real Samsung keyboard works.** 10 words: 52 frames, median 9 ms, 95% at or under 18 ms, no slow UI-thread frames; the 4 janky frames came during the keyboard animation. Memory is about 275 MB, the same as without the editor.
- **The offline merge works:**
  - device A typed "and_A_offline", and a copy (device B) added a bold line while offline;
  - after merging, **both edits were kept** and both copies were identical;
  - it saved on the phone (490 bytes) and exported clean Markdown (the open format).
- **Size:** 107 KB compressed for the editor and merge code (Automerge would be 3.6 MB).
- **Decision: ProseMirror in one bundled web view, plus Yjs, for Notes** (and later Docs and Whiteboard). Markdown stays the export, with a plain-text mode as the fallback.
- **Before it ships:**
  - the Yjs and React Native crypto shim must be proven in the Metro build (it worked in this build);
  - the editor must ask for no network;
  - iOS needs the same test.
- **Agent run:** Managed Agent, Sonnet builder, $0.99. Branch `spike/notes-editor`.

**Spike 1: OneMind Sync (F1). Result 2026-11-26** (Managed Agent, Opus builder-secure, $7.84; draft PR #1299):
- **The approach works:**
  - one plain HTTPS/JSON feed with a cursor, idempotency keys and keep-both conflict copies, specified in `docs/design/SYNC.md`;
  - one append-only change log on the box;
  - a client kit (`clients/sync/`) with an outbox and SQLite storage.
- **Agent evidence (SQLite and PostgreSQL 16):**
  - 7 sync tests pass; the route matrix is 4115 passed, 0 failed;
  - every deliberate bug (4 on the box, 5 in the kit) is caught by a test;
  - end to end against a real gateway: two devices keep both conflicting copies, a replayed key is applied once, another person sees nothing, 100 queued reminders all arrive;
  - a 15 s outage: 11/11 changes delivered exactly once;
  - first sync 63 ms, 100 queued reminders 108 ms.
- **Gate re-check on the Mac:** 38 + 121 tests pass, kit Jest 7/7, `tsc` clean, hygiene clean. No new dependencies.
- **Left before F1 ships:**
  - run it on the S24 and iOS with expo-sqlite (#1290);
  - check that Metro accepts the kit's `.ts` imports;
  - Reminders API, CLI and MCP tools, and screens (D-035).

**Spend on all three spikes:** $9.13 (the ledger total is $11.34 of $200, including earlier runs).

## 4. Engines and licences

### The rules (proposed)

1. **Inside the app binaries (phone, desktop): only permissive licences.**
   - Public-domain and CC0 code (for example SQLite) counts as permissive.
   - The phone's own system frameworks (Android `android.*`, Apple frameworks) are part of the OS and allowed.
   - **No bundled closed-source SDKs, Google Play Services included:** OneMind must work on phones without Google. Location uses Android's `LocationManager` and Apple's CoreLocation (#1290); push uses UnifiedPush.
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
| Documents | **Founder proposal: LibreOffice.**<br>• Our own native editor, so documents are complete on every phone.<br>• **LibreOffice in headless mode** (no window) on the box opens, saves and converts Word, Excel, PowerPoint and ODF files, and exports PDF.<br>• Full desktop LibreOffice streamed from the box (#785) for heavy spreadsheets and slides.<br>Collabora is not needed. | LibreOffice/core ships `COPYING` (GPL-3.0), `COPYING.LGPL` and `COPYING.MPL` (MPL-2.0), checked 2026-11-26 | ✅ allowed by rule 3: unmodified, its own container on the box, never inside the phone or desktop app |
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

## 8. App names

Founder idea: one family name, as in **One Weather, One Doc, One Health, One Scanner, One Map, One Finder, One Reminder, One Translate, One Note.**
- **For:** it reads as one family, matches "OneMind", and is easy to market.
- **Against:**
  - **"OneNote" is Microsoft's product name.** "One Note" is too close to use.
  - **"Finder"** is Apple's file manager, and **"One Health"** is a widely used public-health term.
  - The rest need a trademark check before we commit (UNVERIFIED).
- **Recommendation:**
  - Inside the app, plain names, the way Apple does it: Notes, Maps, Weather.
  - Outside, the family name **"OneMind ___"** (OneMind Notes, OneMind Maps). It carries the brand without clashing.
  - If the "One ___" style is kept, swap the clashes, for example One Notes → **One Pages** or **One Journal**, and One Finder → **One Find**, and check every name first.

## 9. Still open (D-035 records the rest)

1. **Weather source:** MET Norway (after checking its commercial terms), a paid source, or self-hosted Open-Meteo. The Open-Meteo free API is out (non-commercial only).
2. **Passwords:** keep Vaultwarden behind a door (AGPL plus trademark care), or build our own vault.
3. **Documents:** LibreOffice as proposed (its licences fit rule 3; it runs only on the box).
4. **App names** (§8).
