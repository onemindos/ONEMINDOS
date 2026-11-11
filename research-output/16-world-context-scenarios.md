# 16 · World context and 10-year scenarios (2030–2036)

**Owner:** W15 · **Tier:** C (brief; secondary sources allowed and labelled, primary where load-bearing) · **Date:** 2026-11-11 · **Status:** drafted, no refuters (not required at Tier C)
**Claims:** new facts are `C-W15-001…024` ([`evidence/claims/W15.csv`](evidence/claims/W15.csv), sources in [`evidence/sources/W15.md`](evidence/sources/W15.md), saved text and hashes in `evidence/sources/W15/`). Facts already verified by other workstreams are reused by their IDs (W2, W6, W7, W8, W9, W10, W16, the refuter files and the teardowns), not re-researched.
**Feeds:** [`21-ROADMAP-5-10-YEARS.md`](21-ROADMAP-5-10-YEARS.md) uses the scenario IDs (`SCN-A…D`) and trigger IDs (`TRIG-W15-01…16`) in §7. `23-RISK-REGISTER.md` can lift §7 directly.
**Consistent with:** [`01-FOUNDATION-DECISION.md`](01-FOUNDATION-DECISION.md) revision 2. Nothing here changes a Tier A decision. §5 tests each 01 decision against each scenario, and §6 adds cheap hedges that 01 does not yet name.
**Serves requirements:** M-1, M-2, M-4, M-5, M-8, R-3, H-1, H-3, N-2, N-5, N-6, U-5, UX-8, P-7, A-5, AI-8, F-1, F-2, F-4, F-6, F-11, F-13, F-14, D-001
**Owns bank questions:** Q198, Q224, Q225, Q226, Q227, Q241, Q245, Q285 (statuses in [`evidence/qbank/W15.md`](evidence/qbank/W15.md)).
**Not legal advice.** Export-control, trade and EU-law readings are for counsel to confirm.

> ### Explain it like I'm the founder
> You said you want an OS that lasts "given world events". So this file asks: **what could the world look like between 2030 and 2036, and does OneMind still work in each version of it?**
>
> We wrote four stories (scenarios). They are not predictions; real life will be a mix. Each story has **warning lights** (triggers) you can watch, and a list of what OneMind does if the light comes on.
>
> - **A · Fortress blocs.** The US and China split technology further, chips and minerals get rationed, and a Taiwan crisis is possible. *Already visible:* Taiwan makes about two-thirds of the world's most advanced chips [C-W15-023, C-W15-024]; China paused, but did not cancel, its rare-earth export controls, and the pause ran out yesterday [C-W15-004]; a 16 GB Raspberry Pi 5 now costs more than three times its launch price because AI soaks up memory [C-REF3-DC-cost-001].
> - **B · Sovereignty mandate.** Europe (and others) pay real money for "sovereign" technology and write it into rules. *Already visible:* the EU Commission bought cloud with a sovereignty score as an entry gate [C-W15-015]; the CRA, Data Act and right-to-repair law are in force or about to be [C-W6-001, C-W15-013, C-W15-014].
> - **C · Grey grid.** Internet shutdowns, blackouts and disasters become normal. *Already visible:* 313 government internet shutdowns in 2025, a record, including 14 shutdowns of satellite internet [C-W15-001, C-W15-002]; all of mainland Spain and Portugal went dark in April 2025 [C-W15-003].
> - **D · Walled AI gardens.** Apple, Google and NVIDIA make "AI at home" a closed product and close the side doors. *Already visible:* Google will require registered developers for apps installed outside its store, globally from 2027 [C-W15-010].
>
> **The good news:** the foundation in 01 holds in all four. Debian, an open image, k3s, NATS and Apache-2.0 are not owned by any single company or country. **The work is in the edges:** OneMind must be able to **build and update itself with no internet**, **run on more than one kind of chip**, **sell legally into Europe**, and **keep users' phones working with their boxes** even if Apple and Google tighten their rules. §6 lists twelve cheap moves that help in every story; most cost days, not months, if done now.

---

## 1. The answer in one table

| Scenario (2030–2036) | One-line story | Likelihood (judgement, not data) | What it threatens most | Most important OneMind move |
|---|---|---|---|---|
| **SCN-A · Fortress blocs** | Tech decoupling, export bans, chip and memory rationing, possible Taiwan disruption | Medium (partly here already) | Hardware supply, NVIDIA/Jetson availability and price, cross-border sales | Silicon portability: one release contract across x86, arm64 boards from more than one vendor, and a riscv64 CI leg (REC-W15-03, -04) |
| **SCN-B · Sovereignty mandate** | Governments and regulated buyers require provable control, local hosting and EU-law compliance | Medium-high in the EU; low-medium elsewhere | Nothing technical; the risk is *missing* the market by not being certifiable | CRA-ready from the first image; an EU entity and a sovereignty dossier (REC-W15-07, -08) |
| **SCN-C · Grey grid** | Frequent internet shutdowns, grid failures, climate disasters; off-grid goes mainstream | High for shutdowns (trend measured); medium for long grid outages in rich countries | Updates, time, certificates, remote access, cloud AI | Fully offline lifecycle: install, update, verify, restore and AI with zero internet (REC-W15-01, -02, -05) |
| **SCN-D · Walled AI gardens** | Platform owners bundle local AI, close sideloading, and NVIDIA's stack becomes the only easy path | Medium-high for phone platforms; medium for NVIDIA lock-in | Phone clients, app distribution, robot AI stack choice | Web-first clients, an APK outside Play, an accelerator-neutral app contract (REC-W15-06, -09, -10) |

**Bottom line for 01:** no scenario overturns a Tier A decision. Two decisions become *more* important under stress: the Debian core with an engine-neutral disk layout (it keeps OneMind buildable from public mirrors in every bloc), and the "one release contract over per-board backends" rule REC-DEC-06 (it is what makes changing silicon cheap). The weakest point across scenarios is the **Jetson flavor**: it depends on one US vendor's software lifecycle [C-W10-029, C-REF-W7-T-001], on Canonical's permission [C-REF-DC-cost-007], and on export and tariff rules for advanced chips [C-W10-047, C-W15-005]. 01 already hedges it with the meta-tegra route (REC-DEC-18); this file adds a non-NVIDIA robotics SKU as a scenario-triggered option (REC-W15-04).

---

## 2. The world in November 2026: nine forces, with evidence

Each force ends with **"So for OneMind"**. Facts carry claim IDs; judgements are marked as such.

### 2.1 Digital sovereignty is now a procurement criterion, not a slogan (EU)

- The European Commission awarded a sovereign-cloud tender worth up to EUR 180 million over 6 years in April 2026. Eligibility required level **SEAL-2** of its new **Cloud Sovereignty Framework**, which scores eight objectives including supply-chain transparency and technological openness; most winners reached SEAL-3 [C-W15-015].
- The four winners were European providers, but one bid used S3NS, a Thales–Google Cloud joint venture [C-W15-016]. So "sovereign" in practice means *EU-law control and operations*, not "no US technology at all". This matters for OneMind: a US company can still sell, if the control story is right (judgement; counsel to confirm).
- Germany funds open-source sovereignty directly: openDesk is developed by ZenDiS, a publicly funded federal company [C-W15-018], and the Sovereign Tech Fund invests *globally* in open base technologies, with a EUR 50,000 minimum [C-W15-017].
- The CRA applies from 2027-12-11, with vulnerability reporting since 2026-09-11 [C-W6-001]. The Data Act applies since 2025-09-12 [C-W15-012]; its **access-by-design** duty covers connected products placed on the EU market after 2026-09-12 [C-W15-013].

**So for OneMind:** Europe is a real market for a box that can prove who controls it. What sells is *evidence*: an SBOM, signed releases, local-only operation, data export and a support period, all things 01 already requires. **Not opened in this pass:** the EuroStack report, the Gaia-X Trust Framework, and Schleswig-Holstein's migration pages (follow-ups, §10).

### 2.2 AI at home, and AI regulation that diverges

- The EU AI Act applies generally from 2026-08-02; the Digital Omnibus moved high-risk obligations to 2027-12-02 (Annex III) and 2028-08-02 (Annex I, product safety) [C-W6-042, C-W9-042]. Purely personal, non-professional use by individuals is outside the deployer obligations [C-W9-040].
- The US went the other way: a December 2025 executive order set up a federal task force to challenge state AI laws and asked for a federal law that preempts them [C-W15-020]. An executive order is not a statute (judgement), so US state law stays uncertain.
- AI demand moves hardware prices. DRAM contract prices were forecast up 90–95% in one quarter of 2026 [C-W10-037] and the market stayed undersupplied into Q4 2026 [C-W10-038]. NVIDIA raised DGX Spark's price from $3,999 to $4,699 for memory reasons [C-W10-032]. Raspberry Pi raised the 16 GB Pi 5 to $385 (it launched at $120) and blamed a lack of alternative 16 GB DRAM supply [C-REF3-DC-cost-001, C-W10-034].

**So for OneMind:** local AI is the product (AI-8), but the *memory* it needs is the most volatile part of the bill of materials. Two rule-sets will apply to the same box: the EU's (risk-based, dated) and the US's (deregulating, contested). The gateway-enforced approvals in 01 (REC-DEC-13) are what both sides would ask for; keep them as the default everywhere rather than per region.

### 2.3 Chips and GPU geopolitics

- **Concentration.** SIA data (second-hand) put 69% of sub-10nm logic output in Taiwan in 2022, with a projected 47% in 2032 [C-W15-023]. TrendForce put Taiwan at about 68% of 16/14nm-and-below capacity and nearly 80% of EUV-generation capacity in 2023 [C-W15-024]. Range: **roughly two-thirds to four-fifths** of leading-edge capacity sits in one place, falling slowly (SECONDARY, rule 1).
- **Minerals.** China's 2025-10-09 export controls on rare earths, lithium batteries and graphite anodes were suspended from 2025-11-07 to **2026-11-10** [C-W15-004]. That date was yesterday. **What happened next is not verified** in this pass; it is trigger TRIG-W15-02.
- **US controls.** The AI Diffusion Rule was rescinded in May 2025 with "a replacement rule in the future" [C-W15-005]. A 25% Section 232 duty on listed advanced chips and derivative products applies since 2026-01-15 [C-W10-047].
- **Encryption.** Publishing OneMind's open source is not subject to the EAR (no notice unless it uses non-standard cryptography) [C-W15-006]. Shipping compiled images and boxes abroad uses the mass-market route (5A992.c/5D992.c, License Exception ENC with an annual self-classification report) [C-W10-046].
- **Lifecycles are good, supply is not guaranteed.** Pi 5 and CM5 are in production until at least January 2036 [C-W2-029, C-W10-035]; Jetson Thor T4000 is listed to January 2036 [C-W10-029]. A production promise is not a price or allocation promise (above).

**So for OneMind:** the OS is the portable part; the boxes are not. Every board the OS supports is an exit from a supply shock. Multi-arch discipline (no x86- or arm64-only binaries in the core) is cheap now and expensive later.

### 2.4 Energy and the grid

- The 2025-04-28 blackout took down mainland Spain and Portugal; ENTSO-E's final report (2026-03-20) found many interacting causes rather than one failure [C-W15-003].
- AI data-centre demand is a pressure on grids (widely reported; the IEA's own report could not be opened, so no figure is cited here).

**So for OneMind:** a box that is a household's or a farm's "brain" must survive dirty power and long outages: graceful shutdown on UPS signals, journaled writes, power-cut-safe updates (proved in the lab [C-LAB-rauc-k3s-gate-010]) and low idle draw. W10 owns the power design (Q304).

### 2.5 Internet shutdowns, including satellite

- At least 313 deliberate shutdowns in 52 countries in 2025, a record, up from 304 in 2024 [C-W15-001].
- Shutdowns of low-Earth-orbit satellite internet rose from 4 (2024) to 14 in seven countries (2025) [C-W15-002]. Satellite is a backhaul, not an escape hatch. Direct-to-cell data is limited to carrier-listed apps today [C-W8-052].
- NATS leaf buffering delivered 600/600 messages across a cut in our lab [C-W8-050].

**So for OneMind:** "works offline" has to cover the whole lifecycle: install, update, verify signatures, restore, sync time, issue certificates, and run AI. 01 already has offline USB bundles and offline signature verification [C-W6-067]; time, DNS and registry mirroring are still open (Q219, W6).

### 2.6 Robots and drones are becoming regulated products

- The EU Machinery Regulation applies from 2027-01-14 and requires protection against software corruption and evidence of software intervention [C-W6-043, C-W7-045]. Machinery with self-evolving behaviour must stay within its defined task and movement space [C-W7-046].
- The US FCC added **all foreign-produced drones and drone critical components** to its Covered List on 2025-12-22, blocking new equipment authorizations, with a process to restrict previously authorized gear [C-W15-019] (law-firm summary; the FCC page returned 403).

**So for OneMind:** robotics value moves to the software that proves what the machine did and what code ran: signed updates, audit trails, the version-match gate. For drones, OneMind should be the *ground and fleet* software, not the drone's radio or flight hardware, so a component ban hits a partner's SKU, not OneMind's OS (judgement).

### 2.7 Right to repair and real ownership

- The EU Right to Repair Directive applies from 2026-07-31. Manufacturers may not use contractual, hardware or software techniques that impede repair of Annex II goods without legitimate justification [C-W15-014]. Whether a OneMind box falls under Annex II was not checked.
- Under the Data Act, the manufacturer is typically the "data holder" and must give users their device data free [C-W15-012]. A local-first box already meets most of this by design; the duty is to *document* it and to cover any OneMind cloud relay [C-W15-013].
- Irreversible fusing (Pi OTP, Jetson fuses) conflicts with ownership unless there is an owner-key path; W6 designed an owner key-takeover kit for x86 [C-W6-058, C-W6-059].

### 2.8 Apple and Google lock-in

- Google's Android developer verification starts 2026-09-30 in four countries for apps from participating stores and **expands globally to all apps on certified devices in 2027**, with a "power user advanced flow" [C-W15-010].
- The EU fined Apple EUR 500 million in the first DMA non-compliance decision, over App Store anti-steering rules [C-W15-011]. Regulators push one way; platform owners tighten the other.

**So for OneMind:** M-5 (an alternative to Apple and Google) is real demand, but OneMind's own phone clients are exposed to these rules. The browser is the one client platform that neither company can close for a LAN-hosted service (judgement). W11 already makes the PWA the default client; W14 owns the phone side (GrapheneOS, ATAK).

### 2.9 Who controls the build pipeline

- GitHub restricts sanctioned parties and some regions [C-W15-007]. Docker Hub limits anonymous pulls to 100 per 6 hours per IP [C-W15-008]. Bitnami pulled most of its free Docker Hub catalog with weeks of notice in 2025 [C-W15-009]. Docker is retiring Notary v1 content trust on 2026-12-08 [C-REF-W19-cost-002]. Microsoft's 2011 Secure Boot CAs expired in June 2026 [C-REF-W19-longevity-009].

**So for OneMind:** any upstream service can change terms, limits or availability with little notice. A box in a field, and a solo founder's CI, both need a copy of everything they depend on.

---

## 3. What competitors do (with constraint fit)

| Product | Posture on these risks (what it actually does) | Constraints | Constraint fit for OneMind | Lesson |
|---|---|---|---|---|
| **Home Assistant OS** | OS updates are downloaded over HTTPS by the Supervisor from an OTA URL [C-TD-home-assistant-os-020]; funded by a Swiss foundation model and subscriptions [C-W16-012, C-W16-014] | Docker, no Kubernetes, no robotics; very large community | **Partial.** Governance model fits SCN-B; online update path does not fit SCN-C alone | A foundation structure is a sovereignty signal buyers trust |
| **umbrelOS** | Offline root key on a hardware wallet signs the release-signers list, with revocation [C-TD-umbrelos-013] | Debian + Docker, consumer, small team | **High** for key custody; low for IIoT/robotics | Copy the offline-root pattern (01 already does via REC-DEC-08/Z-04) |
| **Olares** | Owner signature checks resolve DID documents through a default Olares cloud service [C-TD-olares-018]; no signature verification of release artifacts found in the CLI [C-TD-olares-006] | k3s, AI-first, VC-funded | **Low** for SCN-C: identity depends on a vendor service | Never make identity or install depend on a OneMind-run cloud |
| **Project N.O.M.A.D.** | Offline knowledge and AI (Kiwix ZIM + RAG) as the core [C-TD-project-nomad-022, C-TD-project-nomad-033]; only the latest release gets fixes and there is no authentication [C-TD-project-nomad-027] | x86 only, homestead/prepper, tiny team | **High** for SCN-C content; low for security and SCN-B | Offline knowledge is a feature people buy; ship it as a Market bundle with real security |
| **StartOS (Start9)** | Builds images for x86_64, aarch64 **and riscv64**, Pi and Rockchip [C-TD-startos-006] | Debian-based, sovereignty audience, small team | **High** for SCN-A portability | A small team can keep a riscv64 target alive if it is in CI from the start |
| **balenaOS** | Offline updates are a full reflash with a preloaded image [C-TD-balenaos-037] | Cloud-managed fleet product | **Low** for SCN-C | Offline must be a first-class update path, not a reflash |
| **Ubuntu Core 26** | Up to 15 years of security maintenance (paid) [C-STEEL-ubu-012] | One vendor's store and permission model | **Medium**: long tail, but single-vendor control is an SCN-B question | Long support is purchasable; plan the cost, keep the exit (01 REC-DEC-17) |
| **VillageOS** | Machines without a public address use a Cloudflare Tunnel [C-TD-villageos-016] | Community-resilience pilot, private server code | **Low** for SCN-C (depends on one US relay) | OneMind's mesh and NATS leaf design (09) is the stronger pattern for F-13 |

**Pattern:** no competitor in the set covers all four scenarios. umbrelOS is strongest on key custody, StartOS on silicon portability, N.O.M.A.D. on offline content, Home Assistant on governance. None documents an offline *rebuild* of its own OS. That gap is OneMind's chance to be the reference for "sovereign" in the literal sense (F-4).

---

## 4. The four scenarios

Each scenario has: the story, **triggers** (warning lights that mean "this is happening"), **signposts** (what to measure and where), what OneMind must do, and which 01 decisions it stresses. Trigger IDs are global so `21-…` and `23-…` can cite them.

### SCN-A · Fortress blocs (decoupling and component bans)

**Story (2030–2036).** The US and China run separate technology stacks. Export controls tighten on AI chips and extend to more end products; China uses mineral controls as a lever; tariffs stack. A blockade or crisis around Taiwan, even a short one, causes a multi-quarter shortage of leading-edge chips. Memory stays expensive because AI data centres outbid consumer devices. Hardware gets dearer and lumpier; software that is portable becomes more valuable.

**Already visible:** chip concentration [C-W15-023, C-W15-024]; the paused mineral controls [C-W15-004]; the Section 232 chip duty [C-W10-047]; rescission and promised replacement of the AI export rule [C-W15-005]; memory-driven price rises [C-W10-037, C-REF3-DC-cost-001, C-W10-032]; the FCC drone ban [C-W15-019].

| Trigger | Warning light | Where to watch |
|---|---|---|
| TRIG-W15-01 | A BIS rule that adds edge AI modules (Jetson-class) or "AI boxes" to licence requirements for any OneMind target market | BIS press releases, Federal Register |
| TRIG-W15-02 | China resumes or widens rare-earth, gallium, germanium or battery-material controls after the 2026-11-10 suspension end | MOFCOM announcements |
| TRIG-W15-03 | Any of: a Jetson, Pi or N-series mini-PC module on allocation, a list price up more than 30% in 12 months, or lead times over 16 weeks | Vendor price pages, distributor stock |
| TRIG-W15-04 | A military or quarantine event in the Taiwan Strait that halts shipping for more than 2 weeks | News; TSMC operational statements |
| TRIG-W15-05 | US Covered List or tariff action that names single-board computers, Chinese-origin SoCs (Rockchip) or NPUs (Hailo origin to be checked) | FCC, USTR, CBP |

**What OneMind must do:**
1. **Keep the OS silicon-portable** (REC-W15-03): one release contract over per-board backends (REC-DEC-06) already exists; add CI build legs for a second arm64 SoC family (RK3588-class, mainline NPU driver from 6.18 [C-W7-049]) and for **riscv64** (Debian has it as an official architecture [C-W15-021]; restic ships riscv64 binaries [C-STEEL-backup-kopia-013]).
2. **Hold a non-NVIDIA robotics SKU option** (REC-W15-04): the capability model and lock-in guard in 08 (W7-R13) make the same app run on RK3588 or Pi + Hailo. If TRIG-W15-01 or -03 fires on Jetson, promote it.
3. **Price for volatility**: quote box prices with a memory-indexed clause or short validity; hold 1–2 quarters of the critical modules once volume justifies it (W10/W16).
4. **Export paperwork early** (REC-W15-08): ENC self-classification for images and boxes [C-W10-046]; ECCN check on any GPU SKU before the first non-US shipment.

**Stresses in 01:** the Jetson flavor (REC-DEC-18) most; the Pi Lite tier through DRAM prices; the GPU-server tier (REC-DEC-03) through tariffs. **Holds:** Debian core and k3s (both build on riscv64-capable upstreams; k3s riscv64 binaries not verified here, see §10).

### SCN-B · Sovereignty mandate (regulated sovereign markets)

**Story.** The EU, and governments that follow it, write sovereignty into procurement and product law. Public bodies, utilities, farms and regulated SMEs must show where data lives, who can switch a device off, and how long it is supported. Certification and documentation become the price of entry. This is the scenario with the biggest *upside* for OneMind, if it is ready.

**Already visible:** the Commission's SEAL-scored tender [C-W15-015]; publicly funded open-source stacks [C-W15-018, C-W15-017]; CRA dates [C-W6-001]; Data Act access-by-design from 2026-09-12 [C-W15-013]; right to repair from 2026-07-31 [C-W15-014]; the AI Act's dated high-risk regime [C-W6-042]; Machinery Regulation from 2027-01-14 [C-W6-043].

| Trigger | Warning light | Where to watch |
|---|---|---|
| TRIG-W15-06 | An EU or member-state tender for edge/on-premise devices or home/municipal infrastructure that scores open source or a SEAL-like sovereignty level | TED tenders, Commission digital-sovereignty pages |
| TRIG-W15-07 | CRA harmonised standards for operating systems cited in the Official Journal (presumption of conformity) | OJ; ETSI/CEN-CENELEC [C-W6-018] |
| TRIG-W15-08 | A revised Cloud Sovereignty Framework or an EU act that extends SEAL-style criteria to on-premise devices or software | Commission |
| TRIG-W15-09 | Sovereign Tech Fund, NLnet or EU calls that fund open edge OS components | sovereign.tech, NLnet |

**What OneMind must do:**
1. **Be CRA-ready at the first sold image** (01 REC-DEC-14), and publish a **sovereignty dossier** (REC-W15-07): SBOM, signing-key custody, where any OneMind-run service is hosted, what works with every OneMind service turned off, data export, and the support end date per SKU [C-W6-005]. Map it to the Cloud Sovereignty Framework's eight objectives so a buyer can score it.
2. **Data Act by design** (REC-W15-08): a documented, free, machine-readable export of device-generated data for every OneMind-made app and box, and a data-sharing notice before any optional relay sync [C-W15-012, C-W15-013].
3. **An EU legal presence** when the first EU sale or grant is real (W16 Q197): CRA authorised representative and grant eligibility.
4. **Apply for open-source funding** for genuinely reusable components (the release contract, the health gate, the plugin policy enforcement) [C-W15-017].

**Stresses in 01:** none negatively. It *rewards* the Apache-2.0 core (D-001), the Debian community base (no vendor permission), the offline root key, and Retain storage. The risk is speed: a solo founder must produce documentation as a product feature.

### SCN-C · Grey grid (shutdowns, outages, disasters)

**Story.** Network and power become unreliable in more places, more often: politically ordered shutdowns, conflict, cable cuts, heat- and storm-driven grid failures. Satellite fills some gaps but can itself be switched off by an operator or a state. Households, farms, clinics and responders want systems that keep working locally for days or weeks. Off-grid is no longer a niche.

**Already visible:** record shutdowns and satellite shutdowns [C-W15-001, C-W15-002]; the Iberian blackout [C-W15-003]; limited direct-to-cell data [C-W8-052].

| Trigger | Warning light | Where to watch |
|---|---|---|
| TRIG-W15-10 | KeepItOn annual count above 350, or a shutdown in an EU or US jurisdiction lasting more than 24 hours | Access Now annual report (each March) |
| TRIG-W15-11 | A grid outage over 48 hours affecting more than 1 million people in a OneMind sales market | ENTSO-E, national grid operators |
| TRIG-W15-12 | A satellite operator restricts service by geography or by customer in a OneMind market | Operator notices, KeepItOn |

**What OneMind must do:**
1. **Offline-complete lifecycle** (REC-W15-01): install from USB, update from a signed USB/LAN bundle, verify signatures offline [C-W6-067], restore from a local restic repository (01 REC-DEC-11), with local time (GPS/RTC), a local CA and local DNS. This closes the open half of Q219.
2. **Box-to-box update relay** (REC-W15-02): one updated box serves signed bundles and container images to its neighbours over LAN or mesh (a local OCI mirror plus the RAUC bundle cache), so a village or a field team updates without the internet.
3. **Local AI by default** (REC-W15-05): every AI feature has a local-model path that works with no network; cloud models are an option (AI-8).
4. **Pluggable backhaul**: Wi-Fi, cellular, satellite and mesh are interchangeable transports under NATS leaf buffering [C-W8-050] (W8 owns the design).

**Stresses in 01:** k3s's need for container images (pre-load core images in the OS image; 01 already ships the core in the image). Secure Boot and certificates need correct time; a box that boots after weeks offline must not reject its own updates. **Holds:** RAUC, restic, NATS leaf.

### SCN-D · Walled AI gardens (platform consolidation)

**Story.** Apple and Google ship capable home AI tied to their accounts and clouds. Sideloading on Android requires registered developers globally from 2027 [C-W15-010]; app stores restrict remote-control, VPN-like and AI apps more tightly. On the robotics side, NVIDIA's integrated stack (Jetson, Isaac, GR00T, Cosmos) is so far ahead that most robot startups standardise on it, along with its licences [C-LIC-003, C-LIC-021]. Regulators push back (DMA fines [C-W15-011]) but slowly.

| Trigger | Warning light | Where to watch |
|---|---|---|
| TRIG-W15-13 | Android verification enforced globally with no workable path for an independent developer's APK, or Play/App Store policy rejects a OneMind client | developer.android.com, store policies |
| TRIG-W15-14 | Apple or Google ship a local-AI home hub with third-party device control in OneMind's segments | Vendor announcements |
| TRIG-W15-15 | NVIDIA changes Jetson/Isaac licence terms to restrict non-NVIDIA-approved OS images, or ends a JetPack branch with less than 12 months' notice | NVIDIA licence texts, lifecycle page [C-W10-029] |
| TRIG-W15-16 | A non-NVIDIA edge accelerator reaches mainline-driver support plus a maintained ROS 2 / VLA inference path | Kernel releases, vendor SDKs |

**What OneMind must do:**
1. **Web-first clients** (REC-W15-06): the PWA (W11) is the primary client; native apps are thin. Register as a verified Android developer early, and distribute the Android APK through a channel outside Play as well (W11/W14).
2. **Accelerator-neutral app contract** (REC-W15-09): `onemind.app.yaml` asks for *capabilities* (e.g. "vision inference ≥ 20 TOPS"), never a vendor; the lock-in guard in 08 is enforced in Market review (W19).
3. **Position against the garden, not beside it** (REC-W15-10): the product promise is "your AI, your box, your keys, works offline, leave any time" (REC-W16-10). That is the one thing a platform owner cannot copy without changing its business.

**Stresses in 01:** Jetson L4T and the Ubuntu GPU flavor (Canonical and NVIDIA permissions). **Holds:** Debian core, Apache-2.0, open plugin points.

---

## 5. Robustness matrix: 01's decisions under each scenario

✅ holds or improves · ⚠️ holds with a named hedge · ❌ fails without action

| 01 decision | SCN-A Fortress | SCN-B Mandate | SCN-C Grey grid | SCN-D Gardens | Hedge (where) |
|---|---|---|---|---|---|
| Debian 13 core (REC-DEC-01) | ✅ community, multi-arch incl. riscv64 [C-W15-021] | ✅ no vendor permission | ✅ mirrorable | ✅ | — |
| Ubuntu 26.04 CI leg (REC-DEC-17) | ✅ | ⚠️ single-vendor control | ✅ | ⚠️ | Keep it a leg, not the base |
| Jetson on L4T Ubuntu (REC-DEC-18) | ❌ export, tariff, price exposure | ⚠️ | ✅ once installed | ❌ licence/lifecycle exposure | meta-tegra route (01), non-NVIDIA SKU (REC-W15-04) |
| RAUC A/B + health gate (REC-DEC-05/07) | ✅ | ✅ CRA update duty | ✅ offline bundles | ✅ | Box-to-box relay (REC-W15-02) |
| Secure Boot + own keys (REC-DEC-20/21) | ✅ | ✅ | ⚠️ time and certificate expiry offline | ✅ | Local time, long-lived offline trust (REC-W15-01) |
| k3s on platform nodes (REC-DEC-09) | ✅ | ✅ | ⚠️ image availability | ✅ | Core images in the OS image; local OCI mirror |
| restic three-key backups (REC-DEC-11) | ✅ | ✅ | ✅ local repo | ✅ | — |
| Apache-2.0 open core (D-001) | ✅ forkable in any bloc | ✅ | ✅ | ✅ the counter-position | — |
| Plugin extension points E1–E10 (REC-DEC-24) | ✅ | ✅ | ⚠️ offline install of signed plugins | ✅ | Offline plugin bundles (W19) |
| GPU-server flavor Ubuntu + RKE2 (REC-DEC-03) | ⚠️ tariffs [C-W10-047] | ⚠️ | ✅ | ⚠️ | Keep it optional; price by quote |

**Reading the matrix:** the only ❌ cells are the Jetson flavor, which 01 already treats as the riskiest dependency (00 risks 1–2). Nothing here asks to change the base, the engine or Kubernetes.

---

## 6. Recommendations: no-regret moves

"No-regret" means it helps in at least three of the four scenarios and costs little now. Timing is a proposal for `20-…`/`21-…`.

| ID | Recommendation | Helps in | When | Cost (estimate) | Serves |
|---|---|---|---|---|---|
| **REC-W15-01** | **Offline-complete lifecycle**: USB/LAN install and update, offline signature verification, local restore, local time (RTC/GPS), local CA and DNS; a box that was offline 90 days accepts its next signed update | C, A, B | 180 days (beta gate) | Days per piece; most parts exist in 01 | N-6, M-1, R-1, R-3, F-13 |
| **REC-W15-02** | **Box-to-box update relay**: a box serves signed RAUC bundles and core OCI images to peers over LAN/mesh | C, A | Year 1 | 1–2 weeks | N-6, UX-6, F-13, F-14 |
| **REC-W15-03** | **Multi-arch discipline**: no x86/arm64-only binaries in the core; a riscv64 build leg in CI (build-only until hardware is bought); a second arm64 SoC family on the support list | A, D | CI leg in year 1; second SoC by year 2 | CI minutes; one board | N-2, H-3, F-1, F-14, R-3 |
| **REC-W15-04** | **Non-NVIDIA robotics SKU as a ready option** (RK3588-class or Pi + Hailo) behind the capability model; promote on TRIG-W15-01/03/15 | A, D | Design year 1; ship on trigger | Low until promoted | M-7, F-2, H-3, N-7 |
| **REC-W15-05** | **Local-first AI**: every AI feature has a local-model path; cloud models are opt-in per integration | C, D, B | 180 days | Design rule | AI-8, M-1, M-2 |
| **REC-W15-06** | **Web-first clients**: PWA primary; verified Android developer registration plus an APK channel outside Play; iOS as a thin client | D | 180 days | Low | UX-8, UX-5, M-5 |
| **REC-W15-07** | **Sovereignty dossier** per release, mapped to the Commission's eight sovereignty objectives: SBOM, key custody, hosting of any OneMind service, offline guarantees, export, support end date | B | First sold image | 2–3 days, then per release | M-2, M-8, R-3, H-1 |
| **REC-W15-08** | **Compliance paperwork early**: ENC self-classification and annual report for images/boxes [C-W10-046]; ECCN review before any GPU SKU export; Data Act access-by-design notice and export [C-W15-013] | A, B | Before first non-US sale | Counsel time | H-1, M-8, M-2 |
| **REC-W15-09** | **Capability-based app contract**: apps request capabilities, never a vendor; enforced in Market review | D, A | Frozen with E1 v1 | Design rule | A-5, F-5, F-2, N-3 |
| **REC-W15-10** | **Public "leave any time" guarantees** (REC-W16-10) as the core brand promise against walled gardens | D, B, C | Launch | Low | M-2, M-5, F-4 |
| **REC-W15-11** | **Self-hosted build and distribution path** (§8) and a yearly **air-gapped rebuild drill** (T-W15-01) | A, C, B | Year 1, then yearly | ~1 day setup, ~1 day per drill | M-6, R-3, F-8, D-001 |
| **REC-W15-12** | **Scenario review** twice a year: walk the §7 trigger table, record which lights are on, update `23-…` | all | From month 6 | 2 hours | M-8, F-1 |

---

## 7. Trigger table for `21-ROADMAP-5-10-YEARS.md`

| Trigger | Scenario | Signal and threshold | Source to watch | Review cadence | Response (pre-decided) |
|---|---|---|---|---|---|
| TRIG-W15-01 | A | Licence requirement for Jetson-class modules or "AI boxes" to a OneMind market | BIS, Federal Register | Quarterly | Promote REC-W15-04; pause GPU-SKU export plans |
| TRIG-W15-02 | A | Mineral controls resume or widen after 2026-11-10 | MOFCOM | Quarterly (first check now) | Buy-ahead on batteries/magnets for robotics kits; re-price |
| TRIG-W15-03 | A | Module allocation, >30% list-price rise in 12 months, or >16-week lead time | Vendor pages, distributors | Monthly once selling | Second-source SKU; memory-indexed pricing |
| TRIG-W15-04 | A | Taiwan Strait disruption >2 weeks | News, TSMC | Event | Freeze new SKUs; ship software-only/BYO installs (P-7) |
| TRIG-W15-05 | A | Covered List/tariff names SBCs, Rockchip or NPU vendors | FCC, USTR | Quarterly | Drop or re-source the affected SKU in the US |
| TRIG-W15-06 | B | EU tender scoring open source or sovereignty for edge/on-prem | TED | Quarterly | Bid with partner; publish dossier (REC-W15-07) |
| TRIG-W15-07 | B | CRA harmonised standard for OS cited in OJ | OJ | Quarterly | Switch to self-assessment route if applicable (W6) |
| TRIG-W15-08 | B | SEAL-style criteria extended to devices/software | Commission | Half-yearly | Map dossier to the new criteria |
| TRIG-W15-09 | B | Open-source infra funding call fits a OneMind component | sovereign.tech, NLnet | Half-yearly | Apply (W16 Q202) |
| TRIG-W15-10 | C | KeepItOn count >350, or a >24 h shutdown in the EU/US | Access Now (March) | Yearly | Raise offline features in roadmap priority |
| TRIG-W15-11 | C | >48 h outage affecting >1M people in a market | Grid operators | Event | Market the resilience bundle; test UPS paths |
| TRIG-W15-12 | C | Satellite service geofenced in a market | Operators, KeepItOn | Event | Mesh/cellular fallbacks first in docs |
| TRIG-W15-13 | D | Android global verification blocks an independent APK path, or a store rejects the client | Android/Apple policy | Half-yearly | PWA-only fallback; F-Droid-class channel |
| TRIG-W15-14 | D | Apple/Google local-AI home hub with third-party device control | Announcements | Event | Sharpen "leave any time" positioning; interoperate (Matter) |
| TRIG-W15-15 | D | NVIDIA licence or lifecycle change against custom OS images | NVIDIA licence texts, lifecycle page | Every JetPack release | Execute the meta-tegra or non-NVIDIA route |
| TRIG-W15-16 | D/A | Non-NVIDIA accelerator gets mainline driver + maintained ROS 2/VLA path | Kernel, vendor SDKs | Yearly | Add as a supported robotics tier |

---

## 8. Minimum self-hosted build and distribution (Q245)

**Goal:** if GitHub, Docker Hub or a CDN becomes unavailable or unaffordable (precedents: [C-W15-007, C-W15-008, C-W15-009, C-REF-W19-cost-002]), OneMind can still build, sign and ship a release, and boxes can still update.

| Piece | Minimum | Why |
|---|---|---|
| Source | A mirror of OneMind repos on a self-hosted forge (Forgejo-class), pushed on every merge | Forge access can be restricted by sanctions or policy [C-W15-007] |
| Packages | A pinned snapshot of the Debian archive subset the image uses (snapshot or a local mirror), per release | Rebuild an old release exactly; Debian is mirrorable by design |
| Container images | A private OCI registry holding every image the core and seed apps use, by digest | Pull limits and catalog withdrawals [C-W15-008, C-W15-009] |
| CI | One self-hosted runner (the founder's build VM, proven in W18) that can run the full image build offline | No dependency on a hosted CI to ship a fix |
| Signing | Offline root + HSM keys (Z-04; two HSMs per W16) | Signing must not need a cloud service |
| Distribution | HTTPS update server + a static mirror elsewhere + USB/LAN bundles (REC-W15-01/02); a peer-to-peer channel (BitTorrent-class) is optional | Updates reach boxes under any single outage |

**Founder test T-W15-01 (air-gapped rebuild drill)** — for `22-…`. *Goal:* rebuild and sign the current OneMind image with the network cable unplugged. *Steps:* (1) disconnect the build VM's network; (2) build the image from the local forge mirror, the Debian snapshot and the local registry; (3) sign it with the offline key; (4) install it on a test box from USB; (5) check its SBOM matches the online build. *Pass:* the image builds, boots, passes the k3s health gate, and its package list equals the online build's (allowing for build timestamps). *Fail:* any step needs the internet. *Decision consequence:* a failure is a release blocker for the first sold image (REC-W15-11).

---

## 9. Question-bank answers (summary; full table in `evidence/qbank/W15.md`)

| Q | Status | Answer in one line |
|---|---|---|
| Q198 | partial | Leading-edge chips are about two-thirds to four-fifths Taiwan-made [C-W15-023, C-W15-024]; mitigate with OS portability and second-source SKUs, not own manufacturing; EMS quotes need outreach |
| Q224 | partial | Source publication is outside the EAR [C-W15-006]; images and boxes use ENC mass-market self-classification [C-W10-046]; AI-chip rules are in flux after the rescission [C-W15-005]; Jetson ECCNs not checked |
| Q225 | partial | Supply risk is real and already priced in (DRAM) [C-W10-037, C-REF3-DC-cost-001]; support RK3588-class and keep riscv64 in CI; foundry-per-SoC data not gathered |
| Q226 | partial | The Commission buys with a SEAL score [C-W15-015]; Germany funds openDesk and open base tech [C-W15-017, C-W15-018]; OneMind could qualify for funding for reusable components; EuroStack/Gaia-X not opened |
| Q227 | partial | The Data Act makes OneMind a data holder for its connected products, with access-by-design for products placed after 2026-09-12 [C-W15-012, C-W15-013]; PIPL, DPDP, 242-FZ and CLOUD Act not opened |
| Q241 | partial | Debian has official riscv64 [C-W15-021]; Ubuntu requires RVA23 from 25.10 [C-W15-022]; keep a CI leg; a credible box is a 2028–2030 decision (judgement); k3s riscv64 binaries not checked |
| Q245 | answered | Four scenarios with triggers (§4, §7) and the minimum self-hosted pipeline plus drill (§8) |
| Q285 | partial | SCN-D covers platform shifts (sideloading [C-W15-010], DMA [C-W15-011], local AI hubs); AR glasses and humanoid forecasts are left to W11/W7 |

---

## 10. Limits and follow-ups

- **Tier C depth:** no refuters ran on this file. Likelihoods in §1 are judgement, not forecasts.
- **Not opened (follow-ups):** the IEA *Energy and AI* report (HTTP 403); NSA CNSA 2.0 documents (HTTP 403; the post-quantum question stays with W6 Q244); EuroStack, Gaia-X, Schleswig-Holstein, Danish and French public-sector migrations; MOFCOM originals; CSIS/RAND Taiwan-contingency reports; China PIPL, India DPDP, Russia 242-FZ and the CLOUD Act; EUR-Lex itself (bot wall; the Data Act Art. 50 text was read on a mirror [C-W15-013]); the FCC Covered List page (403).
- **Time-critical re-check:** China's mineral-control suspension ended 2026-11-10 [C-W15-004]. Check MOFCOM now (TRIG-W15-02); the claim's `recheck_by` is set to 6 months.
- **Not verified here:** k3s release assets for riscv64; whether OneMind products fall under Right to Repair Annex II; Jetson ECCNs; which Hailo/Rockchip parts are Chinese-origin for US rules.
- **Hand-offs:** Q219 offline time/DNS/registry (W6, now with REC-W15-01); Q234 right-to-repair texts (W6, now with C-W15-014); Q242 satellite (W8, now with C-W15-002); Q304 power (W10); Q197 EU entity (W16).

---

## Glossary

| Term | Meaning |
|---|---|
| **Scenario** | A plausible story about the future, used to test a plan. Not a prediction. |
| **Trigger / leading indicator** | A measurable sign that a scenario is starting, chosen in advance so the response is not improvised. |
| **No-regret move** | An action that pays off in most scenarios, so it is worth doing now. |
| **Digital sovereignty** | Control over your data, software and devices under laws you accept, without a foreign company or state able to switch them off. |
| **SEAL level** | The EU Commission's 0–4 sovereignty rating in its Cloud Sovereignty Framework; SEAL-2 means data sovereignty under EU law [C-W15-015]. |
| **EAR / BIS** | US Export Administration Regulations, run by the Bureau of Industry and Security. |
| **ECCN / ENC** | Export classification number; ENC is the licence exception for encryption items. |
| **Section 232** | A US law used to put tariffs on imports for national-security reasons. |
| **Covered List** | The FCC's list of equipment that cannot get new US radio authorizations. |
| **Data holder (Data Act)** | The company that can access data a connected product generates, usually its maker [C-W15-012]. |
| **Access by design** | The Data Act rule that new connected products must let users get their data easily [C-W15-013]. |
| **Right to repair** | Rules that stop makers blocking repairs with contracts, parts pairing or software locks [C-W15-014]. |
| **DMA** | EU Digital Markets Act, rules for "gatekeeper" platforms such as Apple and Google. |
| **Sideloading** | Installing an app from outside the official store. |
| **RVA23** | The RISC-V profile that sets a common baseline for 64-bit application processors. |
| **riscv64** | The 64-bit RISC-V CPU architecture name used by Linux distributions. |
| **LEO satellite** | Low-Earth-orbit satellite internet such as Starlink. |
| **Air-gapped** | Completely disconnected from any network. |
| **OCI registry** | A server that stores container images. |
