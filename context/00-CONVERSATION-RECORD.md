# Conversation Record: Founder Session of 2026-11-10

Everything Zeus (founder) asked, decided and was told in the Claude Code session that created this repo, in chronological order. **This is context for the research agent, not a set of conclusions.** Where a conclusion was reached, the evidence file is named. The research mission may overturn any conclusion if better evidence appears.

---

## 1. Phones and Android sovereignty (where it started)
- Zeus uses a **Samsung S24 Ultra**, loves Android's freedom and sideloading, and runs **ATAK**.
- Discussed: US S24U models have locked bootloaders; Knox eFuse; no-root customization (Shizuku, Universal Android Debloater, Good Lock, Obtainium/F-Droid, Shelter/Island, Tasker, DeX).
- **GrapheneOS on Pixel** recommended as a hardened ATAK field device (EUD). ATAK-CIV runs on GrapheneOS: sideload the APK from tak.gov or use sandboxed Google Play; set location to "allow all the time"; battery unrestricted; exploit-protection compatibility mode if crashes. *Zeus's earlier research found an ATAK crash report on a GrapheneOS Pixel Tablet, so the exact loadout must be tested.*
- Linux phones covered: postmarketOS, Ubuntu Touch, Droidian, Mobian, Sailfish, Librem 5, PinePhone, FuriLabs FLX1; Termux/proot; Android's built-in Linux Terminal VM (AVF). ATAK on Linux phones only via Waydroid (GPS unverified) or **CloudTAK in a browser**.
- Mobile OS landscape: HarmonyOS NEXT (Huawei; HongMeng microkernel, ArkTS, no Android apps, "super device" distributed model, China-only, FCC 2022 ban), Android forks (GrapheneOS, LineageOS, /e/OS, CalyxOS, which came back in July 2026, iodéOS), KaiOS, dead OSes (BlackBerry 10/QNX, Windows Phone, Symbian, webOS, Firefox OS, Tizen), Fuchsia.
- "Build your own OS" levels: (1) launcher + device-owner app on stock Android, (2) AOSP/GrapheneOS fork for Pixel signed with your own keys (relockable bootloader), (3) Linux-phone distro, (4) from scratch. A "OneMind EUD" (end-user device for TAK) idea was raised. Earlier planning docs deferred a custom Android ROM.

## 2. Review of earlier planning docs (the founder's offline planning set)
Four .md files plus a 35-page PDF from Nov 3–4, 2026. Their content is summarized in `context/02-prior-planning.md`.
- **The Blueprint is canonical.**
- **The Build Handoff is outdated:** it uses old pillars (HP/LE/GE/IT), says "no k8s", treats NATS as "later", makes Letta primary, and mentions ClickUp.
- **Open questions repeated across docs:** is Google hardware acceptable, what state is the Dell in, what is the first vertical slice, which task system.
- **Critique:** too much hedging, too many deliverables at once, and the 90-day plan is too big for one engineer.

## 3. Strategy conversation
- OneMind OS **is a layer/platform** above existing OSes, and later its own image. The real moat: homestead + AI agents + TAK/field ops + self-hosting combined.
- Market view: most people won't leave Apple/Google. The opportunity is people with a strong reason to (homesteaders, privacy-minded families, communities, public safety/TAK, small businesses, governments pushing digital sovereignty, especially in Europe). AI is the turning point ("who owns my AI's memory").
- Business model: open-source core + boxes (an Umbrel/Home Assistant Green playbook) + support/community/education.
- Zeus **wants an Umbrel/Home Assistant/CasaOS-like product** with NATS + his services as plug-and-play, access from any device, hardware tiers (simple → powerful), simulations for robotics and agents, AR/VR/XR (access the home box from glasses).
- NVIDIA at **KubeCon NA 2026** (Nov 9–12, Salt Lake City): KAI Scheduler, Dynamo, AI Cluster Runtime, DRA driver, "Agent Substrate Day". The point: Kubernetes + GPU + agents is the industry pattern. Warning: NVIDIA lock-in is the opposite of sovereignty, so stay hardware-agnostic.
- Zeus raised **Fedora CoreOS / Fedora IoT** (fedoraproject.org/coreos) as a candidate core.

## 4. The big brief: verbatim requirements are in `docs/REQUIREMENTS.md` (82 IDs)
Highlights:
- reverse-engineer competitors; research all Linux distros
- sell hardware and become a distributor
- OS profiles for a box or a Pi (e.g. situational awareness, greenhouse automation)
- robotics/drones/physical AI as the main moat
- everything is a node; mesh networking is native
- every app readable by AI (MCP, CLI, API, SSH, MHS); install an app and AI gets permissioned access automatically
- native alert system; cloud apps (Strava example) with API keys shown on the dashboard and given to AI as context
- internal apps (finance, wellness, robotics, infrastructure, PM, mesh, IoT/networking, family, OSINT)
- multi-user family with parental controls; kids' education
- hardware capability auto-detection; QR onboarding for robots and IoT
- multiple machines in one UI, mirror feature, infrastructure map
- Lite/Pro/Omni editions; NVIDIA as a partner
- website (blog, Circle.so education, docs, OS download, store/cart, affiliate links, Zoho Forms, support desk, headless CMS)
- Omarchy-style plugin ecosystem; WebXR and Android XR
- updates that users control; strong support
- "become the industry standard for sovereign operations"
- **No guessing. Do research.**

Images Zeus shared: the Olares Market catalog (agents, AI search, coding, automation, design, deep research, scraping, art, ticketing, payments, speech, productivity, sandbox, personal data/RAG, local LLMs, observability, management), the Olares + Home Assistant page, and Olares One specs.

## 5. Research phase 1 (six agents): see `research/`
Umbrel, Olares, competitor landscape (+ the flagged repos REA/Craft Anything/BLA, + website patterns), base OS and orchestration, robotics/IoT/XR/NVIDIA, AI-native protocols and UX.

Key verified facts:
- umbrelOS is PolyForm-Noncommercial; Olares is AGPL-3.0 with a conflicting non-commercial LICENSE.md
- Kairos is Apache-2.0 (v4.4.0)
- Project N.O.M.A.D. is Apache-2.0
- **MHS = Anthropic's Model Hardware Standard** (research preview, 2026-08-27; waitlist at modelhardwarestandard.com)
- Strava's API policy bars AI use of its data (secondary sources)
- MCP spec 2026-07-28; MCP was donated to the Linux Foundation's Agentic AI Foundation

## 6. Founder decisions (`docs/DECISIONS.md`)
- **D-001:** open core, Apache-2.0
- **D-002:** design all tiers together, with no tier left behind
- **D-003:** one app shell with modules, and scaffold all modules
- **D-004:** hardware on hand: Mac, Android phone, Beelink U55 (likely i3-5005U / 8 GB, to be confirmed with `lscpu`), Dell Latitude 5540, cloud (DigitalOcean); buy list in `docs/HARDWARE.md`
- **D-005:** iOS push uses APNs with an opaque/minimal payload
- **D-006:** apply to NVIDIA Inception (which requires incorporation and a website) and the MHS preview

## 7. Learning track
Zeus is **learning** OS/platform engineering as he goes. He wants explanations, not just answers (`docs/learning/`).
- Lesson 01: the big four bases. Zeus shared two YouTube explainers.
- Lesson 02: Omarchy (MIT, v4.5.0, Arch + Hyprland + Quickshell, agent-native desktop by DHH). It is a desktop *client* edition, not the box base.

## 8. Foundation verification (three agents + HAOS docs): `docs/ADR-001-foundation.md` (PROPOSED)
Zeus asked: why Ubuntu vs Debian? Why do competitors ship their own image? Why k3s when he runs k8s? How does the dashboard work? Backups, rollback, security and updates are his top concerns. **"Use the proven competitors for real-life documentation and use cases. They already figured it out."**

Outcome:
- **Base:** Debian 13 core image (the Umbrel pattern), plus an NVIDIA L4T/Ubuntu 24.04 flavor for Jetson/DGX.
- **Image:** its own read-only image with A/B updates. Rugix (the Umbrel pattern) or RAUC (the HAOS pattern). Kairos dropped as lead because its docs say Pi 5 is unsupported.
- **Commit rule:** the update is committed only after k3s and core pods are healthy.
- **Kubernetes:** k3s on all tiers, RKE2 for the hardened enterprise/public-safety tier. The DOKS cluster can convert with three changes.
- **Backups:** encrypted restic backups plus k3s snapshots.
- **Security:** baseline now, Secure Boot/TPM later. EU Cyber Resilience Act dates noted.
- **Dashboard design:** `docs/DASHBOARD.md` (Simple vs Pro modes, Control Hub).

**ADR-001 is NOT yet approved.** Zeus said "I have questions." The follow-up was this research mission.

## 9. This mission
Zeus wants a **massive "ultracode" research run by a different agent on a bigger account**, using this repo as the middleman.
- Include everything from this chat, and more.
- Find the base Linux OS to build on for robotics, drones and the future, to last given world events.
- Produce a clear path and plan, with a **5–10 year plan**.
- Cover the existing cluster as the proven concept (Backstage etc.) and why an OS is now the best option.
- Cover all hardware.
- Do reverse engineering, use every tool, and put results in a dedicated folder for Zeus to review.
- Act as if this is a **one-shot prompt**.

## 10. Second brief (added while preparing this mission)
Zeus added these, verbatim in spirit:
- **Build for the future:** consider the next 5–10 years of physical AI and everything coming out.
- **NVIDIA** will be one of the best things to keep up with.
- **Ease of use** is the future.
- **Be the OS that supersedes all others** for robotics and physical AI. "We are going to be the moat." Startups will want to integrate into the OneMind Marketplace because it's plug and play on any device, mixing self-hosted and cloud, with people's own and custom applications.
- **The test sentence:** *"I want to connect a robot" → "use OneMind OS."*
- **No limitations:** "I technically want my own kernel, as they say, and have everything on top of it, or our own image if necessary." Choosing that route is a very big determination, and so is choosing the **development tools**, especially for working from the Mac now.
- **Next steps:** after this research decides the core and all paths, devices and offerings, a **second ultracode session** will build it out (otherwise the founder builds it).
- **Final deliverable:** a **PDF** for the founder that explains the full scope, with visuals showing how everything connects, comparisons between Linux distributions and why the best fit was picked, all based on real research, and including everything from this chat.

New requirement IDs F-1…F-10 (`docs/REQUIREMENTS.md` §13). Collaborator: Daniel (GitHub `dcarku`) will run the research agent from his account.

## 11. Third brief: IoT/IIoT, Fedora IoT and VillageOS
Zeus: "Make sure it supports the path of the future **IoT and IIoT**. **Fedora IoT is super important. I don't want to hit limitations** with that." He shared **https://www.villageos.ai**: "This is also why I'm going operating systems. Please go deeper."
- **VillageOS:** "Neighborhood-Scale Intelligence for Resilient Local Sustenance". It *claims* to be a Stanford spin-off ML platform (unconfirmed; research found it is a design/orchestration platform from ReGen Villages, with an AGPL "VillageOS-API", not an OS) and open-source consortium, with partners Khorium.ai (physics simulation), Nurture Robotics (SAMI construction robots) and Earth Rover, and pilots in South Africa, Mexico and Sweden. Its components are a generative design engine, a physics validation layer, construction translation, and EdgeAI operational intelligence for energy, water and food. Deep research: `research/competitors/villageos.md`.
- **Fedora IoT deep dive:** `research/platform/fedora-iot-and-redhat-edge-deep-dive.md`. **IIoT landscape:** `research/platform/iiot-landscape-and-requirements.md`.
- New requirement IDs: F-11, F-12, F-13 (95 total).
- **Note:** ADR-001's earlier dismissal of Fedora IoT must be re-examined with full evidence. The founder's priority on it is explicit.

## 12. Fourth brief
Zeus: "I want OneMind OS to be **as simple as using a Raspberry Pi, up to full enterprise.** From running a **small greenhouse** to running **robotics simulations**, with **no limitations**." Requirement F-14.

## 13. Fifth brief
Zeus asked to also consider **the core differences between kernel families**: macOS is built on **Darwin** (open-source core, the **XNU** kernel derived from **BSD** and the **Mach microkernel**), while Linux uses the independently created **monolithic Linux kernel** (Linus Torvalds). Requirement F-15, covered by W18 and the final PDF.

**Status at hand-off:** the Fedora IoT/Red Hat edge deep dive and the IIoT landscape research were still running when this was saved. If `research/platform/fedora-iot-and-redhat-edge-deep-dive.md` or `research/platform/iiot-landscape-and-requirements.md` is missing, **do that research yourself first** (W2/W8 scope in RESEARCH-MISSION.md).
