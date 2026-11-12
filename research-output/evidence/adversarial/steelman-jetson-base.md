# Runner-up steelman: one non-L4T base on Jetson

- **Protocol:** RESEARCH-MISSION.md §2 rule 7 (mandatory steelman of the runner-up). This agent was told to argue **for** the runner-up as strongly as the evidence honestly allows.
- **Decision under challenge:** 01-FOUNDATION-DECISION.md D2 / REC-DEC-01: "Debian 13 core image; **Jetson flavor on NVIDIA L4T Ubuntu 24.04 (JetPack 7.2+)**; Yocto meta-tegra is the named fallback" [C-W7-007, C-W7-008], and 08 W7-R3 ("meta-tegra spike in year 1; Debian on Jetson ruled out").
- **Runner-up argued for:** a **single OneMind-owned base that also covers Jetson**, so Jetson is not a second distribution from a second vendor. Three concrete forms are weighed: **(Y) Yocto with meta-tegra on Jetson and OneMind's own LTS kernel**, which can grow into one Yocto base for every tier; **(B) bootc on Jetson**; **(D) Debian on Jetson**.
- **Date:** 2026-11-11. **New claims:** `C-STEEL-jb-001…022` in [`../claims/STEEL-jetson-base.csv`](../claims/STEEL-jetson-base.csv). All sources were opened by this agent on 2026-11-11, and code is cited at pinned SHAs. Rows from other workstreams are cited by their existing IDs.
- **Verdict:** `steelman`. In short, **Y is a real, maintained, commercially shipped option, not a hypothetical**. **B and D are not ready.** Y should be the **declared target for the Robotics tier by year 2**, and stop being treated as a "fallback". It should not replace L4T Ubuntu at launch.

> ### Explain it like I'm the founder
> Today's plan has two operating systems: Debian on PCs and Pis, and NVIDIA's own Ubuntu on Jetson robots. NVIDIA decides when that Ubuntu changes (it has changed three times: 20.04, 22.04, 24.04). It also decides when its kernel stops getting fixes, and it just stopped JetPack 5 with no further critical updates [C-STEEL-jb-012]. The alternative is to build the Jetson image **ourselves** with Yocto, the industrial tool NVIDIA now officially supports [C-STEEL-jb-013], using a **long-term-support kernel we pick** [C-STEEL-jb-002]. balenaOS already ships Jetson products this way [C-STEEL-jb-010]. In return, OneMind controls the robot OS's lifetime instead of renting it from NVIDIA. The cost: Yocto is hard to learn, and the "own kernel" path on Jetson is only four months old.

## 1. The decisive new evidence (not in the current decision)

The current decision treats "non-L4T on Jetson" as two options: mainline only, which fails because there is no upstream GPU driver, or Talos's unmerged PR. Both are weak, and the W7-FF-2 refuter already showed a third path: NVIDIA's own BYOK, which pairs an LTS kernel with NVIDIA's out-of-tree (OOT) modules. **This agent found that the third path is already packaged, maintained and in use upstream:**

1. **meta-tegra's LTS branch ships a linux-yocto 6.18 LTS kernel for both Orin (tegra234) and Thor (tegra264).** `linux-yocto_6.18.bbappend` and an RT variant sit beside NVIDIA's 6.8 vendor kernel. They are fed by a dedicated patch-queue repo, `tegra-kernel-cache` (branch `yocto-6.18`). The branch head on 2026-11-11 is literally "bump SRCREV_tegrameta for **6.18.54**" [C-STEEL-jb-002, C-STEEL-jb-006]. So OE4T tracks the upstream stable series, which a vendor 6.8 kernel cannot do (6.8 is not a kernel.org LTS; 6.18 is LTS to Dec 2028 [C-W18-001]).
2. **NVIDIA's OOT stack, including the GPU compute driver, is built against that kernel by the same recipe.** `nvidia-kernel-oot.inc` builds host1x, nvmap and the nvgpu compute package for tegra234. When linux-yocto is the kernel, it skips only two Realtek Wi-Fi modules, because mainline has `rtw88` [C-STEEL-jb-005]. Upstream says this is the BYOK model NVIDIA documents [C-STEEL-jb-016].
3. **The patch queue comes from NVIDIA.** 217 of its 463 patches are "platform" patches taken from NVIDIA's own `linux/patches/<ver>`, and 240 are NVIDIA "sauce" patches [C-STEEL-jb-006]. This is not a hobbyist port. It is NVIDIA's delta re-based onto an LTS.
4. **Real time is on the LTS too.** The kernel cache has `tegra234-preempt-rt` and `tegra264-preempt-rt` BSP descriptions [C-STEEL-jb-006]. Mainline PREEMPT_RT is a normal config option on arm64 [C-W18-005]. NVIDIA's own L4T RT kernel is "Developer-Preview quality" [C-W7-009].
5. **Independent evidence that LTS kernel + OOT nvgpu runs CUDA on Orin:** Talos verified CUDA on Orin NX 16GB on 6.18.24 and 6.18.48, at about 64 to 78 tok/s, and a second user verified it on AGX Orin 64GB [C-STEEL-jb-017]. The regression in that PR is on **7.3**, a non-LTS kernel. That is an argument *for* pinning an LTS, not against BYOK.
6. **Commercial proof that a non-NVIDIA OS can ship on Jetson:** balenaOS, a commercial fleet OS whose device list includes Pi 5, generic x86-64, Orin Nano, AGX Orin and AGX Thor [C-W2-040], builds its Orin OS on **meta-tegra `wrynose`** [C-STEEL-jb-010].

The current plan names meta-tegra a "fallback" because it was assumed to mean "NVIDIA's 6.8 kernel, rebuilt with Yocto." That assumption is now outdated. meta-tegra's default is still the vendor kernel [C-STEEL-jb-003], but the LTS path is a first-class, actively bumped option.

## 2. The case, requirement by requirement

### 2.1 Longevity to 2036 (R-3, M-6, N-2)

| Fact | Effect on L4T Ubuntu (chosen) | Effect on Y (meta-tegra + own LTS) |
|---|---|---|
| Modules are sold to Jan 2032 (Orin), Jul 2033 (AGX Orin Industrial), Aug 2035 (T5000) and Jan 2036 (T4000) [C-STEEL-jb-011] | A robot sold in 2035 will cross **at least two more** JetPack majors. Each major has changed the Ubuntu release (JP5 20.04, JP6 22.04, JP7 24.04 [C-W7-007]), so each is a rootfs rebase dictated by NVIDIA | The rootfs is OneMind's. A JetPack major changes the BSP layer and OOT recipes, **not the OS the customer sees** |
| JetPack 5 was ended on 2026-10-30, with "no longer ... any critical updates" and a paid partner for its kernel [C-STEEL-jb-012]; the r35 branch lived about 4.5 years [C-W7-005] | The kernel's security life is set by NVIDIA, with no written period [C-STEEL-jb-013 shows none on the JetPack page] | The kernel's life is the upstream LTS's, 6.18 to Dec 2028 [C-W18-001], and OneMind moves to the next LTS on its own schedule. CIP SLTS kernels are a possible 10-year base (**UNVERIFIED**: the CIP wiki returned 403) |
| Yocto Wrynose LTS runs to Apr 2030, and future LTS releases are planned for 4 years [C-STEEL-jb-008]; meta-tegra keeps an LTS branch per JetPack major [C-STEEL-jb-009] | n/a | Two predictable cadences (Yocto LTS, kernel LTS) that OneMind can plan a CRA support period against |
| Canonical's Jetson offer: Pro coverage "with no stated number of years"; 24.04 only for Thor [C-REF-DC-robotics-003] | Ubuntu Pro ESM to 2034 covers the archive [C-W2-005], but the L4T kernel's coverage is undocumented (W2-P0-1 longevity refuter) | Not dependent on Canonical |

**The core argument:** 01 §5.7 already caps each Jetson SKU's support period at "the remaining life of its L4T branch + one in-field branch upgrade." That cap is the **direct cost** of L4T. Option Y is the only route in this repo that lets a 2035 Thor robot get a support period longer than NVIDIA's branch.

### 2.2 F-14: one OS from Pi to enterprise

- Today's plan has **two userlands** (Debian, Ubuntu), **two package ecosystems**, **two updaters** (RAUC, NVIDIA A/B; 01 D3) and **three kernel owners**. Every OneMind app, agent, SBOM and CVE pipeline has to be validated twice.
- Y removes the second userland from OneMind's own release process. OneMind's distro layer, users, k3s, signing, health gate and app runtime are defined once. Jetson is a `MACHINE`, not a flavor. Debian and Pi stay as they are if OneMind wants that (the "Jetson only" variant). Or, the bolder variant: the same Yocto distro builds genericx86-64 and Raspberry Pi as well. balenaOS is the proof that one Yocto-based OS spans Pi 5, x86 and Orin/Thor [C-W2-040, C-STEEL-jb-010].
- **One kernel series across tiers:** with linux-yocto 6.18 on both x86 and Jetson, the Robotics and Pro/Lite tiers can share one kernel series, one config base and one CVE feed. L4T 6.8 cannot offer that.
- **One updater becomes possible:** meta-tegra's A/B layout is designed to be driven by "swupdate, rauc, mender, or others" [C-STEEL-jb-020]. Mender's maintained Tegra layer supports wrynose on Thor and Orin [C-W3-053], and Mender also covers Pi 5 and x86 [C-W3-054]. The decision itself says that a Yocto Jetson flavor would make Mender the single framework (01 W3-P0-W3-2 row; 04 §"What would flip it"). On Y, D3's "two backends behind one contract" can collapse to one.
- **NVIDIA itself unified the Jetson userland:** from r39.2, Orin (nvgpu.ko) and Thor (OpenRM nvidia.ko) share **one root filesystem**, with drivers selected at runtime [C-STEEL-jb-014]. JetPack 7 is "aligned with SBSA" [C-STEEL-jb-013], and CUDA ships through SBSA-style `arm64-sbsa-jetson-*` repos [C-STEEL-jb-015]. The pieces OneMind must integrate are therefore shrinking toward a small, well-defined set of packages, which suits a distro OneMind defines itself.

### 2.3 F-11: IoT / IIoT for 10+ years

- Yocto is the default build system of the industrial embedded world. NVIDIA now calls OE4T recipes "full-stack, NVIDIA-validated" [C-STEEL-jb-013].
- **AGX Orin Industrial** (the SKU sold to 2033) is a first-class machine in meta-tegra [C-STEEL-jb-001].
- **IEC 62443-4-1 / CRA evidence comes out of the build:** meta-tegra attached Jetson Linux CVE metadata to the NVIDIA kernel-module and binary recipes in Sept 2026 [C-STEEL-jb-022], so Yocto's CVE check and SBOM output cover NVIDIA's blobs. An L4T Ubuntu image gets its SBOM by scraping an NVIDIA-assembled rootfs.
- **No Canonical trademark condition:** a OneMind-built image contains no Ubuntu binaries, so it sidesteps the IPRights approval requirement that 01 flags for the L4T flavor [C-W2-050]. That requirement is a G1 "COND" on the current winner.
- **A reduced attack surface on fielded robots:** an image has exactly the packages OneMind names, which suits an appliance (the HAOS/Buildroot steelman's argument, W3-steelman, applied to Jetson).

### 2.4 Robotics

- **Real time:** a PREEMPT_RT LTS kernel on Orin/Thor [C-STEEL-jb-006] instead of a developer-preview RT build [C-W7-009]. For control loops this is the more defensible base.
- **ROS 2 is unaffected:** ROS 2 runs in containers on every flavor anyway, and Lyrical rates Ubuntu 24.04 only Tier 3 [C-W7-027]. L4T Ubuntu gives no host-level ROS advantage.
- **GPU / CUDA:** shown working on an LTS + OOT [C-STEEL-jb-017], and packaged by meta-tegra [C-STEEL-jb-005]. The container toolkit is supported [C-STEEL-jb-019].
- **Hardware OneMind might build (08 open question 1):** if OneMind ships its own Jetson carrier, Yocto is where custom carrier boards are normally done (`Creating-a-custom-MACHINE`, `KERNEL_FEATURES_EXTRA_DEVKIT` hooks [C-STEEL-jb-002]). 08 already says the meta-tegra route "becomes the default" in that case.

### 2.5 Security

- **Kernel CVE flow:** upstream stable fixes arrive through 6.18.y bumps, which OE4T is already making [C-STEEL-jb-002]. A vendor kernel depends on NVIDIA's backports (R-W18-1 in 28 rates this Medium/High).
- **Secure boot:** meta-tegra supports NVIDIA's PKC/SBK bootloader signing at build time and UEFI Secure Boot keys (`docs/Secure-Boot-Support.md` at c5efa2f), so OneMind keeps the same chain of trust as stock L4T.
- **Verified rootfs:** dm-verity / signed bundles are standard Yocto practice. The bootc-on-Jetson reference shows that NVIDIA's UEFI can boot a sealed UKI with systemd-boot [C-STEEL-jb-018], so even the Jetson boot chain can be moved onto the same UKI model 01 plans for x86.

### 2.6 Solo-developer operability

The honest pitch is that Y moves work from **run time** to **build time**, and build time is cheap to automate:
- With L4T, every JetPack major brings a manual rootfs rebase, OTA-path validation (35→36 apt upgrade unsupported [C-W3-050]) and a second userland's CVE triage, forever.
- With Y, the BSP is someone else's maintained layer. meta-tegra has nearly ten years of history and NVIDIA's official endorsement [C-STEEL-jb-007, C-STEEL-jb-013]. OneMind maintains a distro layer and bumps pinned SRCREVs in CI. A cached rebuild is an hours-long CI job (LAB-W7-6 sets < 4 h as its pass bar), not founder time.

## 3. The weaker forms, assessed honestly

- **(B) bootc on Jetson: not a single base yet.** The only open example is a "reference example", explicitly not for production use (6 stars). It still uses Ubuntu 24.04 + L4T packages and NVIDIA's 6.8 kernel [C-STEEL-jb-018]. Red Hat Device Edge on Orin exists, but it is paid, RHEL 9.8 based, and its kernel source is unstated [C-W2-041]. bootc also has no boot counting on the composefs backend yet [C-W3-058]. It is useful evidence that NVIDIA's UEFI boots a generic UKI, but it does not remove L4T.
- **(D) Debian on Jetson: blocked today.** CUDA 13.5 lists Debian 13 for amd64 and SBSA servers **but not for Jetson**. The only Jetson rows are Ubuntu 24.04 (JP7.2) [C-STEEL-jb-015]. This narrows C-W18-027, which 28 reads more broadly. 08's "ruled out until NVIDIA lists Debian" stands.

## 4. Genuine weaknesses of the runner-up

1. **The LTS-kernel path is about four months old.** Thor support on linux-yocto landed 2026-07-26 [C-STEEL-jb-004]. There is no evidence yet of it surviving an LTS-to-LTS jump, or of a full camera (VI/Argus), DLA, NVENC/NVDEC and display stack running on it. The 7.3 regression in Talos shows OOT drivers can break silently on kernel changes [C-STEEL-jb-017].
2. **Bus factor.** The kernel patch queue has two contributors (19 and 4 commits) [C-STEEL-jb-006]. meta-tegra itself is dominated by one maintainer (about 2375 of its commits) [C-STEEL-jb-007]. That is the same single-maintainer risk 01 holds against Rugix [C-W3-001].
3. **NVIDIA still calls its own kernel "the most complete and best tested"** and does not list what BYOK loses [C-STEEL-jb-016]. meta-tegra's default is still that vendor kernel [C-STEEL-jb-003].
4. **The 463-patch queue** means NVIDIA's delta has not shrunk. Every LTS re-base is real merge work, done by OE4T, not by upstream [C-STEEL-jb-006].
5. **NVIDIA's container and CUDA validation targets Ubuntu 24.04 only** [C-STEEL-jb-015]. NGC Jetson containers expect the host to provide TensorRT/cuDNN [C-STEEL-jb-019], so OneMind owns the "is this host compatible with Isaac ROS image X" question, and NVIDIA forum support will assume L4T.
6. **Yocto is the steepest tool on the list for a founder who is learning OS engineering:** Linux-only build hosts, about 140 GB of disk and 32 GB of RAM suggested [C-W18-050]. The 180-day plan's lab evidence (RAUC, Rugix, k3s) is all on Debian. A Yocto-everywhere variant would throw that away.
7. **RAUC has no Tegra layer** (removed 2024 [C-W3-021]; still absent [C-STEEL-jb-021]). "One updater" on Y means Mender (delta is paid; W3) or SWUpdate, not the RAUC that 01 chose and lab-proved.
8. **Lifecycle math still has a gap:** 6.18 LTS ends Dec 2028 and Wrynose ends Apr 2030 [C-W18-001, C-STEEL-jb-008]. A 2036 Thor still needs two or three LTS hops. Y makes those hops OneMind's choice, but it does not remove them. Whether CIP SLTS covers Tegra is **UNVERIFIED**.
9. **Nothing has been tested on hardware by this run.** There is no OneMind Jetson, and LAB-W7-6 has not been run.

## 5. Recommendation from the steelman (for DEC to answer)

- **Keep L4T Ubuntu 24.04 for the first Robotics beta** (01 D2). The weaknesses in §4 items 1–3 and 9 are real, and launch should not depend on a four-month-old kernel path.
- **Re-label meta-tegra from "fallback" to "target":** run LAB-W7-6 in the first 180 days instead of "year 1". Run it on **`wrynose` with `PREFERRED_PROVIDER_virtual/kernel = linux-yocto`** (6.18 LTS), not the vendor kernel, and add the tests in §6.
- **Keep the OneMind release contract updater-neutral** (01 already does). Lay out every Jetson as redundant (A/B) from first flash so that a later move from L4T to Y is an image update, not a reflash [C-STEEL-jb-020].
- **Amend 28 / C-W18-027:** CUDA's Debian 13 support excludes Jetson [C-STEEL-jb-015].
- **Amend 08 FF-2 / DC-08:** the third option (LTS + OOT) is packaged upstream in meta-tegra, not only an open Talos PR [C-STEEL-jb-002, C-STEEL-jb-005].

## 6. What evidence would make the runner-up the winner

Y becomes the Jetson default if **all** of these hold. Each is testable on one Orin Nano Super plus one CI builder:
1. **LAB-W7-6+**: meta-tegra `wrynose` with linux-yocto 6.18 builds in CI in under 4 h on cache. On an Orin Nano it runs CUDA (deviceQuery and a TensorRT engine) and an nvidia-container-toolkit container with k3s. Throughput must be within 10% of stock L4T on the same model.
2. **The camera and media stack works on the LTS kernel:** a CSI camera through libargus/nvarguscamerasrc and NVENC encode in a ROS 2 container. This is the gap the W7-FF-2 refuter named.
3. **It survives two consecutive 6.18.y bumps in OE4T** (for example 6.18.54 to 6.18.6x) with no OneMind patching, and meta-tegra ships an LTS-kernel build for the next JetPack point release.
4. **An A/B update with OneMind's health gate** (Mender or SWUpdate on the redundant layout) passes the same power-cut tests RAUC passed [C-LAB-rauc-013…018].
5. **External signals (any one strengthens the case):** NVIDIA documents BYOK for a named LTS with the full OOT set; OE4T adds a second active kernel-cache maintainer; Thor support appears in CIP; NVIDIA announces a JetPack 8 rootfs change (another forced rebase on the L4T path); or OneMind decides to sell its own Jetson hardware (08 open question 1).

**What would kill it:** the camera stack cannot run on linux-yocto, OE4T stops bumping the `yocto-6.18` queue for more than 3 months, or NVIDIA publishes multi-year security support for each JetPack kernel line reaching Orin's 2032 availability.
