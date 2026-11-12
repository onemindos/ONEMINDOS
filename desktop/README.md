<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind desktop client

A small menu-bar app (macOS) and tray app (Windows) for your OneMind box. It finds the box on your network, pairs with it, shows whether everything is fine, tells you when something waits for your approval, and opens the dashboard and the box's files.

This is the **CLIENT-8 skeleton** from the clients plan (`docs/umbrel2/clients.md` on the `u2docs` branch, §4.2 and §5). It is built with **Tauri 2**, the stack that study chose: one codebase for Mac, Windows and later Linux, a small download, and a permissive licence.

> **Does umbrelOS have a desktop app?** Yes. It has a small Mac menu-bar app and a Windows tray app. They find the box, sign in, mount its shared folders and open its web page. The "desktop" look in umbrelOS screenshots (wallpaper, dock, app grid) is its **web page**, not a native app. (Described from the clients study; no umbrelOS code, text or assets are used here. umbrelOS is PolyForm Noncommercial.) OneMind's "desktop" in that sense is the dashboard and Home in `ui/`. This app is the native companion.

| Status, light | Status, dark | Finding a box | Wrong token |
|---|---|---|---|
| ![](docs/screenshots/status-light.png) | ![](docs/screenshots/status-dark.png) | ![](docs/screenshots/discover.png) | ![](docs/screenshots/pair-error.png) |

| Box unreachable (plain-HTTP box) | Calm box, older gateway (dark) |
|---|---|
| ![](docs/screenshots/unreachable.png) | ![](docs/screenshots/calm-dark.png) |

The screenshots are the real `src/` files rendered in a browser through `tools/mock-bridge.js` (`npm run preview`), because this build machine had no screen-recording permission. The pending action has the shape the Rust core read from a local dev gateway (an `app.install` requested by the Hermes agent). Nodes, updates and backups are fixture values: a dev gateway without NATS reports no nodes, and the update and backup routes are not served yet.

## What it does today

| Feature | How |
|---|---|
| Lives in the menu bar / tray | Tauri tray icon (template icon on macOS, no Dock icon). Left click opens the popover under the icon; right click opens a menu (Show, Open dashboard, Files, Quit). On macOS, the number of pending approvals shows next to the icon. |
| Find boxes | mDNS browse of `_onemind._tcp` for 2.5 s (`mdns-sd`), plus a probe of `onemind.local:8080/healthz`. You can also type an address. Discovery only suggests an address. It creates no trust. |
| Pair | Paste a token. The app checks it with `GET /v1/instance`, then stores it in the **OS keychain** (macOS Keychain, Windows Credential Manager) under the box's hub node id. The box list (name, address) is a JSON file in the app's config folder and holds no secrets. |
| Box status | Every 20 s, and on demand: `GET /v1/instance`, `/v1/nodes` (online/total), `/v1/actions` (state `awaiting_approval`), plus the planned `/v1/os/updates` and `/v1/backups/status`. A 404 on a planned route shows "not reported yet" in grey, never a green tick. Every card says how old its data is. |
| Approval notifications | A native notification for each new pending action ("Approval needed on Home box: hermes asks: app.install home-assistant"). Clicking it never approves. You approve in the dashboard. |
| Open dashboard | Opens the box address in the system browser. Box pages never load inside the app's web view (the study's DESK-S1 rule, until pinned trust in web views is proven). |
| Files | Opens `smb://<box>/` in Finder (macOS) or `\\<box>\` in File Explorer (Windows). The share itself (Samba app, per-device users) and a real mount are CLIENT-9. |

**Plain-HTTP rule.** HTTPS is always accepted. Plain HTTP is accepted only to this computer (loopback), or when you tick "This box has no HTTPS yet". Such a box then carries a "Not encrypted" badge. Redirects are never followed, so the token cannot be forwarded to another host.

## Layout

```
desktop/
  src/                 popover UI: plain HTML, CSS and ES modules, no bundler
    app.js             rendering and events; box text only ever goes through textContent
    format.js          pure wording/tone helpers (tested with node --test)
    tokens.css         copy of ui/src/tokens/tokens.css (npm run sync:tokens)
  src-tauri/           Rust core: everything that touches the network, the keychain or the OS
    src/lib.rs         commands, tray, popover placement, poller, notifications
    src/api.rs         gateway client and status parsing
    src/discovery.rs   mDNS browse and the onemind.local probe
    src/address.rs     address normalising and the plain-HTTP rule
    src/store.rs       box list (JSON) and keychain tokens
    capabilities/      the web view gets core:default only: no opener, shell, fs or http permission
  tools/               browser preview with a fixture bridge (used for the screenshots)
  test/                UI unit tests
  assets/              our own icon sources (SVG); src-tauri/icons is generated from them
```

**Why this split.** The web view draws the UI. All network calls, tokens and OS actions stay in Rust and are reached only through named commands. A bug in the page therefore cannot read a token or open arbitrary URLs. The content security policy allows scripts and styles only from the app itself.

## Build and run

You need Node 22+ and Rust (rustup reads `src-tauri/rust-toolchain.toml`; Homebrew `rust` 1.99.1 also works). On Windows you also need the MSVC build tools; WebView2 is part of Windows 11.

```sh
cd desktop
npm ci
npm run dev                 # run with hot reload of src/
npm run build:app           # macOS: src-tauri/target/release/bundle/macos/OneMind.app
npx tauri build --bundles nsis   # Windows: ...\bundle\nsis\OneMind_0.1.0_x64-setup.exe
```

Builds are **unsigned**. On macOS, open the app with right-click → Open the first time. Signing, notarization, MSIX and the signed updater are CLIENT-12.

To try it against a local gateway (dev tokens, loopback only):

```sh
cd core
ONEMIND_HOST=127.0.0.1 ONEMIND_TOKENS_FILE=examples/tokens.example.yaml uv run python -m onemind_core
# in the app: address http://127.0.0.1:8080, token from that example file
```

Set `ONEMIND_DESKTOP_PIN=1` to keep the popover open when it loses focus (handy while developing).

### Windows build in CI

`.github/workflows/ci-desktop.yml` runs on every PR that touches `desktop/**`, on `macos-15` and `windows-2025`. Each run:

1. Runs the UI tests.
2. Runs `cargo test --locked`.
3. Builds the DMG (macOS) or the NSIS installer (Windows).
4. Fails if the installer is 25 MB or larger.
5. Uploads the installer as a build artifact for 14 days.

Actions are pinned by commit, as listed in `os/versions.lock.yaml`. Tauri's bundler downloads the NSIS tools on Windows at build time; pinning or caching them belongs to CLIENT-12.

## Tests

| Test | Command | What it proves |
|---|---|---|
| UI | `npm run check:ui` | wording, tile tones, "not reported" is never green, the plain-HTTP check matches Rust |
| Rust unit | `cd src-tauri && cargo test` | address rules (credentials, schemes, loopback), status parsing for both backup-route drafts |
| Live gateway | `ONEMIND_TEST_GATEWAY=http://127.0.0.1:8080 ONEMIND_TEST_TOKEN=… cargo test -- --ignored live_gateway` | real status read, and a wrong token gives `unauthorized` |
| Live mDNS | advertise with `dns-sd -P "Test box" _onemind._tcp local 8080 onemind.local 127.0.0.1 id=t v=1`, then `cargo test -- --ignored live_mdns` | the browse finds the box |
| Keychain | `cargo test -- --ignored keychain_roundtrip` | write, read and delete one keychain item |

### Measured on the first build (Apple silicon Mac, macOS, 2026-11-12)

- `OneMind.app`: **5.5 MB** (the target is an installer under 25 MB).
- Idle memory after 25 s: **about 53 MB** physical footprint (app 26 MB, WebKit content 22 MB, WebKit networking 4.6 MB, measured with `footprint`). The target is under 120 MB.
- The Windows numbers come from the first CI run.

## Licences (pinned versions)

| Component | Version | Licence | Ships how |
|---|---|---|---|
| tauri, tauri-build | 2.12.5, 2.7.4 | Apache-2.0 OR MIT | linked |
| @tauri-apps/cli | 2.12.4 | Apache-2.0 OR MIT | build tool only |
| tauri-plugin-notification, -opener, -single-instance | 2.8.0, 2.7.2, 2.5.5 | Apache-2.0 OR MIT | linked |
| mdns-sd | 0.21.6 | Apache-2.0 OR MIT | linked |
| reqwest (rustls) | 0.13.5 | MIT OR Apache-2.0 | linked |
| keyring | 3.6.3 | MIT OR Apache-2.0 | linked |
| tokio | 1.54.1 | MIT | linked |
| serde, serde_json, url | 1.0.229, 1.0.154, 2.5.8 | MIT OR Apache-2.0 | linked |
| WKWebView / WebView2 | OS component | Apple / Microsoft terms | part of the OS, not shipped by us |

The 313 crates in the macOS dependency graph are all permissive licences (MIT, Apache-2.0, BSD, ISC, Zlib, Unicode-3.0, Unlicense, CC0, 0BSD), except five under **MPL-2.0** that Tauri brings in (`cssparser`, `cssparser-macros`, `dtoa-short`, `option-ext`, `selectors`). MPL-2.0 is file-level copyleft. Shipping them unmodified inside a commercial app is allowed, as long as we point to their source. A generated third-party notices file (`cargo about`) is part of CLIENT-12.

keyring 4.x exists, but it splits into separate store crates whose API was not checked for this skeleton. 3.6.3 is the last 3.x release.

## Next steps (in epic order)

1. **CLIENT-2 + CLIENT-3:** replace the pasted token with a device request the owner approves (`device.add`): a non-exportable device key (Secure Enclave on Mac, TPM via CNG on Windows) with DPoP on refresh, and fingerprint words plus a check code for first trust. Pin the box CA per instance id, and refuse a changed CA clearly.
2. **CLIENT-9:** shares. Create a per-device SMB user (`POST /v1/shares/credential`, password kept in the keychain), then mount from Rust: NetFS on macOS, `WNetAddConnection2` on Windows (Windows picks the drive letter), gio on Linux. Re-adopt mounts only after the box proves its identity. WebDAV is the fallback if Samba is not chosen (founder decision 2 in the study).
3. **CLIENT-10:** switch from polling to `GET /v1/events` (server-sent events), and add passkey approve from the popover (spike DESK-S2). The fallback stays "open the card in the dashboard". A notification click opens the card and never approves.
4. **CLIENT-11:** laptop folder backup with restic to the box, with verified restores and a pause on battery or metered networks.
5. **CLIENT-12:** Developer ID signing and notarization, MSIX or a signed NSIS installer, the Tauri updater with an Ed25519 key held in a GitHub environment, downgrade refusal, and third-party notices.
6. Linux (`.deb`, AppImage) in CI, and autostart at login (`tauri-plugin-autostart`).
