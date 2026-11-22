<!-- SPDX-License-Identifier: Apache-2.0 -->
# umbrelOS screens and OneMind: what we have, what is built, what is missing

**Date:** 2026-11-20 (ET). **Requested by:** the founder ("what other screens are we missing?"). **Serves:** D-016 (desktop frame), the umbrel-parity issues (UMB-P01 to UMB-P16) and the M-LIVE goal.
**Method:** every screen of umbrelOS 2.0.1, captured from a lab VM (64 captures, desktop and phone, kept off the repo), compared with the routes on `origin/main` (`0211c1b0`), the open pull requests and the issue titles. Companion page: [umbrelos-2-teardown.md](umbrelos-2-teardown.md), how umbrelOS is built.

> ### In plain words
> umbrelOS feels like an operating system because almost every setting a person needs has its own screen. OneMind now has the same desktop frame (D-016) and most of the everyday screens. The rest falls into three groups: screens already built and waiting in a pull request, screens that have an issue but no code, and six screens nobody had planned. The six now have issues (#429 to #434).
>
> Only patterns are copied. umbrelOS is PolyForm Noncommercial, so no code, icons, images or text come from it.

## 1. On main today

| umbrelOS screen | OneMind |
|---|---|
| Login | Sign in (`/login`) |
| Home desktop, edit widgets, wallpaper | Desktop with dock and Launchpad (D-016), widgets and wallpapers from `@onemind/ui` |
| App store, categories, app page | Market (`/market`, `/market/:appId`) |
| Installed apps | Installed (`/installed`) |
| Virtual machines | Machines (`/machines`) |
| Settings → Storage, Backups | Storage, Backups (`/storage`, `/backups`) |
| Settings → Users, account name and password, sessions, 2FA | Users, Account (passkeys, sessions) |

OneMind also has screens umbrelOS lacks: Approvals, Activity (audit), Alerts, Nodes, Control Hub and Agents.

## 2. Built, waiting in an open pull request

| umbrelOS screen | Pull request |
|---|---|
| Settings → Software update | #357 (UMB-P05, #142), in the merge queue on 2026-11-20 |
| Restart, Shut down, Troubleshoot | #355 (UMB-P09, #146) |
| Community app store, per-app settings | #353 (UMB-P06, #143) |
| Users with roles | #369 (FAM-01, #204) |
| Share links in Files | #381 and #375 (FILES-02, #237); two drafts of the same issue, one should close |

The Software update screen can file an install request, but an install only happens once the gateway calls the host service from #385 and releases are signed with the permanent key (REL-01, #153). Today every CI build signs with a throwaway key, so an installed box refuses updates from later builds.

## 3. Planned, no code yet

| umbrelOS screen | Issue |
|---|---|
| Files (Home, Recents, Apps, Trash, cloud drives) | #141, #241 |
| Settings → File sharing (Samba, Time Machine) | #235 |
| Settings → Wi-Fi, Advanced → Network | #239 |
| Terminal | #273 (owner only, in the rescue console, per DEC-CMP-01 #253) |
| Advanced → Tor | #284 (an optional Market app, D-014) |
| Migration assistant, restore at first run | #145 (blocked on a dependency) |
| Open an app at its own address | #139, #286 |
| App store categories in the manifest | #140 |

## 4. Not planned before 2026-11-20, now filed

| umbrelOS screen | Issue | Note |
|---|---|---|
| Live usage (CPU, memory, disk per app) | #429 UMB-P11 | ready |
| Photos | #430 UMB-P12 | founder call: built-in viewer or the Immich app |
| Settings → Language | #431 UMB-P13 | large: string catalogues first |
| Settings → Device info | #432 UMB-P14 | ready; leaves out serials when copied for support |
| Settings → MCP | #433 UMB-P15 | waits for #169; connections go through approval |
| Advanced → Beta program | #434 UMB-P16 | waits for #142, #154 and signed channels (#153) |

## 5. How to keep this page true
When one of these merges, move its row up a section in the same PR (a `fix(docs):` commit). A later umbrelOS release can add screens; re-run the capture against the lab VM and add rows, never copy its text.
