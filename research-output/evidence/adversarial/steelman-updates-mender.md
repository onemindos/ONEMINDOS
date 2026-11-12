# S2 runner-up steelman: Mender as the OneMind update engine

- **Role:** runner-up steelman (RESEARCH-MISSION.md §2 rule 7). This agent was told to argue **for** the runner-up. It is advocacy held to the evidence rules: every fact is primary-sourced and was opened on 2026-11-10, or it is labelled SECONDARY, vendor-stated or UNVERIFIED. §7 states the real weaknesses.
- **Date:** 2026-11-10 · **Re-check by:** 2027-05-10 for versions, boards and repo activity (6 months); 2027-11-10 for LTS policy and pricing (12 months)
- **Verdict:** `steelman`
- **Decision under test:** `01-FOUNDATION-DECISION.md` §3.2 (S2, ADR-001 D3). The corrected score is **RAUC 58.0 vs Mender OSS 57.0**, a tie that was settled for RAUC by three tie-break points (DC-09 Jetson base, cost of deltas, proof).
- **Serves requirements:** F-11, F-14, F-1, M-6, M-7, R-1, R-3, H-1, RS-2, D-001, D-002
- **Ledger:** `evidence/claims/STEEL-updates-mender.csv` (C-STEEL-updates-mender-001 … 025)

> ### Explain it like I'm the founder
> An update engine has two halves. One half lives **on the box**: it writes the new OS into the spare slot, reboots and rolls back if the new version fails. The other half lives **on a server**: it knows which boxes exist, what each one runs, and who gets which update and when.
> RAUC is an excellent **box half** and nothing more. Mender is **both halves**, and both are Apache-2.0, the same license as OneMind (D-001). It is maintained by a company that has been in business since 2008. It also updates the **small chips** around a computer (ESP32 and Zephyr microcontrollers), which is what a greenhouse, a factory line or a robot is full of.
> Our own IoT research (W8) already plans to put **Mender's server** in front of whatever engine we choose. If we will run Mender's server anyway, using Mender's own client removes a seam we would otherwise build and maintain alone.
> The catch, covered in §7, is real. Mender keeps delta updates, staged rollouts, RBAC, mTLS and multi-component updates in its **paid** tiers. Our lab has not run it yet, and its Jetson path on NVIDIA's stock Ubuntu is a community recipe, not a product.

---

## 1. The claim this steelman makes

> **Mender OSS (client 5.2 / Mender Client 6.1 LTS, Server 4.1 LTS, mender-mcu 1.1) is the better ten-year update engine for OneMind. It is the only candidate that covers the whole OneMind device range, from the microcontroller to the Jetson, with one Apache-2.0 artifact format and one self-hostable fleet server. Applied consistently, the frozen anchors score it 62.0 against RAUC's 58.0, outside the 3-point tie band. Two of the three tie-break points that chose RAUC do not survive the primary evidence.**

## 2. The scorecard, re-read with one evidence standard (weights rule 6)

The frozen weights require "the same evidence for every candidate" (`scorecard-weights.md` §5 rule 6). Two Mender cells look scored to a stricter reading than RAUC's.

| Cell | Scored | Argued | Why (anchor text quoted from `scorecard-weights.md` §4) |
|---|---|---|---|
| **C6 Cost and licensing** | 3 | **4** | Anchor 4 reads: "Free for all units, permissive or weak-copyleft licenses, and clear redistribution rights." Mender's client and server are both Apache-2.0 [C-W3-055, C-STEEL-updates-mender-001]. Self-hosted, Mender OSS costs $0 per unit at any fleet size [C-STEEL-updates-mender-015]. RAUC (LGPL-2.1) received 4 under the same anchor. The commercial delta feature is a **missing feature**, not a per-unit cost on Mender OSS. Anchor 4 says nothing about feature completeness, so the paywall belongs under C3 or C7, not C6. Docking it in C6 *and* using it again as a tie-break counts it twice. |
| **C4 Proven in production** | 2 | **3** | Anchor 3 reads: "…**or** one product whose constraints match OneMind's (an appliance, a solo or small team, consumer hardware)." umbrelOS, the closest constraint-matched competitor, shipped on Mender. Its current code still builds a separate `umbrelos-mender-amd64` image for "legacy Mender-provisioned" devices, with Mender's partition numbering and `mender-grub` boot flow [C-W3-040]. That is code confirmation, at a pinned SHA, of a shipping consumer appliance on Mender. The anchor does not say "currently". Vendor-named robotics and agriculture users (Agrointelli's ROBOTTI, DotRobot) are SECONDARY and are **not** counted [C-STEEL-updates-mender-019, -020]. |
| C1, C2, C3, C5, C7 | 3 each | 3 each | No change argued. C7 → 4 was considered (Update Modules give a plugin model, and the open-source server has AWS IoT Core and Azure IoT Hub integrations [C-STEEL-updates-mender-016]). The "vendors certify against it" evidence (an NVIDIA Jetson Platform Services integration) is only a vendor announcement [C-STEEL-updates-mender-018]. SECONDARY caps the cell at 3. |

**Re-computed:** Mender = (3·20 + 3·20 + 3·15 + **3**·15 + 3·10 + **4**·10 + 3·10) / 5 = **62.0**. RAUC stays at its corrected **58.0**. The margin is 4.0, which is **not a tie**, so the tie-break never runs.

Even with only one of the two corrections, Mender reaches 59.0 (C6 alone) or 60.0 (C4 alone). That is a tie in which Mender leads, and the tie-break goes to §3.

## 3. The tie-break, re-examined point by point

| Tie-break point (§3.2) | What it said | What the primary evidence shows | Result |
|---|---|---|---|
| **DC-09 Jetson base** | "Mender's Jetson advantage exists only in a Yocto/meta-tegra rebuild [C-W3-053], so it does not apply to the chosen Jetson flavor. → RAUC." | On **stock L4T**, neither engine is native. The chosen design wraps NVIDIA's own rootfs A/B and image-based OTA (04 §5.3). Mender has a **published wrapper** for exactly that: a Mender Hub tutorial (2024-07-03) uses NVIDIA's `l4t_generate_ota_package.sh` on the stock sample rootfs. Its Update Module reports `SupportsRollback: Yes` and calls `nvbootctrl set-active-boot-slot` on rollback, and it was tested on AGX Orin and Orin Nano at JetPack 5.1.2 (R35.4.1) and 6.x (R36.3.0) [C-STEEL-updates-mender-012]. Northern.tech also states official support for "all NVIDIA Jetson … SOM[s] that support the official L4T (Ubuntu) operating system, running JetPack 4.6 or later" [C-STEEL-updates-mender-013, vendor-stated]. RAUC's community Tegra layer was **removed** in 2024 [C-W3-021], and there is no RAUC wrapper to start from. | **Neutral at worst, Mender at best.** It does not favour RAUC. |
| **Cost (C6)** | "Mender's delta updates are commercial; RAUC's adaptive updates are open source. → RAUC." | True and conceded (§7). But it is already priced into the score (§2), so it should not decide the tie a second time. The cheapest Mender tier with deltas is Professional at **$291/month for up to 250 devices**, hosted [C-STEEL-updates-mender-015]. That is about $14 per device per year at full use. | Favours RAUC, but it is double-counted. |
| **Proof** | "RAUC … passed every pre-registered test in our lab …; Mender has no current constraint-matched appliance (Umbrel left it). → RAUC." | The lab asymmetry exists because **Mender was never run**, not because it failed. "Umbrel left it" is the only reason given, and Umbrel's reason for leaving is listed as an **open, UNVERIFIED item** in 04 §17. Umbrel still keeps Mender-provisioned boxes updating through a Mender-compatible layout [C-W3-040]. | Favours RAUC **until a Mender lab spike runs** (§8). |

## 4. Strongest arguments

### 4.1 One engine, one artifact format, one fleet server: microcontroller to Jetson (F-11, F-14, D-002)

| Fact | Evidence |
|---|---|
| Mender defines three **device tiers** on one server: **Micro** (`mender-mcu` on Zephyr), **Standard** (embedded Linux, A/B OS updates) and **System** (Mender Orchestrator coordinating several components). | mender-docs `02.Overview/17.Device-tiers` @12a68d0 [C-STEEL-updates-mender-005] |
| `mender-mcu` is Apache-2.0, a Zephyr module (Zephyr 4.4 supported) using MCUboot A/B. Its reference board is the ESP32-S3. It had 131 commits from 14 human authors in the last 12 months. Version 1.1 was released 2026-09-02. | mender-mcu README @b186934; Supported releases @12a68d0; GitHub API [C-STEEL-updates-mender-006, -007] |
| **Mender Orchestrator 1.0 (2026-10)** updates "a collection of interdependent Components", reached over CAN bus, I²C, MQTT or anything else an Interface can speak. It works from a Topology plus a Manifest, and "if any Component fails, it rolls back the entire System". The docs give "a drone with onboard sensors, GPS, a flight control computer" as a target, with worked examples that update an ESP32-S3 from a Pi and a Pi from a Pi over MQTT. | mender-docs `07.Orchestrate-updates/01.Overview` @12a68d0 [C-STEEL-updates-mender-008] |
| OneMind's own IIoT plan (W8-R11) already names **"thin-edge.io or Mender OSS first"** as the fleet manager driving the update engine, and G4-M4 schedules a Mender OSS fleet test. | `09-iot-mesh-offgrid-tak.md` lines 61, 276 |

**Why it matters:** F-11 says greenhouses, farms and factories are full of microcontrollers and PLC-adjacent boards. F-14 says "the user never switches products." RAUC updates the Linux box and nothing else. Mender's Micro and System tiers put the ESP32 sensor node, the Pi controller and the Jetson robot under one release, with one signing step and one fleet view. OneMind would otherwise build that orchestration layer itself, as a solo developer.

### 4.2 A self-hostable fleet server under OneMind's own license (F-11 fleets, D-001, sovereignty)

| Fact | Evidence |
|---|---|
| `mender-server` monorepo: "All content in this project is licensed under the Apache License v2, unless indicated otherwise". It contains 9 backend services (deployments, deviceauth, deviceconfig, deviceconnect, inventory, iot-manager, useradm, workflows, create-artifact-worker). Production is installed with a Helm chart. | mender-server @593fff5 LICENSE, README, `backend/services` [C-STEEL-updates-mender-001, -002] |
| The server's evaluation composition runs **NATS 2.15 JetStream** plus MongoDB and Traefik, so it uses the same bus technology as OneMind. | mender-server `docker-compose.yml` @593fff5 [C-STEEL-updates-mender-003] |
| The server had **3,044 commits from 22 human authors** in the last 12 months. | GitHub API [C-STEEL-updates-mender-004] |
| The AWS IoT Core and Azure IoT Hub integrations are "available in all Mender plans, as well as Mender Open Source". | mender-docs `10.Server-integration/05,06` @12a68d0 [C-STEEL-updates-mender-016] |
| "So far, Mender Server supports all Device API versions ever released … a current Mender Server will still work with Mender Client v1.0." | Supported releases @12a68d0 [C-STEEL-updates-mender-010] |

RAUC has no server. A RAUC fleet needs hawkBit or a home-grown service, plus an adapter. For a 2036 horizon, a server that has never broken a fielded client in ten years is an unusually strong longevity signal.

### 4.3 Longevity and support policy (C1, R-3, to 2036)

- **Published LTS table:** Mender Client 6.1 (2026-10) supported, 6.0 to 2027-04; Server 4.1 (2026-01) supported; Gateway, MCU and Orchestrator each on an LTS. "When a new LTS version is released … the previous LTS version is supported for at least 6 months" [C-STEEL-updates-mender-009]. RAUC's security or support policy was **not read** in 04 §5.2.
- **Distribution policy:** client `.deb` packages support "the two latest LTS releases for both Debian and Ubuntu" (today Trixie, Bookworm, Resolute and Noble). meta-mender supports the two latest Yocto LTS releases [C-STEEL-updates-mender-011]. This means a Debian 13 → 14 → 15 rebase path (DC-05) always has a supported Mender package on both sides.
- **Backing:** Northern.tech was founded in 2008 (vendor-stated, SECONDARY) [C-STEEL-updates-mender-019]. The client repo was created 2015-12-07 (GitHub API), so it has 11 years of continuous releases. Its contributor base is multi-author in every component: client 18, server 22, meta-mender 20, mender-convert 12, mender-mcu 14 human authors in the last 12 months [C-W3-069, C-STEEL-updates-mender-004, -007].

### 4.4 Security model (C3, R-1, W6)

| Property | Mender evidence |
|---|---|
| Device identity | Each device has a unique key pair; Ed25519 by default since client 4.1. Keys can be pre-provisioned offline [C-STEEL-updates-mender-021] |
| HSM / TPM-class keys | Device auth key loads from a **PKCS#11 URI** through OpenSSL engine/provider [C-STEEL-updates-mender-022] |
| Artifact signing | RSA ≥3072 or ECDSA P-256. **Multiple verify keys** (`ArtifactVerifyKeys`) "useful for rotating keys". With verification on, unsigned artifacts are rejected. Signing works through PKCS#11 HSMs, HashiCorp Vault, GCP KMS, Azure Key Vault and Keyfactor SignServer [C-STEEL-updates-mender-023] |
| Attack surface | "No open ports on the Device": the client initiates every connection [C-STEEL-updates-mender-021] |
| Power loss | Documented per state: power loss leads to `ArtifactRollback` or `ArtifactFailure`, and error states repeat until they finish [C-STEEL-updates-mender-024] |
| Health gate | `ArtifactCommit_Enter` state scripts can fail the commit, which triggers rollback; exit code 21 means "retry later", so a k3s gate can wait for pods [C-STEEL-updates-mender-024] |
| Secure Boot (x86) | `mender-convert` supports UEFI Secure Boot with shim and signed GRUB, using vendor or custom keys [C-STEEL-updates-mender-014] |

That meets C3 anchor 3 on documentation, the same score as corrected RAUC.

### 4.5 Board coverage of the update path (C2, M-7)

- **x86 and Pi 5 on Debian trixie** come straight from `mender-convert` 5.3.0 configs (`generic_x86-64_hdd_config`, `raspberrypi5_trixie_64bit_config`, plus a Pi 5 "performance" variant) at @7aee704 [C-W3-054, C-STEEL-updates-mender-017]. `mender-convert` converts an **existing** Debian image, so OneMind's Debian 13 pipeline is preserved rather than replaced.
- **Jetson:** two routes. On Yocto, `meta-mender-tegra` covers Thor, AGX Orin, Orin Nano and Orin NX on L4T 39.2 [C-W3-053]. On stock L4T, the community Update Module wraps NVIDIA's OTA (§3).
- **Beyond Linux:** Zephyr MCUs (§4.1). The client README also documents a **QNX 8** build of `mender-update`, which matters for safety-certified robot subsystems [C-STEEL-updates-mender-025].

### 4.6 Robotics

Mender's Orchestrator is designed for the multi-ECU shape of a robot or drone: a companion computer, a flight controller, motor drivers and sensors, all updated and rolled back as one versioned system (§4.1). Vendor-named robotics users are Agrointelli (autonomous farm robot ROBOTTI) and DotRobot. Both are vendor-stated and do not count toward C4 [C-STEEL-updates-mender-019, -020]. RAUC has no equivalent component model. OneMind would have to write one for the Robotics tier.

### 4.7 Solo-developer operability (C5, M-6, F-8)

- No custom image builder is needed. `mender-convert` post-processes the Debian image OneMind already builds, and the docs give CI recipes for GitHub Actions, GitLab and Azure DevOps (`08.Artifact-creation/12.CI-CD`).
- The workstation tools `mender-artifact` and `mender-cli` ship for macOS via Homebrew [C-STEEL-updates-mender-011], which fits the Mac dev path (D-004, F-9).
- **Hosted option:** a founder who does not want to run a server can start on hosted Mender (Basic, $34/month for up to 50 devices), then move to self-hosted OSS [C-STEEL-updates-mender-015].
- On-device control has a D-Bus API, as RAUC does.

## 5. What the RAUC choice gives up (seen from Mender's side)

1. **A second integration seam.** W8 plans Mender OSS (or thin-edge.io) as the fleet plane. RAUC + Mender server means writing and maintaining a RAUC Update Module, with two state machines (RAUC's and Mender's) racing over commit and rollback.
2. **The microcontroller and multi-component story** for F-11 and robotics would have to be built in-house.
3. **A fleet server under Apache-2.0** with ten years of backward device-API compatibility.

## 6. Steelman summary table

| Criterion / requirement | Mender case | Strength |
|---|---|---|
| F-11 IoT/IIoT | Micro tier (Zephyr/MCUboot), Orchestrator over CAN/I²C/MQTT, AWS/Azure IoT in OSS | Strong (but Orchestrator is paid, §7) |
| F-14 Pi → enterprise | One server from 1 device (hosted Basic) to self-hosted Helm on Kubernetes | Strong |
| Longevity to 2036 | Published LTS policy; 11 years of releases; device API never broken; multi-author | Medium–strong |
| Robotics | Orchestrator's system model; Jetson on Yocto (maintained) or stock L4T (community); QNX | Medium |
| Security | PKCS#11 HSM keys, KMS signing, key rotation, no open ports, power-loss semantics | Medium (no revocation, §7) |
| Solo operability | mender-convert keeps the Debian pipeline; macOS tools; hosted start | Medium |

## 7. Genuine weaknesses (stated as hard as the evidence allows)

1. **Open core bites exactly where F-11 lives.** In Mender OSS there are **no** delta updates, phased rollouts, dynamic groups, RBAC, audit logs, mTLS, Mender Gateway (site caching and mTLS) or Orchestrator. Deltas start at Professional. Server-side delta generation, phased rollouts, RBAC, mTLS, Gateway and Orchestrator are Enterprise only, at custom prices [C-STEEL-updates-mender-015]. The strongest F-11 arguments in §4.1 (Orchestrator) and the fleet-scale ones (phased rollouts, RBAC) are **paid**. RAUC's adaptive deltas are free [C-W3-019]. For a 64 kbps, 10%-loss off-grid link (T-W3-05), the lack of a free delta is a real product gap.
2. **No revocation and no signing-time validation.** Mender verifies against a set of public keys. There is nothing like RAUC's CRL, signer allow-list or signing-time checks [C-W3-018]. Rotation exists through multiple keys; revocation means shipping a new key list in an update.
3. **No verity bundles or read-only verified root out of the box.** The Secure Boot docs themselves say Secure Boot "does not provide filesystem integrity" and point to dm-verity [C-STEEL-updates-mender-014]. mender-convert's Secure Boot route is **x86 UEFI only**.
4. **The ARM `apt upgrade` hazard.** The Debian docs warn that on non-x86, running `apt upgrade` on a Mender device "may brick your device" [C-STEEL-updates-mender-014]. For an image-based OS this is a discipline rule, not a blocker, but it must be enforced on the Pi tier.
5. **The Pi 5 path goes through U-Boot**, not Raspberry Pi's native `tryboot` that HAOS uses [C-W3-029]. The robustness of Pi 5 U-Boot under EEPROM updates is UNVERIFIED here.
6. **The stock-L4T Jetson path is a community recipe.** The newest report (2025-08-08, L4T 36.4.3) describes a deployment stuck at "rebooting" with no reply. A 2025-11-02 report of `/data` loss on reflash also went unanswered [C-STEEL-updates-mender-012]. The official claim covers JetPack ≥4.6 but names only Xavier/TX2-era modules [C-STEEL-updates-mender-013].
7. **The server is heavy to self-host.** It runs 11+ containers, plus MongoDB, NATS, Traefik and S3 storage [C-STEEL-updates-mender-003]. MongoDB 5+ is SSPL. Self-hosting is fine, but OneMind could not offer a hosted "OneMind Cloud" with it embedded without counsel review (UNVERIFIED legal reading). Mender Server 4.0 support ended 2026-10, which shows the LTS treadmill [C-STEEL-updates-mender-009].
8. **Single-vendor governance.** Northern.tech decides the open/paid line and has moved features to paid tiers before (UNVERIFIED in this pass). No foundation backs it. RAUC is also mostly one company (Pengutronix, unverified in 04).
9. **No lab result.** RAUC passed every pre-registered test on Debian 13 x86 [C-LAB-rauc-013…018]. Mender has none. Under the frozen rules this keeps Mender's C3 and C5 at documentation level.
10. **The best counter-design is a hybrid.** RAUC on the box, driven by the Mender OSS server through a custom Update Module. It keeps RAUC's free deltas and CRLs and borrows Mender's fleet plane. It does not give MCU or Orchestrator coverage, but it weakens the "use both halves" argument in §5.

## 8. What evidence would make Mender the winner

| # | Evidence | How to get it | Effect |
|---|---|---|---|
| E1 | The scorecard owner accepts the consistency corrections C6 3→4 and C4 2→3 (§2) | Refuter review of this file against `scorecard-weights.md` §4 and §5 rule 6 | Mender 62.0 vs RAUC 58.0: **outright win**, no tie-break |
| E2 | A Mender lab spike matching RAUC's pre-registered tests: mender-convert of the Debian 13 image on x86 (QEMU) and arm64, k3s health gate in `ArtifactCommit_Enter`, forced rollback, power cut mid-write | `evidence/lab/mender/`, same test IDs as `LAB-rauc` | Removes the "Proof" tie-break point |
| E3 | Stock-L4T Jetson Orin Nano at L4T 36.x/39.x: the Mender Update Module wrapping NVIDIA OTA passes install, rollback and the commit gate unattended | Fold into founder-hardware test T-W3-06 | Moves DC-09 to Mender: one fleet server covers all three board families |
| E4 | A written quote for Professional or Enterprise (deltas, phased rollouts, Orchestrator) at OneMind volumes within H-1 margins, **or** an open-source delta path for Mender (for example a community delta Update Module) measured on the T-W3-05 low-bandwidth link | Sales quote; lab | Neutralises the cost tie-break |
| E5 | The fleet-plane decision (W8-R11 / G4-M4) picks Mender OSS server | The W8 fleet test | Makes the RAUC-under-Mender hybrid the only alternative and raises the cost of the seam |
| E6 | A primary-confirmed second shipping product on Mender (an appliance, robot or industrial product, from code or official docs) | Teardown | C4 rises to 3 without relying on Umbrel's legacy path; with failure-report review, toward 4 |

**What would sink this steelman:** E2 or E3 failing; Northern.tech moving rollback, signing or the server to a non-Apache license; or the CRA work (W6) needing revocation that Mender cannot provide.
