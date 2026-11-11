# S1 runner-up steelman: Ubuntu 26.04 LTS (+ Ubuntu Pro for Devices) as the single OneMind base

- **Role:** runner-up steelman (RESEARCH-MISSION.md §2 rule 7). This agent was told to argue **for** Ubuntu against the Tier A choice (Debian 13). It is advocacy held to the evidence rules. Each new fact was opened on 2026-11-11 and is ledgered in [`claims/STEEL-base-ubuntu.csv`](../claims/STEEL-base-ubuntu.csv) as `C-STEEL-ubu-###`. Existing ledger rows are cited by their IDs. Anything not opened is labelled SECONDARY, INFERRED or UNVERIFIED. §8 states the genuine weaknesses plainly.
- **Date:** 2026-11-11 · **Re-check by:** 2027-05-11 (kernel, BSP, NVIDIA and package facts) · 2027-11-11 (lifecycle, pricing, policy)
- **Verdict:** `steelman`
- **Decision under test:** ADR-001 D2 and S1 in [`01-FOUNDATION-DECISION.md`](../../01-FOUNDATION-DECISION.md) §3.1. After correction S1 is a tie (D 62.0 vs A 60.0, or A 60 vs D 58 in the S1-4 variant), and the §3.1.5 tie-break chose Debian 13.
- **The runner-up argued here:** **one Ubuntu LTS family on every tier**, with one vendor security feed (USN/ESM), one subscription (Ubuntu Pro) and one fleet tool (Landscape):
  - Ubuntu 26.04 LTS read-only A/B image (RAUC, the same engine and layout 01 chose) on x86 and Pi 5;
  - Ubuntu on Jetson: today Canonical's certified Jetson images or NVIDIA L4T (both Ubuntu), moving to 26.04 when Canonical's `linux-nvidia-tegra` 7.0 is released;
  - Ubuntu LTS on GPU servers and DGX-class machines;
  - Ubuntu Core 26 as an optional sealed profile for certified IIoT devices.
- **Serves:** F-11, F-14, F-1, F-2, M-6, M-7, N-2, N-8, R-1, R-3, H-1, D-001, D-002

> ### Explain it like I'm the founder
> The Debian decision does not remove Ubuntu from OneMind. 01 already puts **Ubuntu on the Jetson robots and Ubuntu on the big GPU servers**. So the real choice is not "Debian or Ubuntu". It is **"Debian + Ubuntu" or "Ubuntu only"**.
> Every NVIDIA machine you'll ever buy (Jetson, DGX Spark, DGX servers) already ships Ubuntu. ROS 2 treats Ubuntu 26.04 as its main platform. Canonical now ships CUDA and a real-time kernel inside Ubuntu itself, and has started building a 26.04 kernel for Jetson.
> If you pick Ubuntu everywhere, you learn one system, follow one security feed and pay one vendor, and only if you choose to.
> The catch (§8): Canonical's trademark rule still needs a lawyer's answer, the Pi 5 has an open boot bug on Ubuntu today, and nobody in our lab has built the Ubuntu image yet.

---

## 1. The claim this steelman makes

> **Debian's tie-break win rests on three questions (legal redistribution, Pi 5 pipeline, lab and competitor precedent). Two of them do not separate the candidates once the Debian plan is described as it really is: Debian + Ubuntu. The third is about work already done, not about the next ten years. On the structural questions (NVIDIA, robotics, F-14 one OS, IIoT certification lineage, one security feed for a solo developer), Ubuntu wins. Two corrections that apply the same reading 01 gave Debian lift Ubuntu to 64–67 vs Debian's 60–63, outside the 3-point tie band.**

## 2. F-14: "one OS from Pi to enterprise" is a one-vendor fact only on Ubuntu

What 01 §1 actually ships, compared with the Ubuntu-only plan:

| Tier | 01 decision (Debian "core") | Ubuntu-only plan | Evidence |
|---|---|---|---|
| Pi 5 / mini-PC / RTX box | Debian 13 + RAUC | Ubuntu 26.04 + RAUC | RAUC 1.15.1 is in 26.04 universe [C-STEEL-ubu-008] |
| Jetson Orin/Thor | **NVIDIA L4T Ubuntu 24.04** | Ubuntu 24.04 (L4T or Canonical-certified), then 26.04 | [C-W7-007], [C-STEEL-ubu-006], [C-STEEL-ubu-005] |
| GPU server (Omni/Cluster) | **Ubuntu LTS + RKE2** (permitted) | Ubuntu LTS (+ k3s or RKE2) | [C-W2-026] |
| DGX-class | **DGX OS = Ubuntu 24.04** | same | [C-STEEL-ubu-015] |

**The point:**
- The Debian plan is **two distributions** (Debian and Ubuntu), three release lines (13, 24.04, a server LTS), two security trackers (DSA/DLA and USN), two kernel-update streams and **two trademark regimes**.
- The Ubuntu plan is **one distribution and one security feed**, with two LTS releases until a 26.04 Jetson kernel ships.
- G5 already scores this difference: D **PASS** ("one family" [C-W2-026]), A **COND** ("Jetson is a second family" [C-W7-007]).
- For M-6 (one developer), "one feed, one package manager, one vendor to call" is the guard rail.

**The Jetson half is closer to 26.04 than 01 assumes.**
- The W2-P0-1 refuters wrote that "no Jetson module has a 26.04 image" and that Canonical's ESM "does not cover" the Jetson kernel.
- New primary evidence:
  - Canonical maintains `linux-nvidia-tegra` **in the Ubuntu archive's security pocket** for 22.04 and 24.04.
  - On 2026-10-18 Canonical put a **7.0 Tegra kernel for 26.04, with an RT flavour**, into `resolute-proposed` [C-STEEL-ubu-005].
- That kernel is Ubuntu archive software. Ubuntu Pro for Devices covers "Main and Universe for up to 10 years" [C-STEEL-ubu-014], and `linux-nvidia-tegra` sits in universe. So Pro coverage of a Canonical-built Jetson kernel is the *documented default*, not an open question. (INFERRED from component + Pro scope. It holds for Canonical's Jetson kernel, not NVIDIA's L4T kernel.)
- On that path, a single Ubuntu 26.04 family on all three board families is a **dated, visible engineering track**, not a hope. It is not released yet (§8).

## 3. NVIDIA and robotics (C2, F-2, M-7, N-8)

| Fact | Evidence |
|---|---|
| NVIDIA's GPU Operator lists **only Ubuntu** under K3s (Debian is absent) | [C-W2-026] |
| Canonical **distributes CUDA inside Ubuntu 26.04**. The archive carries CUDA 13.1 packages, and NVIDIA driver 595 arrives through the **-security** pocket | [C-STEEL-ubu-003], [C-STEEL-ubu-004] |
| Canonical builds the NVIDIA kernel modules (`linux-restricted-modules`) in step with every kernel security update | [C-STEEL-ubu-016] (Secure Boot signing INFERRED) |
| ROS 2 Lyrical: Ubuntu 26.04 **Tier 1 amd64 + arm64**. Debian 13 is Tier 3 (build from source, EOL 2028-08-09) | [C-W2-028], [C-W7-027] |
| Isaac ROS lists only Ubuntu 24.04 (x86), JetPack and DGX OS as hosts | [C-W7-031] |
| PREEMPT_RT kernel **free in main from 26.04** (`ubuntu-realtime`); `linux-realtime` 7.0 already ships security updates; Pi 5 RT variant via Pro; a Tegra RT flavour is in proposed | [C-STEEL-ubu-007], [C-STEEL-ubu-008], [C-STEEL-ubu-005] |
| Robot vendors ship Ubuntu images (Clearpath: "lightly customized" Ubuntu 24.04) | [C-W7-039] |

**Why this matters:** M-7 says robotics is "the main moat… optimized from day one". The tie-break admits Ubuntu wins DC-13 and DC-15. It then says those wins are "captured by the flavors". But that is the F-14 argument in reverse. A host can be optimized for robotics on only some flavors, and the core image the Pi greenhouse node and the mini-PC run is Debian, which robotics vendors rate Tier 3.
- **"ROS runs in containers" does not settle this.** The containers NVIDIA and ROS publish are Ubuntu userlands (C-W7-031). On an Ubuntu host the container and the host share the same libc, kernel ABI expectations and driver packaging.

## 4. F-11: IoT and IIoT without limitations

| F-11 sub-check | Ubuntu evidence | Note vs Debian |
|---|---|---|
| (b) Real time | Free PREEMPT_RT from 26.04, with 15-year security maintenance [C-STEEL-ubu-007] | Debian also ships `linux-image-rt` [C-W8-001]. Ubuntu adds a vendor-maintained RT kernel for **Tegra** [C-STEEL-ubu-005] and an Intel TCC/TSN variant |
| (c) IEC 62443 | Canonical's development process is **IEC 62443-4-1** (TÜV SÜD) [C-STEEL-ubu-010]. **ctrlX OS** (Bosch Rexroth industrial automation) is built on Ubuntu Core and is IEC 62443-4-2 SL2 (TÜV Rheinland, vendor-stated) [C-STEEL-ubu-010, -011] | Debian's equivalent is Moxa MIL4 (4-2 SL2 declaration) [C-W8-033], a vendor derivative. Debian itself has no 4-1 process certificate. Only Ubuntu has the 4-1 certificate at the **base-OS vendor** |
| CRA | Canonical says it "assumes *Manufacturer* responsibilities under the CRA for the operating system's release cycle" for Ubuntu Core 26 [C-STEEL-ubu-012] | Marketing wording; legal scope UNVERIFIED. Still, no Debian supplier offers anything like it |
| (e) Fleet scale | Landscape is included in Pro for Devices; snap store services are "from $3,000" [C-STEEL-ubu-014] | Landscape's licence is UNVERIFIED. The RAUC-based fleet integrations 01 plans (Mender, thin-edge.io, hawkBit) are distro-agnostic, so they equal Debian |
| (d) Zero-touch | No FDO in the Ubuntu base found | Same gap as Debian. **Not** an Ubuntu advantage |

**Optional sealed profile:** Ubuntu Core 26 runs on the 26.04 base, with 15-year maintenance, TPM-sealed LUKS2 and measured boot [C-STEEL-ubu-012]. It gives OneMind a **certified-lineage IIoT profile in the same family**. In the Debian plan, the nearest equivalent is the bootc track, a third family.

## 5. Longevity to 2036 (C1, G3)

- **Archive:** 26.04 standard to May 2031, ESM to May 2036, Legacy to May 2041 [C-W2-005]. Pro for Devices runs up to 10 years plus Legacy years 11–15 [C-STEEL-ubu-014].
- **Price anchors that are published:** Pro Workstation **$25/machine/year**, Server $500, Legacy +50% [C-STEEL-ubu-014]. A headless box is not a "workstation", so this does not price Pro for Devices. It does bound the order of magnitude, which G3 accepts ("CONDITIONAL… with a bounded estimate").
- **Kubernetes on the same clock:** Canonical Kubernetes 1.32 LTS has ≥ 12 years of security maintenance with Pro [C-STEEL-ubu-013]. No other base vendor in this run offers a Kubernetes lifecycle that matches the OS lifecycle.
- **The asymmetry in 01's DC-03.** 01 writes Debian as "$0 if rebased to 14/15" and Ubuntu as "$0 to 2031, then Pro for Devices". But Ubuntu also has a **$0 rebase path** (26.04 → 28.04 → 30.04, five years of free standard support each, the same A/B bundle mechanism). And Ubuntu has a paid no-rebase path to 2036+, which Debian lacks: Debian ELTS cannot be shared with customers [C-W2-004]. Read symmetrically, DC-03 is **D ≥ A**, not A > D.
- **The asymmetry in S1-1.** 01 raised Debian C1 from 2 to 3 because umbrelOS rebased 12 → 13 by OTA bundle [C-W3-039]. That evidence proves the **mechanism**: an A/B image whose payload is a newer release. The mechanism does not depend on the distro. The same RAUC bundle carrying 28.04 is the same operation. DC-05 should read **A = D** (both "by image swap, precedent on Debian"), not A > D.

## 6. Security and solo-developer operability (C3, C5)

- **C3** is engine-bound, and the engine (RAUC, verity bundles, health gate, LUKS2) is distro-agnostic. Ubuntu = Debian here. On top of that, Ubuntu's base layer adds:
  - Livepatch, in Pro [C-STEEL-ubu-014];
  - NVIDIA modules rebuilt with every kernel security update, so no DKMS build on the device [C-STEEL-ubu-016] (signing INFERRED);
  - TPM-sealed FDE and measured boot, upstream in the Ubuntu Core 26 lineage [C-STEEL-ubu-012].
- **C5:**
  - The image is built from `FROM ubuntu:26.04`, exactly like umbrelOS's `FROM debian:trixie` [C-W2-043]. The Rugix installer lists both Debian and Ubuntu [C-W2-058].
  - The founder already runs Ubuntu-based NVIDIA tooling, and every NVIDIA tutorial, Isaac ROS guide and ROS 2 binary install assumes Ubuntu. On Debian, each of them carries a "translate to Debian" tax for a solo developer.
  - One USN feed is less to track than DSA + DLA + USN.

## 7. Re-score on the frozen card (steelman estimate; W2/DEC own the official scores)

Each change applies to Ubuntu a reading that 01 already gave Debian, or meets the anchor's text with ledgered evidence.

| Cell | 01 | Steelman | Reason |
|---|---|---|---|
| D · C1 | 3 (variant 2) | **3**, variant rejected | The variant's two premises are answered. Jetson-kernel coverage: Canonical ships `linux-nvidia-tegra` in -security, and it sits in universe, which Pro covers [C-STEEL-ubu-005, -014]. Bounded price: published Pro list prices [C-STEEL-ubu-014]. Anchor 4 is not claimed (one maintainer organization) |
| D · C2 | 3 | 3 | Anchor 4 needs "one update framework across all three board families". Neither plan has it (RAUC + NVIDIA on Jetson). This becomes reachable on Ubuntu first, once the 26.04 Tegra kernel is released |
| D · C3 | 3 pending-lab | 3 pending-lab | Same engine as Debian |
| D · C4 | 3 | **4** | Anchor 4: ≥ 3 shipping products including an appliance and a robotics or industrial product, with ≥ 3 failure reports read. DGX OS (appliance OS, Spark to GB300) [C-STEEL-ubu-015], Clearpath robots [C-W7-039], NVIDIA L4T on every Jetson [C-W7-007], ctrlX OS (industrial, Ubuntu Core family) [C-STEEL-ubu-010]. Failure reports read: LP #2170238 [C-STEEL-ubu-009], LP #2127970 and LP #2150073 (W2-P0-1-longevity §2 C) |
| D · C5 | 3 | 3 | Same build pattern as Debian |
| D · C6 | 2 | **3** | Anchor 3: "free with paid support optional; standard copyleft duties only". This holds by the same rebase reading DC-03 gave Debian. The unpriced Pro for Devices is optional, as Debian ELTS is |
| D · C7 | 5 | 5 | Unchanged |

**Totals.**
- Ubuntu: C4 +3 and C6 +2 give **67.0**; C6 only gives 64.0; neither gives 62.0.
- Debian: 60.0. If the C4 reading is extended to Debian by symmetry (umbrelOS, Moxa MIL4, plus a robotics product, which W2 has not ledgered), Debian is 63.0.
- **Margins:** 4–7 points in Ubuntu's favour when both corrections apply. That is outside the tie band. If neither is accepted, the result is the 01 tie.

**Tie-break, re-read honestly** (only if the score stays a tie):

| DC | 01 says | Steelman reading |
|---|---|---|
| G1 / Q-W2-1 | **A** | **Does not separate the candidates.** 01's own Jetson and GPU-server flavours are modified Ubuntu [C-W2-050], so Q-W2-1 must be answered in the Debian plan too. The trump clause keeps copyleft rights [C-STEEL-ubu-001], and SFC says copyleft freedoms are "fully assured" [C-STEEL-ubu-002]. Pro for Devices lists "Trademark use" [C-STEEL-ubu-014]. Residual risk: non-copyleft packages (§8) |
| DC-03 | A ≈ C > D | **D ≥ A** (§5) |
| DC-05 | C > A > D | **A = D** (§5) |
| DC-07 | A = D | A = D |
| DC-19 Pi 5 | A | **A** (open bug, §8) |
| DC-13 / DC-15 | D | **D**, and it applies to the core image too, not only the flavours (§3) |
| DC-04 CRA | A | Mixed: Debian has the cleanest FOSS story; Ubuntu has a 4-1-certified supplier that claims CRA manufacturer duties [C-STEEL-ubu-010, -012] |
| Lab / proven competitor | A | A, but these record work already done (umbrelOS, our spikes) rather than ten-year fit, and RAUC/Rugix results move to Ubuntu with the engine |

## 8. Genuine weaknesses (stated plainly)

1. **Legal is not closed.** The trump clause protects copyleft rights only. SFC says permission to redistribute Ubuntu "as a whole remains in question" for non-copyleft parts [C-STEEL-ubu-002]. Policy s.3 still asks for Canonical approval [C-STEEL-ubu-001]. Shipping it as **the core image on every box** increases the exposure compared with two NVIDIA-only flavours. Counsel's answer to Q-W2-1 is required before this can win.
2. **The Pi 5 is worse on Ubuntu today.** LP #2170238 is still *New* on 2026-11-11, and the latest linux-raspi (7.0.0-1023.23, published 2026-11-10) does not fix it [C-STEEL-ubu-009]. OneMind-sold boxes can ship with a current EEPROM. Bring-your-own Pi 5s with old EEPROMs will stall at boot. umbrelOS proves the Debian + Raspberry Pi kernel route in production [C-W2-044], and no comparable Ubuntu A/B appliance on Pi 5 was found.
3. **No Ubuntu A/B appliance precedent and no lab run.** Ubuntu's appliance proof is Ubuntu Core (snaps, not RAUC), DGX OS (packages, no A/B) and Olares (installer, no OS rollback [C-TD-olares-007]). Every OneMind lab spike ran on Debian 13.
4. **Jetson is still 24.04 in practice.** The 26.04 Tegra kernel is in *-proposed*. Which SoCs it boots, and whether NVIDIA's CUDA/L4T userspace runs on it, is UNVERIFIED [C-STEEL-ubu-005]. Canonical's certified Orin images are still 22.04 [C-STEEL-ubu-006]. Until that changes, "one family" means two Ubuntu releases.
5. **The 2036 window is short and the device price is unpublished.** 26.04 ESM ends in May 2036, before G3's 2036-12-31, so it needs Legacy (+50%) or a rebase [C-W2-005, C-STEEL-ubu-014]. Pro for Devices is "contact sales" [C-W2-006].
6. **Single-vendor governance.** Canonical alone maintains the Ubuntu archive, the Jetson kernel, the RT kernel and Landscape. If Canonical changes direction, OneMind has no second supplier. Debian is community-governed.
7. **26.04 core-userland churn.** rust-coreutils and sudo-rs regressions have hit unattended-update paths (W2-P0-1-longevity §2 C). The A/B image limits the impact but does not remove it.
8. **RAUC in 26.04 is 1.15.1.** 01 requires ≥ 1.15.2 for verity bundles [C-DEC-001 context, 01 §1]. OneMind would pin its own build on either distro, so this is minor.

## 9. What would make Ubuntu the winner

Any **two** of these flip S1 to Ubuntu. All four make it decisive.
1. **Counsel or Canonical answers Q-W2-1 in writing**: either Pro for Devices "Trademark use" covers a modified OneMind image, or debranding is acceptable without recompiling non-copyleft binaries. This answer is needed for 01's Jetson and GPU-server flavours anyway.
2. **`linux-nvidia-tegra` 7.0 reaches resolute-updates/security**, and boots Orin + Thor with a working CUDA userspace in a founder test. This makes Ubuntu 26.04 one release on all three board families and unlocks C2 anchor 4.
3. **LP #2170238 is fixed** (the RPi commit is cherry-picked), and a RAUC A/B Ubuntu 26.04 image passes the existing Debian lab suite (forced rollback and power cut) on x86 and Pi 5.
4. **A quoted Pro for Devices price** within H-1 margins (Q168), or confirmation that OneMind can use the 26.04 → 28.04 rebase path at $0, as 01 assumes for Debian 13 → 14.

**Cheap step to take now:** keep the image layout and RAUC contract distro-neutral (01 already does), and add `FROM ubuntu:26.04` as a CI matrix leg beside `FROM debian:trixie`. Then the switch costs a variable, not a rewrite, whichever way the evidence breaks.
