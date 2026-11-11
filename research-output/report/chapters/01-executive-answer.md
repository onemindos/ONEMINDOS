# The executive answer {#sec-answer}

> **Explain it like I'm the founder.** You asked one question: *what should OneMind OS stand on for the next ten years, and how do we get there?* The short answer is: **build your own read-only operating-system image, keep two copies of it on every box so a bad update rolls itself back, run small Kubernetes (k3s) on every real box, wire everything together with NATS, and put one "capability gateway" in front of every app, device and AI agent.** That is what ADR-001 proposed, and after four rounds of attack that shape still stands. **One thing under it changed in revision 4: the base.** Under the contest rules we locked before scoring, **Ubuntu 26.04 LTS** narrowly beats Red Hat's bootc and Debian 13 (65, 64 and 63 points), but only if Canonical allows OneMind to ship a modified Ubuntu, or OneMind strips the brand and rebuilds it (Z-01). Revision 3 had kept Debian with a tie-break rule written after the scores were known; that rule is withdrawn [C-PROTO4-018]. Until the base is locked, one recipe builds both an Ubuntu and a Debian version. What else changed is detail: the update engine (RAUC instead of Rugix), how "healthy" is checked, how backups work on a single box, which boxes run full Kubernetes, and when Secure Boot arrives. The base and the update engine (RAUC over Mender) both won narrowly, so each has a written, testable way to the runner-up, and for the base the result of each pending answer was written down in advance. Revision 4.1 changed no score: three new attackers who saw only the one-line decision all called it *weakened*, none *wrong*, and the industrial-IoT gate passes with conditions. The one pending test that needs no hardware, Ubuntu's own Secure Boot test, could not run here (Ubuntu's servers are blocked from the research computer), so it is yours to run on day 1 (LT-VM-20). Nearly everything was proven in virtual machines on a Mac; the first 180 days prove it on your real hardware.

**How to read this report.** Every factual sentence carries a claim ID in square brackets, for example [C-W2-001]. Each ID is a row in the research ledger (`research-output/evidence/claims/*.csv`) with its source URL, access date and re-check date; [Appendix C](#sec-claims) lists the source of every ID cited here. Sentences without an ID are recommendations or reasoning, and they name the research file that argues them. Requirement IDs (for example F-14, R-1) come from `docs/REQUIREMENTS.md`. Nothing here is legal advice.

## The answer, one layer at a time {#sec-answer-table}

| Layer | Decision | vs ADR-001 | Confidence |
|---|---|---|---|
| **Base OS** | **Ubuntu 26.04 LTS** core image + RAUC for x86, generic arm64 and Pi 5 (the frozen-protocol result), **conditional on Canonical's permission or a debranded rebuild (Z-01)**; a **Debian 13** version is built from the same recipe until the base is locked before the first box ships; **NVIDIA's L4T Ubuntu 24.04** for Jetson; Ubuntu LTS for GPU servers; **AlmaLinux 10 or RHEL 10 image mode** as a year-2 Industrial profile, CentOS Stream and Fedora IoT as CI canaries. Written in advance: bootc fails on a real Pi 5 → Debian; Canonical refuses → bootc; Ubuntu fails its own Secure Boot test (U-SB, attempted and blocked here; you run it as LT-VM-20) → bootc | **Changed (conditional)** | **Low** (a tie in all 14 weight runs; Ubuntu wins 11, Debian 2, bootc 1) |
| **Image** | OneMind owns the image: one container-style build definition with an Ubuntu 26.04 leg and a Debian 13 leg, turned into A/B disk images; a distro base (not built from source) because of NVIDIA's CUDA path and one-person upkeep | Confirmed | High |
| **Updates** | **RAUC** A/B with verity bundles on x86 and Pi 5, built by OneMind from a pinned upstream tag; NVIDIA's own A/B on Jetson; one release contract; **Mender** is the named runner-up | Changed (engine) | Medium-low |
| **Health gate** | Commit an update only on **fresh** signals from *this* boot; apps excluded; 3 boot tries where the boot path allows; never auto-retry a bad release; shown safe for **one box on SQLite**; cluster rollback still untested | Confirmed, made concrete | **High** (single box) |
| **Kubernetes** | **k3s** on every box with ≥ 4 GB RAM and an SSD; robots and field kits run the k3s *agent* only; smaller devices are **NATS leaf** nodes; RKE2 only when a buyer needs FIPS/STIG | Changed | Medium |
| **Backups** | **restic** with three keys; online SQLite backup of k3s on a single box; automatic verified restores | Changed (method) | High |
| **Security** | Disk layout for Secure Boot and encryption fixed on day 1; encrypted data from first boot; signed releases; human approval in the gateway for anything physical | Changed (timing) | Medium |
| **Plugins** | Ten extension points (E1–E10) in release 1, signed-only | New | Medium |

Source: `01-FOUNDATION-DECISION.md` §1, §3.1.6 and §7 (revision 4.1; no score or ranking change from revision 4). Key evidence: the rev-4 scorecard and its 14 weight runs [C-DEC4-001, C-DEC4-006], Canonical's redistribution rule [C-W2-050], the Ubuntu 26.04 lab leg [C-LAB-ubuntu-2604-leg-011], the health-gate lab [C-LAB-rauc-k3s-gate-008], the k3s footprint [C-LAB-k3s-footprint-restore-007] and the single-box restore [C-LAB-k3s-footprint-restore-011].

![ADR-001's shape survived four rounds of attack; the base under it is now Ubuntu 26.04, conditionally. The diagram shows the whole system that results; Chapter 6 explains each layer.](img/architecture.png){width=100%}

## Ten findings that matter most {#sec-findings}

1. **The three bases are within 2 points, and the locked rules pick Ubuntu.** The rev-4 card is Ubuntu 65, bootc 64, Debian 63 [C-DEC4-001]. The frozen rule calls a gap under 3 points between the **top two** a tie, so only Ubuntu and bootc go to the tie-break; Debian, third, is not a finalist even though it is within 3 points of the leader. On the decision-critical evidence Ubuntu beats bootc **6–4** [C-DEC4-006]. Revision 3 had brought Debian in as a third finalist after the scores were known; that rule is withdrawn [C-PROTO4-018]. The result is fragile: Ubuntu wins 11 of 14 weight runs, Debian 2 and bootc 1 (`01` §3.1.6).
2. **Ubuntu's win needs Canonical's say-so.** A modified Ubuntu may be shipped only with Canonical's approval, or with the trademarks removed and the binaries recompiled [C-W2-050]. That includes the Jetson flavor on every base, because NVIDIA's Jetson root filesystem is Ubuntu [C-REF-DC-cost-007 (SECONDARY: NVIDIA staff on forum)]. Debian's core has no such condition [C-W2-043]. So we wrote down in advance what each answer means: Canonical refuses and you reject the debranded rebuild → bootc; bootc fails on a real Pi 5 (W2-HW-3) → Debian; both → your decision; Canonical agrees with a price → Ubuntu outright; Ubuntu fails its own Secure Boot test (U-SB) → bootc (`01` §3.1.6 h). U-SB was attempted on 2026-11-11 and is **blocked**, not failed: Ubuntu's servers do not resolve from the research environment [C-FIX5-001], so it is a founder-run test, LT-VM-20 (Chapter 4).
3. **"Healthy" must mean healthy now.** After an update, Kubernetes shows the *previous* boot's "all good" status. A naive check committed a broken update with Rugix [C-LAB-debian-rugix-023] and again with RAUC and real k3s [C-LAB-rauc-k3s-gate-008]; the fresh-signal gate caught every one.
4. **Nobody ships exactly our combination.** A targeted search found no field-proven product running Debian or Ubuntu with RAUC [C-DEC-013 (UNVERIFIED: negative search)]; the closest, IronFlockOS (Debian 13 + RAUC + Docker), is pre-1.0 [C-CIT4-001]. Each piece is proven somewhere (Debian in umbrelOS, RAUC in Home Assistant OS, k3s in Olares), so our labs and your hardware tests are the proof of the whole.
5. **Debian's own RAUC is too old for newer kernels.** RAUC 1.13 cannot install any update on Linux 6.19 or later [C-LAB-ubuntu-2604-leg-010], while upstream 1.15.2 passed every test [C-LAB-rauc-1152-011]. So OneMind builds its own RAUC, as Home Assistant does.
6. **Secure Boot works with our layout, but it does not stop downgrades.** Signed per-slot kernels, TPM-unlocked data and rollback all passed in emulation [C-LAB-secureboot-rauc-013], and again on RAUC 1.15.2 [C-LAB-secureboot-1152-005], but an *old* signed kernel still boots against a newer root [C-LAB-secureboot-1152-009]. OneMind adds an anti-downgrade rule.
7. **The plugin sockets must be locked.** systemd's extension feature accepts unsigned add-ons by default [C-REF-W19-security-004]; OneMind switches that off before any third party plugs in.
8. **NVIDIA's Jetson software ends before its hardware does.** JetPack 4 ended 26–32 months before Nano and TX2 NX stopped shipping [C-REF-W7-T-001], and JetPack 5 ended on 2026-10-30 [C-REF-W7L-001].
9. **Robotics simulation lives on Ubuntu.** Isaac Sim lists Ubuntu and Windows hosts only [C-REF-DC-robotics-013], and NVIDIA's DKMS driver broke on routine Debian kernels [C-REF-DC-cost-009]. This is part of why Ubuntu scores highest on ecosystem.
10. **The EU Cyber Resilience Act applies from 2027-12-11** [C-W6-001] and expects security updates to install automatically by default [C-W6-008]. That collides with "never auto-install" and is your call (Z-02).

## "Pi greenhouse → enterprise robotics simulation": one OS at every scale (F-14) {#sec-walkthrough}

You asked for an OS *"as simple as using a Raspberry Pi, up to full enterprise"*. Here is the same OneMind OS growing from one Pi in a greenhouse to a robotics-simulation cluster, step by step, with what stays the same and what changes.

![The six steps. The yellow box is the promise: these parts never change as you grow.](img/scale.png){width=100%}

**Step 1: the greenhouse Pi.** Buy a Pi 5 with 8 GB and an NVMe drive (the Edge size; production of the Pi 5 and CM5 is committed to at least January 2036 [C-W10-035]). Flash the OneMind image, scan the QR code on first boot and pick the `greenhouse` profile. You get Home Assistant, a small MQTT broker and ESPHome sensor boards, on a single-box k3s server (k3s adds about 936 MiB at idle on a 4 GiB arm64 box [C-LAB-k3s-footprint-restore-007]). The important design rule: **the climate loop runs on the ESP32 board, not on the Pi**, so a crashed Pi never cooks the plants. ESPHome's defaults are unsafe for this (a node reboots after 15 minutes without a client, and relays default to OFF at boot), so the profile overrides both [C-W8-029, C-W8-030]. The AI may suggest set-points; opening a valve needs your approval on the phone. Updates use RAUC's Pi 5 "tryboot" path, and backups go to restic.

**Step 2: the homestead.** Add a Lite x86 mini PC. Scan its QR code and it joins the same cluster. The NATS bus now spans both boxes; each box backs the other up. A single box keeps k3s's simple SQLite database, and when a third server joins, one restart with `--cluster-init` moved all records to etcd in our lab [C-W5-005].

**Step 3: the robot bench.** Plug in a Jetson Orin robot. It runs the **k3s agent only**, never the part that holds every password, because a robot can be stolen [C-REF-W4-security-008]. The box recognises it, offers a signed adapter, starts it in *observe-only*, and lets AI move it only with your approval (Chapter 9).

**Step 4: private AI.** Add a Pro box with an NVIDIA RTX card (≥ 16 GB VRAM). The capability detector labels it "Private AI"; the Market places language and vision models there; the Hermes agent gets a body on the box. The same app manifest says what each app needs, and the dashboard answers "runs here / runs on another of your machines".

**Step 5: robotics simulation.** Add an Omni GPU workstation. This is the one place the OS family changes: Isaac Sim supports Ubuntu and Windows hosts only [C-REF-DC-robotics-013], so simulation boxes run the **Ubuntu GPU-server flavor** (gated on Canonical's answer, Z-01) with k3s or RKE2. It still uses the same Market, the same manifest format, the same gateway and the same NATS subjects.

**Step 6: enterprise and many sites.** Ten thousand devices are many site clusters joined by NATS, not one giant cluster: k3s documents 16-CPU/32 GB servers for about 1,800 agents [C-W8-049]. Industrial customers can pick the bootc profile on the Red Hat lineage, which holds IEC 62443-4-2 at security level 2 on RHEL 9.6 [C-W2-042]. The regulated tier can run RKE2 for FIPS.

**The honest caveat.** "One OS" means **one app platform, one release contract and one user experience**, not literally one disk image. There are three image families (the core image on Ubuntu 26.04 or Debian 13, NVIDIA's Jetson Ubuntu, the Ubuntu GPU-server flavor), because NVIDIA rules its hardware. The research scored "one OS from Pi to cluster" as *conditional* for every candidate base, a tie (`01` §3.1.6, DC-17). What makes the promise real is that the parts you touch never change.

| What stays the same at every scale | What changes as you grow |
|---|---|
| `onemind.app.yaml` app format and the Market | Hardware size, and the image flavor on Jetson and GPU boxes |
| The capability gateway, approvals and audit | k3s role (single server → cluster → agent-only robots) |
| NATS subject grammar and leaf links | Datastore (SQLite → etcd at three servers) |
| Signed A/B release contract and health gate | Optional RKE2 for FIPS; optional bootc Industrial profile |
| restic backups with a recovery key | Storage (local disk → Longhorn on 3+ nodes) |
| Dashboard, alerts, identity | Number of sites and the optional cloud hub |

## What competitors do at both ends of the scale {#sec-answer-competitors}

| Product | Smallest box | Largest deployment | Same OS both ends? | Constraint fit with OneMind |
|---|---|---|---|---|
| Home Assistant OS | Pi / HA Green, Buildroot image [C-TD-home-assistant-os-003] | One home server | Yes, but no cluster, no Kubernetes | High for the appliance; none for scale-out |
| umbrelOS 2.0 | Pi 5 + x86, Debian image [C-TD-umbrelos-003] | One box | Yes, single box only | High for the base; no cluster |
| Olares | x86 + NVIDIA, 8 GB floor [C-W4-042] | Multi-node k3s | No image of its own; installs on a host distro [C-TD-olares-007] | High for the app platform; none for OS safety |
| Red Hat Device Edge | Orin and x86, no Pi 5 [C-W2-041] | Fleets with MicroShift | Yes, paid | High for Industrial; none for consumer |
| **OneMind (target)** | Pi 5 Edge profile | Many site clusters + GPU simulation | One app platform; three image flavors | The only one aiming at both ends with robots |

## Recommendations and the requirements they serve {#sec-answer-recs}

| Recommendation (source) | Requirement IDs |
|---|---|
| Own the image; Ubuntu 26.04 core (conditional on Z-01) with a Debian 13 leg until the base lock; pre-registered decision map; Jetson flavor (`01` §3.1.6, §4.1, REC-DEC-17, REC-DEC-42) | RS-1, R-1, M-6, F-7, F-12, F-14, D-002 |
| RAUC A/B with the fresh-signal gate; one release contract (`01` §4.2) | R-1, R-3, M-2, P-7, U-4 |
| k3s on platform nodes, NATS leaf below, agent-only robots (`01` §4.5) | N-9, N-2, N-6, F-14, M-7 |
| restic three-key backups and verified restores (`01` §4.6) | R-2, R-3, UX-6, U-4 |
| Day-1 Secure Boot layout, gateway-enforced approvals (`01` §4.7) | M-2, M-4, AI-5, AI-7 |
| Ten plugin extension points, signed-only (`01` §4.8) | A-5, A-6, F-3, F-4, F-5, F-6 |
| Profiles for greenhouse and TAK node (`09` §8) | P-8, F-13, F-14 |
