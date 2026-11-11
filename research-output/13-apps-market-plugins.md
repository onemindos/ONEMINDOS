# 13 · Apps, Market, internal apps and plugins (W12)

**Date:** 2026-11-11 · **Tier:** B (≥ 1 primary source per claim) · **Status:** draft complete; no refuters run (Tier B does not require them)
**Claims:** [`evidence/claims/W12.csv`](evidence/claims/W12.csv) (C-W12-001…077, C-W12-101…170) · **Sources:** [`evidence/sources/W12.md`](evidence/sources/W12.md) · **Question bank:** [`evidence/qbank/W12.md`](evidence/qbank/W12.md)
**Builds on:** `01-FOUNDATION-DECISION.md` (Market compiles `onemind.app.yaml` to Helm, imports Compose, REC-DEC-10), `05-…` §1.4 (node classes) and §8 (capability-based accelerators), `06-…` (backup hooks in the manifest), the umbrelOS, Olares and HAOS teardowns in `02-competitors/`.
**Not here:** plugin types, extension points, plugin SDK/CLI, signing and the partner programme belong to **W19** (`29-PLATFORM-ECOSYSTEM-MARKETPLACE.md`). Strava/AI permission design and MCP grants belong to **W9** (`10-ai-capability-layer.md`). CRA duties for apps OneMind distributes belong to **W6** (`07-…`, Q212). This file cross-references them and does not repeat them.

> ### Explain it like I'm the founder
> **The Market is three things: a list of apps, a package format, and a set of rules about what you're allowed to ship.** We read the two catalogs you named, line by line: Umbrel's (399 apps) and Olares's (396 apps). They overlap far less than you'd think, with only 56 apps in common [C-W12-001, C-W12-003, C-W12-008].
> **The big surprise is legal, not technical.** Umbrel's app store has **no license at all**, so you can't copy its app files [C-W12-002]. Olares's app store is Apache-2.0, the same license as OneMind, so you *can* reuse it with credit [C-W12-004]. CasaOS's store is also Apache-2.0 [C-W12-009].
> **Several "open source" apps are not open source in a way that lets you sell boxes with them preinstalled.** n8n, Open WebUI, Tandoor, Outline, Akaunting, Invoice Ninja and monetr all carry business restrictions [C-W12-015…021]. And at least one Olares listing calls an app "MIT" when its server part is under a paid enterprise license [C-W12-007]. So every app in the OneMind Market gets a **license class**, and only the green classes go on boxes you sell.
> **The package format:** one `onemind.app.yaml` plus a Helm chart, as 01 decided, with an importer that turns Compose files into OneMind apps. It imports from upstream projects and from the Apache-licensed stores, **never from Umbrel's unlicensed store**.
> **Your own apps:** build the thin parts that make OneMind special (the shell, tasks and knowledge over your Markdown vault, the robot registry, the AI capability layer). **Integrate** proven open-source engines for the heavy parts: Home Assistant, Actual (finance), wger/Endurain (fitness), Mealie/Grocy (family), Kiwix/Kolibri (education) and SpiderFoot/OpenCTI (OSINT).
> **Wellness and finance data can't simply be "given to the AI".** Strava bans AI use outside its own MCP [C-W12-044]. Oura allows AI only through *its* MCP server and forbids caching that data [C-W12-043]. Plaid uses your users' bank data to train *its own* AI [C-W12-065]. The design answer is a per-integration **"may AI see this?" switch**, off by default for these sources.

---

## 0. The answer in twelve lines

1. **Seed the Market with about 55 apps in 12 categories** (§3). They are chosen from the Umbrel and Olares catalogs plus the apps OneMind's profiles need. Every one has a license checked against a LICENSE file pinned to a commit [C-W12-101…170].
2. **Four license classes** decide what OneMind may do with each app: **L1** permissive, **L2** copyleft, **L3** source-available or fair-code, **L4** proprietary or no license. Only L1 and L2 apps may be **preinstalled on sold boxes** (§4).
3. **Never copy umbrel-apps manifests:** that repo has no license [C-W12-002]. Olares's beclab/apps [C-W12-004] and CasaOS-AppStore [C-W12-009] are Apache-2.0 and may be adapted, with attribution.
4. **App format = Helm chart + `onemind.app.yaml`**, as decided in 01. The manifest adds the fields both competitors proved useful: license, RAM/CPU/disk needs, architectures (Olares) [C-W12-005]; permissions, widgets, `implements` and backup exclusions (Umbrel) [C-W12-013]. It also adds what neither has: AI capabilities with effect levels, a data-use policy per integration, and accelerator *capabilities* instead of vendor GPU names (05 §8).
5. **Importer:** `onemind app import` converts upstream `compose.yaml` files, CasaOS `x-casaos` apps and Olares OAC charts into a draft OneMind app. It renders through one OneMind library chart. kompose (Apache-2.0) is the reference [C-W12-012]. Imports enter the Market at the lowest quality tier until reviewed.
6. **Quality tiers** borrow Home Assistant's machine-checked scale (54 rules, Bronze to Platinum [C-W12-014]): **Community → Listed → Verified → Certified**. Listed is enforced by a linter. Verified means OneMind CI installs, upgrades, backs up and restores the app on reference hardware.
7. **Model weights are apps too.** Olares ships 58 model packages, and many carry Gemma/Llama community licenses [C-W12-006]. OneMind's license matrix must track **model licenses** separately from code licenses.
8. **Build order** (§8): shell and system apps → Knowledge + Projects → IoT + TAK + a **robot registry MVP** (moved earlier than APPS.md proposes, because it shares the Nodes registry and is the moat) → Finance → Family → Wellness → Mesh, Infrastructure, OSINT, Education.
9. **Wellness:** an aggregator that reads HealthKit / Health Connect **on the phone** and syncs to the box, plus the user's own Garmin personal API key [C-W12-045]. Oura and Strava data is **display-only by default**; AI access only through their own MCP servers [C-W12-043, C-W12-044]. HIPAA normally does not apply [C-W12-047]. The FTC Health Breach Notification Rule may, so data leaving the box is encrypted end to end [C-W12-048].
10. **Finance:** integrate **Actual Budget (MIT)** as the engine [C-W12-147]. Use **SimpleFIN** for North-American bank sync (read-only, $15/yr, user-owned) [C-W12-060, C-W12-061]. GoCardless is closed to new users [C-W12-063]. Plaid is not a default (it trains its own AI on end-user data [C-W12-065]). The CFPB 1033 open-banking rule exists on paper but is under reconsideration and reportedly enjoined [C-W12-066…068]. AI may read finance data; it may never move money.
11. **OSINT:** keep the module to **world events and infrastructure** (aircraft, ships, hazards, news, the founder's existing feeds), not people search. Scraping a public website is not "without authorization" under the CFAA in the Ninth Circuit [C-W12-072], but contract, GDPR and data-source licences still bind. OpenSky data is non-commercial only [C-W12-075]. Integrate SpiderFoot (MIT), OpenCTI CE (Apache-2.0) and changedetection.io (Apache-2.0); don't bundle Maltego (proprietary) [C-W12-076].
12. **No contradiction with the Tier A foundation was found.** Three tensions are flagged in §11: Market apps need a k3s platform node (≥ 4 GB + SSD), the UX-3 example breaks Strava's terms, and preinstalling copyleft apps carries CRA and source-offer duties.

---

## 1. Glossary

| Term | Meaning |
|---|---|
| **Catalog / app store repo** | A Git repository of app definitions (one folder per app) that a Market reads. |
| **Manifest** | The file describing an app: name, ports, storage, permissions. Umbrel: `umbrel-app.yml`; Olares: `OlaresManifest.yaml`; OneMind: `onemind.app.yaml`. |
| **Helm chart** | The standard Kubernetes package: templates plus values. OneMind apps are Helm charts plus a manifest (01). |
| **OAC** | Olares Application Chart: Helm chart + `OlaresManifest.yaml`. |
| **Compose / `x-` extension** | Docker Compose file; fields starting with `x-` are ignored by Compose, so stores hide metadata there (`x-casaos`) [C-W12-011]. |
| **Importer** | A tool that converts another store's app (Compose, CasaOS, OAC) into a OneMind app draft. |
| **SPDX** | A standard short name for a license, e.g. `Apache-2.0`, `AGPL-3.0`. |
| **Permissive (L1)** | MIT, Apache, BSD, MPL, EPL: reuse and sell freely, keep notices. |
| **Copyleft (L2)** | GPL, AGPL, EUPL: share alike; if you distribute or (AGPL) modify-and-serve, you must offer the source [C-W12-031]. |
| **Source-available / fair-code (L3)** | Code is visible but use is restricted (BSL, SUL, ELv2, FSL, Commons Clause, branding clauses). Not open source. |
| **Aggregate** | Shipping separate programs side by side on one medium. Under GPL-3.0 this does not spread the license to the others [C-W12-030]. |
| **Quality tier** | A badge saying how much testing and review an app has had. |
| **PHR** | Personal health record, in the FTC rule's sense [C-W12-048]. |
| **Aggregator (finance)** | A service (Plaid, SimpleFIN, GoCardless) that fetches bank data for apps. |
| **OSINT** | Open-source intelligence: information gathered from public sources. |
| **Data-use policy** | OneMind's per-integration setting for what may happen to the data: display, store, local AI, external AI, act. |

---

## 2. What competitors do (catalogs, formats, licenses)

| Product | Catalog size and shape | App format | Catalog license | Quality / review | Constraint fit with OneMind |
|---|---|---|---|---|---|
| **umbrelOS** | 399 apps; 10 fixed categories, 88 of them Bitcoin [C-W12-001] | Compose + `umbrel-app.yml` (permissions, widgets, `implements`, `backupIgnore`) [C-W12-013] | **None** (no LICENSE) [C-W12-002] | PR lint via `pull_request_target`, otherwise curated [C-TD-umbrelos-028] | **Low** for format (Docker, not k3s) and **zero** for reuse (no license). **High** for manifest ideas and catalog curation. |
| **Olares** | 396 apps; AI-heavy (125 AI, 58 models, 44 agents) [C-W12-003] | Helm + `OlaresManifest.yaml` with license, RAM/CPU/disk, arch [C-W12-005] and a linter [C-TD-olares-028] | **Apache-2.0** [C-W12-004] (Olares itself is AGPL) | Linter + bot; manual review for privileged images, weakened by a name-substring exemption [C-TD-olares-030] | **High**: k3s + Helm, like OneMind. Reusable with attribution. Its license fields are self-declared and sometimes wrong [C-W12-007]. |
| **CasaOS / ZimaOS** | 182 apps [C-W12-009] | Compose + `x-casaos` (architectures, category, port_map) [C-W12-009] | **Apache-2.0** [C-W12-009] | Not researched (Tier B teardown owns it) | **Medium**: Docker, but legally reusable, and the cleanest Compose source for the importer. |
| **Runtipi** | Not counted | Compose + its own JSON | **GPL-3.0** [C-W12-010] | Not researched | **Low**: anything adapted from it would be GPL. |
| **Home Assistant** | Add-ons + integrations | Add-on `config.yaml` schema [C-TD-home-assistant-os-026] | Apache-2.0 (prior-verified) | **Integration quality scale, 54 machine-checked rules in 4 tiers** [C-W12-014] | **High** for the quality-scale *method*; add-ons are Docker, not k3s. |

**What the numbers say:**
- **The overlap is small.** Only 56 upstream projects appear in both catalogs, out of 376 + 231 [C-W12-008]. Merging both catalogs therefore gives breadth, not duplicates.
- **The two stores have different personalities.** Umbrel leans to self-hosted files, Bitcoin and media. Olares leans to AI, models and agents [C-W12-001, C-W12-003]. OneMind's profiles (TAK, greenhouse, family, robotics, AI) need parts of both, plus IoT apps that neither emphasises.
- **Self-declared licenses can't be trusted.** 70 Olares manifests declare no license [C-W12-006]. AFFiNE is declared MIT although its server is enterprise-licensed [C-W12-007]. OneMind's linter must read the **upstream LICENSE at the pinned commit**, as this workstream did, not trust the manifest.

---

## 3. Market seeding: categories and the seed list (Q264, A-1, A-3)

### 3.1 Taxonomy

The taxonomy is built from the two catalogs' categories [C-W12-001, C-W12-003], re-cut to match OneMind's modules (APPS.md) and profiles (P-8):

`Home & IoT` · `Files & Photos` · `Productivity & Knowledge` · `Security & Network` · `AI & Models` · `Automation` · `Media` · `Family & Home Life` · `Health & Fitness` · `Finance` · `Intel & Monitoring` · `Field, Mesh & TAK` · `Developer` · `Education & Offline Knowledge` · `Robotics` (filled by W7/W19 adapters).

Bitcoin and crypto (95 Umbrel apps) are **not a launch category**. They don't serve any requirement in REQUIREMENTS.md, and they would multiply review load (M-6).

### 3.2 Method

- **Candidates:** every app in both catalogs (56), plus apps that a OneMind module or profile needs.
- **License:** the SPDX ID and file read from the upstream repo **at a pinned commit** (`seed-repo-licenses.csv`, script `fetch-licenses.sh`). Repos GitHub labels `NOASSERTION` were read by hand [C-W12-007, C-W12-015…027].
- **Popularity:** neither catalog publishes install counts in its repo, so GitHub stars at access time are the proxy (in the CSV). This is a weak signal, labelled as such.
- **Footprint and arm64:** taken from Olares's declared `requiredMemory` and `supportArch` where present [C-W12-005]. These are declarations, not measurements. Real numbers come from OneMind CI at the Verified tier (§6).

### 3.3 The seed list

Class key (§4): **L1** permissive · **L2** copyleft · **L3** source-available/fair-code · **L4** proprietary/no license/archived. "Box" = may be preinstalled on a OneMind box OneMind sells.

| Category | App | Catalogs | License [claim] | Class | Olares RAM / arch | Box? | Profile / edition | Notes |
|---|---|---|---|---|---|---|---|---|
| Home & IoT | Home Assistant | U, O | Apache-2.0 [C-W12-101] | L1 | 1100Mi, amd64+arm64 | Yes | Greenhouse, family, all | Engine of the IoT module (W8) |
| Home & IoT | ESPHome | U | MIT + GPL-3.0 runtime [C-W12-024] | L1/L2 | — | Yes | Greenhouse | GPL part is firmware built for devices |
| Home & IoT | Zigbee2MQTT | U | GPL-3.0 [C-W12-103] | L2 | — | Yes | Greenhouse, family | |
| Home & IoT | Mosquitto | U | EPL-2.0 OR BSD-3-Clause [C-W12-104] | L1 | — | Yes | Greenhouse, IIoT | MQTT 5 broker (W8) |
| Home & IoT | Node-RED | U | Apache-2.0 [C-W12-105] | L1 | — | Yes | Greenhouse, IIoT | |
| Home & IoT | Frigate | U, O | MIT [C-W12-106] | L1 | —, amd64+arm64 | Yes | Family, security | Accelerator capability (05 §8) |
| Files & Photos | Immich | U, O | AGPL-3.0 [C-W12-108] | L2 | 2000Mi | Yes (unmodified) | Family | |
| Files & Photos | Nextcloud | U, O | AGPL-3.0 [C-W12-110] | L2 | 3Gi | Yes (unmodified) | Pro | Heavy; Pro only |
| Files & Photos | Syncthing | U, O | MPL-2.0 [C-W12-109] | L1 | 128Mi | Yes | All | |
| Files & Photos | Paperless-ngx | U | GPL-3.0 [C-W12-111] | L2 | — | Yes | Family, SMB | |
| Productivity | Vikunja | U | AGPL-3.0 [C-W12-114] | L2 | — | Yes | Pro | Optional task engine (§8) |
| Productivity | Plane | U, O | AGPL-3.0 [C-W12-113] | L2 | 4Gi, **amd64 only** | No | Omni / SMB | Too heavy for Pi |
| Productivity | Trilium | U, O | AGPL-3.0 [C-W12-116] | L2 | — | Yes | Pro | |
| Productivity | BookStack | U | MIT [C-W12-118] | L1 | — | Yes | SMB | |
| Productivity | Memos | U, O | MIT [C-W12-119] | L1 | 512Mi | Yes | All | |
| Productivity | AFFiNE | U, O | MIT client + **EE server** [C-W12-007] | **L3** | 2Gi | **No** | — | List only; production server needs AFFiNE subscription terms |
| Productivity | Outline | — | BUSL-1.1 until 2030-10-23 [C-W12-018] | **L3** | — | **No** | — | List only |
| Security & Network | Vaultwarden | U, O | AGPL-3.0 [C-W12-120] | L2 | 16Mi | Yes | All | Founder already runs it (context/01) |
| Security & Network | AdGuard Home | U, O | GPL-3.0 [C-W12-121] | L2 | 500Mi | Yes | Family | Parental filtering (U-3, W13) |
| Security & Network | Pi-hole | U | EUPL-1.2 [C-W12-122] | L2 | — | Yes | Family | |
| Security & Network | Headscale | — | BSD-3-Clause [C-W12-124] | L1 | — | Yes | All | Remote access (05 §6) |
| Security & Network | Tailscale | U | BSD-3-Clause client [C-W12-123] | L1 | — | Yes | All | Coordination server is a hosted service |
| Security & Network | Uptime Kuma | U, O | MIT [C-W12-125] | L1 | 512Mi | Yes | All | Feeds the alert center (UX-4) |
| AI & Models | Ollama | U, O | MIT [C-W12-126] | L1 | 64Mi + model | Yes | AI, Pro, Omni | AI-8 GPU detection |
| AI & Models | LocalAI | U, O | MIT [C-W12-128] | L1 | —, amd64 in Olares | Yes | AI | |
| AI & Models | AnythingLLM | U, O | MIT [C-W12-129] | L1 | 512Mi | Yes | AI | |
| AI & Models | LibreChat | U, O | MIT [C-W12-132] | L1 | 1Gi | Yes | AI | Preferred chat UI for boxes |
| AI & Models | Open WebUI | U, O | Open WebUI License (branding clause) [C-W12-015] | **L3** | 512Mi | Unmodified only, branding kept | AI | Allowed if never rebranded; > 50 users needs permission |
| AI & Models | SearXNG | U, O | AGPL-3.0 [C-W12-130] | L2 | 64Mi | Yes | AI, OSINT | |
| Automation | n8n | U, O | Sustainable Use License [C-W12-016] | **L3** | 2Gi | **No** | — | List only; prior planning already says embedding needs an OEM deal (context/02) |
| Automation | Activepieces | U | MIT + EE dirs [C-W12-027] | L1 (core) | — | Yes (core only) | Pro | MIT alternative to n8n |
| Automation | ntfy | U, O | Apache-2.0 [C-W12-107] | L1 | 256Mi | Yes | All | UnifiedPush for alerts (D-005) |
| Media | Jellyfin | U, O | GPL-2.0 [C-W12-133] | L2 | — | Yes | Family | Parental model reference (W13) |
| Media | Navidrome | U, O | GPL-3.0 [C-W12-134] | L2 | 100Mi | Yes | Family | |
| Media | Audiobookshelf | U, O | GPL-3.0 [C-W12-135] | L2 | 256Mi | Yes | Family | |
| Family & Home | Mealie | U, O | AGPL-3.0 [C-W12-138] | L2 | 512Mi | Yes | Family | |
| Family & Home | Grocy | U | MIT [C-W12-139] | L1 | — | Yes | Family, homestead | |
| Family & Home | Homebox | U, O | AGPL-3.0 [C-W12-141] | L2 | 20Mi | Yes | Homestead | Inventory |
| Family & Home | Tandoor | U | AGPL-3.0 + Commons Clause [C-W12-017] | **L3** | — | **No** | — | List only |
| Health & Fitness | wger | U | AGPL-3.0 [C-W12-142] | L2 | — | Yes | Wellness | §9 |
| Health & Fitness | Endurain | U | AGPL-3.0 [C-W12-143] | L2 | — | Yes | Wellness | Strava-like, self-hosted |
| Health & Fitness | FitTrackee | — | AGPL-3.0 [C-W12-145] | L2 | — | Yes | Wellness | |
| Health & Fitness | Habitica | U | GPL-3.0 code, **CC-BY-NC-SA assets** [C-W12-026] | **L3** | — | **No** | — | Non-commercial assets |
| Health & Fitness | Fasten On-Prem | — | GPL-3.0, **archived** [C-W12-028] | **L4** | — | No | — | Was the main self-hosted PHR |
| Finance | Actual Budget | U | MIT [C-W12-147] | L1 | — | Yes | Finance engine | §10 |
| Finance | Firefly III | U, O | AGPL-3.0 [C-W12-148] | L2 | 768Mi | Yes | Finance alt. | |
| Finance | Ghostfolio | U | AGPL-3.0 [C-W12-151] | L2 | — | Yes | Finance | Investments |
| Finance | Wealthfolio | U | AGPL-3.0 [C-W12-152] | L2 | — | Yes | Finance | |
| Finance | Sure (Maybe fork) | U | AGPL-3.0; Maybe itself **archived** [C-W12-022] | L2 | — | Watch | — | Project continuity risk |
| Finance | Invoice Ninja | U | Elastic-2.0 [C-W12-020] | **L3** | — | **No** | SMB | List only |
| Finance | Akaunting | U | BUSL-1.1 (≤ 2 users) [C-W12-019] | **L3** | — | **No** | — | List only |
| Finance | monetr | U | FSL-1.1-MIT [C-W12-021] | **L3** | — | **No** | — | List only |
| Intel & Monitoring | SpiderFoot | — | MIT [C-W12-157] | L1 | — | Yes | OSINT | Low activity [C-W12-077] |
| Intel & Monitoring | OpenCTI CE | — | Apache-2.0 CE + EE files [C-W12-023] | L1 (CE) | — | Omni only | OSINT | Heavy stack |
| Intel & Monitoring | IntelOwl | — | AGPL-3.0 [C-W12-159] | L2 | — | Yes | OSINT | |
| Intel & Monitoring | MISP | — | AGPL-3.0 [C-W12-160] | L2 | — | Omni | OSINT | |
| Intel & Monitoring | changedetection.io | U | Apache-2.0 [C-W12-161] | L1 | — | Yes | OSINT, all | |
| Intel & Monitoring | FreshRSS | U, O | AGPL-3.0 [C-W12-163] | L2 | 256Mi | Yes | OSINT, all | |
| Intel & Monitoring | ArchiveBox | U | MIT [C-W12-162] | L1 | — | Yes | OSINT | |
| Field, Mesh & TAK | OpenTAKServer | — | GPL-3.0 [C-W12-165] | L2 | — | Yes | TAK node | W8 owns the TAK choice |
| Developer | Gitea | U, O | MIT [C-W12-166] | L1 | 1Gi | Yes | Pro, Studio | |
| Developer | code-server | U, O | MIT [C-W12-167] | L1 | — | Yes | Studio | |
| Developer | Grafana | U, O | AGPL-3.0 [C-W12-168] | L2 | 512Mi | Yes (unmodified) | Infrastructure | |
| Education | Kiwix (kiwix-tools) | U | GPL-3.0 [C-W12-136] | L2 | — | Yes | Family, homestead | ZIM content licences are separate (W13) |
| Education | Kolibri | — | MIT [C-W12-137] | L1 | — | Yes | Family, school | W13 |
| Dashboard | Homarr | U | Apache-2.0 [C-W12-170] | L1 | — | Study | — | W11 decides (Q266) |
| (Watch) | File Browser | U | Apache-2.0, **archived** [C-W12-029] | L4 | — | No | — | Don't seed an archived project |
| (Watch) | python-matter-server | U | Apache-2.0, **archived** [C-W12-029] | L4 | — | No | — | Matter moves with HA (W8) |

U = in umbrel-apps@3a087384 · O = in beclab/apps@37a1fb4f (`catalog-umbrel-3a087384-olares-37a1fb4f.csv`).

### 3.4 Launch sets per edition and profile (Q264)

Platform nodes only (≥ 4 GB + SSD; 01 §4.5). Leaf devices run adapters, not Market apps (05 §1.4).

| Set | Apps (all L1/L2 so they can ship on boxes) | Why |
|---|---|---|
| **Lite / 4 GB slim (TAK node, greenhouse)** | Home Assistant, Mosquitto, Node-RED, ESPHome, Zigbee2MQTT, ntfy, Uptime Kuma, Vaultwarden, Headscale client, OpenTAKServer (TAK profile) | Fits the capped app budget; matches W8 profiles |
| **Pro (family / home cloud), ~30** | Lite set + Immich, Syncthing, Paperless-ngx, Memos, Trilium, Vikunja, AdGuard Home, Jellyfin, Navidrome, Audiobookshelf, Mealie, Grocy, Homebox, Kiwix, Kolibri, Actual, Firefly III, wger, Endurain, FreshRSS, changedetection.io, ArchiveBox, Ollama (small models), LibreChat | Consumer value modules (A-4) |
| **Omni (AI / SMB / OSINT)** | Pro set + LocalAI, AnythingLLM, SearXNG, Nextcloud, BookStack, Gitea, code-server, Grafana, OpenCTI CE, IntelOwl, MISP, SpiderFoot, Activepieces | GPU and RAM headroom |
| **L3 apps** | Open WebUI, n8n, AFFiNE, Outline, Tandoor, Invoice Ninja, Akaunting, monetr | **User-installed only** from upstream images; never preinstalled; flagged in the UI |

**Not yet measured:** whether the Pro set actually fits in a Pi 5 8 GB alongside k3s. Test **T-W12-2** (§12) runs it in OneMind CI on the W4 footprint harness.

---

## 4. License policy for the Market (Q250)

*Not legal advice. These rules read the license texts cited. Counsel confirms before the first box ships (`26-…`).*

| Class | Examples | List in Market | Mirror images | Preinstall on sold boxes | Modify | Charge for the app | Obligations |
|---|---|---|---|---|---|---|---|
| **L1 permissive** | MIT, Apache-2.0, BSD, MPL-2.0, EPL-2.0/BSD | Yes | Yes | Yes | Yes | Yes | Keep notices and NOTICE files |
| **L2 copyleft** | GPL-2.0/3.0, AGPL-3.0, EUPL-1.2, LGPL | Yes | Yes, with source offer | Yes, **unmodified and as separate programs**: an aggregate does not spread the GPL [C-W12-030] | Only with the source published; **AGPL changes must be offered to network users** [C-W12-031] | Support/hardware yes; the app itself is free | Corresponding-source offer for every shipped image (W6/W16 own the mechanism) |
| **L3 source-available** | SUL (n8n) [C-W12-016], BUSL (Outline, Akaunting) [C-W12-018, -019], ELv2 [C-W12-020], FSL [C-W12-021], Commons Clause [C-W12-017], branding clause [C-W12-015], EE server parts [C-W12-007] | Yes, labelled | **No** | **No** (selling a box with it preinstalled is exactly what several forbid) | No | No | User pulls upstream image; OneMind shows the restriction at install |
| **L4 proprietary / no license / archived** | umbrel-apps manifests [C-W12-002], Maltego [C-W12-076], Fasten (archived) [C-W12-028] | Link-out only, or not at all | No | No | No | No | — |

**Store repos:** the umbrel-apps manifests (no license) [C-W12-002] are L4: study only, never copied. beclab/apps (Apache-2.0) [C-W12-004] and CasaOS-AppStore (Apache-2.0) [C-W12-009] are L1: adapt with attribution and NOTICE. runtipi-appstore (GPL-3.0) [C-W12-010] is L2: anything adapted from it stays GPL, so keep it out of the Apache core repo.

**Model weights** are a fifth axis. Gemma, Llama and similar community licenses ride along with "model apps" [C-W12-006]. The linter needs a `model.license` field, and the W6/W16 license matrix needs rows per shipped model.

---

## 5. App format and importer (Q134, Q249, A-1, A-2, A-3, AI-3)

### 5.1 `onemind.app.yaml` (consistent with 01 L5, 05 §8, 06 backup hooks)

Each field is listed with where the pattern was proven:

```yaml
apiVersion: onemind.io/v1alpha1          # versioned; Market refuses unknown majors
kind: App
metadata:
  id: actual-budget
  version: 26.11.0                        # app version; chart version separate
  category: finance
  license: { spdx: MIT, source: "https://github.com/actualbudget/actual/blob/<sha>/LICENSE.txt", class: L1 }   # Olares has license [C-W12-005]; OneMind pins + classes it
  upstream: { repo: github.com/actualbudget/actual, commit: <sha> }
chart: { ref: oci://ghcr.io/onemind/charts/actual-budget, digest: sha256:... }
requirements:                              # Olares requiredMemory/supportArch [C-W12-005]
  memory: 256Mi
  disk: 1Gi
  arch: [amd64, arm64]
  nodeClass: platform                      # 05 §1.4: Market apps never land on leaf devices
  accelerator: none                        # or {class: gpu.any|gpu.cuda|npu.inference, memory: 8Gi} (05 §8)
entrances:                                 # Olares entrances; auth level
  - { name: web, port: 5006, auth: private }
storage:
  - { name: data, path: /data, backup: true }
backup:                                    # 06: app declares consistency; restic runs it
  pre: [ "actual-cli export --out /data/.backup" ]
  exclude: [ "/data/cache" ]               # Umbrel backupIgnore [C-W12-013]
permissions:                               # Umbrel permissions [C-W12-013]; enforced as grants (W19 DC-16)
  network: { egress: [ "beta-bridge.simplefin.org" ] }   # default-deny egress (01 §8 L3)
  devices: []
  folders: []
capabilities:                              # AI-3: auto-registered with the capability gateway (W9)
  - { id: finance.transactions.read, effect: read }
  - { id: finance.budget.update, effect: write, approval: required }
integrations:                              # per-source data-use policy (§9, §10; W9 designs the gate)
  - { id: simplefin, data_use: { display: true, store: true, ai_local: true, ai_external: ask, act: false } }
widgets: [ { id: net-worth, type: stat } ] # Umbrel widgets [C-W12-013]; W11 renders
alerts: [ { id: sync-failed, severity: warning } ]   # UX-4
nats: { publishes: [ "evt.ge.finance.synced" ] }     # grammar from context/01
quality: { tier: listed }                  # set by the Market, not the author
```

**Why Helm and not Compose at the core:** decided in 01 and 05 (G5, F-14). This file only adds the fields.

### 5.2 Field mapping (what the importer can and cannot fill)

| OneMind field | umbrel-app.yml [C-W12-013] | OlaresManifest [C-W12-005] | CasaOS `x-casaos` [C-W12-009] | HA add-on `config.yaml` [C-TD-home-assistant-os-026] |
|---|---|---|---|---|
| id, version, category | yes (category free string) | yes | yes | yes |
| license | **no** | yes (self-declared) | no | no |
| memory/disk/arch | no | yes | architectures only | arch only |
| entrances/ports | `port` | entrances | `port_map` | ports, ingress |
| permissions | `permissions` | `permission` | no | many flags (host network, devices, AppArmor) |
| backup hooks | `backupIgnore` | partial (Olares cooperative backup endpoint [C-TD-olares-027]) | no | backup mode per add-on [C-W5-036] |
| AI capabilities, data-use | no | no | no | no |
| accelerator capability | `GPU` permission [C-TD-umbrelos-027] | GPU limits | no | no |

**What this shows:** no importer can fill the AI capability, data-use, license class or backup-consistency fields. Every imported app therefore starts at **Community** tier with those fields empty or `unknown`, and the AI gateway treats undeclared apps as **no capabilities exposed** (fail closed, AI-5).

### 5.3 The importer

`onemind app import <compose.yaml | casaos-app-dir | oac-chart-dir> --out apps/<id>/`

1. **Parse** the source. Compose `x-*` fields are spec-legal metadata [C-W12-011].
2. **Normalise** into an internal app model (services, volumes, ports, env, devices).
3. **Render** to values for **one OneMind library chart** (`onemind-app`), not raw generated manifests. That gives one template to harden (securityContext, limits, NetworkPolicy, Retain storage class per 05 §5). kompose (Apache-2.0, active) [C-W12-012] is the reference for edge cases, and can be vendored if needed.
4. **Draft** `onemind.app.yaml`, with license fetched from the upstream repo at a pinned commit, never from the source manifest [C-W12-007].
5. **Lint** (§6). Anything that needs host network, privileged mode or devices becomes an explicit **grant request**, which a human reviews (W19 owns grants).

**Sources the importer may read:**

| Source | Legal basis | Use |
|---|---|---|
| Upstream project's own `compose.yaml` | Licensed with the project | **Primary path** |
| CasaOS-AppStore | Apache-2.0 [C-W12-009] | Bulk import allowed with attribution |
| Olares beclab/apps | Apache-2.0 [C-W12-004] | Charts are Helm already; translate the manifest, keep NOTICE |
| A user-supplied Umbrel community store URL | No license [C-W12-002] | **Open question for counsel:** a runtime convert-on-the-user's-box feature, never republished by OneMind (also listed in the umbrelOS teardown) |
| Runtipi store | GPL-3.0 [C-W12-010] | Only into a separate GPL repo, if at all |

---

## 6. Quality tiers (A-1, A-6, R-2)

Home Assistant makes quality **machine-checkable**: 54 named rules split into Bronze (20), Silver (10), Gold (21) and Platinum (3), enforced by `hassfest` in CI [C-W12-014]. OneMind copies that *method*, not the rules:

| Tier | Badge | How it is earned (checked by machine unless noted) | Shown to users | Comparable |
|---|---|---|---|---|
| **Community** | grey | Comes from a third-party store or an import; manifest parses | Warning: "not reviewed"; installs only with a confirm step | Umbrel community stores, HACS custom repos |
| **Listed** | blue | Linter passes: chart renders; limits set; no host namespaces or privileged mode without a declared grant; license read from upstream at a pinned SHA and classed; arch and RAM declared; backup section present; capabilities declared (even if empty); images pinned by digest | Normal listing | HA Bronze; Olares linter [C-TD-olares-028] |
| **Verified** | green | OneMind CI installs, upgrades from the previous version, uninstalls, and **backs up and restores** on reference x86 + Pi 5 (+ Jetson if accelerator); measured RAM recorded; SBOM + signature; upstream active in last 6 months; maintainer responds to security reports | "Tested on your hardware class" | HA Silver/Gold |
| **Certified ("Works with OneMind")** | gold | Verified + a partner agreement: security contact, CRA vulnerability handling, support terms (W19 / W6 own the programme) | Partner badge | HA Platinum + "Works with HA" |

**Separate badges, not tiers:** license class (L1–L4), "runs on this box" (capability detection, W10/N-3) and "AI access" (what capabilities the app exposes, W9).

**Dropping a tier is automatic.** An archived upstream (File Browser, Fasten, Maybe [C-W12-029, C-W12-028, C-W12-022]) or a failed restore test lowers the tier and alerts users who have the app installed.

---

## 7. Plugins and website distribution (cross-reference only)

- **Plugin types, extension points, the plugin manifest/SDK/CLI, sandboxing, signing, review and paid plugins:** W19, `29-PLATFORM-ECOSYSTEM-MARKETPLACE.md`, decision-critical DC-16. W12 sets only what Market *apps* need from that design: the grant model (devices, host network, folders) and the capability registration hook.
- **Website distribution (W-8):** the Market index is a Git repository. CI publishes a **signed static JSON index**, and the website renders app pages from the **same index**, so the site and the box can't disagree. Install from the web is a deep link or QR code that the user's box (or phone app, W11) opens; the website never talks to boxes directly. The signing and verified-publisher details are W19's.

---

## 8. Internal apps: scaffold specs and build order (A-4, D-003, Q267)

### 8.1 Build vs integrate (Q267)

| Module | Decision | Engine / Market apps | Reason |
|---|---|---|---|
| Home, Market, Files, Vault, Alerts, Nodes, Family & Users, AI & Agents, Settings, Studio | **Build** | Homarr studied (W11), OpenBao/Infisical (W6), ntfy [C-W12-107] | These *are* the OS (P-2, UX-1) |
| Projects & Tasks | **Build thin** over Markdown/SQLite; Vikunja optional | Vikunja AGPL [C-W12-114]; Plane is amd64-only and 4Gi [C-W12-113 + catalog] | Founder's workflow is Obsidian + Todoist (context/02); AI-native tasks are the point |
| Knowledge (Codex) | **Build** the vault adapter (prior Blueprint acceptance rules) | Obsidian stays an optional client, never redistributed (context/02) | Markdown is the portable format |
| Wellness | **Build thin aggregator**; integrate trackers | wger, Endurain, FitTrackee (AGPL) [C-W12-142, -143, -145] | Terms-limited data; §9 |
| Finance | **Integrate Actual** as engine; OneMind views + capabilities | Actual MIT [C-W12-147]; Firefly III alt. [C-W12-148] | Mature, MIT, bank sync already built [C-W12-062] |
| Family | **Build thin** (calendar, chores, kid profiles); integrate | Mealie [C-W12-138], Grocy [C-W12-139], Kiwix/Kolibri [C-W12-136, -137] | |
| Situational Awareness (TAK) | **Integrate** | W8 decides server; CloudTAK separate app | |
| Mesh & Networking | **Integrate** + views | Headscale [C-W12-124], Meshtastic (W8) | |
| IoT & Home | **Integrate HA** + OneMind views | HA Apache-2.0 [C-W12-101] | |
| Robotics & Drones | **Build** (the moat) | W7/W19 adapters, ROS 2 images | M-7, F-3 |
| Infrastructure | **Build views**; integrate Grafana unmodified | Grafana AGPL [C-W12-168] | Backstage stays a dev portal (05 §10) |
| OSINT & Intel | **Build ingest on NATS**; integrate tools | SpiderFoot, changedetection, FreshRSS, ArchiveBox, OpenCTI CE | §11 |
| Education | **Integrate** | Kolibri, Kiwix; Circle.so stays website (W13) | |

**Unified vs separate apps (A-4):** one **app shell** with modules, each also a standalone Market app (D-003, already decided). The evidence supports it: every "integrate" row above is a separate upstream program that must stay a separate program to keep L2 obligations simple [C-W12-030].

### 8.2 Scaffold spec per module

Every module gets the D-003 checklist (`apps/<module>/onemind.app.yaml`, README, capabilities with effects, NATS subjects, export format). NATS subjects follow the **locked grammar** in context/01 (`tel. det. evt. cmd. intel. ent. svc. agents.`, pillar domains `so hp le ge sys`). No new patterns are invented. **Approval** means the capability gateway asks a human (AI-5).

| Module (`id`) | Key capabilities (effect · approval) | NATS (examples) | Data export | Min node | Wave |
|---|---|---|---|---|---|
| Home (`home`) | `home.layout.read` (read) · `home.widget.add` (write) | `evt.sys.home.changed` | layout JSON | platform 4 GB | 1 |
| Market (`market`) | `market.apps.list` (read) · `market.app.install` (write · **approval**) · `market.app.remove` (destructive · **approval**) | `evt.sys.market.installed`, `svc.market.install` | installed-app list (`OneMindApp` YAML) | platform | 1 |
| Files (`files`) | `files.read` (read, per folder grant) · `files.write` (write) · `files.delete` (destructive · **approval**) | `evt.sys.files.changed` | plain files | platform | 1 |
| Vault (`vault`) | `vault.secret.use` (read, never returns value to AI) · `vault.secret.rotate` (write · **approval**) | `evt.sys.vault.rotated` | encrypted bundle | platform | 1 |
| Alerts (`alerts`) | `alerts.list` (read) · `alerts.ack` (write) · `alerts.rule.create` (write) | `evt.sys.alert.raised`, `svc.alerts.ack` | rules YAML | platform | 1 |
| Nodes (`nodes`) | `nodes.list` (read) · `nodes.join` (write · **approval**) · `nodes.reboot` (destructive · **approval**) | `tel.{node}.sys.health`, `evt.sys.node.joined` | node registry JSON | platform | 1 |
| Family & Users (`users`) | `users.list` (read) · `users.role.set` (write · **owner approval**) | `evt.sys.user.changed` | users + roles (no secrets) | platform | 1 |
| AI & Agents (`agents`) | `agents.grant.list` (read) · `agents.grant.set` (write · **owner approval**) | `agents.*` fabric (context/01) | grants + audit log | platform | 1 |
| Settings (`settings`) | `settings.update.schedule` (write · **approval**) · `settings.backup.run` (write) | `evt.sys.update.*`, `evt.sys.backup.*` | settings YAML | platform | 1 |
| Studio (`studio`) | `studio.app.lint` (read) · `studio.app.install-dev` (write · **approval**) | `evt.sys.studio.built` | app folders | platform 8 GB | 2 |
| Projects & Tasks (`tasks`) | `tasks.read` · `tasks.create` (write) · `tasks.delete` (destructive · **approval**) | `evt.so.task.created` (context/01 example) | Markdown + JSON; Todoist import | platform | 2 |
| Knowledge (`codex`) | `codex.search` (read) · `codex.note.write` (write, hash-checked, per context/02) | `evt.so.note.updated` | the Markdown vault itself | platform | 2 |
| IoT & Home (`iot`) | `iot.entity.read` · `iot.entity.set` (write; **approval** for locks, heaters, valves) | `tel.{node}.iot.*`, `cmd.le.{entity}.{action}` | HA backup + OneMind views | platform | 3 |
| Situational Awareness (`tak`) | `tak.positions.read` · `tak.cot.send` (write · **approval**) | `tak.cot.inject`, `tak.cot.>` | CoT archive | platform 8 GB (TAK Server) | 3 |
| Robotics & Drones (`robotics`) | `robot.list` · `robot.telemetry.read` · `robot.mission.start` (**approval, physical**) | `tel.drone.{id}.*`, `cmd.drone.{id}.{action}` | registry + mission logs | platform (+ Jetson) | 3 (registry MVP) / 5 (missions, sim) |
| Finance (`finance`) | `finance.transactions.read` · `finance.budget.update` (write · **approval**) · **no money movement** | `evt.ge.finance.synced` | Actual export + CSV/OFX | platform | 4 |
| Family (`family`) | `family.calendar.read` · `family.chore.assign` (write) | `evt.hp.family.*` | iCal + JSON | platform | 4 |
| Wellness (`wellness`) | `wellness.summary.read` (read; per-source data-use) · `wellness.habit.log` (write) | `evt.hp.wellness.logged` | FHIR-lite JSON / CSV | platform | 4 |
| Mesh & Networking (`mesh`) | `mesh.peers.read` · `mesh.peer.revoke` (destructive · **approval**) | `tel.{node}.net.*` | peer list | platform | 5 |
| Infrastructure (`infra`) | `infra.workloads.read` · `infra.workload.restart` (write · **approval**) | `evt.sys.infra.*` | Argo app list | platform 8 GB | 5 |
| OSINT & Intel (`intel`) | `intel.feed.read` (read; **tainted**, §11) · `intel.watch.create` (write) | `intel.{domain}.{source}.{type}`, `evt.world.*` (context/01) | ClickHouse/Parquet export | platform 8 GB | 5 |
| Education (`edu`) | `edu.course.list` (read) | `evt.hp.edu.progress` | Kolibri export | platform | 5 |

Pillar-domain mapping (`so`/`hp`/`le`/`ge`) above is OneMind's assumption from context/01's examples. The founder can re-map it; the grammar stays.

### 8.3 Build order (change to APPS.md §C, flagged)

| Wave | Modules | Gate to move on | Change vs APPS.md |
|---|---|---|---|
| 1 | Home, Market, Alerts, Nodes, Family & Users, AI & Agents, Settings, **Files, Vault** | One L1 app installs, is backed up, restored and exposed to the agent with an approval prompt | Files and Vault named explicitly (Market apps need folder grants and secrets) |
| 2 | Knowledge, Projects & Tasks, **Studio** | Founder uses them daily for 2 weeks | Studio earlier: needed to build every later module |
| 3 | IoT & Home, Situational Awareness, **Robotics registry MVP** | Greenhouse and TAK profiles pass W8 tests | **Robotics moves from wave 5 to 3 (registry/telemetry only)**: it shares the Nodes registry, and M-7 makes it the moat |
| 4 | Finance, Family, Wellness | Finance first (MIT engine, fewer legal unknowns); Wellness last (terms and health law, §9) | Order inside the wave set by legal risk |
| 5 | Mesh, Infrastructure, OSINT, Education, Robotics missions/sim | Hardware tiers ship | — |

The founder can reorder (APPS.md says so); this is marked `blocked: founder-decision` in the qbank.

---

## 9. Deep dive: Wellness (UX-3, AI-1, AI-6, M-2, Q256, Q307)

### 9.1 What each data source allows (primary terms)

| Source | How OneMind gets data | Store on box? | Local AI may read? | External AI? | Evidence |
|---|---|---|---|---|---|
| **Apple HealthKit** | Only through OneMind's iOS app on the phone (HealthKit is a device framework) | Yes | Yes, with disclosure | **Only with explicit permission**, naming third-party AI (5.1.2(i)) | [C-W12-040, C-W12-041]; no ads or data mining; no health data in iCloud |
| **Android Health Connect** | Through OneMind's Android app | Yes | Yes | Not banned; transfers to ad platforms/brokers and for credit/insurance banned | [C-W12-042]; AI agents must request only needed types |
| **Garmin** | User's **own Personal API key** (pull) | Yes | **Unknown** | **Unknown** | Personal tier [C-W12-045]; AI clause **UNVERIFIED** (agreement behind sign-in) [C-W12-046] |
| **Oura** | Oura API with user consent | Only as long as strictly necessary; delete within 72 h of a request | **No** via API data | **Only via Oura's MCP Server**, no caching of MCP data | [C-W12-043] |
| **Strava** | Strava API | 7-day cache; no persistent index | **No** | **Only via Strava MCP** (subscribers, personal use) | [C-W12-044] (W9 owns the full analysis) |
| **User's own export files** (FIT, GPX, CSV from the device or account) | Upload into Files | Yes | Yes | User's choice | Analysis, not a sourced rule: API terms bind API clients; files the user exports themselves aren't obtained through the API. **Counsel to confirm.** |
| Whoop, Withings, Dexcom, Fitbit/Google Health | — | — | — | — | **Not researched (partial)** |

**Design rule (W9 builds the gate):** every integration declares `data_use` in the manifest (§5.1). The defaults come from the table. Oura and Strava ship as **`display: true, ai_local: false, ai_external: false`**. Their AI path is "connect your agent to the vendor's own MCP server", which W9's capability layer can broker without the data touching OneMind storage.

### 9.2 Which laws apply

| Law | Applies to OneMind? | Why | Evidence |
|---|---|---|---|
| **HIPAA** | **Normally no** | Covered entities are health plans, clearinghouses and providers billing electronically. A self-hosted wellness app is none of these, unless OneMind signs on as a provider's business associate. | [C-W12-047] |
| **FTC Health Breach Notification Rule** | **Possibly yes** | A PHR is a record that can draw from multiple sources, managed by the individual. A non-HIPAA entity that *offers or maintains* one is a "vendor". A multi-source wellness module looks like a PHR. A breach includes an unauthorized *disclosure* [C-W12-048]. **Mitigation:** OneMind never holds plaintext health data. Anything that leaves the box (backup, relay, support bundle) is encrypted with keys OneMind doesn't hold, because the rule only covers "unsecured" information [C-W12-048]. | [C-W12-048] |
| **GDPR Art. 9** | For EU users, yes when OneMind processes | Health data needs an Art. 9(2) condition, usually explicit consent. A person running their own box is under the household exemption, but the Regulation still applies to anyone *providing the means* as controller or processor (Recital 18). | [C-W12-049] |
| **Washington MHMDA** | If OneMind collects data from WA consumers | Covers health status inferred by algorithms or ML, so AI summaries of non-health data count too | [C-W12-050] |
| COPPA, BIPA | Children's accounts; biometrics | Owned by W9/W13 | — |

**Consequence:** the local-first design is also the compliance design. Keep wellness data on the box; give external AI access only per source and per user; encrypt everything that leaves; never use it for ads or scoring (Apple and Google ban that anyway [C-W12-041, C-W12-042]).

### 9.3 Self-hosted wellness apps

wger (workouts, nutrition; AGPL) [C-W12-142], Endurain (activities; AGPL) [C-W12-143] and FitTrackee (AGPL) [C-W12-145] are L2 and can ship. Habitica is L3 because of its non-commercial assets [C-W12-026]. The leading self-hosted health-record app, Fasten On-Prem, is **archived** [C-W12-028]. That leaves a gap OneMind's wellness module fills: a small aggregator plus daily brief, not a medical record. **Don't build diagnosis or treatment features.** Google's policy notes these may make the app a regulated medical device [C-W12-042].

---

## 10. Deep dive: Finance (Q308, AI-1, AI-5, M-2)

### 10.1 Getting account data

| Route | Coverage | Terms that matter | Fit | Evidence |
|---|---|---|---|---|
| **SimpleFIN Bridge** | North America | Read-only by protocol; user gets a token, the app claims an Access URL; $1.50/mo or $15/yr; 25 institutions + 25 apps | **Default (NA)**: user-owned, read-only, cheap, works fully self-hosted | [C-W12-060, C-W12-061] |
| **Enable Banking** | Europe | Supported by Actual [C-W12-062]; terms not researched | **Candidate (EU)**: partial | [C-W12-062] |
| **GoCardless Bank Account Data** | Europe | Closed to new accounts since July 2025 | **No** | [C-W12-063] (SECONDARY) |
| **Plaid** | US/EU | Developer Policy: no selling, no storing credentials beyond need, no AI clause [C-W12-064]. **Plaid's own privacy policy lets Plaid train AI on end-user data** [C-W12-065]. Built for businesses, not individuals | **Not a default.** It sends the user's bank data to a third party that trains on it (M-2) | [C-W12-064, C-W12-065] |
| **CFPB §1033 open banking (US)** | Large US providers first | Final rule in the eCFR with dates from 2026-04-01 to 2030 [C-W12-066]; under reconsideration since 2025-08 with no new rule published [C-W12-067]; reportedly enjoined [C-W12-068] | **Don't depend on it.** Revisit at re-check | [C-W12-066…068] |
| **File import (CSV/OFX/QFX)** | Everywhere | No third party | **Always available** fallback | Actual and Firefly import (APPS.md MVP) |

### 10.2 Engine and safety

- **Engine: Actual Budget (MIT)** [C-W12-147]. It is L1 (it can be embedded, modified and shipped) and already supports SimpleFIN, Enable Banking and others [C-W12-062]. Firefly III (AGPL) [C-W12-148] stays a Market alternative. Maybe Finance is archived and its fork Sure is young [C-W12-022]: watch only.
- **Token storage:** Actual keeps bank-sync tokens on its server, **not end-to-end encrypted** [C-W12-062]. On OneMind, the Actual server's data sits on the LUKS2 data partition (01 §4.3) and in restic's encrypted backup (01 §4.6). The SimpleFIN Access URL goes into Vault, not plain env vars.
- **What AI may do:** **read** transactions and budgets (local AI by default; external AI per user consent). **Write** categories and budgets only with approval. **Never move money**: SimpleFIN is read-only by design [C-W12-061], and OneMind ships no payment capability in the finance module (AI-5).
- **Liability note:** Plaid's policy shows the duties a credential holder carries [C-W12-064]. OneMind avoids holding bank credentials at all: SimpleFIN tokens are scoped, read-only and revocable by the user [C-W12-061].

---

## 11. Deep dive: OSINT & Intel (Q306, AI-1, M-2)

### 11.1 Scope

Keep the module to **world events, infrastructure and the user's own assets**: aircraft, ships, satellites, hazards, conflict, fire, news, website changes and certificate/domain monitoring. That is what the founder's cluster already runs: feed workers into NATS, a TAK projector and the ClickHouse "time machine" (context/01). **People-search OSINT is excluded from the default product.** It is where most of the legal and ethical risk sits (GDPR Art. 14 notice duties [C-W12-073]; the WA MHMDA's inference rule if health is inferred [C-W12-050]).

### 11.2 Legal and ethical limits

| Topic | What the primary text says | What OneMind does |
|---|---|---|
| **CFAA (US)** | It is a crime to access "without authorization" or "exceed authorized access" [C-W12-070]. The Supreme Court reads this as gates up or down [C-W12-071]. The Ninth Circuit held public web pages have no gates, so scraping them is not "without authorization" [C-W12-072]. | Fetch only public pages and APIs; never log in with someone else's credentials; never bypass a block. Terms-of-service and contract claims are **not** settled by hiQ (later history not opened here: UNVERIFIED). |
| **Data-source licences** | OpenSky data and API: non-profit research and education only; commercial use needs a written licence [C-W12-075]. | Each feed is a Market app declaring its data licence. Commercial boxes don't enable non-commercial feeds by default. **Check the founder's live aircraft feed source** (`blocked: live-cluster`, test in `22-…`). |
| **GDPR** | Art. 14 notice duty when data isn't obtained from the person, with a disproportionate-effort exemption mainly for research/archiving [C-W12-073]; household exemption, but providers of the means stay in scope [C-W12-049]. | Default feeds carry no personal data; person-centric modules are opt-in, documented, and not shipped by OneMind. |
| **EU DSA Art. 40** | Researcher data access is for **vetted researchers** at research organisations, from very large platforms [C-W12-074]. | Not a route for a consumer product. |
| **Prompt injection** | OSINT feeds are attacker-controlled text (Q89, W6/W9). | `intel.*` data is tagged **tainted**; an agent that has read tainted data can't trigger `cmd.*` without human approval (W9 enforces). |

### 11.3 Tools: build vs integrate

| Tool | License | Use |
|---|---|---|
| SpiderFoot | MIT [C-W12-157]; last push 2026-04 [C-W12-077] | Market app (L1), domain/infra recon; maintenance risk noted |
| OpenCTI | Apache-2.0 CE, EE files separate [C-W12-023] | Omni-tier threat-intel platform; ship CE only |
| IntelOwl, MISP | AGPL-3.0 [C-W12-159, C-W12-160] | Market apps (L2), unmodified |
| changedetection.io, ArchiveBox, FreshRSS | Apache-2.0 / MIT / AGPL [C-W12-161…163] | Pro-tier monitoring and archiving |
| Maltego | Proprietary subscription; non-transferable, no copying; free tier for evaluation only [C-W12-076] | **Not bundled.** Users may run their own licensed client |
| **OneMind ingest** | Apache-2.0 (own) | **Build:** feed adapters → `intel.{domain}.{source}.{type}` / `evt.world.*` → ClickHouse (or a lighter store on 8 GB boxes, measured by test T-W12-3) |

---

## 12. Tests to schedule (for `20-…` and `22-…`)

| ID | Test | Pass | Fail → |
|---|---|---|---|
| T-W12-1 | Import the top 50 CasaOS apps with `onemind app import` (in a disposable VM; kompose only as reference) | ≥ 80 % reach **Listed** with only grant requests left for review | The importer becomes "assistive", and manual packaging budget rises |
| T-W12-2 | Install the Pro launch set on Pi 5 8 GB + NVMe with k3s (W4 harness) | All Running; ≥ 1 GiB free; restore drill passes | Trim the Pro set or move apps to Omni |
| T-W12-3 | OSINT ingest of founder's feeds into ClickHouse vs a light store on 8 GB | < 2 GiB RSS at the founder's feed rate | Omni-only module |
| T-W12-4 | License linter vs this workstream's hand results on the 70 seed repos | 100 % match on class (L1–L4) | Fix the linter before Listed opens to the public |
| T-W12-5 (live-cluster) | Founder lists the data sources and their terms for every live feed worker | Each feed has a recorded licence | Disable or relicense non-commercial feeds before sale |

---

## 13. Tensions with the Tier A foundation and other requirements (flagged, not resolved)

1. **Market apps need a platform node (≥ 4 GB + SSD; 01 §4.5, 05 §1.4).** APPS.md says every module is "also a standalone Market app". On sub-4 GB leaf devices, no module runs; leaves get adapters (W19). That is consistent with 01, but the website and in-product copy must not promise "every app on every device" (F-14 is met by the leaf/adapter model, not by Market apps).
2. **UX-3's own example conflicts with vendor terms.** REQUIREMENTS UX-3 says Strava data "is available to AI". Strava's policy bans that outside its MCP [C-W12-044], and Oura's is similar [C-W12-043]. The requirement needs re-wording to "available to AI where the provider allows". Listed for `26-…`. W9 owns the final wording.
3. **Preinstalled copyleft apps carry duties on sold boxes.** These are source offers for GPL/AGPL images [C-W12-030, C-W12-031], plus possibly CRA duties for third-party components OneMind places on the market (W6, Q212). This doesn't change 01, but it is a cost for the hardware business (W16) and belongs in the license matrix.
4. **APPS.md build order changed** (robotics registry to wave 3; Studio to wave 2): flagged for founder decision.

---

## 14. Recommendations → requirement IDs

| ID | Recommendation | Requirement IDs | Claims |
|---|---|---|---|
| W12-R1 | Seed ~55 apps in 12 categories (§3.3); launch sets per edition/profile (§3.4) | A-1, A-3, P-5, P-8, M-3 | C-W12-001, -003, -008, -101…170 |
| W12-R2 | Four license classes; only L1/L2 preinstalled on sold boxes; L3 user-installed with a warning; L4 excluded | A-1, H-1, D-001, R-3 | C-W12-015…021, -030, -031 |
| W12-R3 | Never copy umbrel-apps; adapt Olares and CasaOS stores with attribution; Runtipi only into a GPL repo | A-3, RS-2, D-001 | C-W12-002, -004, -009, -010 |
| W12-R4 | `onemind.app.yaml` fields as §5.1, including license class, data-use, capabilities, backup hooks, accelerator capability | A-2, AI-1, AI-3, N-3, F-5 | C-W12-005, -011, -013 |
| W12-R5 | Importer via one `onemind-app` library chart; license read upstream at a pinned SHA | A-1, A-3, N-9, M-6 | C-W12-007, -011, -012 |
| W12-R6 | Quality tiers Community → Listed → Verified → Certified, machine-checked like HA's scale; automatic downgrade on archival | A-1, A-6, R-2, F-5 | C-W12-014, -022, -028, -029 |
| W12-R7 | Track model-weight licenses separately in the manifest and license matrix | AI-8, D-001 | C-W12-006 |
| W12-R8 | Build vs integrate per module (§8.1); scaffold spec per module (§8.2) | A-4, D-003, P-3 | §8 claims |
| W12-R9 | Build order with gates (§8.3) | A-4, M-6, M-7 | — |
| W12-R10 | Wellness: phone-side HealthKit/Health Connect, Garmin personal key, Oura/Strava display-only with MCP-brokered AI; encrypt anything leaving the box | UX-3, AI-1, AI-5, M-2, U-1 | C-W12-040…050 |
| W12-R11 | Finance: Actual as engine; SimpleFIN default (NA); no Plaid by default; read-only AI, no money movement | UX-3, AI-1, AI-5, M-2 | C-W12-060…068, -147 |
| W12-R12 | OSINT: world-events scope; tainted data; data-licence per feed; SpiderFoot/OpenCTI CE/changedetection integrated; Maltego not bundled | AI-1, AI-5, M-2, AI-9 | C-W12-070…077, -157…163 |
| W12-R13 | Website renders the same signed index the boxes read (W-8; signing in W19) | W-8, A-5 | — |
| W12-R14 | Add every seed app and model license to `license-matrix.csv` (§15) | D-001, RS-1 | C-W12-101…170 |

---

## 15. Seed apps for the license-matrix agent's scope

The license-matrix agent should add these rows, with pinned LICENSE paths from `evidence/sources/W12/seed-repo-licenses.csv`: Home Assistant core, ESPHome, Zigbee2MQTT, Mosquitto, Node-RED, Frigate, ntfy, Immich, Syncthing, Nextcloud server, Paperless-ngx, Plane, Vikunja, AFFiNE (EE server), Trilium, Outline, BookStack, Memos, Vaultwarden, AdGuard Home, Pi-hole, Tailscale, Headscale, Uptime Kuma, Ollama, Open WebUI, LocalAI, AnythingLLM, SearXNG, n8n, LibreChat, Activepieces, Jellyfin, Navidrome, Audiobookshelf, kiwix-tools, Kolibri, Mealie, Grocy, Tandoor, Homebox, wger, Endurain, FitTrackee, Habitica, Actual Budget, Firefly III, Ghostfolio, Wealthfolio, Sure, Invoice Ninja, Akaunting, monetr, SpiderFoot, OpenCTI, IntelOwl, MISP, changedetection.io, ArchiveBox, FreshRSS, OpenTAKServer, Gitea, code-server, Grafana, Homarr, kompose (importer reference); store repos beclab/apps, CasaOS-AppStore, runtipi-appstore, umbrel-apps (L4); plus a model-weights section (Gemma Terms, Llama community licenses) [C-W12-006].

---

## 16. Open items and limits

- **No install-count data:** neither catalog repo publishes installs. Stars are a weak proxy.
- **RAM figures are Olares declarations**, not measurements (T-W12-2).
- **Unverified:** Garmin's AI terms [C-W12-046]; the 1033 injunction (court order not opened) [C-W12-068]; hiQ's later contract-law history; Enable Banking, Whoop, Withings, Dexcom and Fitbit terms.
- **Not done here (Tier B teardowns own it):** CasaOS, Runtipi, Cosmos and YunoHost store governance; their app formats are only sampled.
- **Counsel questions** (for `26-…`): a runtime Umbrel-store converter; preinstalling AGPL apps on sold boxes; Open WebUI's branding clause on boxes above 50 users; FTC HBNR "vendor" status for a self-hosted wellness module.
- No refuters were run (Tier B). The license classifications are mechanical reads of pinned files and the most reliable part of this file. The legal conclusions are the least reliable part.

## Sources

The full list is in [`evidence/sources/W12.md`](evidence/sources/W12.md). Every claim ID resolves in [`evidence/claims/W12.csv`](evidence/claims/W12.csv).
