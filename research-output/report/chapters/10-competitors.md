# What the competitors actually do {#sec-competitors}

> **Explain it like I'm the founder.** Your rule was: *"Use the proven competitors for real-life documentation and use cases. They already figured it out."* We took apart 30 products, reading their build scripts, update code and app manifests at pinned commits, not their marketing. Four things stand out. **Nobody checks that an update really worked before keeping it.** **Signing is the industry's weak spot.** **Nobody does robots.** And **small teams ship these OSes**, so a solo founder can, but the key-person risk is real. Each pattern is copied only when the competitor's situation (hardware, team, Kubernetes, robots) matches OneMind's; that is the "constraint fit" column.

## Four findings across every teardown {#sec-comp-findings}

1. **No health-gated commit anywhere.** Home Assistant OS marks an update good when its Supervisor starts, even if it flags itself unhealthy [C-TD-home-assistant-os-018]; umbrelOS commits at daemon start with no watchdog found [C-TD-umbrelos-019]; ZimaOS marks good after services *start* [C-TD-casaos-zimaos-013]; Talos trusts a possibly stale "Ready" [C-TD-talos-015]. OneMind's fresh-signal gate is stricter than all of them.
2. **Signing is weak.** umbrelOS's stable release runs a server-supplied script with the bundle check switched off, and signing exists only in its beta [C-TD-umbrelos-010, C-TD-umbrelos-013]; Olares checks an MD5 from the same server [C-TD-olares-004]; ZimaOS's signing CA never expires and is named "Development" [C-TD-casaos-zimaos-049]; Synology removed package signing in DSM 7 [C-TD-tier-c-nas-036]. StartOS signs both OS updates and packages [C-TD-startos-014].
3. **No robots.** Across 11 code bases, zero files mention ROS 2 or MAVLink [C-MATRIX-002]. Home Assistant is the IoT champion but stops at vacuums and mowers.
4. **Small teams.** umbrelOS's code came from five people in a year, three of whom wrote 99% [C-MATRIX-005]; Home Assistant OS's top committer wrote 69% of a year's commits [C-MATRIX-006]; Project N.O.M.A.D. has about two maintainers [C-TD-project-nomad-004].

## The comparison {#sec-comp-matrix}

| Product | Base | Updates and rollback | Health gate | Apps / Kubernetes | Licence | Constraint fit |
|---|---|---|---|---|---|---|
| **Home Assistant OS** | Buildroot per board [C-TD-home-assistant-os-003] | RAUC A/B verity, 3 tries [C-TD-home-assistant-os-009] | No [C-TD-home-assistant-os-018] | Docker Supervisor | Apache-2.0 | **High** (update engine, signing, UX) |
| **umbrelOS 2.0** | Debian 13 [C-TD-umbrelos-003] | Rugix A/B [C-TD-umbrelos-010] | No [C-TD-umbrelos-019] | Compose | PolyForm-NC [C-TD-umbrelos-045] | **High** (base, Pi 5, team size) |
| **Olares** | Host Ubuntu/Debian [C-TD-olares-007] | No A/B; retries forward, never back [C-TD-olares-014] | Partial [C-TD-olares-012] | k3s + Helm (OAC) [C-TD-olares-021] | AGPL-3.0 [C-TD-olares-047] | **High** (app platform); none (OS safety) |
| VillageOS | None (a .NET server app) [C-TD-villageos-009] | Replace and restart [C-TD-villageos-014] | n/a | Plain processes | AGPL client, proprietary server [C-TD-villageos-007] | Low (see below) |
| balenaOS | Own Yocto [C-TD-balenaos-010] | Container OS into spare slot [C-TD-balenaos-012] | Partial [C-TD-balenaos-017] | Docker fleet | Apache-2.0 [C-TD-balenaos-003] | Medium (fleet; meta-tegra proof) |
| CasaOS | Host Debian/Ubuntu [C-TD-casaos-zimaos-020] | Downloaded script as root, no rollback [C-TD-casaos-zimaos-023] | None | Docker | Apache-2.0 | Low (stalled [C-MATRIX-008]) |
| ZimaOS | Own Buildroot [C-TD-casaos-zimaos-004] | RAUC verity, 3 tries [C-TD-casaos-zimaos-012] | No [C-TD-casaos-zimaos-013] | Docker | No licence file [C-TD-casaos-zimaos-002] | High for the engine |
| Kairos | Meta-distro over others [C-TD-kairos-008] | Active/passive/recovery [C-TD-kairos-019] | No [C-TD-kairos-022] | k3s | Apache-2.0 [C-TD-kairos-002] | Medium (no Pi 5) |
| Project N.O.M.A.D. | Host Ubuntu/Debian [C-TD-project-nomad-012] | No OS updates [C-TD-project-nomad-015] | Apps only | Docker | Apache-2.0 [C-TD-project-nomad-002] | Medium (offline library) |
| Proxmox VE | Debian 13 [C-TD-proxmox-ve-003] | In-place apt [C-TD-proxmox-ve-013] | None | VMs + LXC | AGPL-3.0 [C-TD-proxmox-ve-004] | Medium |
| StartOS | Debian 13 [C-TD-startos-005] | Image + pointer flip, no OS rollback [C-TD-startos-017] | None | Own packages | MIT [C-TD-startos-002] | Medium (signing model) |
| Talos | Built from source [C-TD-talos-002] | A/B with pending flag [C-TD-talos-013] | Partial [C-TD-talos-015] | Kubernetes only | MPL-2.0 [C-TD-talos-035] | Medium (no Orin) |
| TrueNAS SCALE | Debian 12 [C-TD-truenas-scale-003] | ZFS boot environments, manual [C-TD-truenas-scale-011] | None | Moved k3s → Docker [C-DEC-007] | GPL/LGPL [C-TD-truenas-scale-025] | Medium (portability lesson) |

The full four-slice matrix (base, updates and trust, platform, market and fit) covers 22 products plus Tier C robotics fleet vendors (Formant, Foxglove, Viam, balena for robots) in `02-competitors/MATRIX.md`; Tier C products (Unraid, HexOS, Synology, Cosmos, YunoHost, Runtipi, Cloudron, Puter, Sandstorm, FreedomBox, Coolify/Dokploy, ClawBox and other AI boxes) each have a short teardown in `02-competitors/`.

## What OneMind copies, and what it does better {#sec-comp-copy}

| From | Copy | Do better |
|---|---|---|
| **Home Assistant OS** | RAUC, verity bundles, 3 boot tries, CA rotation by cross-signing [C-W3-024], the encrypted backup "emergency kit", the add-on security rating, "Works with" certification | Commit only on fresh signals; Kubernetes app platform; robots |
| **umbrelOS** | Debian image built like a container, Pi 5 kernel pipeline, over-the-air major rebase [C-W3-039], household accounts, the beta's offline-root signing design | Signed stable releases; health gate; licence that allows OEM partners |
| **Olares** | Five-layer model, k3s + Helm app format, manifest linter, owner-signed dangerous operations, AI router and CLI skills | Own image with rollback; default-deny egress; no linter self-exemption [C-TD-olares-030] |
| **StartOS** | Signing both OS updates and packages | OS rollback |
| **TrueNAS** | Keep apps portable across runtimes | — |

## VillageOS: host and partner, don't compete (F-13) {#sec-villageos}

You shared villageos.ai and said *"this is also why I'm going operating systems."* **VillageOS is not an operating system.** It boots nothing and has no image, no update system and no hardware; it is a server application that keeps the history of every value in a model of a village (homes, tanks, solar, farms), judges values against targets, and runs simulation services; the company calls it "a temporal graph platform" [C-TD-villageos-007]. The website's "EdgeAI without centralized dependencies" [C-TD-villageos-002] does not exist in public code: there is one central server, with readings arriving over web requests [C-TD-villageos-016, C-TD-villageos-023]. The "Stanford spin-off" claim stays unconfirmed; the code comes from ReGen Villages.

| Option | Verdict |
|---|---|
| Compete on land design and finance | **No**: its simulation services are design arithmetic for pre-construction planning [C-TD-villageos-024], which no OneMind requirement asks for |
| Host VillageOS-style apps on OneMind | **Yes, as an optional Market app**, AGPL client parts only; the server is proprietary [C-TD-villageos-007] |
| Partner: OneMind as the edge OS under their "EdgeAI" stage | **Yes, low priority**: a bridge into their HTTP observation API is cheap [C-TD-villageos-022] |
| **Own the use case** (food, water, energy) | **Yes, the real answer:** a greenhouse / homestead profile with open components such as Home Assistant, OpenEMS and farmOS [C-TD-villageos-037, C-TD-villageos-040] |

**VillageOS is a planning brain without a body. OneMind is meant to be the body.** It confirms your instinct: community resilience needs an OS on the box in the greenhouse, not another web service.

## The founder-flagged repos (REA, Craft Anything, BLA) {#sec-flagged}

These are AI-assisted *tools*, not operating systems: **REA** lets a coding agent take a program apart, **Craft Anything** rebuilds an app by studying the original, and **BLA** poisons your own release files so such agents waste their effort (`02-competitors/flagged-repos.md`). The decision:

1. **Don't use them for competitor teardowns.** Home Assistant OS, umbrelOS and Olares publish their source, and reading it at pinned commits is faster and legally cleaner than decompiling images.
2. **Use REA for one thing: attacking OneMind's own releases**, in a throwaway VM, before hardware ships.
3. **Don't put BLA's decoys in OneMind images.** They contradict the promise that everything on the box is readable by AI (AI-1) and would confuse OneMind's own agents.
4. **Copy the honest part of BLA** as release checks (no source maps, debug ports or secrets in shipped files; everything signed), and Craft Anything's licence allowlist as a guard for the Apache-2.0 code (D-001).

**Requirements served:** RS-2, RS-5, M-3, M-6, F-13, P-3, D-001.
