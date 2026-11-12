# The product people touch {#sec-product}

> **Explain it like I'm the founder.** The foundation (Chapters 4–7) is invisible when it works. This chapter covers what people actually see and use: the dashboard and alerts, family accounts, XR, the IoT and mesh features, TAK, the AI layer that lets agents use everything safely, your own apps (finance, wellness, OSINT and the rest), the Market, the website, education and the business. Each section gives the research's recommendation, what competitors do, and the claim IDs behind it.

## Dashboard, clients and alerts {#sec-dashboard}

**What competitors do (from their code).**

| Product | How the dashboard works | Phone alerts | Constraint fit |
|---|---|---|---|
| umbrelOS | One React page; each app opens in a new browser tab on its own port [C-W11-003] | None: notifications are text lines on the box [C-W11-004] | High (appliance, small team) |
| Olares | A desktop in the browser; apps open in windows (iframes); its phone app is one web codebase wrapped for each platform [C-W11-009, C-W11-011] | Via LarePass | High for the app platform |
| Home Assistant | Separate native iOS (Swift) and Android (Kotlin) apps [C-W11-015] | Google's push service, not encrypted [C-W11-016] | High for UX lessons |

**Recommendations** (`12-dashboard-clients-xr.md`):

1. **One web app is the dashboard everywhere.** It installs as a PWA and is wrapped for iPhone, Android, Mac and Windows only to add what the web cannot: push alerts, QR scanning, Face ID, a Mac menu-bar icon (UX-5, UX-8).
2. **Simple vs Pro, and the Control Hub.** Simple mode shows Home, Apps, Files, Alerts and Family; owners and operators also see Nodes, the **Control Hub** (Kubernetes-level, as in Olares), AI & Agents audit and System (`12-…` §5). **No global "Pro mode" switch.** Home Assistant is removing its "Advanced mode" toggle because one switch gated unrelated features [C-W11-019]. Pro screens appear by *role* (owner, operator), and detail sits one click deeper (UX-1, UX-2).
3. **A small rescue screen lives outside Kubernetes**, inside the update agent, so you can still roll back if k3s breaks (R-1).
4. **Alerts travel on NATS.** Android, desktop and web use self-hosted push (ntfy/UnifiedPush); on iPhone, Apple only learns *that* something happened (D-005). Apple accepts pushes only signed with OneMind's own key, so OneMind runs a tiny content-free relay, which brushes against "no OneMind cloud yet" (M-1); your call (UX-4).
5. **Multi-machine view, mirror and infrastructure map.** A *Nodes* app shows every box and device; "mirror" turns out to mean four different things (screen mirror, data replica, failover twin, config clone), so the word needs your definition before it is built (Z-13); the infrastructure map draws from the same capability data as the Market (UX-6, UX-7).
6. **QR onboarding** for boxes, nodes and robots uses the same flow as first boot (N-4, Chapter 9).

## The Omarchy desktop edition {#sec-omarchy}

Omarchy (Arch + Hyprland, MIT) calls itself an "agentic Linux distribution" and already lists Hermes in its agents panel [C-W11-047]. It shipped 72 releases since July 2025, 32 in the last year [C-W11-048]. **Recommendation:** ship a **OneMind client and plugin pack for stock Omarchy** (a top-bar widget with box health and alerts, an agent skill that calls the box's gateway with scoped tokens, and `onemind pair`), **not** a second OneMind OS on rolling Arch, which would double the security workload (UX-10, F-4). A "desktop that is also a node" can come later on bootc if customers ask.

## XR (WebXR, Android XR, visionOS) {#sec-xr}

| Platform | WebXR today | What OneMind does |
|---|---|---|
| W3C WebXR | Candidate Recommendation Draft, 2026-11-09 [C-W11-043] | Stable core to build on |
| Android XR (Chrome) | AR, hand input, anchors, depth [C-W11-044] | First target for immersive "spatial ops" |
| visionOS (Safari) | Immersive VR only; no AR session [C-W11-045] | 2D dashboard panel; VR views |

**Plan:** day one, the dashboard works as a 2D window in every headset browser (it only needs HTTPS on the LAN). Year 2, a WebXR route with a 3D infrastructure map, TAK layer and robot cameras. Year 3+, native apps only for low-latency teleoperation, still behind the approval gateway (UX-9).

## Family accounts, parental controls and a child's device {#sec-family}

Every person gets a role: Owner, Adult, Teen, Child or Guest. Jellyfin already models per-user ratings, tag blocks and schedules [C-W13-001], and OneMind copies that model for every module; Umbrel and Olares have no parental controls at all (`14-…`). The child's own phone is the hard part, because Apple and Google decide what outside apps may lock; OneMind offers a ladder: (1) the child signs in and sees only their apps; (2) the box filters the child's internet through its DNS filter, even away from home over the private network; (3) a walkthrough of Screen Time or Family Link; (4) for a dedicated kids' tablet, a QR reset into full management with an Apache-2.0 open-source MDM (U-1, U-2, U-3).

**New laws target operating systems directly.** California's AB 1043 makes an "operating system provider" ask for a birth date and pass an age range to apps from 2027 (SECONDARY) [C-W13-012]; a 2026 amendment may exempt openly licensed OSes, but whether that covers a company selling boxes is unclear (SECONDARY) [C-W13-014]. systemd already added a birth-date field for this [C-W13-015]. **OneMind collects a birth date for child profiles anyway**, so the age signal is built in from the start.

## Education and offline knowledge {#sec-education}

Children's learning stays on the box and offline: **Kiwix** (offline Wikipedia, 13 GB to 119 GB per edition [C-W13-022]) and **Kolibri** (courses; about 1 GB RAM recommended, runs on a Pi [C-W13-020]). Project N.O.M.A.D. seeds a similar offline library [C-TD-project-nomad-022]. **Circle.so** is for adults learning to build and run boxes (W-2); keep the course source files in your own Git repository, because Circle's export gives members, posts and comments but not lessons or media [C-W13-025].

## Website, store and community {#sec-website}

Copy what competitors converged on: a static site for blog and docs, **Shopify** for the cart, **Discourse** for the forum. Six of seven competitors fingerprinted run Discourse [C-W13-051]. Plugins and apps get website pages with an **"Open in OneMind"** button; the website never sees your box, because your browser remembers the box address, the trick Home Assistant's "My" links use [C-W13-043] (W-1…W-9). Zoho Forms, a support desk, affiliate links and a headless CMS fit around this core (`14-…` §7–§9).

## IoT, Industrial IoT, mesh, off-grid and TAK {#sec-iot}

> The question you asked: does anything in the foundation **block** IoT or IIoT for ten years? **No.** Four things need work, and one tool is off-limits (`09-iot-mesh-offgrid-tak.md`).

- **Industrial vendors already ship Debian.** Siemens' Industrial Edge device image is Debian 12 [C-W8-037]; Moxa's Debian 13-based industrial Linux holds an IEC 62443-4-2 security-level-2 declaration [C-W8-033]; the Debian-based CIP project announced 62443-4-1 and 4-2 compliance [C-W8-034]. **Certification attaches to a product (device + OS + configuration), never to "an OS".**
- **Protocols run as apps:** OPC UA (open62541), Modbus, CAN (SocketCAN in the kernel), BACnet and MQTT are all available on Debian [C-W8-004, C-W8-005, C-W8-002]. **NATS can be the site's MQTT 3.1.1 + Sparkplug B broker, but it rejects MQTT 5 clients**, so an MQTT 5 broker app (Mosquitto or NanoMQ) is bridged in [C-W8-007, C-W8-008]. EMQX ≥ 5.9 is excluded by its licence.
- **Zero-touch onboarding (FDO) is no longer a Fedora advantage:** Fedora IoT's Rust FDO was deprecated in February 2026, and the maintained code is distro-agnostic Go under Apache-2.0 [C-W8-042, C-W8-044]. The Pi 5 has no TPM, so industrial Pi SKUs need a secure element [C-W8-041].
- **Store-and-forward is proven:** when a site's link to the hub dropped, a NATS leaf delivered 600 of 600 readings, with no gaps or duplicates, once the link returned [C-W8-050].
- **The four things to build:** a Pi 5 real-time kernel variant [C-W8-040], a packaged FDO client, the MQTT 5 broker app, and a 10,000-device fleet test.
- **Off-limits: Reticulum.** Its licence forbids use in systems that can harm people and in AI training data [C-W8-014], so it may only be a user-installed, non-default app.
- **OneMind's native mesh** is batman-adv + WireGuard/Headscale + NATS leaf, all in Debian's kernel [C-W8-003], with **Meshtastic and LoRaWAN as radio gateways**. The Meshtastic ATAK plugin sends CoT through the Meshtastic app, with a 3-hop default and a 56 KB file cap [C-W8-015]. ChirpStack (MIT) runs LoRaWAN for battery sensors over kilometres [C-W8-032]. Satellite direct-to-cell is covered in `09-…` §6.
- **Home Assistant is the IoT engine** (Zigbee, Z-Wave, Matter, Thread, ESPHome). Every competitor's HA app needs host networking and device passthrough: umbrelOS runs it privileged with all of `/dev` [C-W8-026]. So the OS exposes those as a **permissioned capability**, not a blanket privilege (E2, Chapter 9).

**Profiles you asked for** (P-8):

| Profile | Hardware | Runs | Key rule |
|---|---|---|---|
| **Pi TAK node** | Pi 5 with ≥ 8 GB (16 GB recommended) | TAK Server in a container; OpenTAKServer for 4 GB boards | TAK recommends 8 GB for a minimal server [C-W8-018]; Debian 13 lacks Java 17 for the host package [C-W8-019] |
| **Greenhouse** | Pi 5 4–8 GB + NVMe + ESPHome boards | Home Assistant, MQTT, NATS leaf for sensors | Control loop on the ESP32, AI writes set-points only [C-W8-029, C-W8-030] |

**TAK after the cloud move** is Z-12: keep TAK Server in the cloud as a relay, move it home, or both. ATAK, iTAK and CloudTAK are the clients either way.

## The AI capability layer: everything readable and actionable by AI {#sec-ai-layer}

**Design** (`10-ai-capability-layer.md`): every app ships one manifest, `onemind.app.yaml`, listing what it can *do* and *show*. The OS publishes that list four ways (**MCP tools, a REST API, CLI commands and Agent Skills**), all through **one capability gateway**, the single place that decides "may this agent do this, for this person, now?" and writes it to an append-only ledger (AI-1, AI-2, AI-3, AI-4). SSH stays available to the owner for the box itself; agents get shell access only as a declared, approval-gated capability.

- **MCP rewrote itself in July 2026** (version 2026-07-28: no sessions, no handshake) [C-W9-001, C-W9-002]. Apps never speak MCP directly, so protocol churn changes adapters, not apps.
- **Authentik cannot yet be the MCP front door:** MCP clients must use RFC 8707 resource indicators [C-W9-004], which Authentik does not implement; the gateway plays that role and still uses Authentik or Kanidm to log people in.
- **Agents are their own principals,** acting as *a named user intersected with a grant*, never as the owner. Umbrel's MCP server lets an agent install an OS update and reboot [C-W6-052]; OneMind requires human approval for physical actuation, OS updates, installs and data export, because prompt injection has no reliable prevention [C-W6-068] (AI-5, AI-7).
- **"May this data go to AI?"** Every integration declares an `aiPolicy`. **Strava** is the textbook "display yes, AI no": its policy bans its data in any AI context window, even with consent [C-W12-044], and bans running an MCP server that exposes it [C-W9-032] (UX-3).
- **Local inference per tier:** llama.cpp/Ollama on Lite, Edge and Pro; vLLM on GPU servers; one model router with data-class rules such as "health and family data never leave the box" (AI-8).
- **Biometrics:** year 1 is passkeys only (the fingerprint or face check happens on the phone [C-W9-043]); on-box face or voice ID waits until year 2+, opt-in, never on by default for children. Illinois lets each person sue for $1,000–$5,000 [C-W9-035], and the GDPR household exemption does not cover the company supplying the software [C-W9-037] (AI-6).
- **MHS (Anthropic's Model Hardware Standard):** a research preview with standardized drivers and declared safety limits, but **no public spec** yet [C-W7-047]. OneMind's device adapters are designed in the same shape, so an MHS driver host can be added the day the spec is published (N-10, D-006).
- **Hermes (AI-9)** becomes an agent principal of the gateway; NATS `svc.*` stays the internal agent bus.

![Every AI action that touches the physical world waits for a human. Safety limits live in the adapter and the device, not in the model.](img/ai-approval.png){width=88%}

## OneMind's own apps: build the thin parts, integrate the heavy ones {#sec-apps}

D-003's app shell hosts modules; each module is also a Market app. The research recommends **building** what makes OneMind special (the shell, tasks and knowledge over your Markdown vault, the robot registry, the AI capability layer) and **integrating** proven engines for the rest (`13-apps-market-plugins.md` §8):

| Module | Integrate | Key constraint |
|---|---|---|
| **Finance** | Actual Budget (MIT) [C-W12-147]; SimpleFIN for North-American bank data, read-only by protocol [C-W12-061] | Plaid's own policy lets Plaid train AI on end-user data [C-W12-065], so it is not a default. AI may read; write only with approval; **never move money** |
| **Wellness** | wger, Endurain and similar self-hosted apps | Strava bans AI use [C-W12-044]; Oura allows AI only through its own MCP server and forbids caching [C-W12-043]; HealthKit data may not be mined for marketing [C-W12-041]; Health Connect bans transfer to brokers [C-W12-042]. The `aiPolicy` switch is **off by default** for these |
| **OSINT & intel** | SpiderFoot (MIT) [C-W12-157], OpenCTI CE, IntelOwl/MISP unmodified | Scope: world events, infrastructure and your own assets; **people-search is excluded**. Public pages only: the US CFAA bars access "without authorization" [C-W12-070]. OpenSky data is non-commercial without a licence [C-W12-075]; Maltego is not bundled [C-W12-076]. OSINT text is tagged *tainted*, so an agent that read it cannot trigger commands without approval |
| Family, food | Mealie, Grocy | Roles from the family section |
| Education | Kiwix, Kolibri | Offline first |
| Robotics, infrastructure, mesh/IoT, PM | Own thin modules on the capability layer | Robot registry and map are OneMind's core value |

## The Market {#sec-market}

- **Format:** `onemind.app.yaml` plus a Helm chart, with an importer for Compose files; it imports from upstream projects and Apache-licensed stores (Olares, CasaOS [C-W12-009]), **never** from Umbrel's unlicensed store [C-W12-002].
- **Licence classes:** several "open source" apps carry business restrictions that block preinstalling them on boxes you sell, among them Open WebUI's branding clause [C-W12-015]; at least one Olares listing calls an app "MIT" when its server part is under an enterprise licence [C-W12-007]. Every app gets a licence class, and only green classes ship preinstalled.
- **Quality tiers** and the plugin types are in Chapter 9.

## Business, licensing and go-to-market {#sec-business}

> **Give the whole OS away and sell what people can't easily copy: boxes, the name, the update service, support and teaching** (`17-business-licensing-gtm.md`).

- Home Assistant pays more than 50 staff with no investors through a foundation and commercial partners [C-W16-012]; 2.28 million homes [C-W16-013].
- Licence switches go badly: HashiCorp, Elastic and Redis all paid for theirs [C-W16-007, C-W16-008, C-W16-009]. Stay Apache-2.0 and protect the **trademark**.
- **Segments:** homesteaders and self-hosters first, then TAK teams; robotics through partners in years 2–3; public safety later.
- **Revenue:** support plans, pre-orders and education in year 1; boxes from year 2; OEM per-device fees, certification and a Marketplace share later (Chapter 11). Market sizes are third-party estimates given as ranges in `17-…` §11 (SECONDARY).
- **Strong support (R-2):** Community (forum, docs, and security updates for the declared support period at no charge), Personal (human help, about $100–200 a year; Start9 charges $200 [C-W16-021]), Business and Fleet tiers. Paid support sells help and response times, **never access to security fixes**, which the CRA requires for the support period [C-W6-002].
- **Before spending money:** incorporate (NVIDIA Inception requires it [C-W16-031]), clear the name with a trademark attorney, and get prices from Canonical and NVIDIA. Outreach drafts are ready but not sent.
