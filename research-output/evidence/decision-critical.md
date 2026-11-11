# Decision-critical questions (could flip ADR-001)

**Selected:** 2026-11-10, before any scoring · **Count:** 24 · **Sources:** `context/05-research-questions.md` (bank IDs Q1–Q335), RESEARCH-MISSION.md §4 examples, `docs/ADR-001-foundation.md`
**Method required for each one (brief §2 rule 7 and §4):** primary sources only, at least 3 refuters with different lenses, a steelman of the runner-up, a verdict table, and a statement of what evidence would flip the decision. Results go in `24-QUESTION-BANK-ANSWERS.md` (status plus claim IDs) and feed the scorecard in `evidence/scorecard-weights.md`.
**Serves requirements:** RS-1, RS-4, R-3, M-6, M-7, F-1, F-2, F-7, F-11, F-12, F-14, N-9, A-5, A-6

> ### Explain it like I'm the founder
> ADR-001 is a proposal: Debian 13 plus Rugix A/B updates, k3s everywhere, a separate NVIDIA flavor for Jetson, and restic backups. Most of the 335 research questions refine that plan. These 24 are different: **depending on their answer, the plan itself could change.** For example, if Fedora IoT's built-in health-checked rollback (greenboot) works on a Pi 5 and Debian's free support ends too early for the boxes we sell, the base could move. So these get researched first and hardest, and each one says up front what answer would change the decision. That way nobody can move the goalposts later.

**Key to the table:**
- **Flips:** the ADR-001 decision (D1–D6) that a different answer would change.
- **Owner:** the workstream (brief §5) responsible for the answer. A second workstream in brackets supplies inputs.
- **Gate / criterion:** where the answer lands in the frozen scorecard.
- **Prior-verified** facts are taken from `context/03-repo-findings-index.md`, which records them as VERIFIED in the phase-1 reports. The owning workstream re-opens the primary source and records it as a claim ID before relying on it.

## Summary table

| DC | Bank IDs | Question (short) | Flips | Owner | Gate / criterion |
|---|---|---|---|---|---|
| DC-01 | **Q288**, Q14, Q13 | Fedora IoT / bootc vs Debian 13 + Rugix as the base, a profile, or both (F-12) | D2, D3 | W2 (W3) | G2–G5, C1–C7 |
| DC-02 | *new (F-11, brief §4)*, Q206 | Does any part of the stack block IIoT: protocols, real time, IEC 62443 path, zero-touch onboarding, 10k fleet? | D2, D3, D4 | W8 (W6) | G4 |
| DC-03 | **Q1**, Q213, Q168 | 10-year lifecycle cost to 2036 per base, per device, at 1k and 10k units | D2 | W2 (W16) | G3, C1, C6 |
| DC-04 | **Q167**, Q17, Q165, Q212 | The CRA support-period obligation versus the base's support window | D2, D6 | W6 | G3, C1 |
| DC-05 | **Q2** | Rebasing a fielded device to a new major OS without a reflash | D2, D3 | W3 | G3, C1 |
| DC-06 | **Q4** | Rugix's bus factor, maturity and exit plan | D3 | W3 | C1, C4 |
| DC-07 | **Q6**, Q47, Q144 | One update framework across x86, Pi 5 and Jetson | D2, D3 | W3 (W7) | G2, C2, C5 |
| DC-08 | **Q8**, Q45, Q179 | The Jetson BSP and module lifecycle | D2 | W7 | G2, G3, C1 |
| DC-09 | **Q7**, Q46, Q59 | Jetson flavor base: stock L4T Ubuntu vs Yocto meta-tegra vs Debian rootfs on the BSP | D2, D3 | W7 (W2) | G1, G2, C2 |
| DC-10 | **Q125**, Q19, Q44, Q18 | Is k3s justified on every tier, versus Compose/Quadlet on small nodes? | D4 | W4 | G5, C5 |
| DC-11 | **Q129**, Q136 | Backup and restore coverage, including single-node k3s on SQLite | D5 | W5 | C3 |
| DC-12 | **Q128**, Q21 | How the OS A/B layer and k3s interact on update and rollback (health-gated commit) | D3, D4 | W3 (W4) | C3 |
| DC-13 | **Q16**, Q55, Q92, Q101 | NVIDIA GPU drivers on Debian (no GPU Operator listing) and drivers on a read-only root | D2 | W4 (W2) | C2, C7 |
| DC-14 | **Q11**, Q48 | Real-time kernel needs of robotics on each board | D2, D4 | W7 (W18) | G4, C2 |
| DC-15 | **Q20**, Q42, Q43, Q56 | ROS 2 tier support on the host OS (Debian is Tier 3) | D2 | W7 | C2, C7 |
| DC-16 | **Q335**, Q254, Q86 | Which plugin extension points the base OS must expose on day one (A-5, A-6) | D1, D3 | W19 | C7 |
| DC-17 | **Q334**, Q98 | One OS, simple from a Pi 5 greenhouse to a GPU cluster (F-14) | D1, D2, D4 | W2 (W4) | G5 |
| DC-18 | **Q206**, Q207, Q208, Q209 | Can Secure Boot / TPM / verified root be added later without changing the layout now? | D3, D6 | W6 (W3) | C3 |
| DC-19 | **Q9** | The Pi 5 / CM5 pipeline on Debian (Raspberry Pi kernel/firmware, tryboot) | D2, D3 | W2 (W3) | G2, C2 |
| DC-20 | **Q3**, Q15 | A distro base vs a build-from-source appliance (Buildroot like HAOS, or Yocto) | D1, D2 | W2 (W18) | C1, C5, C3 |
| DC-21 | **Q324**, Q10 | The kernel route: stock, upstream LTS with a OneMind config, CIP SLTS, vendor BSP or patched | D2, D6 | W18 | C1, C2, C5 |
| DC-22 | **Q286** | Platform first (Core + Client + SDK) or own image first? | D1 | W18 (W4) | C5 |
| DC-23 | **Q127**, Q13 | A Kubernetes-native immutable OS (Talos, Kairos) instead of Debian + Rugix + k3s | D2, D3, D4 | W2 (W4) | C3, C5, G2 |
| DC-24 | **Q215**, Q183 | FIPS 140-3 for the public-safety tier: possible on Debian, or does it force RHEL/Ubuntu Pro/SLE? | D2, D4 | W6 | G5, C6 |

Coverage of the brief's §4 examples: Fedora IoT/bootc vs Debian + Rugix (DC-01) · plugin extension points (DC-16) · lifecycle cost to 2036 (DC-03) · rebasing without a reflash (DC-05) · Rugix bus factor (DC-06) · one update framework (DC-07) · Jetson BSP lifecycle (DC-08) · k3s vs Compose (DC-10) · backup coverage including SQLite (DC-11) · CRA support period (DC-04) · GPU drivers on Debian (DC-13) · real-time kernel (DC-14). All 12 are included.

Coverage of ADR-001: D1 (DC-16, 17, 20, 22) · D2 (DC-01, 02, 03, 04, 05, 07, 08, 09, 13, 14, 15, 17, 19, 20, 21, 23, 24) · D3 (DC-01, 02, 05, 06, 07, 09, 12, 16, 18, 19, 23) · D4 (DC-02, 10, 12, 14, 17, 23, 24) · D5 (DC-11) · D6 (DC-04, 18, 21).

---

## Detail per question

### DC-01 · Fedora IoT / bootc vs Debian 13 + Rugix (F-12)
- **Bank IDs:** Q288 (primary), Q14, Q13. **Owner:** W2, with W3 for update mechanics. **Requirements:** F-12, F-11, F-14, R-1, R-3.
- **Why it can flip ADR-001:** greenboot already implements health-checked commit with automatic rollback, which is ADR-001's claimed improvement (Q288). bootc ships the OS as an OCI image, so the same registry, signing and GitOps tooling would cover both the OS and the apps (Q14). If Fedora IoT/bootc passes G2 (Pi 5) and has a credible 2036 path through CentOS Stream → RHEL image mode, it could become the base or the Industrial track, and D2/D3 would change.
- **Prior-verified (context/03 and the Fedora deep dive):** Fedora IoT has no hold-back tree; the bug "bootc image does not boot on rpi" is open; Pi 5 boots Fedora 44/45 Workstation, but IoT/bootc on Pi 5 is unproven. The deep dive recommends bootc as a strategic Industrial/Enterprise track, not the consumer default.
- **Evidence needed:** the Fedora IoT and bootc docs and issue trackers at pinned commits (Pi 5 status, bootupd PR, greenboot behaviour); Fedora and CentOS Stream 10 lifecycle pages; the RHEL image-mode lifecycle and subscription terms; NVIDIA on Fedora/RHEL (akmods on ostree, RHEL in the GPU Operator matrix); Jetson on RHEL/Fedora; the VM lab (brief §7) with a Fedora IoT/bootc image next to Debian + Rugix doing a forced bad update and rollback; a written steelman for Fedora IoT/bootc.
- **Flip condition:** bootc/Fedora IoT passes G2 and G3 and outscores Debian + Rugix by 3 or more points robustly (scorecard §6). A weaker result (it passes the gates but doesn't win) adds it as a supported profile or track.
- **Result (rev. 4 of `01`, 2026-11-11):**
  - **Answer:** bootc is not the decision of record, but it is **one of the two frozen-protocol finalists**. On the rev-4 card (Ubuntu 65 · bootc 64 · Debian 63), the top-two tie-break goes to Ubuntu 26.04, 6–4 [C-DEC4-001, C-DEC4-006]. The rev-3 three-way tie-break that kept Debian is withdrawn [C-PROTO4-018]. Under the pre-registered map, bootc becomes the S1 result if Canonical refuses Z-01 and the debrand route is rejected, while W2-HW-3 has not failed (01 §3.1.6 h). **Disclosure:** this DC's own flip condition (bootc passes G2 and G3 and "outscores Debian + Rugix by 3 or more points robustly") was met on the rev-3 card if COND counts as passing (C led A by 3.11–4.89 in all 14 runs). Rev. 3 did not say so. On the rev-4 card, after the rule-6 re-score of A·C3, the margin is 1.0 and the condition is not met [C-DEC4-008]. Industrial profile: **AlmaLinux 10 or RHEL 10 image mode** (year 2). CentOS Stream 10 (end of life 2030-05-31 [C-REF4-DC-longevity-001]) and Fedora IoT bootc are CI canaries only. The greenboot silent downgrade is still open upstream [C-LAB-fedora-bootc-011, C-STEEL4-bootc-024]. 01 §3.1.6, §6.14.
  - **Status:** partial · blocked: founder-hardware (W2-HW-3) and founder-decision (Z-38, Z-39).
  - **Refuter verdicts (lens):** dedicated round 4: technical **weakened**, longevity **weakened** ([technical](adversarial/DC-01-technical.md), [longevity](adversarial/DC-01-longevity.md)). On the rev-3 S1 verdict: S1R4 technical, longevity and security **weakened**. Earlier P0 refuters: W2-P0-2 technical **weakened**, longevity **upheld**, robotics **upheld**. Responses: 01 §5.1.1, §5.9.2.
  - **Steelman:** [STEEL4-bootc-core](adversarial/STEEL4-bootc-core.md) (rev. 4, bootc as the core); [W2-steelman](adversarial/W2-steelman.md); [steelman-iiot-runner-up](adversarial/steelman-iiot-runner-up.md).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **W2-HW-3**, now **before gate G1 (week 4)**, with the steelman's conditions (automatic Pi commit that survives a power pull; a #219 patch).

### DC-02 · Is there a blocking limitation for IoT/IIoT? (F-11)
- **Bank IDs:** no single bank question. Built from the brief (§4, §6 gate G4, W8). W8 adds it to `24-…` as a new question. Related: Q206 (chain of trust). **Owner:** W8, with W6 for IEC 62443. **Requirements:** F-11, F-13, AI-7, N-4, N-6.
- **Why it can flip ADR-001:** gate G4 is a must-pass. If the Debian + Rugix stack can't reach an IEC 62443-4-2 path, zero-touch onboarding (FDO, IDevID) or fleet scale of about 10k devices, while CIP Core (Isar) or RHEL image mode can, then D2 gains an Industrial track or changes outright.
- **Prior-verified (IIoT report):** "supervise, not control": hard real time belongs on PLCs, RTOS or MCUs. The NATS MQTT listener implements MQTT 3.1.1 only and rejects MQTT 5 clients. RHEL 9.6 and MicroShift 4.21 have 62443-4-2 SL-C 2 precedents. CIP Core is the best candidate for an Industrial track.
- **Evidence needed:** the IEC 62443-4-1/4-2 catalogue pages (PRIMARY-METADATA) and published vendor certificates; CIP Core and Isar docs; the FIDO Device Onboard spec and its implementations (Fedora's fdo-rs, others) on Debian; IEEE 802.1AR on the target boards' TPMs; fleet-manager limits; OPC UA (open62541) and Sparkplug B on arm64; an MQTT 5 broker decision.
- **Flip condition:** any G4 sub-check FAILs for Debian + Rugix and PASSes for an alternative. **Restated for the decision of record (FIX7, critic P7-2):** any G4 sub-check FAILs for **Ubuntu 26.04 + RAUC + k3s** (01 rev. 4, candidate D). A gate FAIL un-ranks D, as in the "D·G1 COND → FAIL" rows of the 01 §3.1.6 (h) map, which has no G4 row of its own. The card becomes C 64 · A 63, and the result is **C**, 6–5. If A or C fails the same sub-check, the gate decides nothing between them, and an Industrial track is added instead. The Debian condition is kept for the Debian leg.
- **Result for Ubuntu 26.04 + RAUC (FIX7, 2026-11-11):** **not met. G4 = CONDITIONAL, no sub-check FAIL** (09 §1, new first column).
  - **(a) PASS.** The protocol stacks are in 26.04 universe [C-FIX7-004]. Their security fixes need Ubuntu Pro [C-FIX4-001].
  - **(b) COND.** The RT kernel is free on x86 and arm64 from 26.04 [C-FIX7-002, C-STEEL-ubu-008]. Canonical's Pi 4/5 RT variant is stated only for 24.04 [C-FIX7-002, C-FIX7-003].
  - **(c) PASS (path).** A classic Ubuntu 22.04.3 is the OS of an ISASecure 62443-4-2 SL-C 2 host device [C-FIX7-001]. Canonical's process is audited to 62443-4-1 [C-STEEL-ubu-010].
  - **(d) COND.** The same go-fdo gap as on every finalist [C-W8-044, C-REF4-DC-technical-004]. The Pi 5 has no TPM [C-W8-041].
  - **(e) COND.** `rauc-hawkbit-updater` is not packaged for 26.04 [C-FIX7-005, C-FIX7-006]. New mitigation G4-M5 backports it. 10k devices are not shown.
  - **Status:** partial. The 26.04 package facts are SECONDARY (Repology), because the archive does not resolve here; they get a networked re-check (20 D1). The founder test LAB-W8-4 already covers the core legs (22 LT-VM-16).
- **Result (rev. 4 of `01`, 2026-11-11), written for the Debian leg:**
  - **Answer:** G4 stays CONDITIONAL with five mitigations (supervise-not-control, an RT IIoT SKU on x86 `linux-image-rt`, protocol stacks as upstream-pinned app images with a CVE SLA, OneMind's own 62443-4-1 process or a partner, go-fdo with funded interop; plus the maintenance-horizon condition). **Rev. 4 wording:** no G4 sub-check fails *relative to the alternatives*, but four of five are unproven in absolute terms and need OneMind-built work. go-fdo has no release and no FIDO interop [C-REF4-DC-technical-004], and its FDO 2.0 core is a single-author PR in progress [C-REF4-DC-technical-005]. NATS maintainers do not plan MQTT 5, so the Mosquitto/NanoMQ bridge is permanent architecture [C-REF4-DC-technical-003]. FDO is therefore experimental, with IDevID plus manual claim as the day-one fallback. NATS governance (Synadia's 2025 relicensing attempt [C-REF4-DC-longevity-004]) goes to the risk register with a named exit. These gaps are the same on every S1 finalist. 01 §4.7, §5.8, §5.9.2.
  - **Status:** partial (no assessor statement; 10k fleet not simulated; go-fdo interop unproven).
  - **Refuter verdicts (lens):** dedicated round 4: technical **weakened**, longevity **weakened** ([technical](adversarial/DC-02-technical.md), [longevity](adversarial/DC-02-longevity.md)). Earlier P0 refuters: W8-P0-1 IIoT, longevity and security **weakened**; W8-P0-2 IIoT **upheld**, longevity **weakened**, security **upheld**.
  - **Steelman:** [steelman-iiot-runner-up](adversarial/steelman-iiot-runner-up.md).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **LAB-W8-4** (FDO onboarding on Debian and EL10 bootc; DI → TO2 must complete), LAB-W8-3 (Mosquitto bridge against the Sparkplug TCK), and the Flight Control `devicesimulator` / 10k fleet test (Z-27).

### DC-03 · Lifecycle cost to 2036
- **Bank IDs:** Q1 (primary), Q213, Q168. **Owner:** W2, with W16 for pricing. **Requirements:** R-3, H-1, M-8, F-1.
- **Why it can flip ADR-001:** ADR-001 picked Debian partly because it's free. **Prior-verified:** Debian 13 LTS ends 2030-06-30 and Freexian ELTS (paid) runs to 2035-06-30. Ubuntu 24.04 ESM runs to May 2034 and Ubuntu Core 26 to May 2036, but the Ubuntu Pro for Devices price is unpublished. If Debian's 10-year cost (ELTS plus rebases) exceeds a paid alternative's, or if ELTS doesn't cover the packages OneMind uses, D2 changes.
- **Evidence needed:** primary lifecycle pages for every S1 candidate; Freexian ELTS pricing and package-coverage policy; Ubuntu Pro for Devices terms (or a bounded estimate labelled SECONDARY with ≥2 sources); the RHEL for Edge / Device Edge subscription; SUSE SL Micro; the CIP SLTS schedule; a cost model per device per year at 1k and 10k units through 2036.
- **Flip condition:** Debian's bounded cost to 2036 exceeds the cheapest gate-passing alternative's by more than 25%, or its G3 result is FAIL.
- **Result (rev. 3 of `01`, 2026-11-11):**
  - **Answer (rev. 3, priced):** per device, base + CRA, 2027–2036, base scenario: Debian $403 at 1k units and $40 at 10k; Ubuntu Pro for Devices about $385 / $120 (if about $60/box); RHDE $1,756 / $1,391; free AlmaLinux bootc about Debian's. Debian is never > 25% above the cheapest, so the flip is **not met**; it would need a Pro for Devices quote ≤ about $18/box at 1k (≤ $2 at 10k) plus written redistribution permission ([lifecycle-cost-2036](lifecycle-cost-2036.md) COST-2/3). Labour, not licences, dominates; rebase hours are still an assumption.
  - **Status:** partial (quote and rebase hours needed).
  - **Refuter verdicts (lens):** cost **weakened**, robotics **weakened**, longevity **weakened** (all three: wording and labour, not the ranking).
  - **Steelman:** [steelman-base-ubuntu](adversarial/steelman-base-ubuntu.md).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **T-W3-04** (timed Debian 13 → 14 A/B rebase recording founder-hours); quote outreach O-1 (Z-01).

### DC-04 · The CRA support-period obligation
- **Bank IDs:** Q167 (primary), Q17, Q165, Q212. **Owner:** W6. **Requirements:** R-3, H-1, M-8.
- **Why it can flip ADR-001:** a box sold in late 2027 on Debian 13 needs security support well past the free LTS end (2030-06-30). If the CRA's minimum support period (Art. 13(8)) plus the box's product class (default, important Class I/II) forces a support window that only a paid or longer-lived base can meet affordably, D2 changes. The product class also decides whether a third-party conformity assessment is needed (D6).
- **Prior-verified:** CRA vulnerability reporting has applied since 2026-09-11; the main obligations apply from 2027-12-11.
- **Evidence needed:** the official text of Regulation (EU) 2024/2847 on EUR-Lex (Art. 13(8), Art. 14, Annexes I, III, IV) with its application dates; Commission implementing acts or guidance on product categories; the open-source steward provisions; how competitors declare support periods (published security policies).
- **Flip condition:** the declared period plus the box's sales window runs past the base's bounded, affordable support, with no rebase path (DC-05).
- **Result (rev. 3 of `01`, 2026-11-11):**
  - **Rev. 4 sync (FIX7, critic P7-2).** D2 is no longer "confirmed". 01 §7 changed it in rev. 4 to **Ubuntu 26.04 LTS** (conditional), with the Debian 13 leg kept. The support-period reasoning for the decision of record works like this:
    - **The rule.** The CRA asks for at least five years that reflect expected use, taking account of the support periods of integrated components [C-W6-002].
    - **The fit.** Ubuntu 26.04 security maintenance runs to **May 2036 under Ubuntu Pro** [C-W2-005]. A box sold in late 2027 can therefore declare a period of about 8.5 years **without a major-release rebase**. On Debian, the declared period needs a rebase or paid ELTS.
    - **The new cost.** That period depends on a paid subscription with no published device price (Pro for Devices, up to 10 years, years 11–15 via Legacy) [C-W2-006]. The protocol packages OneMind ships from universe are covered only under Pro [C-FIX7-004, C-FIX4-001].
    - **What does not change.** The per-board rule below. Jetson stays on JetPack's Ubuntu 24.04 (Pro to May 2034 [C-W2-005]) and is patched on its own release. **Flip condition (unchanged in kind):** the declared period plus the sales window runs past May 2036, or Pro for Devices is unaffordable or refused (Z-01), with no rebase path (DC-05).
  - **Answer (rev. 3 wording, Debian leg):** D2 confirmed for amd64 and conditional per board: a board that cannot take the next base is patched on its old release for the declared period, which is the minimum of OneMind's and the board vendor's commitment. Image = Class I OS; a box is probably classified by its core function. Route chosen by 2027-Q2; **rev. 3:** a notified-body pre-assessment runs as a parallel track from 2027-Q1. 01 §4.7.
  - **Status:** blocked: founder-decision (counsel, Z-05; support periods, Z-06).
  - **Refuter verdicts (lens):** W6-P0-1 security **weakened**, cost **weakened**, technical **weakened**; W6-P0-2 security, cost and technical **weakened**.
  - **Steelman:** [steelman-cra-notified-body](adversarial/steelman-cra-notified-body.md) (accepted in its fair reading).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** n/a (legal); T-W3-04 supplies the rebase evidence.

### DC-05 · Rebasing without a reflash
- **Bank IDs:** Q2. **Owner:** W3. **Requirements:** R-1, R-3, F-1.
- **Why it can flip ADR-001:** choosing a distro for 10 years really means choosing a rebase strategy. If Rugix can't move a fielded device from Debian 13 to 14 to 15 (partition-table, bootloader or slot-size changes) without a reflash, field devices are stranded, and OSTree/bootc (which rebase by design) gain a decisive edge (D2, D3).
- **Evidence needed:** code-level study of how Umbrel (1.x → 2.0), HAOS (partition-resize migrations, RAUC hooks), Proxmox 8 → 9 and TrueNAS 24 → 25 handle base jumps, at pinned SHAs; Rugix docs on slot sizes and repartitioning; bootc and rpm-ostree rebase docs; a lab spike doing an A/B update from a Debian 13 image to a Debian 14 testing image.
- **Flip condition:** Rugix needs a reflash for a major rebase, and a gate-passing alternative doesn't.
- **Result (rev. 4 of `01`, 2026-11-11):**
  - **Answer:** a Debian major rebase without reflash has **shipped** once: umbrelOS moved from Debian 12 to 13 by OTA bundle [C-W3-039]. But it ran on Rugix/Mender, not RAUC, and post-rebase updates were unreliable in the field: a Debian-packaged Mender client could not read the next release's artifacts, and some units needed a reflash or clean install [C-REF4-DC-technical-006, C-REF4-DC-technical-007, C-REF4-DC-longevity-006, C-REF4-DC-longevity-007]. There is no RAUC major-rebase precedent [C-DEC-013 (UNVERIFIED: negative search)], and OneMind has not run one. bootc rebases by design (lab) [C-LAB-fedora-bootc-015]. On the Ubuntu leg, no rebase is needed to May 2036 under Ubuntu Pro, at an unpublished price [C-W2-005, C-W2-006]. **Flip not met:** RAUC needing a reflash is untested, not shown. In S1's tie-break the A–D DC-05 row moves to ≈ (01 §3.1.6 f).
  - **Status:** partial (T-W3-04 not run).
  - **Refuter verdicts (lens):** dedicated round 4: technical **weakened**, longevity **weakened** ([technical](adversarial/DC-05-technical.md), [longevity](adversarial/DC-05-longevity.md)). Earlier, borrowed: W6-P0-1 technical **weakened**, W2-P0-1 longevity **weakened**, DC-03 longevity **weakened**.
  - **Steelman:** [W2-steelman](adversarial/W2-steelman.md); [STEEL4-bootc-core](adversarial/STEEL4-bootc-core.md) §3.1.
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **T-W3-04**, extended in rev. 4. The **old** slot's RAUC installs the new release's bundle, then two further OTAs (N+1, N+2) follow, with an external data disk attached, on x86 (efi and GRUB routes) and on a Pi 5. Founder-hours per rebase are recorded. Plus a CI rule: every bundle must install with the RAUC shipped two releases earlier.

### DC-06 · Rugix's bus factor and maturity
- **Bank IDs:** Q4. **Owner:** W3. **Requirements:** R-1, R-3, M-6.
- **Why it can flip ADR-001:** D3 makes Rugix the core update mechanism on the strength of one adopter (Umbrel). The update framework is the hardest part to replace after devices ship. **Prior-verified:** Rugix v1.4.0 (2026-11-02), MIT or Apache-2.0; it doesn't mark boots good or bad by itself (the integrator must call `rugix-ctrl`); Umbrel moved from Mender to Rugix.
- **Evidence needed:** the GitHub API for rugix/rugix (contributors and commits in the last 12 months, release cadence, issue response times, the share of commits from the top contributor); the same metrics for RAUC, Mender, SWUpdate, OSTree/bootc and Kairos; public adopters other than Umbrel; the maintainer's company and funding; LICENSE files at a pinned tag; an exit plan (Rugix's RAUC/Mender compatibility boot flows).
- **Flip condition:** a single-maintainer bus factor with no second adopter, while RAUC is comparable on features (it's HAOS-proven). The likely flip is D3 → RAUC.
- **Result (rev. 4 of `01`, 2026-11-11):**
  - **Answer:** Rugix's bus factor is about one (303 of 304 commits in a year, re-checked) [C-W3-001, C-REF4-DC-technical-012]; the move to RAUC stands. **Rev. 4 wording:** the move rests on the S2 card (RAUC 61 vs Rugix 52, outside the band) plus the bus factor. It does not rest on DC-06's literal condition, which is not met, because Rugix has an independent IIoT adopter. RAUC's own concentration is recorded beside Rugix's: two Pengutronix engineers write about 91% of human commits, and 1.16 is unreleased eight months after 1.15.2 [C-REF4-DC-technical-009, C-REF4-DC-technical-010, C-REF4-DC-longevity-008]. Silitics' open-source commitment says nothing about continuity [C-REF4-DC-technical-013]. If Mender is used, a client upgrade is budgeted at least yearly (support windows of 12–16 months) [C-REF4-DC-longevity-009, C-REF4-DC-longevity-010]. Rugix stays the documented alternative.
  - **Status:** answered.
  - **Refuter verdicts (lens):** dedicated round 4: technical **upheld** (two wording corrections), longevity **upheld** (disclosure fix) ([technical](adversarial/DC-06-technical.md), [longevity](adversarial/DC-06-longevity.md)). Earlier: W3-P0-W3-1 technical, security and longevity **upheld**.
  - **Steelman:** [steelman-updates-rugix](adversarial/steelman-updates-rugix.md).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** n/a (F-PI5 decides the Pi 5 engine path; 01 §6.7).

### DC-07 · One update framework across x86, Pi 5 and Jetson
- **Bank IDs:** Q6 (primary), Q47, Q144. **Owner:** W3, with W7 for Jetson. **Requirements:** M-6, M-7, R-1, N-2.
- **Why it can flip ADR-001:** ADR-001 leaves the Jetson A/B method open. If the robot flavor needs a different update system, the moat platform gets the weakest updates, and a sole developer maintains two or three update stacks. A framework that covers all three (for example RAUC through meta-tegra) could replace Rugix (D3) or change the flavor plan (D2). **Prior-verified:** Rugix has no Jetson or Tegra support in its repo (UNVERIFIED as a positive); Kairos supports AGX Orin, Orin NX and Thor but not Pi 5; balenaOS covers Pi 5, Orin and amd64.
- **Evidence needed:** the NVIDIA Jetson Linux developer guide (rootfs A/B, UEFI capsule update, OTA tools); OE4T meta-tegra integrations with RAUC, Mender and SWUpdate at pinned commits; Rugix boot flows; the Kairos Jetson docs; a founder-hardware test plan for an Orin Nano.
- **Flip condition:** no candidate can be one framework for all three, and a per-flavor framework costs more than switching the core framework.
- **Result (rev. 3 of `01`, 2026-11-11):**
  - **Answer:** no engine covers stock-L4T Jetson; one OneMind release contract over RAUC (x86, Pi 5) and NVIDIA rootfs A/B + image-based OTA (Jetson). **Rev. 3:** the Jetson backend is not a thin wrapper: OneMind owns the payload verifier (NVIDIA's payload is unsigned by design), the gate must turn failures into warm resets (cold cycles don't count), failover needs a per-BSP regression test and a post-OTA version check. One framework becomes possible only if Jetson moves to meta-tegra. 01 §4.2.
  - **Status:** partial · blocked: founder-hardware.
  - **Refuter verdicts (lens):** cost **weakened**, security **weakened**, technical **weakened**.
  - **Steelman:** [steelman-updates-mender](adversarial/steelman-updates-mender.md) (one engine via meta-tegra).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **T-W3-06** (extended: cold-cycle-after-hang, mount failure with watchdog, post-OTA version assertion; plus Mender E3).

### DC-08 · The Jetson BSP and module lifecycle
- **Bank IDs:** Q8 (primary), Q45, Q179. **Owner:** W7. **Requirements:** M-7, N-8, F-2, R-3.
- **Why it can flip ADR-001:** robots sold as long-term products must not be stranded on a frozen vendor kernel. **Prior-verified:** JetPack 7.x is Ubuntu 24.04 with kernel 6.8 and supports Orin and Thor; Jetson Linux 38.4 doesn't support the Orin family. If NVIDIA's per-release security support is short, and mainline Linux covers too little of Orin/Thor, the Jetson flavor needs a different base (DC-09) or a support contract, which changes D2 and the CRA math (DC-04).
- **Evidence needed:** the NVIDIA Jetson product lifecycle page (module EOL dates); the L4T release history (r35/r36/r38/r39) with security-update cadence; NVIDIA's support statements per JetPack release; the upstream kernel tree (arch/arm64/boot/dts/nvidia, the tegra drivers) against the OE4T linux-tegra diff.
- **Flip condition:** the security-update window per L4T release is shorter than the support period OneMind must declare, with no affordable bridge.
- **Result (rev. 4 of `01`, 2026-11-11):**
  - **Answer:** NVIDIA publishes no per-branch security window. Per module, `support_end` = the EOL of the last JetPack branch NVIDIA ports it to; JetPack 5 ended on 2026-10-30 [C-REF-W7L-001]. **Rev. 4: the "affordable bridge" is not demonstrated.** No documented console-free r36 → r39 upgrade moves QSPI on production modules, and JetPack 5 ended about a year before NVIDIA's own roadmap date (DC-08 technical refuter; its sources are cited under colliding REF4 IDs and are not ledgered). Ports to older modules lag by months [C-REF4-DC-longevity-011]. NVIDIA's new Yocto support states no lifetime [C-REF4-DC-longevity-012], and meta-tegra has about three active maintainers [C-REF4-DC-longevity-013]. So Jetson SKUs declare support from the **current branch only** until a lab proves the upgrade. NVIDIA roadmap dates are recorded as "estimate, has been missed early". A paid sustaining tail is priced (follow-up for `lifecycle-cost-2036.md`). **Not flipped:** a paid partner tail exists. The same holds on every S1 base, because the Jetson flavor is L4T on all of them.
  - **Status:** partial (was "answered"; the bridge is unproven).
  - **Refuter verdicts (lens):** dedicated round 4: technical **weakened**, longevity **weakened** ([technical](adversarial/DC-08-technical.md), [longevity](adversarial/DC-08-longevity.md)). Earlier: W7-FF-1 robotics, technical and longevity **weakened**.
  - **Steelman:** [steelman-jetson-base](adversarial/steelman-jetson-base.md).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **new, proposed for 22:** an unattended r36.5 → r39.2 image-based OTA on a production Orin NX with `ROOTFS_AB=1`, data kept, QSPI version checked before and after.

### DC-09 · Which base for the Jetson flavor
- **Bank IDs:** Q7 (primary), Q46, Q59. **Owner:** W7, with W2. **Requirements:** M-7, N-8, F-2, D-001.
- **Why it can flip ADR-001:** the L4T Ubuntu flavor inherits Ubuntu's userspace and Canonical's terms, which undercuts why Debian was chosen. A Yocto meta-tegra build or a Debian rootfs on the BSP could unify the image family (F-14) or make Yocto the cross-board system (DC-20). The NVIDIA license terms for redistributing L4T, CUDA and TensorRT in an image (G1) can also rule options in or out.
- **Evidence needed:** the JetPack 6/7 component matrix (CUDA, TensorRT, VPI, DeepStream, Isaac ROS, Holoscan) per rootfs option; OE4T meta-tegra's supported-release table; the NVIDIA Jetson software license and CUDA EULA redistribution clauses; Isaac ROS container host requirements; how robotics firms ship Jetson images (Q50).
- **Flip condition:** a non-Ubuntu Jetson rootfs keeps full JetPack capability and passes G1, which unifies the family; or stock L4T fails G1 for redistribution.
- **Result (rev. 3 of `01`, 2026-11-11):**
  - **Answer:** L4T Ubuntu 24.04 (JetPack 7.2+) for the launch beta, gated on Z-01 (it is modified Ubuntu); Yocto meta-tegra + linux-yocto 6.18 is an evaluated target; **rev. 3:** Canonical's certified Jetson image joins LAB-W7-6 as a third arm, and Orin launches on JP 6.2.x if a JP 7.2 BSP upgrade cannot be completed in the lab. 01 §4.1.
  - **Status:** partial · blocked: founder-hardware and founder-decision (Z-01, Z-16).
  - **Refuter verdicts (lens):** cost **weakened**, robotics **weakened**, technical **upheld** (two qualifications).
  - **Steelman:** [steelman-jetson-base](adversarial/steelman-jetson-base.md).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **LAB-W7-6** (meta-tegra on 6.18: CUDA/TensorRT within 10%, CSI camera, NVENC, two 6.18.y bumps, A/B with the gate).

### DC-10 · Is k3s justified on every tier?
- **Bank IDs:** Q125 (primary), Q19, Q44, Q18. **Owner:** W4. **Requirements:** N-9, N-2, F-14, M-6.
- **Why it can flip ADR-001:** HAOS and Umbrel, the two most proven appliances, use Docker. N-9 says the question is still open. If k3s's idle footprint and flash-write volume are too high for a 4 GB Pi 5 or a robot, D4 becomes tiered (Compose/Quadlet on small nodes), which in turn affects the app format and F-14. **Prior-verified:** k3s's server minimum is 2 cores/2 GB; it measures about 1.6 GB with a workload (k3s v1.26.5 profile); an agent uses about 270 MB.
- **Evidence needed:** the k3s resource-profiling docs at the current version; the VM lab's measured idle and loaded footprint (brief §7 item 4), flash writes in bytes per day, and boot-to-ready time for k3s (SQLite), k0s and Podman + Quadlet running the same reference apps; Olares's k3s footprint on its minimum hardware; SUSE's k3s/RKE2 lifecycle (Q18).
- **Flip condition:** k3s on a 4 GB Pi 5 leaves less than about 2 GB for apps, or writes enough per day to threaten SD/eMMC life over 5 years, while a Compose/Quadlet node can still join the same app platform.
- **Result (rev. 4 of `01`, 2026-11-11):**
  - **Answer:** k3s on every platform node (≥ 4 GB RAM **and** SSD/NVMe), NATS leaf below, 8 GB recommended, capturable field nodes agent-only; the Market compiles to Helm and imports Compose. Lab: +936 MiB idle on a 4 GiB arm64 VM [C-LAB-k3s-footprint-restore-007]. **Rev. 4:** the memory side holds as measured. The flash side needs a fault case: SQLite compaction in kine can stall permanently (a v0.13.4–v0.13.9 regression), after which writes and state.db grow without bound (DC-10 technical refuter; sources cited under colliding REF4 IDs, not ledgered). So kine ≥ v0.13.10 is pinned, compaction lag raises an alert, and T-W4 is extended. k3s minors (about three a year, each through the gate) are a recurring cost, and Market CI gates chart API compatibility per minor [C-REF4-DC-longevity-014]. SUSE's possible sale [C-REF4-DC-longevity-015, SECONDARY: press] and kine's single-engineer concentration [C-REF4-DC-longevity-016] are vendor risks, with exits to k0s, RKE2 and kubeadm. 01 §4.5, §5.9.2.
  - **Status:** partial · blocked: founder-hardware.
  - **Refuter verdicts (lens):** dedicated round 4: technical **weakened**, longevity **weakened** ([technical](adversarial/DC-10-technical.md), [longevity](adversarial/DC-10-longevity.md)). Earlier: W4-P0-1 technical, cost and security **weakened**.
  - **Steelman:** [W4-steelman](adversarial/W4-steelman.md) (Compose everywhere; 64.0 with G5 relaxed).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **T-W4 soak**, extended in rev. 4: hardened k3s with the real OneMind stack on a Pi 5 4 GB NVMe for 30 days, one injected compaction failure, and state.db size and bytes/day recorded. Less than 2.0 GiB free, more than 5 GB/day, or an unrecoverable stall raises the floor to 8 GB or makes the node agent-only.

### DC-11 · Backup and restore coverage, including single-node SQLite
- **Bank IDs:** Q129 (primary), Q136. **Owner:** W5. **Requirements:** R-1, R-2, M-2, UX-6.
- **Why it can flip ADR-001:** D5 assumes `k3s etcd-snapshot` plus restic. **Prior-verified:** k3s's default datastore is SQLite (single server only); etcd snapshots run twice a day and keep 5; k3s rollback means a binary downgrade plus a restore from a snapshot taken on the older minor; SQLite snapshot coverage is UNVERIFIED. If SQLite isn't covered, single boxes need embedded etcd from day one (more RAM and flash wear) or another backup path, which changes D4/D5 defaults.
- **Evidence needed:** the k3s datastore and backup docs, and the source at a pinned tag (etcd-snapshot behaviour with kine/SQLite); a lab restore onto a fresh VM (brief §7 item 5) for SQLite and etcd; whether SQLite can migrate to embedded etcd in place; what HAOS, Umbrel and Olares back up, from code.
- **Flip condition:** no supported SQLite backup/restore, and no in-place migration to etcd, so the single-box default must change.
- **Result (rev. 4 of `01`, 2026-11-11):**
  - **Answer:** single-box datastore = online SQLite `.backup` + token inside restic; a full restore onto a fresh VM was verified [C-LAB-k3s-footprint-restore-011]; etcd clusters use `etcd-snapshot`, restic-wrapped; hub/Pro/Omni servers move to embedded etcd if the corrected T-W5-03 passes. **Rev. 4:** `PRAGMA integrity_check` passes a runaway, compaction-stalled datastore (DC-11 technical refuter; sources cited under colliding REF4 IDs, not ledgered). So a backup counts as "verified" only if state.db is within a size budget and compaction is not lagging. The box gets an on-device offline-compaction procedure with a free-space precheck. On a `restic check` failure, the box retries once and runs a memory test before reporting damage. restic's maintainer concentration (one person writes most commits [C-REF4-DC-longevity-017]) is recorded under the same rule that moved D3 off Rugix, with a CI read test by an independent implementation. T-W5-03 runs under write load [C-REF4-DC-longevity-018]. 01 §4.6, §5.9.2.
  - **Status:** answered (lab) · open tests.
  - **Refuter verdicts (lens):** dedicated round 4: technical **weakened**, longevity **weakened** ([technical](adversarial/DC-11-technical.md), [longevity](adversarial/DC-11-longevity.md)). Earlier: W5-P0-1 technical, security and longevity **upheld**; W5-P0-2 technical, security and longevity **weakened**.
  - **Steelman:** [steelman-etcd-every-box](adversarial/steelman-etcd-every-box.md) (accepted conditionally); [steelman-backup-kopia](adversarial/steelman-backup-kopia.md).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **T-W5-03** corrected and run under write load (72 h, hardened k3s, Pi 5 8 GB + NVMe and x86; etcd ≤ 2× SQLite and ≤ 5 GB/day); **T-W5-01** two-engine memory test; rev. 4 adds a CI restore of a multi-GB, compaction-stalled state.db within the box's free space.

### DC-12 · How the A/B layer and k3s interact (health-gated commit)
- **Bank IDs:** Q128 (primary), Q21. **Owner:** W3, with W4. **Requirements:** R-1, R-2, AI-4.
- **Why it can flip ADR-001:** "commit only after k3s and the core pods are healthy" is ADR-001's main improvement. Rolling the OS back to a slot with an older k3s against a newer datastore could brick the cluster (k3s refuses downgrades). If this can't be made safe with k3s inside the image, D3/D4 change: k3s lives outside the A/B image, or the update model changes (for example OSTree/bootc with greenboot, or Talos).
- **Evidence needed:** k3s upgrade and downgrade docs and source; Rugix and RAUC commit hooks; how greenboot, Kairos, Talos, Flatcar and HAOS define health, from code; a lab spike doing a forced bad update with automatic rollback, gated on k3s readiness (brief §7 item 2), including the case of a rollback across a k3s minor version.
- **Flip condition:** no safe design exists for rollback across a k3s minor version with k3s in the A/B image.
- **Result (rev. 4 of `01`, 2026-11-11):**
  - **Answer:** a safe design is **shown for a single box on SQLite**: k3s inside the read-only slot, the datastore on `data`, each trial on a copy, a fresh-signal gate (apps excluded, 3 tries on GRUB, watchdog), a k3s-minor guard and no auto-retry. The same unchanged gate passed on Debian (RAUC 1.13 and 1.15.2), Ubuntu 26.04 (RAUC 1.15.1), with Mender and, in rev. 4, on **native arm64** [C-LAB-rauc-1152-011, C-LAB-ubuntu-2604-leg-011, C-LAB-mender-014, C-LAB-aarch64-gate-004]. The naive gate committed a broken kubelet every time, on arm64 too [C-LAB-aarch64-gate-010]. **Rev. 4 conditions, from three dedicated refuters:**
    1. On embedded-etcd servers, a per-node file copy is not a supported etcd rollback. Cluster rollback goes through `etcd-snapshot` restore (untested).
    2. App and core-service migrations are held until the OS commits.
    3. The gate gives two verdicts. "Image bad" (k3s or the kubelet never healthy) is final. "Environment bad" (k3s healthy but a core pod starved) is re-offered with a bounded counter and an alert, so a hostile app cannot block a security release for good.
    4. After a commit, `prevent-late-fallback` and a version floor raised by security releases retire the old slot [C-LAB-secureboot-1152-010, C-REF4-DC-security-001].
    5. Installed charts get a pre-publish API scan against the target k3s minor, and a costed policy says how long stepping-stone images are kept.
    6. The gate deadline is wall-clock time, so a slow host can turn a good trial into a rollback [C-LAB-aarch64-gate-006].
    Rollback across a k3s minor is not yet run. 01 §4.2 item 6, §5.9.2.
  - **Status:** partial (T-W3-03; hardware).
  - **Refuter verdicts (lens):** **dedicated (rev. 4, closes P3-9):** technical **weakened**, longevity **weakened**, security **weakened** ([technical](adversarial/DC-12-technical.md), [longevity](adversarial/DC-12-longevity.md), [security](adversarial/DC-12-security.md)). The technical and longevity files cite their sources under colliding REF4 IDs, so those sources are not ledgered. Earlier: W3-P0-W3-2 technical, security and longevity (they covered the engine, not the gate).
  - **Steelman:** Mender and Rugix steelmen (the gate is engine-neutral); [STEEL4-bootc-core](adversarial/STEEL4-bootc-core.md) (logically bound images as the bootc alternative).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **F1/F2** (RAUC + k3s gate on x86 hardware with 10 real power pulls). **T-W3-03**, run twice in rev. 4: on a single box and on a three-server embedded-etcd cluster, each with a migrating app and an API-removal chart, plus an N → N+3 offline catch-up, with `prevent-late-fallback` on.

### DC-13 · NVIDIA GPU drivers on Debian
- **Bank IDs:** Q16 (primary), Q55, Q92, Q101. **Owner:** W4, with W2. **Requirements:** N-8, F-2, AI-8.
- **Why it can flip ADR-001:** **Prior-verified:** the GPU Operator's OS list doesn't mention Debian; the Container Toolkit lists only Debian 11 as tested; CUDA 13.5 lists Debian 12/13; NVIDIA runs a `debian13` apt repo; Debian's own driver (550) predates RTX 50. If NVIDIA validates only Ubuntu and RHEL, the Pro and Omni tiers fight NVIDIA on every release, and N-8/F-2 push those tiers to Ubuntu or RHEL (D2). Kernel modules on a signed read-only root (DKMS) could favour bootc or sysext designs (Q101).
- **Evidence needed:** the current GPU Operator platform support page; Container Toolkit install docs; CUDA release notes; NVIDIA driver docs for nvidia-open module signing with Secure Boot; DRA driver status; a lab or cloud-GPU spike: Debian 13 + NVIDIA driver repo + toolkit + device plugin on k3s, testing time-slicing and a driver upgrade.
- **Flip condition:** a needed feature (time-slicing, MIG, CDI, DRA, Secure Boot-signed modules) fails on Debian 13 but works on a validated base.
- **Result (rev. 3 of `01`, 2026-11-11):**
  - **Answer:** Debian works for the Pro box (driver, toolkit, device plugin, time-slicing) with a recurring per-kernel module build and sign in CI; GPU-server and robotics-simulation boxes default to the Ubuntu GPU flavor after Z-01. **Rev. 3:** kernel security fixes are never held for the GPU module (7-day max lag); > 1 release-blocking module failure in 6 months moves GPU tiers to Ubuntu. 01 §4.1, §4.7.
  - **Status:** partial · blocked: founder-hardware.
  - **Refuter verdicts (lens):** cost **upheld** (cost correction), robotics **weakened**, technical **weakened**.
  - **Steelman:** [steelman-base-ubuntu](adversarial/steelman-base-ubuntu.md).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** Pro-box GPU lab (Debian 13 + NVIDIA `debian13` repo + toolkit + device plugin on k3s, time-slicing, a driver and a point-kernel upgrade); Isaac Sim headless on Debian (Z-17).

### DC-14 · Real-time kernel needs of robotics
- **Bank IDs:** Q11 (primary), Q48. **Owner:** W7, with W18. **Requirements:** M-7, N-7, F-11, F-7.
- **Why it can flip ADR-001:** if control loops can't share a node with k3s even with PREEMPT_RT, CPU isolation and the static CPU manager, the node architecture changes (a separate MCU/RTOS, or a partitioning hypervisor), and the kernel route changes (DC-21). It also affects G4 sub-check (b).
- **Evidence needed:** the kernel.org and LWN record of PREEMPT_RT's merge into 6.12; Debian `linux-image-rt` packages for amd64 and arm64; Raspberry Pi RT kernel notes; NVIDIA's L4T RT kernel docs; ros2_control real-time requirements; a founder-runnable cyclictest test under load (QEMU timing isn't meaningful).
- **Flip condition:** an RT kernel isn't available on a target flavor (for example the Pi kernel or L4T), and the alternative base provides one.
- **Result (rev. 3 of `01`, 2026-11-11):**
  - **Answer:** an RT kernel exists on every flavor; it is not a flip. RT profile ships with a per-unit 12 h cyclictest acceptance test; loops under about 1 ms default to an MCU; **rev. 3:** RT pods run in a dedicated namespace with a `SYS_NICE`-only exception for signed robot apps (Pod Security forbids it otherwise [C-DEC-015]). 01 §4.7.
  - **Status:** blocked: founder-hardware.
  - **Refuter verdicts (lens):** robotics **upheld** on the flip (weakened on usability), technical **weakened**, security **upheld**.
  - **Steelman:** none dedicated (flip not approached).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **LAB-W7-1** (12 h cyclictest under k3s + memory/GPU stressor on a Pi 5 and two Orin modules).

### DC-15 · ROS 2 tier support on the host OS
- **Bank IDs:** Q20 (primary), Q42, Q43, Q56. **Owner:** W7. **Requirements:** M-7, N-7, F-3, F-4.
- **Why it can flip ADR-001:** **Prior-verified:** ROS 2 Lyrical (LTS to May 2031) is Tier 1 on Ubuntu 26.04 and Windows 11 only; Jazzy is Tier 1 on Ubuntu 24.04; Debian is not Tier 1. If running ROS 2 in Ubuntu containers on a Debian host loses something a robot needs (DDS/Zenoh discovery across pod networks, shared memory, devices, real time), or proprietary SDKs (ZED, RealSense) need an Ubuntu host, the robot tier moves to Ubuntu, which changes D2.
- **Evidence needed:** REP 2000 (the ROS 2 platform tiers) for Jazzy, Kilted and Lyrical; containerized ROS 2 docs (Isaac ROS dev containers, rmw_zenoh router needs); vendor SDK OS-support pages; how robot companies ship (Q50).
- **Flip condition:** a capability needed on the robot only works on an Ubuntu host.
- **Result (rev. 3 of `01`, 2026-11-11):**
  - **Answer:** ROS 2 runs in containers on every flavor; no host capability needed only on Ubuntu has been found. Conditions: Fast DDS SHM asserted in use; GPU robot containers move with the host driver; robot pods host-equivalent with DDS Security or zenoh; **rev. 3:** RealSense through the UVC backend on Debian must keep metadata, sync, multi-camera and IMU, else x86 robot hosts move to Ubuntu. 01 §4.7.
  - **Status:** blocked: founder-hardware.
  - **Refuter verdicts (lens):** technical **upheld**, longevity **weakened**, security **upheld**.
  - **Steelman:** [steelman-base-ubuntu](adversarial/steelman-base-ubuntu.md) (ROS Tier 1 argument).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **LAB-W7-2** (ROS 2 + RealSense UVC on Debian 13 6.12, SHM check) and **LAB-W7-3** (Isaac ROS container on Debian vs Ubuntu, same driver).

### DC-16 · Plugin extension points on day one (A-5, A-6)
- **Bank IDs:** Q335 (primary), Q254, Q86. **Owner:** W19. **Requirements:** A-5, A-6, F-3, F-4, F-5, AI-3.
- **Why it can flip ADR-001:** some plugin types need OS-level hooks: device and driver adapters (kernel modules, udev rules), OS/image profiles (P-8), and desktop/shell plugins. If a read-only, image-based root can't load drivers or profiles without forking the image, D1/D3 must change (for example to system extensions like sysext, bootc layering, or a profile layer in the image design).
- **Evidence needed:** code-level study of how HAOS (add-ons, the hardware-access model), Olares (OAC and its linter), Umbrel, Omarchy, systemd-sysext and bootc layering add host-level capability; the plugin-type list in W19 mapped to the OS hooks each one needs.
- **Flip condition:** a day-one plugin type needs host changes that the ADR-001 image design can't provide without a fork.
- **Result (rev. 4 of `01`, 2026-11-11):**
  - **Answer:** ten extension points E1–E10, with enforcement (signed-only sysext/confext, no directory extensions, quarantine before merge, per-vendor driver packs, `module.sig_enforce=1`, TUF-style revocation). **Rev. 3:** E9 v1 adds signed configuration, a rollout/hold field and a "disable capability" entry, automated re-validation, a drilled kill list, a root lifetime and vendor-exit clause; E10 sets `force_eeprom_read=0` and per-kernel overlay CI. **Rev. 4 (E10, three more refuters):** the overlay loader sits outside the slot (Pi 5 EEPROM, Jetson QSPI UEFI), so the EEPROM/QSPI version is pinned, gated and recorded in the release manifest; CI is a kernel × firmware matrix on real boards; the trial gate checks each profile's certified overlay device nodes. On unfused Pi, E10 is a configuration control, not an integrity control [C-REF4-DC-security-007, C-REF4-DC-security-008]. Conditional on T-W19-01's security variant. 01 §4.8, §5.9.2.
  - **Status:** partial (T-W19-01…03 not run) · founder-decision Z-21, Z-22.
  - **Refuter verdicts (lens):** 28 refuters: wave 2 (15: 9 weakened, 6 upheld), rev. 3 (10, all weakened) and rev. 4 (3 on E10: [technical](adversarial/DC-E10-technical.md), [longevity](adversarial/DC-E10-longevity.md), [security](adversarial/DC-E10-security.md), all **weakened**) across technical, cost, security and longevity. E10 now has five. 01 §5.10, §5.10.1, §5.9.2.
  - **Steelman:** none (DC-16 is a design question, not a runner-up choice).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **T-W19-01** security variant (VM: unsigned image, directory and tampered image refused after reboot and RAUC slot switch); T-W19-02 (two driver packs); T-W19-03 (OneMind-signed modules under lockdown; rev. 4: shim `vendor_cert` arm first); rev. 4: E10 matrix (two EEPROM releases × two kernels × two Pi 5 board revisions, per-slot overlays, vendor updater off).

### DC-17 · One OS from Pi to enterprise (F-14)
- **Bank IDs:** Q334 (primary), Q98. **Owner:** W2, with W4. **Requirements:** F-14, M-4, N-2, P-5, H-3.
- **Why it can flip ADR-001:** gate G5 is a must-pass. If the same image family can't serve both a 4–8 GB Pi 5 and a multi-node GPU cluster, the stack fails the founder's core promise. A base that does (balena, Talos/Omni, Red Hat Device Edge → OpenShift, Ubuntu Core → Ubuntu Pro) would win (D1, D2, D4).
- **Evidence needed:** the measured footprint on the smallest node (shared with DC-10); a documented scale-out path for each candidate, from single node to HA to GPU cluster; how competitors achieve "the same product at every scale", from their docs and code.
- **Flip condition:** G5 FAILs for the proposal and PASSes for an alternative.
- **Result (rev. 3 of `01`, 2026-11-11):**
  - **Answer:** G5 is CONDITIONAL for Debian, Ubuntu and bootc alike (Jetson is a second family on every base), so the row is a tie. **Rev. 3:** the small end must be priced at 2026 DRAM prices and a Pi 5 is never the server/CA holder of a mixed cluster. 01 §3.1.5, §4.5.
  - **Status:** blocked: founder-hardware.
  - **Refuter verdicts (lens):** technical **weakened**, cost **weakened**, security **upheld**.
  - **Steelman:** [steelman-base-ubuntu](adversarial/steelman-base-ubuntu.md).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** minimum OneMind stack on a real 4 GB Pi 5 (≥ 1 GiB headroom) and the one-cluster test (one Helm set on Pi 5, x86 and Orin).

### DC-18 · Adding the chain of trust later without a layout change
- **Bank IDs:** Q206 (primary), Q207, Q208, Q209. **Owner:** W6, with W3. **Requirements:** M-2, R-1, U-4.
- **Why it can flip ADR-001:** D6 puts Secure Boot and TPM in phase 2. If adding a UKI, TPM-sealed LUKS or dm-verity to a Rugix/Debian image later needs a different partition layout or bootloader, the layout has to be chosen now, and the update tool might change (D3). Pi 5 OTP secure boot and Jetson fuses are irreversible, so their compatibility with the A/B flow must be known before any box ships.
- **Evidence needed:** Rugix boot-flow docs for systemd-boot and UKI; systemd-cryptenroll TPM2 docs; Raspberry Pi secure-boot docs (rpi-eeprom signing) against tryboot; the NVIDIA Jetson secure-boot and disk-encryption guide; how Kairos Trusted Boot, bootc and HAOS lay out disks.
- **Flip condition:** retrofitting a verified boot chain needs a reflash on the proposal's layout.
- **Result (rev. 3 of `01`, 2026-11-11):**
  - **Answer:** no layout change needed: the §4.3 layout passed Secure Boot with signed per-slot UKIs, rollback, firmware refusal and TPM unlock in emulation [C-LAB-secureboot-rauc-012…016]. **Rev. 3:** db key enrolled on every x86 box from the first shipment, an ODM db/KEK update test, and a PCR 15 volume check against volume substitution. Jetson secure boot and fTPM stay factory decisions. 01 §4.3.
  - **Status:** partial · blocked: founder-hardware.
  - **Refuter verdicts (lens):** technical **weakened**, longevity **weakened**, security **weakened** (none on the layout itself).
  - **Steelman:** [steelman-updates-rugix](adversarial/steelman-updates-rugix.md) (systemd-boot argument, answered by X-2R).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **F-SB-1…3** (real firmware, Microsoft-signed option ROMs, power cut under Secure Boot); ODM db/KEK update under power loss; **SB-5b** (PCR 15 check).

### DC-19 · The Pi 5 / CM5 pipeline on Debian
- **Bank IDs:** Q9. **Owner:** W2, with W3. **Requirements:** P-8, N-2, H-3.
- **Why it can flip ADR-001:** **Prior-verified:** stock Debian 13 doesn't officially support Pi 5; Umbrel ships Pi 5 using Raspberry Pi's kernel and firmware on Debian; Raspberry Pi OS is Debian trixie. The Lite tier depends on a pipeline that is undocumented. If it relies on fragile third-party repos, G2 becomes CONDITIONAL, which shifts the score toward bases with first-class Pi 5 support (Ubuntu, which is certified).
- **Evidence needed:** Umbrel's image build at a pinned SHA (the Pi layers in its Rugix Bakery recipes); the Raspberry Pi kernel and firmware repos and their support policy; rpi-eeprom and tryboot docs; Raspberry Pi product-lifetime statements for Pi 5 and CM5.
- **Flip condition:** the Pi 5 path can't be maintained for the support period without carrying a fork.
- **Result (rev. 3 of `01`, 2026-11-11):**
  - **Answer:** CONDITIONAL: Debian userspace + Raspberry Pi's kernel/firmware archive (umbrelOS precedent); pin the archive snapshot, keyring and EEPROM release; 16K-page CI cell; **rev. 3:** each rpi kernel bump passes a 72 h NVMe soak and boot/USB smoke test, because Raspberry Pi changes kernel majors mid-release and HAOS shipped silent NVMe corruption [C-REF3-DC-technical-022]. RAUC tryboot kit desk-checked [C-LAB-rauc-1152-017]; one trial boot on Pi 5. 01 §3.1.5, §4.1.
  - **Status:** blocked: founder-hardware.
  - **Refuter verdicts (lens):** longevity **upheld**, robotics **weakened**, technical **weakened**.
  - **Steelman:** [steelman-base-ubuntu](adversarial/steelman-base-ubuntu.md) (certified Pi 5).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **F-PI5** (`lab/rauc-1152/PI5-TRYBOOT-FOUNDER-TEST.md`: 13 steps incl. power pulls during write, trial and commit).

### DC-20 · A distro base vs a build-from-source appliance
- **Bank IDs:** Q3 (primary), Q15. **Owner:** W2, with W18. **Requirements:** F-7, M-6, R-3, RS-4.
- **Why it can flip ADR-001:** HAOS (Buildroot) and most commercial embedded and robotics products (Yocto) build from source. That gives smaller images, a more complete SBOM and less CVE noise, which the CRA will reward. Yocto is the only option with BSP layers for every target board. Buildroot + RAUC (HAOS) is the mandatory runner-up steelman candidate.
- **Evidence needed:** HAOS's build at a pinned SHA; the Yocto LTS policy (Scarthgap to April 2028, Wrynose to April 2030 per context/03); the layer index for meta-tegra, meta-raspberrypi and meta-rockchip; a lab measurement of the same minimal image (kernel, systemd, containerd, k3s) built both ways: size, SBOM, CVE count, build time.
- **Flip condition:** the from-source build is maintainable by one developer (within the C5 anchors) and scores higher on C1 and C3.
- **Result (rev. 4 of `01`, 2026-11-11):**
  - **Answer (measured in rev. 3, re-read in rev. 4):** the same minimal x86 core was built with mkosi (Debian 13.7) and with Buildroot 2025.02.19 LTS. Buildroot is 4–6× smaller, with a complete SBOM and incremental builds of 29–102 s, and has 7–18% fewer CVE IDs; the kernel is 73–80% of IDs in both [C-LAB-minimal-image-dc20-011…013, C-LAB-minimal-image-dc20-021]. **Rev. 4 (three dedicated refuters):** that metric cannot carry the pre-registered 50% threshold. Kernel counts are equal by construction, because version matching ignores the kernel config. Debian's 161 "triaged" userspace IDs are unfixed (74 not-fixed, 87 won't-fix). Two scanners agree on counts in only about 15% of images [C-REF4-DC-security-004, C-REF4-DC-security-005]. Buildroot's LTS now runs three years with paid stewards [C-REF4-DC-security-006]. So the **flip is not decided on CVEs**. **D1 (a distro base) stands on the NVIDIA/CUDA path and one-developer maintainability**, not on the patch backlog. On the Debian leg, that advantage is shown for the full-support and LTS phases only; ELTS-phase arm64 coverage is unconfirmed (DC-20 longevity refuter).
  - **Status:** partial (was "answered"; x86 only; CVE clause to be re-measured).
  - **Refuter verdicts (lens):** **dedicated (rev. 4, closes P3-9):** technical **weakened**, security **weakened**, longevity **weakened** ([technical](adversarial/DC-20-technical.md), [security](adversarial/DC-20-security.md), [longevity](adversarial/DC-20-longevity.md)). The technical and longevity files cite their sources under colliding REF4 IDs, so those sources are not ledgered.
  - **Steelman:** [W3-steelman](adversarial/W3-steelman.md) (Buildroot + RAUC).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** aarch64 (Pi 5) leg of the same scripts (DC20-R6). **New in rev. 4 (DC20-R7, proposed for 22):** re-run with a compiled-source kernel CVE filter on both legs, a second scanner (Trivy or OSV-Scanner), a VEX pass, and Debian's IDs split by tracker state. Neither is hardware-blocked.

### DC-21 · The kernel route (F-7)
- **Bank IDs:** Q324 (primary), Q10. **Owner:** W18. **Requirements:** F-7, F-15, R-3, M-6.
- **Why it can flip ADR-001:** the kernel is the biggest long-term cost and the source of most security fixes. If a CIP SLTS kernel or an upstream LTS with a OneMind config (the HAOS/ChromeOS approach) gives 10-year coverage that Debian's stock kernel doesn't, D2's "stock Debian kernel" premise changes, and so may the base (CIP Core/Isar).
- **Evidence needed:** the kernel.org LTS release schedule; the CIP SLTS schedule, reference hardware and membership tiers; the Debian kernel team's policy; how HAOS and ChromeOS configure and update their kernels (from code); the board-to-kernel map (mainline, CIP, vendor).
- **Flip condition:** stock Debian kernels can't cover the declared support period for the target boards, but a CIP or OneMind-configured LTS can at solo-developer cost.
- **Result (rev. 4 of `01`, 2026-11-11):**
  - **Answer:** K1 (the board maintainer's kernel) at launch, with a CI kernel contract. **Rev. 4:** the K2-hybrid trigger is likely **not** met. A OneMind-built shim carries OneMind's own `vendor_cert` and is signed by the db key OneMind already enrols. It makes the **stock** kernel trust OneMind's module key through the `.machine` keyring, with no console step. This is read from source and not yet run (DC-21 technical refuter; its sources are cited under colliding REF4 IDs, not ledgered). It becomes **T-W19-03's first arm**, and K2-hybrid is used only if it fails. Kernels 6.12 and 6.18 are both projected to end in Dec 2028, so K2 gains no support window [C-REF4-S1R4-technical-001]. The kernel contract treats a major kernel jump inside a distribution release as normal, with driver packs gated per kernel ABI (Raspberry Pi moved 6.12 → 6.18 in June 2026 [C-REF4-DC-longevity-021, SECONDARY: press]); the kernel CNA issues about 50–60 CVEs a week [C-REF4-DC-longevity-022, SECONDARY]. **Per base:** on the Debian leg, the kernel after 2028 is Debian's backport, and arm64 after 2030 has no owner, so a CIP 6.12 quote is brought forward. On the Ubuntu leg, Canonical carries its kernel to May 2036 under Pro [C-W2-005]. 01 §3.5, §5.9.2.
  - **Status:** partial (T-W19-03, T-W18-3/4).
  - **Refuter verdicts (lens):** dedicated round 4: technical **weakened**, longevity **weakened** ([technical](adversarial/DC-21-technical.md), [longevity](adversarial/DC-21-longevity.md)). Earlier: W18-P0-1 technical, cost and robotics **weakened**; W18-P0-2 technical, cost and robotics **weakened**.
  - **Steelman:** [steelman-kernel-runner-up](adversarial/steelman-kernel-runner-up.md) (K2-hybrid; trigger 3 met in rev. 2, now contested by the shim route).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** **T-W19-03**, shim arm first (one evening on an x86 box: build shim with `VENDOR_CERT_FILE`, sign with the db key, check `/proc/keys` for `.machine`, `modprobe` a OneMind-signed module under `lockdown=integrity`); T-W18-4 (< 1 h weekly kernel bump, including Pi); Pi 5 mainline boot test; Z-19.

### DC-22 · Platform first, or own image first?
- **Bank IDs:** Q286. **Owner:** W18, with W4 (input to `20-PLAN-180-DAYS.md`). **Requirements:** M-6, F-9, P-7, P-9.
- **Why it can flip ADR-001:** the canonical Blueprint (context/02) says to build the portable platform (Core + Client + SDK) first, then package an appliance. ADR-001 D1 says to ship our own image, including on bring-your-own hardware. If the evidence favours platform first, D1 becomes a later phase and the first 180 days change.
- **Evidence needed:** how Umbrel (Docker installer, then umbrelOS), Home Assistant (Core, then Supervised, then HAOS), Olares (script installer, no image) and Start9 (an image from day one) actually sequenced platform and image, from release history and repos; what each sequence cost them.
- **Flip condition:** proven competitors that match OneMind's constraints all went platform first, and image first measurably delays the first usable release.
- **Result (rev. 3 of `01`, 2026-11-11):**
  - **Answer:** platform first inside an image-first plan; the image from the same layers from about week 3. **Rev. 3:** the sunset applies to host-modifying script installs only; a self-contained container/VM developer preview stays after image GA (developer-only, localhost-bound, own update channel). 01 §4.4.
  - **Status:** answered · founder-decision Z-14, Z-24.
  - **Refuter verdicts (lens):** longevity **weakened**, security **upheld** (conditions), technical **weakened**.
  - **Steelman:** none dedicated.
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** n/a.

### DC-23 · A Kubernetes-native immutable OS (Talos, Kairos)
- **Bank IDs:** Q127 (primary), Q13. **Owner:** W2, with W4. **Requirements:** R-1, M-6, N-9.
- **Why it can flip ADR-001:** Talos has A/B updates and Kubernetes built in, and an API instead of a shell, which removes the OS-versus-k3s interaction problem (DC-12). **Prior-verified:** Talos v1.14.5 (MPL-2.0; Omni is BSL 1.1) has SBC overlays for Pi 4/CM4, Pi 5 and Jetson Nano only, and Orin support is an unmerged PR; Kairos v4.4.0 (Apache-2.0) doesn't support Pi 5 and commits after cloud-init.
- **Evidence needed:** current Talos and Kairos support matrices and release notes; the status of the Talos Orin PR; how host-level services (NATS leaf, Tailscale, mesh radios) run on each; Omni and Kairos licensing for a fleet plane; production adopters.
- **Flip condition:** one of them passes G2 (Pi 5 and Jetson Orin) and G5 and outscores the proposal.
- **Result (rev. 3 of `01`, 2026-11-11):**
  - **Answer:** Talos and Kairos stay rejected as the base (no official Pi 5 NVMe + Orin GPU pair); Talos's Pi 5 support moved to the upstream RP1 topology in Nov 2026 and is a 2027-Q2 watch item with Kairos #2010. 01 §5.9.1.
  - **Status:** answered (re-check 2027-Q2).
  - **Refuter verdicts (lens):** longevity **upheld**, cost **upheld**, technical **upheld**.
  - **Steelman:** none dedicated (runner-ups for S1 are Ubuntu and bootc).
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** n/a.

### DC-24 · FIPS 140-3 for the public-safety tier
- **Bank IDs:** Q215 (primary), Q183. **Owner:** W6. **Requirements:** P-5, M-4, H-3, F-14.
- **Why it can flip ADR-001:** D4 names RKE2 for the hardened tier and cites FIPS 140-2. **Prior-verified:** RKE2 has FIPS 140-2 builds (BoringCrypto). The question bank (Q183) says FIPS 140-2 sunsets in 2026; that is **UNVERIFIED** until W6 opens the NIST CMVP notice. If a FIPS/CJIS-capable tier needs a validated module that only exists on Ubuntu Pro, RHEL or SLE, the hardened tier needs a different base. That breaks "one OS" (G5) unless the main base changes too.
- **Evidence needed:** the NIST CMVP validated-modules search (the current certificates for BoringCrypto, Ubuntu Pro FIPS, the RHEL and SLE modules, and any Debian-usable module); the CMVP 140-2 sunset notice; RKE2 FIPS docs; the CJIS Security Policy's encryption section (official text).
- **Flip condition:** no validated module can run on a Debian base, and the public-safety tier is kept in scope.
- **Result (rev. 3 of `01`, 2026-11-11):**
  - **Answer:** validated FIPS 140-3 modules run on Debian (Go #5247 with vendor-affirmed OEs, OpenSSL FIPS provider), so the tier does not force a vendor base; but k3s cannot run in Go's FIPS-only mode, so the regulated tier runs RKE2 (#4968, Canal); **rev. 3:** the CJIS AES-256 path is a *candidate* day-1 answer pending SC-13 text and counsel, and CJI must not ride a WireGuard-only path. 01 §4.7.
  - **Status:** partial · blocked: founder-decision (Z-08, Z-25).
  - **Refuter verdicts (lens):** longevity **weakened**, security **weakened**, technical **upheld** on the base (day-1 weakened).
  - **Steelman:** none dedicated.
  - **Founder test (in [`22-HARDWARE-LAB-TEST-PLAN.md`](../22-HARDWARE-LAB-TEST-PLAN.md)):** n/a (buyer and counsel input).

---

## Questions considered and not selected (why)

| Bank IDs | Topic | Why not decision-critical |
|---|---|---|
| Q84–Q102 (except Q101) | AI capability layer, MCP, agents | These shape layers above the OS. They don't change the base, the update framework or the runtime. Q101's driver and model-store point is folded into DC-13. |
| Q133, Q134, Q249 | App package format, GitOps alongside the Market | They depend on D4 (DC-10). The format is a W12/W19 decision on top of whichever runtime wins. |
| Q135, Q137, Q138, Q139 | Storage, networking, mesh, NATS topology | These are choices inside the Kubernetes platform. They don't flip it. |
| Q165–Q187 (except Q167, Q168, Q183) | Certification, BOM, tariffs, ODMs, market | These affect the hardware line and go-to-market, not the software foundation. Q167 and Q168 are in DC-03/DC-04, and Q183 is in DC-24. |
| Q49–Q54, Q57–Q58 | Robot middleware, drones, safety standards, Ubuntu Core for robots | Robot-plan questions (P1). Q57's Ubuntu Core comparison is scored under S1, and Q58's power-loss realities are covered by the lab spikes in DC-12. |
| Q325 | Non-Linux kernels | Phase-1 evidence and the driver, NVIDIA and Kubernetes ecosystems make a non-Linux route very unlikely to win. W18 still answers it, with sources. If W18 finds a credible non-Linux path, it is promoted here and logged. |

## Change log

| Date | Change | Reason | By |
|---|---|---|---|
| 2026-11-10 | Initial selection: 24 questions | Brief §4; selected before any scoring | FRAME agent |
| 2026-11-11 | Revision 2 of `01`: DC-16 decided (§4.8, E1–E10) after 15 refuters (§5.10); 17 dedicated DC refuters added (§5.9): two each for DC-03, 09, 13, 14 and 19, one each for DC-07, 15, 17, 18, 22, 23 and 24. The selection of 24 questions is unchanged. Per-DC Result blocks are still to be written (critic pass-2 #7a) | Wave-2 adversarial pass; critic pass-2 N10 | HYG agent (log entry only) |
| 2026-11-11 | Revision 3 of `01`: a **Result** block (answer, status, refuter verdicts with lenses, steelman, founder test ID) added to all 24 DCs. 19 more dedicated DC refuters (DC-03, 07, 09, 13, 14, 15, 17, 18, 19, 22, 23, 24 now have three lenses each); 10 more DC-16 refuters (25 in all); steelmen for embedded etcd (DC-11) and the CRA notified body (DC-04). DC-03 priced (`lifecycle-cost-2036.md`), DC-20 measured (`lab/minimal-image-dc20/`), DC-12 re-proven with three engines and two bases. **No DC flipped ADR-001.** Shortfalls kept visible: DC-12 and DC-20 have no dedicated refuter; `22-…` does not exist yet, so founder tests are named by ID. The selection of 24 questions is unchanged | Wave-3 gap closing; critic pass-2 #7a, N7, N9, N14 | DEC agent |
| 2026-11-11 | Revision 4 of `01` (DEC4): Result blocks re-written for **DC-01, 02, 05, 06, 08, 10, 11, 12, 16 (E10), 20 and 21** with the round-4 refuter verdicts and written responses. DC-12 and DC-20 now have three **dedicated** refuters each, and E10 five (closes P3-9 for them). The eight borrowed DCs gained two dedicated round-4 refuters each (technical, longevity). Status changes: DC-08 and DC-20 answered → partial. DC-01 discloses that its own pre-registered flip margin was met on the rev-3 card, and is not met on the rev-4 card [C-DEC4-008]. The S1 decision of record is now the frozen-protocol result (Ubuntu 26.04, conditional; `01` §3.1.6). DC answers that say "on Debian" describe the Debian leg, which is the pre-registered result if W2-HW-3 fails. Every "`22-…` not yet written" label is corrected (P3-8a). **No DC answer flips an ADR-001 element on its own**; the D2 change comes from the scorecard protocol, not from a DC. The selection of 24 questions is unchanged | Critic pass-3 P3-1, P3-8(a), P3-9; S1 protocol ruling; round-4 refuters | DEC4 agent |

## Glossary

- **ADR-001:** the architecture decision record proposing the foundation (Debian 13 + Rugix + k3s/RKE2 + L4T flavor). Status: proposed, not approved.
- **Flip:** a research answer that changes one of ADR-001's decisions D1–D6.
- **Refuter:** an independent agent told to disprove a conclusion, given only the claim and its sources.
- **Steelman:** the strongest honest case for the runner-up option.
- **greenboot:** the Fedora/RHEL tool that runs health checks after an update and rolls back automatically if they fail.
- **bootc:** a tool that ships and updates the whole OS as a container (OCI) image.
- **BSP (board support package):** the vendor's kernel, drivers and firmware for a specific board, such as NVIDIA's Linux for Tegra (L4T) for Jetson.
- **CIP SLTS:** the Civil Infrastructure Platform's super-long-term-support kernels (about 10 years), aimed at industrial devices.
- **FDO:** FIDO Device Onboard, a standard for zero-touch device onboarding.
- **FIPS 140-3:** the US standard for validated cryptographic modules, required by many government buyers.
- **REP 2000:** the ROS document that lists which operating systems each ROS 2 release supports, and at which tier.
