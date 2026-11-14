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

## Founder notes (2026-11-14 onward)
Short answers to founder questions, saved so they are not lost in chat. Folder: [`founder/`](founder/).

| # | Note |
|---|---|
| 01 | [What "onemindd" means, and why GitHub Free is enough for now](founder/01-daemons-and-the-github-plan.md) |
| 02 | [Inside the umbrelOS 2.0.1 images](founder/02-umbrelos-image-teardown.md) |

The "On `main`?" column was checked on 2026-11-12. The leap's live state is in [`docs/leap/STATUS.md`](../leap/STATUS.md).
