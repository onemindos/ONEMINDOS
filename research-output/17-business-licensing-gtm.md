# 17 · Business, licensing and go-to-market (W16)

**Date:** 2026-11-10 · **Tier:** B (at least one primary source per claim; market sizes follow rule 1) · **Status:** draft, no refuters run (Tier B does not require them)
**Claims:** `C-W16-###` in [`evidence/claims/W16.csv`](evidence/claims/W16.csv) (55 rows). IDs from other workstreams are reused where they already cover a fact. **Sources:** [`evidence/sources/W16.md`](evidence/sources/W16.md); saved page text and SHA-256 in `evidence/sources/W16/`. **Question statuses:** [`evidence/qbank/W16.md`](evidence/qbank/W16.md). **Outreach drafts:** [`evidence/outreach-drafts-W16.md`](evidence/outreach-drafts-W16.md).
**Not legal, tax or financial advice.** Licence, trademark, CRA and entity readings are interpretations for counsel to check. Market sizes are third-party estimates (`SECONDARY`) given as ranges.

> ### Explain it like I'm the founder
> **Give the whole OS away and sell what people can't easily copy: the boxes, the name, the update service, support and teaching.** That is how Home Assistant pays more than 50 staff with no investors [C-W16-012, C-W16-014]. Its foundation took in CHF 8.84 million in 2025 from about 2.28 million homes [C-W16-013].
> **Your protection is your trademark, not your licence.** Apache-2.0 lets anyone sell your code, but it gives them no right to your name [C-W16-001]. Umbrel and Olares used licences that block resale [C-TD-umbrelos-045, C-TD-olares-047]. That stops OEM partners too, and Olares has since moved its main licence to AGPL [C-W16-006]. HashiCorp, Elastic and Redis show how badly a later licence switch goes down with users [C-W16-007, C-W16-008, C-W16-009].
> **Ask contributors to sign off (DCO), not to sign a CLA.** Home Assistant's "CLA" is really a DCO [C-W16-003].
> **Sell to homesteaders and self-hosters first, then TAK teams.** The robotics moat comes through partners in years 2–3. Public safety and enterprise come later, because enterprise sales sank Sandstorm [C-W16-050].
> **Before you spend money:** incorporate (NVIDIA Inception requires it [C-W16-031]), clear the name with a trademark attorney (we could not search it [C-W16-054]), and get prices from Canonical and NVIDIA. The drafts are ready.

---

## 0. Glossary

| Term | Plain meaning |
|---|---|
| **Open core** | The main product is open source; the company earns from things around it (hardware, hosted services, support) and sometimes from closed add-ons. |
| **Apache-2.0** | A permissive licence. Anyone may use, change and sell the code. It includes a patent licence from contributors, but **no right to use the trademark** [C-W16-001]. |
| **AGPL / copyleft** | Anyone who changes the code and offers it to users, even over a network, must publish those changes. |
| **BSL / FSL ("source-available")** | The code is readable, but commercial competing use is banned for a period. After that it converts to an open licence (FSL: 2 years [C-W16-010]). |
| **PolyForm Noncommercial** | No commercial use at all without a separate deal (umbrelOS) [C-TD-umbrelos-045]. |
| **CLA** | Contributor Licence Agreement. A contract in which contributors grant the company extra rights, often including the right to relicense their code. |
| **DCO** | Developer Certificate of Origin. A one-line sign-off in which a contributor certifies they have the right to submit the code under the project's licence. It grants no extra rights [C-W16-002]. |
| **Trademark** | A registered name or logo. It is the only thing Apache-2.0 does not hand out. |
| **OEM / ODM** | OEM: a company that sells a product under its own brand. ODM: the factory that designs and builds it for them. |
| **TAM / SAM / SOM** | Total, serviceable and obtainable market: everyone in the category, the part you can reach, and what you can realistically win. |
| **Attach rate** | The share of hardware buyers who also buy a subscription. |
| **CRA** | The EU Cyber Resilience Act. It sets security and support-period duties for products sold in the EU ([`07-…`](07-security-compliance.md)). |

---

## 1. The answer

| # | Decision | Recommendation | Confidence | Requirement IDs |
|---|---|---|---|---|
| **REC-W16-01** | What is open and what is paid | Every line of OneMind-written code inside the OS image stays Apache-2.0, with **no feature gates** on bring-your-own hardware. Paid items sit *outside* the image: boxes, the hosted Link service (relay, offsite backup), the fleet console, support, certification and OEM licensing, and education. | High | D-001, P-7, M-1, M-8, R-2, H-1 |
| **REC-W16-02** | Licence protection and contributions | Keep Apache-2.0 (D-001). Get protection from a **trademark policy and certification marks**. Contributors use a **DCO sign-off** (inbound = outbound Apache-2.0). No CLA, no copyright assignment. Publish a no-relicensing pledge for the core. | High | D-001, A-6, F-5 |
| **REC-W16-03** | Trademarks | Get a clearance opinion, then file "OneMind" / "OneMind OS" (classes 9 and 42, consider 35, 38 and 41) in the US and through Madrid (EU, UK) **before** printing packaging. Write a trademark policy modelled on Debian's and the Open Home Foundation's. | Medium (search was blocked) | H-1, H-4, W-4 |
| **REC-W16-04** | Editions (P-5) | Editions are **hardware profiles plus support levels, not software feature tiers**: Edge (leaf), Lite, Pro, Robotics, Omni, Cluster. The same app platform runs everywhere (F-14). | High | P-5, D-002, F-14, A-7 |
| **REC-W16-05** | Pricing | Use the competitor-anchored price bands in §6 as hypotheses. W10 must check them against landed BOM before any price is published. | Medium-low | H-1, A-7 |
| **REC-W16-06** | Support plans | Security updates are free for the declared support period (CRA). Sell three levels: Community (free), Personal ~$100–200/yr, Business per node/yr. Fleet management is priced per device per month. | Medium | R-2, R-3, M-4 |
| **REC-W16-07** | OEM programme | "Manufacture with OneMind" from year 2: trademark and certification licence, signed-update and fleet service per device, and a "Works with OneMind" badge with a small annual fee. Robot and drone makers come first. | Medium | H-4, F-4, F-5, M-7 |
| **REC-W16-08** | First segments | Year 1: homestead/greenhouse and self-hosting families on Edge/Lite. Second: TAK field teams (civilian, SAR, volunteer). Year 2–3: robotics developers and OEMs. Later, with FIPS and NDAA work: public safety and enterprise. | Medium | M-4, F-13, H-1 |
| **REC-W16-09** | Partnerships | NVIDIA: Inception now, NPN OEM later. Raspberry Pi: "Powered by" plus MHS camera alignment. Canonical: quote and permission request. Anthropic MHS: waitlist, pitched as a device integrator. | Medium | N-8, F-2, AI-2, N-10, D-006 |
| **REC-W16-10** | Company-death commitments | Publish them on day 1: works offline forever, data export, signing-key escrow, an unlock path and a public end-of-support date per SKU. | High | M-2, R-3, M-8 |

---

## 2. What is open and what is paid (Q181, Q260, D-001)

### 2.1 What competitors do

| Product | What is free | What is paid | Licence | Constraint fit with OneMind |
|---|---|---|---|---|
| **Home Assistant / Nabu Casa** | The whole OS, Core and integrations, with no feature gates | Link $6.50/mo or $65/yr (remote access, offsite backup, voice, support) [C-W16-014]; Green box $199 [C-W16-016]; WWHA certification CHF 500/yr [C-W16-015] | Apache-2.0 [C-W16-005] | **High.** Local-first, appliance OS, hardware sales, Apache. Differences: no Kubernetes, no robotics, and a 50+ person team [C-W16-012]. |
| **umbrelOS** | The OS for personal use; app installs | Hardware $499–$1,899 [C-TD-umbrelos-047]; "Umbrel Protect" add-on; commercial licence by deal | PolyForm-NC [C-TD-umbrelos-045] | **Medium.** Same consumer market, but the licence model conflicts with D-001 and with any OEM channel. |
| **Olares** | The OS ("free and open source for self-hosting") | Olares One $4,999, sold as a one-time purchase [C-TD-olares-046, C-W16-020] | AGPL-3.0 since 2025-08-30, with a legacy non-commercial LICENSE.md still present [C-W16-006, C-TD-olares-047] | **Medium.** It uses k3s like OneMind, but it is VC-funded (>$100M [C-W16-018]) and sells only high-end hardware. |
| **Start9** | StartOS | Hardware; Premium Support $200/yr, with a year included with each box [C-W16-021] | MIT [C-W16-005] | **High** for support pricing (small team, sovereignty buyers). |
| **IceWhale (CasaOS/ZimaOS)** | CasaOS | ZimaBoard $339–399, ZimaCube 2 $799–2,499 [C-W16-026] | CasaOS Apache-2.0 [C-W16-005]; ZimaOS repo has no licence file [C-W3-047] | **Medium.** Hardware-led; the commercial OS is closed. |
| **Proxmox VE** | All features | Per CPU socket per year: €120 community repo, €370/€550/€1,100 support [C-W16-028] | AGPL (not ledgered here) | **Medium.** Proves "no feature gates, sell the stable repo and support". Its buyers are IT teams, not families. |
| **Unraid** | Nothing (a 30-day trial) | Perpetual licence $49/$109/$249; the tiers differ by update years and device count, not features [C-W16-029] | Proprietary | **Low.** A closed OS conflicts with D-001, but it shows home users will pay $49–249 once for software. |
| **balena** | Open-source openBalena, balenaOS | Hosted fleet: 10 devices free, then $159–1,439/mo with $2–3 per extra device per month [C-W16-030] | Apache-2.0 (balenaOS) | **High for the OEM and fleet tier** (robot and IoT fleets). |
| **Sandstorm** (failure case) | Open source platform | Enterprise features (LDAP, SAML, policies): "almost no one has purchased" [C-W16-050] | Apache-2.0 | **High as a warning.** A solo or small team selling closed enterprise features failed. |

### 2.2 Recommendation (REC-W16-01)

1. **Open (Apache-2.0, in the image):** OS, dashboard, app platform, Market client, capability gateway, MCP/CLI/API, backup tooling, update client, robot onboarding, SDK and the `onemind.app.yaml` format. This matches D-001 and 01's CRA response: "keep all OneMind-authored code in the base image Apache-2.0 and keep closed features out of it" ([01 §5](01-FOUNDATION-DECISION.md), [C-W6-013]).
2. **Paid, outside the image:**
   - **Hardware** (H-1).
   - **OneMind Link**, a hosted service: remote-access relay, encrypted offsite backup target, push relay (D-005), optional cloud model credits. Self-hosting alternatives (Tailscale/Headscale, your own S3) stay documented and free (M-1).
   - **Fleet console** (hosted or on-prem) for 10+ devices, OEMs and integrators.
   - **Support and SLAs** (§7).
   - **Certification and trademark licensing** (§8).
   - **Education** (§9).
3. **No closed "Pro" modules in year 1.** Three reasons. Sandstorm's closed enterprise edition did not sell [C-W16-050]. Proxmox and Home Assistant earn without gating [C-W16-028, C-W16-014]. A closed component inside the image complicates the CRA position that 01 depends on. If a closed module is ever needed (for example a FIPS-validated crypto pack for government), ship it as a separate signed add-on with its own ADR (D-001 "write that ADR before the first paid feature").

**Why not gate features by edition (Q260)?** Gating would need licence keys and feature flags in the image, which contradicts Apache-2.0 trust and the F-14 promise of "the same OS everywhere, no limitations". In the comparable products, the editions buyers actually pay for are hardware (Umbrel, ZimaCube) or service levels (Proxmox, Start9).

---

## 3. Licence protection and contributor policy (Q173)

### 3.1 Options compared

| Option | Stops a competitor rebadging the core? | Allows OEM partners and enterprise adoption? | Community trust | Evidence | Fit |
|---|---|---|---|---|---|
| **Apache-2.0 + trademark policy + certification** (HA model) | Not the code, but they cannot use the name, the Market, signed updates or the badge | Yes | Highest | HA/OHF funds 50+ staff on this model [C-W16-012, C-W16-013]; Apache §6 withholds the trademark [C-W16-001] | **Recommended** |
| **AGPL-3.0** | Partly: a rebadger must publish its changes | OEMs can ship it, but many companies' policies forbid AGPL (FSL's authors say so [C-W16-010]) | Medium | Olares moved here in 2025 [C-W16-006]; Elastic and Redis added AGPL to win back the "open source" label [C-W16-008, C-W16-009] | Conflicts with D-001 |
| **BSL / FSL** (time-delayed open) | Yes, for 2–4 years | OEMs need a commercial licence | Low to medium | HashiCorp's 2023 switch to BSL [C-W16-007] | Conflicts with D-001 and the CRA FOSS framing |
| **Apache core + proprietary modules** | Only the modules | Yes | Medium | Sandstorm's enterprise modules did not sell [C-W16-050] | Allowed by D-001 later, but not in year 1 |
| **PolyForm Noncommercial** | Yes, fully | **No**: OEMs, resellers and even support businesses need a deal [C-TD-umbrelos-045] | Low (not OSI open source) | umbrelOS | Rejected: kills H-4 |

**The rebadging risk is real but small.** Anyone can already take Debian, k3s and RAUC, all of them permissive or LGPL [C-W2-049, C-W4-075]. What a competitor cannot copy is OneMind's signed update service, Market catalogue and curation, certification badge and brand. The open question is whether **a well-funded company** (Olares has raised over $100M [C-W16-018]) forks the Apache core. If it does, Apache-2.0 still lets OneMind pull their improvements back, because their code would also be Apache-licensed if they publish it. They are not obliged to publish it, which is the trade-off D-001 already accepted.

### 3.2 Relicensing is costly

HashiCorp (2023, MPL → BSL) [C-W16-007], Elastic (back to AGPL in 2024 after leaving open source in 2021) [C-W16-008] and Redis (to AGPL in 2025 after SSPL) [C-W16-009] all reversed or caused backlash. The lesson for OneMind: **choose once and promise not to relicense the core.** A CLA that lets the company relicense contributors' code weakens that promise.

### 3.3 DCO or CLA (REC-W16-02)

| | DCO (sign-off) | CLA (grant to company) |
|---|---|---|
| What the contributor gives | A certification that they may submit under the project licence [C-W16-002] | Usually a broad copyright and patent licence, sometimes a relicensing right |
| Friction | A `-s` flag on each commit | A legal form; GitLab dropped its CLA because it deterred contributors [C-W16-004] |
| Who uses it | Linux, GitLab since 2017 [C-W16-004]; **Home Assistant's "CLA" is a DCO variant naming Apache 2.0** [C-W16-003] | Many single-vendor projects |
| Does OneMind need relicensing rights? | No. Apache-2.0 inbound already lets OneMind ship contributed code inside paid products (inference; Apache-2.0 grants these rights to everyone) | Only if OneMind wanted to move the core to a non-Apache licence, which §3.2 argues against |

**Recommendation:** DCO with a CI check, inbound = outbound Apache-2.0, plus a short `TRADEMARKS.md` and a no-relicensing pledge for the core. If a large corporate contributor asks for a CLA, accept the Apache Software Foundation's standard corporate CLA form *in addition* (it is a licence grant, not an assignment). That is UNVERIFIED as a practice here; counsel should confirm.

---

## 4. Trademarks (Q174)

**Status: blocked.** The USPTO search API refused scripted access, and trademark mirrors returned HTTP 403. Search results show a similar-sounding AI software brand, "1mind" (1mind AI, Inc.), with reported filings; we did not open those records [C-W16-054]. "One Mind" is also a common phrase in health and mental-health branding (not ledgered). **A clearance search by a trademark attorney is required** before packaging is printed or a domain strategy is fixed (REC-W16-03). This is founder action **T-W16-1** in §14.

**Third-party marks OneMind will touch:**

| Mark | Rule | Consequence |
|---|---|---|
| Debian | Factual "based on Debian" statements are fine. Never use it in a product name, domain or anything that implies endorsement [C-W16-011] | "OneMind OS (based on Debian 13)" is fine; "Debian OneMind" is not |
| Ubuntu (Jetson and GPU flavours) | A modified Ubuntu image needs Canonical approval, or the marks removed **and binaries recompiled** [C-W2-050]. NVIDIA says its L4T redistribution answer does not cover the Ubuntu rootfs [C-REF-DC-cost-007] | **Blocks selling Jetson boxes** until Canonical answers (outreach drafted) |
| Raspberry Pi | "Powered by Raspberry Pi" logo by application [C-W16-036] | Apply before launching the Edge SKU |
| Home Assistant / WWHA | Badge only for certified end devices; hubs and bridges are excluded [C-W16-015] | A OneMind box **cannot** carry WWHA (it is a hub). It can only say it runs HA as an app |
| NVIDIA | Usage rules come through NPN membership [C-W16-033] | Do not use "NVIDIA-certified" wording without the programme |

---

## 5. Competitor business models and funding (Q172)

| Company | Funding (source type) | Revenue model | Sustained? | Constraint fit |
|---|---|---|---|---|
| **Nabu Casa / Open Home Foundation** | None: "No VC money, or private equity" [C-W16-014] | Link subscription + hardware; partners must give most of their net profit from licensed products to OHF [C-W16-012]. OHF revenue CHF 8.84M in 2025 [C-W16-013] | **Yes**, since 2018, funding 50+ FTE [C-W16-012] | **Best match** for the local-first consumer model. Its scale (2.28M homes) took about 10 years |
| **Umbrel** | $3M seed, 2021 [C-W16-017] | Hardware ($499–1,899) + Protect add-on [C-TD-umbrelos-047] | Unknown (private) | Same consumers; restrictive licence |
| **Olares** | >$100M including a SIG-led Series A [C-W16-018] ($45M Series A in a 2025 release, unverified [C-W16-019]) | Hardware ($4,999); Kickstarter $2.34M [C-W16-018] | Too early | Funded far beyond a solo founder's reach. Do not compete on price at the high end |
| **Start9** | $1.2M seed, 2021 (SECONDARY) [C-W16-022] | Hardware + $200/yr support [C-W16-021] | Operating since 2020 [C-W18-064] | Similar sovereignty buyer, small team |
| **IceWhale** | Crowdfunding: ZimaCube about 1,252 backers / ~$1.2M (unverified) [C-W16-027] | Hardware [C-W16-026] | Yes, as a hardware business | Hardware-first model |
| **Framework** | $18M (2024) including a $17M Series A-1; "raise as little as possible" [C-W16-023] | Hardware + marketplace | Growing | Hardware longevity brand (Q204 is with W10) |
| **System76** | Not researched in this pass | Hardware + Pop!_OS | — | Gap, low priority |
| **Viam** (robotics platform) | $45M Series B, $87M total (SECONDARY) [C-W16-025] | Hosted robotics platform | VC-stage | **Robotics competitor-partner**: a cloud fleet platform, not an OS |
| **Foxglove** (robotics data) | $40M Series B (2025) [C-W16-024] | SaaS (data and observability) | VC-stage | An integration target (MCAP, MIT [C-W7-059]), not a competitor |
| **balena** | Not researched | Per-device fleet SaaS [C-W16-030] | Operating since about 2013 (not ledgered) | **Pricing reference** for OneMind's fleet console |
| **Sandstorm** | Venture-backed (not ledgered) | Enterprise features + hosted Oasis | **No**: "our business has not succeeded" [C-W16-050] | Warning case |

**What this tells OneMind (derived):**
1. The one proven, independent, open-source home-OS business is HA's, built on a subscription plus hardware, with no feature gates. In 2025 it brought in about CHF 3.9 of foundation revenue per active household (CHF 8.84M / 2.28M; derived arithmetic, not a stated figure [C-W16-013]). It needs **very large install bases**.
2. Hardware-led players (Umbrel, IceWhale, Olares) raise money or crowdfund to cover inventory. Crowdfunding validated about $1–2.3M of demand for each box category [C-W16-018, C-W16-027].
3. Robotics software companies raise $40–87M and sell to enterprises [C-W16-024, C-W16-025]. That is a partner and integration market for OneMind, not a direct fight for a solo founder (M-6).

---

## 6. Editions and pricing (Q181, Q260, P-5, A-7)

### 6.1 Price anchors (primary store or pricing pages)

| Category | Anchor | Claim |
|---|---|---|
| Entry appliance | HA Green $199 / €179 | C-W16-016 |
| SBC | Raspberry Pi 5 16GB $305; CM5 from $67.50; both in production until at least January 2036 | C-W16-034, C-W16-035 |
| Home server | Umbrel Home $499–949; Umbrel Pro $699–1,899 | C-TD-umbrelos-047 |
| NAS / prosumer | ZimaCube 2 $799 / $1,299 / $2,499 | C-W16-026 |
| AI box | Olares One $4,999 | C-TD-olares-046 |
| Software, one-time | Unraid $49 / $109 / $249 | C-W16-029 |
| Subscription | HA Link $6.50/mo or $65/yr | C-W16-014 |
| Support | Start9 $200/yr; Proxmox €370–1,100 per socket/yr | C-W16-021, C-W16-028 |
| Fleet | balena $2–3 per device per month above the included devices | C-W16-030 |

### 6.2 Recommended editions (REC-W16-04, REC-W16-05)

**These are hypotheses.** Each must pass W10's landed-BOM check (Q176) before publication. The Tier A constraints from 01 are applied explicitly.

| Edition | Hardware (from 01 and W10) | Role under Tier A | Planning price band | Anchor |
|---|---|---|---|---|
| **OS (BYO)** | Any supported x86, Pi 5, Jetson | Full OS, free | $0 | HA, Proxmox |
| **Edge** | Pi 5 / CM5, <4 GB or SD | **NATS leaf + adapters, not a k3s platform node** (01: k3s needs ≥4 GB + SSD) | $149–249 kit | HA Green $199 |
| **Lite** | N150-class x86 or Pi 5 8–16 GB + NVMe | Single-box k3s platform | $399–699 | Umbrel Home $499–949 |
| **Pro** | Ryzen/Core + RTX | k3s + GPU (Debian + driver until Q-W2-1 is answered) | $1,299–2,999 | ZimaCube 2 / Umbrel Pro / Olares One |
| **Robotics** | Jetson Orin / Thor | L4T Ubuntu 24.04 flavour | Dev kit + margin; **not sold until Canonical/NVIDIA redistribution is cleared** | — |
| **Omni / Cluster** | Multi-node, GPU | Quote | Quote | — |

**Flag for 01 (not resolved here):** F-14 says "the same OneMind OS" from Pi to cluster, but under 01 the cheapest Edge kit is a *leaf*, not a full k3s node. Marketing must say "Edge nodes join a OneMind hub". Selling a $149 Pi kit as a standalone "OneMind OS box" would over-promise.

---

## 7. Support plans (R-2, R-3)

| Level | Contents | Price hypothesis | Anchor |
|---|---|---|---|
| **Community** | Forum, docs, **security updates for the declared support period at no charge** | Free | CRA support-period duties [C-W6-002, C-W6-005] |
| **Personal** | Human help, remote-assist session, priority bug triage; a year included with each box | $100–200/yr | Start9 $200/yr [C-W16-021] |
| **Business** | Response targets, N tickets/yr, offline update bundles | Per node/yr, roughly €300–1,100 | Proxmox [C-W16-028] |
| **Fleet** | Hosted or on-prem console, staged rollouts, device health | $2–3 per device per month | balena [C-W16-030] |

**CRA interplay:** support periods must be declared per SKU and be at least five years unless expected use is shorter [C-W6-002]. 01 caps each SKU at its board's kernel window. Paid support therefore sells **help and SLAs, never access to security fixes**. Selling the fixes would undercut the CRA position and the sovereignty brand.

---

## 8. "Manufacture with OneMind": the OEM programme (Q199, H-4)

**What competitors offer:** Olares sells its own box. The legacy non-commercial clause in its tree, and the absence of any public OEM page (olares.com/oem returned 404), mean we found **no public "Manufacture with Olares" terms** [C-W16-020, C-TD-olares-047]. Umbrel's licence requires a commercial deal for any third-party hardware [C-TD-umbrelos-045]. Home Assistant licenses its brand only to contractual partners who pass most of their profit back [C-W16-012], and runs WWHA certification for CHF 500/yr [C-W16-015]. NVIDIA's own partner network has an OEM type for companies that "manufacture and resell under their own brand" [C-W16-033].

| Programme element | Design | Why |
|---|---|---|
| **Licence** | Code free under Apache-2.0. A **trademark and certification licence** ("OneMind OS inside", "Works with OneMind") by contract | Apache gives no trademark rights [C-W16-001] |
| **Fee** | Annual programme fee (admin-level, like WWHA's CHF 500) + a per-device fee for the **signed-update and fleet service** | Recurring revenue tied to the service actually delivered (balena-style [C-W16-030]) |
| **Image customisation** | An OEM profile layer in the same image pipeline (D-002). OEM apps go in a vendor Market channel | No forks |
| **Signing keys** | OneMind root → per-OEM intermediate signing key, revocable. Escrow and unlock terms in the contract | Builds on 01's signing chain decision; links to Q200 (W6) |
| **CRA role** | An OEM selling under its own name is the **manufacturer** under CRA [C-W6-015]. OneMind supplies SBOMs, security updates and a vulnerability-handling feed under contract | The contract must allocate duties |
| **First targets (year 2–3)** | Small robot, drone and IoT-gateway makers using Jetson, Pi CM5 or x86 | M-7 moat; W19 picks the names |

---

## 9. Education revenue (W-2)

Circle costs $89/mo (Professional), **$199/mo (Business, needed for its API and MCP access)** or $419/mo (Scale) [C-W16-046]. Recommendation: free docs and a free community (trust). Paid **cohort courses** ("build your own OneMind box", "TAK node in a weekend", "greenhouse automation") and team training for OEMs. Treat education as a **customer-acquisition channel that pays for itself**, not a main revenue line, until data says otherwise. Founder decision Q320 (Circle vs self-hosted) is W13's.

---

## 10. Partnerships (Q188, Q189, D-006)

| Partner | What the primary source says | What it means for OneMind | Next action |
|---|---|---|---|
| **NVIDIA Inception** | Free; requires incorporation (with its date), a working website, a pitch deck, <10 years old, founder-run; resellers and distributors excluded; revenue not required [C-W16-031]. Preferred pricing is a **rebate on a subset of enterprise GPUs** through suppliers, with no special access [C-W16-032] | **Flag against D-006's rationale ("Jetson/GPU discounts"):** the FAQ does not mention Jetson pricing. The discount may not apply to Robotics SKUs. Present OneMind as a software platform and OEM, not a reseller (the application draft already does) | Incorporate, publish the site, apply; ask the questions in the outreach draft |
| **NVIDIA Partner Network** | OEM partner type; Embedded Systems (Jetson) competency; requirements vary by level [C-W16-033] | The route to "NVIDIA-optimised OneMind boxes" (N-8) in year 2+. The Jetson BSP licence is now verified: redistributable unmodified on NVIDIA hardware, with conditions [C-LIC-001] [C-LIC-048] | After the first SKU ships |
| **Raspberry Pi** | Pi 5 and CM5 in production until at least January 2036 [C-W16-034, C-W16-035]; "Powered by" logo by application; Design Partners [C-W16-036]; Raspberry Pi is an **MHS early adopter** with a Camera MHS Driver [C-W16-037] | The best-matched hardware partner for the 10-year Edge/Lite story. MHS gives a shared technical agenda | Apply for the logo; outreach on supply allocation and MHS |
| **Canonical** | Modified Ubuntu needs approval [C-W2-050]; Pro for Devices price unpublished, IoT services $3k–25k+ [C-W2-006] | Gates the Jetson and GPU flavours (01 Q-W2-1) | Quote and permission request (drafted) |
| **Anthropic MHS** | Research preview for **scientific labs and advanced manufacturers**, by application; MCP/CLI/code; open source later [C-W16-037] | OneMind's consumer and homestead angle is **outside the stated preview audience**. Pitch it as a device-integration platform (Pi, Jetson, robots) and contributor of safety evaluations. Do not plan revenue on it | Waitlist entry with a revised pitch (drafted) |
| **Open Home Foundation** | Commercial partner model [C-W16-012] | Partner, don't compete: run HA as OneMind's IoT engine (W8) | Later: explore a commercial partner relationship |

**Note on `docs/applications/nvidia-inception.md` (not edited; docs/ is read-only for this run):** it lists "GPU Operator (with K3s support)" as a use of NVIDIA technology. 01 found the GPU Operator does not support Jetson, and NVIDIA's AI-conformance list does not include k3s [C-W4-023, C-W4-038]. Zeus should reword that line before submitting.

---

## 11. Segments, market size and the first 100 customers (Q187, Q282)

### 11.1 Top-down market sizes (rule 1: SECONDARY, at least 2 sources, ranges)

These are **category proxies**, not OneMind's market. Analyst methods are proprietary. Each page names only its broad method.

| Proxy market | 2025 range | Growth range | Sources and stated method | Relevance |
|---|---|---|---|---|
| Consumer NAS (home-server proxy) | **$6.7–6.9B** | 9.4–12.2% CAGR | Grand View: "IR documents, primary interviews, paid databases" [C-W16-038]; Polaris: "secondary research, primary research, database, analyst review" [C-W16-039] | Lite/Pro boxes compete for this money |
| Robot operating-system software | **$0.67–0.74B** | 12.7–13.7% CAGR | Mordor [C-W16-040]; Precedence [C-W16-041] (method not stated on the page) | Robotics OS and OEM licensing. Small, industrial-led (56% industrial robots [C-W16-040]) |
| Edge AI hardware | **$9.1–26.1B** (definitions differ ~3×) | 17.6–22.1% CAGR | MarketsandMarkets press release [C-W16-042]; The Business Research Company [C-W16-043] | Pro, Robotics and Omni hardware |

### 11.2 Bottom-up signals (reachable communities)

| Segment | Signal | Claim |
|---|---|---|
| Smart-home self-hosters | 2.28M+ active HA households, +28%/yr | C-W16-013 |
| Home-server buyers | Unraid: "over half a million users" (vendor claim) | C-W16-029 |
| AI-box early adopters | Olares Kickstarter $2.34M; at the reported ~$2,999 launch price that is roughly 780 units (derived; the price is from the Olares teardown) | C-W16-018 |
| NAS crowdfunding | ZimaCube about 1,252 backers (unverified) | C-W16-027 |
| TAK users | ~300,000 US federal (FY25) to >500,000 global | C-W16-044, C-W16-045 |
| Robotics developers | Not measured here (W19 / W7) | — |
| Homesteaders, off-grid, EU sovereignty buyers | **No defensible primary or two-source number found.** Founder interviews needed (T-W16-3) | — |

### 11.3 Segment scorecard and first-100 path

| Segment | Willingness to pay (evidence) | Sales cycle | Fit with Tier A stack | Barriers | Rank |
|---|---|---|---|---|---|
| **Homestead / greenhouse / off-grid** | Hardware + support (HA, Start9 anchors) | Short (DTC) | High: Pi leaf + Lite hub, NATS buffering (W8) | Market size unmeasured | **1** |
| **Privacy families / self-hosters** | Proven: $199–949 boxes, $65/yr Link | Short | High | Crowded (Umbrel, HA, Zima) | **1 (with the above)** |
| **TAK field teams (SAR, volunteer, civilian)** | Unmeasured; TAK base is large [C-W16-044] | Medium | High: TAK profile (W8) | Gov buyers need NDAA, TAA, FIPS (W6 Q182/Q183) | **2** |
| **Robotics developers / OEMs** | Proven: VC money in robotics software [C-W16-024, C-W16-025] | Long | Medium: Jetson flavour gated on Canonical | Licence gate (Q-W2-1), support load | **3 (year 2–3)** |
| **SMB** | Proxmox-style support | Medium | Medium | Support staffing | 4 |
| **Public safety / enterprise** | High, but slow | Long | Medium (RKE2/FIPS later) | Enterprise sales (Sandstorm lesson [C-W16-050]) | 5 (year 3+) |

**First 100 paying customers (hypothesis to test, REC-W16-08):** a **"Greenhouse + TAK field kit" pair** (Lite hub + 1–2 Pi Edge leaves), sold DTC with a year of support included, launched through education content and a crowdfunding or pre-order campaign. A campaign tests price before inventory is bought, as the competitors did [C-W16-018]. **Founder decision** (open question 4 in REQUIREMENTS): this pick is the most defensible from evidence, but it is marked `blocked: founder-decision`.

---

## 12. Funding, entity and grants (Q197, Q202)

| Item | Primary-source fact | Implication |
|---|---|---|
| Incorporation | Inception requires an incorporated company and its date [C-W16-031] | Incorporate before D-006 can proceed |
| Foundation later | OHF: Swiss Stiftung that owns the brands and licenses them to commercial partners [C-W16-012] | Years 3–5 option to lock in community trust (M-8); not now |
| NLnet NGI Zero | €5k–50k first grants, European dimension, next deadline 2027-01-03 [C-W16-047] | Fits open components (e.g. the RAUC Secure Boot backend, MHS/MCP adapters). Eligibility of a US company is uncertain, needs checking |
| Sovereign Tech Fund | Work must cost more than €50k and be open base technology [C-W16-048] | Fits a shared upstream piece (e.g. RAUC improvements), not OneMind's product |
| DigitalOcean Hatch | Credits (amount varies) for 12 months + 15 months of support [C-W16-049] | Fits the founder's existing DO stack (CI, Link prototype) |
| SBIR / AFWERX, EU Horizon | Not researched in this pass | Gap, listed in `26-…` |
| Entity type (C-corp, LLC, EU subsidiary) | No primary source opened | **blocked: founder-decision** + counsel |

---

## 13. Failure modes and company-death commitments (Q310, REC-W16-10)

| Failure | What happened | OneMind commitment |
|---|---|---|
| Sandstorm (2017) | Open project thrived; the business failed on enterprise sales [C-W16-050] | No closed enterprise edition in year 1; sell hardware, services and support |
| WD My Book Live (2021) | Unpatched since 2015; an unauthenticated factory-reset bug wiped devices [C-W16-051] | Declared support period per SKU, then a clear end-of-support plus an offline-only mode; never leave a remote-wipe path unauthenticated |
| Revolv, Insteon, Helm, Stadia | Not opened in this pass | Gap (Tier C) |

**Commitments to publish at launch:** (1) The box works fully offline and LAN-only forever (M-1). (2) One-click full export plus restic restore onto any hardware (01, W5). (3) Signing-key escrow with a published "if OneMind ceases" procedure, and an owner-controlled key option (Q200/Q235 with W6). (4) An end-of-support date shown at purchase (CRA [C-W6-005]).

---

## 14. Company cost model sketch (Q313, partial)

| Cost line | Unit price (primary) | Note |
|---|---|---|
| Update and backup storage, CDN | R2: $0.015/GB-month, **no egress charges** [C-W16-052] | Update egress for 10k devices costs nothing on R2; storage dominates |
| Signing HSM | YubiHSM 2 $650; FIPS model $950 [C-W16-053] | Buy 2 (primary + escrow) |
| Community/education platform | Circle Business $199/mo [C-W16-046] | Or self-host (W13) |
| WWHA-style certification you run | Admin-level fee benchmark CHF 500/yr [C-W16-015] | Revenue, not cost |
| Ubuntu Pro / ELTS / RHEL | Unpriced [C-W2-006, C-W2-003] | Blocked: paywalled (01 DC-03) |
| CI build farm, insurance, legal, support staff | Not researched | Remaining for `21-…` |

Break-even per tier is **not computed**, because landed BOM (W10) and the OS-support fees (DC-03) are missing. Status: partial.

---

## 15. Things that contradict or strain the Tier A foundation (flagged, not resolved)

1. **Jetson / Robotics SKU cannot be sold yet.** Canonical's redistribution rule [C-W2-050], NVIDIA's statement that the Ubuntu rootfs is outside its L4T redistribution answer [C-REF-DC-cost-007], together block a commercial Robotics box. (The BSP licence itself is no longer a blocker: it permits unmodified redistribution on NVIDIA hardware, with conditions [C-LIC-001] [C-LIC-048].) That box is the moat edition (M-7). 01 already gates the GPU flavour on Q-W2-1. **This file adds that the Robotics SKU's revenue plan is gated too.**
2. **Edge edition is a leaf, not "the same OS"** (§6.2). F-14 marketing must be worded carefully.
3. **D-006 rationale (Jetson/GPU discounts) is weaker than stated:** Inception preferred pricing covers "a subset of enterprise-grade GPUs" by rebate [C-W16-032].
4. **CRA "security updates on by default"** (01, founder decision SEC-05) means support plans cannot charge for security fixes (§7).
5. **bootc Industrial profile (year 2)** implies RHEL subscription or AlmaLinux. If RHEL, a per-device fee (unpriced) enters the Industrial SKU cost; AlmaLinux is the free EL10 tier [C-STEEL-IIOT-002], and Red Hat Device Edge already runs on Jetson Orin [C-W2-041]. Decide when the profile ships.
6. **Anthropic MHS** targets labs and manufacturers [C-W16-037]. The `docs/applications/anthropic-mhs-preview.md` pitch leads with consumer and homestead use, which fits the preview's audience less well.

---

## 16. Founder actions and tests (for `22-…` and `26-…`)

| ID | Action | Pass / done when | Status |
|---|---|---|---|
| T-W16-1 | Trademark clearance search (USPTO, EUIPO, UKIPO, WIPO) by an attorney for "OneMind" and "OneMind OS" in classes 9 and 42 | Written opinion: low conflict risk, or a new name chosen | blocked: founder-decision |
| T-W16-2 | Incorporate; publish a landing page; submit Inception | Inception acceptance | blocked: founder-decision |
| T-W16-3 | 30 customer-discovery interviews (10 homestead, 10 self-host family, 10 TAK field) with a scripted questionnaire on price for the Lite box, the Link subscription and support | At least 30% say they would pre-order at the band price | blocked: founder-decision |
| T-W16-4 | Send the Canonical, NVIDIA, Raspberry Pi and MHS outreach (drafts in `evidence/outreach-drafts-W16.md`) | Written answers recorded in the claims ledger | blocked: founder-decision |
| T-W16-5 | Pre-order or crowdfunding test for the first kit | More than 100 paid pre-orders | after T-W16-3 |

---

## 17. Recommendation → requirement trace

| Rec | Requirement IDs |
|---|---|
| REC-W16-01 | D-001, P-7, M-1, M-8, R-2, H-1, F-6 |
| REC-W16-02 | D-001, A-5, A-6, F-5 |
| REC-W16-03 | H-1, H-4, W-3, W-4 |
| REC-W16-04 | P-5, P-6, D-002, F-14, A-7, H-3 |
| REC-W16-05 | H-1, A-7, A-8 |
| REC-W16-06 | R-2, R-3, R-1, M-4 |
| REC-W16-07 | H-4, F-4, F-5, M-7, A-7 |
| REC-W16-08 | M-4, F-13, M-6, H-1, open question 4 |
| REC-W16-09 | N-8, F-2, AI-2, N-10, D-006 |
| REC-W16-10 | M-2, R-3, M-8, M-1 |

**Not covered here, and owned elsewhere:** BOM and ODM economics (W10: Q176, Q180), tariffs and export controls (Q177, Q178), certification costs (Q170), and the Marketplace revenue share for paid plugins (W19).
