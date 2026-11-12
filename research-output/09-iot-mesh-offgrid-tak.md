# 09 · IoT, Industrial IoT, mesh, off-grid and TAK

**Workstream:** W8 (Tier A for IoT/IIoT foundation fit, F-11) · **Date:** 2026-11-10 (synced to `01` rev. 4.1 on 2026-11-11, SYNC5-c) · **Status:** final for this run; refuters have run (W8 P0 refuters, round-4 DC-02 refuters, `01` §5.8 and §5.9.2)
**Sync note (rev. 4.1):** the foundation is now the one in `01` §1: **Ubuntu 26.04 LTS + RAUC A/B** is the decision of record, a **Debian 13 leg** is built from the same definition until the base is locked, and **Rugix is the documented alternative, not the update engine**. Most of this file was written on 2026-11-10 for "Debian 13 + Rugix". That analysis is kept as the record of the Debian leg. The first column of the §1 table assesses G4 for the decision of record (FIX7, re-checked by DEC5): **CONDITIONAL, no sub-check fails** [C-G4U-001, C-G4U-004, C-G4U-008].
**Owns:** DC-02 (gate G4, "no blocking IoT/IIoT limitation") · the P-8 profiles for a **Pi TAK node** and a **greenhouse controller** · bank questions listed in `evidence/qbank/W8.md`
**Builds on:** `research/platform/iiot-landscape-and-requirements.md` (the IIoT report, not redone here), `research/platform/robotics-iot-xr-nvidia.md` §3–§7, `research/platform/fedora-iot-and-redhat-edge-deep-dive.md` §7, `context/03` §1.5, and the parallel teardowns in `02-competitors/` (HAOS, umbrelOS, Olares, VillageOS)
**Evidence:** claims `evidence/claims/W8.csv` (C-W8-001…063) · sources `evidence/sources/W8.md` · lab spike `evidence/lab/w8-nats-leaf-buffer/` · scorecard rules `evidence/scorecard-weights.md` (frozen v1.0; this file reports gate **G4** only and scores nothing else)
**Serves requirements:** F-11, F-12, F-13, F-14, N-1, N-2, N-4, N-6, N-10, AI-7, P-8, A-5, A-7, M-4, M-7, R-1, R-3, U-5, H-3

> ### Explain it like I'm the founder
> You asked for an OS that never hits a wall for IoT or industrial IoT, from a greenhouse to a factory. The question this file had to answer is simple: **does anything in the proposed foundation block that?** When this was written the foundation was Debian 13 + Rugix A/B updates + k3s + NATS. Since `01` rev. 4 it is **Ubuntu 26.04 + RAUC A/B + k3s + NATS**, with a Debian 13 leg kept until the base is locked. The answer is the same for both: nothing blocks it (§1).
>
> **Short answer: no, nothing blocks it, but four things need work, and one tool we were counting on is off-limits.**
> - **Industrial vendors already ship Debian.** Siemens' own Industrial Edge device image is Debian 12 [C-W8-037]. Moxa's industrial Linux is Debian 13, and it holds the industrial security certificate (IEC 62443-4-2, level 2) that people assume only Red Hat has [C-W8-033]. So choosing Debian doesn't lock you out of factories.
> - **The four things to build:** a real-time kernel for the Pi 5 (Debian has one for PCs and generic ARM, the Pi 5 needs its own build) [C-W8-001, C-W8-040]; packaging a zero-touch onboarding client (FDO) [C-W8-044]; a second MQTT broker for devices that speak MQTT 5, because NATS refuses them [C-W8-007]; and a proof that the fleet tooling handles about 10,000 devices.
> - **Off-limits:** Reticulum, a popular off-grid mesh network, has a license that forbids use in any system that can harm people and any use in AI training data [C-W8-014]. A product sold to public safety and built around AI can't bundle it.
> - **Proven in our lab today:** when the internet link to a site drops, a small NATS server on the site box keeps every sensor reading and delivers all of it once the link returns. 600 out of 600 messages, none lost or doubled [C-W8-050].
> - **Your two profiles:** a Pi TAK node needs a Pi 5 with at least 8 GB (16 GB recommended) and runs TAK Server in a container [C-W8-018, C-W8-019]. A greenhouse controller is a Pi 5 with 4–8 GB, Home Assistant, a small MQTT broker and ESPHome sensor boards. Those boards must be configured so they don't reboot and switch every relay off when the Pi is down [C-W8-029, C-W8-030].

---

## 0. The answer (P0 conclusions)

| # | Conclusion | Evidence | Confidence | Req. IDs |
|---|---|---|---|---|
| **P0-1** | *(Rev. 4.1: the same holds for the decision of record, Ubuntu 26.04 + RAUC + k3s: G4 CONDITIONAL, no sub-check fails, so DC-02's flip condition is not met for it either; §1 first column [C-G4U-001, C-G4U-004, C-G4U-008].)* **Gate G4 is not failed by Debian 13 + Rugix + k3s. Its result is CONDITIONAL**, with four named mitigations: a Pi 5 PREEMPT_RT kernel variant, a packaged FDO client, an MQTT 5 broker app, and a 10k-device fleet test. **DC-02's flip condition ("a G4 sub-check FAILs for Debian + Rugix and PASSes for an alternative") is not met.** ADR-001 D2/D3 stand on IoT/IIoT grounds. | §1 table; C-W8-001…006, 033, 037, 038, 044, 046, 049, 050 | High for (a)–(d), medium for (e) | F-11, F-12, F-14 |
| **P0-2** | **IEC 62443-4-2 does not require the Red Hat lineage.** A Debian 13-based OS (Moxa MIL4) holds a 62443-4-2 SL2 certification declaration (2026-07-02). The Debian-based CIP project announced 62443-4-1 and 4-2 compliance (2026-09-28). Certification attaches to a product (device + OS + configuration), never to "an OS". | C-W8-033, 034, 035; RHEL precedent C-W8-063 | High (vendor-published; certificate PDFs not opened) | F-11, R-3 |
| **P0-3** | **FDO zero-touch onboarding is not a Fedora/RHEL advantage any more.** Fedora IoT's Rust FDO implementation was deprecated on 2026-02-09. The maintained FDO code is distro-agnostic Go (Apache-2.0). FDO 1.1 and 2.0 are Proposed Standards (2026-04-02). | C-W8-042, 043, 044 | High | N-4, F-11, F-12 |
| **P0-4** | **NATS can be the site's MQTT 3.1.1 + Sparkplug B broker, but it cannot accept MQTT 5 clients.** NATS rejects MQTT v5 at connect, and it has implemented "Sparkplug Aware" broker rules since 2024. OneMind needs an MQTT 5 broker as a Market app (Mosquitto, EPL-2.0 OR BSD-3-Clause, or NanoMQ, MIT), bridged into NATS. EMQX ≥ 5.9 is excluded: its BSL forbids embedding it in a product. | C-W8-007…013 | High | F-11, AI-7, A-5 |
| **P0-5** | **NATS leaf nodes give store-and-forward across outages, but only for subjects captured by a stream on the leaf.** Lab: 600/600 delivered, no gaps or duplicates, 40 s after the hub returned. Plain pub/sub was not buffered. | C-W8-050 (lab) | High for the tested case; long and lossy outages untested | N-6, F-13, P-8 |
| **P0-6** | **OneMind's native mesh is batman-adv + WireGuard/Headscale + NATS leaf, with Meshtastic and LoRaWAN as radio gateways. Reticulum may only be a user-installed, non-default app.** batman-adv, 802.11s and WireGuard are in Debian's kernel [C-W8-003]. Reticulum's license bars harmful-use systems and AI training [C-W8-014]. | C-W8-003, 014, 015, 016, 032 | High | N-6, F-13, D-001 |
| **P0-7** | **The base OS must expose host networking and device-passthrough as a permissioned capability, because every competitor's Home Assistant app needs it.** umbrelOS runs HA privileged with host networking and all of `/dev` [C-W8-026]. Olares turns privileged on for USB radios [C-W8-027]. HA supports Matter only on HA OS [C-W8-025]. | C-W8-024…027, 060 | High | A-5, AI-7, N-1, F-11 |
| **P0-8** | **A Pi TAK node needs a Pi 5 with ≥ 8 GB and runs TAK Server as a container.** TAK supports Raspberry Pi OS 64-bit and recommends an 8 GB Pi for a minimal server [C-W8-018]. Debian 13 has no Java 17 for the host package [C-W8-019]. OpenTAKServer (GPL-3.0) is the light alternative for 4 GB boards [C-W8-021]. | C-W8-017…023 | High (docs); footprint `pending-lab` | P-8, N-2, F-14 |
| **P0-9** | **ESPHome's defaults are unsafe for an unattended greenhouse.** A node reboots after 15 min with no API client, and relays default to OFF at boot. The greenhouse profile must override both and keep the control loop on the node. | C-W8-029, 030 | High | P-8, AI-7, F-13 |

**What would flip these.** P0-1 flips if any of: a Pi 5 PREEMPT_RT build can't hold soft-real-time latency under k3s load (LAB-W7-1); a 62443-4-2 assessor rejects a Debian + Rugix host-device configuration that it accepts on RHEL; FDO can't bind to the target boards' identity hardware; or a 10k simulated fleet can't be driven by any Rugix-integrated fleet manager while Flight Control on bootc can. P0-4 flips if NATS adds MQTT 5. P0-6 flips if Reticulum is relicensed.

---

## 1. DC-02 · Gate G4: is there a blocking IoT/IIoT limitation? (F-11)

G4 has five sub-checks (`evidence/scorecard-weights.md` §2). One FAIL fails the gate. Below, each sub-check is tested against the ADR-001 stack and the runner-ups. A cell marked *carried* reuses a sibling workstream's or prior report's claim.

| Sub-check | **Ubuntu 26.04 + RAUC + k3s (decision of record, 01 rev. 4; added by FIX7)** | Debian 13 + Rugix + k3s (ADR-001) | Fedora IoT / Fedora bootc | CentOS Stream 10 → RHEL 10 image mode | CIP Core (Debian via Isar) | Ubuntu Core 24/26 |
|---|---|---|---|---|---|---|
| **(a) Industrial protocols run as apps** (OPC UA, MQTT 5 + Sparkplug B, Modbus, BACnet, CAN) | **PASS.** open62541 1.4.11.1, mosquitto 2.0.22 (MQTT 5), libmodbus 3.1.11 and can-utils are in 26.04 *universe* [C-FIX7-004]. Universe security fixes come with Ubuntu Pro for Devices, which lists "Universe and Main" [C-FIX4-001], so the protocol packages are covered only on a Pro-attached box. SocketCAN, the Sparkplug-aware NATS and bacnet-stack are base-agnostic, as in the Debian column; everything else ships as containers. | **PASS.** open62541 packaged for amd64/arm64 [C-W8-004]; libmodbus, mosquitto (MQTT 5), can-utils packaged [C-W8-005, 011]; SocketCAN in the kernel [C-W8-002]; NATS is Sparkplug-aware for 3.1.1 [C-W8-008]; BACnet via bacnet-stack (GPL with linking exception) [C-W8-059]. Everything else ships as containers. | PASS *(containers; same apps)*. | PASS *(containers)*. | PASS *(Debian packages)* [C-W8-038]. | PASS *(snaps/containers; carried from IIoT report)*. |
| **(b) Real time:** PREEMPT_RT or isolated cores; hard RT delegated | **CONDITIONAL.** x86 and generic arm64: the PREEMPT_RT kernel is free from 26.04 (`ubuntu-realtime`, `linux-realtime` in main) [C-FIX7-002, C-STEEL-ubu-008]; an Intel-optimised variant comes with Pro [C-FIX7-002]. **Pi 5:** Canonical states its Pi 4/5 real-time variant only for the **24.04** release (v6.8) [C-FIX7-002], and no 26.04 `linux-raspi-realtime` is listed [C-FIX7-003, SECONDARY]. *DEC5 correction:* Canonical's releases table lists a raspi real-time variant for 26.04 (RT kernel 7.0), and its 26.04 install guide names `linux-raspi-realtime` [C-G4U-001, C-G4U-002]. Which Pi models it boots, and whether it is in the 26.04 archive, are unverified. So G4-M1 still applies (measure, else build). Jetson: Canonical's `linux-nvidia-tegra` 26.04 `-rt` flavour is only in `-proposed` [C-STEEL-ubu-005]. | **CONDITIONAL.** x86 and generic arm64: Debian ships `linux-image-rt-*` [C-W8-001]. **Pi 5:** Raspberry Pi ships only generic `-rpi-v8-rt` builds, no Pi 5 (2712) RT kernel [C-W7-024], and its tree has no bcm2712 RT defconfig [C-W8-040]. Mitigation: measure `v8-rt` on Pi 5, else build a 2712 RT variant (W18). Jetson: NVIDIA's RT kernel is Developer Preview (carried, W7). | CONDITIONAL. Fedora defaults RT builds off (carried, deep dive §7). | PASS on x86 (RHEL for Real Time); ARM64 RT is Tech Preview (carried). | CONDITIONAL. CIP maintains 10-year SLTS kernels (carried, IIoT report); an RT variant was not verified here. | CONDITIONAL (carried). |
| **(c) A path to IEC 62443-4-1/4-2** | **PASS (path exists).** A classic Ubuntu LTS (22.04.3, with Eurotech ESF) is the OS of an ISASecure-certified IEC 62443-4-2 **SL-C 2 host device**, the ReliaCOR 44-11 [C-FIX7-001]. Canonical's secure development process is audited to 62443-4-1 [C-STEEL-ubu-010], and the Ubuntu Core-based ctrlX OS holds 4-2 SL2 [C-CIT4-012, C-STEEL-ubu-010]. No 26.04 certificate exists; OneMind's path is still a certified reference box (§4). | **PASS (path exists).** A Debian 13-based OS holds a 4-2 SL2 certification declaration on specific hardware [C-W8-033]; CIP (Debian-based) announced 4-1 + 4-2 [C-W8-034]. OneMind's path is a certified *reference box*, not a certified OS (§4). | CONDITIONAL. No Fedora certificate; it relies on RHEL. | PASS. RHEL 9.6 and MicroShift 4.21 SL-C 2 (RHEL 10 not listed) [C-W8-063]. | PASS [C-W8-034]. | CONDITIONAL. The Eurotech precedent is Ubuntu 22.04, not Ubuntu Core (carried). |
| **(d) Zero-touch onboarding** (FDO, IDevID or equivalent) | **CONDITIONAL**, the same as Debian: go-fdo is distro-agnostic but has no release and no FIDO interop [C-W8-044, C-REF4-DC-technical-004], and no Ubuntu package was found. *DEC5:* go-fdo-client v1.0.0 and go-fdo-server v1.0.2 are now released, but packaged only as RPMs, and the library they pin is untagged and not interop-tested [C-G4U-004…006]. The Pi 5 has no TPM [C-W8-041]. Whether Ubuntu's wpa_supplicant is built with Wi-Fi DPP was not verified (the archive does not resolve from this session). | **CONDITIONAL.** FDO: go-fdo (Apache-2.0) is distro-agnostic [C-W8-044], but there's no Debian package, and it isn't interop-certified yet. Wi-Fi DPP is built into Debian's wpa_supplicant/hostapd [C-W8-006]. IDevID needs a TPM: fine on x86 boxes, but **the Pi 5 has no TPM** in Raspberry Pi's security architecture [C-W8-041], so a TPM HAT or secure element is needed for industrial SKUs. | CONDITIONAL. Its FDO client (fdo-rs) is deprecated [C-W8-043]; it moves to the same Go code. | CONDITIONAL (same). | CONDITIONAL (no FDO in CIP found). | CONDITIONAL. "Secure onboarding" is claimed in Canonical docs (carried), mechanism not verified here. |
| **(e) Fleet scale to ~10k devices** | **CONDITIONAL.** k3s sizing is base-agnostic [C-W8-049]. RAUC's fleet client is the hawkBit updater (LGPL-2.1, v1.4) [C-FIX7-006], but it is packaged for Ubuntu 26.10 and Debian 14, not 26.04 [C-FIX7-005, SECONDARY], so OneMind must build or backport it. Landscape comes with Pro for Devices [C-FIX4-001], but it manages packages and inventory (at most 100 instances per change plan) and has no A/B bundle handling, so **hawkBit is the OTA plane** [C-G4U-008, C-G4U-010]. **Not shown:** a 10k run. | **CONDITIONAL.** k3s: 16+ CPU/32 GB servers for 1,800+ agents [C-W8-049], so 10k devices means many site clusters, not one. Rugix integrates with Mender, thin-edge.io, Nexigon and Memfault [C-W8-046, 047]. NATS leaf hub-and-spoke works for one site in our lab [C-W8-050]. **Not shown:** a 10k run. | CONDITIONAL. Flight Control is bootc/ostree-native [C-W8-048]; scale also unproven here. | CONDITIONAL (same tool, with Red Hat support). | CONDITIONAL. | CONDITIONAL (Landscape, carried). |
| **G4 result** | **CONDITIONAL** | **CONDITIONAL** | **CONDITIONAL** | **CONDITIONAL** (strongest on c) | **CONDITIONAL** (strongest on c) | **CONDITIONAL** |

**Reading the table.** No stack PASSes every sub-check, and no stack FAILs one. The industrial differences are real but are **not gate failures**: the Red Hat lineage has *ready* 62443 and x86 RT evidence and CIP has *ready* 62443 evidence, while Debian + Rugix has it by *precedent*. That difference is scored under C3 (security) and C4 (proven in production) in `01-FOUNDATION-DECISION.md`, not here. **DC-02 verdict: ADR-001 is not flipped by IoT/IIoT.** The additive "Industrial track" proposed in the IIoT report (CIP Core or RHEL image mode on certified hardware) stays a *sales option*, not a foundation change.

**G4 for the decision of record (FIX7, 2026-11-11; closes critic gap P7-2).** Revision 4 of `01` moved the base to Ubuntu 26.04 + RAUC, but this table was written for Debian 13 + Rugix, and 01 scored D·G4 on a ROS 2 platform row that covers none of the five sub-checks. The new first column fixes that. **Result: Ubuntu 26.04 + RAUC is CONDITIONAL on G4, with no sub-check FAIL.** A FAIL would have un-ranked D, as the D·G1 FAIL rows of the map in 01 §3.1.6 (h) do, and handed S1 to C. That did not happen, so the S1 result does not move.
- **Where Ubuntu is stronger than the Debian column:** (c) has a direct precedent, a *classic* Ubuntu LTS inside a 62443-4-2 SL-C 2 certified host device [C-FIX7-001]. And the 26.04 real-time kernel is free on x86 and generic arm64 [C-FIX7-002].
- **Where it is weaker or new:**
  - (b) Pi 5 real time: FIX7 read Canonical's Pi real-time variant as 24.04-only [C-FIX7-002, C-FIX7-003]. DEC5 found a raspi variant documented for 26.04 [C-G4U-001, C-G4U-002], not yet measured on a Pi 5, so this is weaker only until G4-M1 measures it.
  - (e) Landscape is not an A/B OTA plane, so the fleet plane on this leg is hawkBit [C-G4U-008, C-G4U-010].
  - (a) The protocol packages sit in *universe*, so their security fixes depend on Ubuntu Pro [C-FIX7-004, C-FIX4-001].
  - (e) RAUC's hawkBit client is not packaged for 26.04 [C-FIX7-005].
- **Mitigations on this leg.** G4-M1 to G4-M4 below apply unchanged, except that "Debian package and Rugix recipe" (M2) and "Rugix update agent" (M4) mean an Ubuntu `.deb` and the RAUC + hawkBit updater on this leg. One item is added: **G4-M5**, which backports `rauc-hawkbit-updater` 1.4 to 26.04 in the image pipeline (about 1 day, year 1, inside LAB-W8-5).
- **Caveat.** Package facts for 26.04 come from Repology (SECONDARY), because the Ubuntu archive does not resolve from this session. Re-check them against the archive on a networked machine (20 D1).

**CONDITIONAL mitigations (carry into `20-PLAN-180-DAYS.md` and `23-RISK-REGISTER.md`):**

| ID | Mitigation | Owner | Cost / when | Test |
|---|---|---|---|---|
| G4-M1 | Pi 5 soft-RT: measure `-rpi-v8-rt`, else build a bcm2712 PREEMPT_RT variant in the image pipeline | W18 / founder | ~2–4 days; days 60–120 | LAB-W7-1 |
| G4-M2 | Package `go-fdo-client` as a Debian package and Rugix recipe, with a rendezvous/owner service as a OneMind Cloud or self-hosted app | W8 / W6 | ~1 week; year 1 | LAB-W8-4 |
| G4-M3 | Ship an MQTT 5 broker app (Mosquitto default, NanoMQ for small boards), bridged to NATS subjects; run the Sparkplug TCK against NATS and the broker | W8 | ~1 week; days 90–180 | LAB-W8-3 |
| G4-M4 | Fleet test: 100 simulated sites (k3s + NATS leaf + Rugix update agent) against one hub, extrapolated to 10k, plus a vendor fleet manager (thin-edge.io / Mender OSS) driving Rugix | W8 / W4 | ~2 weeks; year 1 | LAB-W8-5 |

---

## 2. Protocols and the site bus

### 2.1 What changed since the IIoT report

The IIoT report (§1, §2) stands. Three findings correct or extend it:

1. **NATS is Sparkplug-aware.** The IIoT report listed "NATS conformance with Sparkplug" as UNVERIFIED. The NATS server has implemented Sparkplug Aware broker rules since 2024-04-03 [C-W8-008], and Sparkplug accepts any full MQTT 3.1.1 server with QoS 0/1, Will and retained messages [C-W8-010]. NATS supports QoS 0/1/2 [C-W8-007]. **Still UNVERIFIED:** a TCK run. Note that the `.` in `spBv1.0` becomes `//` in NATS subjects [C-W8-009], so OneMind's subject grammar must leave Sparkplug in its own namespace, bridged rather than rewritten.
2. **MQTT 5 needs a second broker.** NATS rejects MQTT v5 clients outright [C-W8-007]. Broker options, by license (G1):

| Broker | MQTT 5 | License | Embed in a sold OneMind box? | Note |
|---|---|---|---|---|
| **Mosquitto** | Yes [C-W8-011] | EPL-2.0 OR BSD-3-Clause [C-W8-011] | **Yes.** Default | In Debian trixie (2.0.21) [C-W8-005]; in Umbrel's catalog [C-W8-028] |
| **NanoMQ** | Yes, except enhanced auth and server redirection [C-W8-012] | MIT [C-W8-012] | **Yes.** Small-board option | Has a QUIC bridge build option |
| HiveMQ CE | Yes (carried) | Apache-2.0 (GitHub metadata) | Yes, but JVM-heavy | |
| **EMQX ≥ 5.9** | Yes | **BSL 1.1**; the grant excludes "integrating into a product… offered to third parties" [C-W8-013] | **No** | User-installed only, never bundled |
| NATS MQTT | **No (3.1.1 only)** [C-W8-007] | Apache-2.0 | Yes (it's the bus) | Sparkplug-aware [C-W8-008] |

3. **Current versions** (all `PRIMARY-METADATA`, 2026-11-10): open62541 v1.5.10 (MPL-2.0) [C-W8-055]; Apache PLC4X **1.0.0** (2026-09-07; the IIoT report saw it pre-1.0) [C-W8-056]; OpenPLC's v4 runtime v4.3.2 (v3 is end-of-life) [C-W8-057]; Akri v0.14.0, Eclipse Hono 2.7.0, EdgeX 4.0.2, Node-RED 5.0.9, 4diac FORTE 3.3.0 [C-W8-058]; Margo still **Preview Release 3**, no GA date [C-W8-053], and its spec repo carries an OWF CLA grant, not an SPDX license [C-W8-054].

### 2.2 The site bus design (recommendation W8-R1)

```
 field devices                      OneMind node (site)                                hub (home server / cloud)
 ─────────────                      ───────────────────                                ─────────────────────────
 ESPHome ──native API──► Home Assistant ─┐
 Zigbee/Z-Wave ─► Z2M/ZWJS ─MQTT 3.1.1─┐ │
 MQTT 5 sensors ──► Mosquitto (app) ───┤ │ bridge
 Sparkplug edge nodes ─MQTT 3.1.1──────┼─┴──►  NATS (k3s pod, JetStream domain "site-x")  ══ leaf ══►  NATS hub
 OPC UA PLCs ◄─ open62541/PLC4X adapter┤          streams: tel.> evt.> det.> (local)                 streams source site-x
 Modbus/BACnet ◄─ adapter app ─────────┘          KV: device twins (desired/reported)
 LoRaWAN ─► ChirpStack ─MQTT─► NATS                 └─► capability gateway (MCP) ─► agents, approvals
 Meshtastic radio ─MQTT/serial─► mesh gateway ─► NATS ─► tak.cot.inject ─► TAK Server
```

- **NATS is the authority bus at every site**, the same doctrine as the founder's cluster (context/01 §5). Devices that can't speak NATS get a bridge, as the doctrine says: "Anything that can't speak NATS gets a bridge."
- **MQTT 3.1.1 devices** (Zigbee2MQTT, ChirpStack, Meshtastic gateways, Sparkplug edge nodes) can connect **directly to the NATS MQTT listener** [C-W8-007, 008]. **MQTT 5 devices** connect to Mosquitto, which bridges topics into NATS.
- **Subject mapping follows the locked grammar** (context/01 §5): `tel.{node}.{class}.{metric}`, `evt.{domain}.{entity}.{event}`, `cmd.{domain}.{entity}.{action}`, `det.…`, `tak.cot.inject`. Raw vendor topics (ChirpStack's `application/…/event/up` [C-W8-032], Meshtastic's `msh/…` [C-W8-016], Sparkplug's `spBv1.0/…`) stay in a bridged raw namespace. An adapter app normalises them into the grammar. **No new top-level patterns are invented.**
- **Every subject that must survive an outage gets a stream on the leaf** (§5.1, lab result).
- **Commands carry a TTL and an idempotency key**, so a command delivered after an outage is dropped, not executed late (§5.1).

### 2.3 Control vs supervision (unchanged, restated as a rule)

The IIoT report's split stands: safety and hard real-time loops stay on PLCs, MCUs and certified controllers; OneMind **supervises** and sends **bounded setpoints**. Two additions from this pass:
- **Debian ships PREEMPT_RT kernels and the TSN qdiscs** (taprio, etf) plus PTP clock support [C-W8-001, C-W8-003]. So soft-real-time and TSN-ready supervision on x86/arm64 needs no custom kernel. On Pi 5 it does (G4-M1).
- **EtherCAT, PROFINET and IO-Link stay below a PLC or gateway.** OneMind reads them through OPC UA or vendor gateways (IIoT report §1.2).

---

## 3. What industrial edge platforms actually ship (competitor and constraint fit)

### What competitors do

| Product | Base OS (evidence) | Update / fleet | Team & market | K8s? | Constraint fit with OneMind |
|---|---|---|---|---|---|
| **Siemens Industrial Edge Own Device (IEOD)** | **Debian 12** + Industrial Edge Device Kit 1.24.1; x86-64 UEFI only, min 2 GB; TPM 2.0 disk encryption [C-W8-037] | Industrial Edge Management (central, closed) | Global automation vendor | Docker apps | **High on base OS** (Debian appliance for industry); low on openness and arm |
| **Siemens SIMATIC IOT2050** | Debian via **Isar + isar-cip-core** [C-W8-038] | SWUpdate image variants (README) | Same | No | **High**: proves the CIP/Isar industrial route on Arm |
| **Moxa MIL3/MIL4** | **Debian 11 / Debian 13**; 10-year support (MIL4 to Aug 2035) [C-W8-033] | Vendor tools | Industrial hardware vendor | No | **High on certification**: a Debian 13-based 62443-4-2 SL2 product [C-W8-033] |
| **Revolution Pi** | Raspberry Pi OS (Debian) "RevPi Trixie", kernel 6.18 [C-W8-039] | Apt | Small industrial vendor, CM5 hardware | No | **High on Pi/CM5 path** (same SoC family as OneMind Edge) |
| **Red Hat Device Edge** | RHEL image mode (bootc) + MicroShift; GA on Jetson Orin (carried) [C-W8-063] | Flight Control / Edge Manager, bootc-native [C-W8-048] | Large vendor | MicroShift | Medium: best certified story; subscription; Pi weak |
| **Ubuntu Core** | Snap-based; 10 + 5 years (carried, IIoT report) | Snap store / Landscape | Large vendor | Optional | Medium: lock-in to snaps, per-device Pro pricing unpublished |
| **Azure IoT Operations / AWS Greengrass** | Customer OS; cloud-managed (carried) | Cloud | Hyperscalers | Arc / no | Low: cloud lock-in, runtime churn (IIoT report §3) |
| **Home Assistant OS** | Buildroot + RAUC (see `02-competitors/home-assistant-os.md`) | Supervisor | Funded team, consumer | No | High for consumer IoT UX, none for IIoT |
| **umbrelOS / Olares** | Debian + Rugix / installs on Ubuntu/Debian with k3s | umbreld / Olares | Small / funded teams | No / k3s | Consumer only: **no MQTT broker in Olares's catalog**; neither catalog has TAK, Meshtastic, OPC UA or LoRaWAN apps [C-W8-028] |

**Lesson.** The industrial vendors whose constraints are closest to OneMind (Siemens IEOD, IOT2050, Moxa, RevPi) **ship Debian or Debian-derived images**. That makes "Debian appliance + container apps" the constraint-matched default for IIoT, not just for consumer boxes. The Red Hat lineage is the strongest *certified-subscription* option and is kept as the Industrial/Enterprise track (deep dive §9), with no foundation change. **No consumer competitor (Umbrel, Olares, HAOS) covers IIoT, mesh or TAK at all [C-W8-028]: that gap is OneMind's opening.**

---

## 4. IEC 62443, NIST 800-82 and what OneMind must do

- **Standards (metadata only, clause text not read):** IEC 62443-4-2:2019, edition 1.0, stability date 2027, so a revision may come [C-W8-035]. NIST SP 800-82r3 is final; the **Rev 4 draft closes comments on 2026-11-30** [C-W8-036].
- **Precedents:** Moxa MIL4 (Debian 13) holds 4-2 SL2 on named UC models [C-W8-033]. CIP announced 4-1 + 4-2 compliance, and adopters keep product responsibility [C-W8-034]. RHEL 9.6 / MicroShift 4.21 hold SL-C 2 [C-W8-063].
- **What it means for OneMind (W8-R5):** OneMind should claim 62443 for a *reference box* (OneMind Industrial: an x86 IPC or CM5 carrier with a TPM 2.0, signed A/B, measured boot), assessed as a **host device** with its configuration. Start with the **4-1 process** (SBOM, vulnerability handling, secure update), which also feeds the CRA (W6 owns the CRA analysis). **The certificate PDFs themselves weren't opened**, so the scope of each precedent is as published by the vendor. Before any marketing claim, buy or request the Moxa declaration and the CIP assessment report (`evidence/outreach-drafts.md` is W6's).

---

## 5. Mesh, off-grid and satellite (N-6, F-13)

### 5.1 NATS leaf store-and-forward: lab result

The phase-1 research could not confirm leaf buffering from the docs. The W8-1 spike (`evidence/lab/w8-nats-leaf-buffer/`, criteria written before the run) showed [C-W8-050]:

| Step | Result |
|---|---|
| Leaf (own JetStream domain `site1`) + hub stream **sourcing** the leaf stream | Normal flow: 100/100 |
| Hub down; 500 acked publishes at the leaf | All 500 accepted and stored locally (600 on the leaf) |
| Hub back | Leaf link up in ~1 s; **hub stream 600/600 after 40 s**; payloads 1..600, no gaps, no duplicates |
| Plain core-NATS publishes during the outage | **Not delivered** (expected) |

**Design rules from the result (W8-R2):**
1. Every telemetry, event, detection and audit subject a site must keep is captured by a **leaf-local stream** with an age/size limit sized for the longest expected outage. Example: a homestead on satellite planning for 7 days at 5 msg/s needs about 3M messages.
2. Status UIs show "synced" only when **source lag = 0**, not when the link is up. The ~40 s catch-up is source retry, not link time.
3. **Commands are never replayed blindly:** `cmd.*` messages carry an expiry, and the device rejects late ones. Request/reply doesn't survive outages, so agents must handle "site unreachable" explicitly.
4. Untested, scheduled in `22-…` as LAB-W8-2: lossy links (tc netem), multi-day outages, a full leaf disk, power loss on a Pi 5 during the write, and 100 leaves on one hub.

### 5.2 Native mesh options

| Option | What it is | License / packaging | Fit | Verdict |
|---|---|---|---|---|
| **batman-adv** | Layer-2 mesh in the kernel | Kernel module in Debian (`CONFIG_BATMAN_ADV=m`), `batctl` packaged [C-W8-003, 005] | Wi-Fi/Ethernet mesh across a farm; DHCP and IPv6 work unchanged (carried, context/03) | **Native, default** for multi-box sites |
| **802.11s** | Wi-Fi mesh standard | `CONFIG_MAC80211_MESH=y`; wpa_supplicant `CONFIG_MESH=y` [C-W8-003, 006] | Encrypted (SAE) mesh links under batman-adv | **Native**, transport for batman-adv |
| **WireGuard + Headscale/Tailscale** | Overlay VPN | Kernel WireGuard [C-W8-003]; Headscale v0.29.7 BSD-3 [C-W8-061] | Remote reach (U-5); single tailnet per Headscale (carried) | **Native** for remote access |
| **NATS leaf** | Store-and-forward data plane | Apache-2.0 | Lab-proven buffering [C-W8-050] | **Native**, the data plane across sites |
| **Meshtastic** | LoRa text/position/telemetry mesh | Firmware GPL-3.0 on separate radios; MQTT gateway topics [C-W8-016]; ATAK plugin GPL-3.0 [C-W8-015] | Low-rate fallback channel, PLI and chat for TAK; 56 KB file cap, hop limit 3 [C-W8-015] | **Gateway app** (separate process: no license mixing) |
| **LoRaWAN (ChirpStack)** | Sensor WAN | MIT; MQTT JSON integration [C-W8-032]; Concentratord supports SX1301/1302/1303 HALs [C-W8-032] | Battery sensors over kilometres (soil, water tanks) | **Market app** (greenhouse/farm bundle) |
| **Reticulum** | Crypto networking over any medium | **Reticulum License: no use in systems able to harm humans; no AI-training use** [C-W8-014] | Technically excellent for very slow links (carried) | **Not bundled, not default.** User-installed app only, with a license notice. It can't sit in a public-safety or AI-native default image |
| **Satellite direct-to-cell** | Phone-to-satellite data | Android apps must opt in via `PROPERTY_SATELLITE_DATA_OPTIMIZED`; FCM needs `bandwidth_constrained_ok` [C-W8-051]; carriers list supported apps (SECONDARY) [C-W8-052] | Phones in dead zones, not boxes | **Client feature:** the OneMind phone app should opt in and send only alerts and approvals over constrained networks (W11). A box needs a terminal (Starlink-class) or LTE, not D2C |

**Competitor check:** no consumer competitor offers any of this natively (§3, [C-W8-028]). VillageOS describes a "digital mycelial network" with no protocol or code (`02-competitors/villageos.md` §8).

---

## 6. Home Assistant as OneMind's IoT engine (Q305)

### What competitors do

| Product | How HA runs | Device access | Matter/Thread | Code | Constraint fit |
|---|---|---|---|---|---|
| **HAOS** | Native, with the Supervisor and apps | Full | **The only supported Matter setup** [C-W8-025] | `02-competitors/home-assistant-os.md` | Consumer appliance |
| **umbrelOS** | HA Container (2026.11.1) | `network_mode: host`, `privileged: true`, `/dev` and D-Bus mounted [C-W8-026]; Zigbee2MQTT also privileged [C-W8-060] | Unsupported path (Container) | umbrel-apps@51aac97 | Same as OneMind's consumer tier; no k8s |
| **Olares** | HA Container (2026.10.0) as a k8s Deployment | Privileged **only** if USB passthrough is enabled; warns "≈ host root"; network coordinators need no passthrough [C-W8-027] | Unsupported path | beclab/apps@37a1fb4 | **Closest to OneMind** (k3s) |

**Recommendation (W8-R3):**
1. **Default:** HA Container as a Market app on k3s, the Olares pattern, with two declared capabilities in `onemind.app.yaml`: `hostNetwork` (for mDNS/IPv6 multicast discovery, which Matter needs [C-W8-025]) and a **named device grant** (one `/dev/serial/by-id/...` path, never all of `/dev` as Umbrel does). Both need the user's approval at install and are audit-logged. **This is a day-one base-OS extension point** (feeds DC-16 / W19): device grants, host network and udev-stable device names.
2. **Prefer network radio coordinators** (Ethernet/Wi-Fi Zigbee or Thread coordinators via `socket://`) in OneMind bundles. That removes the privileged need entirely [C-W8-027].
3. **Full Matter/Thread and HA apps:** offer **"Home Assistant OS as a VM"** (a KubeVirt or QEMU VM app) on x86 and Pi 5 boxes with enough RAM. This is HA's supported path [C-W8-024, 025]. Pi 5 KVM performance is `pending-lab` (LAB-W8-6).
4. **Never re-implement HA.** OneMind reads HA's entities into the capability layer (MCP) with per-entity permission classes (read / advisory-write / control-write / safety-read-only, IIoT report §5.2).

---

## 7. TAK (situational awareness)

| Component | Facts | License | OneMind use |
|---|---|---|---|
| **TAK Server** | Public source on GitHub up to 5.7 [C-W8-017, 062]; supports RPi OS 64-bit and Ubuntu 22; 4 cores / 8 GB / 40 GB; a Pi 4 8 GB is recommended for a minimal setup; Java 17; single server < 500 users; Docker and hardened Docker bundles [C-W8-018] | GPL-3.0 [C-W8-017] | **Pro/Omni tiers and Pi 5 16 GB:** container (Debian 13 lacks Java 17 [C-W8-019]); reuse the founder's hardened images and NatsBridgePlugin (context/01 §7) |
| **OpenTAKServer** | Python 3.10+, RabbitMQ; Ubuntu and Raspberry Pi installers; ATAK 4.8+, iTAK, WinTAK; has a Meshtastic gateway page [C-W8-021] | GPL-3.0 | **Pi TAK node on 4–8 GB** and the field kit; candidate default for small boards (`pending-lab`) |
| **FreeTAKServer** | No push since 2024-10-29 [C-W8-022] | EPL-2.0 | **Avoid** (stale) |
| **CloudTAK** | Browser TAK client; Compose gives the core map, full ETL needs AWS [C-W8-023] | **AGPL-3.0** | Separate Market app (the founder runs it); don't embed in the dashboard's code (AGPL) |
| **ATAK-CIV** | Source on TAK-Product-Center/atak-civ; the DoD repo is archived [C-W8-020] | GPL-3.0 | Client on phones (W14) |
| **Meshtastic ATAK plugin** | Needs the Meshtastic app + ATAK-CIV; relays mesh ↔ TAK server [C-W8-015] | GPL-3.0 | Phones; the box uses a Meshtastic-radio gateway instead |

**License note (G1):** GPL-3.0 and AGPL-3.0 TAK components are fine as **separate Market apps** (separate programs talking over the network). They must not be linked into OneMind's Apache-2.0 core, and the box must offer source for GPL binaries it ships (license matrix, W6/§6 of the brief).

---

## 8. P-8 profiles: Pi TAK node and greenhouse controller

### 8.1 What a "profile" is (W8-R4)

A profile is **not a separate OS**. It is the same signed OneMind image (base per `01` §1: Ubuntu 26.04 + RAUC A/B + k3s + NATS on the decision of record, with a Debian 13 leg until the base lock; written originally for Debian 13 + Rugix) plus three layers, all versioned and signed:
1. **A bundle:** a pinned set of Market apps with their versions (the A-7 bundle mechanism).
2. **A config pack:** NATS streams and subject mappings, capability grants, update policy and resource budget.
3. **Optional image extras** baked into the image by the release pipeline's layers (Rugix Bakery when this was written) *only* where they must exist before networking: radio drivers, kernel variant (RT), udev rules.

It is chosen at first boot (QR or the setup page) or switched later. That keeps F-14 ("one OS, no product switch"): a greenhouse Pi and a GPU cluster run the same image family and app format. W12/W19 own the bundle format. This section specifies the two required profiles.

### 8.2 Profile `tak-node` (Pi TAK node)

| Field | Specification | Evidence / status |
|---|---|---|
| **Purpose** | A portable, off-grid TAK server for a team: CoT relay, data packages, chat; works with no internet; syncs to the hub when a link exists | P-8, N-6 |
| **Hardware** | **Pi 5 16 GB** (TAK Server profile) or **Pi 5 8 GB** (OpenTAKServer profile); NVMe (not SD) for the database; 12 V DC input; 1–2 Meshtastic radios on USB; optional GPS (PPS) for time | TAK recommends 8 GB for a minimal server on a Pi 4 [C-W8-018]; k3s server ~1.6 GB measured on Pi 4 (context/03 §1.4); total budget `pending-lab` |
| **Base** | Standard OneMind Edge image (arm64; base per `01` §1: Ubuntu 26.04 on the decision of record, Debian 13 leg kept; RAUC A/B; k3s single node) | `01` rev. 4.1 §1 |
| **Apps (bundle)** | (a) **TAK Server** container + PostGIS (16 GB variant), or **OpenTAKServer** (8 GB variant) [C-W8-018, 021]; (b) NATS with a NatsBridgePlugin-style CoT bridge on `tak.cot.inject` / `tak.cot.>`; (c) **mesh gateway**: Meshtastic radio over serial/MQTT → NATS → CoT [C-W8-015, 016]; (d) Headscale client (WireGuard) for remote reach; (e) chrony with GPS time | context/01 §5, §7 |
| **Network** | Local Wi-Fi AP (hostapd; DPP available to onboard headless devices by QR [C-W8-006]) + optional batman-adv mesh to other boxes [C-W8-003]; WireGuard to the hub; NATS leaf (own domain) to the hub | §5 |
| **Streams (leaf)** | `COT` capturing `tak.cot.>` (7 days); `tel.>` mesh radio health; `evt.>` audit | Lab rule §5.1 |
| **Security** | TAK client certificates (TAK's enrollment); no public ports; TAK ports reachable only on the local AP and the tailnet (the founder's live pattern, context/01); Meshtastic channels with a non-default key [C-W8-016] | Q231 (W6) |
| **Updates** | Manual ("update when I want", R-1); offline bundle from USB; never auto-update in the field | R-1; W3 |
| **Power** | Measure idle/load watts (LAB-W8-7) | `pending-lab` |
| **Acceptance tests** | (1) 10 ATAK/iTAK clients connect over the local AP and see each other's PLI; (2) a Meshtastic-only phone appears on the TAK map via the gateway; (3) unplug the uplink 24 h, then reconnect: hub has every CoT (stream lag 0); (4) A/B (RAUC) update + rollback with TAK healthy as the gate; (5) cold boot to TAK ready in under 3 min | LAB-W8-1 (in `22-…`) |

### 8.3 Profile `greenhouse` (greenhouse controller)

| Field | Specification | Evidence / status |
|---|---|---|
| **Purpose** | Climate (temperature, humidity, CO₂), irrigation and lighting for one greenhouse or homestead; AI-advised setpoints; works fully offline | P-8, F-13, F-14 |
| **Hardware** | **Pi 5 4–8 GB** (8 GB if HA + Grafana + LoRaWAN); NVMe preferred; ESP32 sensor/relay nodes (ESPHome); optional LoRaWAN HAT for remote tanks/soil; a network Zigbee coordinator if Zigbee sensors are used | HA OS needs ≥ 2 GB on a Pi [C-W8-024]; Olares HA requests 1 GiB, limit 3 GiB [C-W8-027] |
| **Base** | Same OneMind Edge image; no RT kernel needed (greenhouse loops are seconds-to-minutes "soft control", IIoT report §5.2) | ADR-001 |
| **Apps (bundle)** | Home Assistant (Container app, §6) with ESPHome and Zigbee2MQTT; Mosquitto (MQTT 5) [C-W8-011]; NATS (site bus); optional ChirpStack [C-W8-032]; optional Node-RED; time-series store + dashboard (license per W12) | §2, §6 |
| **Control rule (the important one)** | **The loop runs on the ESP32 node, not on the Pi.** Each actuator node has a local thermostat/hysteresis and a max-runtime limit for pumps, valves and heaters. The Pi sends **setpoints** (`cmd.greenhouse.{zone}.set_*`, with a TTL) | IIoT report §5.2; Q94 |
| **ESPHome settings (mandatory)** | `api: reboot_timeout: 0s` (the default 15 min reboots every node when the Pi is down [C-W8-029]); explicit `restore_mode` per relay (the default `ALWAYS_OFF` turns heaters off at every reboot [C-W8-030]): heaters `RESTORE_DEFAULT_ON` in frost season or local thermostat; pumps `ALWAYS_OFF`; API encryption key set [C-W8-029] | ESPHome license: runtime GPLv3 on the node, fine as user firmware [C-W8-031] |
| **Subjects** | `tel.{esp-node}.climate.air_temp`, `tel.{esp-node}.soil.moisture`, `evt.greenhouse.{zone}.frost_risk`, `cmd.greenhouse.{zone}.set_target_temp` (grammar from context/01 §5) | Locked grammar |
| **AI permissions** | Agents may *read* all `tel.*`; *advisory-write* setpoints within configured bounds; *control-write* (direct relay) only with human approval; no write to safety-classed tags | AI-5, AI-7 |
| **Off-grid** | NATS leaf to the hub if any; local alerts (UX-4) even with no internet; power budget for solar | §5 |
| **Acceptance tests** | (1) kill the Pi for 30 min: heaters and vents keep their local behaviour and no node reboots; (2) restore: hub receives the full 30 min of readings; (3) an AI setpoint outside bounds is rejected and logged; (4) A/B (RAUC) rollback with HA healthy as the gate; (5) idle RAM on a 4 GB Pi 5 under 50% | LAB-W8-8 (in `22-…`) |

---

## 9. Community resilience and VillageOS (F-13)

The VillageOS teardown is in `02-competitors/villageos.md`. Its verdict, **"host and partner, do not compete on design"**, is consistent with W8's evidence. VillageOS's public code has no IoT protocol, hardware or edge runtime; OneMind is the edge layer it lacks. W8 adds:
- **The food/water/energy apps OneMind needs are adapter apps on the site bus** (§2.2): energy (Modbus/SunSpec inverters via the Modbus adapter [C-W8-005]), water (LoRaWAN tank and flow sensors [C-W8-032]), food (the greenhouse profile, §8.3).
- **A neighbourhood is a set of sites joined by NATS leaves and a batman-adv/Wi-Fi mesh**, each able to run alone [C-W8-050, C-W8-003]. That is the "digital mycelial network" VillageOS describes, built from shipping parts.
- **Licensing:** VillageOS-API is AGPL-3.0 + commercial (teardown). Host it only as a separate Market app.

---

## 10. Recommendations with requirement IDs

| ID | Recommendation | Requirement IDs | Section |
|---|---|---|---|
| **W8-R1** | NATS as the site bus everywhere; MQTT 3.1.1/Sparkplug direct to NATS; Mosquitto (default) or NanoMQ as the MQTT 5 app; EMQX never bundled; raw vendor topics bridged, then normalised into the locked grammar | F-11, AI-7, N-1, A-5, D-001 | §2 |
| **W8-R2** | Leaf-local JetStream streams for every subject that must survive outages; synced = lag 0; commands with TTL | N-6, F-13, R-2, UX-4 | §5.1 |
| **W8-R3** | HA Container as the IoT engine app with declared `hostNetwork` + named device grants (a base-OS extension point); network coordinators in bundles; HAOS-as-VM for full Matter/Thread | AI-7, A-5, A-6, N-1, U-4 | §6 |
| **W8-R4** | Profiles = same image + bundle + config pack + minimal Bakery layers; ship `tak-node` and `greenhouse` first | P-8, F-14, A-7, N-2, M-4 | §8 |
| **W8-R5** | 62443 route: a certified reference box (TPM 2.0, signed A/B), assessed as a host device; start 4-1 process work now; keep CIP/RHEL image mode as the Industrial track (sales option) | F-11, F-12, R-3, H-1, H-3 | §4, §1 |
| **W8-R6** | Zero-touch: OneMind Join QR for consumers (robotics report §4 pattern); go-fdo client package + DPP for industrial; IDevID only on TPM-equipped SKUs | N-4, F-11, F-3 | §1(d) |
| **W8-R7** | Native mesh = batman-adv + 802.11s + WireGuard/Headscale + NATS leaf; Meshtastic and ChirpStack as gateway apps; Reticulum user-installed only | N-6, U-5, F-13, D-001 | §5.2 |
| **W8-R8** | TAK: TAK Server (container) on 16 GB+ nodes, OpenTAKServer on 8 GB Pi nodes; CloudTAK as a separate AGPL app; no GPL/AGPL code in the Apache core | P-8, N-6, D-001 | §7 |
| **W8-R9** | The greenhouse control loop lives on the node; ESPHome `reboot_timeout: 0s` and explicit `restore_mode`; AI writes setpoints only | AI-5, AI-7, P-8, F-13 | §8.3 |
| **W8-R10** | Phone app opts in to constrained satellite networks for alerts and approvals only | UX-5, UX-4, N-6 | §5.2 |
| **W8-R11** | Fleet plane: site clusters + NATS hub-and-spoke + a Rugix-integrated fleet manager (thin-edge.io or Mender OSS first; Nexigon as a commercial option); Flight Control only on the bootc track; prove 10k by simulation | F-11, M-4, R-1, R-3 | §1(e) |
| **W8-R12** | Host VillageOS-style planning apps; own the edge (adapters, bus, profiles) | F-13, F-5 | §9 |

---

## 11. Lab and founder tests (to copy into `22-HARDWARE-LAB-TEST-PLAN.md`)

| ID | Test | Pass criteria | Blocks |
|---|---|---|---|
| LAB-W8-1 | Pi TAK node acceptance (§8.2 tests 1–5) on a Pi 5 16 GB and 8 GB | All five pass; RAM headroom ≥ 20% | P0-8 footprint |
| LAB-W8-2 | NATS leaf outage extended: tc netem 30% loss, 72 h outage, leaf disk full, power cut during write (Pi 5 NVMe) | No loss within the stream limits; a clear error at the limit; no corruption after power loss | P0-5 scope |
| LAB-W8-3 | Sparkplug TCK against the NATS MQTT listener and Mosquitto | The TCK "compliant" (and for NATS "aware") profiles pass | P0-4 |
| LAB-W8-4 | go-fdo client on Debian 13 (x86 + TPM, Pi 5 without TPM): DI → TO0/1/2 against a self-hosted owner | Device enrolls and receives NATS creds and a WireGuard key with no keyboard | G4(d) |
| LAB-W8-5 | 100 simulated sites (k3s + NATS leaf + Rugix agent in VMs) against one hub; a staged OTA wave | Hub CPU/RAM linear; wave completes with health-gated rollback on 5% injected failures | G4(e) |
| LAB-W8-6 | HAOS as a VM on Pi 5 8 GB and x86 under k3s (KubeVirt or QEMU) with a Thread border router | Matter device commissions; Thread OTA works | W8-R3 |
| LAB-W8-7 | Power: idle/load watts for both profiles | Recorded (feeds Q304) | Q304 |
| LAB-W8-8 | Greenhouse acceptance (§8.3 tests 1–5) | All pass | P0-9 |

---

## 12. Open items and assumptions

- **UNVERIFIED:** Sparkplug TCK results for NATS; the scope text of the Moxa and CIP 62443 documents (vendor pages only); the TCG device-identity spec version (search results conflict: v1.1 vs v1.10, so it was not cited as fact); the official T-Mobile app list (403); Pi 5 PREEMPT_RT latency; footprints of both profiles.
- **Assumption (rule 8):** the founder accepts GPL-3.0/AGPL-3.0 TAK components as separate Market apps under the Apache-2.0 core. Listed for `26-OPEN-QUESTIONS-FOR-ZEUS.md`.
- **Founder decision needed:** TAK Server (heavy, the founder's current stack) vs OpenTAKServer (light) as the *default* in the Pi TAK profile. The recommendation is per-RAM-tier (W8-R8). `blocked: founder-decision`.
- **Not re-researched here (owned elsewhere):** CRA classification (W6), Jetson RT and ROS (W7), k3s-vs-Compose on sub-4 GB nodes (W4), the bundle/plugin manifest (W12/W19), and phones and GrapheneOS (W14).

---

## Glossary

- **IIoT (Industrial IoT):** sensors, machines and controllers in factories, farms, utilities and buildings, connected for monitoring and control.
- **OPC UA:** the main industrial standard for reading and writing machine data with a shared information model.
- **MQTT / MQTT 5:** a lightweight publish/subscribe protocol for devices. Version 5 adds features such as shared subscriptions and user properties. NATS speaks only 3.1.1.
- **Sparkplug B:** rules on top of MQTT that say how industrial devices announce themselves ("birth"), report data and signal death. Standardised as ISO/IEC 20237.
- **Modbus / BACnet / CAN:** older field protocols for meters and drives / building automation / vehicles and machinery.
- **PREEMPT_RT:** a Linux kernel mode that makes worst-case delays small and predictable (soft real time).
- **TSN (Time-Sensitive Networking):** Ethernet features for scheduled, deterministic traffic.
- **IEC 62443-4-1 / 4-2:** the industrial security standards for a supplier's development process (4-1) and a component's technical controls (4-2). **SL2** = security level 2.
- **FDO (FIDO Device Onboard):** a protocol that lets a device find and join its owner's system automatically on first power-up, using an "ownership voucher".
- **IDevID (IEEE 802.1AR):** a factory-installed device identity certificate, ideally protected by a TPM.
- **DPP (Wi-Fi Easy Connect):** onboarding a device to Wi-Fi by scanning its QR code.
- **NATS leaf node:** a small NATS server at a site that connects out to a hub and can store messages locally (JetStream) while the link is down.
- **JetStream domain:** a namespace that keeps a leaf's stored streams separate from the hub's.
- **Stream source:** a hub stream that copies messages from another stream (here, from the leaf), resuming after outages.
- **batman-adv / 802.11s:** kernel mesh networking. Boxes relay traffic for each other so a farm needs no cabling between buildings.
- **Meshtastic:** cheap LoRa radios that relay short messages and positions over kilometres without any network.
- **LoRaWAN / ChirpStack:** a long-range, low-power sensor network / its open-source network server.
- **TAK / CoT:** Team Awareness Kit, the map and situational-awareness ecosystem (ATAK, iTAK, WinTAK, TAK Server) / Cursor on Target, its XML/protobuf message format.
- **Profile (P-8):** the same OneMind image plus a bundle of apps and a config pack for one job.
- **Unified Namespace (UNS):** one bus where all plant data is published under a hierarchical naming scheme.

## Sources

All sources are listed in `evidence/sources/W8.md`, with access dates, types and archive links. Code citations are pinned to commit SHAs in `evidence/claims/W8.csv`.
