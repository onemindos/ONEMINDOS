# FreedomBox: Tier C teardown

**Workstream:** W1 (Tier C) · **Tag:** `TD-tier-c-alt` · **Date:** 2026-11-11 · **Status:** draft, brief (Tier C; no refuter pass required)
**Claims:** `evidence/claims/TD-tier-c-alt.csv` (FreedomBox rows 029–041) · **Sources:** `evidence/sources/TD-tier-c-alt.md`
**Pinned:** `salsa.debian.org/freedombox-team/freedombox@fadba12ed288d0186b858dc79001811c5963cf8e` (package 26.15, 2026-11-02) [C-TD-tier-c-alt-031]
**License note:** AGPL-3.0-or-later [C-TD-tier-c-alt-029]. Study the patterns; do not copy code into OneMind's Apache-2.0 core.

> ### Explain it like I'm the founder
> FreedomBox is the **oldest "personal server for non-experts"** still alive, and it is **an official part of Debian**, the same base OneMind picked [C-TD-tier-c-alt-030]. You flash an image onto a cheap board or PC, open a web page, and install apps like a VPN, chat, file sharing, a wiki or offline Wikipedia (Kiwix) with a few clicks.
>
> **How it stays safe:** it is just Debian with a web control panel. Updates are ordinary Debian security updates, installed automatically, and it can even move itself to the next Debian release on its own [C-TD-tier-c-alt-033]. If the disk uses btrfs, it takes a **snapshot** first, so you can go back by hand [C-TD-tier-c-alt-034][C-TD-tier-c-alt-035].
>
> **The lesson for OneMind:** FreedomBox proves that "Debian + a web panel + automatic updates" can run for over a decade (copyright from 2011 [C-TD-tier-c-alt-029]) on volunteer effort. It also shows the limits: slow adoption, weak hardware (its own box has 1 GB of RAM), no Pi 5 image, no AI, and rollback only if you happened to pick btrfs [C-TD-tier-c-alt-038][C-TD-tier-c-alt-039][C-TD-tier-c-alt-041].
>
> **For OneMind:** copy the "app = a small module that knows how to install, configure, back up and diagnose a service" idea, the automatic distro-upgrade with a snapshot first, and the backup-battery box design for off-grid use. Do better with a read-only image and A/B rollback that always works.

---

## 1. What it is, in one table

| Topic | What FreedomBox does | Evidence |
|---|---|---|
| **Architecture** | A Django web panel ("FreedomBox Service", formerly Plinth; Django per `pyproject.toml` at the pinned commit) with separate privileged helper functions, on a normal Debian system; 70 modules (apps plus system modules such as firewall, upgrades, backups) | [C-TD-tier-c-alt-041][C-TD-tier-c-alt-032] |
| **Base OS** | **Debian** (stable images, testing/unstable for development); package is in Debian itself | [C-TD-tier-c-alt-030][C-TD-tier-c-alt-031] |
| **Update / rollback** | `unattended-upgrades` + `needrestart`; an hourly check can run an **automatic dist-upgrade** to the next Debian stable. A snapper snapshot is taken first **only on a btrfs root**; rollback is a manual snapper action. No A/B, no health-gated commit | [C-TD-tier-c-alt-033][C-TD-tier-c-alt-034][C-TD-tier-c-alt-035] |
| **App format** | Python module (an `App` subclass) declaring Debian packages, firewall ports, web server config, backup paths and diagnostics; e.g. Kiwix installs `kiwix-tools`. A few apps (Home Assistant, Nextcloud) are **podman containers** from FreedomBox's own registry, "not reviewed by Debian" | [C-TD-tier-c-alt-032][C-TD-tier-c-alt-037] |
| **Backups** | borgbackup to local disk or a remote server over sshfs | [C-TD-tier-c-alt-036] |
| **AI features** | **None** (no AI, LLM or MCP module) | [C-TD-tier-c-alt-041] |
| **Hardware** | Any Debian-capable machine; images for amd64, arm64, armhf, i386, Pi 2/3/4 and other boards; **no Pi 5 image listed**. Sold boxes: Olimex **Pioneer Edition** (Allwinner A20, SD card, backup battery for 4–5 h) and **Libre Crafts** (built by FreedomBox developers) | [C-TD-tier-c-alt-038][C-TD-tier-c-alt-039][C-TD-tier-c-alt-040] |
| **Licence** | AGPL-3.0-or-later | [C-TD-tier-c-alt-029] |
| **Business model** | Non-profit foundation, donations; hardware sold by partners | [C-TD-tier-c-alt-030][C-TD-tier-c-alt-040] |
| **Team / activity** | Active: release 26.15 on 2026-11-02, with translations from many volunteers | [C-TD-tier-c-alt-031] |

## 2. Strengths and weaknesses

| Strengths | Weaknesses |
|---|---|
| Inside Debian: packaging, security team and long life come for free [C-TD-tier-c-alt-030] | Mutable root; rollback depends on btrfs being chosen at install [C-TD-tier-c-alt-035] |
| Fully automatic security and release upgrades, snapshot first [C-TD-tier-c-alt-033][C-TD-tier-c-alt-034] | No health gate: nothing checks the box works after an upgrade [C-TD-tier-c-alt-033] |
| Apps carry their own backup and diagnostics hooks [C-TD-tier-c-alt-032] | Catalogue limited to what Debian packages, plus a few containers [C-TD-tier-c-alt-037] |
| Backup battery in the reference box: good for outages [C-TD-tier-c-alt-039] | Weak reference hardware; no Pi 5; no GPU, AI or robotics [C-TD-tier-c-alt-038][C-TD-tier-c-alt-041] |

## 3. What competitors do (Debian-based personal servers)

| Product | Base | Update safety | AI | Constraint fit to OneMind |
|---|---|---|---|---|
| **FreedomBox** | Debian packages on a normal root [C-TD-tier-c-alt-030] | Auto upgrades; snapshot only on btrfs [C-TD-tier-c-alt-033][C-TD-tier-c-alt-035] | None [C-TD-tier-c-alt-041] | **Candidate** for app-module and auto-upgrade patterns; **low** for the image |
| **umbrelOS 2.0** | Debian 13 image [C-TD-umbrelos-003] | Rugix A/B [C-TD-umbrelos-010] | Built-in MCP [C-TD-umbrelos-039] | **Default** (same base, same team scale) |
| **StartOS** | Debian 13 via live-build [C-TD-startos-005] | Pointer flip; no OS rollback [C-TD-startos-016][C-TD-startos-019] | MCP [C-TD-startos-029] | **Candidate** |

## 4. Constraint fit and what OneMind does with it

**Constraint fit: Medium.** Same base (Debian) and the same "non-expert self-hoster" user, and a volunteer team even smaller than OneMind's. It does not match on Kubernetes, robotics, AI, GPUs or image-based updates.

| ID | Recommendation | Evidence | Req IDs |
|---|---|---|---|
| REC-TDC-FBX-01 | Each OneMind app manifest declares, besides how to install it, **its backup paths, firewall ports, health/diagnostic checks and uninstall cleanup**, so backup, firewall and the health view work for every app without app-specific code. | [C-TD-tier-c-alt-032][C-TD-tier-c-alt-036] | A-1, A-2, UX-6, R-2 |
| REC-TDC-FBX-02 | Plan the **Debian 13 → 14 move as an image update**, not an in-place `dist-upgrade`: FreedomBox's automatic dist-upgrade works only because Debian packages can be upgraded in place, and its safety net exists only on btrfs. OneMind's A/B image gives every box the rollback FreedomBox gives only some. | [C-TD-tier-c-alt-033][C-TD-tier-c-alt-035] | R-1, R-3, F-14 |
| REC-TDC-FBX-03 | Offer a **backup-battery or UPS-aware** option for the Edge/Lite boxes and the greenhouse profile, with clean shutdown on low battery; FreedomBox's reference box shows it is cheap to include. | [C-TD-tier-c-alt-039] | N-6, F-13, H-1 |
| REC-TDC-FBX-04 | Label **third-party container apps** clearly in the Market ("updated and reviewed by upstream, not OneMind"), as FreedomBox does for Home Assistant; this sets the right expectation for quality tiers. | [C-TD-tier-c-alt-037] | A-6, U-4 |

## Glossary

| Term | Meaning |
|---|---|
| **dist-upgrade** | Moving a Debian system to the next major release (e.g. 13 → 14) by upgrading packages in place. |
| **unattended-upgrades** | Debian's tool that installs security updates automatically. |
| **btrfs / snapper** | btrfs is a file system that can take instant snapshots; snapper is the tool that manages and rolls back to them. |
| **borgbackup** | A deduplicating, encrypted backup tool (OneMind chose restic for the same job). |
| **podman** | A Docker-compatible container engine that runs without a central daemon. |
| **AGPL** | A copyleft licence; patterns may be studied, code not copied into Apache-2.0 OneMind. |
