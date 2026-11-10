# OneMind OS: Product Requirements

**Source:** Zeus Delacruz, founder, in a direct brief on 2026-11-10 (Claude Code session), plus earlier decisions in the same conversation.
**Status:** Captured requirements. These describe what OneMind OS must become, not what exists today.
**Rule:** Each requirement has an ID. Research, architecture and roadmap docs must trace back to these IDs. Nothing here may be dropped silently. If a requirement changes, edit it and record the change in the change log at the bottom.

---

## 0. Mission

> **Be the operating system for sovereignty.** Give people back their power: their own cloud, AI, data, devices, robots and infrastructure, running locally on hardware they own. Go from a single-person home lab to enterprise and public-safety deployments, and **become the industry standard for sovereign operations**, surpassing Umbrel, Olares, CasaOS, HAOS and Project N.O.M.A.D.

| ID | Requirement |
|---|---|
| M-1 | **Local-first is the moat.** Self-hosted first. A OneMind-operated cloud option comes later, not now. |
| M-2 | Privacy by default. Users own their data, identities and keys. |
| M-3 | **Combining many applications into one OS is the core goal**: self-hosted apps, cloud apps and OneMind's own apps, unified. |
| M-4 | Scale from a single person to a family, community, business, warehouse, public safety and enterprise. Small builds and very large deployments are both first-class. |
| M-5 | Be a long-term alternative to Apple and Google ecosystems as people become more aware of what they give up. |
| M-6 | The founder is a sole developer at the start. The foundation must **give one developer guard rails without capping what the platform can become.** |
| M-7 | Robotics, drones and physical AI are a **very high priority and the main moat**. The architecture must be optimized for them from day one, not bolted on later. |
| M-8 | Treat this as a major, long-term company product, not a side project. |

## 1. Product shape (Umbrel/Olares-class, superseded)

| ID | Requirement |
|---|---|
| P-1 | An Umbrel-like **home cloud OS that just works**: open a browser at a local address, install apps, manage storage, run your world, with no technical knowledge required. |
| P-2 | **Front door/dashboard is the missing piece today.** Backstage is too shallow. It must be a real operating-system experience, not just a portal. |
| P-3 | Replicate the **Olares topology/structure** (Infrastructure → Platform → Framework → Built-in apps → Community apps) where it is optimal. |
| P-4 | Product surfaces to plan: **Core, Dashboard, Desktop, SDK, Mobile, OS Image, Federation.** |
| P-5 | Editions: **Lite, Pro, and Super/Omni**, from home lab to enterprise. |
| P-6 | Every machine has a **"superpower"** (a specialty), and each box gives different capabilities. |
| P-7 | **Bring your own hardware** (free install) **and** a turnkey plug-and-play box. |
| P-8 | Specialized **OS profiles/images** for focused projects on a box or Raspberry Pi, e.g. situational awareness (TAK) or something as simple as automating a greenhouse. |
| P-9 | Support built in for the ongoing **containerized/cluster structure** (the founder's current Kubernetes cluster is the reference example). |

## 2. Apps, app store and plugins

| ID | Requirement |
|---|---|
| A-1 | **One-click install** from a library/app store of hundreds of apps (Umbrel App Store / Olares Market class). |
| A-2 | Plug-and-play for **any app, including OneMind's own internal apps**. |
| A-3 | Plan how to **reverse-engineer, learn from and include** the apps found in competitors' catalogs (Olares Market: chat, AI search, coding, task automation, general agents, design, deep research, scraping/search, art/design, ticketing, payments, speech/audio, productivity, sandbox, personal data/RAG, local LLMs, observability, management) and Umbrel's catalog. |
| A-4 | **Internal OneMind apps** that eventually replace third-party tools: finance, wellness, robotics, infrastructure, project management (replacing ClickUp/Todoist-class tools), mesh, IoT and networking, family management, OSINT (possibly a custom app), and others. Possibly **one unified app** that replaces most of them. |
| A-5 | An internal **plugin system**, also browsable and distributable through the website. |
| A-6 | **Community ecosystem** where the community can edit, add and share plugins and apps later (the Omarchy plugin ecosystem and Hyprland + Arch power are reference inspirations). |
| A-7 | **Bundles**: curated hardware + software combinations for real-life and real-time operations. |
| A-8 | **Recommendations and comparisons** of hardware and software inside the platform. |

## 3. AI-native OS

| ID | Requirement |
|---|---|
| AI-1 | **Everything hosted on the OS is context for AI.** All apps, data, devices and infrastructure can be read by AI, subject to permission. |
| AI-2 | Native protocols inside the OS: **MCP, CLI, API, SSH**, and future protocols (Zeus referred to one as "MHS", which needs verifying; see Open Questions). |
| AI-3 | **Installing an app automatically registers it** for AI access, both the local AI and external AIs when allowed, with permissions. |
| AI-4 | An OS-level agent can **set up and manage the OS itself** (Umbrel 2.0 does this via MCP; OneMind must match and exceed it). |
| AI-5 | **Human-in-the-loop** approvals, native to the AI layer. |
| AI-6 | **Biometric structures** (later), native and AI-integrated. |
| AI-7 | Embedded AI and IoT can connect and be driven by AI. |
| AI-8 | Local LLMs with **automatic GPU detection** (Umbrel does this for Ollama), plus support for external models. |
| AI-9 | Existing OneMind AI assets (Hermes/Legacy agents, NATS agent discovery) carry forward. |

## 4. Dashboard and user experience

| ID | Requirement |
|---|---|
| UX-1 | A **unified application** (Umbrel-like) for everything on the OS. |
| UX-2 | **Fully customizable dashboard**: add external links, connect external application APIs, replace Homepage/Homarr-style dashboards entirely. |
| UX-3 | **Cloud app integrations**, e.g. Strava: the user adds API keys or OAuth, their stats show on the dashboard, and the data is available to AI as context via MCP. |
| UX-4 | **Native alert system** for infrastructure and everything else, built in with no external services. Everything running on the OS is visible in the app. |
| UX-5 | Run anything from **minimal to enterprise infrastructure from a phone app** connected to the user's box. |
| UX-6 | **Multiple machines in one interface**, cluster-specific features, and a **mirror feature** that mirrors one device to another. |
| UX-7 | **Infrastructure map**: automatically map out the user's infrastructure (later). |
| UX-8 | Access from **every platform**: iPhone, Android, Mac, Windows, Linux and the web, like Umbrel's apps; open the box straight from a Mac. |
| UX-9 | **XR access**: WebXR and Android XR, so users can reach their home box and services from glasses or headsets. |
| UX-10 | Option for a desktop edition built on Omarchy (Arch + Hyprland). |

## 5. Users, family and security

| ID | Requirement |
|---|---|
| U-1 | **Multi-user and native**: each household member gets their own space ("everyone gets their own umbrel"). |
| U-2 | Children in the household can use it, including **educational platforms**. |
| U-3 | **Parental monitoring/controls** where wanted, including adding the OS or app to a child's device to access particular apps. |
| U-4 | Unified accounts, MFA, secret management and app isolation (the Olares security model is a benchmark). |
| U-5 | Remote access from anywhere (Tailscale-class), private by default. |

## 6. Nodes, hardware and capability detection

| ID | Requirement |
|---|---|
| N-1 | **Everything is a node**: regular devices, edge devices, sensors, robots and drones. |
| N-2 | Must run on simple computers, Raspberry Pis, CPU-only PCs, GPU machines, edge devices and connected sensors. |
| N-3 | **Hardware capability auto-detection**: for custom machines, tell users whether they can run something, from a simple app up to major robotics simulations. |
| N-4 | **QR-code onboarding** for robots and IoT: scan, and the device is added to the OS immediately and can later be driven by AI. |
| N-5 | Deployment modes: **cloud, local, edge, hybrid**. |
| N-6 | **Mesh networking is native** (homesteads, greenhouses, off-grid infrastructure), with options to add cloud. |
| N-7 | Built for **robotics, drones, physical AI and simulation** (Sims for robotics and AI agents). |
| N-8 | **NVIDIA as a major partner**: everything NVIDIA offers should eventually run natively on OneMind machines, and OneMind will build machines customized for it. |
| N-9 | Decide whether to stay with **native Kubernetes (k8s/k3s) over Docker-only**, given GPUs and future workloads. To be decided from research. |
| N-10 | Edge/IoT later uses the protocol Zeus called "MHS" (to verify) for context and control. |

## 7. Updates, support and reliability

| ID | Requirement |
|---|---|
| R-1 | A **solid update system**: people update **when they want** (user-controlled), safely. |
| R-2 | A good **support system** so everything stays solid. |
| R-3 | Long-term maintainability for hardware OneMind sells. |

## 8. Hardware business

| ID | Requirement |
|---|---|
| H-1 | **Sell hardware** in the future and become a main distributor of OneMind boxes: plug and play. |
| H-2 | **Custom-built boxes**, documented. Research what competitors' boxes run (Umbrel Home/Pro, Olares One, ZimaCube, HA Green/Yellow, Start9). |
| H-3 | Simple through powerful tiers, including GPU and robotics-capable machines and NVIDIA-optimized builds. |
| H-4 | Hardware + software bundles (see A-7) and an OEM path (like "Manufacture with Olares"). |

## 9. Domains OneMind must cover

Sovereign operations, situational awareness/TAK, OSINT, homestead/greenhouse/off-grid, robotics/drones/physical AI, wellness (a major focus), finance, family management, education, project management, infrastructure, mesh/IoT/networking, and AR/VR/XR.

## 10. Website and community (onemindos website)

| ID | Requirement |
|---|---|
| W-1 | **Blog**, news, resources, **education**, partners, community, all on one platform. |
| W-2 | **Education via Circle.so**, so people feel confident building their own box or buying one. Heavy focus on education. |
| W-3 | **OS download** page and **documentation** for the OS. |
| W-4 | **Hardware sales / cart**, plus affiliate links. |
| W-5 | Forms via **Zoho Forms**. |
| W-6 | **Support desk.** |
| W-7 | Possibly a **headless API/CMS**. |
| W-8 | Plugin/app distribution on the website (see A-5). |
| W-9 | Research what competitors' websites run on and replicate what works. |

## 11. Research mandate

| ID | Requirement |
|---|---|
| RS-1 | **No guessing.** Research, cite sources and find the patterns. |
| RS-2 | Reverse-engineer Umbrel, Olares, CasaOS/ZimaOS, HAOS, Project N.O.M.A.D. and the other competitors found. |
| RS-3 | Review the Olares built-in apps: Desktop, Files, Vault, Market, Wise, Settings, Control Hub, Studio. |
| RS-4 | Survey **all relevant Linux distributions** for the base OS. |
| RS-5 | Review the repos the founder flagged: storytold/craft-anything, qybaihe/bla, morluto/rea. |
| RS-6 | If source code of anything is needed, ask Zeus and he will help obtain it. |
| RS-7 | Document everything in this repo (github.com/Zeus-Delacruz/ONEMINDOS). |

## 12. Existing assets to carry forward

Kubernetes cluster (DigitalOcean) with Argo CD GitOps, NATS JetStream (with established subject doctrine), Authentik IdP, Tailscale, TAK Server + CloudTAK (onemindos.dev), Hermes agents, onemind-core (Python/FastAPI) and onemind-mcp, Backstage, Obsidian vault + Todoist, and earlier planning docs in the founder's offline planning set (summarized in context/02-prior-planning.md) (the Blueprint is canonical).

---

## 13. Platform ambition and build path (added 2026-11-10, second brief)

| ID | Requirement |
|---|---|
| F-1 | **Built for the next 5–10 years of physical AI.** The foundation must anticipate what is coming (humanoids, VLA models, world models, edge inference, new robot hardware), not just what exists today. |
| F-2 | **Keep pace with NVIDIA:** track and natively support NVIDIA's roadmap (Jetson, DGX, Isaac, GR00T, Cosmos, Omniverse, NIM, the Kubernetes GPU stack), while staying hardware-agnostic. |
| F-3 | **Ease of use is the future.** "I want to connect a robot → use OneMind OS" must be plug and play on any device. |
| F-4 | **Supersede the other OSes for this purpose and be the moat:** the default OS that people and startups build on for robotics, physical AI and sovereign operations. |
| F-5 | **Third-party ecosystem:** other startups integrate their products, apps and devices into the OneMind Marketplace (SDK, certification, distribution, revenue model). Users run their own and custom applications too. |
| F-6 | **Self-hosted mixed with cloud:** hybrid by design, from local-only to cloud-connected. |
| F-7 | **Build without limitations:** evaluate owning the kernel ("our own kernel") and/or our own image. Kernel strategy (upstream vs vendor BSP vs a custom-configured or patched OneMind kernel, real-time) is a major determination. |
| F-8 | **Development tooling and path, especially from the founder's Mac:** the toolchain for building the OS, images, kernel, apps and robotics software on a Mac (Apple Silicon), plus CI. |
| F-9 | **Two-phase execution:** this research run decides the core and the paths. A **second ultracode session** then builds it out, or the founder builds it. The research must produce the build brief for that session. |
| F-10 | **Final PDF report** for the founder: full scope, visuals, how everything connects, Linux distro comparisons and why the chosen one fits best, all evidence-based, covering everything discussed in the founding session. |

---

## Open questions (do not assume)

1. ~~"MHS" protocol~~ **Resolved:** Anthropic's **Model Hardware Standard** (research preview, announced 2026-08-27) for AI agents operating physical hardware. Reachable via MCP/CLI/code. The spec isn't public yet; open-sourcing is planned. See `research/platform/ai-native-protocols-and-ux.md` §3.
2. Kubernetes everywhere, or a hybrid (Docker on tiny nodes, k8s on boxes)? To be decided from research (N-9).
3. License model for OneMind's own code (open core? which license?).
4. First hardware tier to ship and first target customer segment.
5. The first OneMind internal app to build.

## Change log

| Date | Change |
|---|---|
| 2026-11-10 | Initial capture from founder brief. |
| 2026-11-10 | Added §13 F-1..F-10 (physical AI 5–10 yr, NVIDIA, ease of use, ecosystem, kernel/image ownership, Mac dev path, second build session, final PDF). Total IDs: 92. |
