<!-- SPDX-License-Identifier: Apache-2.0 -->
# Founder note 08: real paths for C2 and physical AI now that OneMind is a full OS

**For:** Zeus · **Date:** 2026-11-24
**Status:** founder-requested learning entry. It adds no decision and starts no work. Robotics and drone paths stay **parked** under the founder rule of 2026-11-14 (no robotics work until OneMind has a robot). "When" columns and the "what first" list are opinion; the facts point to the research files that hold the evidence.
**Feeds:** profiles P-8 (Pi TAK node, greenhouse controller), N-6 and F-13 (offline and mesh), F-11 to F-14 (IoT and IIoT), AI-5 (human approval), the hardware line ([`research-output/11-hardware-line.md`](../../../research-output/11-hardware-line.md)), the roadmap ([`research-output/21-ROADMAP-5-10-YEARS.md`](../../../research-output/21-ROADMAP-5-10-YEARS.md)).

---

## Terms

- **C2 (command and control):** coordinating people, sensors and vehicles during an operation: who is where, what is happening, who does what next. Civilian forms: incident command, search and rescue, site security, field crews.
- **Physical AI:** AI that senses or affects the real world: cameras, sensors, valves, drones, robots.
- **TAK (Team Awareness Kit):** a shared live map for teams. ATAK (Android), iTAK (iPhone) and WinTAK are the clients; TAK Server or OpenTAKServer is the hub.
- **NATS leaf node:** a small message server on a site box that keeps working, and stores messages, when the link to the main hub is down.
- **Companion computer:** the Linux computer on a drone or robot that does the thinking, next to the flight or motor controller that does the flying or driving.

---

## 1. Why a full OS matters here

An app on someone else's computer cannot do these jobs. OneMind can, because it owns the box:

| OneMind piece | Why C2 and physical AI need it | Evidence |
|---|---|---|
| Works offline: NATS leaf store-and-forward | A site that loses internet loses nothing; the lab delivered 600 of 600 messages after an outage | [`09-iot-mesh-offgrid-tak.md`](../../../research-output/09-iot-mesh-offgrid-tak.md) P0-5 |
| Mesh networking: batman-adv, WireGuard/Headscale, Meshtastic and LoRaWAN gateways | Boxes and radios still talk with no cell or internet | doc 09 P0-6 |
| Hardware access as a permission | Radios, USB sensors and cameras need host access, granted per app | doc 09 P0-7 |
| A/B updates with health-gated rollback | A box in a field or on a vehicle cannot be bricked by an update | lesson [07](../07-image-ab-updates-health-gate.md) |
| Gateway approvals with short expiry | AI proposes, a person approves, and a queued "open valve" never replays hours later | [`core/`](../../../core/), [`context/02-prior-planning.md`](../../../context/02-prior-planning.md) §5 |
| Hash-chained audit log | After an incident you can prove who decided what and when | [`audit.py`](../../../core/onemind_core/audit.py) |
| Real-time kernel profile and the Jetson flavor | Control loops and robot "body brains" | [`08-robotics-drones-physical-ai.md`](../../../research-output/08-robotics-drones-physical-ai.md) FF-3, FF-5 |

---

## 2. C2 paths

| # | Path | Who buys it | What runs on OneMind | Status on 2026-11-24 | When (opinion) |
|---|---|---|---|---|---|
| **C1** | **Off-grid go-box for emergencies:** a case with a box, a radio and a battery that a team carries to an incident | Volunteer emergency teams (CERT), search and rescue, county emergency managers, wildfire crews | TAK Server (OpenTAKServer on small boards) for map sharing with ATAK/iTAK phones · [`offline-maps`](../../../apps/offline-maps/) · [`kiwix`](../../../apps/kiwix/) · Meshtastic radio gateway · [`ntfy`](../../../apps/ntfy/) alerts · [`mosquitto`](../../../apps/mosquitto/) · NATS leaf · AI that summarizes the situation and drafts tasks, every action approved | Maps, Kiwix, ntfy and Mosquitto are in the Market. The TAK app, Meshtastic gateway and Pi TAK node profile (Pi 5, 8 GB or more) are researched, not built (doc 09 P0-8) | First C2 product, after M-LIVE |
| **C2** | **Site operations center** for a campus, farm, church, school or event | Small security teams, facility managers | [`home-assistant`](../../../apps/home-assistant/) · [`zigbee2mqtt`](../../../apps/zigbee2mqtt/) · cameras with Frigate (people and vehicle detection) · [`grafana`](../../../apps/grafana/) · [`uptime-kuma`](../../../apps/uptime-kuma/) · AI watches and proposes ("lock gate B"), a person approves | Home Assistant, Zigbee and Grafana are in the Market; Frigate is researched, not packaged | Soon after C1 |
| **C3** | **Multi-site fabric:** one headquarters box plus a box at every site | Farm co-ops, contractors, utilities, multi-campus organisations | Fabric join by QR and owner approval ([`fabric.py`](../../../core/onemind_core/fabric.py)) · Headscale mesh · NATS leaf per site · one dashboard for all sites | Fabric join is in the gateway; the mesh has a lab and a design (lesson [11](../11-mesh-headscale-derp-nats-leaf.md)) | Years 1–2 |
| **C4** | **Field crew operations:** crews, vehicles, tools, check-ins | Small field-service businesses | [`vikunja`](../../../apps/vikunja/) tasks · [`homebox`](../../../apps/homebox/) assets · [`syncthing`](../../../apps/syncthing/) · location over TAK or Meshtastic · [`metabase`](../../../apps/metabase/) reports | Most apps are in the Market | Any time |
| **C5** | **Industrial edge** (the year-2 Industrial profile) | Factories, water plants | MQTT 5 broker bridged into NATS (Sparkplug B) · OPC UA · IEC 62443 certificate path | Researched (doc 09 P0-2, P0-4) | Year 2 |
| **C6** | **Public-safety and government tier** | Agencies, through resellers | All of the above plus NDAA/TAA hardware rules and certifications | Planned (doc 11, distributor phase) | Years 3–5 |

---

## 3. Physical AI paths

| # | Path | Who buys it | How it works on OneMind | Status on 2026-11-24 | When (opinion) |
|---|---|---|---|---|---|
| **P1** | **Greenhouse and farm controller** | Growers, homesteads, schools | ESPHome sensor boards keep their own control loop even when the box is down · [`esphome`](../../../apps/esphome/) · [`home-assistant`](../../../apps/home-assistant/) · [`node-red`](../../../apps/node-red/) · [`ollama`](../../../apps/ollama/) suggests watering, a person approves, the request expires fast | Profile researched, including the two ESPHome safety overrides (doc 09 P0-9); apps are in the Market | First physical-AI product, after M-LIVE |
| **P2** | **Edge vision AI:** cameras plus a local model on a GPU box | Farms (animals, gates), shops (stock), wildlife, inspection | Pro tier (x86 with a GPU) · Frigate · local vision models · nothing leaves the site | Ollama is in the Market; the GPU flavor is planned | Years 1–2 |
| **P3** | **Drone operations station** | Survey, agriculture, search and rescue | A Jetson or Pi as the companion computer; **the flight controller (PX4) stays in charge**; OneMind does mission planning, the MAVLink-to-NATS bridge, video, logs and approval before a mission upload | Researched (doc 08 §11.2); US BVLOS rules not final | Year 2+, **parked** |
| **P4** | **Robot thinking brain and fleet layer** | Robot startups, labs, universities | Robotics tier on Jetson Orin · ROS 2 in containers · a scoped robot-runtime security profile · A/B on Jetson · QR onboarding · OneMind runs updates, approvals, logs and the fleet | Researched (doc 08 FF-1 to FF-8) | Year 1 beta to an OEM in years 2–3, **parked** |
| **P5** | **Robotics education kit** | Schools, homeschool groups, makers | [`kolibri`](../../../apps/kolibri/) offline lessons, Pi or ESP32 kits, a local AI tutor | Kolibri is in the Market | Any time (LE pillar) |
| **P6** | **Home robots and humanoids** | Households | OneMind as the household's brain and permission layer; the robot asks the gateway | Vision only | Years 5–10 |

### The three-brain rule (doc 08)

1. **Reflex brain:** a tiny chip that runs the emergency stop and motor limits. AI never runs here.
2. **Body brain:** Linux running the motors and sensors in real time.
3. **Thinking brain:** AI plus OneMind, which plans, sees, talks and asks.

OneMind always lives in the thinking brain. Safety and stop functions never depend on the cloud, a browser or a remote approval.

---

## 4. Boundary

C2 positioning is civil and public safety. Anything weapons- or targeting-related brings export law (ITAR) and a different risk class. "AI never actuates without human approval" is a selling point exactly here, because agencies are being asked for human-in-the-loop guarantees.

## 5. What first (opinion)

1. **After M-LIVE, build C1 (go-box) and P1 (greenhouse) together.** They share most parts: Pi 5 or N-series hardware, Mosquitto, the NATS leaf, the mesh, approvals and ntfy. Most apps exist, the hardware is cheap, and neither needs a robot.
2. **Then C2 (site operations) and P2 (vision AI),** which share cameras and Frigate.
3. **Robots and drones (P3, P4) stay parked** until OneMind has a robot. The research is ready when that changes.

---

## Check yourself
1. Which two paths share the most parts, and name three of those parts.
2. Why must a greenhouse sensor board keep its own control loop?
3. On a drone, which computer is in charge of flying, and what does OneMind do?
4. What stops an approved "open valve" from running hours later?
5. Which paths are parked, and under what rule?
