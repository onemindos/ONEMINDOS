# VillageOS (villageos.ai / ReGen Villages) - competitor research

Research date: 2026-11-10. Rule applied: only claims backed by a source I opened are stated as fact; everything else is in the UNVERIFIED list.

## 1. Summary

- VillageOS is NOT an operating system in the OneMind sense. It is a design-and-orchestration software platform (generative land-development design, a "temporal graph" database, simulation/ingestion microservices, a web GUI and CLI) from **ReGen Villages Holding B.V.**, a Dutch company founded 2016 by James Ehrlich (Stanford-affiliated). [S2, S3, S6]
- villageos.ai is a one-page marketing site that presents VillageOS as the lead member of an "open-source consortium" (VillageOS, Khorium.ai, Nurture Robotics, Earth Rover plus universities). The consortium claims are self-reported; I found no independent confirmation. [S1, S5]
- The "EdgeAI Operational Intelligence" layer (stage 04) is a paragraph of marketing copy. No code, hardware, protocol or control-loop spec is public. The public code is a server-side graph platform, not edge firmware. [S1, S6]
- Public GitHub code exists (ReGen-Villages/VillageOS-API, AGPL-3.0 + commercial dual license, .NET 10 / React / Python/Go/Rust/Node examples), actively committed (last push 2026-11-10), explicitly "prerelease, not production ready". The core server "Mycelium" is in a separate repo that is not public. [S6]
- Assessment: adjacent, not a direct competitor today. It is a planning/finance/design layer for land development. OneMind is the runtime/edge layer. Best framed as a potential integration target and a source of ideas, with low near-term threat.

## 2. Facts table

| Item | Fact | Source |
|---|---|---|
| Site | villageos.ai: static single page, last-modified 2026-02-17, "(c) 2026 VillageOS.ai, A Stanford University Spin-off" | S1 |
| Tagline | "Neighborhood-Scale Intelligence for Resilient Local Sustenance"; "open-source consortium building low-power, decentralized AI systems" | S1 |
| Legal entity | ReGen Villages Holding B.V. / ReGen Villages BV (Netherlands). Copyright holder in the code repo | S3, S6, S7 |
| Founded | 2016 (ReGen Villages) | S3 |
| Founder | James Ehrlich | S2, S3, S4 |
| Open-source API | Said "not yet released" in June 2026 podcast; a different public repo (VillageOS-API) exists since 2026-07-01 | S4, S6 |
| Code license | AGPL-3.0 or commercial; mandatory attribution "Powered by VillageOS" | S6 |
| Repo activity | Created 2026-07-01, pushed 2026-11-10, 1 star | S6 (gh api) |
| Contact form | villageos.ai posts to /aip/contact.php; server header `x-powered-by: PHP/7.4.33` (PHP 7.4 is end-of-life) | S1 (curl) |
| Site features | i18n.js (not publicly fetchable, 404) and rtl.css, so multilingual / RTL support is intended | S1 |
| Standard pages | /about, /team, /research, /pilots, /docs, /blog, /partners, /sitemap.xml, /robots.txt all return 404 | S1 (curl) |
| Claimed value | "$94B in avoided-cost potential from improved community design" (no method or source given) | S1 |

## 3. Team and partners

**People (public professional info only)**
- **James Ehrlich**: founder of ReGen Villages Holding B.V.; Director of Compassionate Sustainability and Entrepreneur in Residence at Stanford CCARE (since Aug 2017); affiliate of Stanford Woods Institute; MS studies in Mechanical Engineering at Stanford 2013-2016 with the Center for Design Research; Singularity University faculty; NASA Ames senior fellow (Opus Novum). Earlier career in video-game / special-effects software. [S3, S4]
- Aaron Frank wrote the 2024 Singularity Hub profile (author, not team). [S2]
- villageos.ai names no other individuals. No team page exists. [S1]

**Consortium as listed on villageos.ai [S1]** (all self-reported)

| Member | What the site says it does | What I could verify |
|---|---|---|
| VillageOS | Stanford spin-off ML platform for generative design + EdgeAI ops | Matches ReGen Villages' software [S2, S3, S6] |
| Khorium.ai | "Stanford spin-off" accelerating physics simulation to validate VillageOS designs | khorium.ai is a real AI simulation-automation company (MeshGen, SimOps, EvalTool, Teleology: CAD to mesh to solve to validate to redesign). The Stanford spin-off claim and the VillageOS link are NOT confirmed by its own site or search. [S8] |
| Nurture Robotics | "Open-source platform for self-assembling, task-agnostic robotics" (SAMI) | nurturerobotics.com exists but its homepage only says "Innovative Robotics Solutions"; no SAMI content found; search found nothing on SAMI. UNVERIFIED |
| Earth Rover | "University of Exeter and Harper Adams Institute backed" autonomous ground systems for resource mapping / ecological monitoring | Two distinct Earth Rovers exist. (a) Earth Rover Program (Harper Adams research; partners Exeter, CIAT, CER-K; funded by Bezos Earth Fund and Optimus UBS; seismic/GPR soil mapping; no robot described; no VillageOS mention) [S9, S10]. (b) earthrover.farm, a UK ag-robot company (CLAWS laser weeding robot) [S11]. The VillageOS description (Exeter + Harper Adams, ecological mapping) fits (a) better, but a rover is not shown. Which one is meant is UNVERIFIED |
| Academic / institutional | Stanford (CDR, Doerr School, Woods, CCARE), KTH AI Society, American Univ. of Ras Al Khaimah (proposed), FLAME Univ., Chanakya Univ., TU Delft, Wageningen, NYU Abu Dhabi, MBZUAI, KACST | Listed only on villageos.ai; none independently confirmed. Ehrlich's Stanford affiliation (CCARE, Woods, CDR) is confirmed [S3] |

## 4. Technology

**Design platform (2024-2026 description).** Generative design that ingests parcel boundaries, topography, climate history, hydrology, soils, wildlife corridors, traffic, property values, demographics and local regulations; game-engine 3D "diorama" (Unreal Engine + Cesium map data per 2024 article); language / foundation models to query site conditions; feasibility, cost, ESG/SDG and carbon modeling. [S2, S4]

**Operational ("EdgeAI") layer as described by the founder.** After construction: tinyML sensors, small language models, a "digital mycelial network" of decentralized nodes, a small energy-efficient edge data center, and a thin privacy-preserving cloud link (anonymized, encrypted, compressed) for cross-site learning. Infrastructure discussed: solar/agrovoltaics, small wind, biogas, aquaponics, waste-to-energy. No sensor models, boards, protocols or control-loop details were named. [S4]
villageos.ai says only: EdgeAI "aggregates sensor data from infrastructure and weather systems to tune performance without centralized dependencies" and feeds operational data back to design. [S1]

**Public code: VillageOS-API [S6].** Client-side tools for a "temporal graph platform" (everything stored as connected "Things" with history), whose server **Mycelium** is a separate, non-public repo.
- Trellis: React web GUI (Sigma.js graph, Three.js + IFC viewer, SSE live updates, config-driven operations dashboards, land-intake, pipelines pages).
- Taproot: CLI (CRUD, temporal queries, services, pipelines, event stream).
- Microservices (.NET 10 mostly; Python, Go, Rust, Node examples): Delta (data-source registry), Tributary (HTTP calls + JSONata transforms, ESRI/ArcGIS auth), Metabolism (consume/produce simulation), Phloem (pipeline orchestrator), Xylem (IFC ingest), Forage (site data resolution), Intake (land intake), EnergyBalance (net-positive site energy verdict), WaterReserve (stored water vs consumption simulation), ModelBridge, Quadrat (GeoTIFF raster reader), Feedback (files bugs to Azure DevOps).
- Service contract: HTTP plus a JWT signed on P-256. CI uses Azure Pipelines; docs published to a GitHub wiki.
- Searching the services doc for MQTT / Modbus / OPC-UA / IoT / MCP found no hits: **no IoT protocol, hardware or MCP support is evident in the public repo.**

**Other repos named "villageos" on GitHub are unrelated or unverified** (hackathon-style projects by other users). I did not attribute them to this company.

## 5. Pilots

- villageos.ai: "Pilot Projects: South Africa, Mexico, Sweden - Active research collaborations with landowners testing VillageOS generative design and EdgeAI operations across diverse climate zones and regulatory contexts." No sites, partner names, dates, scale or results are given. [S1] Nothing else I found corroborates these three pilots. UNVERIFIED beyond the claim.
- June 2026 podcast: demo site near Riyadh (urban-edge parcel, ~1,200-1,300 families scenario); 2012 research beds in East Palo Alto and San Anselmo; comparison modeling for Nevada and the Nordics; planned Stanford Doerr / Planetary Intelligence Accelerator affiliation. [S4]
- Historical: 2016 Almere (Netherlands) land grant and planned ~100-home ReGen Village, designed with EFFEKT architects; later coverage mentions 200-300 homes and 2018 infrastructure permits. No source I found confirms completion. [S5, S7]

## 6. Business

- Model signals: dual-licensed software (AGPL + paid commercial license, attribution required); consortium/open-science positioning; "blended finance" pitch connecting landowners, developers and governments with institutional capital (insurers, sovereign wealth funds, pension funds). Does not appear to sell hardware. [S1, S6]
- Target customers (form on site): landowners, developers, government/planning, institutional investors, insurance/risk, universities. [S1]
- Funding: ReGen Villages' older materials cite a Series A target (reports vary: EUR 16M to EUR 25M); no amount raised is confirmed. [S7 via search summaries] Treat as UNVERIFIED and dated (2016-2018).
- Status: early. Website is a brochure; software described as in development (2024) and API "not yet released" (June 2026); public repo marked prerelease. Active engineering cadence in Nov 2026 suggests a funded small dev team. [S2, S4, S6]
- Real estate / finance orientation, not edge-compute product orientation.

## 7. Relationship to OneMind OS

**Overlap**
- Same domain vocabulary: smart communities, food / water / energy, resilient decentralized neighborhoods, robotics/physical AI, edge AI, sensor-driven optimization, off-grid contexts, AI agents.
- Both talk about digital-twin / graph-of-things models (their temporal graph vs OneMind's agent-accessible app/device layer).

**Differences (why not a direct competitor today)**
- VillageOS: pre-construction design, feasibility, finance and simulation platform; centralized server (Mycelium) with a GUI/CLI; customers are land developers and capital. OneMind: runtime OS on owned hardware (Kubernetes app platform, MCP-permissioned agents across apps/devices, robotics, mesh, TAK), sells hardware; customers are homesteads, communities, operators.
- No public edge OS, no hardware, no device protocols, no MCP, no tactical (TAK) or mesh components visible.

**Positioning verdict**
- Competitor: weak, only on the "smart-community narrative" and consortium/finance mindshare.
- Partner / integration target: plausible. Their stage 04 "EdgeAI Operational Intelligence" needs exactly what OneMind provides: a sovereign edge runtime with sensor ingestion, local agents and actuation. OneMind could be the substrate that runs VillageOS-style apps (their microservices follow an HTTP+JWT contract and are containerizable; AGPL requires care).
- Customer: possible as a reference deployment for pilot sites (South Africa / Mexico / Sweden) if those become real.

**Concrete integration ideas (hypotheses, not validated)**
1. Ship a OneMind "community design to operations" bridge: import their site/model (IFC, parcel, energy and water studies) into OneMind as the digital-twin seed; OneMind pushes live sensor state back.
2. Package Trellis/Taproot/microservices as OneMind catalog apps (check AGPL network-use obligations first).
3. Expose OneMind sensor and actuator data via an API their Forage/Tributary/ModelBridge style services can consume.

## 8. Lessons for OneMind

1. Lead with a measurable outcome narrative: avoided losses, insurability, supply-chain resilience. It gives them a finance audience (insurers, sovereign funds) that OneMind's technical positioning lacks.
2. Open core with dual licensing (AGPL + commercial + mandatory attribution) is a workable template if OneMind open-sources parts.
3. Design-to-operate feedback loop (operational data refining designs) is a strong product story; OneMind can offer the operate half and the data return path.
4. Consortium framing buys credibility with universities cheaply, but their listed partner claims are mostly unverifiable. OneMind should publish named, verifiable partners and artifacts instead.
5. Config-driven dashboards over a graph model (KPI / chart / table widgets from a JSON spec) is a pattern worth considering for OneMind UI.
6. Their gap is the one OneMind fills: no shipped hardware, protocols, offline/mesh, or agent permissioning. Do not copy the pre-construction planning scope.

## 9. Risks

- Narrative collision: both brand as an "OS" for resilient communities; buyers or press may conflate them. Differentiate as runtime/edge OS vs planning platform.
- Credibility asymmetry: Stanford affiliation and a long university list are strong signals even though largely unverified; a reseller or integrator could bundle a competing edge layer under the VillageOS brand.
- Licensing: AGPL with attribution plus a commercial option; embedding their code in OneMind could force source disclosure of network-served derivatives.
- Partner claims could be loosely substantiated (Earth Rover ambiguity, Khorium/Nurture unclear). Do any partnership due diligence directly before relying on them.
- "Open-source consortium" but core server (Mycelium) is private: openness is partial.
- Moving target: repo is active and the site was updated Feb 2026; the EdgeAI layer could be specified at any time.

## 10. UNVERIFIED list

- Pilots in South Africa, Mexico, Sweden: only claimed on villageos.ai.
- That Khorium.ai is a Stanford spin-off and an active VillageOS collaborator.
- What Nurture Robotics' "SAMI" is, and that it is open-source; nurturerobotics.com has no product content.
- Which "Earth Rover" is the consortium member, and whether any rover or hardware is involved.
- All university collaborations other than Ehrlich's own Stanford affiliations (KTH AI Society, RAK, FLAME, Chanakya, TU Delft, Wageningen, NYUAD, MBZUAI, KACST).
- Any EdgeAI hardware, sensors, IoT protocols, control loops or actuator integration.
- The "$94B avoided-cost" figure and its method.
- Funding raised, valuation, investors, headcount; Series A amounts are from dated press (2016-2018).
- Whether the Almere project was built.
- Mycelium (core server) architecture and license: repo not public.
- "Patent-pending" status of VillageOS (from founder bio, no patent number seen).
- Content of regenvillages.com beyond its title/meta (page is JS-rendered; fetch returned a title only).
- Stanford Center for Design Research as the originating lab: confirmed only that Ehrlich did master's-era research with CDR [S3]; the site's claim of a Stanford "spin-off" is not independently verified by Stanford OTL.

## 11. Sources (all opened 2026-11-10)

- S1: https://www.villageos.ai/ (HTML, headers via curl; sub-paths /about /team /research /pilots /docs /blog /partners /sitemap.xml /robots.txt returned 404; /aip/contact.php returned x-powered-by PHP/7.4.33)
- S2: https://singularityhub.com/2024/12/29/inside-villageos-a-simcity-like-tool-for-regenerative-living-spaces/
- S3: https://lifeboat.com/bios.james.ehrlich.shtml
- S4: https://edgeaipod.buzzsprout.com/2363070/episodes/18240345-village-os-ai-for-sustainable-living (EDGE AI POD, 2026-06-11)
- S5: web search results (search summaries only): ecowatch.com/2016/06/07/off-grid-regen-village/, effekt.dk/news/2016/6/3/land-grant-signed-for-regen-villages-in-almere-netherlands, archdaily.com/794167, goodnewsnetwork.org eco-village article
- S6: https://github.com/ReGen-Villages/VillageOS-API (README, LICENSE, LICENSE-COMMERCIAL.md, docs listing, commits via gh api)
- S7: https://regenvillages.com/ (title and meta tags only: "Opensource orchestration software for the design and operation of resilient land developments")
- S8: https://khorium.ai/ (product pages: MeshGen, SimOps, EvalTool, Teleology); search results for Khorium (f4.fund/startups/khorium)
- S9: https://www.harper-adams.ac.uk/research/project/2393/eart-rover-program
- S10: https://www.earthroverprogram.org
- S11: https://www.earthrover.farm/ and https://business.esa.int/projects/Earth-Rover
- S12: https://nurturerobotics.com/ (homepage; no product detail)
