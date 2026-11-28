<!-- SPDX-License-Identifier: Apache-2.0 -->
# Learning track

Plain-English lessons for Zeus, who is learning OS engineering while building OneMind OS. Each lesson defines its terms, links to the code or evidence it describes, and ends with questions to check yourself. Lessons 07–16 also have "Try it" steps you can run on a Mac.

## Foundations: choosing the base (2026-11-10 to 2026-11-11)
| # | Lesson |
|---|---|
| 01 | [The big four Linux bases](01-linux-bases.md) |
| 02 | [Omarchy, and where it fits](02-omarchy.md) |
| 03 | [Debian vs Ubuntu vs bootc](03-base-os-debian-vs-ubuntu.md) |
| 04 | [Install modes and running in the cloud](04-install-modes-and-cloud.md) |
| 05 | [The official route; why not Fedora or Arch](05-official-route-and-why-not-fedora-arch.md) |
| 06 | [Image building on our hardware](06-image-building-on-our-hardware.md) |

## What we built in the first build week (2026-11-12)
Read in order: each builds on the one before.

| # | Lesson | On `main`? |
|---|---|---|
| 07 | [The image, A/B updates and the health gate](07-image-ab-updates-health-gate.md) | yes, battery-tested in QEMU |
| 08 | [From a Debian fix to your box: security pipeline and TUF](08-security-pipeline-and-tuf.md) | yes; publishing waits for the founder's keys |
| 09 | [The gateway: approvals, agents and MCP](09-gateway-approvals-agents-mcp.md) | yes |
| 10 | [App pipeline, scan gate and install sandbox](10-app-pipeline-scan-gate-sandbox.md) | yes; the install sandbox is on `main` (PR #40), the host firewall part is still open |
| 11 | [The mesh: Headscale, DERP, NATS leaves and the FB-3 lab](11-mesh-headscale-derp-nats-leaf.md) | design, lab and tested parts; `onemind mesh status` and `onemindd mesh` are wired, the gateway side is not |
| 12 | [Backups and restore](12-backups-and-restore.md) | backup agent runs in `onemindd` when its settings file exists; nothing installs one yet |
| 13 | [Identity and passkeys](13-identity-and-passkeys.md) | contract and code on `main` (PR #41); browser sign-in needs HTTPS or localhost |
| 14 | [Notifications and alerts](14-notifications.md) | event plumbing, contract and notifier on `main` (PR #44) |
| 15 | [The design system and the dashboard](15-design-system-and-dashboard.md) | yes |
| 16 | [How we test](16-testing-strategy.md) | unit to system tests yes; fuzz, property and browser e2e not yet |

## Robotics: documented target, not shipped support (2026-11-14)

| # | Lesson |
|---|---|
| 17 | [Robotics as first-class citizens: Debian/Ubuntu qualification and the autonomy boundary](17-robotics-first-class-citizens.md) |

## Founder notes (2026-11-14 onward)
Short answers to founder questions, saved so they are not lost in chat. Folder: [`founder/`](founder/).

| # | Note |
|---|---|
| 01 | [What "onemindd" means, and why GitHub Free is enough for now](founder/01-daemons-and-the-github-plan.md) |
| 02 | [Inside the umbrelOS 2.0.1 images](founder/02-umbrelos-image-teardown.md) |
| 03 | [Olares, Project NOMAD, k3s vs Docker, and where OneMind goes next](founder/03-competitors-and-where-we-go.md) |
| 04 | [Before the big build: code check, process fixes, seeing the OS, open decisions](founder/04-before-the-big-build.md) |
| 05 | [Decision briefs, week of 2026-11-16: Z-41, signing keys, hardware, scoring rules, bootc Pi test, VMs/terminal/Tor](founder/05-decision-briefs-nov-2026.md) |
| 06 | [The test lab, machine by machine: R530 + Proxmox, which box tests what, what to sell](founder/06-test-lab-hardware.md) |
| 07 | [Kanidm and single sign-on: what it is, is it the right pick, and F-34](founder/07-kanidm-and-single-sign-on.md) |
| 08 | [How the OneMind image works, and how open it should be](founder/08-how-the-onemind-image-works.html) (web page with diagrams: the disk, boot, read-only root, A/B updates, what ships, firmware and openness; facts checked 2026-11-21; open it in a browser) |
| 09 | [Why our own OS: distro vs image, bootc, Buildroot, Rugix vs RAUC, k3s, phones, desktop, the gateway](founder/09-why-our-own-os.md) |
| 10 | [Real paths for C2 and physical AI: go-box, site ops, fabric, greenhouse, vision AI, drones, robots](founder/10-c2-and-physical-ai-paths.md) |
| 11 | [JADC2 and OneMind: sense, make sense, act; the data fabric; what to adopt and where we differ](founder/11-jadc2-and-onemind.md) |
| 12 | [Clock, Secure Boot, disk and admin tools, and the `onemind` CLI](founder/12-clock-secure-boot-tools-and-the-cli.md) (Step 2 of the stable-and-live sprint, 2026-11-25) |
| 13 | [The key ceremony, explained for a first-time OS builder](founder/13-the-key-ceremony-explained.md) (what the root keys do, why the owner holds them, YubiKeys vs USB sticks, is it required; 2026-11-25) |
| 14 | [OneMind's own apps](founder/14-onemind-internal-apps.html) (web page: every built-in, built and planned app by state; built-in vs Market vs custom apps; how AI agents reach them; what to build next; 2026-11-26; open it in a browser) |
| 15 | [One app on every device, own vs borrow, and the 3D map](founder/15-one-app-own-vs-borrow-and-3d-maps.md) (issues #1234, #1235; three shells + server-driven screens #641/#642 instead of an app per feature; own the experience, borrow the engine; MapLibre 2D, Cesium outdoor 3D, three.js indoor; 2026-11-26) |

Also from founder questions: [First Android build: the app live on a real phone, why the nightly APK crashed and how to build, install and connect it](android-first-build.md) (2026-11-26).

Also from founder questions: [umbrelOS screens and OneMind: what we have, what is built, what is missing](umbrelos-screen-gaps.md) (2026-11-20).

The "On `main`?" column was checked on 2026-11-12. The leap's live state is in [`docs/leap/STATUS.md`](../leap/STATUS.md).
