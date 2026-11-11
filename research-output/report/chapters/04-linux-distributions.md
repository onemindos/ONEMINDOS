# Which Linux, and why Debian fits best {#sec-distros}

> **Explain it like I'm the founder.** The base OS is the ground floor every OneMind box stands on: the programs, the kernel, how security fixes arrive and which chips it runs on. We put 12 candidates through the same contest. First, **gates**: must-pass rules (licence, x86 + Pi 5 + Jetson, a support path to 2036, no IoT/IIoT blocker, one OS from Pi to cluster). Then a **score out of 100** with weights frozen *before* scoring, one source per score. Three finalists ended within three points of each other, which the rules call a tie, so the decision went to a head-to-head comparison on the evidence that is hardest to undo. **Debian 13 won that, narrowly.** Ubuntu and Red Hat's bootc stay as written, testable paths back.

## The gates {#sec-distro-gates}

| Candidate | Licence to ship it | x86 + Pi 5 + Jetson | Support to 2036 | Verdict |
|---|---|---|---|---|
| **Debian 13** (+ L4T Jetson flavor) | Conditional: the core is free to redistribute modified [C-W2-043]; the Jetson flavor is modified Ubuntu [C-W2-050] | Pi 5 via Raspberry Pi's kernel, as umbrelOS ships [C-W2-044] | LTS to 2030-06-30; paid ELTS to 2035, quote-only and not shareable with customers [C-W2-001, C-W2-004] | Ranked |
| **Ubuntu 26.04** | Modified Ubuntu needs Canonical's approval or trademark removal and recompiled binaries [C-W2-050] | Pi 5 certified [C-W2-057]; Jetson is Ubuntu | Pro to May 2036, Pro for Devices unpriced [C-W2-005, C-W2-006] | Ranked |
| **RHEL-family bootc** (CentOS Stream / AlmaLinux / RHEL image mode) | RHEL needs an agreement; AlmaLinux free [C-W2-041] | No Pi 5 on RHEL; experimental AlmaLinux images [C-SCORE-025]; RHDE on Orin [C-W2-041] | AlmaLinux 10 to 2035-05-31 [C-W2-013] | Ranked |
| Fedora IoT, Yocto + RAUC, Buildroot + RAUC, Ubuntu Core | Pass or conditional | Conditional | Fedora: about 13 months per release [C-W2-015] | Ranked |
| Talos, Kairos, SUSE Linux Micro, balenaOS, NixOS, Alpine, CIP Core | — | **Fail**: no merged Orin support in Talos [C-W4-064]; Kairos has no Pi 5 [C-REF-DC-longevity-008] | **Fail** for short-lived ones | Out |

## The scores {#sec-distro-scores}

Weights (frozen in `evidence/scorecard-weights.md` before scoring): longevity/support 20, hardware and robotics fit 20, security and update safety 15, proven in production 15, solo-developer operability 10, cost and licensing 10, ecosystem 10.

![Base OS scores. Grey: the workstream's first card. Blue/green: revision 3, where every cell carries a citation. The three leaders sit inside the tie band.](img/chart-s1-base-os.png){width=92%}

| Candidate | Longevity | HW + robotics | Update safety | Proven | Solo ops | Cost | Ecosystem | **Total** |
|---|---|---|---|---|---|---|---|---|
| RHEL-family bootc | 3 [C-W2-013] | 3 doc-only [C-SCORE-025] | 3 lab [C-W2-054] | 3 [C-W2-041] | 4 [C-W2-056] | 3 [C-W2-013] | 4 [C-W2-026] | **64** |
| Ubuntu 26.04 | 3 [C-W2-005] | 3 [C-W2-026] | 3 [C-W2-058] | 3 [C-W7-039] | 3 [C-W2-043] | 2 [C-W2-006] | 5 [C-W2-028] | **62** |
| **Debian 13 + RAUC** | 3 [C-W3-039] | 3 [C-W2-044] | 3 lab [C-LAB-rauc-015] | 3 [C-W2-043] | 3 [C-W2-045] | 3 [C-W2-001] | 3 [C-W2-026] | **60** |
| Fedora IoT | 3 [C-W2-015] | 2 [C-SCORE-027] | 3 [C-W2-054] | 1 [C-W2-019] | 4 [C-W2-056] | 4 [C-W2-024] | 2 [C-W2-028] | 52 |
| Ubuntu Core | 3 [C-W2-008] | 2 [C-W2-009] | 4 [C-W2-006] | 2 [C-SCORE-023] | 2 [C-W2-006] | 2 [C-W2-006] | 3 [C-SCORE-023] | 52 |
| Yocto + RAUC | 2 [C-W2-034] | 3 [C-W2-049] | 3 [C-W2-049] | 2 [C-W2-040] | 2 [C-W18-050] | 4 [C-W2-049] | 2 [C-W3-052] | 51 |
| Buildroot + RAUC (the HAOS way) | 1 [C-W2-035] | 2 [C-W2-047] | 3 [C-W2-047] | 3 [C-W2-047] | 2 [C-W2-047] | 4 [C-W2-049] | 2 [C-W2-047] | 46 |

Each cell is 0–5; total = Σ(weight × score)/5. Full cell citations and the 14-run sensitivity analysis are in `evidence/scorecard-rev3.md`.

## The tie-break: why Debian {#sec-why-debian}

When three candidates are within reach of a tie, each pair is compared on the decision-critical evidence (`01` §3.1.5). A candidate that beats every other one head-to-head wins.

| Question | Ubuntu 26.04 | Debian 13 | RHEL bootc | Favours |
|---|---|---|---|---|
| Can OneMind legally ship the image? | Needs Canonical's permission [C-W2-050] | Yes, as an appliance already does [C-W2-043] | AlmaLinux free; RHEL needs an agreement [C-W2-041] | Debian ≈ bootc > Ubuntu |
| Upgrade a fielded box to the next major release without a reflash? | No precedent found | umbrelOS did Debian 12 → 13 over the air [C-W3-039] | By design [C-LAB-fedora-bootc-015] | bootc > Debian > Ubuntu |
| Pi 5 in production | Certified, but an open boot regression on older Pi 5 firmware [C-DEC-006] | Shipped by umbrelOS [C-W2-044] | Experimental, manual steps [C-SCORE-025] | Debian |
| NVIDIA GPUs on the base | Validated with k3s [C-W2-026] | Works, but NVIDIA's DKMS build broke on routine Debian kernels [C-REF-DC-cost-009] | Validated for RKE2 [C-W2-026] | Ubuntu |
| Industrial vendor process (IEC 62443-4-1) | Canonical audited by TÜV SÜD [C-STEEL-ubu-010] | Vendor declarations only [C-REF-W8-security-006] | RHEL 9.6 SL-C 2 [C-STEEL-IIOT-008] | Ubuntu ≈ bootc |
| Lab: same RAUC + real-k3s exam | Pass [C-LAB-ubuntu-2604-leg-011] | Pass [C-LAB-rauc-1152-011] | A power cut during finalize **silently downgraded a healthy box** [C-LAB-fedora-bootc-011] | Debian = Ubuntu > bootc |
| Second supplier if the vendor changes course | Canonical alone | Community-governed; LTS by paid Freexian contributors [C-REF-DC-cost-003] | Red Hat downstream risk | Debian |
| Proven constraint-matched competitor | None | umbrelOS 2.0 [C-W2-043] | RHDE (vendor, no Pi) | Debian |

**Result:** Debian beats Ubuntu **7–4**, Ubuntu beats bootc **6–4**, and Debian draws bootc **5–5**, a draw Debian takes because bootc's wins sit on the industrial and GPU tiers that already have their own flavors, while Debian's sit on the Pi 5 tier no flavor covers for bootc. **No finalist beats Debian head-to-head.**

**Debian wins on what is hard to undo:** no one's permission is needed to ship the core image; the closest proven competitor runs it; every lab ran on it; and no single vendor controls it. **Ubuntu wins where NVIDIA rules**, which is why Jetson and GPU-server boxes use Ubuntu-based flavors.

**What would flip it (written in advance):**

- **To Ubuntu:** Canonical grants written redistribution permission (Z-01) **plus** either a sensible Pro for Devices price **or** NVIDIA's Jetson kernel with CUDA on Ubuntu 26.04. The Ubuntu CI leg is already proven runnable (about 40 lines of bootstrap change, no gate change) [C-LAB-ubuntu-2604-leg-011], so the switch is a build variable.
- **To bootc:** an AlmaLinux bootc image passes the gated-update test on a real Pi 5 (W2-HW-3), **and** the greenboot silent-downgrade bug is fixed upstream [C-LAB-fedora-bootc-013], **and** a Pi commit path needs no manual `sync`.

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

**So:** one Containerfile builds on CentOS Stream 10 / AlmaLinux 10 (free) and RHEL 10 image mode (paid, IEC 62443 path), gated by greenboot on k3s, as the **Industrial profile** in year 2 (Z-10); Fedora IoT bootc builds in CI as an **early-warning canary**. Two industrial tests (FDO on both stacks, a Flight Control fleet simulation) were pulled into the first 180 days, so if Debian blocks industrial onboarding, the switch happens in year 1, not year 2 (Z-27). This overturns ADR-001's implicit "no Fedora/RHEL role".

## One base or two? And why not build from source? {#sec-one-base}

- **Two image families plus a flavor is unavoidable** while NVIDIA owns Jetson's software: CUDA 13.5 lists Debian 13 for x86 and Arm servers but **not** for Jetson [C-STEEL-jb-015]. OneMind keeps *one release contract* over them (Chapter 7).
- **A Jetson image that does not depend on Ubuntu** (Yocto meta-tegra with the 6.18 LTS kernel) is tested inside 180 days: it is packaged upstream for Orin and Thor, and balenaOS ships Orin on it [C-STEEL-jb-002, C-STEEL-jb-010]. It becomes the Jetson default only if CUDA, cameras and A/B all pass (Z-16).
- **Building from source the Home Assistant way is not a security shortcut.** We built the same tiny OS both ways: Buildroot is 4–6× smaller, but has only 7–18% fewer known vulnerabilities, because most of them live in the kernel either way [C-LAB-minimal-image-dc20-011].

![Distro vs build-from-source, measured. Size drops a lot; known holes barely move.](img/chart-dc20.png){width=78%}

## What competitors build on (constraint fit) {#sec-distro-competitors}

| Product | Base | Constraint fit with OneMind | What OneMind takes |
|---|---|---|---|
| umbrelOS 2.0 | Debian 13, snapshot-pinned, built as a container [C-TD-umbrelos-003] | **High** (Pi 5 + x86, small team) | Debian core, image-as-container-build, over-the-air major rebase |
| Home Assistant OS | Buildroot, one image per board [C-TD-home-assistant-os-003] | High for the appliance; base differs | RAUC, three boot tries, CA rotation |
| StartOS | Debian 13 via live-build [C-TD-startos-005] | Medium | Second Debian appliance precedent |
| Proxmox VE | Debian 13 + own packages [C-TD-proxmox-ve-003] | Medium | Debian holds up as an enterprise base |
| TrueNAS SCALE | Debian 12 from a frozen mirror [C-TD-truenas-scale-003] | Medium | Moved apps off Kubernetes: keep apps portable |
| Olares | Host Ubuntu or Debian, no image [C-TD-olares-007] | None for OS safety | Nothing at this layer |
| balenaOS | Own Yocto distribution [C-TD-balenaos-010] | Medium (fleet product, no k3s) | meta-tegra is shippable on Orin |
| Red Hat Device Edge | RHEL bootc on Orin [C-W2-041] | High for Industrial only | The Industrial profile |

**Requirements served:** RS-1, RS-2, R-1, R-3, M-6, M-7, N-1, N-2, N-7, N-8, H-3, P-5, F-1, F-2, F-7, F-11, F-12, F-14, D-001 (`03` §13, `01` §11).
