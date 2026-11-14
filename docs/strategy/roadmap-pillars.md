<!-- SPDX-License-Identifier: Apache-2.0 -->
# Roadmap pillars: from the Foundation Report to issues

**Date:** 2026-11-14 · **Status:** plan for the founder; changes no decision in [`docs/DECISIONS.md`](../DECISIONS.md) or [`docs/leap/LANES.md`](../leap/LANES.md). New issue IDs are proposals for [`docs/leap/BACKLOG.md`](../leap/BACKLOG.md); IDs that already exist there (CORE-*, DEV-*, PLAN-*) keep their backlog meaning.
**Founder brief (2026-11-14):** compare what the Foundation Report and the repo say against what is built, find the gaps (including competitor features), and organise the next work in GitHub Projects so nothing conflicts.
**Sources:** the Foundation Report **rev 4** (`research-output/report/chapters/`, PDF `research-output/ONEMIND-OS-FOUNDATION-REPORT.pdf`, 111 pages, 2026-11-11; it supersedes the 101-page rev 3), `docs/leap/BACKLOG.md`, `docs/leap/STATUS.md`, the parity plans [`nomad-parity.md`](nomad-parity.md) and [`umbrel-parity.md`](umbrel-parity.md), and code searches on `origin/main` on 2026-11-14.

> ### In plain words
> The work is now split into 13 pillars, one GitHub Project each, plus one master board that shows everything. Each pillar lists the gaps between the report and `main` as issues, with why, scope, depends-on and a done-when checklist. Every issue has a **Horizon**: *Now* (start next), *Next* (after a dependency or a founder decision) or *Later* (parked, year 2, or needs hardware).

## 1. Conflicts and checks, so nothing is built in the wrong direction
| Item | What the sources say | How the issues handle it |
|---|---|---|
| Base OS | Report rev 4 recommends **Ubuntu 26.04** (Z-38 option a); the founder chose **Debian 13** on 2026-11-11 (D-007, Z-38 = b) | Every issue builds on D-007. Ubuntu stays a light CI hedge; Jetson stays on L4T |
| Robotics and TAK | The report makes robots the moat; the founder focus of 2026-11-12 parked PLAN-E7-LAB, PLAN-E14 and PLAN-E15 | Robotics and TAK issues are labelled `parked`, Horizon *Later*, except **ROB-01**, the EU Machinery Regulation decision log, which has a legal date (2027-01-14) |
| LUKS2 decision IDs | LANES.md and ALPHA-CHECKLIST.md call it F-61/F-62; DECISIONS-NEEDED.md uses F-61 for the desktop updater key and has no F-62; the disk-encryption question is F-60 | IMG-05 names all three; the numbering needs a founder or Lane A fix |
| STATUS.md | Last updated 2026-11-12 and behind `main` (for example photos, files and app lifecycle merged but rows read `todo`) | Issues that reuse a backlog ID carry a "check main before claiming" note |
| AI actuation | The rule "AI never actuates without human approval" | Every issue repeats it; motion stays lab-only until LT-VM-18 passes |

## 2. The boards
- **Master:** [OneMind OS Roadmap](https://github.com/orgs/onemindos/projects/2): every item, with fields Pillar, Horizon, Lane, Track and Order.
- **IMG:** [Base OS & Images](https://github.com/orgs/onemindos/projects/3): The read-only Debian 13 image (D-007), boards (x86, Pi 5, Jetson, cloud, VM), installer, kernels, firmware, Secure Boot and disk layout. Specs: docs/learning/07, os/, report ch. 4–5 and 7.
- **REL:** [Updates & Releases](https://github.com/orgs/onemindos/projects/4): RAUC A/B updates, the health gate, TUF signing, the release pipeline, the security channel, offline and USB updates, fleet staging. Specs: docs/leap/core/UPDATES.md, report ch. 7, decisions Z-02, Z-03, Z-04, Z-20, F-27.
- **SEC:** [Security & Compliance](https://github.com/orgs/onemindos/projects/5): Threat model, gateway hardening, audit chain, NATS TLS, identity floor, and the EU Cyber Resilience Act (applies 2027-12-11). Specs: docs/security/, report ch. 7 and 13, decisions Z-04, Z-05, Z-06.
- **BAK:** [Backups & Recovery](https://github.com/orgs/onemindos/projects/6): restic backups with verified restores, whole-box restore, recovery mode, mirror (warm standby). Specs: docs/architecture/BACKUPS.md, report ch. 7, decision Z-13.
- **AIG:** [AI Gateway & Agents](https://github.com/orgs/onemindos/projects/7): The capability gateway: approvals, ledger, MCP, REST, CLI and Agent Skills, agent principals, aiPolicy, the model router, local inference, GPUs. AI never actuates without owner approval. Specs: report ch. 3 (AI layer), research 10.
- **NET:** [Fabric, Mesh & Networking](https://github.com/orgs/onemindos/projects/8): Joining machines into one OneMind: node join, NATS hub and leaf, Headscale mesh, HTTPS names, per-app login, relay and remote access. Specs: docs/architecture/FABRIC.md, NETWORKING.md, report ch. 6.
- **MKT:** [Marketplace & Apps](https://github.com/orgs/onemindos/projects/9): The Market: app manifest, CI app gate, licence classes, quality tiers, the app catalog, OneMind's own modules, and NOMAD and umbrelOS parity apps. Specs: docs/APPS.md, report ch. 3 (Market, own apps), research 13.
- **PLG:** [Plugin Ecosystem & SDK](https://github.com/orgs/onemindos/projects/10): Seven plugin types and the ten sockets E1–E10, plugin CLI, signing and revocation, review pipeline, Works with OneMind certification, revenue share. Specs: docs/leap/dev/PLUGIN-SDK.md, report ch. 9, decisions Z-21, Z-22.
- **ROB:** [Robotics & Physical AI](https://github.com/orgs/onemindos/projects/11): Connect a robot → use OneMind: robot registry, ROS 2 and MAVLink adapters, motion safety gates, the EU Machinery Regulation decision log, Jetson, accelerators. Parked by founder focus except the compliance log; AI actuation stays lab-only until LT-VM-18 passes. Specs: report ch. 9 and 12, research 08.
- **FLD:** [IoT, Field & TAK](https://github.com/orgs/onemindos/projects/12): Greenhouse and TAK node profiles, MQTT 5, industrial protocols, zero-touch onboarding (FDO), off-grid mesh radio, store-and-forward, fleet scale. Specs: report ch. 3 (IoT, TAK), research 09.
- **UX:** [Dashboard, Clients & Family](https://github.com/orgs/onemindos/projects/13): The dashboard (Simple and Pro by role), phone and desktop apps, PWA, family accounts and parental controls, the Omarchy pack, XR. Specs: docs/DASHBOARD.md, docs/strategy/umbrel-parity.md, report ch. 3.
- **BIZ:** [Website, Community & Business](https://github.com/orgs/onemindos/projects/14): Website and downloads, docs, forum, store, support tiers, company setup, trademark, partners. Specs: report ch. 3 (business), research 14 and 17.
- **LAB:** [Hardware Lab & Gates](https://github.com/orgs/onemindos/projects/15): Real-hardware proofs and the 180-day gates G0–G7: Pi 5, Jetson, x86, soak tests, alpha and beta exits. Blocked on F-25 (hardware order). Specs: research-output/20-PLAN-180-DAYS.md, 22-HARDWARE-LAB-TEST-PLAN.md, lab-kits/.

Saved views (board by Status, table by Horizon) are set in the GitHub web page; the CLI cannot create them.

## 3. Issues by pillar
### IMG · Base OS & Images
| Issue | Title | Horizon | Lane / labels |
|---|---|---|---|
| [#148](https://github.com/onemindos/ONEMINDOS/issues/148) | **IMG-01** Secure Boot: signed UKIs on the x86 efi route and the key model | Next | lane:B, needs-founder |
| [#149](https://github.com/onemindos/ONEMINDOS/issues/149) | **IMG-02** Grow the second slot and data partition on first boot | Next | lane:B |
| [#150](https://github.com/onemindos/ONEMINDOS/issues/150) | **IMG-03** Real-time kernel variant for Pi 5 and x86 | Later | lane:B, needs-hardware |
| [#151](https://github.com/onemindos/ONEMINDOS/issues/151) | **IMG-04** Pin and gate board firmware per release (Pi EEPROM, Jetson QSPI) | Next | lane:B, needs-hardware |
| [#152](https://github.com/onemindos/ONEMINDOS/issues/152) | **IMG-05** Encrypted data partition: LUKS2 + btrfs | Next | lane:B, needs-founder |
| also | [#133](https://github.com/onemindos/ONEMINDOS/issues/133) NMD-08; [#136](https://github.com/onemindos/ONEMINDOS/issues/136) NMD-11 | | |

### REL · Updates & Releases
| Issue | Title | Horizon | Lane / labels |
|---|---|---|---|
| [#153](https://github.com/onemindos/ONEMINDOS/issues/153) | **REL-01** Offline TUF root ceremony, 2-of-3 signers and escrow | Now | lane:B, needs-founder |
| [#154](https://github.com/onemindos/ONEMINDOS/issues/154) | **REL-02** Security updates on by default, with opt-out and a window | Next | lane:A, needs-founder |
| [#155](https://github.com/onemindos/ONEMINDOS/issues/155) | **CORE-UPDATE-7** Offline grace and USB/LAN mirror installs | Next | lane:B |
| [#156](https://github.com/onemindos/ONEMINDOS/issues/156) | **CORE-UPDATE-9** Fleet-staged updates and the release service on NATS | Next | lane:A, lane:B |
| [#157](https://github.com/onemindos/ONEMINDOS/issues/157) | **CORE-UPDATE-8** Rescue console in onemindd, outside Kubernetes | Next | lane:A, lane:B |
| also | [#132](https://github.com/onemindos/ONEMINDOS/issues/132) NMD-07; [#142](https://github.com/onemindos/ONEMINDOS/issues/142) UMB-P05 | | |

### SEC · Security & Compliance
| Issue | Title | Horizon | Lane / labels |
|---|---|---|---|
| [#158](https://github.com/onemindos/ONEMINDOS/issues/158) | **SEC-CRA-01** Cyber Resilience Act readiness by 2027-12-11 | Next | lane:A, lane:B, needs-founder |
| [#159](https://github.com/onemindos/ONEMINDOS/issues/159) | **CORE-SEC-6** `onemind audit verify`, signed checkpoints and an agent kill switch | Next | lane:A |
| [#160](https://github.com/onemindos/ONEMINDOS/issues/160) | **CORE-SEC-9** CSP, security headers, body and rate limits on the gateway | Next | lane:A |
| [#161](https://github.com/onemindos/ONEMINDOS/issues/161) | **CORE-SEC-4** NATS nkeys and TLS everywhere | Next | lane:B |

### BAK · Backups & Recovery
| Issue | Title | Horizon | Lane / labels |
|---|---|---|---|
| [#162](https://github.com/onemindos/ONEMINDOS/issues/162) | **BAK-01** Mirror: warm standby with one-click promote | Later | lane:A, lane:B, needs-founder |
| [#163](https://github.com/onemindos/ONEMINDOS/issues/163) | **BAK-02** Monthly whole-box restore drill, under 60 minutes | Next | lane:B |
| [#164](https://github.com/onemindos/ONEMINDOS/issues/164) | **BAK-03** Backups for offline content and models (size-aware tier) | Next | lane:A |
| also | [#145](https://github.com/onemindos/ONEMINDOS/issues/145) UMB-P08; [PR #123](https://github.com/onemindos/ONEMINDOS/pull/123) | | |

### AIG · AI Gateway & Agents
| Issue | Title | Horizon | Lane / labels |
|---|---|---|---|
| [#165](https://github.com/onemindos/ONEMINDOS/issues/165) | **AIG-01** aiPolicy: may this data go to AI? | Next | lane:A |
| [#166](https://github.com/onemindos/ONEMINDOS/issues/166) | **AIG-02** Local model router with data-class rules | Next | lane:A |
| [#167](https://github.com/onemindos/ONEMINDOS/issues/167) | **AIG-03** Hermes as a gateway agent principal | Next | lane:A |
| [#168](https://github.com/onemindos/ONEMINDOS/issues/168) | **AIG-04** Tainted input: content an agent read cannot trigger commands | Next | lane:A |
| [#169](https://github.com/onemindos/ONEMINDOS/issues/169) | **DEV-MCP-10** MCP revision 2026-07-28 support | Next | lane:A |
| also | [#128](https://github.com/onemindos/ONEMINDOS/issues/128) NMD-03; [#130](https://github.com/onemindos/ONEMINDOS/issues/130) NMD-05 | | |

### NET · Fabric, Mesh & Networking
| Issue | Title | Horizon | Lane / labels |
|---|---|---|---|
| [#170](https://github.com/onemindos/ONEMINDOS/issues/170) | **CORE-FABRIC-5** Leaf mode in onemindd for small devices (no k3s) | Next | lane:B |
| [#171](https://github.com/onemindos/ONEMINDOS/issues/171) | **CORE-FABRIC-4** Capability labels and the "runs here / on another machine" verdict | Next | lane:A |
| [#172](https://github.com/onemindos/ONEMINDOS/issues/172) | **CORE-NET-15** Public app exposure through the relay | Later | lane:B |
| also | [#139](https://github.com/onemindos/ONEMINDOS/issues/139) UMB-P02; [PR #88](https://github.com/onemindos/ONEMINDOS/pull/88) | | |

### MKT · Marketplace & Apps
| Issue | Title | Horizon | Lane / labels |
|---|---|---|---|
| [#173](https://github.com/onemindos/ONEMINDOS/issues/173) | **APPS-01** Licence classes per app: only green classes ship preinstalled | Next | lane:A |
| [#174](https://github.com/onemindos/ONEMINDOS/issues/174) | **APPS-02** Quality tiers for apps and plugins (Bronze, Silver, Gold) | Next | lane:A |
| [#175](https://github.com/onemindos/ONEMINDOS/issues/175) | **PLAN-E6** Manifest v1 freeze with one validator | Next | lane:A |
| [#176](https://github.com/onemindos/ONEMINDOS/issues/176) | **APPS-03** OneMind modules: finance, wellness, OSINT, family | Next | lane:A |
| also | [#126](https://github.com/onemindos/ONEMINDOS/issues/126) NMD-01; [#127](https://github.com/onemindos/ONEMINDOS/issues/127) NMD-02; [#129](https://github.com/onemindos/ONEMINDOS/issues/129) NMD-04; [#134](https://github.com/onemindos/ONEMINDOS/issues/134) NMD-09; [#140](https://github.com/onemindos/ONEMINDOS/issues/140) UMB-P03; [#143](https://github.com/onemindos/ONEMINDOS/issues/143) UMB-P06; [#147](https://github.com/onemindos/ONEMINDOS/issues/147) UMB-P10; [#117](https://github.com/onemindos/ONEMINDOS/issues/117) app gate failures; [PR #124](https://github.com/onemindos/ONEMINDOS/pull/124); [PR #125](https://github.com/onemindos/ONEMINDOS/pull/125) | | |

### PLG · Plugin Ecosystem & SDK
| Issue | Title | Horizon | Lane / labels |
|---|---|---|---|
| [#177](https://github.com/onemindos/ONEMINDOS/issues/177) | **DEV-PLG-1** Plugin manifest: extensions, permissions, plugin, compat + validator | Next | lane:A |
| [#178](https://github.com/onemindos/ONEMINDOS/issues/178) | **DEV-PLG-3** Gateway plugin registry and the plugin principal | Next | lane:A |
| [#179](https://github.com/onemindos/ONEMINDOS/issues/179) | **DEV-PLG-5** Widget host: sandboxed iframes and a postMessage bridge (E5) | Next | lane:A |
| [#180](https://github.com/onemindos/ONEMINDOS/issues/180) | **DEV-PLG-7** OCI pack, signing and install by digest | Next | lane:A |
| [#181](https://github.com/onemindos/ONEMINDOS/issues/181) | **DEV-PLG-8** `onemind plugin init` and `plugin dev` | Next | lane:A |
| [#182](https://github.com/onemindos/ONEMINDOS/issues/182) | **DEV-PLG-9** Revocation list (kill switch) and countersignature | Next | lane:A |
| [#183](https://github.com/onemindos/ONEMINDOS/issues/183) | **DEV-PLG-12** Scan gate for plugin artifacts | Next | lane:A |
| [#184](https://github.com/onemindos/ONEMINDOS/issues/184) | **DEV-PLG-13** Plugin test harness and `onemind plugin test` | Next | lane:A |
| [#185](https://github.com/onemindos/ONEMINDOS/issues/185) | **DEV-PLG-14** Publish from CI (OIDC), public plugin index, review pipeline | Next | lane:A |
| [#186](https://github.com/onemindos/ONEMINDOS/issues/186) | **PLG-SOCK-01** Host sockets E2–E4: capability broker, signed sysext, driver packs | Next | lane:A, lane:B, needs-founder |
| [#187](https://github.com/onemindos/ONEMINDOS/issues/187) | **PLG-CERT-01** "Works with OneMind" certification and the revenue share | Later | needs-founder |

### ROB · Robotics & Physical AI
| Issue | Title | Horizon | Lane / labels |
|---|---|---|---|
| [#188](https://github.com/onemindos/ONEMINDOS/issues/188) | **ROB-01** Robot decision log for the EU Machinery Regulation | Now | lane:A |
| [#189](https://github.com/onemindos/ONEMINDOS/issues/189) | **ROB-02** Robot registry and map (OneMind's own module) | Later | lane:A, parked |
| [#190](https://github.com/onemindos/ONEMINDOS/issues/190) | **ROB-03** ROS 2 bridge adapter, observe-only first | Later | lane:A, parked |
| [#191](https://github.com/onemindos/ONEMINDOS/issues/191) | **PLAN-E7-LAB** Motion safety gates and typed capabilities behind the lab flag | Later | lane:A, parked |
| [#192](https://github.com/onemindos/ONEMINDOS/issues/192) | **ROB-04** "Connect a robot" QR onboarding (LeRobot SO-100/101, TurtleBot 4) | Later | lane:A, needs-hardware, parked |
| [#193](https://github.com/onemindos/ONEMINDOS/issues/193) | **ROB-05** MAVLink / PX4 drone adapter | Later | lane:A, parked |
| [#194](https://github.com/onemindos/ONEMINDOS/issues/194) | **PLAN-E15** Robot in simulation (Isaac Sim / Gazebo) | Later | lane:A, parked |
| [#195](https://github.com/onemindos/ONEMINDOS/issues/195) | **ROB-06** Jetson flavor: track the current JetPack major within 60 days | Later | lane:B, needs-hardware, needs-founder |
| [#196](https://github.com/onemindos/ONEMINDOS/issues/196) | **ROB-07** Accelerator capabilities: ONNX + per-backend engines, no hard CUDA | Next | lane:A |

### FLD · IoT, Field & TAK
| Issue | Title | Horizon | Lane / labels |
|---|---|---|---|
| [#197](https://github.com/onemindos/ONEMINDOS/issues/197) | **FLD-01** Greenhouse profile | Next | lane:A, lane:B, needs-hardware |
| [#198](https://github.com/onemindos/ONEMINDOS/issues/198) | **PLAN-E14** TAK node profile (TAK Server or OpenTAKServer) | Later | lane:A, needs-hardware, parked |
| [#199](https://github.com/onemindos/ONEMINDOS/issues/199) | **FLD-02** MQTT 5 broker app bridged to NATS | Next | lane:A |
| [#200](https://github.com/onemindos/ONEMINDOS/issues/200) | **CORE-FDO-1** Zero-touch onboarding (FDO) client | Next | lane:B |
| [#201](https://github.com/onemindos/ONEMINDOS/issues/201) | **FLD-03** Industrial protocol adapters: OPC UA, Modbus, CAN, BACnet | Later | lane:A |
| [#202](https://github.com/onemindos/ONEMINDOS/issues/202) | **FLD-04** Native off-grid mesh: batman-adv + Meshtastic and LoRaWAN gateways | Later | lane:B, needs-hardware |
| [#203](https://github.com/onemindos/ONEMINDOS/issues/203) | **FLD-05** 10,000-device fleet test | Later | lane:B |
| also | [#131](https://github.com/onemindos/ONEMINDOS/issues/131) NMD-06; [#137](https://github.com/onemindos/ONEMINDOS/issues/137) NMD-12 | | |

### UX · Dashboard, Clients & Family
| Issue | Title | Horizon | Lane / labels |
|---|---|---|---|
| [#204](https://github.com/onemindos/ONEMINDOS/issues/204) | **FAM-01** Family roles and parental controls | Next | lane:A |
| [#205](https://github.com/onemindos/ONEMINDOS/issues/205) | **FAM-02** Child internet filtering through the box's DNS, also away from home | Next | lane:A |
| [#206](https://github.com/onemindos/ONEMINDOS/issues/206) | **UX-01** Simple and Pro by role: Control Hub and AI & Agents audit | Next | lane:A |
| [#207](https://github.com/onemindos/ONEMINDOS/issues/207) | **UX-02** Omarchy client and plugin pack | Later | lane:A |
| [#208](https://github.com/onemindos/ONEMINDOS/issues/208) | **UX-03** iPhone push through a content-free relay | Later | lane:A, needs-founder |
| [#209](https://github.com/onemindos/ONEMINDOS/issues/209) | **UX-04** WebXR: 3D infrastructure map and robot views | Later | lane:A |
| also | [#138](https://github.com/onemindos/ONEMINDOS/issues/138) UMB-P01; [#141](https://github.com/onemindos/ONEMINDOS/issues/141) UMB-P04; [#144](https://github.com/onemindos/ONEMINDOS/issues/144) UMB-P07; [#146](https://github.com/onemindos/ONEMINDOS/issues/146) UMB-P09 | | |

### BIZ · Website, Community & Business
| Issue | Title | Horizon | Lane / labels |
|---|---|---|---|
| [#210](https://github.com/onemindos/ONEMINDOS/issues/210) | **BIZ-01** Website hosting and domain | Now | needs-founder |
| [#211](https://github.com/onemindos/ONEMINDOS/issues/211) | **BIZ-02** Forum and "Open in OneMind" links | Later | lane:A |
| [#212](https://github.com/onemindos/ONEMINDOS/issues/212) | **BIZ-03** Support tiers and the store | Later | needs-founder |
| [#213](https://github.com/onemindos/ONEMINDOS/issues/213) | **BIZ-04** Company setup: incorporate, trademark, NVIDIA Inception, vendor quotes | Now | needs-founder |
| also | [#135](https://github.com/onemindos/ONEMINDOS/issues/135) NMD-10; [PR #122](https://github.com/onemindos/ONEMINDOS/pull/122) | | |

### LAB · Hardware Lab & Gates
| Issue | Title | Horizon | Lane / labels |
|---|---|---|---|
| [#214](https://github.com/onemindos/ONEMINDOS/issues/214) | **LAB-01** Order the hardware (F-25) | Now | needs-founder |
| [#215](https://github.com/onemindos/ONEMINDOS/issues/215) | **CORE-UPDATE-4** Gate G1 on metal: x86 update engine and the Pi soak start | Next | lane:B, needs-hardware |
| [#216](https://github.com/onemindos/ONEMINDOS/issues/216) | **PLAN-E10** Gate G2: Pi 5 image with RAUC tryboot and the wizard | Next | lane:B, needs-hardware |
| [#217](https://github.com/onemindos/ONEMINDOS/issues/217) | **PLAN-E11** Gate G3: Jetson and the platform floor | Next | lane:B, needs-hardware |
| [#218](https://github.com/onemindos/ONEMINDOS/issues/218) | **LAB-02** 200 forced-bad updates with zero bad commits | Next | lane:B |
| [#219](https://github.com/onemindos/ONEMINDOS/issues/219) | **LAB-03** Alpha exit: 25 outside users and a second operator unaided | Later | needs-founder |

## 4. Where to start
1. **Founder, this week:** LAB-01 (order hardware; the Pi soak must start by 2026-12-11), REL-01 (signing ceremony), BIZ-01 (domain), BIZ-04 (company setup). Each unblocks many issues.
2. **Lane A, now:** UMB-P01 (lifecycle buttons), UMB-P04 (dashboard pages), UMB-P10 (unblock the Market), ROB-01 (decision log), then the NMD and AIG items.
3. **Lane B, now:** finish #88 (mesh, HTTPS, join), then CORE-FABRIC-5 (leaf mode), REL items and IMG-02.
4. **Wait:** everything labelled `needs-hardware` until LAB-01 lands; everything `parked` until the founder un-parks it.

## 5. Words used
- **Pillar:** one area of the product with its own board.
- **Horizon:** when to start: Now, Next or Later.
- **Lane:** which build agent owns it (docs/leap/LANES.md).
- **CRA:** the EU Cyber Resilience Act, which applies to products sold in the EU from 2027-12-11.
- **Machinery Regulation:** EU rules for machines, including robots, from 2027-01-14.
