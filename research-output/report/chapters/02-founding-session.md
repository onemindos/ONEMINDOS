# Everything from the founding session {#sec-founding}

> **Explain it like I'm the founder.** On 10 November 2026 you spent one long session talking through phones, earlier plans, strategy, competitors, Linux, Kubernetes, robots, IoT, VillageOS, kernels and plugins. This chapter walks that conversation in order (from `context/00-CONVERSATION-RECORD.md`) and, for each topic, says **what the research found** and **where the full answer lives**. Appendix A is the checklist proving every topic is covered.

## Phones and Android sovereignty (where it started) {#sec-phones}

**What you said.** You use a Samsung S24 Ultra, love Android's freedom and run ATAK. GrapheneOS on a Pixel was suggested as a hardened ATAK field device, and you remembered an ATAK crash report on a GrapheneOS Pixel Tablet.

**What the research found** (`15-phones-field-devices.md`):

- **The phone is a client, not the OS we build.** OneMind OS runs on boxes; phones connect through the OneMind app and ATAK/iTAK. Nothing about phones changes the foundation.
- **Your field phone: a Pixel 8 or newer with GrapheneOS.** GrapheneOS recommends only Pixel 8 and later, which carry a 7-year support guarantee and hardware memory tagging [C-W14-002].
- **The Pixel Tablet crash could not be found anywhere public** (GrapheneOS tracker, ATAK tracker, the web) [C-W14-018]. More important: **the Pixel Tablet has no GPS and no cellular modem** [C-W14-011], so it can never be a standalone ATAK field device. ATAK's own location code warns, rather than crashes, when GPS is missing [C-W14-015]. A one-hour test in `15-…` Appendix A tells the likely causes apart (memory-protection toggle, a tablet OS bug, or a plugin).
- **The real GrapheneOS + ATAK gotcha is networking, not crashes:** multicast over a VPN is blocked by GrapheneOS's leak protection (open issue) [C-W14-010].
- **Your S24 Ultra stays a great stock ATAK phone.** A US S24 Ultra cannot take a custom OS; forcing one trips Samsung's one-time Knox e-fuse for good [C-W14-021]. Use no-root tools (Shizuku, UAD-ng, Obtainium, Shelter, Tasker, DeX).
- **Fairphone and friends:** CalyxOS is back and supports Fairphone 4–6 and Pixels [C-W14-027]; iodéOS, /e/OS and Volla are covered in `15-…` as client options.
- **Linux phones are not ATAK phones in 2026.** postmarketOS has renamed itself Nura [C-W14-029]; FuriLabs FLX1s runs FuriOS on 8 GB [C-W14-030]; but Waydroid has no GPS pass-through, open since 2021 [C-W14-031]. On a Linux phone, the TAK answer is **CloudTAK in the browser**.
- **Termux and Android's built-in Linux Terminal (AVF):** the Terminal runs an experimental Debian VM behind developer options [C-W14-033]. It is a developer convenience, not a OneMind node runtime: do not plan a "phone as a k3s node" (REC-W14-09).

### The mobile OS landscape, HarmonyOS and the dead OSes {#sec-harmonyos}

- **HarmonyOS NEXT** dropped Android compatibility entirely and runs only native apps (SECONDARY, unverified) [C-W14-037]. Its open sibling's discovery layer, DSoftBus, is Apache-2.0 [C-W14-036]. **Lesson written into OneMind's architecture:** no single store, push service or cloud in the client path; OneMind gets Huawei's "super device" outcome with NATS, QR onboarding and the capability layer (REC-W14-10).
- **The microkernel lesson:** even Huawei kept Linux API/ABI compatibility to reuse drivers [C-W18-036] (Chapter 5).
- **Android forks and the rest:** GrapheneOS, LineageOS, /e/OS, CalyxOS and iodéOS are client options compared in `15-…`; KaiOS serves feature phones and is out of scope. A custom Android ROM stays deferred, as the earlier planning documents also concluded.
- **Dead OSes** (BlackBerry 10/QNX, Windows Phone, Symbian, webOS, Firefox OS, Tizen) and Fuchsia teach the same thing: an OS without an app and driver ecosystem dies. Fuchsia's Zircon shipped commercially on one device class (SECONDARY) [C-W18-039].

### "Build your own OS" levels and the OneMind EUD {#sec-eud}

| Level | What it is | Verdict for OneMind |
|---|---|---|
| 1. Launcher + device-owner app on stock Android or GrapheneOS | OneMind app + open-source device management (Headwind MDM, Apache-2.0) | **Build first** (REC-W14-08) |
| 2. AOSP/GrapheneOS fork signed with your own keys | GrapheneOS ships about 80 releases a year [C-W14-040]; a solo founder cannot keep a fork secure | Not before year 2, only for a paying customer |
| 3. Linux-phone distro | No ATAK with GPS today [C-W14-031] | No |
| 4. From scratch | Huawei's path [C-W14-037] | Never |

**The "OneMind EUD" becomes a kit**, not an OS: a Pixel with GrapheneOS, the OneMind app, ATAK and plugins, enrolled by QR into the customer's box. A small vendor already sells exactly that shape (Pixel 9 + GrapheneOS + ATAK) for about USD 1,500 (`15-…` §11).

## The earlier planning documents (the Blueprint) {#sec-blueprint}

**What you decided:** the Nov 3–4 **Blueprint is canonical**; the Build Handoff is outdated (old pillars, "no k8s", NATS "later", Letta primary, ClickUp). The critique was too much hedging and a 90-day plan too big for one engineer.

**What the research did with it** (`20-PLAN-180-DAYS.md`): the 180-day plan keeps the Blueprint's milestone order (M0 reconcile → M1 secure vertical slice → M2 extensions → M3 disconnected client → M4 independent owner → M5 managed appliance) and maps all 24 acceptance tests A01–A24, but moves dates, because the Blueprint's plan did not include the OS image, A/B updates, Secure Boot, Pi 5, Jetson or GPU work. **M6 (multi-site federation) is outside the 180 days**, following the Blueprint's own rule "if M1 or recovery fails, cut breadth". The four questions repeated across the old documents (is Google/Pixel hardware acceptable, the Dell's state, the first vertical slice, which task system) are answered or scheduled in Chapter 14.

## The strategy conversation {#sec-strategy}

- **OneMind is a platform first and an image second.** The research confirms the order for development (platform built first in a VM, image from the same layers from about week 3) but makes the **image the product**: every competitor that ran both a script install and an image later dropped the script. Home Assistant ended its Core and Supervised installs because they "generate more issues" [C-REF-DC-longevity-004], and Umbrel dropped script installs at 1.0 [C-REF-DC-longevity-005].
- **The moat: homestead + AI agents + TAK/field ops + self-hosting, and robots.** Across 11 competitor code bases, zero files mention ROS 2 or MAVLink [C-MATRIX-002]; robotics is open ground (Chapter 10).
- **AI is the turning point** ("who owns my AI's memory"): OneMind's answer is that memory, models and data live on the owner's box by default, and a model router keeps health and family data local (Chapter 3).
- **Market view.** Most people won't leave Apple and Google; the first customers are people with a strong reason to (homesteaders, privacy-minded families, TAK teams, small businesses, sovereignty-minded governments). `17-…` recommends homesteaders and self-hosters first, then TAK teams, robotics through partners in years 2–3, and public safety later, because enterprise sales sank Sandstorm [C-W16-050].
- **Business model:** open core + boxes + support + education, the Home Assistant playbook. Its foundation took in CHF 8.84 million in 2025 from about 2.28 million homes [C-W16-013] (Chapter 3).
- **You want an Umbrel/Home Assistant/CasaOS-like product** with NATS and your services plug-and-play, access from any device, simple → powerful hardware tiers, robot and agent simulation, and XR. All of these have homes in Chapters 3, 8, 9 and 12.
- **NVIDIA at KubeCon NA 2026 (Salt Lake City, 9–12 Nov).** NVIDIA released NVKE/NVKR as a public preview, "not yet recommended for production" [C-W4-039], and Agent Substrate entered the CNCF Sandbox [C-W4-040]; the larger 2026 moves came at KubeCon Europe, where the DRA GPU driver was donated to Kubernetes and KAI Scheduler entered the CNCF Sandbox [C-W4-032]. **The warning stands:** these tools validate Ubuntu, RHEL, SLES, Talos and RKE2, not Debian or k3s (`05` §7), and NVIDIA lock-in is the opposite of sovereignty, so OneMind's app manifests must run on AMD, Intel, Hailo and Rockchip too (Chapter 12).
- **Fedora CoreOS / Fedora IoT as the core.** Answered in full in Chapter 4: a profile and a canary, not the base, today.

## Your existing cloud cluster: the proven concept, and why an OS now {#sec-cluster}

Your DigitalOcean cluster already runs NATS JetStream, Argo CD, Backstage, Hermes, an MCP server, TAK Server with CloudTAK, Authentik and Tailscale (`context/01`, reported state). It proves the *software*. What it cannot give is what only the machine owner can: atomic OS updates with rollback, hardware detection, first-boot onboarding, working through internet loss, physical device access and per-device keys (`05` §12). The two products that won households, Home Assistant OS and umbrelOS, ship their own image and keep the app runtime simple [C-W4-043, C-W4-044]; Olares, which only installs on a stock distro, needs 8 GB and has no OS rollback [C-W4-042].

- **Converting the cluster is not "three changes".** Your own read-only inventory lists 13 dependencies, four of them real work (control plane, 95 block volumes, load balancers, snapshots) [C-W4-063]. The plan is six phases, app by app, with the NATS bus authority flipping last (Chapter 6).
- **Fix this first:** the public ingress-nginx controller has been unmaintained since March 2026 [C-W4-016]. It is risk RR-04, critical, and live today.
- **Backstage stays** as the developer and enterprise portal in the cloud tier; it needs at least 6 GB RAM just to run [C-W4-059], too much for a home box. The OneMind dashboard becomes the front door.
- **Hermes moves as-is.** The upstream agent image already builds for amd64 and arm64 on Debian trixie [C-W4-058]; its NATS contracts become the OS's internal bus contract.

## The big brief (82, now 97, requirement IDs) {#sec-big-brief}

Every item you listed has an owner in the research and a place in this report:

| You asked for | Where it is answered |
|---|---|
| Reverse-engineer competitors; research all Linux distros | Chapter 10; Chapter 4 |
| Sell hardware and become a distributor | Chapter 8 (no own boxes in year 1; certified list first) |
| OS profiles for a box or a Pi (situational awareness, greenhouse) | [Walkthrough](#sec-walkthrough); Chapter 3 (TAK node, greenhouse) |
| Robotics, drones, physical AI as the moat | Chapter 12; Chapter 9 (robot plug-and-play) |
| Every device is a node; mesh native | Chapter 6; Chapter 3 (mesh) |
| Every app readable by AI (MCP, CLI, API, SSH, MHS) with permissions | Chapter 3 (AI capability layer) |
| Native alert system | Chapter 3 (dashboard and alerts) |
| Cloud apps (Strava) with API keys shown and given to AI | Chapter 3 ("may this go to AI?" flag) |
| Internal apps: finance, wellness, robotics, infrastructure, PM, mesh, IoT, family, OSINT | Chapter 3 |
| Multi-user family, parental controls, kids' education | Chapter 3 |
| Hardware capability auto-detection; QR onboarding | Chapter 8; Chapter 9 |
| Multiple machines in one UI, mirror, infrastructure map | Chapter 3 |
| Lite/Pro/Omni editions; NVIDIA as a partner | Chapter 8; Chapter 12 |
| Website (blog, Circle.so, docs, downloads, store, affiliates, Zoho Forms, support, CMS) | Chapter 3 |
| Omarchy-style plugin ecosystem; WebXR and Android XR | Chapter 9; Chapter 3 |
| Updates users control; strong support | Chapter 7; Chapter 14 (Z-02) |
| Become the industry standard for sovereign operations | Chapter 11 (roadmap exit criteria) |
| **No guessing. Do research.** | Every claim ID; Appendix C |

**The Olares images you shared** (Market catalog, Olares + Home Assistant, Olares One): the Market research read both catalogs line by line, 399 Umbrel apps and 396 Olares apps with only 56 in common [C-W12-001, C-W12-008]. Olares's app repository is Apache-2.0 and reusable with credit [C-W12-004]; Umbrel's has no licence at all, so its files cannot be copied [C-W12-002]. Olares One is benchmarked in Chapter 8.

## What phase-1 research reported, re-checked {#sec-phase1}

| Phase-1 fact | Status after this run |
|---|---|
| umbrelOS is PolyForm-Noncommercial; Olares AGPL-3.0 with a leftover non-commercial file | Confirmed [C-TD-umbrelos-045, C-TD-olares-047]; Olares moved its main licence to AGPL in 2025 [C-W16-006] |
| Kairos is Apache-2.0 | Confirmed [C-TD-kairos-002]; its Pi 5 support is still an open issue since 2023 [C-REF-DC-longevity-008], so it was dropped as a lead |
| Project N.O.M.A.D. is Apache-2.0 | Confirmed [C-TD-project-nomad-002] |
| MHS = Anthropic's Model Hardware Standard, research preview 2026-08-27 | Confirmed; no public spec yet, Hugging Face (LeRobot) and Raspberry Pi are early adopters [C-W7-047] |
| Strava bars AI use of its data (secondary sources then) | Now **primary**: the Strava API Policy in force since 2026-06-01 bans its data in any AI context window, even with consent [C-W12-044] |
| MCP spec 2026-07-28; MCP donated to the Linux Foundation's Agentic AI Foundation | Confirmed [C-W9-001, C-W9-009] |

## Founder decisions D-001 to D-006 {#sec-decisions-d}

| ID | Decision (`docs/DECISIONS.md`) | What the research did with it |
|---|---|---|
| **D-001** | Open core, Apache-2.0 | Kept. Your protection is the **trademark**, not the licence: Apache-2.0 grants no right to your name [C-W16-001]. Use a DCO, not a CLA, as Home Assistant effectively does [C-W16-003]. The CRA makes the open/paid boundary a compliance question too (Z-05). |
| **D-002** | Design all tiers together | Kept. One image pipeline, many profiles; x86, Pi 5 and Jetson are all in the week-4 to week-8 bake-off (Chapter 11). |
| **D-003** | One app shell with modules; scaffold all | Kept. Each module is also a Market app; build the thin parts, integrate proven engines for the heavy ones (Chapter 3). |
| **D-004** | Hardware on hand: Mac, Android, Beelink U55, Dell 5540, cloud | Kept. The Dell is your best Secure Boot test bed (custom keys allowed) [C-W10-043]; the Beelink's i3-5005U is a "worst-case old box" (no listed TPM firmware) [C-W10-041]. Buy a Pi 5 and a Jetson Orin Nano Super now. |
| **D-005** | iOS push via APNs with an opaque payload | Kept. Catch: Apple accepts pushes only signed with OneMind's developer key, so a tiny content-free relay is needed (Chapter 3). |
| **D-006** | Apply to NVIDIA Inception and the MHS preview | Kept. Inception is free but requires incorporation and a working website [C-W16-031]. |

## The learning track {#sec-learning}

You are learning OS engineering as you go (Lesson 01: the big four bases; Lesson 02: Omarchy). `27-LEARNING-PATH.md` turns this into **12 modules in build order**, each with why-now, reading (official material first), one hands-on exercise in the Linux VM on your Mac, vocabulary and self-check questions. The fastest single resource is Bootlin's free embedded-Linux training [C-W17-001]; the single most important module is **L5, A/B updates with RAUC**, because it is what keeps boxes in homes from bricking. Omarchy is a desktop *client* edition (Chapter 3), not the box base.

## ADR-001 and your questions about it {#sec-adr}

ADR-001 was **proposed, not approved**; you said "I have questions". Here are the questions and the answers in one line each:

| Your question | Short answer | Chapter |
|---|---|---|
| Why Ubuntu vs Debian? | Ubuntu scores slightly higher on hardware fit and NVIDIA, but a modified Ubuntu needs Canonical's permission [C-W2-050]; Debian wins the tie-break and the Ubuntu leg stays in CI | 4 |
| Why do competitors ship their own image? | Because only an image gives atomic updates with rollback; script installs were dropped [C-REF-DC-longevity-004] | 4, 7 |
| Why k3s when I run full Kubernetes? | Same API and manifests, one binary, about 1 GB of RAM [C-LAB-k3s-footprint-restore-007]; RKE2 is the bigger sibling from the same vendor | 6 |
| How does the dashboard work? | One web app, role-based "Pro" screens, rescue screen outside Kubernetes | 3 |
| Backups, rollback, security, updates (your top concerns) | Fresh-signal health gate, restic with a recovery key and verified restores, day-1 Secure Boot layout | 7 |
| "Use the proven competitors" | Done for 30 products, each with a constraint-fit verdict | 10 |

**Final verdict on ADR-001** (`01` §7): **confirmed** in architecture (own image, Debian core, A/B with a health gate, k3s, restic); **changed** in the update engine (Rugix → RAUC, OneMind-built), the k3s datastore backup method, the RKE2/FIPS text, CRA timing and Secure Boot timing; **overturned** on Kairos for Jetson, the system-upgrade-controller on image nodes, "DOKS converts in three changes" and "no Fedora/RHEL role".

## The second to sixth briefs {#sec-briefs}

- **Second brief (F-1…F-10): the future, NVIDIA, ease of use, "I want to connect a robot → use OneMind OS", the Marketplace, your own kernel or image, the Mac toolchain, a second build session and this PDF.** Physical AI and NVIDIA: Chapter 12. Kernel and image ownership, Mac toolchain: Chapter 5. Robot plug-and-play and the Marketplace: Chapter 9. The build brief for the second session is `30-NEXT-ULTRACODE-BUILD-BRIEF.md` (summarised in Chapter 11).
- **Third brief (F-11…F-13): IoT and IIoT without limits, Fedora IoT "super important", VillageOS.** IoT/IIoT: Chapter 3; Fedora IoT: Chapter 4; VillageOS: Chapter 10.
- **Fourth brief (F-14): as simple as a Pi, up to full enterprise.** The [walkthrough](#sec-walkthrough) in Chapter 1.
- **Fifth brief (F-15): kernel families, Darwin/XNU vs BSD vs Linux.** Chapter 5.
- **Sixth brief: the plugin ecosystem.** Chapter 9.
