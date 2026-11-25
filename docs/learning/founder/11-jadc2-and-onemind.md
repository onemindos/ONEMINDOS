<!-- SPDX-License-Identifier: Apache-2.0 -->
# Founder note 11: JADC2 and OneMind, what to adopt and where we differ

**For:** Zeus · **Date:** 2026-11-25
**Status:** founder-requested learning entry. It adds no decision and changes no locked rule. Zeus named JADC2 as the concept behind much of OneMind's structure; this note maps one onto the other. Facts about JADC2 come only from the two public sources below; facts about OneMind point to repo files. Ideas to adopt are proposals, not board items.
**Feeds:** the One Mind fabric ([`research-output/fabric/`](../../../research-output/fabric/)), AI risk classes (fabric rule A4), C2 paths in founder note [10](10-c2-and-physical-ai-paths.md), the public-safety tier ([`research-output/11-hardware-line.md`](../../../research-output/11-hardware-line.md)), AI-5 (human approval).

**Sources (public US government documents):**
- Department of Defense, *Summary of the Joint All-Domain Command and Control (JADC2) Strategy*, March 2022. Published on media.defense.gov (exact URL not checked by script: the site refuses automated requests; UNVERIFIED).
- Congressional Research Service, *Joint All-Domain Command and Control (JADC2)*, In Focus IF11493, updated 2022-01-21, crsreports.congress.gov (same caveat).

---

## 1. Short answer

JADC2's structure is a strong model for OneMind, and the plans already follow much of it: one data fabric, one bus, resilience when cut off, and a sense → make sense → act loop. The best one-line position is **"JADC2-style command and control for everyone who is not the military": sites, responders, farms and families.**

One deliberate difference: as CRS describes it, JADC2 aims to link sensors to weapons, with AI identifying targets and recommending the weapon. **OneMind keeps a person deciding and does no targeting.** That is the safety story and the market.

---

## 2. What JADC2 is, in plain words

- **The problem:** each military service built its own tactical network, and the networks could not talk to each other. Analysing the situation and issuing orders took days.
- **The idea:** connect the sensors of every service into one network, so decisions take hours, minutes or seconds. DoD's own analogy is Uber, which matches riders and drivers from their positions.
- **The loop:** **Sense** (collect and integrate data from every domain) → **Make Sense** (analyse it, with AI and machine learning, into a shared understanding) → **Act** (decide and send the decision out).
- **The data fabric:** DoD's working definition is a federated data environment for sharing information through interfaces and services, so partners can discover, understand and exchange data across domains, echelons and security levels.
- **Five lines of effort (LOEs):** (1) data enterprise, (2) human enterprise, (3) technical enterprise, (4) nuclear command and control, (5) sharing with mission partners.
- **Six principles:** sharing designed at enterprise scale; layered security; common data and interface standards; resilience in degraded and contested conditions; unity of effort; speed of delivery.
- **Mission command:** when links break, subordinate commanders act on the senior commander's known intent.

---

## 3. How OneMind maps to it

| JADC2 | OneMind today | Gap or next step (proposal) |
|---|---|---|
| **Sense** | NATS bus, node heartbeats, ESPHome, Zigbee, MQTT, cameras; TAK feeds planned | Adapters for TAK/CoT, Meshtastic, MAVLink (fabric FB-3) |
| **Make Sense** | Local AI (Ollama, Hermes) reading through the gateway's MCP read tools; Grafana | A **shared live map** (common operating picture) in the dashboard |
| **Act** | Actions → owner approval → executor ([`core/`](../../../core/)); alerts through ntfy and the dashboard | Send approved decisions out to TAK clients and phones |
| **Data fabric** | The One Mind fabric: one bus (NATS), addresses `site/node/device/capability` ([`00-FABRIC-SUMMARY.md`](../../../research-output/fabric/00-FABRIC-SUMMARY.md)) | Already designed |
| **LOE 1 Data:** minimum metadata tags, standard interfaces, "visible, accessible, understandable, linked, trustworthy, interoperable, secure" | OpenAPI contract, generated SDK, schema-tagged messages, hash-chained audit | A standard **observation envelope**: source, time, confidence, sensitivity label |
| **LOE 2 Human:** training, AI tools, "pre-determined, pre-approved, event-driven bundled authorities" | Approval queue, roles, the learning track | **Playbooks**, within the boundary in §5 |
| **LOE 3 Technical:** resilient, diverse transport, no single point of failure | Mesh, Headscale/DERP, NATS leaf, A/B updates, one cluster per site | On the board (CORE-NET, CORE-FABRIC) |
| **LOE 4 Nuclear C2** | n/a | n/a |
| **LOE 5 Mission partners** | Federation between organisations is planned for later (M6: NATS account imports and exports, [`04-CONNECTIVITY-AND-TOPOLOGY.md`](../../../research-output/fabric/04-CONNECTIVITY-AND-TOPOLOGY.md)) | **Partner sharing scopes**: one OneMind shares chosen data with another, each owner in control |
| **Resilient when degraded** | Offline-first: 1,200 of 1,200 messages delivered after 30 minutes cut off; no offline time limit (fabric FB-7) | **"Train as we fight"**: automated tests that cut the uplink, kill the hub, drop the radio |
| **Mission command** | Site boxes keep running when cut off; ESPHome keeps its own control loop | Local playbooks that run within the owner's stated intent |
| **Secure, layered** | Guard, roles, sandbox, signed updates, Secure Boot path, audit ([`research-output/07-security-compliance.md`](../../../research-output/07-security-compliance.md)) | Planned |

---

## 4. Five ideas worth adopting (proposals)

1. **Make the Sense → Make Sense → Act loop the product's story and screen layout:** three panes, what is happening, what it means, what we are doing. Plain for customers, and it matches public-safety buyers' existing mental model.
2. **A common operating picture:** one live map combining TAK positions, nodes, sensors, cameras and alerts. It is the C1 go-box's main screen (note 10).
3. **A standard observation envelope on the bus:** who sensed it, when, how sure, how sensitive. This is JADC2's minimum metadata tagging, and it lets AI and partners trust and filter data.
4. **Partner sharing (LOE 5):** a county's OneMind and a volunteer team's OneMind share chosen data, each owner controlling exactly what. That is the path to the public-safety tier.
5. **Degraded-mode testing as a habit:** cut links, kill the hub, drop the radio in the lab, and prove the site keeps working.

---

## 5. Where OneMind must differ

- **No sensor-to-weapon, no AI targeting.** CRS describes JADC2's AI identifying targets and recommending weapons, and notes analysts asking how much human involvement remains. OneMind stays out of that on principle, and because export law (ITAR) would follow.
- **Pre-approved authorities fit only partly.** Fabric rule A4 ([`07-AI-OVER-THE-FABRIC.md`](../../../research-output/fabric/07-AI-OVER-THE-FABRIC.md)) already draws the line:
  - `write` → owner **or a standing approval**: JADC2-style playbooks are allowed here (for example "always send an alert when the river sensor passes 3 m").
  - **`actuate` → owner + step-up, never a policy**: opening valves, unlocking doors and moving machines always need a person at that moment.
  This matches the locked rule that AI never actuates without human approval. Whether playbooks may ever reach `actuate` is Zeus's decision; this note recommends keeping A4 as it is.
- **Speed vs approval:** JADC2 optimises for seconds. OneMind optimises for fast understanding (AI) and a fast human yes or no (one tap on the phone), not for removing the person.

---

## 6. Lessons from JADC2's critics (CRS)

| What CRS reports | Lesson for OneMind |
|---|---|
| Questions about technical maturity and affordability; Congress cut the FY2021 ABMS request for unjustified growth | Start with one site and one go-box, not "all domains" |
| Who holds decision authority across domains? | Keep the authority model explicit: owner roles, per-site owners, approvals routed to the target site's owner (fabric FB-10) |
| The Navy's stated priority was removing proprietary network standards | Open standards everywhere: OpenAPI, MCP, MQTT/Sparkplug, CoT, Apache-2.0 |

---

## Check yourself
1. Name the three steps of the JADC2 loop and the OneMind part that does each.
2. What is a data fabric, and what is OneMind's called?
3. Which JADC2 line of effort points to the public-safety tier, and what would OneMind build for it?
4. Under fabric rule A4, may a standing approval open a valve? Why or why not?
5. Give one lesson from JADC2's critics and how OneMind applies it.
