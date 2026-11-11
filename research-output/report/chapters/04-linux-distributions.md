# Which Linux, and why Ubuntu wins narrowly {#sec-distros}

> **Explain it like I'm the founder.** The base OS is the ground floor every OneMind box stands on: the programs, the kernel, how security fixes arrive and which chips it runs on. We put 12 candidates through the same contest. First, **gates**: must-pass rules (licence, x86 + Pi 5 + Jetson, a support path to 2036, no IoT/IIoT blocker, one OS from Pi to cluster). Then a **score out of 100** with weights and rules frozen *before* scoring, one source per score. The rules say: if the **top two** are less than 3 points apart, it is a tie, settled by the decision-critical evidence between those two. Revision 4 applies that rule exactly as locked. **Ubuntu 26.04 (65) and bootc (64) tie, and the evidence gives it to Ubuntu, 6 rows to 4.** Debian (63) is third, so it is not in the tie-break. The win is narrow and conditional: Canonical must allow OneMind to ship a modified Ubuntu, or OneMind must strip the brand and rebuild (Z-01). What each pending answer will mean was written down before it arrives, and one of those answers gives Debian.

## The gates {#sec-distro-gates}

| Candidate | Licence to ship it | x86 + Pi 5 + Jetson | Support to 2036 | Verdict |
|---|---|---|---|---|
| **Debian 13** (+ L4T Jetson flavor) | Conditional: the core is free to redistribute modified [C-W2-043]; the Jetson flavor is modified Ubuntu [C-W2-050] | Pi 5 via Raspberry Pi's kernel, as umbrelOS ships [C-W2-044] | LTS to 2030-06-30; paid ELTS to 2035, quote-only and not shareable with customers [C-W2-001, C-W2-004] | Ranked |
| **Ubuntu 26.04** | Modified Ubuntu needs Canonical's approval or trademark removal and recompiled binaries [C-W2-050] | Pi 5 certified [C-W2-057]; Jetson is Ubuntu | Pro to May 2036, Pro for Devices unpriced [C-W2-005, C-W2-006] | Ranked |
| **RHEL-family bootc** (CentOS Stream / AlmaLinux / RHEL image mode) | RHEL needs an agreement; AlmaLinux free [C-W2-041] | No Pi 5 on RHEL; experimental AlmaLinux images [C-SCORE-025]; RHDE on Orin [C-W2-041] | AlmaLinux 10 to 2035-05-31 [C-W2-013] | Ranked |
| Fedora IoT, Yocto + RAUC, Buildroot + RAUC, Ubuntu Core | Pass or conditional | Conditional | Fedora: about 13 months per release [C-W2-015] | Ranked |
| Talos, Kairos, SUSE Linux Micro, balenaOS, NixOS, Alpine, CIP Core | — | **Fail**: no merged Orin support in Talos [C-W4-064]; Kairos has no Pi 5 [C-REF-DC-longevity-008] | **Fail** for short-lived ones | Out |

**The IoT/IIoT gate (G4), checked for Ubuntu in revision 4.1.** Revision 4 had scored Ubuntu's IIoT gate from a ROS 2 source only, so revision 4.1 checked its five sub-checks one by one. Result: **conditional, and no sub-check fails**. Industrial protocols pass (an MQTT 5 broker ships in 26.04 [C-G4U-003]). Real time is conditional: Canonical documents a Raspberry Pi real-time kernel for 26.04, but no one has measured it on a Pi 5 [C-G4U-001, C-G4U-002]. Zero-touch onboarding is conditional: the open-source FDO client and server are released, but only as RPM packages [C-G4U-004, C-G4U-005]. Fleet scale is conditional: Canonical's Landscape manages packages but not A/B updates, so the update server is hawkBit [C-G4U-008, C-G4U-010]. Because nothing fails, the gate does not change the result (`01` §3.1.1, `09` §1). The "one OS from Pi to cluster" gate (G5) is conditional for every base, because the Jetson flavor is NVIDIA's Ubuntu 24.04 on all of them.

## The scores {#sec-distro-scores}

Weights (frozen in `evidence/scorecard-weights.md` before scoring): longevity/support 20, hardware and robotics fit 20, security and update safety 15, proven in production 15, solo-developer operability 10, cost and licensing 10, ecosystem 10.

![Base OS scores. Grey: the revision-3 card, where every cell first carried a citation. Blue/green: the revision-4 card, after one evidence correction applied to every RAUC stack. The gold band marks 3 points from the leader, but under the frozen rule only the top two tie.](img/chart-s1-base-os.png){width=92%}

| Candidate | Longevity | HW + robotics | Update safety | Proven | Solo ops | Cost | Ecosystem | **Total** |
|---|---|---|---|---|---|---|---|---|
| **Ubuntu 26.04 + RAUC** | 3 [C-W2-005] | 3 [C-W2-026] | **4** doc-only [C-LAB-ubuntu-2604-leg-011, C-LAB-secureboot-1152-005] | 3 [C-W7-039] | 3 [C-W2-043] | 2 [C-W2-006] | 5 [C-W2-028] | **65** |
| RHEL-family bootc | 3 [C-W2-013] | 3 doc-only [C-SCORE-025] | 3 lab [C-W2-054] | 3 [C-W2-041] | 4 [C-W2-056] | 3 [C-W2-013] | 4 [C-W2-026] | **64** |
| Debian 13 + RAUC | 3 [C-W3-039] | 3 [C-W2-044] | **4** lab [C-LAB-secureboot-rauc-012…015, C-LAB-secureboot-1152-005] | 3 [C-W2-043] | 3 [C-W2-045] | 3 [C-W2-001] | 3 [C-W2-026] | **63** |
| Yocto + RAUC | 2 [C-W2-034] | 3 [C-W2-049] | **4** doc-only [C-DEC4-001] | 2 [C-W2-040] | 2 [C-W18-050] | 4 [C-W2-049] | 2 [C-W3-052] | 54 |
| Fedora IoT | 3 [C-W2-015] | 2 [C-SCORE-027] | 3 [C-W2-054] | 1 [C-W2-019] | 4 [C-W2-056] | 4 [C-W2-024] | 2 [C-W2-028] | 52 |
| Ubuntu Core | 3 [C-W2-008] | 2 [C-W2-009] | 4 [C-W2-006] | 2 [C-SCORE-023] | 2 [C-W2-006] | 2 [C-W2-006] | 3 [C-SCORE-023] | 52 |
| Buildroot + RAUC (the HAOS way) | 1 [C-W2-035] | 2 [C-W2-047] | **4** doc-only [C-DEC4-001] | 3 [C-W2-047] | 2 [C-W2-047] | 4 [C-W2-049] | 2 [C-W2-047] | 49 |

Each cell is 0–5; total = Σ(weight × score)/5 [C-DEC4-001]. **What changed from revision 3:** the update-safety cell (C3) of every RAUC stack rose from 3 to 4, because our Secure Boot lab passed on RAUC, also on the 1.15.2 OneMind ships [C-LAB-secureboot-1152-005], and the updater contest (S2) already scored RAUC 4 on that same lab [C-DEC4-002]. A proposed cut of bootc's cell to 2, for its power-cut downgrade bug, was **rejected**: S2 scores the same bootc stack 3 on the same lab row, so cutting it here alone would break the "same standard for everyone" rule. It is shown as a variant below. Full cell citations are in `evidence/scorecard-rev3.md` and `01` §3.1.6 (d).

**Shaking the weights.** Each of the seven weights was moved up and down by 5 points (14 runs). Every run is a tie, so the tie-break decides every run: **Ubuntu wins 11, Debian 2** (more weight on security, or less on solo operability) **and bootc 1** (less weight on ecosystem) [C-DEC4-006]. Under the rules that makes the result **fragile**, not settled.

## The tie-break between the top two: why Ubuntu {#sec-why-ubuntu}

The frozen rule settles a tie between the **top two only**, row by row on the decision-critical evidence (`01` §3.1.6 f). Revision 3 instead brought Debian in as a third finalist and compared all three head-to-head, which kept Debian. That step was a rule written after the scores were known and never logged, so revision 4 **withdraws** it [C-PROTO4-018].

| Question (decision-critical row) | Ubuntu 26.04 | RHEL-family bootc | Favours |
|---|---|---|---|
| Can OneMind legally ship the image? (G1) | Needs Canonical's approval, or the brand removed and binaries recompiled [C-W2-050] | AlmaLinux free to redistribute [C-STEEL4-bootc-014] | bootc |
| Cost per device at 10,000 units (DC-03) | Pro for Devices has no published price [C-W2-006] | AlmaLinux bootc costs about the same as Debian (`lifecycle-cost-2036.md`) | bootc |
| Upgrade to the next major release without a reflash (DC-05) | No production precedent found | By design, shown in our lab [C-LAB-fedora-bootc-015] | bootc |
| CRA free-software route (DC-04) | Modified-Ubuntu terms add a vendor dependency | AlmaLinux clean [C-W6-013] | bootc |
| One update framework (DC-07) | RAUC on x86 and Pi 5, NVIDIA's on Jetson [C-W3-049] | greenboot is GRUB-only; Pi experimental [C-W3-058] | Ubuntu |
| Pi 5 pipeline (DC-19) | Certified [C-W2-057], with an open boot bug on older Pi 5 firmware [C-DEC-006] | Experimental, manual steps [C-SCORE-025] | Ubuntu |
| NVIDIA GPUs on the base (DC-13) | Validated with k3s [C-W2-026]; Canonical builds signed NVIDIA modules per kernel [C-STEEL-ubu-016] | Validated for RKE2 [C-W2-026] | Ubuntu |
| ROS 2 support tier (DC-15) | Tier 1 on x86 and Pi [C-W7-027] | Tier 2 on amd64 | Ubuntu |
| Who carries NVIDIA forward? | Canonical ships CUDA in 26.04 [C-STEEL-ubu-003] | Red Hat Device Edge on Orin, paid [C-W2-041]; the free Jetson route is frozen [C-STEEL4-bootc-013] | Ubuntu |
| Lab: the same RAUC + real-k3s exam | Pass [C-LAB-ubuntu-2604-leg-011] | A power cut during finalize **silently downgraded a healthy box** [C-LAB-fedora-bootc-011] | Ubuntu |
| One OS Pi → cluster (G5), IIoT vendor process, governance, proven competitor, signed GPU modules under Secure Boot | — | — | Equal |

**Result: Ubuntu beats bootc 6–4.** **Frozen-protocol S1 result: Ubuntu 26.04 LTS + RAUC A/B, with NVIDIA's L4T Ubuntu flavor on Jetson. Fragile (11 of 14 runs). Conditional on Canonical's permission (gate G1, Z-01) and on G5.** The same rows also give the other pairs, which matter when a run flips or an answer arrives: Debian beats Ubuntu 6–5 and bootc beats Debian 6–5 [C-DEC4-006]. **Every pair is decided by one or two rows.**

| Card | Frozen rules (top-two tie, row-count tie-break) | Revision-3 three-way rule (withdrawn) |
|---|---|---|
| Revision 3 (bootc 64 · Ubuntu 62 · Debian 60) | **Ubuntu** > bootc > Debian | Debian > Ubuntu > bootc |
| Revision 4 (Ubuntu 65 · bootc 64 · Debian 63) | **Ubuntu** > bootc > Debian | No winner (a cycle) |

**The case for Debian is real, but in the rules it is only tie-break rows.** No one's permission is needed to ship its core image; the closest constraint-matched competitor (umbrelOS) runs it; and every lab ran on it, now including native Arm and Secure Boot on RAUC 1.15.2 [C-W2-043, C-LAB-aarch64-gate-004, C-LAB-secureboot-1152-005]. You can still choose Debian yourself: Z-38 sets out the options, and the choice is then logged as yours, not as the scorecard's (Chapter 14).

### Revision 4.1: three blind attacks, no change {#sec-blind-refuters}

Earlier attackers (refuters) had read the research's own reasoning. In revision 4.1 three new ones were given **only the one-line decision** and asked to disprove it with their own sources. All three returned **weakened**; none returned **refuted**, and none found a score that disagrees with its source, so no score moves (`01` §5.1.3).

| Lens | Verdict | Strongest point | What would turn it into "refuted" |
|---|---|---|---|
| Technical | Weakened | "One OS" is really a family: a 26.04 core, a 24.04 Jetson flavor whose standard support ends in 2029, and a separate Pi kernel [C-REF5-S1-technical-003, C-REF5-S1-technical-004]. RAUC has no merged Pi firmware fail-safe backend [C-REF5-S1-technical-006] | Refuted if Canonical refuses and the rebuild costs more than Debian with paid extended support, or if RAUC cannot replace Ubuntu's Pi boot fallback while a Debian A/B image passes the same power-cut test |
| Longevity / vendor | Weakened | Canonical's permission "can be revoked at any time" [C-REF5-S1L-002]; JetPack 7 stays on Ubuntu 24.04 [C-REF5-S1L-009] | Refuted by a refusal, or a revocable-only offer with an unaffordable rebuild, or a Pro for Devices price that breaks the bill of materials |
| Security | Weakened | If OneMind must strip the brand and rebuild, it loses Canonical's signed boot chain and must get its own shim signed [C-REF5S1SEC-001, C-REF5S1SEC-002]; "supported to 2036" holds only with Ubuntu Pro [C-REF5S1SEC-006] | Refuted if the rebuild route is forced with no shim plan, no hardware key store and no promise on how fast security fixes are rebuilt |

**What this changes:** no score and no ranking. It sharpens two conditions: Canonical's answer (Z-01) must cover revocation and say which route ships, and "one OS" means one app platform over a 26.04 core and a 24.04 Jetson flavor. **The decision of record stays Ubuntu 26.04 + RAUC: fragile (11 of 14 runs), conditional on Z-01 and G5.**

## What changes the result: written in advance {#sec-decision-map}

Three results are pending: **Canonical's reply (Z-01)**, **the bootc test on a real Pi 5 (W2-HW-3)**, and **Ubuntu's own Secure Boot test (U-SB)**. U-SB was added after three refuters attacked this result: Ubuntu's one-point lead rests on a Secure Boot score earned by a lab that ran **Debian** (`01` §5.1.2) [C-FIX4-010, C-FIX4-014]. On 2026-11-11, before any of the three was known, the research applied the frozen rules to each outcome and recorded the result (`01` §3.1.6 h) [C-DEC4-007]:

| Event | Card | Base-OS result |
|---|---|---|
| None of the three results yet (today) | Ubuntu 65 · bootc 64 · Debian 63 | **Ubuntu** (fragile) |
| **U-SB fails**, or passes only after a partition or bootloader change | bootc 64 · Debian 63 · Ubuntu 62 | **RHEL-family bootc**, 6–5 over Debian (bootc 11, Ubuntu 3 of 14 runs) |
| **U-SB passes** unchanged in two runs | Ubuntu 65 · bootc 64 · Debian 63 | **Ubuntu** (as today; its Secure Boot score is then lab-tested) |
| **U-SB fails and W2-HW-3 fails** | Debian 63 · Ubuntu 62 · bootc 60 | **Debian 13**, 6–5 over Ubuntu (14 of 14 runs) |
| **U-SB fails and Canonical refuses** | bootc 64 · Debian 63 | **RHEL-family bootc**, 6–5 (14 of 14 runs) |
| **W2-HW-3 fails** (bootc on a real Pi 5) | Ubuntu 65 · Debian 63 · bootc 60 | **Debian 13**, 6–5 over Ubuntu |
| **Canonical refuses**, and you reject the debranded rebuild | bootc 64 · Debian 63 | **RHEL-family bootc**, 6–5 over Debian |
| **Canonical refuses and W2-HW-3 fails** | Debian 63 · bootc 60 | Debian leads, but only in 7 of 14 runs: **unstable, your decision** |
| **Canonical agrees** and publishes a price | Ubuntu 67 · bootc 64 · Debian 63 | **Ubuntu outright** |

**U-SB was tried, and is blocked, not failed.** The test's pass/fail rule was frozen at 15:51 UTC on 2026-11-11, before any build, and the run started at once in a disposable virtual machine. It stopped because Ubuntu's download servers do not resolve from the research environment, while Debian, Fedora, kernel.org and GitHub do [C-FIX5-001, C-FIX5-002]. The rules forbid working around a block, so it was not run. **"Blocked" is not an event in the table:** no score moves, and Ubuntu's lead still rests on a Secure Boot score with no Ubuntu lab behind it. The kit is ready, with only the pre-registered Ubuntu changes [C-FIX5-003]: **you can run it as lab test LT-VM-20 on your Mac on day 1 (2026-11-16)**, about 1.5–2 hours unattended, twice (`22` LT-VM-20, `20` D1). That is decision Z-41 (Chapter 14).

**What this means in practice.** One image recipe builds an **Ubuntu 26.04 version and a Debian 13 version** side by side (switching between them costs about 40 lines of bootstrap change and no gate change [C-LAB-ubuntu-2604-leg-011]). Nothing Ubuntu-based ships before Canonical answers. The base is **locked at gate G6** (April 2027), before anyone else installs OneMind. bootc is a different build, and a box shipped on Debian or Ubuntu + RAUC cannot move to bootc without a reflash [C-STEEL4-bootc-025], so the **bootc Pi 5 test runs before week 4**.

**Variants a reviewer might prefer.** At least seven other readings change the winner (`01` §3.1.6 g, V1–V6 and V8), and none was applied, because each would treat candidates unequally or change a rule after scoring [C-DEC4-007]. Scoring "experimental" Pi 5 support as 2 for bootc gives **Debian** (V1); scoring Ubuntu's longevity cell 2 gives **bootc** (V2); keeping Ubuntu's Secure Boot cell at 3 until U-SB runs gives **bootc** (V3); cutting bootc's update-safety cell to 2 for the power-cut bug gives **Debian** (V4); the security refuter's own card gives **Debian** (V5); scoring "proven in production" on the whole stack including the update engine gives **bootc** outright (V6); and reading Canonical's condition as a fail for Ubuntu alone gives **bootc** (V8). Z-40 asks you to write these readings down **before** W2-HW-3 runs, so no rule is chosen after its result is known.

## Lifecycle and cost to 2036 {#sec-lifecycle}

![Support windows (end dates cited in 03 §6.1; bar starts approximate). Every base needs a rebase or a paid tail to reach 2036.](img/chart-lifecycle.png){width=96%}

A box sold in late 2027 with a 7–10-year promise lives to about 2035–2037. **Every** base needs either one in-place rebase (Debian 13 → 14/15, AlmaLinux 10 → 11, Ubuntu 26.04 → 28.04) or a paid tail [C-W2-001, C-W2-005, C-W2-013]. Debian releases about every two years (11 in 2021, 12 in 2023, 13 in 2025) [C-COST-007]. The Jetson Orin module itself ends in January 2032 [C-W2-030], before any OS end.

![Cost per device to 2036 in the base scenario (01 §3.1.5, evidence/lifecycle-cost-2036.md). Ubuntu's figure assumes about $60 per box for Pro for Devices, which Canonical does not publish.](img/chart-cost-2036.png){width=80%}

Ubuntu sells Pro as an annual or one-time fee for up to 10 years, with Legacy beyond [C-COST-002]; Red Hat Device Edge is "RHEL at a reduced cost" [C-COST-009]. **Labour, not licences, dominates every base**: about 1,680 base hours plus 1,480 CRA hours to 2036 on Debian at the middle assumption (a computed estimate, `evidence/lifecycle-cost-2036.md`). That is the main argument for hiring a release engineer first (Chapter 11).

## Your Fedora IoT question (F-12) {#sec-fedora-iot}

> **Short answer: Fedora IoT is a profile and a canary, not the base, today. The Red Hat bootc lineage is genuinely excellent and becomes OneMind's Industrial profile in year 2.**

**What we checked** (`03-base-os.md` §9, at Tier A depth):

- **It works.** In our VM lab, Fedora IoT bootc with greenboot booted with composefs and SELinux, accepted an update only after k3s was healthy, and rolled back a broken update with zero manual commands [C-W2-054].
- **But not fast enough or safe enough yet.** That automatic rollback took 32 minutes against a 15-minute target [C-W2-054]. A power cut during the update's "finalize" step **silently downgraded a healthy box**, twice out of two [C-LAB-fedora-bootc-011], and the default update timer re-staged a known-bad image [C-LAB-fedora-bootc-009].
- **Each Fedora release lives about 13 months** with no "stay one behind" option [C-W2-015]; Fedora 45 ends 2027-12-08.
- **Pi 5 is experimental.** Fedora 44/45 run on Pi 5 with gaps (no sound, no USB boot; CM5 still in progress, SECONDARY) [C-SCORE-027]; bootc images need a bootloader change that is still an open pull request [C-PLAN180-003].
- **FDO zero-touch onboarding is no longer a Fedora advantage:** Fedora IoT's own FDO was deprecated, and the maintained code is distro-agnostic [C-W8-042, C-W8-044].
- **The Red Hat lineage has real industrial credentials:** RHEL 9.6 and MicroShift hold IEC 62443-4-2 security level 2 [C-W2-042], and Red Hat Device Edge runs on Jetson Orin (paid) [C-W2-041].

**So:** one Containerfile builds on **AlmaLinux 10** (free) or **RHEL 10 image mode** (paid, IEC 62443 path), gated by greenboot on k3s, as the **Industrial profile** in year 2 (Z-10). CentOS Stream 10, which ends 2030-05-31, and Fedora IoT bootc build in CI only as **early-warning canaries** [C-REF4-DC-longevity-001]. Two industrial tests (FDO on both stacks, a Flight Control fleet simulation) were pulled into the first 180 days, so if the core base blocks industrial onboarding, the switch happens in year 1, not year 2 (Z-27). If bootc instead becomes the core base through the decision map above, this profile becomes the main line. This overturns ADR-001's implicit "no Fedora/RHEL role".

## One base or two? And why not build from source? {#sec-one-base}

- **Two image families plus a flavor is unavoidable** while NVIDIA owns Jetson's software: CUDA 13.5 lists Debian 13 for x86 and Arm servers but **not** for Jetson, where only Ubuntu 24.04 is listed [C-CIT4-003]. Even with an Ubuntu 26.04 core, Jetson stays on NVIDIA's own Ubuntu 24.04, a second release. OneMind keeps *one release contract* over them (Chapter 7).
- **A Jetson image that does not depend on Ubuntu** (Yocto meta-tegra with the 6.18 LTS kernel) is tested inside 180 days: it is packaged upstream for Orin and Thor, and balenaOS ships Orin on it [C-STEEL-jb-002, C-STEEL-jb-010]. It becomes the Jetson default only if CUDA, cameras and A/B all pass (Z-16).
- **Building from source the Home Assistant way is not a security shortcut.** We built the same tiny OS both ways: Buildroot is 4–6× smaller, but has only 7–18% fewer known vulnerabilities, because most of them live in the kernel either way [C-LAB-minimal-image-dc20-011]. The refuters showed that CVE count alone cannot settle this, so the distro base now stands on two other reasons: the NVIDIA/CUDA path, and what one person can maintain (`01` R4-9).

![Distro vs build-from-source, measured. Size drops a lot; known holes barely move.](img/chart-dc20.png){width=78%}

## What competitors build on (constraint fit) {#sec-distro-competitors}

| Product | Base | Constraint fit with OneMind | What OneMind takes |
|---|---|---|---|
| umbrelOS 2.0 | Debian 13, snapshot-pinned, built as a container [C-TD-umbrelos-003] | **High** (Pi 5 + x86, small team) | Image-as-container-build, over-the-air major rebase; the Debian leg's precedent |
| Home Assistant OS | Buildroot, one image per board [C-TD-home-assistant-os-003] | High for the appliance; base differs | RAUC, three boot tries, CA rotation |
| StartOS | Debian 13 via live-build [C-TD-startos-005] | Medium | Second Debian appliance precedent |
| Proxmox VE | Debian 13 + own packages [C-TD-proxmox-ve-003] | Medium | Debian holds up as an enterprise base |
| TrueNAS SCALE | Debian 12 from a frozen mirror [C-TD-truenas-scale-003] | Medium | Moved apps off Kubernetes: keep apps portable |
| Olares | Host Ubuntu or Debian, no image [C-TD-olares-007] | None for OS safety | Nothing at this layer |
| balenaOS | Own Yocto distribution [C-TD-balenaos-010] | Medium (fleet product, no k3s) | meta-tegra is shippable on Orin |
| Red Hat Device Edge | RHEL bootc on Orin [C-W2-041] | High for Industrial only | The Industrial profile |

**Requirements served:** RS-1, RS-2, R-1, R-3, M-6, M-7, N-1, N-2, N-7, N-8, H-3, P-5, F-1, F-2, F-7, F-11, F-12, F-14, D-001 (`03` §13, `01` §11).
