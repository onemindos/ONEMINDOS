# HexOS: Tier C teardown

**Workstream:** W1 (Tier C) · **Tag:** TD-tier-c-nas · **Date:** 2026-11-11
**Claims:** `evidence/claims/TD-tier-c-nas.csv` (HexOS rows C-TD-tier-c-nas-018 … 030), plus reused C-TD-truenas-scale-* · **Sources:** `evidence/sources/TD-tier-c-nas.md`
**Pins:** `eshtek/hexos-docs@af3e217c` (2026-11-10), `eshtek/hexos-app-catalog@fb2daaa6` (2026-11-08). Release analysed: **HexOS 25.10.7** installer (2026-09-03) with the Command Deck as of 2026-11-10 [C-TD-tier-c-nas-018, C-TD-tier-c-nas-026].
**Requirements served:** P-7, R-1, A-1, A-2, A-3, A-5, AI-1, AI-8, UX-6, H-1, H-2, F-6, F-14, D-001

> ### Explain it like I'm the founder
> HexOS is **not a new operating system.** It is a friendly app ("Command Deck") on top of an unmodified **TrueNAS** install. Its installer is literally `TrueNAS-SCALE-25.10.7-HexOS.iso`, signed by iXsystems [C-TD-tier-c-nas-018]. Eshtek, a startup reportedly led by ex-Unraid developers [C-TD-tier-c-nas-023, SECONDARY], owns the user experience. iXsystems owns the OS, the kernel, ZFS and the updates.
>
> **Why it matters to you:** HexOS proves that **"UX layer on a proven base" is a viable startup**. It ships a new release roughly every few days (58 release notes in two years) [C-TD-tier-c-nas-022]. It already does things OneMind wants. A **Local AI** wizard picks models that fit your GPU and installs Ollama plus an agent, including **Hermes Agent** [C-TD-tier-c-nas-027]. App updates are held 7 days and come with restore points [C-TD-tier-c-nas-026]. Encrypted "Buddy Backup" goes to a friend's box [C-TD-tier-c-nas-029]. The price of this model: it started cloud-hosted, and in mid-2026 sign-in still went through Eshtek's cloud [C-TD-tier-c-nas-020, C-TD-tier-c-nas-023]. It is also x86-only and cannot move faster than TrueNAS does [C-TD-tier-c-nas-024, C-TD-tier-c-nas-028].

## 1. W1 fields

| Field | HexOS (evidence) |
|---|---|
| **Architecture** | Command Deck web app + a local agent ("HexOS Local") driving the **TrueNAS middleware API**. The full TrueNAS UI stays available underneath [C-TD-tier-c-nas-029]. The deck is served from `deck.hexos.com` **and** from the server's own address. The hosted deck hands the browser over to the server when it can reach it [C-TD-tier-c-nas-021]. Until April 2026 the backend was cloud-hosted. HexOS 1.0 moved everyone to "Local" and deprecated the hosted backend [C-TD-tier-c-nas-020]. |
| **Base OS** | Stock TrueNAS Community Edition (Debian 12; see `truenas-scale.md`), version range enforced by HexOS (≥ 24.10.2.2, < 26.0.0 at 1.0) [C-TD-tier-c-nas-020]. TrueNAS 27 not yet offered on 2026-11-06 [C-TD-tier-c-nas-028]. |
| **Image / install** | HexOS Imager (signed Windows build, notarized Mac build) downloads, checks and writes the ISO, then reads it back. The ISO is GPG-signed by iXsystems [C-TD-tier-c-nas-018]. The guide tells users to **disable Secure Boot** if it blocks the boot [C-TD-tier-c-nas-019]. |
| **Update / rollback** | OS: TrueNAS's ZFS boot environments with manual rollback and no signature check in the client [C-TD-truenas-scale-009, C-TD-truenas-scale-011, C-TD-truenas-scale-008]. Command Deck: **deployed automatically by Eshtek**, no user action [C-TD-tier-c-nas-022]. Apps: opt-in auto-update in a daily window, **7-day hold**, restore point first, and roll back of the app version as well as its data [C-TD-tier-c-nas-026]. |
| **App format** | JSON **install scripts** (schema v4–v6) that fill in TrueNAS app values, with **hooks**: TypeScript functions for health checks, configuration, OAuth sign-in, cross-app links and user "Actions". They live in a catalogue repo with no licence file [C-TD-tier-c-nas-025]. "Collections" install linked groups of apps [C-TD-tier-c-nas-027]. |
| **Identity** | HexOS account (email) with 2FA. Authentication still passes through the cloud [C-TD-tier-c-nas-023, SECONDARY]. |
| **AI features** | **Local AI collection:** GPU-aware model picker, Ollama + Open WebUI/AnythingLLM + Hermes Agent or OpenClaw + optional OpenCode, SearXNG, n8n. Needs an NVIDIA/AMD GPU [C-TD-tier-c-nas-027]. No MCP server for the box itself was found. |
| **Backups** | Encrypted **Buddy Backup** to a friend's HexOS server. App restore points [C-TD-tier-c-nas-029, C-TD-tier-c-nas-026]. |
| **Hardware** | x86 with SSE4.2/POPCNT, 8 GB RAM, a 20 GB SSD boot drive. **No ARM**. Can run under Proxmox. The FAQ still says 16 GB, an inconsistency [C-TD-tier-c-nas-024]. Points buyers to TrueNAS hardware. A crowd-sourced "Hardware Advisor" database is coming [C-TD-tier-c-nas-024]. |
| **License** | Proprietary UI. The UI repo is not public. `hexos-shared` types are GPL-3.0 [C-TD-tier-c-nas-030]. |
| **Business model** | Lifetime licence per server, reported at USD 199 in early access [C-TD-tier-c-nas-023, SECONDARY; the pricing page could not be read]. Partner tokens let catalogue apps get per-install partner credentials [C-TD-tier-c-nas-025]. Sponsors OpenZFS AnyRAID to grow the base [C-TD-tier-c-nas-029]. |

## 2. Failure signals

| Signal | Lesson for OneMind |
|---|---|
| Cloud-hosted control plane at launch; moving it local took a 1.0 migration of every customer [C-TD-tier-c-nas-020] | Design local-first from day one (F-6). Cloud is optional, never on the sign-in path. |
| Sign-in still depends on Eshtek's cloud after "Local" [C-TD-tier-c-nas-023] | Sovereignty claims must survive "vendor offline". OneMind tests login with the WAN unplugged (22, lab plan). |
| Can't offer TrueNAS 27 until its own code is adapted [C-TD-tier-c-nas-028] | A UX layer on someone else's OS waits on their schedule. This supports OneMind owning its image (W18). |
| "Disable Secure Boot" in the install guide [C-TD-tier-c-nas-019] | Consumer boxes need a signed boot chain that just works (REC-DEC-20). |

## 3. What competitors do (constraint-fit)

| Product | Base | Control plane | AI | Constraints | Constraint fit with OneMind |
|---|---|---|---|---|---|
| **HexOS** | Stock TrueNAS [C-TD-tier-c-nas-018] | Hosted + local deck [C-TD-tier-c-nas-021] | Local AI wizard incl. Hermes Agent [C-TD-tier-c-nas-027] | Startup; x86 only; NAS-first; no robotics | **Low** for base/updates; **Default** for app-UX patterns (collections, hold-and-restore updates) |
| umbrelOS | Own Debian image | Local only | MCP server | Small team; x86 + Pi | High for home tier |
| Olares | Ubuntu/Debian + k3s | Local + LarePass | AI gateway | Funded; GPU boxes | High for k3s layer |
| **OneMind (01)** | Own Debian 13 image | Local-first, optional cloud | MCP behind approvals | Solo; Pi → GPU; robotics | — |

## 4. What OneMind copies and what it does better

| # | Pattern | Copy or improve | Requirement IDs |
|---|---|---|---|
| REQ-HX-1 | **App "collections":** install and link a group of apps with one review screen [C-TD-tier-c-nas-027] | Copy as Market bundles (e.g. "Greenhouse", "TAK node") | A-1, A-7, P-8 |
| REQ-HX-2 | **Auto-updates with a 7-day hold + restore point + version rollback** [C-TD-tier-c-nas-026] | Copy. Add OneMind's health check to trigger the rollback automatically | R-1, A-2 |
| REQ-HX-3 | **GPU-aware AI wizard** that shows only the models that fit [C-TD-tier-c-nas-027] | Copy, driven by OneMind's capability detection (NFD/GPU feature discovery) | AI-8, A-8, N-8 |
| REQ-HX-4 | **Declarative hooks** for post-install setup and user "Actions" [C-TD-tier-c-nas-025] | Copy the idea in `onemind.app.yaml`. **Do better:** run hooks in a sandbox with declared permissions, and expose them as MCP tools | A-5, AI-1, AI-5 |
| REQ-HX-5 | **Buddy Backup** to a friend's box, end-to-end encrypted [C-TD-tier-c-nas-029] | Copy as box-to-box restic targets (06, UX-6) | UX-6, R-2 |
| REQ-HX-6 | **Crowd-sourced hardware advisor** [C-TD-tier-c-nas-024] | Copy as opt-in "works with OneMind" telemetry (11) | H-2, A-8 |
| REQ-HX-7 | **Local-first control plane** | **Do better:** no cloud on the login path, ever [C-TD-tier-c-nas-023] | F-6, D-001 |
| REQ-HX-8 | **Owning the OS layer** | **Do better:** own the image and update chain, so OneMind's UX never waits on another vendor's major release [C-TD-tier-c-nas-028] | F-7, F-8, R-3 |

**Effect on Tier A decisions:** none flip. HexOS is evidence *for* the W18 choice to own the image rather than skin someone else's. It is also a strong source of Market UX patterns.

## Glossary

| Term | Meaning |
|---|---|
| **Command Deck** | HexOS's web dashboard. |
| **Install script** | A HexOS JSON file that answers all of an app's install questions for the user. |
| **Hook** | A small program that runs at a set moment (after install, on a button press) to configure an app. |
| **Restore point** | A snapshot of an app's data (and now its version) taken before a change. |
| **GPG signature** | A cryptographic signature that proves who built a file. |
| **Early access** | Selling a product before 1.0, usually at a discount. |
