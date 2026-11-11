# W2 runner-up steelman: Fedora IoT / CentOS Stream bootc (image mode) as the OneMind base

- **Role:** runner-up steelman (RESEARCH-MISSION.md §2 rule 7). This agent was told to argue **for** the runner-up. It is advocacy held to the evidence rules: each fact below is primary-sourced and was opened on 2026-11-10, or is labelled SECONDARY, vendor-stated, INFERRED or UNVERIFIED. The genuine weaknesses are in §8, stated plainly.
- **Date:** 2026-11-10 · **Re-check by:** 2027-05-10 for board, BSP, kernel and bootc facts (6 months); 2027-11-10 for lifecycle and pricing (12 months)
- **Verdict:** `steelman`
- **Decision under test:** ADR-001 **D2** (and the D3 parts that depend on the base). The ADR proposal is *Debian 13 "trixie" core image + Rugix A/B, plus an NVIDIA L4T/Ubuntu flavor for Jetson*. W2's draft (`03-base-os.md`) scores Ubuntu 26.04 first (62.0), with RHEL-family bootc and Debian 13 + Rugix tied at 56.0 and Fedora IoT at 48.0. It makes bootc an Industrial profile only.
- **The runner-up argued here:** the **Red Hat image-mode lineage as one product family**: Fedora IoT bootc (upstream canary) → CentOS Stream 10 bootc → **AlmaLinux 10 bootc (free shipped base)** → RHEL 10 image mode / Red Hat Device Edge (paid, certified tier), with greenboot health-gated rollback and the OS shipped as an OCI image.
- **Serves requirements:** F-11, F-12, F-14, F-1, F-2, F-7, F-8, M-4, M-6, M-7, R-1, R-3, N-2, N-4, N-8, U-4, AI-4, AI-7, RS-2, D-001

> ### Explain it like I'm the founder
> With **bootc**, your whole operating system is built like an app container. You write a `Containerfile` ("start from AlmaLinux 10, add k3s, add our health check"), push it to a registry like any Docker image, and every box pulls the new OS, keeps the old one, and switches back by itself if the new one fails its health check. We tested this in our lab, and it did exactly that.
> The best case for it as **the** base is that the rest of the field asks OneMind to build the hard parts itself: the "only commit when k3s is healthy" rule, the update signing, the fleet manager, the industrial certificate and the Jetson image. In the Red Hat lineage those parts **already exist as shipped, open-source code**, and NVIDIA ships its own Jetson software for RHEL **as a bootc image**.
> The two holes W2 found, "no Raspberry Pi 5" and "no Jetson", are smaller than the draft says. AlmaLinux publishes bootc images **tested on Pi 5**, and Jetson Orin is a GA Red Hat product built on bootc. The catch (§8): the Pi 5 route is experimental and community-run, the Jetson route needs a paid Red Hat subscription, and NVIDIA's GPU Operator doesn't list RHEL with k3s.

---

## 1. The claim this steelman makes

> **One bootc artifact format, built from one Containerfile, can serve OneMind from a Raspberry Pi 5 greenhouse node to an OpenShift-class cluster. It does so with less OneMind-owned code than Debian 13 + Rugix: health-gated commit, rollback, rebase without reflash, fleet management, OS signing and sealing all exist upstream. It also gives the only multi-vendor path to 2036 that has both a free tier (AlmaLinux/CentOS) and a certified paid tier (RHEL, IEC 62443-4-2). On the frozen scorecard, with evidence the W2 draft didn't have, the RHEL-family bootc stack scores 60–64. That beats ADR-001's Debian 13 + Rugix (56) by 4–8 points and ties or beats Ubuntu 26.04 (62).**

## 2. Strongest arguments (each with primary evidence)

### 2.1 The two gate gaps W2 cited are narrower than scored (G2, C2, F-14, N-2)

W2 scored RHEL-family bootc **C2 = 1** because "no Pi 5 (anchor 2 needs Pi 5)" [03 §4]. W3 marked bootc's board gate **FAIL: "GRUB+shim only, no Pi tryboot or Jetson path shown"** [04 §212, C-W3-058]. New primary evidence on both:

| Fact | Evidence (opened 2026-11-10) |
|---|---|
| **AlmaLinux publishes bootc images for Raspberry Pi, tested on Pi 5.** README: "It has been tested on: several rpi5 versions including 2g, 8g, and 16g · rpi4 · rpi3 · rpi zero 2 w". Install: "GPT image if your PI supports it (RPI5, RPI4)… Flash it to an m.2 drive (RPI5 only), SD card, or USB device." Labelled "*experimental*". | `AlmaLinux/bootc-images-rpi@bb8e83e6b898db63ca2b53a69343f067dfa4f28a:README.md` [S-01] |
| What works: "installing the raw base image onto a rpi", "building your own custom images based on the AlmaLinux RPI bootc image", "**switching the rpi to a custom image** with a similar kernel", "devicetree management". | same file [S-01] |
| Built images exist for AlmaLinux **10**, 10-kitten and 9: release `2026-03-15-1` ships `image-almalinux-bootc-rpi-gpt-10-20260316-arm64.raw.xz`; release `2025-07-15-1` had per-board `rpi5-10` images. Pre-built OCI bases on `quay.io/almalinuxorg/almalinux-bootc-rpi`. | `gh api repos/AlmaLinux/bootc-images-rpi/releases` [S-01] |
| The image is a normal bootc build: `FROM quay.io/centos-bootc/centos-bootc:stream10` builder → `bootc-base-imagectl build-rootfs --manifest=almalinux-10-rpi` → `FROM scratch`, `LABEL containers.bootc 1`. The kernel is AlmaLinux's packaged Raspberry Pi kernel (`raspberrypi2-kernel4`) from AlmaLinux's own signed `raspberrypi` repo. | `…@bb8e83e:10-rpi/Containerfile`, `10-rpi/kernel.yaml`, `10-rpi/almalinux-raspberrypi.repo` [S-01] |
| AlmaLinux maintains that Pi kernel for EL10: `raspberrypi2-kernel4-6.12.96-20260724.v8.1.el10.aarch64.rpm` is in the repo. This is the same *pattern* as ADR-001's Debian route (the Raspberry Pi vendor kernel, repackaged), but with a distro-signed package. | `https://repo.almalinux.org/almalinux/10/raspberrypi/aarch64/os/Packages/` (directory listing, 2026-11-10) [S-02] |
| **The Pi boot problem (Fedora IoT #82) is solved without UEFI or GRUB** by `rpi-bootc-bootloader`, wired into `ostree-finalize-staged`. It uses the Pi firmware's own **tryboot** A/B: "Failure to boot or a power cycle should return it automatically to the current, working image." Licence: "BSD 2 Clause or Apache 2.0. Your choice." | `kfox1111/rpi-bootc-bootloader@82739f4c9ae6de9ce071014bff9dee16842fb978:README.md`, `LICENSE`; pinned as tag v0.0.8 in AlmaLinux's Containerfile [S-03] |
| **NVIDIA's Jetson software for RHEL is itself a bootc image.** Red Hat KB: "NVIDIA Jetpack for Red Hat Enterprise Linux (RHEL) is delivered as a bootable container (bootc) image." Devices: Jetson Orin, IGX Orin. "Red Hat Enterprise Linux 9.8 (General availability)". Updated 2026-06-24. | `https://access.redhat.com/node/7140448` [S-04]; RHDE on Orin GA [C-W2-041] |
| NVIDIA's CUDA repository publishes `rhel10` (and `fedora45`) next to `debian13` and `ubuntu2604`. | `https://developer.download.nvidia.com/compute/cuda/repos/` (listing, 2026-11-10) [S-05] |
| An RT kernel is in the free lineage: CentOS Stream 10 compose `CentOS-Stream-10-20261110.0` has `kernel-rt-6.12.0-282.el10` for **x86_64 (RT) and aarch64 (NFV)**. AlmaLinux 10 ships `kernel-rt-6.12.0-211.74.2.el10_2.x86_64`. | `composes.stream.centos.org/stream-10/production/latest-CentOS-Stream/compose/{RT,NFV}/…` [S-06]; `repo.almalinux.org/almalinux/10/RT/x86_64/` [S-06] |

**What this does to the scorecard.** The C2 anchor 3 reads: *"x86, Pi 5 and Jetson all have a documented path (a flavor split is allowed). NVIDIA x86 driver and container toolkit available from NVIDIA for this base. ROS 2 runs in containers. PREEMPT_RT available."* (`scorecard-weights.md` C2). Each clause now has a primary source: x86 (RHEL/Alma), **Pi 5 (AlmaLinux bootc RPI, documented and tested)**, **Jetson (JetPack for RHEL, bootc, GA)**, NVIDIA CUDA `rhel10` repo, ROS 2 in containers (W7 FF-7 already calls containers mandatory on every flavor [08 §6]), and kernel-rt. On that reading C2 = **3**, the same as Debian 13 + Rugix and Ubuntu. If the Pi 5 route is discounted as experimental, C2 = **2** (anchor 2: "x86 and Pi 5 supported, Jetson only through community work"). That is still double the draft's 1.

### 2.2 The "commit only when healthy" promise is already shipped code, and OneMind proved it (C3, R-1, AI-4)

- ADR-001 D3 sells "mark good only after k3s + core pods are healthy" as OneMind's own improvement. **greenboot already does it** (required.d checks before `boot-complete.target`, bounded counter, then `bootc rollback`) [C-W2-022, C-W2-023]. Our lab showed it end to end on Fedora IoT 45 bootc with k3s under SELinux Enforcing on a composefs read-only root: GREEN boot, automatic rollback of a broken update with **zero manual commands**, and power cut during staging and finalization survived (2/2) [C-W2-052, 054, 055].
- **Rugix "does not mark boots good or bad by itself"** (prior-verified, context/03 §1.2; W3 says OneMind must supply this step [ADR-001 D3, E3]). On the ADR stack this is code OneMind writes, tests and owns for ten years. On bootc it's a 25-line `required.d` script.
- **Rebase without reflash (DC-05) is a design property, not a spike.** `bootc switch` moves a device to a different image, including a different distro major [C-W3-060]. bootc's maintainers commit: "We will ensure that every existing system can be upgraded in place seamlessly across any future changes" (`bootc-dev/bootc@27f1e64:README.md`) [C-W2-024]. W2's own P0-6 says *every* base needs at least one in-place major rebase before 2036, and that this matters "as much as the distro choice" [03 §1]. bootc is the only candidate where it's the normal update command. For Rugix it is "unproven" (03 §7 item 5).
- **Sealed, verified boot is documented upstream:** "A sealed image is a cryptographically signed and verified bootc image… Unified Kernel Images… Composefs integration… Secure Boot", where the composefs SHA-512 digest is in the signed UKI command line, so "the system will only boot if the root filesystem matches exactly what was signed" (`bootc-dev/bootc@27f1e64:docs/src/building/bootc-sealed-images.7.md#L5-L17`) [S-07]. ADR-001 D6 defers Secure Boot + TPM to "Phase 2" and points at Kairos as the reference. bootc has it in-tree.

### 2.3 The OS becomes an OCI artifact, which is what OneMind already operates (C5, M-6, F-8, F-9)

- The OneMind cloud already runs on GHCR images, digest pinning, Argo CD and GitOps (context/01). bootc makes the **OS another image in the same registry**, with the same digests, the same signing (sigstore/cosign via `containers-policy.json`) and the same SBOM attestations. Umbrel already defines its OS in a Dockerfile, then has to convert it to block images with Rugix Bakery [C-W2-043, 046]. bootc removes that conversion step.
- **Measured build effort:** Containerfile build + `bootc-image-builder` qcow2 in about 1–2 minutes each, on Apple Silicon, from public bases [C-W2-056]. Compare HAOS-style from-source builds at 75–159 min per board (W3 steelman §8). The solo-developer path from the founder's Mac is podman + a Linux VM, the same as for apps (F-8).
- **App images can be bound to the OS release.** "Logically bound images" pull named container images during `bootc upgrade`/`switch`, so k3s's airgap images or the NATS leaf can ship with the OS version that needs them, with "the same confidence you can with `ExecStart=`" (`bootc-dev/bootc@27f1e64:docs/src/bootc-logically-bound-images.7.md#L5-L27`) [S-08]. That directly mitigates DC-12 (OS and k3s version skew on rollback), the main open risk our lab left untested.

### 2.4 F-11 (IoT/IIoT at fleet scale): the fleet plane exists, is Apache-2.0, and is bootc-native

| Fact | Evidence |
|---|---|
| **Flight Control** (upstream of Red Hat Edge Manager), Apache-2.0: "Declarative management of fleets of edge devices and their workloads." "It works best on image-based Linux operating systems running **bootc** or **ostree**, with container workloads running on Podman/Docker or Kubernetes (MicroShift)." | `flightctl/flightctl@f99870eafa95003d1511577efc1c6e8c4ce7d5d1:README.md` [S-09] |
| Features: GitOps `ResourceSync`; fleet templates with "disruption budgets and staged rollouts"; "TPM-backed attestation"; device certificates "bootstrapped from hardware root-of-trust"; "OTA updates via bootc or rpm-ostree with transactional rollback (Greenboot integration). The agent downloads assets before applying, so updates survive network interruptions"; Helm/kustomize workloads; `ImageBuild` produces bootc images with the agent embedded. | same file [S-09] |
| Active: v1.4.0 released **2026-11-09**, v1.3.2 on 2026-11-05. | `gh api repos/flightctl/flightctl/releases` [S-09] |
| **IEC 62443-4-2 SL-C 2** (TÜV Rheinland) for RHEL 9.6, OpenShift 4.20 and MicroShift 4.21 | [C-W2-042] |
| Red Hat Device Edge on Jetson Orin: RHEL 9.8 bootc + MicroShift + Edge Manager, GA | [C-W2-041] |

**Why it matters:** W8 found the ADR stack's fleet plane is a set of integrations (Rugix → Mender, thin-edge.io, Nexigon or Memfault), "not shown" at 10k [09 §1(e)]. W8-R11 even confines Flight Control to "only the bootc track". On bootc, F-11's fleet, attestation, staged-rollout and rollback chain is **one Apache-2.0 project already built for this OS model**, with a commercial twin (Edge Manager) for customers who want an SLA. IEC 62443 is the only *industrial certificate* on any candidate OS in this run, and it sits in this lineage.

### 2.5 F-14 (one OS from Pi to enterprise): one artifact format at every scale

| Scale | bootc member | Evidence |
|---|---|---|
| Pi 5 greenhouse node | AlmaLinux 10 bootc RPI (or Fedora IoT bootc once #82 closes) | [S-01], [C-W2-018] |
| x86 mini-PC / RTX box | AlmaLinux 10 / CentOS Stream 10 bootc + NVIDIA `rhel10` CUDA repo | [C-W2-013], [S-05] |
| Jetson Orin robot | JetPack for RHEL (bootc, GA) / RHDE | [S-04], [C-W2-041] |
| GPU AI server | **RHEL AI ships as bootc images with CUDA**, e.g. `registry.redhat.io/rhelai3/bootc-cuda-rhel9` (catalog entry; Red Hat docs pages returned 403 to our fetcher) | `catalog.redhat.com/en/software/containers/rhelai3/bootc-cuda-rhel9/69134f9144e252b39640be71` (SECONDARY: search-result metadata, page not opened) [S-10] |
| Cluster nodes | OpenShift "Image mode for OpenShift" (on-cluster OS image layering, fully supported from 4.19); Red Hat says OpenShift "will transition to bootc sometime in 2026" | `developers.redhat.com/articles/2025/09/23/customize-rhel-coreos-on-cluster-image-mode` (SECONDARY: search excerpt) [S-11] |
| DGX-class | RHEL 10 on DGX Spark: "development preview" (2026-05-12) | `redhat.com/en/blog/supercharging-local-ai-development-rhel-nvidia-dgx-spark` [S-12] |

Ubuntu's G5 PASS rests on "the same userland family". bootc's case is stronger in one specific way: **the same update mechanism, signing model and fleet plane at every size** (`bootc switch` + greenboot + Flight Control), not just the same package family. W2 admits Ubuntu's G5 still depends on DC-07 ("one update framework across all three boards") being proven [03 §4 note 2]. For the bootc lineage, NVIDIA's own Jetson deliverable *is* a bootc image.

### 2.6 Longevity to 2036 and vendor risk: three independent suppliers on one format (C1, C6, R-3)

- **Free tier:** AlmaLinux 10 security support to **2035-05-31** [C-W2-013]. The step to AlmaLinux 11 is a `bootc switch`, not a reflash (§2.2).
- **Paid tier, vendor 1:** RHEL 10, ten years plus ELCP [C-W2-010]; image mode included in every RHEL subscription [C-W2-012].
- **Paid tier, vendor 2:** CIQ publishes "Rocky Linux from CIQ" bootc images with "commercial support and security response SLAs", and is listed as a bootc adopter since 2026 (`ciq.com/blog/rocky-linux-from-ciq-bootable-container-images-bootc`, vendor-stated, SECONDARY; `bootc-dev/bootc@27f1e64:ADOPTERS.md`) [S-13].
- **Contrast:** Ubuntu's 2031–2036 tail is Canonical-only, at an unpublished Pro for Devices price, and with a trademark policy that may forbid redistributing a modified image [C-W2-006, C-W2-050]. Debian's paid tail (Freexian ELTS) forbids sharing fixes with third parties, which means OneMind's customers [C-W2-004].
- **Governance:** bootc was accepted into the **CNCF Sandbox on 2025-01-21** (`cncf.io/projects/bootc/`; SECONDARY: search excerpt; W3 records "bootc is CNCF Sandbox" [04 §160]). It's dual MIT/Apache-2.0 [C-W2-024]. Rugix is a founder-owned company's project (DC-06 bus factor) [C-W3-015].
- **Adoption of the format** (bootc ADOPTERS at `27f1e64`): Red Hat, AlmaLinux Atomic SIG, CIQ, Universal Blue (Aurora/Bazzite/Bluefin), HeliumOS, ALT Atomic, Caligra and Luft directly. Through ostree: Endless (2014), Apertis (2020), Fedora and Playtron GameOS [S-14]. The ostree base is "over 13 years old (as of 2024)".

### 2.7 Robotics (M-7, F-2): no worse than the ADR, and better on Jetson and safety plumbing

- **ROS 2:** W7 already concluded that containers are the 10-year ROS path **on every flavor**, including Ubuntu 24.04 for Lyrical [08 §6, FF-6]. RHEL 10 is ROS 2 Lyrical **Tier 2** on amd64, which beats Debian trixie's **Tier 3** [C-W2-028]. The ADR's Debian base is the weaker one here.
- **Jetson:** ADR-001 runs Jetson on a second userland with "an A/B method to pick" (§4 spike 6). On bootc, NVIDIA's own RHEL JetPack is a bootc image, GA, and is updated with the same commands and fleet plane as the rest of the line [S-04, S-09].
- **RT:** kernel-rt is in CentOS Stream 10 for x86_64 and aarch64 and in AlmaLinux 10 for x86_64 [S-06]. On Pi 5, *no* candidate has a Pi 5 RT kernel from the vendor (W8: Raspberry Pi ships no bcm2712 RT build [09 §1(b)]). Every candidate has that gap, not just bootc.
- **Safety:** SELinux Enforcing with k3s worked first time in our lab [C-W2-052], with MAC confinement of robot containers from day one. ADR D6 plans AppArmor profiles that OneMind writes itself.

### 2.8 Security and the CRA (C3, U-4, DC-04)

- The read-only, content-verified root (composefs), SELinux enforcing, signed OCI images, TPM-backed device attestation (Flight Control) and the sealed UKI path are **upstream features**, not OneMind code (§2.2, §2.4) [C-W2-052, S-07, S-09].
- The RHEL security response and the 62443-4-2 certificate give EU CRA conformity work an existing vendor evidence trail for the paid tier [C-W2-042]. Debian's equivalent is a certified *hardware product* by a third party, not the OS [09 §1(c), C-W8-033].

### 2.9 Licence fit (G1, D-001)

bootc is MIT/Apache-2.0, greenboot-rs BSD-3, Flight Control Apache-2.0, rpi-bootc-bootloader BSD-2/Apache-2.0, and AlmaLinux packages are their upstream licences [C-W2-024, C-W2-049, S-03, S-09]. Nothing in the free tier carries a trademark-redistribution condition like Canonical's [C-W2-050]. The AlmaLinux RPI *build repo* is GPL-3.0 (its scripts), which OneMind would re-implement rather than copy. That is a 30-line Containerfile pattern (§8.9).

## 3. Steelman re-score on the frozen card (estimates; W2 owns the official scores)

Formula: Σ(weight × score)/5. Only the cells this steelman contests are changed. All other cells are W2's.

| Cell | W2 draft | Steelman | Evidence for the change |
|---|---|---|---|
| C. RHEL-family bootc · C2 (20) | 1 | **3** (2 if Pi 5 is discounted as experimental) | §2.1: Pi 5 documented and tested [S-01, S-03]; Jetson bootc GA [S-04]; CUDA `rhel10` [S-05]; kernel-rt [S-06]; ROS in containers [08 §6] |
| C · C3 (15) | 3 | 3 (a case for 4: sealed UKI + composefs digest + Secure Boot is documented [S-07], but see §8.5) | §2.2 |
| C · C4 (15) | 3 | 3 | RHDE, RHEL AI, OpenShift and Universal Blue are on this lineage [C-W2-041, S-10, S-11, S-14] |
| **C total** | **56.0** | **64.0** (60.0 with C2 = 2) | |
| A. Debian 13 + Rugix (ADR-001) | 56.0 | 56.0 (unchanged) | |
| D. Ubuntu 26.04 | 62.0 | 62.0 (unchanged) | |

**Reading it:** with C2 = 3, bootc **beats ADR-001 by 8.0** and ties Ubuntu (64 vs 62, a gap under 3). With C2 = 2 it **beats ADR-001 by 4.0** and ties Ubuntu (60 vs 62). Either way, the DC-01 numerical test ("outscores Debian + Rugix by 3 or more points") is met against the ADR proposal. The test isn't fully met, because G2 must also *PASS*, and the Pi 5 route is experimental (§8.1). A tie with Ubuntu is broken by decision-critical evidence: DC-05 (rebase without reflash, which bootc does by design), DC-07 (one update framework, where NVIDIA's own Jetson bootc image helps bootc) and Q-W2-1 (Canonical redistribution, a risk bootc does not have).

## 4. What OneMind would actually build (the runner-up made concrete)

1. **One `Containerfile` repo, three `FROM` lines:** `quay.io/almalinuxorg/almalinux-bootc-rpi:10` (Pi 5), `quay.io/almalinuxorg/almalinux-bootc:10` (x86/arm64), and NVIDIA JetPack for RHEL / RHDE (Jetson, paid). The same layer on top of each: k3s + k3s-selinux, the OneMind greenboot `required.d` k3s/core-pods check, the NATS leaf as a logically bound image, the Flight Control agent, and the OneMind signing policy.
2. **CI:** `podman build` → `bootc container lint` → cosign sign + SBOM attest → push to GHCR → `bootc-image-builder` for first-flash media (qcow2/raw/ISO). This is the same pipeline the cloud apps already use.
3. **Updates:** `bootc upgrade` / `switch`, staged, applied on a user-timed reboot (Umbrel/HAOS UX). greenboot on GRUB targets, and Pi firmware tryboot via `rpi-bootc-bootloader` on Pi 5, with its `sync` step driven by the greenboot success hook (INFERRED integration; untested).
4. **Fleet:** Flight Control (self-hosted, Apache-2.0) for the consumer and pro fleet. Red Hat Edge Manager for customers who buy support.
5. **Canary:** Fedora IoT bootc in CI on every Fedora release, as the 6-to-12-month early warning for the EL line (W2-R4 already proposes this).
6. **Paid tier:** the same Containerfile retargeted `FROM` RHEL 10 image mode for public-safety and industrial buyers who need the 62443 certificate and an SLA.

## 5. New sources opened for this steelman (2026-11-10)

| ID | Source | Type | Used in |
|---|---|---|---|
| S-01 | `github.com/AlmaLinux/bootc-images-rpi` @ `bb8e83e6b898db63ca2b53a69343f067dfa4f28a`: `README.md`, `10-rpi/Containerfile`, `10-rpi/kernel.yaml`, `10-rpi/almalinux-raspberrypi.repo`; releases API (2026-03-15-1, 2025-07-15-1) | PRIMARY (code) | §2.1, §2.5 |
| S-02 | `https://repo.almalinux.org/almalinux/10/raspberrypi/aarch64/os/Packages/` (raspberrypi2-kernel4-6.12.96-20260724.v8.1.el10) | PRIMARY (repo listing) | §2.1 |
| S-03 | `github.com/kfox1111/rpi-bootc-bootloader` @ `82739f4c9ae6de9ce071014bff9dee16842fb978`: `README.md`, `LICENSE`; tags v0.0.6–v0.0.8 | PRIMARY (code) | §2.1, §8 |
| S-04 | `https://access.redhat.com/node/7140448`, "Installing and deploying applications on RHEL-based Jetpack software for NVIDIA devices" (updated 2026-06-24) | PRIMARY (vendor KB) | §2.1, §2.5, §2.7 |
| S-05 | `https://developer.download.nvidia.com/compute/cuda/repos/` (rhel10, fedora40–45, debian13, ubuntu2604 present) | PRIMARY (repo listing) | §2.1 |
| S-06 | CentOS Stream 10 compose `CentOS-Stream-10-20261110.0` RT/x86_64 and NFV/aarch64 (`kernel-rt-6.12.0-282.el10`); `repo.almalinux.org/almalinux/10/RT/x86_64/os/Packages/` | PRIMARY (repo listing) | §2.1, §2.7 |
| S-07 | `bootc-dev/bootc@27f1e64ea93639929ed0088cdc230c220dac0fe6:docs/src/building/bootc-sealed-images.7.md#L5-L48` | PRIMARY (code/docs) | §2.2, §8.5 |
| S-08 | `bootc-dev/bootc@27f1e64:docs/src/bootc-logically-bound-images.7.md#L5-L54` | PRIMARY (code/docs) | §2.3 |
| S-09 | `github.com/flightctl/flightctl` @ `f99870eafa95003d1511577efc1c6e8c4ce7d5d1`: `README.md`; releases API (v1.4.0, 2026-11-09) | PRIMARY (code) | §2.4 |
| S-10 | RHEL AI `bootc-cuda-rhel9` catalog entry and RHEL AI 3.4 release notes (docs.redhat.com returned HTTP 403 to WebFetch) | SECONDARY (search metadata only) | §2.5 |
| S-11 | `developers.redhat.com/articles/2025/09/23/customize-rhel-coreos-on-cluster-image-mode`; OCP 4.19 "Image mode for OpenShift" docs | SECONDARY (search excerpt, not opened) | §2.5 |
| S-12 | `https://www.redhat.com/en/blog/supercharging-local-ai-development-rhel-nvidia-dgx-spark` (2026-05-12) | PRIMARY | §2.5 |
| S-13 | `https://ciq.com/blog/rocky-linux-from-ciq-bootable-container-images-bootc` | SECONDARY (vendor-stated, search excerpt) | §2.6 |
| S-14 | `bootc-dev/bootc@27f1e64:ADOPTERS.md` (full file, includes CIQ 2026, Luft 2026, Kheeper 2026, not in C-W2-025) | PRIMARY (code) | §2.6 |
| S-15 | `https://almalinux.org/blog/future-of-almalinux/` (2023-07-13): Red Hat "will no longer be providing the means for downstream clones to continue to be 1:1 binary copies"; AlmaLinux "will instead aim to be binary compatible with RHEL" | PRIMARY | §8.6 |
| S-16 | `github.com/bootcrew/mono` @ `5f048fa65a94daefc814d3cdd941d8d1e113c09e` (arch, debian, opensuse, ubuntu dirs); `bootcrew/debian-bootc` README "Debian Bootc experiment" | PRIMARY (code) | §8.8 |
| S-17 | `https://nullr0ute.com/category/kernel/`, "Fedora 44 on the Raspberry Pi 5" (2026-03-14; Fedora ARM maintainer's site; images hosted there, not official Fedora media) | SECONDARY (maintainer blog) | §8.1 |
| S-18 | `gh api repos/fedora-iot/iot-distro/issues/82` (open, last updated 2025-07-09); `coreos/bootupd/pulls/935` (open, last updated 2026-03-23) | PRIMARY | §8.1 |
| S-19 | `github.com/microshift-io/microshift` releases (4.22.0 OKD/SCOS builds, 2026-10-07); no licence field in the API | PRIMARY (metadata) | §8.7 |

## 6. Corrections this steelman found (for the ledger)

1. **03 §4 C-C2 = 1 ("no Pi 5") and 04 §212 ("no Pi tryboot or Jetson path shown") are out of date.** AlmaLinux bootc RPI images are documented and tested on Pi 5, with a firmware-tryboot bootloader [S-01, S-03]. NVIDIA JetPack for RHEL is a GA bootc image [S-04]. Re-score C2 against the anchor text, and re-score W3's bootc G2 cell from FAIL to CONDITIONAL.
2. **C-W2-025 (ADOPTERS) is incomplete.** The pinned file also lists direct adopters CIQ (2026), AlmaLinux Atomic SIG (2025), Universal Blue (2024), HeliumOS, ALT Atomic, Caligra and Luft [S-14].
3. **09 §1(b) "Fedora defaults RT builds off"** is true for Fedora but not for the lineage: kernel-rt ships in CentOS Stream 10 (x86_64 and aarch64) and AlmaLinux 10 (x86_64) [S-06].
4. **03 §9.1 "Fedora IoT issue #82 open"** is still accurate, but #82 hasn't been updated since 2025-07-09 and bootupd PR #935 since 2026-03-23 [S-18]. The Pi fix landed **beside** Fedora (AlmaLinux + rpi-bootc-bootloader), not through those two tickets. Track S-01/S-03 instead.

## 7. What would flip W2 toward the bootc lineage as THE base

All of these are testable within the first 90 days:
1. **W2-HW-3, re-pointed:** flash `image-almalinux-bootc-rpi-gpt-10` to a Pi 5 (NVMe and SD), `bootc switch` to a OneMind Containerfile with k3s + greenboot, then repeat lab H2/H3 using Pi tryboot. **Pass = automatic return to the good image with no console.** That turns C2 = 3 from documentation-only into lab-proven and G2 into PASS.
2. **Jetson Orin Nano on JetPack-for-RHEL bootc + k3s** (or MicroShift), with a CUDA pod and a `bootc switch` round trip. Pass = the GPU pod runs, and the switch and rollback work. That would show one update framework across all three boards (DC-07), which Ubuntu has not shown.
3. **Canonical declines modified-image redistribution, or Pro for Devices is priced high (Q-W2-1, Q168).** Ubuntu then drops out [03 §5], and the contest is bootc vs Debian, where bootc leads by 4–8 points.
4. **A Rugix rebase-without-reflash spike (DC-05) fails or needs repartitioning.** bootc's rebase is the standard command.
5. **NVIDIA lists RHEL with K3s in the GPU Operator matrix, or OneMind standardises on RKE2 for GPU nodes** (ADR D4 already names RKE2 for the hardened tier, and RHEL 10 is listed for RKE2 [C-W2-026]).

## 8. Genuine weaknesses (stated plainly)

1. **The Pi 5 route is experimental, and in practice it rests on one community maintainer.** AlmaLinux labels the images "*experimental*" and warns: "be careful with low endurance drives… cheep flash usb drives or sd cards can be used up fast". It lists "firmware updating" as an open issue ("You may need to perform some manual steps or reimage the pi") [S-01]. `rpi-bootc-bootloader` has 1 GitHub star, was created 2026-02-18, is at v0.0.8, and is pulled by `curl` from a personal repo during the build [S-03]. Its tryboot flow needs a manual `rpi-bootc-bootloader sync` to commit. **greenboot's automatic rollback is GRUB-only** [C-W2-023], so the Pi health gate is integration work OneMind would own. Fedora's own Pi 5 images are on a maintainer's personal site, not official media [S-17], and Fedora IoT #82 is stalled [S-18]. Pi 5 is the entry tier of F-14 and N-2. Today, Debian/Raspberry Pi OS (Umbrel, shipping) and Ubuntu (certified) are far more proven there.
2. **The Jetson path is paid and one generation behind.** JetPack for RHEL is RHEL **9.8**, Orin and IGX Orin only. **No Thor** was found [S-04, C-W2-041]. There's no free AlmaLinux Jetson route. RHEL 10 on DGX Spark is a "development preview" [S-12]. Ubuntu is still NVIDIA's day-one platform (JetPack 7, DGX OS).
3. **NVIDIA's GPU Operator does not list RHEL with K3s, and doesn't list Fedora at all** [C-W2-026]. On k3s, the GPU tiers use the host driver + Container Toolkit + device plugin (the same mitigation the ADR uses for Debian), or move to RKE2. W2's C7 point for Ubuntu stands.
4. **ROS 2 has no arm64 binaries on RHEL** (Tier 2 is amd64 only; Fedora is not listed) [C-W2-028]. Containers cover this, but robot integrators expect `apt install ros-*`, and the ROS ecosystem is Ubuntu-first.
5. **The sealed-boot path and the greenboot path pull in different directions.** Sealed images "Have systemd-boot available (and NOT have `bootupd`)" [S-07], while greenboot's counter lives in GRUB's grubenv [C-W2-023]. Choosing sealed boot later is a **bootloader change**, which C3 anchor 4 penalises. OneMind would need to pick a boot chain on day one.
6. **Red Hat governance risk is real and has happened.** In 2023 Red Hat stopped providing "the means for downstream clones to continue to be 1:1 binary copies", and AlmaLinux moved to "binary compatible" [S-15]. The free tier depends on AlmaLinux's ability to keep tracking CentOS Stream. CentOS Stream 10 itself ends 2030-05-31 [C-W2-014], and Fedora IoT's lead has said "We don't have the resources" for an oldstable tree [C-W2-019].
7. **Some "industrial" features are less Red Hat-specific than they look.** Fedora IoT's Rust FDO implementation was **deprecated on 2026-02-09**, and the maintained FDO code is distro-agnostic Go [09 P0-3, C-W8-042..044]. The 62443-4-2 certificate covers **RHEL 9.6 / MicroShift**, not AlmaLinux, CentOS or RHEL 10 [C-W2-042]. A free-tier OneMind box inherits none of it. MicroShift without a subscription is a community OKD build (`microshift-io`) with no licence field in its repo metadata [S-19]. That's a reason to keep k3s, not to adopt MicroShift.
8. **bootc on Debian/Ubuntu is still an experiment, so the format doesn't give a Ubuntu-Jetson bridge.** bootcrew's Debian and Ubuntu images describe themselves as experiments [S-16]. bootc's portability beyond the RPM world is a promise, not a product, as of 2026-11-10.
9. **x86 hardware floor.** RHEL 10 and default AlmaLinux 10 need x86-64-v3 [C-W2-011]. AlmaLinux offers an x86-64-v2 build, but third-party EL10 packages target v3 (AlmaLinux Kitten wiki, SECONDARY search excerpt). Older Atom/Celeron boxes may be excluded (W2-HW-5).
10. **Fewer constraint-matched consumer appliances.** No consumer self-hosting appliance comparable to HAOS or Umbrel ships on this lineage. The closest bootc consumer products are desktops and game consoles (Universal Blue, Playtron) [S-14]. The founder rule (§2 rule 2) prefers constraint-matched competitors, and Umbrel's Debian + Rugix is one. C4 stays at 3, not higher.
11. **The lab was QEMU on Apple Silicon, single runs** [W2-L1 RESULT, Limits]. Rollback across a k3s minor version (DC-12) is untested on any base. Logically bound images are a mitigation on paper only.

**Bottom line for the orchestrator:** ADR-001 dismissed this runner-up mainly on two board gaps. Both are now partly closed by primary evidence: a documented, Pi 5-tested AlmaLinux bootc image with firmware tryboot, and NVIDIA's own GA bootc JetPack for RHEL. On the frozen card, the RHEL-family bootc stack plausibly scores **60–64**, above ADR-001's Debian 13 + Rugix (56) and level with Ubuntu (62). It brings shipped code for the three things OneMind would otherwise build itself: health-gated rollback, in-place rebase and a bootc-native fleet manager. It does **not** clear G2 as a PASS until the Pi 5 route is shown on hardware, and its Jetson tier is paid and stops at Orin. The defensible minimum is W2-R3 (a bootc Industrial profile). The steelman's ask is more: **run §7 tests 1 and 2 before D2 is frozen.** If both pass, bootc should be the core base, with Fedora IoT as its canary.
