<!-- SPDX-License-Identifier: Apache-2.0 -->
# Project NOMAD parity: match every feature, then go past it

**Date:** 2026-11-14 · **Status:** plan for the founder; changes no decision in [`docs/DECISIONS.md`](../DECISIONS.md) or the contract [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md). Item IDs `NMD-*` are proposals for [`docs/leap/BACKLOG.md`](../leap/BACKLOG.md); nothing here is claimed on the board.
**Founder brief (2026-11-14):** "make sure we conquer their setup; document it and plan to add these things."
**Evidence:** the teardown [`research-output/02-competitors/project-nomad.md`](../../research-output/02-competitors/project-nomad.md) (v1.35.1, still the latest release on 2026-11-14), NOMAD's website and public roadmap (read 2026-11-14), NOMAD's `SECURITY.md` and issues (read with `gh` on 2026-11-14), and `origin/main` of this repo on 2026-11-14.
**Sibling pages:** [`umbrel-parity.md`](umbrel-parity.md), [`core-alignment.md`](core-alignment.md), founder note [`docs/learning/founder/03-competitors-and-where-we-go.md`](../learning/founder/03-competitors-and-where-we-go.md) (PR #122).

> ### In plain words
> Project NOMAD is a free app you install on an Ubuntu PC. It fills the PC with offline Wikipedia, courses, maps and a local AI, and it reached about 43,400 GitHub stars in 16 months. Its website shows 4 modules, but it really has about 30 features. OneMind already beats it on safety (logins, backups, OS updates, Pi and Jetson support, AI that can only ask). It loses today on **content**: OneMind has no offline-knowledge apps yet.
> This page lists every NOMAD feature, what OneMind has, and the plan to close each gap. §4 is the build order.

---

## 1. Are NOMAD's gaps on purpose?
Partly. Each answer cites NOMAD's own words or code.

| Gap | On purpose? | Evidence |
|---|---|---|
| **No logins** | **Yes, a stated design rule.** Its `SECURITY.md` says no authentication on the Command Center "is intentional", and treats the local network as the trust boundary. The admin-only request (#1238) was closed "not planned"; #227 and #764 ended with documentation pointing to an optional Caddy basic-auth guide. | `SECURITY.md`; issues #227, #764, #1238; teardown §7 |
| **No backups** | **Deferred, not a stance.** The scheduled-backups request (#715) was moved to the community roadmap. The update script tells users to back up first, with no tool to do it. | issue #715; teardown §9 |
| **No OS updates** | **Yes, by scope.** NOMAD is an app on top of the user's own Ubuntu or Debian, not an operating system. Host patching is left to the user. Its users now ask for a "System Update Status" panel on the roadmap. | teardown §3 and §5; public roadmap |
| **x86 only** | **Yes, a product choice.** The site says it is "built for robust hardware" so the AI can be strong, and sends Raspberry Pi users to Internet-in-a-Box. The ARM64 pull request (#419) was closed without merging. | website; PR #419; teardown §11 |

**What this means:** NOMAD chose simplicity for one trusted household on one strong PC. OneMind targets the households, field kits and fleets that choice leaves out: shared homes with children and guests, Pi and Jetson boxes, and machines that must update themselves safely.

## 2. Every NOMAD feature against OneMind
**Status key:** `have` = on `origin/main`; `partial` = some of it on `main`; `in-flight` = open PR or running session; `gap` = nothing yet. App tiers come from each `apps/*/onemind.app.yaml` on `main`.

### 2.1 The four headline modules
| NOMAD feature | OneMind today | Status | Plan |
|---|---|---|---|
| Information Library (Kiwix, ZIM files) | No Kiwix app | gap | NMD-01 |
| Content manager: Wikipedia sizes, curated collections (medical, survival, education), content auto-update | None | gap | NMD-01, NMD-02 |
| AI Assistant (Ollama) | `apps/ollama`, tier community | partial | NMD-03 |
| GPU auto-detect: NVIDIA, AMD (ROCm), else CPU | `onemindd` reports NVIDIA and Jetson GPUs (`cmd/onemindd/README.md`); no AMD or Intel; no GPU scheduling for apps | partial | NMD-05 |
| RAG chat over the library and uploaded files (Qdrant), editable system prompt, evaluation harness | None (AnythingLLM and LibreChat app folders are `blocked`) | gap | NMD-03 |
| Offline Maps (OpenStreetMap, PMTiles, region downloads) | None | gap | NMD-01 |
| Education Platform (Kolibri, Khan Academy) | None | gap | NMD-01 |

The four modules plus the content manager are the running "Offline Knowledge bundle for the Market" session (REC-NOMAD-01); no PR yet on 2026-11-14.

### 2.2 The "Supply Depot" apps (17 seed apps in v1.35.1)
| NOMAD app | OneMind equivalent | Status |
|---|---|---|
| Kiwix, Kolibri, Ollama, Qdrant | see §2.1 | gap / partial |
| Vaultwarden | `apps/vaultwarden` | have (verified) |
| Jellyfin | `apps/jellyfin` | have (community) |
| Homebox | `apps/homebox` | have (community) |
| FlatNotes | `apps/trilium`, `apps/memos` | have (community) |
| Stirling-PDF | `apps/bentopdf` | have (community) |
| FileBrowser | core files service (#77) | have |
| Excalidraw | `apps/excalidraw` | blocked (scan) |
| Calibre-Web | `apps/calibre-web` | blocked (scan) |
| CyberChef, IT-Tools | none | gap: NMD-04 |
| Meshtastic Web, MeshCore Web | none | gap: NMD-06 |
| nomad-translate (translation proxy) | none | gap: NMD-04 (LibreTranslate or similar, licence check first) |

### 2.3 Platform features
| NOMAD feature | OneMind today | Status |
|---|---|---|
| One-line install on Ubuntu/Debian | `deploy/install.sh` developer install (#26, #78); flashable images and USB installer (#66) | have, and more |
| Windows via WSL2 | none | gap, low priority (OneMind is a box OS) |
| Per-app update: keep old, health-check new, roll back | app lifecycle with health-gated update and automatic revert (#72) | have |
| Core auto-update policy: window, 72 h cool-off, same-major only, disable after 3 failures, dry-run simulator | maintenance windows in automation (#75) and `onemind update` (#15); no cool-off, failure back-off or simulator found on `main` | partial: NMD-07 |
| Offline-aware image pruning (never delete images of stopped apps) | not found on `main` | gap: NMD-08 |
| Custom apps with a mount guard | Compose import and community sources in #57; install sandbox (#40) | in-flight |
| Hardware benchmark and public leaderboard | none | gap: NMD-09 |
| Minimum CPU level check (the `x86-64-v2` lesson, NOMAD #661) | not found on `main` | gap: NMD-09 |
| Log viewer (Dozzle) | app logs in #57 | in-flight |
| Disk usage view | storage service on `main`; storage actions in #103 | partial / in-flight |
| Creator Packs (third-party content channel) | none | gap: NMD-10 (licensed per pack, never bundled) |
| Zero telemetry | no telemetry; public-repo hygiene rules | have |
| Video guides, community builds, merch, Ko-fi | website and guides (`site/`) | partial (business, not software) |

### 2.4 Where OneMind is already ahead
| Capability | NOMAD | OneMind on `main` |
|---|---|---|
| Accounts and roles | none, by design | owner, adult, guest and child roles (`core/onemind_core/identity/service.py`), passkeys (#41) |
| Backups and restore | none | restic backups with verified restores (#86, #91) |
| OS updates with rollback | none | read-only image, RAUC A/B, fresh-signal health gate, TUF-signed updates (#10, #15) |
| Signed releases | unsigned, installer pulled from `main` with no checksum | signed bundles and TUF (publishing waits on F-27) |
| AI permission layer | none: the AI only reads | AI and agents can only request; the owner approves; audit chain; MCP with approvals |
| Hardware | x86 only | x86, Raspberry Pi 5, Jetson, cloud images (#66) |
| Many machines as one | one box | mesh join and fabric (#88 in-flight) |
| Automation, notifications, photos | none | #75, #44, #108 |

## 3. What NOMAD's users ask for next
From the public roadmap (read 2026-11-14; vote counts at that time). These show demand OneMind can meet first.

| Request (votes) | OneMind answer | Plan |
|---|---|---|
| Distance between two map points (28) | part of the maps app | NMD-01 |
| Ham radio / SDR reference library (23); frequency lists (10) | content packs | NMD-02 |
| Custom map layers and overlays (14) | part of the maps app | NMD-01 |
| Mesh AI (14); MeshCore BBS with store-and-forward (10); Meshtastic app | NATS bus + mesh adapters | NMD-06 |
| Let the AI search online and save to the knowledge base (12) | approval-gated: the AI asks, the owner approves the save | NMD-03 |
| Offline office suite (11 + 3) | office app (Collabora or OnlyOffice; licence check) | NMD-04 |
| Offline audio player for podcasts and books (11) | `apps/audiobookshelf` is blocked; `apps/navidrome` exists | Market unblock (A11) |
| Shareable offline installer (10) | USB installer and images (#66); add "make an installer from this box" | NMD-11 |
| Home Assistant app (9) | `apps/home-assistant` is blocked | Market unblock (A11) |
| System update status in the admin panel (9) | OS update status exists in the API; show it in the dashboard | dashboard wiring pass |
| ArchiveBox (8) | Market app | NMD-04 |
| Non-English content catalogs (8) | content manager with language choice | NMD-02 |
| Radio speech-to-text (7) | Whisper-class app on the GPU, transcripts searchable by the AI | NMD-12 |
| Folder ingest for the AI at night (5); scheduled AI on/off (5) | automation schedules (#75) driving the AI apps | NMD-03, NMD-07 |
| Vision model for hard PDFs (5); Intel NPU (4); live GPU gauge (3); GPU for every app (3) | GPU and accelerator layer | NMD-05 |

## 4. The plan, in build order
Each item names its owner lane per [`docs/leap/LANES.md`](../leap/LANES.md) and the step it feeds. Items 1 to 8 need no hardware.

| # | ID | What | Lane | Feeds | Done when |
|---|---|---|---|---|---|
| 1 | **NMD-01** | Offline Knowledge bundle: Kiwix with a library manager, Kolibri, offline maps (PMTiles) with distance and overlays, one-click bundle and an off-grid profile | A (`apps/`) | REC-NOMAD-01, Wave G #7 | in progress in its own session; each app passes the CI app gate or is `blocked` with a reason |
| 2 | **NMD-03** | AI over your library: Qdrant (or similar) + RAG chat on the existing Ollama app; editable system prompt; folder ingest on a schedule; "save web result" only after owner approval | A | AI capability layer (report §3.8) | chat answers from a ZIM and an uploaded PDF in a test; no write without approval |
| 3 | **NMD-02** | Content manager: pick Wikipedia size and language, curated packs (medical, survival, education, radio), auto-update in the maintenance window, size shown before download | A + dashboard | REC-NOMAD-01 | a pack downloads, updates and is removed from the dashboard |
| 4 | **NMD-04** | Fill the Supply Depot gap: CyberChef, IT-Tools, a translation app, ArchiveBox, an office suite | A (`apps/`) | A11 | each app passes the gate or is `blocked` with a reason |
| 5 | **NMD-07** | Update policy knobs for apps and content: cool-off hours, same-major only, back-off after repeated failures, a dry-run of "what would update tonight" | A (core) | REC-NOMAD-03 | tests for each rule; shown in the dashboard |
| 6 | **NMD-08** | Offline-aware garbage collection: prune superseded images, never those of installed-but-stopped apps; a disk budget per box | A + B | REC-NOMAD-04 | an offline box can restart every installed app after GC |
| 7 | **NMD-05** | GPU and accelerator layer: AMD and Intel detection next to NVIDIA and Jetson, GPU requests in the app manifest, GPU sharing between apps (HAMi pattern from Olares; licence check first), a live GPU gauge | A (core) + B (`os/`) | report §6.5 | two apps share one GPU in CI or a cloud GPU VM |
| 8 | **NMD-09** | "Can my box run this?": a benchmark score, a minimum CPU level per app image checked before install or update, and an opt-in public leaderboard | A | REC-NOMAD-08, REC-NOMAD-11, report §8.2 | install refuses an app whose CPU level the box lacks, with a clear message |
| 9 | **NMD-06** | Mesh radio: Meshtastic and MeshCore web apps, then a native adapter on the NATS bus with store-and-forward messages | B (mesh) + A (apps) | report §3.7, REC-NOMAD-09 | messages relay between two boxes in a lab test; real radios wait on F-25 |
| 10 | **NMD-12** | Radio speech-to-text: transcribe an SDR feed and make it searchable by the AI | A | NOMAD roadmap demand | after NMD-05 and NMD-06 |
| 11 | **NMD-11** | "Make an installer from this box": write a USB installer that carries the box's current signed image, for offline onboarding | B (`os/`) | image line (#66) | after F-27, so the copied image is signed |
| 12 | **NMD-10** | Content-pack channel for third-party creators, licensed per pack, never bundled into the image | A | REC-NOMAD-10 | a business decision for Zeus first |

**What does not need building:** logins, roles, backups, OS updates, Pi and Jetson support, signed releases, per-app rollback and the AI permission layer are already on `main`. The marketing should say so plainly: everything NOMAD does, with a lock on the door and a safety net under the floor.

## 5. Licences to check before shipping
- NOMAD's code is Apache-2.0, the same as OneMind: patterns and even code may be reused, with attribution in NOTICE. Prefer re-implementing to keep one code style.
- NOMAD's **Creator Pack** content uses a separate non-commercial licence that forbids forks from serving it. Never bundle it.
- Each upstream app and content source needs its own check before it ships: Kiwix ZIM content, Kolibri channels, OpenStreetMap data (ODbL attribution), the office suite, the translation models, HAMi.

## 6. Words used
- **ZIM:** a compressed file format for whole websites, such as Wikipedia, read by Kiwix.
- **PMTiles:** a single-file format for map tiles, so a whole region's map works offline.
- **RAG:** retrieval-augmented generation: the AI looks things up in your documents first, then answers.
- **SDR:** software-defined radio: a USB radio receiver controlled by software.
- **Meshtastic / MeshCore:** cheap long-range radios that pass text messages between each other with no internet.
- **Cool-off:** waiting a set time after a release before installing it, so others hit the early bugs first.
