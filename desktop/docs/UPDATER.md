<!-- SPDX-License-Identifier: Apache-2.0 -->
# Desktop app updates: channel and signing design

**Status (2026-11-12): designed, switched off.** The app has no updater today: no `tauri-plugin-updater` dependency, no public key, no endpoint, and it never checks for updates. People install a new version by hand. Turning updates on needs two founder decisions (§6) and is built in UMB-CLIENT-12 (`.github/workflows/desktop-release.yml`, `desktop/release/**`).

> **Explain it like I am the founder**
> An updater is a door into every computer that runs the app: whoever can publish an update can run code there. So an update must prove two things before it installs. First, that **we** built it (our signature, checked by the app itself). Second, that it is **newer** than what is installed (no one may push an old version with known holes). A "channel" is a named stream of versions: `stable` for everyone, `beta` for people who opt in.

## 1. Two signatures, two jobs

| Signature | Proves | Checked by | Key | Decision |
|---|---|---|---|---|
| OS code signing: Apple Developer ID plus notarization (macOS), Authenticode (Windows) | The publisher, to the operating system, so it opens the app without warnings | macOS Gatekeeper, Windows SmartScreen | Apple and Windows signing accounts | F-59 (exists) |
| Updater signature: Ed25519 (minisign format, `tauri signer generate`) | That an update file came out of our release pipeline unchanged | The app itself, before installing, with the public key built into it | Our own key pair; the public key is committed in `tauri.conf.json` | **F-61** (new) |

Both are required. The OS signature alone does not stop an attacker who controls the download host from serving an older, validly signed build; the updater checks the version too (§4). The updater signature alone does not satisfy Gatekeeper or SmartScreen.

## 2. Channels

| Channel | Who | What ships there |
|---|---|---|
| `stable` (default) | everyone | releases that passed the beta for at least 7 days with no open P0/P1 bug |
| `beta` | people who switch it on in the app | every release candidate |

- The channel list is **compiled into the app**. A setting chooses one of them; nothing (a box, a web page, a notification) can point the updater at another URL.
- Endpoints are HTTPS only. The plugin refuses plain HTTP unless an explicit insecure option is set, and the release check fails the build if that option appears.
- Switching `beta` → `stable` never downgrades: the app stays on its beta build until `stable` passes it.

## 3. Where updates come from

Each channel is one static JSON file in the plugin's documented format:

```json
{"version": "0.2.0", "notes": "…", "pub_date": "2026-12-01T10:00:00Z",
 "platforms": {"darwin-aarch64": {"signature": "<minisign signature>", "url": "https://…/OneMind_0.2.0_aarch64.app.tar.gz"},
               "windows-x86_64": {"signature": "…", "url": "https://…/OneMind_0.2.0_x64-setup.exe"}}}
```

Hosting options (part of F-61):

| Option | For | Against |
|---|---|---|
| **A. GitHub Releases** of this repo, one release per channel holding `latest.json` and the artifacts (recommended now) | No server to run; artifacts next to the source; free | Ties update traffic to GitHub; the URL names the repository |
| B. Our own update host (`https://updates.<our-domain>/desktop/<channel>/latest.json`) | Independent of GitHub; can do staged rollouts later | Needs the product domain (name clearance Z-29) and a server |
| C. **The box serves the manifest** it fetched from A or B (later, local-first) | Works on a LAN with no internet; the owner can hold the household on one version | The box cannot forge an update (the signature is ours), but it can hold one back; needs a contract route |

Static files mean the check sends nothing about the computer: no version, no machine id in the URL.

## 4. Rules the app enforces

1. **Signature first.** A file whose Ed25519 signature does not verify against the built-in public key is deleted, not installed (plugin behaviour; tested in §5).
2. **Newer only.** Keep the plugin's default comparison (install only if the offered version is greater than the running one). Never add a custom comparator that allows equal or lower versions.
3. **Ask, then install.** The tray shows "Update ready: 0.2.0" with the notes; installing needs a click. No silent installs, including for security fixes (the box's OS has its own security channel; this is a client app).
4. **Check rarely.** At start and every 6 hours, and never on a metered network (the same rule as laptop backups, CLIENT-11).
5. **Driven from Rust.** The web view gets no `updater:*` permission; the popover asks a Rust command, which talks to the plugin.

## 5. Turning it on (UMB-CLIENT-12 checklist)

1. Founder: F-59 accounts and F-61 (key custody and hosting).
2. Generate the key pair offline; put the private key and its password in a GitHub **environment** `desktop-release` with a required reviewer (as CORE-SEC-8 does for OS release keys), readable only by `desktop-release.yml`. Keep an offline backup: losing the key means every installed app must be reinstalled by hand.
3. Add `tauri-plugin-updater` (pin a version released at least two weeks earlier; record it and its licence in the README table and `os/versions.lock.yaml`), `bundle.createUpdaterArtifacts: true`, and `plugins.updater` with `pubkey` and the two channel endpoints.
4. Release workflow: build, OS-sign and notarize, sign the update artifacts (`TAURI_SIGNING_PRIVATE_KEY` from the environment), publish `latest.json` per channel.
5. Tests that must pass before the first public build: a tampered artifact is rejected; an artifact signed with another key is rejected; an older version is not offered for install; an `http://` endpoint is refused; Windows NSIS `passive` install completes on a clean Windows 11 VM.

**Key rotation.** The public key is inside the app. To rotate, ship one update signed with the old key that carries the new public key; from then on releases use the new key.

## 6. Founder decisions

- **F-59** (exists): Apple Developer ID and a Windows code-signing account.
- **F-61** (new, this PR): who holds the updater signing key and how it is backed up, and where updates are hosted (A now, C later, is the proposal).
