# IIoT runner-up steelman: an EL10 bootc industrial base (AlmaLinux/CentOS bootc → RHEL image mode / Red Hat Device Edge) instead of Debian + "certified reference box later"

- **Role:** runner-up steelman (RESEARCH-MISSION.md §2 rule 7). This agent was told to argue **for** the strongest IIoT alternative to OneMind's Tier A IIoT approach. It is advocacy held to the evidence rules: every new fact was opened on 2026-11-11 and is in [`../claims/STEEL-iiot-runner-up.csv`](../claims/STEEL-iiot-runner-up.csv) (`C-STEEL-IIOT-001…012`); reused facts cite their existing ledger IDs; anything else is labelled INFERRED or UNVERIFIED. The genuine weaknesses are in §7, stated plainly.
- **Date:** 2026-11-11 · **Re-check by:** 2027-05-11 (packages, releases, kernels) · 2027-11-11 (certifications, lifecycle, subscription terms)
- **Verdict:** `steelman`
- **Decision under test:** `09-iot-mesh-offgrid-tak.md` P0-1/P0-2/P0-3 and W8-R5/R6/R11, as adopted by `01-FOUNDATION-DECISION.md` §1: *Debian 13 + A/B (RAUC) + k3s + NATS is the IIoT foundation; G4 is CONDITIONAL with four mitigations; the Red Hat lineage is a year-2 "Industrial track"/sales option; Flight Control only on that track.*
- **Not a repeat of** [`W2-steelman.md`](W2-steelman.md). That file argued bootc as *the whole base* (Pi 5 to cluster). This file argues the narrower, IIoT-specific case: **for F-11 the Industrial profile should be bootc-first from day 1, and it should be the reference design the Debian consumer image converges toward, not a later add-on.** It reuses W2-steelman facts by ID and adds IIoT evidence W8 did not have.
- **Why this candidate and not Ubuntu Core:** §6 weighs Ubuntu Core honestly (it has a real industrial flagship, Bosch Rexroth ctrlX OS, and a 62443-4-1 process certificate [C-STEEL-IIOT-012]). It loses this slot on F-14 (no Jetson/GPU-cluster path in the same format) and on licence/lock-in (snaps, Canonical-only store and Pro for Devices pricing) [C-W2-006, C-W2-050].
- **Serves requirements:** F-11, F-12, F-14, N-4, M-4, M-7, R-1, R-3, U-4, H-3, F-2

> ### Explain it like I'm the founder
> Our IIoT plan says: "Debian can do industrial, it just needs four things built: a real-time kernel for the Pi 5, a zero-touch onboarding client, an MQTT 5 broker, and a 10,000-device fleet test. Red Hat's line is a sales option for later."
>
> The best case against that plan is simple: **in the Red Hat image-mode line, three of those four things are already shipped, signed packages or upstream projects today, and the fourth (the fleet manager) is built for exactly this OS model.** The free versions (CentOS Stream 10 and AlmaLinux 10, supported to 2035) already carry the zero-touch onboarding client and server as normal packages [C-STEEL-IIOT-001, C-STEEL-IIOT-002]; Debian carries none. They carry a real-time kernel [C-STEEL-IIOT-003]. Flight Control, the open-source fleet manager, gives every device a TPM-backed identity by the industry spec and is released weekly by a team of dozens of Red Hat engineers [C-STEEL-IIOT-005, C-STEEL-IIOT-006]. And it is the only line where the *operating system itself* holds the factory security certificate (IEC 62443-4-2) [C-STEEL-IIOT-008].
>
> The honest catch: the Pi 5 is still experimental on this line, factory protocol libraries like OPC UA aren't packaged for it (they'd ship as containers), and the certified version costs a Red Hat subscription. So the argument is "make the industrial box bootc from the start", not "throw away Debian on the Pi".

---

## 1. The claim this steelman makes

> **For F-11, OneMind's industrial and public-safety SKUs should be built on the EL10 bootc lineage from the first industrial release, with Flight Control as the fleet plane, rather than on Debian 13 + RAUC with four owned mitigations and a certified "reference box" assessed later.** On G4's five sub-checks the EL10 bootc stack is PASS on (a), (b-x86), (c) and (d-on-TPM hardware) with *shipped* artefacts, against Debian's PASS on (a) and (c) only, with (b), (d), (e) CONDITIONAL on OneMind-owned work. It is the one candidate whose IIoT story needs no OneMind-owned onboarding, attestation, health-gate or fleet code, and the one whose paid tier carries a 62443-4-2 certificate on the OS itself.

What it does **not** claim: that DC-02's formal flip condition is met. DC-02 flips only if a sub-check *FAILs* for Debian, and none does (§7.1).

## 2. G4 re-run with evidence W8 did not have

| Sub-check | W8 result for Debian 13 + A/B + k3s | W8 result for CentOS 10 → RHEL 10 image mode | Steelman result for EL10 bootc (new evidence) |
|---|---|---|---|
| (a) Industrial protocols | PASS | PASS (containers) | **PASS.** EPEL 10 packages libmodbus 3.1.12 and mosquitto 2.0.22 (MQTT 5) [C-STEEL-IIOT-004]; Fedora ships open62541 **1.5.8/1.5.10** [C-STEEL-IIOT-004] while Debian trixie's 1.4.11 has 23 open CVEs marked "vulnerable (no DSA)" (W8 IIoT refuter, counter-argument 2). Fedora is the CI canary and the source of an OPC UA container base that is current. *Gap:* open62541 is not in EPEL 10 (§7.3). |
| (b) Real time | CONDITIONAL (Pi 5 has no RT build) | PASS on x86, ARM64 RT Tech Preview | **PASS on x86 in the free tier:** AlmaLinux 10 ships `kernel-rt-6.12.0-211.74.2.el10_2` [C-STEEL-IIOT-003]; CentOS Stream 10 ships `kernel-rt` for x86_64 and aarch64 (NFV) [W2-steelman S-06]. Industrial IPCs are mostly x86. Pi 5: same gap as Debian (§7.2). |
| (c) 62443 path | PASS (Moxa/CIP precedent; OneMind certifies a reference box later) | PASS | **PASS, and the only candidate where the OS itself is certified:** RHEL 9.6 and MicroShift 4.21, SL-C 2, TÜV Rheinland [C-STEEL-IIOT-008, C-W2-042]. The Debian precedents are for Moxa's and CIP's *own* builds; OneMind's Debian image inherits neither (W8 IIoT refuter, counter-argument 3). |
| (d) Zero-touch onboarding | CONDITIONAL (go-fdo unpackaged; Debian packages nothing) | CONDITIONAL ("same", fdo-rs deprecated) | **PASS on TPM-equipped SKUs.** W8's "same" is out of date: CentOS Stream 10 AppStream ships `go-fdo-client 1.0.0-9.el10` and `go-fdo-server 1.0.2` with manufacturer, owner and rendezvous roles, on x86_64 and aarch64 [C-STEEL-IIOT-001]; AlmaLinux 10 ships them too [C-STEEL-IIOT-002]. `tpm2-tools` is in BaseOS [C-STEEL-IIOT-001]. Flight Control enrolls devices with a TPM-held LDevID chained to the EK certificate per TCG device-identity §6.6 [C-STEEL-IIOT-006]. G4-M2 ("package go-fdo-client as a Debian package", ~1 week) is work this lineage has already done, with distro security maintenance attached. |
| (e) Fleet to ~10k | CONDITIONAL (Rugix/RAUC + third-party fleet managers; not shown) | CONDITIONAL | **CONDITIONAL, but with the tooling to prove it built in:** Flight Control ships `devicesimulator`, which runs many real agent processes with Prometheus metrics, and a Helm pre-upgrade scale job [C-STEEL-IIOT-007]. G4-M4's "100 simulated sites" test can be run against the actual production fleet plane, not a stand-in. No 10k result is published (§7.4). |
| **G4** | **CONDITIONAL** (3 owned mitigations + 1 test) | CONDITIONAL | **CONDITIONAL only on (e) and on Pi 5 RT** |

**What changes for OneMind's 180-day plan:** G4-M2 (FDO packaging) disappears; G4-M1 (RT) disappears for x86 industrial SKUs; the health gate that `01` §1 makes OneMind write ("fresh signals only") becomes a greenboot `required.d` script on a shipped framework [C-W2-022, C-W2-054]; the fleet plane, staged rollouts and TPM attestation are one Apache-2.0 project instead of an integration choice among four vendors [C-W8-046, C-W8-048].

## 3. F-11 at fleet scale: who owns the hard code for ten years

| Industrial function | Debian 13 + RAUC (decided) | EL10 bootc (this steelman) |
|---|---|---|
| A/B or image rollback with health gate | RAUC + **OneMind-written** fresh-signal gate [01 §1] | bootc + greenboot, lab-proven rollback with zero manual commands [C-W2-054] |
| OS signing / sealed boot | OneMind release contract, Secure Boot spike X-2R pending [01 §4.3] | cosign-signed OCI images; sealed UKI + composefs digest documented in-tree [W2-steelman S-07] |
| Device identity + attestation | IDevID "only on TPM SKUs", mechanism to build [09 W8-R6] | Flight Control TPM LDevID/LAK per TCG [C-STEEL-IIOT-006] |
| Zero-touch onboarding | go-fdo, to be packaged by OneMind [09 G4-M2] | go-fdo client/server as distro packages [C-STEEL-IIOT-001, 002] |
| Fleet manager | thin-edge.io / Mender OSS / Nexigon, to be integrated [09 W8-R11] | Flight Control (Apache-2.0, v1.4.0 on 2026-11-09) [C-STEEL-IIOT-005]; Red Hat Edge Manager for an SLA |
| Rebase to next major (2030s) | in-place OTA proven by umbrelOS for 12 → 13 [C-W3-039] | `bootc switch` is the normal update verb [C-W3-060, C-W2-024] |
| 62443-4-2 evidence | precedent on third-party builds [C-W8-033, 034] | certificate on RHEL 9.6 / MicroShift 4.21 [C-STEEL-IIOT-008] |

**Bus factor**, which this run used to demote Rugix (303 of 304 commits by one person [C-W3-001]): Flight Control's top eight contributors each have 237–665 commits [C-STEEL-IIOT-005]. bootc is CNCF Sandbox since 2025-01-21 [C-STEEL-IIOT-009]. The FDO concern the IIoT refuter raised (go-fdo's thin human contributor base) is real, but on EL10 the *distro* carries the package and its security errata, which Debian does not.

## 4. F-14 (one OS, Pi to enterprise) seen from the industrial end

An industrial buyer's ladder is gateway → line IPC → site server → plant/OT cluster → vendor cloud. On EL10 bootc every rung uses the **same artefact (an OCI OS image), the same update verb, the same health framework and the same fleet plane**: AlmaLinux/CentOS bootc on IPCs and arm64 gateways, MicroShift (certified, 2 vCPU / 3 GB starter VM [C-STEEL-IIOT-011]) or k3s on the node, RHDE on Jetson Orin [C-W2-041], OpenShift image mode at the cluster [W2-steelman S-11, SECONDARY]. The Debian plan reaches the same ladder with **three update mechanisms** (RAUC on x86/Pi, NVIDIA image OTA on Jetson, something else on GPU servers) under one "release contract" OneMind writes [01 §1 D3]. The steelman's point: F-14 says "the user never switches products"; in the industrial tier, *operations* teams are the users, and one update mechanism is the product they see.

Old industrial x86: RHEL 10 needs x86-64-v3 [C-W2-011], which excludes many Atom-class IPCs. AlmaLinux 10 publishes an `x86_64_v2` tree [C-STEEL-IIOT-003], so the free tier still covers them (whether AlmaLinux publishes v2 *bootc* bases is UNVERIFIED).

## 5. Longevity to 2036, robotics, security, solo-developer operability

- **Longevity:** free tier AlmaLinux 10 to 2035-05-31 [C-W2-013]; RHEL 10 ten years plus ELCP [C-W2-010]; image mode in every RHEL subscription [C-W2-012]. The move to EL11 is `bootc switch`. Debian's 2030–2035 tail (Freexian ELTS) cannot be shared with OneMind's customers [C-W2-004], which matters most to industrial buyers on 10–15-year asset lives.
- **Robotics:** ROS 2 Lyrical rates RHEL 10 Tier 2 (amd64) versus Debian trixie Tier 3 [C-W2-028]. On Jetson, NVIDIA JetPack for RHEL is itself a bootc image (GA, RHEL 9.8) [W2-steelman S-04], so industrial AMRs/inspection robots ride the same fleet plane as their gateways. Hard real time stays on MCUs in both plans [09 §2.3].
- **Security / CRA:** SELinux enforcing with k3s worked first time in the lab [C-W2-052]; composefs read-only root; signed OCI images; TPM attestation [C-STEEL-IIOT-006]. For the CRA (automatic security updates by default [C-W6-008]) a vendor with a published errata stream on the OS is an existing evidence trail.
- **Solo-developer operability:** the OS is a `Containerfile`; build + disk image took about 1–2 minutes each on the founder's class of Mac [C-W2-056]; OneMind's cloud already runs on GHCR + digests + GitOps, so the OS joins the same pipeline. The no-cost Red Hat Developer Subscription covers up to 16 systems including "small production use" [C-STEEL-IIOT-010], enough to build and test the certified tier before the first industrial customer pays for it. Flight Control replaces a fleet backend OneMind would otherwise self-host and integrate.

## 6. The other contender, Ubuntu Core, weighed fairly

Ubuntu Core has the **strongest shipped industrial reference** in this run: Bosch Rexroth's ctrlX OS runs on it, and Canonical holds a TÜV SÜD-audited IEC 62443-4-1 *process* certification (2025-09-18) [C-STEEL-IIOT-012]. Red Hat's page shows 4-2 *component* certificates but no 4-1 [C-STEEL-IIOT-008]. If OneMind's industrial market were PLC/automation vendors only, Ubuntu Core would be the better runner-up. It loses here because (1) everything ships as snaps through a Canonical-controlled store, (2) Pro for Devices pricing is unpublished and modified-Ubuntu redistribution needs Canonical's approval [C-W2-006, C-W2-050], (3) W2 scored it 0 on C4 and 46.0 overall [01 §3.1.2], and (4) it has no Jetson or GPU-cluster member in the same format, so it does not reach F-14.

## 7. Genuine weaknesses (stated plainly)

1. **DC-02 is not flipped.** The protocol requires a Debian sub-check FAIL; every Debian gap here is CONDITIONAL with a costed mitigation [09 §1]. This steelman reduces *owned work and risk*; it does not show a blocking limitation.
2. **Pi 5 is the soft spot.** AlmaLinux's Pi bootc images are labelled experimental and community-run; Fedora IoT's Pi bootc boot bug is open [C-W2-018, W2-steelman S-01]. No vendor Pi 5 RT kernel exists on any lineage [C-W8-040]. The greenhouse/homestead SKUs (F-13) therefore still want Debian or Raspberry Pi OS, so OneMind would run two base families anyway.
3. **Protocol libraries are thinner in EL.** open62541 is not in EPEL 10 [C-STEEL-IIOT-004]; OPC UA, BACnet and Sparkplug ship as containers, so OneMind owns those images' CVEs on either base.
4. **No 10k evidence either.** Flight Control has a simulator but no published 10k run [C-STEEL-IIOT-007]. Fleet scale is unproven on both sides.
5. **The certificate is narrower than it sounds.** It covers RHEL 9.6 / MicroShift 4.21, not RHEL 10, not AlmaLinux, not k3s [C-STEEL-IIOT-008]. OneMind's free-tier image inherits nothing; only a RHEL-based SKU sold under a Red Hat agreement does [C-W2-041]. MicroShift itself needs a subscription in production.
6. **Downstream risk.** AlmaLinux is "binary compatible", not 1:1, since Red Hat's 2023 source change [W2-steelman S-15]; a further Red Hat policy change could hit the free tier.
7. **Two bases for the founder to learn.** A solo founder running Debian for consumer boxes plus EL10 bootc for industrial doubles kernel, CVE and image-pipeline work. This is the strongest practical argument for the decided plan.
8. **Lab coverage:** our bootc lab ran Fedora IoT 45, not AlmaLinux/CentOS 10, and no FDO onboarding was exercised on any base [C-W2-052; 09 LAB-W8-4 pending].

## 8. What evidence would make this the winner

| Test | Pass condition that would flip the IIoT recommendation |
|---|---|
| LAB-W8-4 on both stacks | go-fdo onboarding from distro packages on AlmaLinux 10 bootc + TPM works end to end, while the Debian path needs OneMind-built packages and patches |
| G4-M4 with Flight Control | 1k+ simulated agents with `devicesimulator` against one hub with OS updates staged under a disruption budget, versus no comparable result for a RAUC-integrated fleet manager |
| Pi 5 bootc | AlmaLinux 10 bootc RPI drops "experimental", or Fedora IoT #82 closes, and a ledgered Pi 5 boot/rollback lab run passes (W2-HW-3) |
| Customer signal | A first industrial/public-safety buyer requires a 62443-4-2 *OS* certificate or Red Hat support in the RFP |
| Assessor answer | A 62443-4-2 assessor quotes materially lower cost/time for a RHEL image-mode host device than for a Debian + RAUC one |
| Debian side fails | Pi 5/x86 PREEMPT_RT under k3s load misses latency targets (LAB-W7-1) while kernel-rt on EL10 x86 holds them |

If the first two pass and any one of the rest does, the IIoT recommendation should change from "Debian + reference box; Red Hat as year-2 sales option" to **"Industrial SKUs are EL10 bootc + Flight Control from the first industrial release; Debian stays for consumer/Pi SKUs."**

## 9. Sources opened for this file (2026-11-11)

All new rows are in [`../claims/STEEL-iiot-runner-up.csv`](../claims/STEEL-iiot-runner-up.csv): CentOS Stream 10 compose `CentOS-Stream-10-20261110.0` package listings; AlmaLinux 10 AppStream, RT and BaseOS listings; Fedora mdapi (f43–f45, epel10); `flightctl/flightctl@f99870eafa95003d1511577efc1c6e8c4ce7d5d1` (attestation doc, devicesimulator doc) and its v1.4.0 release and contributors API; `openshift/microshift@564ee6c1baa19f2b2442715ffeda0eeb21cdb0a9` getting-started; access.redhat.com/compliance/iec-62443-4-2; cncf.io/projects/bootc; developers.redhat.com no-cost RHEL FAQ; ubuntu.com/blog/canonical-iec-62443-4-1. Reused IDs come from `W2.csv`, `W3.csv`, `W6.csv`, `W8.csv` and `W2-steelman.md` §5.
