<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind for Mac: read-only Finder location (spike, issue #705)

**What it is.** A small signed Mac app. You type your OneMind gateway address and a dev token, press
**Add OneMind to Finder**, and a **OneMind** entry appears under *Locations* in the Finder sidebar. Files
show as online-only (a cloud icon) until you open one; then the bytes come down from the gateway.
Nothing is ever written back.

**Why a spike.** Two questions decide how the native Mac sync client (#707 to #710, #714) is built:
1. Does Apple's *File Provider* framework (the same one iCloud Drive, Dropbox and OneDrive use) work
   against our gateway's real file API, inside the sandbox, with hardened runtime and Developer ID?
2. Can a shared core written in Rust (so Mac, Windows and Linux clients share one sync engine) link
   into that sandboxed extension and run there?

## Words used here
- **File Provider extension**: a separate small program inside the app that macOS starts on demand to
  answer Finder: "what is in this folder?" and "give me this file's bytes". *Replicated* means macOS
  keeps the files on disk itself (under `~/Library/CloudStorage`) and the extension only fetches.
- **Domain**: one sidebar location. The host app registers exactly one, `onemind`.
- **App group**: a shared container both the app and the extension can read; it carries the saved
  gateway address and root, and is the keychain access group for the token.
- **Hardened runtime / Developer ID**: Apple's code-signing rules for apps distributed outside the App
  Store. Notarization is Apple's malware scan on top.
- **UniFFI**: a Mozilla tool that generates Swift (and Kotlin, Python) bindings for a Rust library.

## Layout
| Path | What |
|---|---|
| `OneMind.xcodeproj` | Xcode project: targets `OneMind` (SwiftUI host app), `OneMindFileProvider` (extension), `OneMindTests` |
| `OneMind/` | The host app window: address, root, dev token; add or remove the domain |
| `FileProvider/` | The replicated extension, the folder enumerator, and the Rust-core probe |
| `Shared/` | Code both targets (and the tests) compile: config and refusals, the gateway client, item mapping, domain registration, the app-group store |
| `Tests/` | XCTest: 19 tests over the client, the refusals, the item mapping and the Rust core |
| `Config/` | Info.plists and entitlements (sandbox, app group, network client for the extension only) |
| `core-ffi/` | The tiny Rust library (`core_version`, `normalize_path`) exported with UniFFI 0.29.4 |
| `scripts/build-core-ffi.sh` | Xcode build phase: cargo, then uniffi-bindgen, then `swiftc` into the `OneMindCore` module |

## How it talks to the gateway
Only `GET`, only with `Authorization: Bearer <dev token>`:
- `GET /v1/files/list?root=&path=&limit=500`, following the `Link: rel="next"` header, and only to the
  same scheme, host and port (a link elsewhere is refused, so the token never leaves the box).
- `GET /v1/files/stat` for one item.
- `GET /v1/files/download` in 8 MiB `Range` chunks. The first answer's `ETag` goes back as `If-Range`;
  if the file changed mid-download the gateway sends it whole (200) and the client starts over. Each
  chunk moves the `Progress` that Finder shows. An empty file (416 with `bytes */0`) is handled.

**Must refuse (tested):** no token, a blank token, or plain `http://` to another machine means nothing
is saved, the domain is never added, and the extension answers *not authenticated* (Finder shows its
sign-in state). Create, modify and delete answer `NSFeatureUnsupportedError`, and no item ever offers a
write capability.

## Build and test (any Mac with Xcode 16 or later)
```bash
brew install rustup && rustup-init -y && rustup target add aarch64-apple-darwin   # x86_64-apple-darwin too for universal Release
xcodebuild test -project desktop-mac/OneMind.xcodeproj -scheme OneMind
```
Run from the repo root. The first build compiles the Rust crate (about one minute); later builds reuse it.
Without a team, everything is ad-hoc signed ("Sign to Run Locally"): fine for the tests, but the domain
cannot really be added (see the answers below).

## Result (2026-11-22, Xcode 27.2, macOS 27.2, Apple silicon)
| Question | Answer | How we know |
|---|---|---|
| Does the project build: app + embedded replicated extension + tests? | **Yes** | `xcodebuild test` exit 0; `OneMind.app/Contents/PlugIns/OneMindFileProvider.appex` present |
| Do list, Range download, progress and the refusals behave? | **Yes**, against the gateway's real contract | 19 XCTest cases pass; with the token and foreign-link guards removed, 7 fail |
| Does a Rust UniFFI library link into the sandboxed extension? | **Yes** (static library, Swift module `OneMindCore`) | extension binary carries the `uniffi_onemind_core_ffi_*` symbols; `CoreFFITests` calls Rust from Swift |
| Does it run in the extension under the sandbox on a real domain? | **UNVERIFIED** | needs a Developer ID-signed build; lab kit step 6 (Console line `rust core 0.1.0 linked`) |

**Shared-core route: viable, with three build traps (all fixed in `scripts/build-core-ffi.sh`):**
1. Xcode's exported build settings break cargo (a proc-macro crate "cannot be found"): run cargo with a
   clean environment.
2. Stripped proc-macro dylibs fail to load on this toolchain ("mis-aligned LINKEDIT string pool"):
   `core-ffi/Cargo.toml` sets `strip = false` for build-time crates.
3. Xcode does not compile Swift files written by a script phase: the script compiles the generated
   bindings into a static Swift module that the targets import. For the real client this becomes an
   XCFramework built once per release.

## Answers the issue asked to record (UNVERIFIED until the lab kit runs)
1. **Does Developer ID need a provisioning profile?** *UNVERIFIED.* Our reading of Apple's "Configuring
   app groups" and the App Sandbox entitlement docs: an app group in the macOS form `<TeamID>.<name>`
   needs no provisioning profile for Developer ID; the iOS form `group.<name>` does need the App Groups
   capability and a profile. Whether a File Provider extension needs a profile of its own is not
   settled by those pages. That is why this spike uses the macOS form.
2. **What must the app-group id look like?** `$(TeamIdentifierPrefix)com.onemindos.mac`, for example
   `ABCDE12345.com.onemindos.mac`. It is one build setting, `ONEMIND_APP_GROUP`, used by both
   entitlements files, both Info.plists (`OneMindAppGroup`) and the extension's
   `NSExtensionFileProviderDocumentGroup`, which must equal it. With ad-hoc signing the prefix is empty,
   so the group is only `com.onemindos.mac` and macOS will not honour it. *UNVERIFIED:* whether macOS 15
   or later shows the "would like to access data from other apps" prompt for this form.
3. **Can the token sit in the data-protection keychain with the app group as access group, readable by
   both processes?** *UNVERIFIED.* `Shared/AppGroupConfigStore.swift` does it that way; lab kit step 5
   shows it.

## Lab kit (the founder, on a real Mac: macOS 14 and the current macOS)
Needs: the Apple Developer account (Team ID), Xcode, Rust as above, and a OneMind box reachable over
https. Write the results in the table and paste them into the PR.

1. Get a dev token for your own person: `POST /v1/tokens` signed in as you (the gateway's API tokens,
   H-09); copy the secret once. Do not paste it anywhere but the app.
2. Build signed: `xcodebuild -project desktop-mac/OneMind.xcodeproj -scheme OneMind -configuration Release DEVELOPMENT_TEAM=<TeamID> CODE_SIGN_IDENTITY="Developer ID Application" ONLY_ACTIVE_ARCH=YES build`.
   Record whether Xcode asks for a provisioning profile (answer 1).
3. Optional: notarize with `xcrun notarytool submit` and `xcrun stapler staple`.
4. Copy `OneMind.app` to `/Applications` and open it.
5. Type the box address (`https://...`), root `shared`, the token; press **Add OneMind to Finder**.
6. Open Console.app, filter `com.onemindos.mac.fileprovider`: look for `rust core 0.1.0 linked`.
7. Finder sidebar: **OneMind** under Locations. Put a 200 MB file in Shared from the dashboard; it shows
   with a cloud icon (online-only).
8. Double-click it: Finder shows download progress, then it opens. Select another file, press Space:
   Quick Look shows it.
9. Try to drag a file into OneMind, rename one, delete one: each is refused.
10. Press **Remove from Finder**; then `ls ~/Library/CloudStorage` shows nothing for OneMind.

| Step | macOS 14 | current macOS |
|---|---|---|
| 2 profile needed? | | |
| 5 domain added | | |
| 6 Rust line in Console | | |
| 7 Locations + online-only | | |
| 8 progress + Quick Look | | |
| 9 writes refused | | |
| 10 CloudStorage empty | | |

## Not in this spike
- No change feed: new files appear when a folder is reopened (`enumerateChanges` reports nothing; the
  real client uses the sync index revision). The working set is empty, so no Recents or Tags.
- No sign-in or pairing flow: a typed dev token stands in for it.
- No CI job yet: adding one is a CI change that belongs to the CI owner, and it would need the
  self-hosted Mac runner (#299) with Rust installed.
