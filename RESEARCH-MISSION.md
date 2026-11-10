# 🧭 RESEARCH MISSION: OneMind OS Foundation & 10-Year Plan

> **You are the research lead for OneMind OS.** This file is your complete, one-shot brief. **You cannot ask the founder anything during this run.** Everything you need is in this repo, and everything you produce goes into [`research-output/`](research-output/). Work at maximum depth: orchestrate many parallel sub-agents, verify adversarially, and keep looping until a pass finds nothing new. Token cost is not a constraint. Being wrong is.

**Commissioned by:** Zeus Delacruz, founder of OneMind OS · **Date:** 2026-11-10
**Repo:** https://github.com/onemindos/ONEMINDOS. Base branch `main`. Clone it; never force-push.
**Reviewer:** Zeus, who is learning OS/platform engineering as he goes. Explain clearly, define terms, and show the "why".

**Terms used here (tool-independent):**
- **Orchestrate:** run independent sub-agents in parallel (one per workstream, competitor or claim). If your platform can't, run them sequentially.
- **Refuter:** an independent agent told to *disprove* a conclusion.
- **Completeness critic:** an agent that asks what is missing.
- **Loop until dry:** repeat until **two consecutive completeness-critic passes add no new question, gap or source**.

---

## 0. The mission in one paragraph

Decide, **with primary-source evidence and proof from competitors**, what OneMind OS should build on for the next 5–10 years: the base Linux OS, image build and A/B updates with rollback, the Kubernetes platform, storage and backups, security, the fit for robotics, drones, physical AI, IoT and mesh, and the hardware line. Then produce **a clear path and plan: the first 180 days, then year 1, years 2–3, years 3–5 and years 5–10.** Also produce **the build brief for a second ultracode session** that will implement the chosen core, and a **final PDF report** for the founder.

**The founder's north star (F-1..F-14):**
- *"I want to connect a robot" → "use OneMind OS."*
- **One OS, simple at every scale (F-14):** as simple as a Raspberry Pi, all the way to full enterprise. The same OneMind OS runs a small greenhouse and robotics simulations, with no limitations. Every foundation choice must pass this test: *does it stay simple on a Pi and still scale to a GPU cluster, with no product switch?*
- Build for the **next 5–10 years of physical AI**, and keep pace with **NVIDIA**.
- **Ease of use first.** Become **the OS that supersedes the others** for robotics, physical AI and sovereign operations.
- A **Marketplace startups integrate into**: plug and play on any device, self-hosted mixed with cloud, with users' own and custom apps.
- **No limitations:** decide whether OneMind should own its **kernel** and/or its **image**, and pick the **development toolchain**, especially from the founder's Mac.
- **IoT and Industrial IoT for 10+ years, without limitations (F-11).** The founder says **Fedora IoT is "super important" (F-12).** Give Fedora IoT and the Red Hat edge lineage (bootc/image mode, CentOS Stream, RHEL for Edge / Device Edge, MicroShift, greenboot, FDO zero-touch onboarding) a full, fair, evidence-based evaluation as **the base, a profile, or both**. ADR-001's earlier dismissal must be re-examined, not assumed.
- **Community-scale resilience** (food, water, energy) is a core use case. Study **VillageOS.ai** (F-13): *"this is also why I'm going operating systems."*
- Confirm, change or overturn the current *proposed* decision in [`docs/ADR-001-foundation.md`](docs/ADR-001-foundation.md).
- Give a status to every question in [`context/05-research-questions.md`](context/05-research-questions.md).
- Trace every requirement in [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md).

**The current proposal you must stress-test (ADR-001, not yet approved):**
- **Base:** Debian 13 "trixie" core image (Umbrel's pattern) plus an NVIDIA L4T/Ubuntu 24.04 flavor for Jetson/DGX.
- **Image and updates:** OneMind's own read-only image, with signed A/B updates via **Rugix** (Umbrel's tool) or **RAUC** (Home Assistant OS's tool). Commit an update only after k3s and the core pods are healthy.
- **Kubernetes:** **k3s** on every tier, and **RKE2** for the hardened enterprise and public-safety tier.
- **Backups and security:** encrypted restic plus k3s snapshots; a security baseline now, with Secure Boot and TPM later.

---

## 1. Read first, in this order

1. [`context/00-CONVERSATION-RECORD.md`](context/00-CONVERSATION-RECORD.md): everything the founder asked and decided in the founding session
2. [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md): **97 requirement IDs** (including §13 F-1…F-15: the founder's second and third briefs). Every recommendation must trace to them.
3. [`docs/DECISIONS.md`](docs/DECISIONS.md): founder decisions D-001…D-006. These are binding. You may argue to revisit one only with strong evidence, flagged explicitly.
4. [`docs/ADR-001-foundation.md`](docs/ADR-001-foundation.md): the proposal under test
5. [`context/01-proven-infrastructure-cluster.md`](context/01-proven-infrastructure-cluster.md): **the proven concept.** The founder already runs managed Kubernetes on DigitalOcean (DOKS) with Argo CD, a Backstage portal, NATS JetStream, Hermes AI agents, an MCP server, TAK Server plus CloudTAK, Authentik and Tailscale. Treat its contents as *reported state*. You have no access to the live cluster or its private repo.
6. [`context/02-prior-planning.md`](context/02-prior-planning.md): the authoritative summary of the Nov 3–4 Blueprint (Core contracts, acceptance tests A01–A24, milestones). The original documents are offline and unavailable to you. List anything you need from them in `26-OPEN-QUESTIONS-FOR-ZEUS.md`.
7. [`context/03-repo-findings-index.md`](context/03-repo-findings-index.md): facts already verified, about 150 UNVERIFIED items, and 40 contradictions. **Build on this; don't redo it.**
8. [`context/04-founder-and-ecosystem.md`](context/04-founder-and-ecosystem.md): the founder profile and ecosystem. Where it conflicts with this brief, this brief wins.
9. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (v0.1, *partly superseded by ADR-001, which wins on base OS, image and updates*), [`docs/DASHBOARD.md`](docs/DASHBOARD.md), [`docs/APPS.md`](docs/APPS.md), [`docs/HARDWARE.md`](docs/HARDWARE.md), [`docs/learning/`](docs/learning/)
10. Everything in [`research/`](research/): the phase-1 reports and the three `verify-*` reports

**Vision:** OneMind OS is *the operating system for sovereignty*. It is a local-first home and edge cloud OS where:
- every device is a node: Pi, mini PC, GPU box, Jetson robot, drone, sensor, XR headset
- every app installs in one click from a Market
- everything installed becomes readable and actionable by AI, with permissions, through MCP, CLI, API and SSH, plus Anthropic's Model Hardware Standard (MHS) for devices
- a native alert center, multi-user family accounts with parental controls, mesh and off-grid networking, and TAK situational awareness are built in
- OneMind ships its own apps: finance, wellness, project management, family, robotics, infrastructure, mesh/IoT, OSINT and education

It is sold as Edge / Lite / Pro / Robotics / Omni / Cluster editions and boxes, as Apache-2.0 open core. **Goal:** surpass Umbrel, Olares, CasaOS/ZimaOS, Home Assistant OS and Project N.O.M.A.D. and become the industry standard for sovereign operations, from a solo home lab to public safety and enterprise. Robotics, drones and physical AI are the moat.

---

## 2. Rules

1. **No guessing.** Every factual claim cites a primary source you actually opened (official docs, release notes, standards, legal text, or source code at a pinned commit or tag). Anything else is labelled `SECONDARY` or `UNVERIFIED`.
   - **Paywalled standards** (ISO, IEC, CJIS) and gated reports: cite the official catalogue page or abstract as `PRIMARY-METADATA`. Never claim to have read clause text you didn't open.
   - **Legal and regulatory claims:** cite the official text (EUR-Lex article numbers, eCFR sections) with its application dates.
   - **Market sizes and prices:** at least 2 independent sources with methods stated, given as a range and labelled `SECONDARY`. Not legal or financial advice.
   - **Load-bearing web sources:** archive them (a Wayback URL, or saved text plus a hash in `research-output/evidence/sources/`).
   - **Code citations:** permalinks pinned to a commit SHA (`repo@sha:path#Lx-Ly`), never branch names.
2. **Proven competitors are evidence, constraint-matched.** The founder's rule is *"Use the proven competitors for real-life documentation and use cases. They already figured it out."* For each question, show what Home Assistant OS, umbrelOS and Olares (and others) *actually do*. Record each competitor's constraints: hardware targets, team size, Kubernetes or not, robotics or not. **A competitor pattern is the default only when its constraints match OneMind's. Otherwise it is one candidate among others.** Every "what competitors do" table needs a **constraint-fit** column.
3. **Reverse-engineer from code, not marketing.** Read build scripts, update modules, manifests, CI and partition layouts. Cite paths at SHAs.
4. **Licenses.** OneMind is Apache-2.0 open core (D-001).
   - You may *study* PolyForm-Noncommercial (umbrelOS), AGPL (Olares, Glance), GPL (Homepage) and unlicensed (umbrel-apps) code. **Never recommend copying it.** Patterns only.
   - Build `evidence/license-matrix.csv` (§6) covering every recommended component, including the transitive ones: firmware blobs, the NVIDIA Jetson Linux/JetPack EULA and CUDA redistributables, Raspberry Pi firmware, the GPL kernel's source-offer obligations, Rugix/RAUC/k3s/RKE2/Longhorn, and each Market seed app.
5. **Safety.**
   - Never run untrusted code outside a disposable VM with no host credentials and no access to private networks.
   - For installers (`curl | bash`): download, hash, read, then run inside the VM.
   - Never send emails, forms or DMs, and never contact vendors. Draft any outreach for Zeus in `evidence/outreach-drafts.md`.
   - Never bypass CAPTCHAs or bot walls. Mark the source `UNVERIFIED (blocked)` instead.
   - **The repo is public:** no secrets, private IPs (RFC1918, 100.64/10), `.ts.net` names, emails or personal data. Run `gitleaks` or `trufflehog` before every push.
6. **Trace everything.** Each recommendation lists the requirement IDs it serves. All 97 IDs must be covered in `25-TRACEABILITY.md`.
7. **Adversarial verification protocol** (P0 conclusions):
   - Each refuter gets *only the claim and its cited sources*, not the author's reasoning. It must produce the strongest counter-argument, at least 2 new sources found specifically by looking for failure or abandonment evidence, a verdict (`upheld` / `weakened` / `refuted`), and a statement of **what evidence would flip the decision**.
   - Use 3 or more refuters with different lenses: technical, longevity/vendor risk, security, cost/business, robotics fit.
   - A mandatory **steelman of the runner-up** must be written by an agent told to argue *for* it (e.g. Buildroot+RAUC the HAOS way, or bootc/Fedora IoT).
   - A `weakened` verdict requires a written response. Record everything in a table per decision.
8. **You can't ask Zeus.** Wherever a file says "ask Zeus" (RS-6, some questions), pick the most defensible option, state the assumption inline, mark the item `blocked: founder-decision` in `24-…`, and list it in `26-OPEN-QUESTIONS-FOR-ZEUS.md`.
9. **Teach.** Each major document gets an "Explain it like I'm the founder" box, a glossary, and "what competitors do" tables.
10. **Things change.** Every product or version fact goes in the claims ledger (§6) with its version, release date, support end and **re-check-by** date: 6 months for kernel, BSP and Kubernetes facts, 12 months for lifecycle pages and pricing.

## 3. Tools, limits and what you can't do

You have web search (use deep or extended modes for niche and recent facts), web fetch, the GitHub CLI and API, a shell, and a sandbox or VMs.
- **Rate limits:** prefer authenticated `gh api`. Use shallow or partial clones (`--depth 1 --filter=blob:none`, sparse checkout) instead of many per-file API calls. On HTTP 429 or a 403 rate limit, back off exponentially, switch to cloning, or move to another workstream and come back.
- **Checkpoint often:** commit and push after each workstream so partial work survives.

**Method substitutions** (many questions mention things you can't do):

| If a method needs… | Do this instead |
|---|---|
| The founder's **live cluster**, billing or private accounts | Use `context/01` only. Answer `partial: based on reported state`. Put the exact read-only commands Zeus should run (kubectl/doctl/argocd) in `22-HARDWARE-LAB-TEST-PLAN.md` |
| **Physical hardware** (Pi 5, Jetson, RTX, Dell Latitude 5540, Beelink U55, Mac, Android) | Use a QEMU/VM substitute where it's meaningful (x86_64 always; aarch64 under QEMU). Otherwise write a founder-runnable test with pass/fail criteria in `22-…`. Answer `blocked: founder-hardware` with your best evidence-based expectation |
| **Contacting vendors, quotes, interviews** | Use public docs, pricing, filings and published interviews. Draft outreach in `evidence/outreach-drafts.md`. Mark `partial` |
| **The founder's choice** | Rule 8 |

**Reverse-engineering helpers:** the founder flagged `morluto/rea`, `storytold/craft-anything` and `qybaihe/bla` (see [`research/competitors/flagged-repos.md`](research/competitors/flagged-repos.md)). **Review them** (W1). **Use them only** if a Tier A question can't be answered by reading source, only in a disposable VM, and only on software you're licensed to analyze.

## 4. Scope, tiers and depth

**Work in tier order. Don't start Tier B or C until the Tier A deliverables are drafted and pushed (draft PR open).**

| Tier | What | Depth required |
|---|---|---|
| **A (deep, first)** | W2 (with **Fedora IoT/bootc at full depth**), W3, W4, W5, W6, W7 foundation-fit, **W8 IoT/IIoT foundation-fit**, **W18 kernel/image route** · full teardowns of **Home Assistant OS, umbrelOS, Olares**, plus a **VillageOS** teardown · the **decision-critical questions** · the mandatory VM lab (§5) | Primary sources, ≥3 refuters per conclusion, code paths, the teardown minimum (below) |
| **B (medium)** | **W19 ecosystem** · teardowns of balenaOS, StartOS, Kairos, Talos, TrueNAS SCALE, CasaOS/ZimaOS, Proxmox, Project N.O.M.A.D. · W8, W9, W10, W11, W12, W16 | ≥1 primary source per claim; condensed teardowns (architecture, update/rollback, app format, license, lessons) |
| **C (brief)** | Teardowns of Unraid, HexOS, Synology DSM, Cosmos, YunoHost, Runtipi, Cloudron, Puter, Sandstorm, FreedomBox, Coolify/Dokploy, ClawBox and other AI boxes, robotics fleet vendors (Formant, Foxglove, Viam, balena-for-robots) · W13, W14, W15, W17 | 1–2 pages each; secondary sources allowed if labelled |

**Decision-critical questions:** before answering the bank, select the **15–25 questions whose answers could flip ADR-001** and list them in `evidence/decision-critical.md`. Examples:
- Fedora IoT/bootc vs Debian + Rugix for IoT/IIoT (F-12)
- which plugin extension points the base OS must expose on day one (A-5/A-6)
- lifecycle cost to 2036
- rebasing without a reflash
- Rugix's bus factor and maturity
- one update framework across x86, Pi 5 and Jetson
- the Jetson BSP lifecycle
- the k3s-vs-Compose justification
- backup and restore coverage (including single-node k3s SQLite)
- the CRA support-period obligation
- GPU drivers on Debian
- the real-time kernel needs of robotics

These get the full method. Other P0s get primary sources. P1 gets ≥1 primary source per claim. P2 can be a short scenario-level answer with sources.

**Teardown minimum (Tier A):**
1. The pinned repo commit/tag and release analyzed, with dates.
2. ≥8 code citations covering image build, partition layout, update client, signing/keys, health check/rollback, app manifest, backup and auth.
3. A boot→update→rollback sequence diagram derived from code.
4. A **claims vs code** table with ≥5 rows (marketing or docs claim checked against source: agree or contradict).
5. ≥3 real-world failure reports from issue trackers or forums, and what they teach.
6. A constraint-fit summary.
7. What OneMind copies and what it does better.

## 5. Workstreams (cover ALL)

| # | Workstream | Must include |
|---|---|---|
| **W1** | **Competitor teardowns** (tiers above) | For each product: architecture, base OS, image build, install paths, update/rollback, app format, identity, AI features, backups, security, hardware, license, business model, strengths and weaknesses, constraint-fit, and what OneMind copies or does better. **Umbrel 2.0 specifics:** Debian trixie build, Rugix, umbreld, the app gateway, the MCP server, Machines/VMs, FailSafe ZFS, household accounts, backups, release signing. **Olares specifics:** k3s, the OAC/Helm format, Market, the Desktop/Files/Vault/Wise/Settings/Control Hub/Studio built-ins, LarePass, the Lares/Router agent, HAMi, multi-node, Olares One. **HAOS specifics:** Buildroot, RAUC, partitions, Supervisor, backups (SecureTar), AppArmor. **Flagged repos (RS-5):** review rea, craft-anything and bla (license, activity, what they do, safety) and decide whether OneMind should use them for teardowns or adopt BLA-style defenses for its own images. Output: `02-competitors/flagged-repos.md`. |
| **W2** | **Base OS (P0)** | Compare Debian 13 · Ubuntu 24.04/26.04 LTS · Fedora/CentOS Stream bootc, Fedora IoT and CoreOS · Alma/Rocky · SUSE SL Micro · Buildroot · Yocto · NixOS · Talos · Kairos · Ubuntu Core · balenaOS · Alpine. **Score** each: lifecycle to 2036 (free and paid), boards (x86, Pi 5/CM5, Jetson Orin/Thor, RK3588, Qualcomm, RISC-V), NVIDIA support, real-time kernel (PREEMPT_RT mainline status), ROS 2 tier support, image tooling, reproducibility, governance and vendor risk, cost, community, and who ships products on it. **Answer the founder's Fedora IoT question with evidence.** Decide whether to have one base or two (core plus Jetson flavor), and whether a Buildroot/Yocto approach (HAOS) beats a distro base for an appliance. **Fedora IoT gets Tier A depth (F-12):** build on [`research/platform/fedora-iot-and-redhat-edge-deep-dive.md`](research/platform/fedora-iot-and-redhat-edge-deep-dive.md). Cover Pi 5 status, bootc maturity, the CentOS Stream → RHEL 10-year path, greenboot, FDO, MicroShift, NVIDIA on RHEL/Fedora, and Jetson. Run the **VM lab** for a Fedora IoT/bootc image alongside Debian + Rugix, and include a **written steelman for Fedora IoT/bootc**. |
| **W3** | **Image, install, updates, rollback (P0)** | Compare Rugix, RAUC, Mender, SWUpdate, OSTree/bootc, Kairos, and NVIDIA L4T's own A/B for Jetson. Cover: signing chains (Umbrel's offline root key and revocation, HAOS's keyring CA split), the health-gated commit, delta updates, channels, user-controlled timing, pre-update backup, recovery partition and factory reset, power loss mid-update, and the disk layout per board. **Install paths (P-7):** flashable image vs USB installer vs a script on an existing distro vs a VM appliance (Proxmox/UTM/Hyper-V). Show what Umbrel, Olares, CasaOS, HAOS and StartOS offer, how a bring-your-own-hardware install gets updates and rollback, and a supported install matrix per tier. |
| **W4** | **Kubernetes, cluster conversion, NVIDIA (P0/P1)** | Compare k3s, RKE2, k0s, Talos, MicroK8s and Docker/Compose, including **why Kubernetes at all**, given that Umbrel and HAOS use Docker. Cover: single node → HA → multi-site (KubeEdge, OpenYurt, Karmada, Liqo, NATS leaf), GitOps (Argo/Flux) coexisting with a Market controller, storage (local-path, Longhorn, OpenEBS, ZFS, Ceph), ingress after ingress-nginx's EOL (Traefik, Gateway API), and networking (Cilium/Flannel, MetalLB, Tailscale/Headscale/NetBird). **A concrete conversion plan for the founder's DOKS cluster** (context/01), and Backstage's future: kept as a developer portal or replaced by the OneMind dashboard. **Why an OS is now the best option** compared with continuing as a cluster plus portal. **NVIDIA on k3s (N-8):** GPU Operator, device plugin vs DRA driver, KAI Scheduler, Dynamo, AI Cluster Runtime and HAMi, checked against the KubeCon NA 2026 announcements (Nov 9–12). **Lock-in guard:** the same manifests must run on AMD, Intel, Hailo and RK3588 NPUs. **AI-9:** migrating Hermes agents and NATS contracts. |
| **W5** | **Backups, recovery, data (P0)** | Compare restic, Kopia, borg and Velero; k3s datastore snapshots (SQLite vs etcd); Longhorn; ZFS send/recv. Cover 3-2-1, encryption and key recovery, restore drills, RPO/RTO targets, what HAOS, Umbrel and Olares back up, whole-box restore onto new hardware, and box-to-box mirroring (UX-6). |
| **W6** | **Security & compliance (P0/P1)** | Threat model for an AI-operated OS controlling physical devices. Cover Secure Boot, TPM and LUKS on x86; Pi 5 OTP secure boot; Jetson fuses (irreversible); read-only root; AppArmor/SELinux; k3s CIS and RKE2 FIPS; Pod Security; network policy; secrets (OpenBao/Infisical); supply chain (SLSA, Sigstore, SBOM); CVE handling; prompt injection against device control. **Law:** the EU Cyber Resilience Act (obligations and dates for hardware vendors), the Radio Equipment Directive, FCC, GDPR, US state privacy laws, COPPA (children's accounts), and public safety (CJIS, FirstNet/TAK). |
| **W7** | **Robotics, drones, physical AI** (foundation fit is P0; the plan is P1/P2) | ROS 2 (Jazzy/Lyrical vs host OS), containerized ROS on k3s, real-time needs, Zenoh/DDS security, micro-ROS, PX4/ArduPilot/MAVLink, Open-RMF, NVIDIA Isaac ROS/Sim/Lab, GR00T, Cosmos, Holoscan, the Jetson lifecycle, non-NVIDIA accelerators (Hailo, Coral, RK3588 NPU, Qualcomm), LeRobot, **Anthropic MHS** (status and integration path), digital twins (USD/glTF), teleoperation, safety (ISO 10218, ISO 13482, IEC 61508, the EU Machinery Regulation from 2027), drones (FAA Part 107/Remote ID, EASA), and how robotics companies ship and update their OS. **Does the base OS hold for robots over 10 years?** **Physical AI 2026–2036 (F-1, F-2):** where humanoids, VLA and world models, edge inference silicon and robot hardware are heading; NVIDIA's announced roadmap (GTC/CES/KubeCon 2025–2026: Jetson Thor and its successors, GR00T, Cosmos, Isaac, Omniverse, Newton physics, NIM) and how OneMind keeps pace on day one of each release; non-NVIDIA alternatives, so OneMind isn't locked in. |
| **W8** | **IoT, IIoT, mesh, off-grid, TAK (F-11; P0 for foundation fit)** | Home Assistant as the IoT engine (Matter/Thread/Zigbee/Z-Wave/ESPHome), MQTT, LoRaWAN (ChirpStack), Meshtastic (including the ATAK plugin), Reticulum, batman-adv, satellite direct-to-cell, NATS leaf buffering during outages, greenhouse and homestead controllers, TAK Server/CloudTAK/ATAK/iTAK. Specify OneMind **profiles** (P-8) for a Pi TAK node and a greenhouse controller. **IIoT (F-11):** OPC UA (PubSub, over MQTT), MQTT 5 + Sparkplug B, Modbus, BACnet, CAN/CANopen, IO-Link, TSN; a unified namespace on NATS/MQTT; Eclipse Kura/Ditto/Hono/Tahu, EdgeX Foundry, Node-RED, Apache PLC4X, open62541, OpenPLC/4diac, Margo, Akri; industrial edge platforms and the OS they ship (Siemens Industrial Edge, Red Hat Device Edge, Ubuntu Core, Azure IoT Operations, AWS Greengrass, Litmus, Ignition); IEC 62443-4-1/4-2/3-3 and NIST 800-82r3; zero-touch onboarding (FIDO FDO, IEEE 802.1AR IDevID, Matter, DPP); the control (PLC/RTOS/Zephyr) vs supervision (Linux) split; industrial gateways and IPCs (Revolution Pi, IOT2050); fleets of 10k devices. Build on [`research/platform/iiot-landscape-and-requirements.md`](research/platform/iiot-landscape-and-requirements.md). **Community resilience (F-13):** a VillageOS teardown ([`research/competitors/villageos.md`](research/competitors/villageos.md)) covering food/water/energy edge AI and whether OneMind should compete, partner, or host VillageOS-style apps. |
| **W9** | **AI capability layer** | MCP (current spec, auth, registry, Apps), A2A, Agent Skills, MHS. The `onemind.app.yaml` → registry → MCP/REST/CLI/Skills design (see [`research/platform/ai-native-protocols-and-ux.md`](research/platform/ai-native-protocols-and-ux.md) §10). Permissions, approvals and audit; agent sandboxing; local inference and GPU sharing; Umbrel 2.0's MCP server and Olares's Lares/Router at code level. **Cloud apps (UX-3):** verify Strava's AI restriction against the primary Strava API Agreement (quote the clause and its date), and design a per-integration "may this data go to AI" flag, with Strava as the "display yes, AI no" example. **Biometrics (AI-6):** WebAuthn/passkeys and local face/voice ID, storage, and legal limits (BIPA, GDPR Art. 9, COPPA). Recommend a phase. |
| **W10** | **Hardware line & capability detection** | Competitor box specs, BOMs and teardowns (Umbrel Home/Pro, Olares One, ZimaBoard/ZimaCube, HA Green, Start9 Server One, ClawBox, DGX Spark). OneMind Edge/Lite/Pro/Robotics/Omni reference designs with BOM ranges, each machine's "superpower" (P-6), bundles (A-7), in-platform recommendations (A-8), and distributor economics (H-1). ODM/OEM paths, certification cost and time, supply and price volatility (the 2026 Jetson and DGX price hikes, memory prices), tariffs and export controls, warranty/RMA, NVIDIA Inception and OEM programs. **The capability-detection model** (NFD and GPU feature discovery) behind "your box can or can't run this". **Founder hardware:** what the Beelink U55 (likely i3-5005U; confirm TPM and UEFI Secure Boot) and the Dell 5540 can and cannot validate; the Mac for arm64 QEMU/UTM tests from week 1 (D-002); purchase dates for the Pi 5 and Jetson Orin Nano Super so ARM and Jetson are in the first bake-off. |
| **W11** | **Dashboard, clients, XR** | Screen-by-screen benchmark of Umbrel, Olares, HA, CasaOS, Homarr and Synology. Simple vs Pro modes; the native alert center (self-hosted push; minimal APNs on iOS per D-005); iOS, Android, **Windows and macOS clients** (UX-8); the Omarchy (Arch + Hyprland) desktop edition; PWA; WebXR, Android XR and visionOS; the multi-machine view, mirroring and the infrastructure map; **QR onboarding** for nodes and robots; the SDK and Federation surfaces (P-4). |
| **W12** | **Apps, Market, internal apps, plugins** | Market seeding by category from the Olares and Umbrel catalogs, with a license check per app; app format and importer; quality tiers; the plugin ecosystem (lessons from Omarchy, HACS, Obsidian, VS Code); plugin distribution on the website (W-8); scaffold specs for every module in [`docs/APPS.md`](docs/APPS.md), with build order. **Deep dives:** **Wellness** (Apple HealthKit, Health Connect, Garmin, Oura, Strava and their AI terms; HIPAA applicability, the FTC Health Breach Notification Rule, GDPR Art. 9; self-hosted wellness apps). **Finance** (SimpleFIN, Plaid, GoCardless and their terms; Firefly III and Actual Budget; what AI may read or act on). **OSINT** (legal and ethical limits; SpiderFoot/Maltego-class tool licenses; build vs integrate). |
| **W13** | **Family, education, community, website** | Roles and parental controls (the Jellyfin model, COPPA), installing a client on a child's device (U-3), kids' education and offline knowledge (Kolibri, Kiwix, N.O.M.A.D.), the education business on Circle.so, and a website stack covering blog, docs, OS downloads, store/cart, affiliate links, Zoho Forms, support desk and headless CMS. Include what competitors' websites run on (W-9) and community platforms. |
| **W14** | **Phones & field devices** | GrapheneOS on Pixel as a hardened ATAK device: current supported devices and evidence of ATAK compatibility. **Investigate the reported ATAK crash on a GrapheneOS Pixel Tablet** and write a GrapheneOS + ATAK test in `22-…`. Also cover the founder's **Samsung S24 Ultra** as a no-root client and ATAK device (Knox and bootloader limits; Shizuku, UAD, Obtainium, Shelter, Tasker, DeX); Fairphone with CalyxOS, iodéOS or /e/OS; Volla; Linux phones (postmarketOS, Ubuntu Touch, Droidian, Mobian, Sailfish, Librem 5, PinePhone, FuriLabs FLX1) and whether ATAK runs via Waydroid with GPS or CloudTAK in a browser is the answer; Android's AVF Linux Terminal; the 4 "build your own OS" levels and when a "OneMind EUD" makes sense; lessons from HarmonyOS on platform sovereignty. |
| **W15** | **World context & 10-year scenarios** | Digital sovereignty (EuroStack/Gaia-X, data localization), AI at home, chip and GPU geopolitics (Taiwan, export controls), energy and off-grid resilience, internet shutdowns, regulatory trajectories for AI, robotics and drones, right to repair, and the future of Apple and Google lock-in. Write 3–4 scenarios for 2030–2036, each with what OneMind must do to stay robust in it. |
| **W16** | **Business, licensing, go-to-market** | What is open vs paid under Apache-2.0 open core; CLA vs DCO; trademarks; an OEM program ("Manufacture with OneMind"); pricing per tier; support plans; education revenue; partnerships (NVIDIA, Raspberry Pi, Anthropic MHS); first segments (homesteaders, families, TAK and public safety, SMB); market sizing (rule 1); competitor funding. |
| **W18** | **Kernel & image ownership + development toolchain (P0, F-7, F-8, F-15)** | **Kernel families first (F-15):** Darwin/XNU (Mach microkernel + BSD; open-source parts on opensource.apple.com and apple-oss-distributions) vs FreeBSD/OpenBSD (TrueNAS CORE, pfSense, PlayStation) vs Linux (monolithic, GPLv2) vs microkernels (seL4, Zircon, HongMeng). Compare driver ecosystems, NVIDIA/Jetson support, containers and Kubernetes (Linux namespaces/cgroups vs jails), robotics/ROS 2 tiers, IoT, licensing (APSL/BSD/GPL), and why Linux is or isn't the right family. Also explain what Darwin means for **developing on the Mac** (no Linux containers natively, so VMs are needed). **"Own kernel" options, with evidence:** (a) stock distro kernel; (b) upstream LTS kernel with a OneMind config (the HAOS and ChromeOS approach); (c) vendor BSP kernels (Raspberry Pi fork, NVIDIA L4T kernel); (d) a patched OneMind kernel (PREEMPT_RT, security patches); (e) a microkernel or new kernel (Fuchsia/Zircon, seL4, Redox, HarmonyOS HongMeng as a cautionary tale). For each: maintenance cost for a solo developer, security patch flow, board coverage, NVIDIA driver compatibility, real-time fit, longevity and kernel LTS lifecycles (kernel.org, CIP SLTS). **What "our own OS" realistically means:** owning the image, kernel config, update chain and SDK, not writing a kernel. Show who did it and at what cost (ChromeOS, SteamOS, HAOS, Umbrel, Olares, Android/AOSP, HarmonyOS). **Image build tooling:** debos, mkosi, Rugix Bakery, Buildroot, Yocto, bootc/osbuild, Kairos, and NVIDIA's L4T flash tools. **Mac development path (Apple Silicon):** UTM/QEMU, Lima/Colima, OrbStack, Docker buildx multi-arch, cross-compiling arm64/x86_64 kernels and images on macOS vs a Linux build VM, remote builders (cloud ARM/x86, GitHub Actions arm64 runners), k3d/kind for local Kubernetes, ROS 2 on a Mac (containers), Isaac Sim (needs an RTX, so a cloud GPU), flashing a Pi and Jetson from a Mac (Jetson SDK Manager needs an x86 Ubuntu host; verify). Give a recommended dev setup plus CI/CD pipeline for images, apps and signing. |
| **W19** | **Platform & plugin ecosystem: OneMind as the robot/physical-AI OS (P1; plugin extension points are P0, A-5, A-6, F-3..F-6)** | **Plugin ecosystem (founder priority):** define every **plugin type** OneMind supports and its extension points in the OS: (1) Market apps (Helm + `onemind.app.yaml`); (2) dashboard widgets and UI extensions (sandboxed iframes, MCP Apps); (3) desktop and shell plugins (the Omarchy model on the Hyprland edition); (4) device, driver and protocol adapters (robots, IoT/IIoT, MHS/MCP device profiles); (5) AI skills, agents and tools; (6) automations and workflows; (7) OS/image profiles (greenhouse, TAK node, industrial). For each, specify the manifest, SDK and CLI (`onemind plugin init|validate|publish`), sandboxing and permissions, signing and verified publishers, review and quality tiers, versioning and compatibility ranges, update and uninstall behavior, and offline installs. **Learn from proven ecosystems at the code level:** Omarchy plugins (`omarchy-plugin-validate`, plugins.omarchy.org), Home Assistant integrations + HACS + the quality scale, Olares OAC + linter, Umbrel community app stores, Backstage plugins, Obsidian community plugins, VS Code extensions, Grafana plugins, the WordPress ecosystem, browser extension stores, and ROS packages. Cover what made each succeed or fail (security incidents, malware in AUR/npm/VS Code), community editing and forking, distribution through the website (W-8), and the revenue and licensing model for paid plugins. **Decide which extension points must exist in the base OS on day one,** so plugins never require forking the OS. How platforms became the default: Android (OEM/GMS), ROS, Home Assistant integrations, Steam/SteamOS, Apple MFi, NVIDIA Jetson partner ecosystem, Viam, Foxglove. Design the **third-party integration path**: SDK, `onemind.app.yaml` and device-driver/adapter packages, MHS/MCP device profiles, a "Works with OneMind" certification, the developer portal, Marketplace revenue share, and listing review and security. The **robot plug-and-play** flow ("connect a robot, use OneMind"): discovery, QR or USB/network onboarding, driver/adapter auto-install, capability detection, safety gates. **Hybrid self-hosted + cloud** (F-6) without lock-in. Developer-experience benchmarks. Which robotics, drone and IoT startups would integrate first, and why. |
| **W17** | **Founder learning path** | A sequenced curriculum for Zeus with links, ordered to match the build plan: Linux internals, image builds, A/B updates, k3s, NATS, security, ROS 2 and Jetson. |

**Easily-missed requirement IDs**, each with a named home:

| ID | Topic | Goes in |
|---|---|---|
| P-3 | Map OneMind onto Olares's layers | 01 |
| P-4 | SDK/Federation | 12, 05 |
| P-6, A-8 | Machine superpowers and recommendations | 11 |
| A-7, H-1 | Bundles and the distributor model | 11, 17 |
| UX-8 | Windows and macOS clients | 12 |
| U-3 | A child's device | 14 |
| AI-9 | Hermes migration | 05, 10 |
| W-8, W-9 | Website plugin distribution, competitor website stacks | 14 |

## 6. Deliverables (all in `research-output/`)

| File | Content |
|---|---|
| `00-EXECUTIVE-SUMMARY.md` | 2–3 pages: the answer, top 10 findings, top 10 risks, decisions Zeus must make, and a **status and confidence table per workstream** (update it after each phase) |
| `01-FOUNDATION-DECISION.md` | **Final recommendation** per tier: base OS, image and updates, install paths, Kubernetes, storage, backups, security. Includes the scorecard, the adversarial tables, the runner-up steelman, **"ADR-001: confirmed / changed / overturned"**, and "Explain it like I'm the founder". |
| `02-competitors/<slug>.md` + `02-competitors/MATRIX.md` | Slug = lowercase-kebab product name, e.g. `home-assistant-os.md`, `umbrelos.md`, `olares.md`, `casaos-zimaos.md`, `robotics-viam.md`, `flagged-repos.md` |
| `03-base-os.md` · `04-image-install-updates-rollback.md` · `05-kubernetes-cluster-conversion-nvidia.md` · `06-backups-recovery.md` · `07-security-compliance.md` · `08-robotics-drones-physical-ai.md` · `09-iot-mesh-offgrid-tak.md` · `10-ai-capability-layer.md` · `11-hardware-line.md` · `12-dashboard-clients-xr.md` · `13-apps-market-plugins.md` · `14-family-education-community-website.md` · `15-phones-field-devices.md` · `16-world-context-scenarios.md` · `17-business-licensing-gtm.md` | W2–W16 (numbers 18–19 reserved) |
| `20-PLAN-180-DAYS.md` | **Structure:** (a) 6 phases of about 4 weeks, each with a goal, deliverables, linked Blueprint acceptance tests (A01–A24) and requirement IDs; (b) **go/no-go gates** (e.g. "week 4: Rugix rollback spike passes on Beelink → proceed; fails → RAUC branch"); (c) every lab test from `22-…` scheduled, with its decision consequence; (d) the assumed solo-developer capacity in hours/week, plus a cut list if behind; (e) weeks 1–2 broken down by day |
| `21-ROADMAP-5-10-YEARS.md` | Year 1, years 2–3, years 3–5, years 5–10. For each: product and editions, hardware, robotics, team, revenue model, **measurable exit criteria**, the leading indicators to watch, and the scenario triggers from W15 that would change course |
| `22-HARDWARE-LAB-TEST-PLAN.md` | Founder-runnable tests (devices and live-cluster read-only checks), with exact commands and pass/fail criteria |
| `23-RISK-REGISTER.md` | Each risk with likelihood, impact, mitigation, owner and trigger |
| `24-QUESTION-BANK-ANSWERS.md` | Every question: status is one of `answered`, `partial`, or `blocked: founder-hardware / founder-decision / paywalled / live-cluster`. Include the answer, sources and claim IDs |
| `25-TRACEABILITY.md` | Requirement ID → recommendation → file. All 97 IDs |
| `26-OPEN-QUESTIONS-FOR-ZEUS.md` | Options plus a recommendation for each. **Must include:** REQUIREMENTS open questions 2–5; the recurring Blueprint questions (is Google/Pixel hardware acceptable, the Dell 5540's state, the first vertical slice, which task system); every `blocked: founder-decision` item; and code or access you needed but couldn't get (RS-6) |
| `27-LEARNING-PATH.md` | W17 |
| `28-KERNEL-IMAGE-OWNERSHIP-AND-DEV-TOOLCHAIN.md` | W18, including the recommended Mac dev setup and CI/CD diagram |
| `29-PLATFORM-ECOSYSTEM-MARKETPLACE.md` | W19: **plugin types and extension-point map, plugin manifest/SDK/CLI spec, security model, comparison of proven ecosystems**, and the Marketplace and partner model |
| `30-NEXT-ULTRACODE-BUILD-BRIEF.md` | **The one-shot brief for the second ultracode session** that implements the chosen core (F-9): repo layout, image build pipeline, kernel config, update and signing chain, k3s platform, first apps, dashboard MVP, the robot onboarding MVP, test harness, milestones and a definition of done. Written so an agent can execute it without questions, in the same style as this file |
| **`ONEMIND-OS-FOUNDATION-REPORT.pdf`** (+ source `report/`) | **The final PDF for the founder (F-10).** It must stand alone and be visual. Contents: (1) executive answer, including a **"Pi greenhouse → enterprise robotics simulation" walkthrough** showing the same OneMind OS at every scale (F-14); (2) **everything from the founding session**: every topic in `context/00-CONVERSATION-RECORD.md`, including **IoT/IIoT, Fedora IoT, VillageOS, kernel families (Darwin/BSD/Linux)**, phones, GrapheneOS/ATAK, HarmonyOS, Omarchy, Fedora IoT, competitors, decisions D-001..D-006, the dashboard, family, XR, mesh, OSINT, wellness, finance, website and education; (3) **Linux distribution comparison** tables and charts and **why the chosen base fits best**; (4) kernel and image ownership route; (5) **architecture diagrams showing how everything connects**: device → node → k3s → capability layer → AI/agents → dashboard/clients → cloud, plus robots, drones, IoT, TAK, NATS and the Marketplace; (6) the update, rollback, backup and security flows as diagrams; (7) the hardware line and box designs; **(7b) the plugin ecosystem: plugin types, how a third party builds and publishes one, and how they plug into the OS and dashboard (diagram)**; (8) competitor comparison; (9) the 180-day plan and the 5–10-year roadmap as timelines; (10) the physical-AI and NVIDIA outlook; (11) risks; (12) decisions for Zeus; (13) glossary and sources. Build it from Markdown with rendered diagrams (Mermaid/Graphviz via pandoc or Typst, or HTML → PDF). Commit the source in `research-output/report/` and the PDF at `research-output/ONEMIND-OS-FOUNDATION-REPORT.pdf`. Every claim must carry a citation or claim ID; no guessing |
| `SOURCES.md` | Bibliography: URL, access date, type, archive link, claims supported |
| `REVIEW-CHECKLIST.md` | Zeus's reading order plus approval checkboxes per decision |
| `evidence/claims.csv` | **Claims ledger:** claim_id, claim, component, version, release_date, support_end, source_url, source_type, commit_or_tag, accessed_date, recheck_by, confidence, used_in, status. Every load-bearing sentence in 01 and 03–07 carries a `[C-###]` |
| `evidence/license-matrix.csv` | component, version, SPDX (from a pinned LICENSE file), source, commercial redistribution allowed, source-offer obligation, patent clause, Apache-2.0 compatible, blob/EULA terms |
| `evidence/scorecard-weights.md` | **Frozen before scoring** (see below) |
| `evidence/decision-critical.md` | The 15–25 decision-critical questions |
| `evidence/lab/<spike>/` | Lab spikes (§7) |
| `evidence/outreach-drafts.md` | Draft vendor and expert outreach for Zeus to send |

**Scorecard protocol (P0 decisions):**
- **Must-pass gates first:** license compatible with Apache-2.0 open core; supports x86 + Pi 5 + Jetson Orin (or an explicit flavor split); a credible support path to 2036 at a stated cost; **no blocking limitation for IoT/IIoT (F-11)**; **one OS from Pi to enterprise (F-14)**: the same image family and app platform from a 4–8 GB Pi 5 greenhouse node to a multi-node GPU cluster running Isaac Sim, with a simple UX at both ends: industrial protocols, real-time, IEC 62443 path, zero-touch onboarding, fleet scale.
- **Then a weighted 0–5 scale** with written anchors per criterion. Suggested weights: longevity/support 20, hardware and robotics fit 20, security/update safety 15, proven in production 15, solo-developer operability 10, cost/licensing 10, ecosystem 10.
- **Freeze the weights** in `evidence/scorecard-weights.md` before scoring, and log any change.
- **One citation per cell.** Unverified cells score the lowest anchor.
- **Sensitivity analysis:** does the winner change under ±5 on each weight?

## 7. Mandatory VM lab (Tier A, where your environment allows it)

1. Build a **Debian 13 + Rugix** image and a **RAUC** image in QEMU (x86_64; aarch64 if feasible).
2. Run a forced bad update with **automatic rollback through a health-gated commit** (k3s readiness).
3. **Cut power mid-update** (kill QEMU during the write).
4. Measure **k3s idle and loaded footprint**.
5. **Restore** with restic plus a k3s snapshot (SQLite single-node and etcd) onto a fresh VM.
6. Optionally, observe the Olares, Umbrel and CasaOS installers in disposable VMs (rule 5).

Each spike lives in `evidence/lab/<spike>/` with:
- a README giving the goal, the hypothesis and the **pass/fail criteria, written before running**
- pinned versions and hashes, and a runnable script
- raw logs and the result

If your environment can't run VMs, say so in `00-…`, and turn each spike into a founder-runnable test in `22-…`.

## 8. Git workflow

1. Clone `https://github.com/onemindos/ONEMINDOS` and branch **`research/ultracode-foundation`** from `main`.
2. **If you lack push access,** fork the repo and open the PR from `yourfork:research/ultracode-foundation` to `onemindos/ONEMINDOS:main`.
3. **If the branch or PR already exists,** add commits to it. Never force-push, and never open a second PR.
4. **Open a *draft* PR early,** once the Tier A baseline is in (claims ledger plus W2/W3 drafts). Title: `Research: OneMind OS foundation & 10-year plan`. Push after every workstream. Mark it *Ready for review* only when §9 is met.
5. The PR body holds the executive summary and review checklist. If it would exceed about 60k characters, summarize and link to the files instead.
6. Don't modify `docs/` or `context/` except to fix factual errors you can prove, in separate `fix(docs): …` commits with the evidence.
7. Run `gitleaks detect` (or `trufflehog`) before each push, and grep `evidence/` for RFC1918/CGNAT addresses, `.ts.net` names and email addresses.

## 9. Definition of done

- [ ] Tier A complete to the teardown minimum, the scorecard protocol and the adversarial protocol, plus the VM lab (or founder-runnable equivalents).
- [ ] Every workstream W1–W17 has its file, at its tier's depth.
- [ ] Every question in the bank has a status. The decision-critical ones are fully evidenced.
- [ ] All 97 requirement IDs are traced.
- [ ] ADR-001 is explicitly confirmed, changed or overturned.
- [ ] `20-PLAN-180-DAYS.md` (with gates) and `21-ROADMAP-5-10-YEARS.md` (with exit criteria) are complete.
- [ ] Every claim used in `01-FOUNDATION-DECISION.md` resolves to a primary-source row in `evidence/claims.csv`.
- [ ] `license-matrix.csv` covers every recommended component.
- [ ] `28-…`, `29-…` and **`30-NEXT-ULTRACODE-BUILD-BRIEF.md`** are complete.
- [ ] **`ONEMIND-OS-FOUNDATION-REPORT.pdf`** is built, readable standalone, visual, and covers every topic in the conversation record.
- [ ] The PR is marked ready for review.

**If you can't finish everything:** Tier A, W18 and `01-FOUNDATION-DECISION.md` come first, then `30-…` and the PDF. Then state exactly what remains, by workstream, in `00-EXECUTIVE-SUMMARY.md`.
