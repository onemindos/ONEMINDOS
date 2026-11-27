<!-- SPDX-License-Identifier: Apache-2.0 -->
# Spike 2: the Notes editor on phones (D-032)

**Question:** how does OneMind Notes (later Docs) edit rich text inside the React Native app, offline, with two people editing one note and a CRDT merge (a data type whose copies can be edited separately and always merge, losing nothing)?
**Answer in one line:** a bundled offline web editor (ProseMirror) inside one `react-native-webview`, bound to a Yjs document that the app stores and merges. Not yet proven on a phone: see "Not run".

## Comparison (licences read from each project's own repository LICENSE file, 2026-11-27)

| Option | Licence (SPDX) | Source | Maintenance (npm `modified`) | RN 0.88 / Expo 58 fit | Verdict |
|---|---|---|---|---|---|
| **(a) ProseMirror in a WebView** (prosemirror-* + y-prosemirror) | MIT | https://github.com/ProseMirror (core moved to https://code.haverbeke.berlin/prosemirror); https://github.com/yjs/y-prosemirror | prosemirror-model 2026-11-08; y-prosemirror 1.3.7, 2025-07 (stable, quiet) | Runs on web, Android and iOS unchanged: same editor as the dashboard could use. The only native part is react-native-webview | **Chosen.** Our code, no network page, full schema control (checklists, later tables, comments) |
| (a2) TipTap (@tiptap/core, ProseMirror under it) | MIT (core) https://github.com/ueberdosis/tiptap/blob/main/LICENSE.md | same | 3.35.0, 2026-11-20 | Same as (a). Some TipTap extensions and the cloud are paid or not open | Fine later; (a) needs fewer layers. Use only MIT packages |
| (a3) 10tap-editor (TipTap in a WebView, RN wrapper) | MIT https://github.com/10play/10Tap-Editor | same | 1.1.0, 2026-10-19 | Peer dep react-native-webview `*`. Pulls ~20 TipTap packages and lodash | A shortcut, but hides the WebView bridge we want to own |
| (b) `TextInput` + Markdown preview (e.g. @expensify/react-native-live-markdown) | MIT https://github.com/Expensify/react-native-live-markdown | same | 0.1.374, 2026-11-19 | Native module, needs a dev build and the new architecture; styles Markdown source live | Good for plain-Markdown notes. No real lists, checkboxes or formatting toolbar; merge works on the Markdown text only |
| (c) react-native-enriched (native rich text) | MIT https://github.com/software-mansion/react-native-enriched | same | 0.8.1, 2026-06-16 | Native on both platforms, but 0.x, and it has no Yjs binding: we would write the document <-> CRDT mapping ourselves | Watch it. Not a base for CRDT editing today |

| Merge library | Licence | Source | Size | React Native |
|---|---|---|---|---|
| **Yjs 13.6.33** | MIT https://github.com/yjs/yjs | | 29 KiB gzip alone; **ProseMirror + y-prosemirror + Yjs = 332 KB minified, 107 KB gzip** (esbuild, measured). Pure JS | Works, with one trap (below) |
| Automerge 3.5.0 | MIT https://github.com/automerge/automerge | | wasm file is 3.6 MB (measured, `automerge_wasm_bg.wasm`) | Needs wasm in Hermes and a bundler setup. Its ProseMirror binding is a separate project. Not tried |

**Why Yjs:** small, pure JS, and y-prosemirror already maps a ProseMirror document to a Yjs tree. Automerge is not worse as a CRDT; it costs more here (3.6 MB wasm, no binding we tried).

## Findings (what the build showed)
1. **Trap: lib0 (Yjs's helper) breaks under Metro.** lib0's `react-native` export condition requires `isomorphic-webcrypto/src/react-native`, which is not installed (its last release is 2022 and it needs the removed `expo-random`). Jest fails with "Cannot find module", and Metro would fail the same way. Fix in this spike: `src/spikes/notes/webcryptoShim.js` answers that import with `expo-crypto`'s random bytes, wired in `metro.config.js` and the Jest mapper. **Metro bundling itself was not run here** (no Android SDK): the Jest mapper is proven, the Metro rule is not.
2. **Merge behaves.** Two devices edited offline (new blocks, typing in one paragraph, bold, ticking a task) and merged in either order: every edit is kept and both copies end identical.
3. **Formatting at the edge of a run is a toss-up.** Text typed next to a bold or italic run may take that format; which side wins depends on random client ids. No text is lost. Product decision later (Yjs `format` options).
4. **The bundled editor runs.** The built bundle was loaded in jsdom (a simulated browser, not a phone): it mounts, the task and tick commands change the Yjs tree in the same shape `noteDoc.ts` reads, and an update from the app side shows up in the page. Throwaway check, not committed.
5. **react-native-webview types** need `<WebView<object>>` with TypeScript 6 (the default generic is `undefined`, which makes the props `never`).

## What is in the patch
- `src/spikes/notes/noteDoc.ts` (+ test): the note as a Yjs doc, add block, Markdown export, save and load, two-way sync.
- `webEditor.entry.js`: runs in the WebView (schema: paragraph, heading, bold, italic, bullet list, checklist with a tick, undo and redo). `scripts/build-notes-editor.mjs` bundles it with esbuild into a git-ignored file. `npm start/android/ios` run that first.
- `editorHtml.ts`: the page, with a Content-Security-Policy that allows no network request at all.
- `NotesEditorSpike.tsx`: the screen: editor, "Saved on this phone", a Markdown view, and the two-device merge demo.
- `src/spikes/flag.ts`: the screen exists only in a dev build or with `EXPO_PUBLIC_ONEMIND_SPIKES=1`.

Dependencies added (all MIT, none GPL/AGPL): react-native-webview 14.0.1 (Expo 58's pinned version) and yjs 13.6.33 + its lib0 0.2.120 ship in the app. The prosemirror-*, y-prosemirror, y-protocols, lib0 and esbuild packages are devDependencies, used only to build the editor bundle, which then ships inside the app (so their MIT code does ship as part of that bundle). Full list and URLs are in SUMMARY.md.

## How to open the spike on the S24 Ultra
Needs a dev build (react-native-webview is a native module, so Expo Go is not enough here; UNVERIFIED for Expo Go).
1. `cd mobile && npm ci && make -C ../sdk gen-code` (the SDK code is generated, once per clone).
2. USB debugging on, phone connected: `npm run android` (builds the editor bundle first, then installs a dev build). Later runs: `npm start`.
3. Sign in to your box as usual (the app needs a connection to start).
4. Open the **Me** tab. Near the bottom, tap **Notes editor (spike)**. Or run `adb shell am start -a android.intent.action.VIEW -d "onemind://spikes/notes-editor"`.
5. Try: type; tap B, I, H1, H2, bullet, the checkbox button, Tick; turn on airplane mode, edit, close and reopen the app (the note is still there). Then tap **Start device B (copy)**, **B edits offline** (adds a bold-numbered task), keep typing in the editor, then **Merge B and A**: both edits must appear in the Markdown view.
6. A release build shows the entry only if built with `EXPO_PUBLIC_ONEMIND_SPIKES=1`.

## Not run (honest list)
- Nothing ran on a phone, an emulator or iOS. Typing, the keyboard, selection handles, the toolbar's touch size, scrolling inside the WebView and memory are unmeasured. The founder's S24 run is the real test.
- Metro bundling and `expo run:android` were not run. The injected-script bridge (`injectJavaScript`) and `onShouldStartLoadWithRequest` blocking are written from the library docs, untested on a device.
- The on-device file store (`expo-file-system`) is untested; tests use an in-memory store.
- Not built: sync with the box (that is spike 1 / F1), two real people, comments, images, tables, IME composition behaviour (Samsung keyboard) under a WebView.

## Recommendation
Go with (a): ProseMirror in one bundled WebView + Yjs, as the Notes and Docs editor, conditional on the S24 run showing acceptable typing and keyboard behaviour. Keep note data as a Yjs update log on the box (via OneMind Sync) with Markdown as the export. Keep (b) as the fallback for a plain-Markdown mode, and re-check react-native-enriched once it is 1.0 and has a CRDT story. Decide the lib0 shim as a permanent patch or a Yjs fix upstream.
