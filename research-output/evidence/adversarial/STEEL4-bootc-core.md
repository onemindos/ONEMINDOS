# Steelman 4: RHEL-family bootc as the OneMind OS core (S1 candidate C)

**Date:** 2026-11-11 · **Owner:** STEEL4-bootc (independent steelman, RESEARCH-MISSION.md §2 rule 7, the mandatory "steelman of the runner-up") · **Role:** told to argue **for** candidate C, and to state its weak spots honestly
**Candidate under argument:** S1 candidate C, "RHEL-family bootc (+RHDE on Orin)", the top raw score on the fully cited card (C 64.0 · D 62.0 · A 60.0) [C-SCORE-025; `evidence/scorecard-rev3.md` §3.2]
**Inputs read:** RESEARCH-MISSION.md, `00-EXECUTIVE-SUMMARY.md`, `01-FOUNDATION-DECISION.md` §3.1, `evidence/scorecard-weights.md` (frozen v1.0 and §8), `evidence/scorecard-rev3.md`, `evidence/critic/pass-3.md`, and the existing claim rows for C. **Not read:** any other file in `evidence/adversarial/` (as instructed), so this file is independent of the earlier W2 and IIoT steelmen.
**New evidence:** 25 claims in `evidence/claims/STEEL4-bootc.csv` (C-STEEL4-bootc-001…025), sources in `evidence/sources/STEEL4-bootc.md`. Older claim IDs are reused where the run already verified the fact.
**Serves requirements:** F-12, F-14, F-11, F-2, F-1, N-2, M-7, M-8, R-1, R-3, H-1, H-3, D-001, RS-1, RS-4

> ### Explain it like I'm the founder
> **bootc** turns a normal container image (the same kind of file your apps already are) into the whole operating system of a box. You write a `Containerfile`, build it on your Mac, push it to a registry, and every box pulls the new OS, keeps the old one, and can go back. Red Hat, AlmaLinux, Rocky Linux's vendor CIQ and Fedora all ship this the same way.
>
> **The best case for it:** moving a box to the next major OS version is a single built-in command, not a project. It works offline from a USB stick. There's a published security-support date (AlmaLinux 10 to May 2035) and nobody's permission is needed to ship it. It has a stronger security ceiling than our current plan: the root filesystem can be sealed with a signature checked at boot. Three enterprise vendors and a CNCF project stand behind the update tool.
>
> **The honest catch:** on the **Raspberry Pi 5**, everything rests on **one volunteer's** repo and a tiny bootloader script. The free **Jetson** route is a frozen 2024 package set, so Jetson needs NVIDIA's own Ubuntu or a paid Red Hat subscription. The one lab power-cut bug we found is still unfixed upstream.
>
> **What this means for you:** bootc isn't a worse choice. It's a choice that **one Pi 5 test can win or lose**, and it has to be made **before the first box ships**. You can't move a shipped box from Debian + RAUC to bootc without reflashing it.

---

## 1. The case in one paragraph

If OneMind OS were built today by someone who had never seen ADR-001, the RHEL-family bootc stack would be the obvious first draft. Its OS **is** an OCI container image, so OneMind gets one artefact type, one registry, one signing tool and one CI pipeline for the OS and the Market apps alike [C-W2-056, C-STEEL4-bootc-022]. Major-version rebases are a built-in verb that our lab ran in place [C-LAB-fedora-bootc-015]. The free tier has a dated end of security support [C-W2-013], which a CRA declaration needs [C-W6-002, C-W6-005]. It needs no vendor permission to ship [C-STEEL4-bootc-014]. Three enterprise vendors ship the update tool, which is a CNCF project [C-STEEL4-bootc-017, C-STEEL-IIOT-009]. Its industrial pieces (FDO onboarding, greenboot health checks, an Apache-2.0 fleet manager with TPM identity) are already signed distro packages [C-STEEL-IIOT-001, C-STEEL-IIOT-002, C-STEEL-IIOT-005, C-STEEL-IIOT-006]. NVIDIA and Red Hat committed to Day-0 support for new NVIDIA silicon on RHEL [C-STEEL4-bootc-011]. On the frozen protocol it is the raw leader in **14 of 14** sensitivity runs [`scorecard-rev3.md` §3.3]. The Debian verdict rests on an unlogged pairwise tie-break rule [`critic/pass-3.md` P3-1]. Under the critic's second reading, where an unmet third-party condition disqualifies Ubuntu, C wins S1 **outright** [P3-1].

## 2. What candidate C actually is (per board)

A steelman must argue for a concrete stack, not a brand. This is the version I defend:

| Board | OS image | Update and rollback | Source | Cost |
|---|---|---|---|---|
| x86_64 (Beelink, Dell, mini PC, GPU server) | `FROM` AlmaLinux 10 bootc (CentOS Stream 10 as the early-warning CI leg; Fedora as the canary) | `bootc upgrade` / `switch`, greenboot health gate (GRUB) | [C-W2-012, C-STEEL-IIOT-002, C-W3-058] | $0; RHEL optional per buyer |
| Raspberry Pi 5 | AlmaLinux 10 bootc RPi image: AlmaLinux-signed Raspberry Pi kernel, Pi `tryboot` via `rpi-bootc-bootloader` | bootc staging plus a Pi tryboot "try once, fall back" boot | [C-STEEL4-bootc-003, C-STEEL4-bootc-004, C-SCORE-026] | $0 |
| Jetson Orin | **Either** NVIDIA L4T Ubuntu (the same flavor split candidate A uses) **or** Red Hat Device Edge, paid, for buyers who want one vendor | NVIDIA A/B, or bootc under RHDE | [C-W2-041, C-STEEL4-bootc-012] | $0 / RHDE subscription [C-COST-009] |
| Apps on every board | k3s (with `k3s-selinux`) and the Market; core pods as **logically bound images**, so the OS image pins them | rolled back together with the OS | [C-W2-052, C-STEEL4-bootc-022] | $0 |
| Fleet (optional) | Flight Control (Apache-2.0) | TPM-backed device identity | [C-SCORE-014, C-STEEL-IIOT-006] | $0 self-hosted |

This is **one image family on x86 and Pi 5** plus a Jetson flavor split, the same split shape as Debian's (A), and with fewer distributions than Ubuntu's (D), which also needs a separate Jetson GPU path [`01` §3.1.5, DC-17].

## 3. The ten strongest arguments for C

**3.1 Rebase is the product's native verb (DC-05).** Every base has to reach 2036 through at least one major-version move. On Debian that move is a project: umbrelOS did one Debian 12 → 13 OTA rebase [C-W3-039], and T-W3-04 still has to time it in founder-weeks. On bootc it's `bootc switch` to a new image tag. Our lab ran it in place, kept `/var` data and switched back [C-LAB-fedora-bootc-015]. Upstream promises that every existing system can be upgraded in place across future changes [C-W2-024]. The run's own tie-break already gives DC-05 to C [`01` §3.1.5].

**3.2 One artefact from Mac to fleet.** The OS is a container image. A OneMind `Containerfile` built in an aarch64 Lima VM on the founder's Mac in about 1–2 minutes [C-W2-056], against the C5 anchor-3 target of "under 1 h per image". The same registry, mirroring config and signature policy serve OS and apps [C-STEEL4-bootc-020, C-STEEL4-bootc-021]. **Logically bound images** go further: the host image names the exact app images it boots with, and bootc pulls them during the upgrade, keeps them for rollback and cleans them up [C-STEEL4-bootc-022]. A RAUC + k3s design has to build that "OS and core pods move together" guarantee by hand.

**3.3 Offline and air-gapped updates are built in.** Copy the OS image to a USB stick as an OCI directory, run `bootc switch --transport oci` once, then `bootc upgrade --apply` from the stick. systemd units can automate it, on LUKS media if needed [C-STEEL4-bootc-021]. That serves the off-grid, community-resilience and public-safety buyers directly (F-13, F-11).

**3.4 A published support date, and a paid path beyond it.** AlmaLinux 10 has security support to **2035-05-31** [C-W2-013] and lists aarch64 as a supported architecture in every 10.x release [C-STEEL4-bootc-016]. RHEL 10 has a ten-year life cycle, then ELCP: 6 years for even minors and 9 years for the terminal 10.10, plus renewable Long-Life terms after that [C-STEEL4-bootc-010]. A buyer who needs a box frozen past 2035 therefore has a vendor to pay, which the Debian route doesn't offer as a product (01 notes ELTS is not usable for a fleet as-is [C-W2-004]). For the CRA, Art. 13(8) asks the manufacturer to weigh "the support periods of integrated third-party components providing core functions" [C-W6-002], and Art. 13(19) requires a dated end at purchase [C-W6-005]. A component with a published month and year is the easiest kind to declare.

**3.5 No permission step, and the rules are written down.** AlmaLinux allows commercial redistribution of official releases with its marks. A modified build must not call itself AlmaLinux, but may say it is "derived from the source code for the AlmaLinux OS distribution" [C-STEEL4-bootc-014]. That is the Debian-style story, not the Canonical one, where a modified image needs approval or trademark removal **and recompiled binaries** [C-W2-050, C-LIC-011]. The update stack is permissive: bootc MIT/Apache-2.0, greenboot-rs BSD-3-Clause, Flight Control Apache-2.0 [C-LIC-040]. **Correction to the run's record:** the Pi bootloader script that ships inside the image is licensed "BSD 2 Clause or Apache 2.0. Your choice." [C-STEEL4-bootc-006]. C-SCORE-026's "no licence detected (NOASSERTION)" is GitHub's detector failing on a non-standard file, not a missing licence, so it is not a G1 problem.

**3.6 A higher security ceiling than the current plan.** bootc's composefs backend can **seal** an image: fs-verity is enforced, and the expected root digest sits inside a UKI signed for Secure Boot, so a tampered root does not boot. It's supported with systemd-boot and covered by bootc's stability promise [C-STEEL4-bootc-018]. A shipping product already boots this way next to Windows [C-STEEL4-bootc-017]. That is the "verity root" that C3 anchor 5 asks for and that RAUC's plan does not have yet [`01` §3.2, S2-2]. Around it: SELinux by default (k3s ships `k3s-selinux`, used in our lab [C-W2-052]), and RHEL 9.6 and MicroShift 4.21 hold IEC 62443-4-2 SL-C 2 certificates [C-W2-042].

**3.7 Governance: several vendors and a foundation, not two engineers.** bootc had 59 human commit authors in a year and OSTree 30 [C-W3-068]. Red Hat, CIQ (Rocky Linux), the AlmaLinux Atomic SIG, Universal Blue and others ship it as vendors [C-STEEL4-bootc-017], and it is a CNCF Sandbox project [C-STEEL-IIOT-009]. Compare RAUC, maintained mainly by two engineers who write 86% of the commits [C-REF-W3-longevity-001]. AlmaLinux is run by a foundation that, since 2023, targets **binary** (not bug-for-bug) compatibility with RHEL, so it can ship fixes ahead of Red Hat [C-STEEL4-bootc-015]. If Red Hat changes course, AlmaLinux, CIQ and Fedora remain.

**3.8 NVIDIA treats this family as first class on servers.** NVIDIA's CUDA repository has `rhel10` (and `fedora45`) trees [C-SCORE-030], and the Container Toolkit installs with `dnf` [C-SCORE-031]. The GPU Operator matrix lists RHEL 10.0–10.2 for upstream Kubernetes and RKE2 [C-W2-026]. In January 2026 Red Hat announced "RHEL for NVIDIA", with Day-0 support for new NVIDIA architectures starting with Rubin and OpenRM drivers plus CUDA in RHEL repositories [C-STEEL4-bootc-011]. For the Omni/Cluster tier and robotics simulation, this is a vendor-backed path that Debian lacks (Isaac Sim lists only Ubuntu and Windows hosts [C-REF-DC-robotics-013], and NVIDIA's DKMS build broke on routine Debian 13 point kernels [C-REF-DC-cost-009]).

**3.9 IIoT pieces are already in the free distribution.** CentOS Stream 10 and AlmaLinux 10 ship go-fdo-client and go-fdo-server (FIDO Device Onboard: zero-touch onboarding), greenboot and bootc as signed packages [C-STEEL-IIOT-001, C-STEEL-IIOT-002]. Flight Control gives TPM-backed LDevID device identity [C-STEEL-IIOT-006] and a device simulator for fleet-scale load tests [C-STEEL-IIOT-007]. ROS 2 Lyrical lists RHEL 10 at Tier 2 (amd64), above Debian Trixie's Tier 3 [C-W2-028].

**3.10 Real-time kernel packages exist on both CPU architectures in the family.** CentOS Stream 10 ships `kernel-rt` for **aarch64 and x86_64** (6.12.0-281.el10) [C-STEEL4-bootc-008], and AlmaLinux 10 ships it for x86_64 [C-SCORE-029]. That meets G4(b)'s "PREEMPT_RT or isolated-core path" on x86 and on generic arm64 servers.

## 4. The weak spots, stated without spin

| # | Weak spot | Evidence | How bad | Mitigation a bootc plan would carry |
|---|---|---|---|---|
| W1 | **Pi 5 rests on one person.** The AlmaLinux RPi bootc repo has 75 commits from one contributor (next: 12); the 60 newest commits are all his; 12 stars, 0 forks; last release 2026-03-16 [C-STEEL4-bootc-001]. He also wrote the 1-star tryboot script it ships [C-SCORE-026]. The repo calls itself "experimental" [C-SCORE-025]. CM5 support has been an open issue since 2025-12-13 [C-STEEL4-bootc-002]. Fedora IoT's own Pi bootc bug #82 and its bootupd fix #935 are still open [C-STEEL4-bootc-024]. | Primary metadata | **Severe.** By the bus-factor test that moved the engine from Rugix to RAUC, this route fails on its own [`01` §3.2 DC-06]. | OneMind owns its fork of both repos (about 40 lines of Containerfile plus one shell script), as it already owns a custom RAUC tryboot backend [C-LAB-rauc-1152-017]. Ask AlmaLinux (via outreach drafts, not sent) whether its Atomic or ARM SIG will adopt the repo |
| W2 | **The Pi kernel is AlmaLinux's, and it has lagged.** Good: it is a signed package from an official AlmaLinux repo, and the newest build appeared one day after Raspberry Pi's tag (6.12.115, 2026-11-04) [C-STEEL4-bootc-004]. Bad: the upstream base sat at 6.12.47 from 2025-10 to 2026-07, about ten months [C-STEEL4-bootc-005]. | Primary listing; rebuild contents not inspected | Medium | Track the AlmaLinux Pi kernel publication date in CI; fall back to building Raspberry Pi's kernel (route K3) if a gap passes 30 days |
| W3 | **The Pi commit step is manual, and the build is unpinned.** Committing a good tryboot needs `rpi-bootc-bootloader sync` [C-SCORE-026]. The image build downloads that script by tag with no checksum [C-STEEL4-bootc-003]. On Pi 5 the firmware gives **one** trial boot under any engine [C-LAB-rauc-1152-012]. | Primary code | Medium | Call `sync` from greenboot's success hook (to be built and tested; this is the open item in `01`'s flip list); pin the script by commit hash |
| W4 | **Jetson's free route is frozen.** NVIDIA's only public RHEL Jetson repo is `rhel-9.4/r36.3.1`, built 2024-07-02, unsigned (`gpgcheck=0`), and its kernel module requires one exact RHEL 9.4 kernel [C-STEEL4-bootc-013]. The maintained route is **paid** RHDE on Orin, aligned with RHEL 9.8, with no Thor or RHEL 10 mentioned [C-STEEL4-bootc-012]. RHEL 9 is a 2022 major, so it ends around 2032 (AlmaLinux 9's matching date is 2032-05-31 [C-STEEL4-bootc-016]; derived). | Primary | **High for the "one OS" story, neutral against A.** C on Jetson is the same L4T flavor split as A, plus an optional paid single-vendor SKU A doesn't have | Ship the L4T flavor exactly as A plans; offer RHDE only to a buyer who pays for it |
| W5 | **The power-cut downgrade is unfixed.** A power cut during finalize silently downgraded a healthy box in 2/2 lab runs [C-LAB-fedora-bootc-011]. Upstream #219 is still open with no fix PR among the 15 newest [C-STEEL4-bootc-024]. A gated rollback took 32 min against a 15-min target, dominated by the check timeout [C-W2-054]. | Lab + primary | Medium: it's a one-version downgrade, not a brick, and the fix proposed in #219 is small [C-LAB-fedora-bootc-012] | Carry a OneMind greenboot patch until upstream merges one; re-time the gate with a shorter timeout (untested) |
| W6 | **The security ceiling and automatic rollback don't live in the same backend today.** Sealed images need the composefs backend [C-STEEL4-bootc-018], which has no boot counting yet [C-STEEL4-bootc-019]; greenboot's boot counting is GRUB/ostree [C-W3-058]. The backend is fixed at install by the image, and I found no documented in-place move from ostree to composefs [C-STEEL4-bootc-025]. | Primary docs | **Medium-high.** C3 stays at 3. Choosing ostree now and sealing later is probably a reinstall, the very thing anchor 4 penalises | Day 1 uses composefs + systemd-boot with **systemd-boot's own boot counting** plus a OneMind health unit (untested; a founder or VM spike) |
| W7 | **Signatures are opt-in.** bootc's default container policy does not require signed images [C-STEEL4-bootc-020]. | Primary docs | Low: a config file | Ship `policy.json` requiring cosign signatures for the OneMind registry |
| W8 | **No upstream support window.** bootc releases weekly from `main`, has no release branches and no backports, and has deferred a support-duration policy [C-STEEL4-bootc-023]. | Primary | Low-medium: the distro's bootc package inherits the distro's lifecycle; OneMind must not ship upstream bootc directly | Take bootc only from AlmaLinux/CentOS packages |
| W9 | **RT on arm64 is not in the free stable tier.** AlmaLinux 10's RT repo is x86_64 only [C-STEEL4-bootc-007]; aarch64 `kernel-rt` exists only in CentOS Stream 10 [C-STEEL4-bootc-008], which ends 2030-05-31 [C-STEEL4-bootc-009]. The Pi kernel is a separate package with no RT build in that repo [C-STEEL4-bootc-004]. User measurements of Pi 5 PREEMPT_RT are poor under any distro [C-REF-DC-robotics-006]. | Primary + forum | Low against A (Debian's Pi kernel is Raspberry Pi's too); real for "RT robots on Pi" generally | Hard real time goes to an MCU/PLC (G4(b)); soft RT on Jetson or x86 |
| W10 | **Lifecycle edges.** AlmaLinux minors end when the next ships [C-STEEL4-bootc-016], so images must keep moving (fine for an image OS). AlmaLinux 10 ends 2035-05-31 [C-W2-013], so 2036 needs an EL11 rebase, the same as Debian needs 14/15. CentOS Stream 10 ends 2030 [C-STEEL4-bootc-009]. AlmaLinux depends on RHEL-compatible sources; its 2023 move to binary compatibility shows that dependency can shift [C-STEEL4-bootc-015]. | Primary | Low-medium | Rebase drill on bootc (cheap, see 3.1); CentOS Stream only as a CI canary |
| W11 | **No constraint-matched appliance.** The direct adopters are mostly desktops and vendor products; none is a Pi-class home/edge appliance like umbrelOS or HAOS [C-STEEL4-bootc-017, `01` §9]. | Primary | Medium (C4 = 3) | None but time; note A's exact stack (Debian + RAUC) has no product either [C-DEC-013] |
| W12 | **GPU Operator on k3s lists only Ubuntu** [C-W2-026]. | Primary | Low: affects A equally; matters for Omni/Cluster, where RHEL's RKE2 row exists | RKE2 or upstream Kubernetes on the GPU tier, which `01` already allows |

## 5. The scorecard, re-read by the steelman (no weight or anchor change)

I don't ask for any cell to move up. The frozen anchors are stricter than my argument, and that is the point of freezing them.

- **C2 = 3 is defensible but fragile.** Each clause of anchor 3 has a source [`scorecard-rev3.md` §3.2]. My new evidence cuts both ways. It strengthens "documented path" (an official, signed AlmaLinux Pi kernel repo that tracks Raspberry Pi tags [C-STEEL4-bootc-004]; RT on aarch64 in the family [C-STEEL4-bootc-008]; a redistributable bootloader [C-STEEL4-bootc-006]). It weakens "path" as a long-term promise (bus factor 1 [C-STEEL4-bootc-001]; a frozen free Jetson route [C-STEEL4-bootc-013]). **Anchor 4 is out of reach.** No vendor-validated NVIDIA on the k3s stack, and no single update framework across all three boards.
- **C3 = 3 stays.** W6 is why: anchor 4 needs a Secure Boot path with no later layout change, and today's rollback path (ostree + greenboot + GRUB) and sealed path (composefs + systemd-boot) are different installs [C-STEEL4-bootc-018, C-STEEL4-bootc-019, C-STEEL4-bootc-025].
- **C1 = 3, C4 = 3, C5 = 4, C6 = 3, C7 = 4 stand** as cited in rev. 3. I would not argue C6 up: the AlmaLinux cost is the same as Debian's [C-COST-009 / lifecycle-cost COST-5].

**So the raw order stays C 64 · D 62 · A 60 on the literal card, and C 60 if a refuter reads "experimental, one maintainer" as "not a documented path".** My evidence makes that strict reading *more* reasonable than before (W1), so a fair steelman should say so.

## 6. The tie-break, re-argued from C's side

`01` §3.1.5 counts A vs C as **5–5** and breaks the draw with a "tier argument". The steelman's case against that step:

1. **The tier argument is circular.** It discounts C's wins (DC-05, DC-13, DC-15, NVIDIA trajectory, IIoT) because the plan "already gives" those tiers to a bootc Industrial profile and an Ubuntu GPU flavor. But that plan was written with A as the core. With C as the core, those wins land **on the core**, and only the Jetson flavor remains, the same as under A (§2).
2. **The governance row is scored on the distro only.** Debian's community governance beats AlmaLinux's dependence on RHEL sources: a fair A win at the distro layer. But the row is meant as "second supplier if the vendor changes course". For the **update stack**, C has three shipping vendors and a CNCF project [C-STEEL4-bootc-017, C-STEEL-IIOT-009] against RAUC's two-engineer core [C-REF-W3-longevity-001]. On the whole stack, I'd score the row **≈**. That turns A vs C into **4–5 for C**. A fair judge could keep it for A. I record both.
3. **The "proven competitor" row compares unequal things.** A's precedent is umbrelOS on Debian **with Rugix**; no Debian + RAUC product exists [C-DEC-013]. C's precedent is a vendor edge product without a Pi [C-W2-041]. Both are "base layer only". The row is honestly A's, but narrowly.

**Where C genuinely loses**, and no argument fixes it: DC-19 (Pi 5 pipeline, see W1–W3), the lab row (W5), and DC-07 (one update framework: RAUC's plan covers x86 + Pi with one engine that has a lab record; bootc's Pi leg is a community port). Those three rows are all **the Pi 5**.

**Under the critic's two literal readings of the frozen rule** [P3-1]:
- *Strict top two (C vs D):* `01` scores D 6–4 over C. But D's G1 is an **unmet** third-party condition (Canonical's written permission, Z-01), and C's G1 is met without anyone's permission [C-STEEL4-bootc-014]. If an unmet COND that depends on a third party disqualifies, **C wins S1 with no tie-break**: C 64 vs A 60 is 4.0, outside the band.
- *Unmet COND does not disqualify:* the top two are C and D, and the tie-break is C vs D, not A vs C. A is a finalist only under the rev-3 pairwise amendment, which `scorecard-weights.md` §8 does not log [P3-1].

**Steelman conclusion on protocol:** A survives only under a rule written after the scores were known. Under both readings the frozen text supports, C is the winner or a finalist. The honest way out is the one P3-1 proposes: put S1 to the founder as a protocol choice, with the Pi 5 test as the evidence that decides it.

## 7. The point most likely to be missed: this choice expires at first shipment

The Debian ↔ Ubuntu hedge is cheap because both use the same RAUC layout, so it's a CI variable [`01` REC-DEC-17]. **Debian + RAUC ↔ bootc is not.** The partition layout, bootloader and update client all differ, and even within bootc the backend is fixed at install [C-STEEL4-bootc-025]. Once the first customer box ships on A, moving it to C is a reflash with a data migration, and vice versa. So "keep bootc as a year-2 Industrial profile" (`01` REC-DEC-04) is a real option for **new** SKUs only, never for the installed base. The founder should therefore run **W2-HW-3 before G1 (week 4)**, not later in the 180 days. One Pi 5, one afternoon, and the S1 question closes on evidence instead of a tie-break rule.

## 8. What a OneMind-on-bootc build would look like (so the comparison is like for like)

1. `Containerfile` `FROM` the AlmaLinux 10 bootc base; add k3s, `k3s-selinux`, the OneMind agent and a greenboot `required.d` k3s check with the fresh-signal rule the run already proved [C-LAB-rauc-k3s-gate-008]; core pods as logically bound images [C-STEEL4-bootc-022].
2. Sign every image with cosign; ship a `policy.json` that refuses unsigned OneMind images [C-STEEL4-bootc-020].
3. Pi 5: a OneMind fork of the AlmaLinux RPi Containerfile with the bootloader pinned by hash, and `sync` called from the health-check success hook (new work, about the size of the RAUC tryboot backend already built [C-LAB-rauc-1152-017]).
4. Carry a greenboot patch for #219 until upstream fixes it [C-LAB-fedora-bootc-012].
5. Jetson: the L4T flavor exactly as in `01`; RHDE as an optional SKU.
6. CI legs: AlmaLinux 10 (ship), CentOS Stream 10 (early warning, aarch64 RT), Fedora (canary). Offline USB update as a release artefact [C-STEEL4-bootc-021].

The engineering left over is **similar in size** to A's. A needs its own RAUC build, a custom Pi tryboot backend and an anti-downgrade rule [`00` findings 4, 8]. C needs a Pi commit hook, a greenboot patch and a pinned Pi build. Neither is free.

## 9. What competitors and adopters do (constraint fit)

| Who | Base / update | Hardware | Team / market | Constraint fit with OneMind |
|---|---|---|---|---|
| Red Hat Device Edge | RHEL bootc image + MicroShift + Edge Manager [C-W2-041, C-STEEL4-bootc-012] | x86, Jetson Orin (paid), no Pi | Large vendor, enterprise edge | **Partial**: same stack and edge/robotics target, but not a small team or consumer box, and no Pi |
| Universal Blue (Bazzite, Bluefin, Aurora) | Fedora bootc images [C-STEEL4-bootc-017] | Consumer x86 PCs and handhelds | Community, consumer | **Partial**: proves bootc at consumer scale with a small team; desktop, not appliance |
| CIQ (Rocky Linux from CIQ) | Image-based Rocky via bootc (2026) [C-STEEL4-bootc-017] | Servers and cloud | Vendor | Low: servers, but a second EL vendor betting on bootc |
| Luft | Fedora, composefs, sealed UKIs, systemd-boot [C-STEEL4-bootc-017] | x86 desktops | Small vendor | Low on hardware, **high on the security pattern** W6 needs |
| umbrelOS | Debian 13 + Rugix (earlier Mender) [C-W2-043, C-W3-040] | Pi 5 + x86 | Small team, consumer | **High**, and it is *not* bootc: the strongest evidence against C on the Pi tier |
| Home Assistant OS | Buildroot + RAUC [C-TD-home-assistant-os-003] | Pi, x86, many SBCs | Small core team, consumer | High, not bootc |

## 10. Verdict and flip evidence

**Steelman verdict:** C is a legitimate co-leader, not a runner-up. On the frozen protocol it leads the raw card in every sensitivity run. It wins S1 outright under one literal reading of the tie rule, and is a finalist under the other. It owns the strongest rebase, offline-update, licensing, governance-of-the-update-stack and NVIDIA-server arguments. **Its case collapses to one question: is the Pi 5 path real?** Today the honest answer is "documented, signed kernel, one maintainer, manual commit, unfixed power-cut bug". That is not good enough to ship to a greenhouse, and it is fixable on a timescale of weeks, not years.

**Evidence that would flip S1 to C** (adds to `01` §3.1.5's list; all must hold):
1. W2-HW-3 passes on a real Pi 5: AlmaLinux bootc image, k3s-gated `bootc switch` to a broken image, automatic return with no console.
2. The Pi commit is automatic (`sync` from the health hook) and survives a power pull during first boot.
3. greenboot #219 is fixed upstream, or a OneMind patch passes the lab's power-cut test [C-LAB-fedora-bootc-011].
4. **New:** the Pi path stops being one person's: AlmaLinux (a SIG) or OneMind owns the repo, or it reaches ≥ 2 active maintainers.
5. **New:** a composefs + systemd-boot-counting spike shows sealed images *and* automatic rollback on one x86 layout (closes W6, lifts C3 toward 4).

**Evidence that would kill C as the core:** W2-HW-3 fails; the AlmaLinux Pi kernel repo goes more than 90 days behind Raspberry Pi's tags [C-STEEL4-bootc-004, C-STEEL4-bootc-005]; the RPi bootc repo is archived; or a Red Hat source-access change stops AlmaLinux's EL11 [C-STEEL4-bootc-015].

**What the decision owner should do with this:** log the tie-break rule in `scorecard-weights.md` §8 (P3-1); move W2-HW-3 ahead of G1; and present S1 to Zeus as a protocol choice that the Pi 5 test settles, noting that the choice becomes permanent for every box shipped (§7).

## Requirement trace

| Recommendation | Requirement IDs |
|---|---|
| Run W2-HW-3 before G1, and treat S1 as a protocol choice for the founder | F-12, F-14, RS-1, RS-4, N-2, H-3 |
| If C: AlmaLinux 10 bootc core, L4T Jetson flavor, RHDE optional | F-2, M-7, N-2, H-1, D-001 |
| If C: cosign policy, composefs sealing spike, greenboot #219 patch | R-1, M-2, U-4 |
| Declare support from published component dates (AlmaLinux 10 to 2035-05-31; EL11 rebase before 2036) | R-3, M-8, F-1 |
| FDO, Flight Control, offline USB updates for IIoT and off-grid sites | F-11, F-13, N-4, N-6 |

## Glossary

| Term | Meaning |
|---|---|
| **bootc** | A tool that installs and updates a whole Linux OS from a container image, keeping the previous one for rollback. |
| **OSTree / composefs** | Two ways bootc stores OS versions on disk. composefs can make the root read-only and cryptographically checked. |
| **Sealed image** | A composefs root whose fingerprint is signed into the boot file (UKI), so Secure Boot also protects the root filesystem. |
| **UKI** | Unified Kernel Image: kernel, initramfs and command line in one signed file. |
| **greenboot** | Health checks that run after an update boots and trigger a rollback if they fail. |
| **tryboot** | The Raspberry Pi firmware's "boot this once; if it fails, go back" switch. |
| **Logically bound image** | An app container image that the OS image names, so the two update and roll back together. |
| **RHDE** | Red Hat Device Edge: RHEL plus MicroShift and Edge Manager, sold for edge devices. |
| **ELCP / LL** | Red Hat's paid extended-support streams for one RHEL minor version. |
| **Bus factor** | How many people would have to leave before a project stalls. |
| **COND (gate)** | A gate passed only with a named condition. Whether an *unmet* third-party condition disqualifies is the open question in P3-1. |
