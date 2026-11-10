# Research Question Bank

Generated 2026-11-10 by 7 domain agents and 1 completeness critic, after they read REQUIREMENTS, ADR-001 and the conversation record. **335 questions in 9 sets** (Q324–Q335 added for the later founder briefs).

**Priority:** **P0** = blocks the foundation decision · **P1** = needed for the 1–2 year plan · **P2** = 5–10 year horizon.

The research agent must give **every** question a status (answered / partial / blocked) in `research-output/24-QUESTION-BANK-ANSWERS.md`, and may add questions.

> **Method substitutions (read before answering):** many methods below assume access you don't have.
> - **Live cluster, billing or private accounts:** use `context/01` (reported state). Answer `partial` and write the read-only commands for Zeus in `22-HARDWARE-LAB-TEST-PLAN.md`.
> - **Physical hardware:** use a QEMU/VM substitute where meaningful. Otherwise write a founder-runnable test and mark `blocked: founder-hardware`.
> - **Vendor contact, quotes or interviews:** use public sources only, and draft outreach in `evidence/outreach-drafts.md`.
> - **"Ask Zeus":** decide, state your assumption, and mark `blocked: founder-decision`.
>
> See RESEARCH-MISSION.md §3. Select the decision-critical subset first (§4).

## Base OS and longevity: distro, kernel, image pipeline, A/B updates, board support, supply chain and lifecycle (challenging ADR-001: Debian 13 + Rugix A/B + k3s/RKE2 + L4T flavor)

**Q1 [P0]** Across 2026-2036, what are the exact, primary-source support end dates (free and paid) for each candidate base: Debian 13/14/15 (regular, LTS, Freexian ELTS pricing), Ubuntu 24.04/26.04 (standard, ESM, Pro for Devices actual per-device price), RHEL 10 / AlmaLinux 10 / Rocky 10 / CentOS Stream 10 bootc, SLE Micro 6.x / openSUSE Leap Micro, Fedora CoreOS/IoT, Alpine, NixOS, Talos, Flatcar, Ubuntu Core 24/26, Yocto LTS (Scarthgap/Wrynose) and Buildroot LTS, and what does a 10-year per-device support cost model look like for each at 1k, 10k and 100k units?  
*Why:* ADR-001 picks Debian 13 partly on cost and support horizon, but trixie LTS ends 2030-06-30, well inside the 10-year hardware promise (R-3, H-1) and the EU CRA support-period obligation. The real comparison is the cost of covering 10 years, not the length of one release.  
*Method:* Read each vendor's lifecycle page, Freexian ELTS pricing, Canonical Pro for Devices (request a quote or find published OEM terms), SUSE/Red Hat edge subscription docs and the Yocto/Buildroot release wikis. Build a spreadsheet: date, cost per device per year, architectures covered, and the source URL with access date.

**Q2 [P0]** How many major-version rebases (for example Debian 13 to 14 to 15) does a 10-year appliance need, and how do Umbrel, Proxmox, TrueNAS SCALE and HAOS handle a base jump across an A/B image (data partition migration, k3s datastore, bootloader and partition-table changes)? Can Rugix move a fielded device to a new base without a reflash?  
*Why:* Picking a distro for 10 years is really picking a rebase strategy. If a base upgrade needs a reflash, field devices (robots, off-grid boxes) get stranded.  
*Method:* Reverse-engineer the Umbrel 1.x to 2.0 migration, Proxmox 8 to 9 and TrueNAS 24 to 25 upgrade paths (release notes, upgrade scripts in their repos) and the HAOS partition-resize migrations (operating-system repo, rauc hooks). Test on the Beelink: build a Debian 13 Rugix image, then a Debian 14 testing image, and attempt an A/B update across them.

**Q3 [P0]** Is a Debian-based image (Rugix or debos/mkosi) truly better than a build-from-source system (Yocto or Buildroot as HAOS uses) on reproducibility, SBOM completeness, CVE triage effort, image size and boot time for our target boards? Measure the same minimal OneMind image (kernel, systemd, containerd, k3s) built both ways.  
*Why:* HAOS chose Buildroot and Umbrel chose Debian, and both work. ADR-001 copies Umbrel without measuring the maintenance cost of carrying thousands of Debian packages versus a minimal from-source image, which is what CRA and SBOM work will charge for.  
*Method:* Build both images for x86-64 and Pi 5 in CI. Compare reproducible-build results (diffoscope across two builds), SBOM output (syft or Yocto create-spdx), package count, CVE count from grype/trivy against each, image size, cold-boot time to k3s Ready, and engineer-hours per monthly security rebuild.

**Q4 [P0]** What is Rugix's real maturity and bus factor: who maintains it (Silitics), how many contributors and commits in the last 12 months, release cadence, issue response times, production users besides Umbrel, funding model, and does the license (MIT/Apache-2.0) cover rugix-ctrl, rugix-bakery and the bootloader integration? What is the exit plan if it is abandoned?  
*Why:* ADR-001 makes Rugix the core update mechanism on the strength of one adopter. An update framework is the hardest component to swap after devices ship.  
*Method:* GitHub API analysis of rugix/rugix (contributors, commit graph, releases, open/closed issue ratio), reading the LICENSE files, searching for public adopters, and contacting the maintainers. Compare the same metrics for RAUC, Mender, SWUpdate, OSTree/bootc and Kairos.

**Q5 [P0]** Feature-by-feature, how do Rugix, RAUC, Mender (OSS vs Enterprise), SWUpdate, OSTree/rpm-ostree/bootc, Kairos, Ubuntu Core snaps, balenaOS and NVIDIA L4T A/B (nv_update_engine / Capsule) compare on: signature and key-rotation model, delta/streaming updates over flaky or metered links, a health-check commit hook, the bootloaders supported (GRUB, systemd-boot, U-Boot, Pi tryboot, UEFI capsule, Jetson UEFI), Secure Boot/TPM integration, offline USB updates and fleet server options?  
*Why:* OneMind must update everything from a Pi to a Jetson robot to an x86 GPU box, often offline (homestead, field, TAK). Two or three different update stacks across flavors would cost a sole developer far more than any single feature.  
*Method:* Primary docs plus source reading of each project. Build a matrix with one row per board family. Validate the top two hands-on: forced-failure rollback, power-pull during write, USB offline bundle, and a 50 MB delta over a throttled link (tc netem at 64 kbps with 10% loss).

**Q6 [P0]** Can ONE update framework cover x86 UEFI, Raspberry Pi 5/CM5, Jetson Orin/Thor and Rockchip boards, or is a per-flavor framework unavoidable? Specifically, can Rugix or RAUC drive Jetson's UEFI A/B rootfs slots and bootloader capsule updates without breaking NVIDIA's OTA path and JetPack upgrades?  
*Why:* ADR-001 leaves the Jetson A/B method open (Kairos vs NVIDIA vs RAUC), yet robotics is declared the moat (M-7). If the robot flavor runs a different update system, the moat platform gets the weakest updates.  
*Method:* Read the NVIDIA Jetson Linux developer guide (rootfs A/B, UEFI capsule update, image-based OTA tools), meta-tegra (OE4T) RAUC/Mender/SWUpdate integrations, and the Kairos Jetson docs. Hardware test on an Orin Nano/NX dev kit: install with RAUC via meta-tegra versus the NVIDIA OTA tools versus Kairos, then do a forced rollback.

**Q7 [P0]** Should the Jetson flavor be NVIDIA's stock L4T Ubuntu, a Yocto meta-tegra build (OE4T), or a Debian/Ubuntu rootfs on the L4T BSP? Compare JetPack component availability (CUDA, TensorRT, VPI, DeepStream, Isaac ROS, Holoscan), NVIDIA support status, security update cadence, image size and boot time.  
*Why:* The L4T flavor in ADR-001 inherits Ubuntu's full userspace and Canonical's ESM terms, which contradicts the reason Debian was chosen. Several robotics companies ship meta-tegra instead.  
*Method:* NVIDIA Jetson Linux release notes and the JetPack 6/7 component matrix, the OE4T meta-tegra README and supported-release table, and Isaac ROS container requirements. Build all three on an Orin dev kit; run a TensorRT + Isaac ROS benchmark plus a Holoscan sample, then measure and compare.

**Q8 [P0]** What is the real Jetson BSP lifecycle: for Orin (JetPack 6 to 7) and Thor (JetPack 7), how long does NVIDIA ship kernel and security updates per L4T release, how does that line up with Jetson module EOL dates (Orin until at least 2032?), and how far behind mainline is the L4T kernel? How much of Orin and Thor is upstream in mainline Linux today (DRM/display, GPU via nouveau/nova, camera/ISP, PCIe, NVENC)?  
*Why:* Robots and drones sold as long-term products must not get stuck on a frozen vendor kernel. This decides whether mainline-plus-blobs is realistic in 5 to 10 years.  
*Method:* NVIDIA Jetson product lifecycle page, L4T release cadence history (r32/r35/r36/r38), and the upstream kernel tree (arch/arm64/boot/dts/nvidia, drivers/gpu, tegra mailing list). Count upstreamed vs downstream-only drivers from the OE4T linux-tegra diff against mainline.

**Q9 [P0]** Raspberry Pi 5 / CM5 on Debian: what exactly does Umbrel take from Raspberry Pi's kernel/firmware repos versus Debian main, how does Raspberry Pi OS (trixie) handle bootloader EEPROM updates and tryboot-based A/B, and what support does Raspberry Pi Ltd commit to (production lifetime of Pi 5 and CM5 to at least 2036; kernel LTS cadence)?  
*Why:* Pi 5 is the Lite tier and the entry point for specialized OS profiles (P-8). ADR-001 depends on Umbrel's undocumented Pi pipeline and stock Debian is not Pi 5 certified.  
*Method:* Reverse-engineer the umbrelOS image build (rugix bakery recipes in getumbrel repos) for the Pi layers. Read Raspberry Pi product-obsolescence statements, the rpi-eeprom repo and tryboot docs. Hardware test: Pi 5 with Rugix tryboot A/B plus an EEPROM update plus a rollback.

**Q10 [P0]** Which kernel strategy gives the best 10-year outcome: Debian's stable kernel, mainline LTS (6.12/6.18 CIP SLTS) built ourselves, vendor BSP kernels per board, or a mix? What is the Civil Infrastructure Platform (CIP) SLTS 10-year kernel offer, which boards does it cover, and what does membership cost?  
*Why:* Kernel ownership is the biggest long-term cost and the source of most security fixes. CIP was created to give industrial devices 10-year kernels, exactly the R-3 and CRA problem.  
*Method:* CIP project docs (SLTS kernel schedule, reference hardware, membership tiers), kernel.org LTS schedule, and Debian kernel team policy. Map each target board to which kernel it can run (mainline, CIP, vendor) with a citation.

**Q11 [P0]** Is PREEMPT_RT, now merged in mainline since 6.12, good enough on our boards for robotics control loops? Measure cyclictest worst-case latency under load (k3s, containers, GPU inference) on x86 mini PC, Pi 5 and Jetson Orin, stock vs RT kernel. Does running k3s with real-time pods (CPU isolation, isolcpus, the static CPU manager policy) preserve those numbers?  
*Why:* M-7 says robotics must be optimized from day one. If control loops cannot share a node with the Kubernetes platform, the node architecture (separate MCU/RTOS, or a partitioning hypervisor) changes fundamentally.  
*Method:* Hardware tests with cyclictest/rt-tests and stress-ng, plus k3s with the kubelet CPU manager static policy and a ros2_control demo. Read NVIDIA's Jetson RT kernel docs (L4T ships an RT variant) and Raspberry Pi RT notes. Publish latency histograms.

**Q12 [P0]** How do HAOS, umbrelOS, Olares, ZimaOS, StartOS, Proxmox VE, TrueNAS SCALE, balenaOS and Talos actually build and ship images? For each: build system (Buildroot, debos, rugix-bakery, mkosi, live-build, Yocto, custom), CI infrastructure, signing keys and where they live, partition layout, bootloader, update server/CDN, release channels, and the size of the team maintaining the OS layer.  
*Why:* The founder's rule is to copy proven competitors. ADR-001 covers only three of them, and in limited depth. Team size versus scope tells a sole developer what is realistically maintainable.  
*Method:* Clone and read each public repo: home-assistant/operating-system, getumbrel/umbrel, beclab/Olares, IceWhaleTech/ZimaOS, Start9Labs/start-os, the Proxmox git, truenas/scale-build, balena-os/meta-balena, siderolabs/talos. Reconstruct each pipeline, inspect a downloaded image (partition table, fs types, bootloader config), and count active OS-layer committers.

**Q13 [P0]** Would an immutable, Kubernetes-native OS (Talos Linux, Kairos, Flatcar, Fedora CoreOS/bootc, SLE Micro, Ubuntu Core) beat a custom Debian+Rugix image for OneMind's k3s-first design? Test each on the Beelink, Dell 5540 and Pi 5 for: install UX, API-driven config, A/B and rollback, k3s/RKE2 support, GPU (NVIDIA) extension story, Pi 5 and Jetson support, and the ability to add host-level services (NATS leaf, Tailscale, mesh radios).  
*Why:* ADR-001 dismissed Kairos on Pi 5 support and the cloud-init commit, but never evaluated Talos, Flatcar, bootc or SLE Micro, which are purpose-built for this. The founder also raised Fedora CoreOS/IoT, which has not been answered.  
*Method:* Hands-on installs on the hardware on hand, using each project's docs (Talos SBC and Pi support matrix, image factory system extensions for NVIDIA; Fedora IoT/CoreOS on Pi; bootc-image-builder; SLE Micro Pi support; Ubuntu Core 24 models). Score against a fixed rubric, with timing and failure logs.

**Q14 [P0]** Is bootc (OCI container images as the OS, used by Fedora/CentOS/RHEL image mode and now a CNCF sandbox project) a better long-term update primitive than block-level A/B, given that OneMind already runs an OCI registry and GitOps? Can bootc deliver a Debian-based image (bootc-debian experiments), and how does it handle rollback, offline updates and small eMMC/SD devices?  
*Why:* If the OS ships as an OCI image, the same registry, signing (cosign/sigstore), SBOM attestations and Argo-style tooling cover both OS and apps. That is a big simplification for one developer and the direction Red Hat and others are heading.  
*Method:* bootc upstream docs and repo, the CNCF sandbox application, the Fedora/CentOS bootc docs, and community Debian/Ubuntu bootc builds. Hands-on: build a bootc image with k3s on x86, upgrade, roll back, and run offline upgrade from a USB OCI archive. Measure update size versus a Rugix delta.

**Q15 [P0]** Should OneMind use a Yocto/OpenEmbedded base (possibly with meta-tegra, meta-raspberrypi, meta-rockchip, meta-virtualization for k3s, and meta-rauc/meta-mender) as the single cross-board build system, as most commercial embedded and robotics products do? What is the measured cost for one developer (build times, cache size, upgrade effort between Yocto LTS releases)?  
*Why:* Yocto is the industry norm for products sold with long support, and the only option with first-class BSP layers for every target board. ADR-001 did not evaluate it.  
*Method:* Yocto Project docs and LTS policy, layer index for the BSP layers. Do a spike build of core-image-minimal plus k3s for qemux86-64, raspberrypi5 and jetson-orin-nano-devkit using sstate mirror and hash equivalence. Record build hours, disk and rebuild times.

**Q16 [P0]** For the x86 GPU tier, does NVIDIA's debian13 driver repo plus Container Toolkit plus k8s device plugin (or the DRA driver) give parity with the GPU Operator on Ubuntu for MIG, time-slicing, MPS, vGPU, CUDA forward compatibility and driver upgrade without reboot? What is NVIDIA's committed support for Debian in the driver, CUDA and GPU Operator release notes, and is open-kernel-module (nvidia-open) signing compatible with our Secure Boot plan?  
*Why:* N-8 makes NVIDIA a major partner. If NVIDIA validates only Ubuntu and RHEL, the Debian core may fight NVIDIA on every release; this could flip the base decision for the Pro/Omni tiers.  
*Method:* NVIDIA CUDA install guide platform table, GPU Operator platform support page, nvidia-container-toolkit docs, DRA driver repo. Hardware or cloud GPU test: install on Debian 13 and Ubuntu 24.04 with k3s; run MIG/time-slicing, a driver upgrade, and Secure Boot with a MOK-signed nvidia-open module.

**Q17 [P0]** What exactly does the EU Cyber Resilience Act require of OneMind as a hardware seller and as an open-source steward (Apache-2.0 core): SBOM format, vulnerability handling, minimum support period and how it is set, update delivery obligations, conformity assessment class (is a home-server or robot OS an important/critical product?), and how do the base-OS choice and upstream support windows affect compliance? Include equivalents: US Cyber Trust Mark, UK PSTI, and NDAA/FCC rules for drones.  
*Why:* CRA reporting applies from 2026-09-11 and main obligations from 2027-12-11, before or around the first hardware sale. The support period declared must be backed by the base OS lifecycle.  
*Method:* Read Regulation (EU) 2024/2847, its annexes and the Commission implementing acts and harmonised standards drafts; ENISA guidance; OpenSSF and Eclipse ORC CRA guidance for open-source stewards; UK PSTI regulations; FCC Cyber Trust Mark rules; NDAA section 848 and Blue UAS framework for drones.

**Q18 [P0]** k3s vs RKE2 vs k0s vs MicroK8s vs Talos-native Kubernetes vs plain kubeadm for the long term: what are SUSE's actual support lifecycles for k3s and RKE2 (still UNVERIFIED in ADR-001), what is k3s's release and CVE patch cadence, can a single fleet run k3s on small nodes and RKE2 on hardened nodes and federate them, and what does Olares change in its k3s fork?  
*Why:* ADR-001 lists the SUSE k3s lifecycle as unverified. The Kubernetes distro is welded to the OS image (it is part of the health-check commit), so its lifecycle is part of the base decision.  
*Method:* SUSE/Rancher support matrix and lifecycle pages, the k3s and RKE2 GitHub release history, k0s (Mirantis) and MicroK8s (Canonical) docs. Diff the Olares k3s fork against upstream. Measure k3s idle RAM/CPU on the Pi 5 and Beelink versus k0s.

**Q19 [P0]** Is Kubernetes on every node right for the smallest and most constrained nodes (Pi Zero/sensor gateways, drones, battery-powered field kits), or should OneMind define a tiered node model: full k3s nodes, a lightweight agent node (for example a NATS leaf + container runtime + MHS/MCP agent), and MCU-class devices? What do KubeEdge, OpenYurt, Akri, balena, and Azure IoT Edge show about this split?  
*Why:* N-9 is still open (Kubernetes everywhere vs hybrid), and the base-OS image design depends on what runs on the smallest node.  
*Method:* Read KubeEdge, OpenYurt and Akri architecture docs and adopter case studies; measure k3s agent footprint on a Pi Zero 2 W and Pi 5 vs a NATS leaf plus podman. Map each N-1 node type to a node class with evidence.

**Q20 [P0]** How do ROS 2 distributions bind to the base OS (ROS 2 Kilted, Lyrical and their Tier 1 platforms: Ubuntu 24.04/26.04, RHEL; Debian only Tier 3), and what is the cost of running ROS 2 and Isaac ROS in containers on a Debian host versus natively on Ubuntu? Do robotics partners and customers expect Ubuntu?  
*Why:* ROS 2's Tier 1 is Ubuntu, so the Debian core may be second-class for the robotics moat unless everything robotics is containerized; this tests ADR-001's claim that apps do not care about the host.  
*Method:* REP-2000 (ROS 2 target platforms), ROS 2 release pages, Isaac ROS docs. Hardware test on Orin and x86: ROS 2 + Isaac ROS in containers on Debian 13 vs Ubuntu 24.04 host; compare DDS/Zenoh latency, GPU access, and device access (cameras, CAN, serial).

**Q21 [P0]** Does the proposed 'healthy before commit' rule (commit the A/B slot only after k3s and core pods are healthy) hold up in practice: what timeouts, which pods, what happens if the data partition or a user app is the failure cause rather than the OS, and how do we avoid rollback loops or bricking when the network is down at first boot? How do Kairos, Talos, Flatcar (update_engine + locksmith) and HAOS define health?  
*Why:* This is ADR-001's main improvement over competitors, but the commit criteria are unspecified and a bad definition causes either false rollbacks or committed broken updates.  
*Method:* Read the health-check implementations in HAOS (Supervisor), Talos (machined), Flatcar update_engine and Kairos. Prototype on the Beelink with Rugix: inject failures (broken kernel, broken k3s, broken app, no network, full disk) and record outcomes for each policy.

**Q22 [P1]** Should hard-real-time and safety-critical robot functions run on Linux at all, or on a companion MCU/RTOS (Zephyr, NuttX/PX4, micro-ROS) or a partitioning hypervisor (Jailhouse, Xen dom0less, ACRN, Bao) alongside the OneMind Linux? What do PX4, ArduPilot, Unitree, Boston Dynamics Spot (CORE I/O), Clearpath and NVIDIA Isaac reference robots actually do?  
*Why:* This challenges the assumption that the OneMind OS image is the robot's whole OS, and defines the node boundary for drones and robots.  
*Method:* Read the architecture docs and teardowns of PX4 (NuttX FMU + Linux companion), ArduPilot, Spot CORE I/O, Clearpath, Unitree Go2/G1 (reverse-engineer published firmware where legal), and NVIDIA Isaac AMR. Test Jailhouse or Xen dom0less on Orin or x86 if practical.

**Q23 [P1]** Is NixOS a serious candidate for the base or for a developer edition, given declarative full-system config, atomic rollback, reproducible builds and strong Pi/Jetson community support (nixos-hardware, jetpack-nixos by Anduril)? What are its real costs (learning curve, appliance A/B story, security-support lifecycle, enterprise acceptance)?  
*Why:* Anduril, a defense robotics company, maintains jetpack-nixos, which shows that robotics/defense players chose Nix for Jetson. Declarative config also fits an AI agent managing the OS (AI-4).  
*Method:* Read anduril/jetpack-nixos, nixos-hardware, NixOS release and security policy, and nixos appliance projects (for example nixos-generators, nix-community disko, and image-based update work). Build a NixOS k3s image for Orin and Pi 5 and compare with the Debian prototype.

**Q24 [P1]** Which ARM SoC families beyond Pi and Jetson are viable 10-year targets (Rockchip RK3588/RK3576 via Radxa/Orange Pi/Turing RK1, Qualcomm QCS6490/IQ9 with Ubuntu or Qualcomm Linux, NXP i.MX 95, MediaTek Genio, AMD/Xilinx Kria) given mainline upstream status, NPU driver openness (rocket/RKNPU, Ethos, Hexagon), vendor longevity commitments and price?  
*Why:* H-3 needs simple through powerful tiers, and depending only on NVIDIA and Raspberry Pi is the lock-in that sovereignty warns against. Mainline status determines whether a 10-year image is possible.  
*Method:* Collabora RK3588 mainline status, kernel source tree, Qualcomm Linux and Ubuntu IoT for Qualcomm announcements, NXP longevity program, vendor EOL pages. Boot test of mainline Debian or Armbian on an RK3588 board with k3s and NPU inference.

**Q25 [P1]** How does each candidate base handle reproducible builds and supply-chain attestation: Debian reproducible-builds percentage and snapshot.debian.org pinning, Yocto reproducibility and SPDX 3.0 output, NixOS, Fedora/bootc; can we reach SLSA Build L3 for the OS image with in-toto/sigstore attestations, and what does Umbrel's pinned-snapshot approach actually pin?  
*Why:* Selling sovereign hardware to public safety and the EU requires provable provenance. CRA, US federal procurement (SSDF) and customers will ask for SBOMs and build provenance.  
*Method:* reproducible-builds.org stats, Debian snapshot docs, Yocto SPDX/create-spdx docs, SLSA spec, sigstore/cosign docs. Reverse-engineer the umbrelOS build for its snapshot pin. Build our image twice on separate runners and diff with diffoscope.

**Q26 [P1]** What are the governance and vendor-risk profiles of each upstream we depend on (Debian, Canonical, Red Hat/IBM, SUSE (k3s, RKE2, Longhorn, SLE Micro), NVIDIA, Raspberry Pi Ltd, Silitics (Rugix), Sidero (Talos), Spectro Cloud (Kairos)) including license-change history (for example HashiCorp BUSL, Red Hat source access changes, Broadcom/VMware), ownership changes, and the fork path if terms change?  
*Why:* Sovereignty is the product. Building it on a component whose owner can change terms (as happened with RHEL sources and Terraform) undermines the core promise and the 10-year plan.  
*Method:* Project governance docs, foundation membership (CNCF, LF, OSI), license history, corporate filings and news. Produce a risk register rating each dependency on license, ownership, bus factor and fork viability, with citations.

**Q27 [P1]** For drones specifically, what OS and update stack do the leading open and defense-oriented platforms use (PX4 on NuttX + companion computer, ArduPilot, Auterion Skynode/AuterionOS, ModalAI VOXL (QRB5165 + its OS), Skydio, Blue UAS-cleared platforms), and can OneMind's Jetson or Qualcomm flavor serve as the companion computer OS while staying NDAA/Blue UAS friendly?  
*Why:* Drones are named as part of the moat. AuterionOS is an existing commercial drone OS and a competitor or model, and US public-safety buyers require NDAA-compliant stacks.  
*Method:* Auterion and ModalAI public docs and SDK repos (voxl-* on GitLab), PX4 companion computer docs, DIU Blue UAS lists. Reverse-engineer a published VOXL system image if obtainable (ask Zeus per RS-6).

**Q28 [P1]** How do hardware interfaces robots and field kits need (CAN/SocketCAN, GMSL/MIPI CSI cameras, LiDAR over Ethernet, IMUs over SPI/I2C, PTP/gPTP time sync, USB serial radios such as Meshtastic, LoRa HATs, SDR) get exposed through a read-only A/B image into k3s pods safely? Which device plugin or DRA patterns (Akri, smarter-device-manager, generic-device-plugin) work, and how are device-tree overlays managed across A/B updates?  
*Why:* N-4 (QR onboarding of robots and IoT) and N-6 (native mesh) need host hardware passed through the immutable OS to containers, and device-tree overlays are often where A/B images break.  
*Method:* Kubernetes DRA docs, Akri and squat/generic-device-plugin repos, Raspberry Pi config.txt/overlay docs, Jetson pinmux and device-tree overlay docs. Hardware test: SocketCAN USB adapter, a CSI camera on Pi 5 and a Meshtastic radio exposed to pods, surviving an A/B update.

**Q29 [P1]** What is the right boot security chain per board, and in what order should it be rolled out: UEFI Secure Boot + shim + signed UKI + TPM2-sealed LUKS (systemd-cryptenroll, measured boot) on x86; Raspberry Pi 5 secure boot (rpi-sb-provisioner, OTP keys) and its limits; Jetson fuse-based secure boot and OP-TEE disk encryption? What breaks with A/B (key rotation, PCR policy updates on kernel change, recovery), and how does Microsoft's 2026 Secure Boot CA expiry and rotation affect a 10-year x86 device?  
*Why:* Phase 2 of D6 promises Secure Boot, TPM and fusing. Fusing is irreversible, and the 2011 Microsoft CA certificates expiring in 2026 directly affect fielded x86 boxes.  
*Method:* systemd UKI/cryptenroll docs, Microsoft Secure Boot certificate update guidance, Raspberry Pi secure boot docs and rpi-sb-provisioner repo, NVIDIA Jetson security guide. Hardware test on the Dell 5540: signed UKI + TPM2-sealed LUKS through an A/B update and rollback.

**Q30 [P1]** What image partitioning, filesystem and storage choices survive 10 years of field use on SD, eMMC, NVMe and HDD: EROFS vs squashfs root, ext4 vs btrfs vs ZFS vs XFS for data, wear behavior on SD/eMMC under k3s/etcd/SQLite write load, and power-loss resilience? How do HAOS, Umbrel (ZFS FailSafe), TrueNAS and balena handle this?  
*Why:* k3s datastores and container layers write constantly, killing SD cards; off-grid users will pull power. The D5 layout needs evidence on wear and power-loss behavior.  
*Method:* Read HAOS partition docs, Umbrel FailSafe docs, OpenZFS on ARM notes. Run 72-hour write-amplification tests (iostat, smartctl/mmc extcsd life estimate) of k3s on Pi 5 SD vs NVMe, and repeated power-cut tests with a relay-controlled supply during writes and updates.

**Q31 [P1]** How should OneMind produce and maintain specialized OS profiles (P-8: TAK situational awareness box, greenhouse Pi, robot, drone companion, NAS, GPU AI box) from one build pipeline: layered image recipes (Rugix layers, mkosi profiles, Yocto distros/machines, bootc derived images, Talos extensions, Buildroot defconfigs)? Which approach keeps the matrix (profiles x boards x channels) testable by one developer with CI?  
*Why:* The product promises many profiles across many boards. Matrix explosion is the main way a sole-developer OS project fails.  
*Method:* Compare documented layering in Rugix bakery, mkosi, Yocto, bootc and Talos image factory. Prototype two profiles x three boards in GitHub Actions/self-hosted runners; measure build time, cache sizes and test-run time on real hardware via a small hardware-in-the-loop rig.

**Q32 [P1]** What does hardware-in-the-loop (HIL) testing for an OS image look like at small scale (labgrid, LAVA, Timesys, openQA, balena autokit, Tuxsuite), and what minimum test lab (boards, USB-SD muxes, power switches, serial consoles) would let one developer gate every release on Pi 5, x86 and Jetson?  
*Why:* A/B rollback only protects users if releases are tested on real boards before shipping. R-1 and R-2 require that, and the cluster plus Backstage could host it.  
*Method:* Read the labgrid, LAVA and openQA docs and how HAOS, Raspberry Pi and Linaro test images. Price a bill of materials for a 4-board lab and prototype labgrid with one Pi 5 and the Beelink, driven from the existing Argo/Backstage setup.

**Q33 [P1]** How should the existing DigitalOcean Kubernetes (DOKS) cluster with Argo CD, Backstage, NATS, Authentik and Tailscale be used as the proof-of-concept control plane for the OS: OS image build CI, signed update server/CDN, fleet inventory in the Backstage catalog, release channels, and telemetry? What do Mender server, hawkBit (Eclipse), balenaCloud open-balena, Rugix fleet and Talos Omni provide that we would otherwise build?  
*Why:* The founder wants the cluster and Backstage shown as a proven concept of OneMind's infrastructure. The update/fleet server is the other half of the base-OS decision and must also work fully self-hosted and offline.  
*Method:* Inventory the live cluster read-only through the onemind-kubernetes and onemind-backstage MCP tools. Read Eclipse hawkBit, open-balena, Mender OSS server and Omni docs/licenses. Prototype: hawkBit or a static signed-bundle repo served from the cluster, pushing a Rugix/RAUC update to the Beelink over Tailscale.

**Q34 [P1]** How do updates work fully offline and in disconnected or mesh-only deployments (homestead, disaster response, TAK field kits): sneakernet USB bundles, one box acting as update mirror for a mesh (OCI registry mirror, apt/snapshot mirror, peer-to-peer distribution like Spegel, Kraken or Dragonfly), signature validity and clock problems without NTP/GNSS, and key revocation without Internet?  
*Why:* N-6 and the off-grid user base make offline updates a core requirement, not an edge case. Signature expiry and revocation checks often break when devices are offline for months.  
*Method:* Read RAUC/Rugix/bootc offline-update docs, Spegel and Dragonfly docs, TUF (The Update Framework) spec on freshness and offline. Test: an air-gapped Beelink + Pi 5 receiving OS and app updates from a USB bundle and from a peer box, with the clock deliberately wrong.

**Q35 [P1]** Should OneMind adopt The Update Framework (TUF) or Uptane (automotive OTA security standard) semantics for OS, k3s, app and firmware updates, and how do Rugix's signing model, RAUC's x.509 model, sigstore/cosign and Notary v2 map onto them? Where do the offline root keys live (HSM, YubiHSM, Nitrokey), and what is the key-compromise recovery procedure for fielded devices?  
*Why:* Signing is the single point of failure for a fleet. Uptane exists precisely for safety-critical vehicles, which robots and drones increasingly resemble.  
*Method:* TUF and Uptane specs, Rugix and RAUC signing docs, sigstore docs, published key-ceremony write-ups (Umbrel, Tor, Debian, HAOS if public). Write a key hierarchy design and test a key rotation and revocation on a test fleet.

**Q36 [P1]** What firmware layers sit below the OS on each board and how will they be updated and supported for 10 years: x86 UEFI via LVFS/fwupd (which mini-PC vendors such as Beelink, Minisforum, ASRock and Dell support it), Pi EEPROM, Jetson QSPI/UEFI capsules, Rockchip SPI/U-Boot, NVMe and Wi-Fi firmware, and BMC/out-of-band options (OpenBMC, PiKVM, Intel AMT, Jetson recovery mode)?  
*Why:* Firmware is a separate update layer in D3 and a common source of bricked or vulnerable devices. Choosing hardware vendors with LVFS support is a hardware-business decision tied to the base OS.  
*Method:* LVFS vendor list and device database, fwupd docs, NVIDIA capsule update docs, rpi-eeprom repo, PiKVM and OpenBMC docs. Check the Dell 5540 and Beelink U55 with fwupdmgr; contact candidate box ODMs on BIOS update and source-access policies.

**Q37 [P1]** For OneMind-branded hardware (H-1 to H-4), what do Umbrel Home/Pro, Olares One, ZimaCube/ZimaBoard, Home Assistant Green/Yellow, Start9 Server and balenaFin use for board, ODM, firmware, factory flashing and provisioning (serials, keys, device identity), and what is the cheapest path to a factory-provisioned, secure-boot-ready OneMind box with a 10-year parts and firmware guarantee?  
*Why:* The base OS must match the factory process: secure boot keys, device certificates and image provisioning are set at manufacture and cannot be fixed later.  
*Method:* Teardowns and FCC ID filings (fccid.io) of competitor boxes, vendor spec pages, ODM listings, HA Yellow/Green published schematics, Raspberry Pi CM5 provisioning docs and rpi-sb-provisioner. Ask ODMs for quotes on BIOS customization and lifetime commitments.

**Q38 [P1]** What do sovereign, defense and public-safety buyers require from the base OS for procurement (FIPS 140-3 validated crypto modules, DISA STIGs/CIS benchmarks for Debian vs Ubuntu vs RHEL vs SLE, Common Criteria, FedRAMP edge, CJIS for public safety, BSI/ANSSI qualifications in the EU), and which bases have validated modules available without paid subscriptions?  
*Why:* RKE2 provides FIPS for Kubernetes, but the host OS crypto must also be validated for public-safety and enterprise tiers. Debian has no FIPS-validated OpenSSL, which may push the hardened tier to Ubuntu Pro, RHEL clones or SLE Micro.  
*Method:* NIST CMVP validated module search, DISA STIG library, CIS benchmark list, Canonical FIPS docs, Red Hat/Alma/Rocky FIPS status, SUSE certifications, CJIS Security Policy, BSI and ANSSI product lists.

**Q39 [P2]** What is the realistic status and timeline of RISC-V for OneMind targets (SpacemiT K1/K3, SiFive P870, StarFive, Milk-V, Sophgo SG2044; RVA23 profile compliance; Debian and Ubuntu official riscv64 support; UEFI/EBBR boot; GPU/NPU drivers)? At what point (year) could a RISC-V OneMind box be a credible sovereign alternative?  
*Why:* RISC-V is the strongest sovereignty hedge against ARM and x86 licensing and export controls over a 5 to 10 year horizon, and EU/US/China sovereignty programs are funding it.  
*Method:* RISC-V International profile docs, Debian riscv64 release status, Ubuntu RVA23 policy, vendor roadmaps, Phoronix and LWN coverage. Boot test of Debian riscv64 plus k3s on an available RVA22/RVA23 board.

**Q40 [P2]** Which desktop and client editions should share the core: the Omarchy (Arch + Hyprland) desktop edition, a Debian/Fedora Atomic desktop, or a separate client-only app? Can an Arch-based rolling desktop coexist with a fixed-release appliance core under one support promise, and how do Universal Blue/Bazzite (bootc-based desktops) maintain rolling-yet-atomic images?  
*Why:* UX-10 asks for an Omarchy desktop option; a second base distro doubles the security and support load unless built on the same image technology.  
*Method:* Omarchy repo and docs, Universal Blue and Bazzite build pipelines (bootc + GitHub Actions), Fedora Atomic docs. Estimate the maintenance load of each option in engineer-hours per month from their commit and release history.

**Q41 [P2]** What 5 to 10 year trends could force a base change, and what decision points should the plan schedule: Debian 15 timing, Ubuntu 28.04, the RHEL 10 to 11 cycle, bootc and image-mode adoption, Rust in the kernel and Rust userspace (uutils, sudo-rs) in distros, mainline NVIDIA (nova driver), RISC-V RVA23 hardware, EU sovereign-OS initiatives (for example openDesk, EU OS proposals, Gaia-X), export-control or tariff effects on NVIDIA/ARM/Rockchip/Chinese boards?  
*Why:* The founder wants a plan that lasts given what is happening in the world. The plan needs explicit re-evaluation gates rather than a one-time pick.  
*Method:* Distro roadmap announcements, LWN and kernel mailing-list summaries, NVIDIA open-driver roadmap, EU OS and openDesk project pages, US BIS export-control rules and FCC covered-list updates. Produce a dated decision calendar (2027 to 2036) with trigger conditions.

## Robotics, drones, physical AI & simulation (ROS 2, RT Linux, middleware, flight stacks, fleet mgmt, NVIDIA/non-NVIDIA edge AI, safety & regulation, sim/digital twin, teleop, robot OS image shipping)

**Q42 [P0]** Which ROS 2 distros (Jazzy LTS to May 2029, Kilted, Lyrical LTS due May 2026) provide Tier-1 binary packages for Debian 13 trixie (amd64 and arm64), versus only Ubuntu 24.04/26.04? If Debian is Tier-3/source-only, what does it cost (build time, CI, breakage per sync) to maintain our own trixie apt repo of ROS 2 for 5+ years?  
*Why:* ADR-001 D2 picks Debian 13 for the core image, but robotics is the main moat (M-7). If ROS 2 only ships first-class on Ubuntu, Debian becomes the wrong base for the moat, or ROS has to live only in containers.  
*Method:* Read REP-2000 (ROS 2 target platforms) for Jazzy, Kilted and Lyrical; check packages.ros.org dists; check ros2/ci and the ros-infrastructure buildfarm config; try a colcon build of ros-core plus nav2 on trixie arm64 and amd64, and record time and failures.

**Q43 [P0]** Can ROS 2 run fully containerized on a Debian 13 host (Ubuntu-based ROS images on k3s) without losing anything a robot needs: DDS/Zenoh multicast discovery across pod networks, shared-memory transport (iceoryx, Zenoh SHM, FastDDS SHM) across pods, /dev access for cameras/serial/CAN/GPIO, and real-time scheduling? Which CNI settings (hostNetwork, Multus, macvlan) does each need?  
*Why:* Decides whether the 'apps don't care, they're containers on k3s' claim in D2 holds for robotics, or whether the robot workload needs host-level ROS.  
*Method:* Hardware test on a Beelink/Dell and a Pi 5: k3s with Flannel vs Cilium vs Multus; run talker/listener, nav2 and a camera pipeline across pods; measure latency, jitter, throughput and discovery reliability; read Canonical/Open Robotics/ROS Discourse guidance on ROS in Kubernetes (e.g. FogROS2, ros2-k8s demos).

**Q44 [P0]** Is Kubernetes (k3s) on the robot itself the right runtime, or should the robot run a lighter supervisor (systemd + Podman/Docker Compose, balena-style, or Zenoh-based launcher) with k3s only on the home/edge server? What do real robot fleets (Boston Dynamics Spot CORE, Clearpath/OTTO, Formant, InOrbit, Viam, Foxglove customers) actually run on board?  
*Why:* Challenges D4 (k3s on every tier). k3s control-plane overhead, etcd/SQLite writes and pod restart semantics may conflict with safety-critical on-robot loops and power budgets.  
*Method:* Reverse-engineer published images and docs (Spot CORE I/O, Clearpath ROS 2 Jazzy OS images, Viam RDK agent, balenaOS, Husarion OS, Unitree SDK images); measure k3s idle CPU/RAM/flash writes on Jetson Orin Nano and Pi 5 vs Podman+systemd; check Akri/KubeEdge/k0s/microk8s robotics case studies.

**Q45 [P0]** For the Jetson flavor: which JetPack/L4T versions (JetPack 6.x on Ubuntu 22.04 vs JetPack 7 on Ubuntu 24.04) support which modules (Orin Nano/NX/AGX, Thor), what is NVIDIA's support lifecycle per release, and how long are Orin modules guaranteed to be produced (NVIDIA Jetson product lifecycle page)? Does JetPack 7 cover Orin or only Thor at launch?  
*Why:* The L4T flavor is the only supported path to NVIDIA robotics; a mismatched JetPack/module matrix could strand shipped robots on an EOL Ubuntu.  
*Method:* NVIDIA Jetson Linux release notes, JetPack roadmap, developer.nvidia.com/embedded/lifecycle, Jetson forum announcements; tabulate module x JetPack x Ubuntu x EOL.

**Q46 [P0]** Can a Jetson run a Debian-based or Yocto-based OneMind image instead of NVIDIA's Ubuntu L4T (e.g. meta-tegra Yocto, OE4T, Debian with NVIDIA BSP debs, balenaOS Jetson, Kairos Jetson, Canonical's Ubuntu for Jetson), while keeping CUDA, TensorRT, VPI, Isaac ROS and secure boot? What breaks?  
*Why:* Could collapse the two-flavor cost in D2 or prove it is unavoidable; also decides whether we control our own Jetson update chain.  
*Method:* Read meta-tegra/OE4T docs and supported JetPack versions; read balena and Kairos Jetson docs; build a meta-tegra image for Orin Nano dev kit; run CUDA samples, TensorRT and an Isaac ROS container; diff against stock L4T.

**Q47 [P0]** What A/B update mechanism should the Jetson flavor use: NVIDIA's own A/B rootfs + capsule UEFI update (nvbootctrl, OTA tools), RAUC (meta-tegra supports it), Mender, Rugix, or Kairos? Which handles bootloader/QSPI firmware updates safely, and which can share signing keys and UX with Rugix on the Debian flavor?  
*Why:* Open item in ADR-001 §5 ('Jetson A/B method'); bricking a robot in the field via bootloader update is a fatal failure mode.  
*Method:* NVIDIA Jetson Linux Developer Guide (Software Packages and Update Mechanism, Root File System Redundancy, UEFI capsule update); meta-tegra RAUC/Mender layers; Rugix board support list; forced power-cut tests during update on Orin Nano.

**Q48 [P0]** Does the robot need PREEMPT_RT, and is it available and supported on each flavor: mainline Linux 6.12+ (PREEMPT_RT merged in 6.12) on Debian 13 (linux-image-rt), Raspberry Pi kernel RT builds, and NVIDIA's RT kernel for L4T? What worst-case latencies (cyclictest) do we get with k3s running?  
*Why:* Motor control, ros2_control and some sensor drivers need bounded latency; k3s and container runtimes add jitter. Decides kernel choice and whether to isolate cores.  
*Method:* Debian trixie kernel packages; Raspberry Pi linux repo RT configs; NVIDIA Jetson Linux 'Real-Time Kernel' docs; cyclictest/rtla tests with and without k3s, with isolcpus/cpuset and Kubernetes static CPU manager, on Pi 5, x86 mini PC and Orin.

**Q49 [P0]** Which middleware should be OneMind's robot backbone: rmw_zenoh (Tier-1 in Jazzy/Kilted?), Cyclone DDS, Fast DDS, or Eclipse Zenoh directly, and how does it bridge to the existing NATS fabric (NATS grammar already used in the cluster)? Is there a maintained Zenoh<->NATS or DDS<->NATS bridge, and what are latency/bandwidth costs over Tailscale/WireGuard and lossy radio links?  
*Why:* Two buses (NATS for platform, Zenoh/DDS for robots) need a defined boundary; DDS over WAN/VPN is a known failure point.  
*Method:* REP-2000 rmw tiers; ros2/rmw_zenoh repo and release notes; zenoh-plugin-ros2dds; search for NATS bridges; benchmark pub/sub over Tailscale and a throttled link (tc netem) with Zenoh vs Cyclone vs NATS.

**Q50 [P0]** How do established robot companies ship and update their OS images (Clearpath, Husarion, Unitree, Boston Dynamics, Agility, Figure, Skydio, Anduril, DJI, Auterion/Skynode, ModalAI VOXL, Formant/Viam customers)? Which build tool (Yocto, Debian live-build, mkosi, Buildroot), which updater (Mender, RAUC, SWUpdate, OSTree), and what base distro?  
*Why:* ADR-001 copied appliance competitors (HAOS/Umbrel), not robot competitors; the moat should copy proven robot practice.  
*Method:* Reverse-engineer downloadable images (Husarion OS, Clearpath ISO, ModalAI VOXL SDK, Auterion OS docs, PX4 companion images), firmware teardown write-ups, job postings, open-source repos and conference talks (ROSCon, Embedded OSS Summit).

**Q51 [P0]** Should drones use PX4 or ArduPilot (or both) as the flight-controller firmware, and what is the companion-computer integration pattern (MAVLink 2 + MAVSDK/MAVROS, uXRCE-DDS for PX4 ↔ ROS 2, DroneKit)? Which is better for licensing (BSD-3 vs GPLv3) given we plan to sell hardware?  
*Why:* Licensing and integration path affect the business model and the OneMind drone capability API.  
*Method:* PX4 and ArduPilot docs and license files; PX4 uXRCE-DDS docs; ArduPilot DDS docs; Dronecode governance; test SITL of both with a ROS 2 companion container on k3s.

**Q52 [P0]** Which safety standards apply to each robot class we plan (home service robots ISO 13482, industrial/cobots ISO 10218-1/-2:2025, AMRs ISO 3691-4 and ANSI/A3 R15.08, functional safety IEC 61508 / ISO 13849, UL 3300), and which parts must run on a certified safety MCU/RTOS rather than Linux? What is the minimum safe architecture (e-stop, safety-rated speed monitoring) we must design in from day one?  
*Why:* Linux plus an AI agent cannot be the safety function; the architecture must separate a certified safety channel early or the product cannot be certified later.  
*Method:* Standard abstracts and scopes (ISO, IEC, UL catalogs), A3 publications, safety architectures of certified products (e.g. Universal Robots, MiR, Boston Dynamics Spot safety docs), Zephyr/FreeRTOS SafeRTOS certification status.

**Q53 [P0]** How should the AI capability layer (agents acting via MCP/CLI/API) be allowed to command physical robots and drones safely: what permission, rate-limit, geofence, simulation-first and human-confirmation patterns exist (ROS 2 SROS2/DDS-Security access control, ros2 action guards, MAVLink signing, PX4 geofence/failsafe), and how do existing 'LLM-to-robot' systems (ROS-LLM, ROSA, NVIDIA Isaac agents, Anthropic Project Fetch / MHS work) bound actions?  
*Why:* Core differentiator (every device exposed to agents) collides directly with physical safety; must be designed before the capability gateway is built.  
*Method:* SROS2 docs, DDS-Security spec, MAVLink 2 message signing docs, PX4 failsafe docs; read papers/repos for ROSA (NASA JPL), ROS-LLM, Anthropic publications on robotics/MHS; threat-model with STRIDE.

**Q54 [P0]** What does each NVIDIA physical-AI component require at runtime and license-wise: Isaac Sim / Isaac Lab (GPU class, Omniverse Kit, Ubuntu-only?), Isaac ROS (JetPack/x86 versions, NITROS), GR00T N1.x foundation models (Jetson Thor requirement?), Cosmos world models (GPU memory), Holoscan (sensor processing), and can they run on a Debian 13 x86 + RTX host inside k3s?  
*Why:* N-8 says everything NVIDIA should run natively on OneMind machines; if Isaac Sim needs Ubuntu, the Pro/Omni GPU tier may need Ubuntu too, undermining D2.  
*Method:* NVIDIA Isaac Sim system requirements page, Isaac ROS release notes, GR00T and Cosmos GitHub/HF model cards and licenses (NVIDIA Open Model License), Holoscan SDK docs; hardware test: Isaac Sim container + Isaac ROS container on Debian 13 + RTX via NVIDIA container toolkit on k3s.

**Q55 [P0]** Is NVIDIA GPU Operator, or at minimum the NVIDIA device plugin + container toolkit + DCGM exporter + MIG/time-slicing, reliable on Debian 13 and on Jetson (k3s), and how do Isaac/Holoscan workloads share one GPU with Ollama/LLMs and sim? What does the NVIDIA Jetson k8s device plugin support today?  
*Why:* ADR-001 open item 'GPU Operator on Debian'; GPU sharing between AI and robotics workloads on one box is a core Pro/Omni promise.  
*Method:* GPU Operator platform support matrix, k8s-device-plugin repo, NVIDIA container toolkit docs; spike #5 and #6 in ADR §4 extended to time-slicing tests with concurrent LLM + Isaac ROS.

**Q56 [P0]** How do ZED SDK, RealSense SDK, Ouster/Livox SDKs and other proprietary robotics SDKs declare OS support (often Ubuntu-only), and can they run in Ubuntu containers on a Debian host without kernel module issues?  
*Why:* Proprietary sensor SDKs are a hidden Ubuntu coupling that could challenge D2.  
*Method:* Vendor support matrices; test container images on Debian 13 host with USB passthrough; check DKMS requirements (librealsense uvcvideo patches).

**Q57 [P0]** Is Ubuntu Core (snaps, 10-12 year support, used by many robot OEMs) or Ubuntu 24.04 + Canonical's real-time kernel a better robot base than Debian 13 once you price Ubuntu Pro for Devices per unit? Get an actual quote for Pro for Devices at 100 / 1,000 / 10,000 units.  
*Why:* ADR-001 rejected Ubuntu partly because the device price is unpublished; robotics ecosystem gravity is Ubuntu, so the decision needs a real number.  
*Method:* Contact Canonical sales (with Zeus's approval), read Ubuntu Core and real-time kernel docs, compare with Debian ELTS (Freexian) per-device pricing and the cost of self-maintaining ROS on Debian.

**Q58 [P0]** Do read-only root + A/B images and k3s survive the physical realities of robots and drones: power loss mid-write, vibration, flash wear from logs/etcd, brownouts on battery, and temperature extremes? What filesystem and logging settings (EROFS/squashfs, F2FS/ext4 data, journald volatile, k3s SQLite/etcd write rates) are required for SD/eMMC/NVMe longevity?  
*Why:* Appliance competitors live on a shelf; robots and drones do not. The ADR's disk layout must be validated for mobile hardware.  
*Method:* Power-cut rigs (relay cycling) during update and normal operation on Pi 5 (SD and NVMe), Orin Nano (NVMe); measure write amplification with iostat/smartctl over 72h; read Rugix/RAUC power-fail guarantees.

**Q59 [P0]** What licensing constraints apply to redistributing NVIDIA components (L4T BSP, CUDA, TensorRT, Isaac ROS, GR00T/Cosmos model licenses) inside a OneMind image and on sold hardware, and what NVIDIA partner agreement is required to ship them preinstalled?  
*Why:* Selling NVIDIA-based boxes with a custom OS requires redistribution rights; a license gap blocks the Omni/robot tier.  
*Method:* Read NVIDIA Software License Agreement for Jetson Linux, CUDA EULA redistribution attachments, NVIDIA Open Model License, Isaac ROS Apache/NVIDIA licenses; check how balena, Canonical and Kairos ship Jetson images.

**Q60 [P1]** What is the lifecycle and end-of-life policy of ROS 2 distros versus Debian 13 (LTS to 2030-06-30) and Ubuntu 24.04 (standard to 2029), and how do we align robot software releases so a shipped robot never sits on an unsupported ROS + OS combination? How do commercial vendors (Canonical ROS ESM, Open Robotics/OSRF) extend ROS support, and at what price?  
*Why:* 5-10 year horizon; hardware sold must have a defined support period (EU CRA).  
*Method:* ROS 2 releases page; Canonical ROS ESM pricing/terms; Clearpath/Husarion upgrade policies; build a timeline chart of OS vs ROS vs JetPack EOLs.

**Q61 [P1]** What are the exact FAA rules a OneMind drone product and its software must meet: Part 107 (including operations over people, BVLOS waiver/ the proposed Part 108 BVLOS rule status), Remote ID (Part 89: standard RID vs broadcast module, Declaration of Compliance, FAA-accepted means of compliance ASTM F3411/F3586), and LAANC integration? What is the current status of Part 108 as of late 2026?  
*Why:* Selling drone hardware/software in the US requires Remote ID compliance; BVLOS rules decide what autonomous features are legal.  
*Method:* eCFR 14 CFR Parts 89, 107 and Federal Register for Part 108; FAA Remote ID DOC list; ASTM standards summaries; FAA LAANC USS requirements.

**Q62 [P1]** What do EASA rules require for drones sold or flown in the EU: C0–C6 class marking (Delegated Regulation 2019/945), Open/Specific categories, SORA 2.5, Direct Remote ID, geo-awareness, and U-space? Who can CE-mark a class-labelled drone and what does it cost?  
*Why:* EU sovereignty market is a stated target; drone hardware must be class-marked.  
*Method:* EUR-Lex 2019/945 and 2019/947 and amendments; EASA SORA 2.5 and easy-access rules; notified body fee schedules; interview/read docs from EU drone makers (Parrot, Quantum Systems).

**Q63 [P1]** What does the EU Machinery Regulation 2023/1230 (applies from 2027-01-20) require for autonomous mobile robots and machines with AI/self-evolving behaviour: which annex triggers third-party conformity assessment, cybersecurity essential requirements, software update obligations, and how does it interact with the EU AI Act (high-risk safety components) and the Cyber Resilience Act?  
*Why:* Any robot sold in the EU after Jan 2027 must comply; OS update and AI-agent control features may become 'safety components'.  
*Method:* EUR-Lex 2023/1230 Annex I/II, EU AI Act Annex I/III, CRA; Commission guidance; harmonised standards list; legal analyses from notified bodies (TÜV, DEKRA).

**Q64 [P1]** What exactly is 'Anthropic MHS' and any Anthropic robotics work (e.g. Project Fetch), and what interfaces, licenses or partner programs could OneMind integrate with? Separately, what is the current state of Claude/other LLM computer-use and tool-use for robot control?  
*Why:* Named in the domain brief; must be verified from primary sources rather than assumed (research-don't-assume rule).  
*Method:* anthropic.com research/news pages, Anthropic docs, papers; label anything unconfirmed; compare with Google Gemini Robotics and NVIDIA GR00T announcements.

**Q65 [P1]** Which non-NVIDIA edge inference accelerators should OneMind support for Lite/Edge tiers and drones (Hailo-8/8L/10H incl. Raspberry Pi AI Kit/HAT+, Google Coral Edge TPU status, Rockchip RK3588 NPU via RKNN, Qualcomm QCS6490/Dragonwing/RB5 with QNN, Intel NPU/OpenVINO, AMD Ryzen AI/XDNA, Axelera, DeepX, MemryX), and what is each one's Linux driver status on Debian 13, mainline-kernel status, container support, model toolchain, and vendor longevity?  
*Why:* Avoid NVIDIA lock-in for cheaper SKUs and sovereignty buyers; driver availability on Debian decides if the base works for those boards.  
*Method:* Vendor docs and GitHub (hailort, rknn-toolkit2, rocket/accel subsystem in mainline, Qualcomm Linux), Debian package search, benchmark YOLO/whisper on each via a common harness (ONNX Runtime EPs), check Coral repo activity.

**Q66 [P1]** Should OneMind standardize on a portable inference layer (ONNX Runtime with EPs, TensorRT, OpenVINO, Apache TVM, ExecuTorch, llama.cpp/GGUF, LiteRT) so the same perception/VLA model can be deployed to Jetson, Hailo, RK3588 and x86 GPU? What accuracy/latency loss does each conversion path introduce?  
*Why:* Hardware auto-detection (N-3) and multi-vendor robots need one model packaging format and capability descriptor.  
*Method:* Convert a reference model set (YOLOv8/11, Depth Anything, SmolVLA/π0, Whisper) through each path; measure on hardware; read ONNX Runtime EP support matrix and ExecuTorch backend list.

**Q67 [P1]** How does Hugging Face LeRobot (datasets format, SmolVLA, policies, SO-100/101 and other supported arms, async inference) fit OneMind: can a LeRobot training/inference pipeline run on k3s with GPU, record teleop data to the OneMind data plane, and deploy policies to Jetson/Pi robots? What hardware does it officially support and what licenses apply?  
*Why:* Cheapest credible path to a physical-AI demo and community; tests the 'robotics app' end to end.  
*Method:* huggingface/lerobot repo, docs, dataset format spec v2/v3; build an SO-101 arm, record data via teleop, train SmolVLA on a GPU node in k3s, deploy to Pi 5/Orin; log what breaks.

**Q68 [P1]** What is the right open-source fleet management and multi-robot orchestration layer: Open-RMF (status, maintainer activity, ROS 2 distro support, traffic/door/lift adapters), vs commercial/open alternatives (Formant, InOrbit, Viam, Freedom Robotics, FogROS2, Foxglove for observability), and how much of it overlaps with Kubernetes + NATS we already run?  
*Why:* Fleet control is a likely OneMind app and differentiator; must avoid building what Open-RMF already solves or adopting a dying project.  
*Method:* open-rmf GitHub activity and releases, OSRA governance, Foxglove/MCAP license, Viam RDK license and architecture, demo Open-RMF in Gazebo on k3s.

**Q69 [P1]** How should robots and drones be onboarded and identified as OneMind nodes (QR onboarding N-4): device identity (TPM/secure element, X.509, SPIFFE/SPIRE), zero-touch provisioning patterns used by robot vendors, FIDO Device Onboard (FDO), and how robot identity maps to SROS2 keystores, MAVLink signing keys and k3s node join tokens?  
*Why:* One identity model across k3s, ROS 2 security, MAVLink and the capability gateway is needed before hardware ships.  
*Method:* FDO spec (FIDO Alliance) and LF Edge implementation, SPIRE docs, SROS2 keystore docs, how Viam/Formant/balena provision devices; prototype QR → enrollment → SROS2 cert issuance.

**Q70 [P1]** What teleoperation stack should OneMind offer for robots and drones over home internet, Starlink, LTE and mesh radios (WebRTC-based: Foxglove, Transitive Robotics, GStreamer webrtcbin, LiveKit; video encoders on Jetson NVENC and Pi 5 lacking hardware H.264 encode), and what latency/bandwidth is achievable? How does it integrate with TAK (CoT/KLV video, ATAK video streams)?  
*Why:* Teleop is needed for data collection, safety takeover and public-safety use; Pi 5 lacks a hardware video encoder which affects SKU choice.  
*Method:* Benchmarks of WebRTC stacks on Pi 5 vs Orin NVENC; Transitive Robotics and Foxglove licenses; TAK video and CoT docs, existing ROS-TAK bridges (e.g. ros2_tak/FreeTAK integrations); netem tests at 100–800 ms RTT.

**Q71 [P1]** How should OneMind integrate drones and robots into TAK situational awareness: MAVLink→CoT bridges, UAS Tool (ATAK plugin) status and licensing, KLV/MISB metadata for video, and CloudTAK/TAK Server data flow through NATS?  
*Why:* TAK/public safety is a core vertical and the user already runs CloudTAK; drone feeds into TAK are a concrete early product.  
*Method:* tak.gov plugin catalog, open-source bridges on GitHub (mavlink2cot, ros2tak), MISB ST 0601 docs, prototype PX4 SITL → CoT → CloudTAK.

**Q72 [P1]** Which simulator(s) should OneMind standardize for sim-to-real and for 'Sims for robotics and AI agents' (Gazebo Harmonic/Ionic/Jetty, Isaac Sim/Lab, MuJoCo/MJX/MuJoCo Playground, Genesis, Webots, CARLA, AirSim successors e.g. Project AirSim/Colosseum, PX4/ArduPilot SITL), considering license, GPU need, ROS 2 support, headless k3s operation, and streaming to the browser/XR?  
*Why:* Simulation is required on capable tiers (N-3, N-7) and drives GPU sizing of Pro/Omni hardware.  
*Method:* Project licenses and release cadences; run each headless in k3s with GPU; measure RTF on an RTX box and DGX Spark-class device; check pixel-streaming/WebRTC options (Omniverse Kit streaming, Gazebo web).

**Q73 [P1]** What is the sim-to-real pipeline cost and evidence: which published results (Isaac Lab locomotion, LeRobot, MuJoCo Playground, GR00T) transferred to real hardware on Jetson-class compute, what domain randomization and system ID were needed, and what compute (GPU-hours) does a small team need for training vs on-robot inference?  
*Why:* Determines whether the 'physical AI moat' needs a training cluster, cloud GPU credits, or only edge inference; shapes hardware tiers and 5-10 year plan.  
*Method:* Read papers and repos with real-robot results (Isaac Lab, legged_gym, Unitree RL, LeRobot reports); reproduce one sim-to-real policy on a cheap robot; record compute used.

**Q74 [P1]** What microcontroller layer should OneMind robots and drones use: micro-ROS (supported RTOSes/MCUs, Jazzy status), Zephyr vs FreeRTOS vs NuttX (PX4), and how are MCU firmwares updated and signed from the OneMind OS (MCUboot, DFU over CAN/USB, PX4 bootloader)?  
*Why:* Real robots split Linux high-level and MCU low-level control; firmware update is a separate update layer already listed in D3.  
*Method:* micro-ROS docs/repos activity, Zephyr LTS and safety certification status, MCUboot docs, PX4 bootloader docs; prototype micro-ROS on an RP2040/ESP32/STM32 connected to a Pi 5 k3s node.

**Q75 [P1]** Which buses and peripherals must the base image support out of the box for robotics (SocketCAN/CAN-FD, EtherCAT via IgH/SOEM, Dynamixel, RS-485/Modbus, GPIO/I2C/SPI via libgpiod, USB3 depth cameras RealSense/ZED/OAK-D, GMSL cameras on Jetson, LiDAR drivers, GNSS RTK), and do their drivers/udev rules work on Debian 13, the Pi kernel and L4T with a read-only root?  
*Why:* Hardware auto-detection and QR onboarding promise must hold with read-only root + A/B; missing kernel modules force custom kernels.  
*Method:* Kernel config diffs (Debian trixie, raspberrypi/linux, L4T); vendor SDK docs (librealsense, ZED SDK Ubuntu-only?, DepthAI); hardware plug tests on each flavor with read-only root.

**Q76 [P1]** What is the security posture required for networked robots and drones (ROS 2 SROS2 maturity, known DDS CVEs, Zenoh security/access control, MAVLink signing adoption, Alias Robotics robot vulnerability database), and what does the EU CRA require of robot software (SBOM, vulnerability handling, support period)?  
*Why:* Robots are exposed to agents and the internet; sovereign/public-safety buyers will demand evidence.  
*Method:* CVE databases for DDS/Zenoh/PX4/ArduPilot, Alias Robotics RVD, SROS2 docs, CRA text; run a pentest of a ROS 2 + Zenoh deployment over Tailscale.

**Q77 [P1]** Which US/EU export controls and procurement rules affect OneMind robotics/drone products and components (EAR/ITAR on drones, NDAA Section 848/Blue UAS list, American Security Drone Act 2023, DJI restrictions, EU dual-use regulation, Chinese-origin components like Unitree/Rockchip/Hailo origin)?  
*Why:* Public-safety and government buyers require Blue UAS/NDAA-compliant hardware; component choices (RK3588, Unitree) may exclude those markets.  
*Method:* DIU Blue UAS cleared list and framework, NDAA FY20/FY24 text, BIS EAR CCL categories 9A012/ECCN for drone parts, EU 2021/821; map each candidate SoC/robot to origin and restrictions.

**Q78 [P1]** What hardware should OneMind's robotics SKUs be built on over 1–5 years (Jetson Orin Nano Super/Orin NX/AGX/Thor, DGX Spark, Qualcomm robotics RB3/RB5 and IQ series, RK3588 boards, Pi 5 + Hailo, x86 with RTX), with price, power, availability, long-term supply commitments, carrier-board ecosystems (Seeed, Connect Tech, Auvidea) and NVIDIA partner program requirements (Jetson Partner/Inception)?  
*Why:* Hardware sales are in the business model; SKU selection must match OS flavors and support periods.  
*Method:* Vendor datasheets and lifecycle pages, distributor pricing, NVIDIA partner program terms; power and thermal tests of shortlisted boards running the OneMind stack.

**Q79 [P1]** How should robot data (rosbag2/MCAP, video, telemetry, LeRobot datasets) flow into the existing OneMind data plane (NATS JetStream, ClickHouse time machine) with offline-first sync over intermittent links, and which formats preserve time sync (PTP/chrony, gPTP on Jetson)?  
*Why:* The cluster already has a data plane; robot data must fit it for training and AI context without new silos.  
*Method:* MCAP spec, rosbag2 storage plugins, NATS JetStream mirror/leaf docs, ClickHouse ingestion benchmarks; prototype rosbag2 → MCAP → NATS → ClickHouse with a network-partition test.

**Q80 [P1]** Can the existing DOKS cluster + Backstage setup serve as the proof-of-concept for robot fleet ops (Backstage catalog entities for robots/drones, Argo CD GitOps to edge k3s robots via fleet tools like Rancher Fleet, Argo CD ApplicationSets, Flux, or KubeEdge/OpenYurt), and what breaks when robot nodes are offline for days?  
*Why:* The user wants the cluster and Backstage shown as proven infrastructure; GitOps to intermittently connected robots is a known hard case.  
*Method:* Inspect current cluster via onemind-kubernetes/Backstage MCP (read-only); read Rancher Fleet, KubeEdge, OpenYurt, Argo CD pull-mode docs; test a k3s robot node disconnected for 72h then reconnecting.

**Q81 [P1]** How do humanoid and quadruped vendors expose their robots to third-party software (Unitree SDK2 and ROS 2 support, Boston Dynamics Spot SDK, Agility, Booster, Fourier, 1X), and can OneMind wrap them as capability nodes without modifying their onboard OS?  
*Why:* OneMind likely integrates third-party robots before shipping its own; adapter strategy matters more than base OS for those.  
*Method:* Vendor SDK docs and licenses on GitHub; test Unitree Go2/G1 or Spot SDK in a k3s pod via network API; document security of each SDK.

**Q82 [P2]** What digital-twin format and runtime should OneMind adopt: OpenUSD (AOUSD core spec status, Omniverse), glTF 2.0, URDF/SDF/MJCF/USD conversions, and which tools keep a live twin of a home/homestead/warehouse in sync with sensors (Isaac Sim, Omniverse Nucleus alternatives, Gazebo, Three.js/Cesium for TAK maps)?  
*Why:* Digital twins tie robotics, homestead/IoT and XR together; picking the wrong interchange format is costly long term.  
*Method:* AOUSD spec releases, Khronos glTF roadmap, urdf-usd-converter and Isaac importers; prototype a homestead twin in USD and glTF and stream to browser/XR.

**Q83 [P2]** What are the 5–10 year trajectories that could invalidate today's choice: ROS 2 vs emerging stacks (dora-rs, Copper-rs, Zenoh-native, Rust robotics), VLA/foundation models moving on-device (GR00T, π0, Gemini Robotics On-Device), RISC-V robotics SoCs, Jetson successors, humanoid platforms (Unitree, Figure, 1X, Apptronik) opening SDKs, and NVIDIA possibly shifting Jetson to a different base OS?  
*Why:* Horizon is 5–10 years; the foundation must have exit ramps for each trend.  
*Method:* Repo activity metrics (dora-rs, copper-rs, ROS 2 contributors), roadmap statements from NVIDIA GTC/Computex, Google DeepMind, Physical Intelligence, RISC-V International; build a scenario matrix with trigger signals.

## AI-native OS and agents: MCP, A2A, MHS, Agent Skills, local inference, model routing, GPU sharing, agent sandboxing, permissions/approval/audit, personal-data memory/RAG, on-device models, voice, competitor agent surfaces, prompt-injection risk for a device-controlling OS

**Q84 [P0]** Under MCP spec 2026-07-28 (stateless, no initialize, server/discover, MRTR, tasks extension, CIMD), what exactly must a OneMind 'OS MCP gateway' implement to be conformant, and which of the current official SDKs (Python, TypeScript, Go, Rust) implement 2026-07-28 fully today, with which gaps?  
*Why:* The capability layer (AI-1..AI-4) is the core product promise; if the SDK in our stack (onemind-core Python, onemind-mcp) lags the spec, we build on a moving target. Determines gateway language and whether onemind-mcp is rewritten.  
*Method:* Read modelcontextprotocol.io spec 2026-07-28 changelog + SEPs 2567/2575/2322/2663; clone each official SDK, grep for server/discover, InputRequiredResult, _meta protocol version; run the official conformance suite (if published) against a test server per SDK; record pass/fail matrix.

**Q85 [P0]** Does Authentik (current release) support everything MCP authorization requires: RFC 9728 Protected Resource Metadata consumption, RFC 8414/OIDC discovery, Client ID Metadata Documents, RFC 8707 resource indicators with audience-restricted tokens, RFC 9207 iss, PKCE, client-credentials, and token exchange (RFC 8693) for agent-on-behalf-of-user? If not, what fills the gap (Keycloak, Zitadel, Ory Hydra, Kanidm, a OneMind token broker)?  
*Why:* Authentik is the existing IdP and the planned AS for every app/agent; a missing feature forces an IdP change before the foundation is fixed, and the IdP must also run on a Pi 5 Lite box.  
*Method:* Read Authentik source (goauthentik/authentik providers/oauth2) and release notes; stand up Authentik on k3s, run MCP Inspector and Claude/VS Code clients against a protected MCP server, capture token claims; repeat with Keycloak/Zitadel/Kanidm; measure RAM footprint of each on Pi 5.

**Q86 [P0]** What is the minimal app-manifest schema that lets 'install an app → it is automatically registered for AI with permissions' (AI-3), and how do Umbrel 2.0, Olares (OlaresManifest + Agent Skills), Home Assistant (exposed entities / LLM APIs), Backstage Actions Registry and CasaOS each encode capabilities, scopes and destructive hints? Can one manifest generate MCP tools, CLI subcommands, OpenAPI, Agent Skills (SKILL.md) and an MCP-Registry-compatible server.json?  
*Why:* The app manifest is the single most load-bearing contract in the OS; getting it wrong forces re-packaging hundreds of apps later.  
*Method:* Reverse-engineer umbrelOS 2.0 source (getumbrel/umbrel, mcp module) and its app-store manifests; Olares OlaresManifest.yaml spec and CLI skill sources; HA mcp_server integration code; Backstage mcp-actions backend; produce a field-by-field comparison and a draft OneMind manifest with a code generator prototype.

**Q87 [P0]** How exactly does umbrelOS 2.0 implement its MCP server (tool list, the reported 7 default/38 granted tools, token storage, permission categories enforcement point, audit/last-request tracking, transport over plain HTTP on LAN), and where are its weaknesses (agents act as owner, no per-user scoping, no approval step, plaintext LAN)?  
*Why:* Umbrel is the direct competitor reference the founder named for AI-4; OneMind must 'match and exceed' it, which requires knowing precisely what it does and does not do.  
*Method:* Clone getumbrel/umbrel at tag 2.0.0+, read the MCP server code paths; install umbrelOS 2.0 on x86 VM, connect an MCP client, enumerate tools, attempt out-of-scope calls, sniff LAN traffic; note license limits (PolyForm Noncommercial) so learning stays clean-room.

**Q88 [P0]** Where should the enforcement point for agent permissions live: in a single OneMind capability gateway, in Kubernetes RBAC on per-agent ServiceAccounts, in an OPA/Cedar/OpenFGA policy engine, in each app, or layered? What do Kubernetes-MCP-server ('read_only is best-effort, RBAC is the real control'), Google/Microsoft agent-identity work, and SPIFFE/SPIRE workload identity recommend?  
*Why:* Determines whether k3s RBAC/ServiceAccounts are part of the AI security model (strengthening the case for k3s over Docker-only on Lite tiers, N-9) and how human-in-the-loop (AI-5) is enforced.  
*Method:* Read containers/kubernetes-mcp-server, MCP roadmap agent-identity SEPs (DPoP, ID-JAG, RFC 8693), Cedar and OpenFGA docs; build a prototype gateway on k3s with per-agent SA + OpenFGA relationships; red-team for confused-deputy and token passthrough.

**Q89 [P0]** What is the threat model and measured prompt-injection success rate when an LLM agent with OS-level tools (files, app restart, device control, robot/drone actuation) reads attacker-controlled content (email, web pages, RSS, OSINT feeds, TAK CoT, camera OCR)? Which mitigations actually work in published evals: CaMeL-style dual-LLM/capability tracking, FIDES/information-flow control, spotlighting, tool-call allowlists, approval gates on tainted flows?  
*Why:* An OS that controls physical devices for families and public safety cannot ship with injectable agents; the mitigation architecture must be designed into the gateway from day one, not added later.  
*Method:* Read primary papers (Google DeepMind CaMeL, Microsoft FIDES, AgentDojo, InjecAgent, ASB benchmarks), OWASP LLM/Agentic Top 10; run AgentDojo-style tests against a prototype gateway with local models (Qwen/Llama/Gemma) and frontier APIs; record attack success with and without each mitigation.

**Q90 [P0]** Should agents and agent-run code execute in gVisor, Kata Containers, Firecracker microVMs, or the Kubernetes SIG agent-sandbox (kubernetes-sigs/agent-sandbox) CRD, and which of these actually work on Debian 13 arm64 (Pi 5, no nested virt/KVM limits), x86 mini PCs, and Jetson L4T kernels with GPU passthrough?  
*Why:* Sandbox choice constrains kernel config of every image flavor (KVM, cgroup, seccomp) and must be decided before the Debian/L4T kernels are frozen; Jetson L4T kernel may lack required features.  
*Method:* Read agent-sandbox repo/KEP, gVisor platform docs (systrap vs KVM), Kata/Firecracker arm64 support matrices; hardware test on Pi 5 (Debian 13 + RPi kernel), Beelink U55, Dell 5540, and a Jetson Orin: runtimeClass install, cold-start latency, memory overhead, GPU access, nvidia-container-runtime interplay.

**Q91 [P0]** Which local inference runtime(s) should be the OS default per tier: Ollama, llama.cpp server, vLLM, SGLang, TensorRT-LLM/NIM, MLC-LLM, ExecuTorch, or NVIDIA Dynamo? Benchmark tokens/s, time-to-first-token, RAM, concurrency, and OpenAI-API compatibility on Pi 5 (CPU/Hailo), Intel/AMD iGPU mini PC, RTX 50-series, Jetson Orin/Thor, and DGX Spark.  
*Why:* AI-8 (auto GPU detection + local LLMs) and the hardware-tier definitions (Lite/Pro/Omni, N-3) depend on what models actually run usefully on each box; also tests whether Debian 13 + NVIDIA repo driver is sufficient for vLLM/SGLang without GPU Operator.  
*Method:* Hardware benchmark harness (llama-bench, vLLM benchmark_serving, genai-perf) with fixed model set (Qwen3 4B/8B/32B, Llama, Gemma, gpt-oss) at Q4/Q8/FP8; publish a capability matrix; read license terms of NIM (NVIDIA AI Enterprise) vs open runtimes.

**Q92 [P0]** Does running inference engines with GPU on Debian 13 + NVIDIA debian13 driver repo + Container Toolkit + k8s device plugin (no GPU Operator) support time-slicing, MPS, MIG (where applicable) and the new Kubernetes DRA NVIDIA driver, and how does that compare to Ubuntu 24.04 with GPU Operator? Is the lack of GPU Operator support on Debian a real blocker for AI workloads?  
*Why:* Directly challenges ADR-001 D2 (Debian core): if multi-model GPU sharing only works well on Ubuntu, the 'Pro' GPU tier may need Ubuntu or a third flavor.  
*Method:* Read NVIDIA k8s-device-plugin, k8s-dra-driver-gpu, GPU Operator platform support pages; spike on a cloud RTX/L4 VM with Debian 13 and Ubuntu 24.04: install, run two inference pods sharing one GPU via time-slicing/MPS/DRA, measure isolation and throughput.

**Q93 [P0]** What does Anthropic's Model Hardware Standard (MHS) specify once published (device description schema, safety interlocks, actuation semantics, telemetry, transport, auth), how does it relate to MCP and to ROS 2, and what must OneMind's node/device model look like now to be MHS-compatible later?  
*Why:* N-10 and the robotics moat (M-7) depend on MHS; designing the device registry before the spec is public risks incompatibility, so we need the best-available signal and an adapter strategy.  
*Method:* Read modelhardwarestandard.com, Anthropic announcement 2026-08-27 and any published drafts/repos; join waitlist (D-006); compare with ROS 2 (rosbridge, ros2 MCP servers), OPC UA, Matter, MAVLink; draft an abstraction that maps all of them to one OneMind device capability schema.

**Q94 [P0]** How should AI control of physical actuators (robots, drones via MAVLink/PX4/ArduPilot, ROS 2 nodes, greenhouse relays, Matter devices) be gated: which actions require human approval, geofencing, rate/force limits, two-person rules, and hardware e-stop independent of the AI path? What do ROS 2 safety, PX4 failsafes, IEC 61508/ISO 10218/ISO 13482 and FAA Part 107/108 require?  
*Why:* Physical AI is the moat but also the biggest liability; the permission model must express physical-risk tiers, not just data scopes, and regulators may dictate this.  
*Method:* Read standards summaries, PX4/ArduPilot failsafe docs, ROS 2 security (SROS2) and safety working group outputs, FAA Part 108 BVLOS rule text; design risk tiers; test with a simulated drone (PX4 SITL + Gazebo/Isaac Sim) driven by an agent through the gateway with injection attempts.

**Q95 [P0]** For memory and RAG over personal data (files, mail, photos, chats, health, finance, TAK history), which local stack is best per tier: embedding models (size/quality on CPU and Jetson), vector stores (pgvector, Qdrant, LanceDB, sqlite-vec, Milvus), and graph/temporal memory (Graphiti, Letta, mem0, Cognee)? How is per-user and per-app access control enforced inside retrieval so the AI cannot leak one family member's data to another?  
*Why:* AI-1 'everything is context' collides with U-1 multi-user privacy; permission-aware retrieval is unsolved in most stacks and determines storage architecture.  
*Method:* Read each project's license, ACL features and arm64 support; benchmark indexing/query latency and RAM on Pi 5 and mini PC with a 100k-document synthetic family corpus; red-team cross-user leakage via crafted queries.

**Q96 [P0]** How does Olares implement its AI layer end to end (Agent Skills compiled into CLI, model router skill, LarePass, Wise/RAG, per-app permissions via its SysEvent/tapr system), and which parts are actually AGPL-3.0 vs non-commercial, so OneMind knows what it may study, reuse or must avoid?  
*Why:* Olares is the only k3s-based competitor and its topology is a stated template (P-3); licensing conflict (AGPL + non-commercial LICENSE.md) affects clean-room design.  
*Method:* Clone beclab/Olares and related repos; trace the agent-skill, model router and permission code; read every LICENSE file per directory; install Olares on a test box and capture API calls made by its agents.

**Q97 [P0]** What does the KubeCon NA 2026 NVIDIA/CNCF 'agent substrate' work (KAI Scheduler, Dynamo, AI Cluster Runtime, DRA driver, agent-sandbox, kagent, Kubernetes AI conformance program) define as the standard Kubernetes AI platform, and does k3s pass the CNCF Kubernetes AI Conformance requirements?  
*Why:* Supports or challenges ADR-001 D4 (k3s everywhere); if AI conformance requires features k3s or Debian lacks, the platform choice must change.  
*Method:* Read CNCF Kubernetes AI Conformance program docs and test suites, KubeCon NA 2026 talk recordings/slides; run conformance tests on k3s and RKE2 clusters with a GPU node.

**Q98 [P0]** Can a coherent AI-native experience run on the Lite tier (Pi 5 8/16 GB, no NPU, or with Hailo-8/10H, or Pi AI HAT+ 2) with k3s + gateway + IdP + NATS + small model, or does Lite require offloading inference to a Pro box or external API? What is the RAM budget breakdown?  
*Why:* Challenges the 'k3s on every tier' and 'no tier left behind' (D-002) decisions with actual resource numbers for the AI layer, not just the platform.  
*Method:* Hardware test on Pi 5 16 GB with Debian 13 + k3s + Authentik + NATS + gateway + llama.cpp 1–4B model and Hailo accelerator; measure idle/peak RAM, thermals, SD vs NVMe; compare with a Docker-only variant.

**Q99 [P0]** How should the OS model identity for agents distinct from users (agent principals, delegation chains, per-agent tokens like Umbrel, OAuth token exchange, SPIFFE IDs) so that 'kid's tutor agent' and 'dad's infra agent' have different scopes, and how does this map onto Authentik users/groups and Kubernetes namespaces per user?  
*Why:* U-1 multi-user plus AI-5 approvals require that agents have their own identities and constrained delegation; Umbrel's 'agents act as the owner' is the gap to exceed.  
*Method:* Read MCP roadmap identity SEPs, IETF OAuth agent drafts (e.g., draft on AI agent auth, transaction tokens), SPIFFE docs; prototype per-user namespace + per-agent identity with Authentik and OpenFGA; test parental-control scenarios.

**Q100 [P0]** For the Jetson/robotics tier, how do NVIDIA Isaac ROS, Isaac Sim/Lab, GR00T, Cosmos and Holoscan integrate with an agent layer, which require JetPack-specific (L4T Ubuntu 24.04) containers, and can they be orchestrated by k3s with the NVIDIA device plugin on Jetson without breaking real-time ROS 2 performance?  
*Why:* Validates the L4T flavor in ADR-001 D2 and the k3s-on-robots assumption; real-time robot control under Kubernetes is unproven and could force a different runtime on robots.  
*Method:* Read NVIDIA Isaac ROS/Jetson container docs and JetPack 7 release notes; hardware test on Jetson Orin/Thor: k3s + Isaac ROS perception pipeline + agent issuing goals; measure latency jitter with and without k3s, PREEMPT_RT kernel availability.

**Q101 [P0]** Is the Debian 13 + Rugix A/B read-only root compatible with the AI layer's needs for large mutable model stores (tens to hundreds of GB), fast model swaps, kernel modules for GPUs/NPUs (DKMS on read-only root), and sandbox runtimes, or does an image-based approach like Fedora CoreOS/bootc, NixOS, Talos + system extensions, or Ubuntu Core handle accelerator drivers better?  
*Why:* Directly challenges ADR-001 D1–D3: NVIDIA and NPU kernel modules on a signed read-only image are a known pain point and could favor bootc/sysext-based designs.  
*Method:* Read Rugix docs on kernel module handling, Talos system extensions (nvidia), Fedora bootc NVIDIA guidance, NixOS CUDA; build images with NVIDIA driver baked in for Debian+Rugix and bootc; test A/B update with driver version change and rollback.

**Q102 [P0]** What does an AI agent need to safely self-manage the OS (AI-4): which operations (updates, rollback, backup restore, network changes, user management) should be agent-callable at all, how does the 'healthy before commit' A/B logic expose state to agents, and how do we prevent an agent from bricking or locking out a box (break-glass, recovery console, immutable admin path)?  
*Why:* Umbrel explicitly excludes shutdown, factory reset, backups, users and network from MCP; OneMind wants to exceed that, which needs a principled safety envelope tied to the update system.  
*Method:* Review Umbrel's exclusions and HAOS supervisor API; design operation risk tiers; fault-injection test an agent performing update + rollback + restore on Rugix test boxes with injected malicious instructions.

**Q103 [P1]** How should GPU and accelerator scheduling across heterogeneous nodes (Pi + Hailo, iGPU, RTX, Jetson, remote cloud GPU) be done: KAI Scheduler, Kueue, Volcano, HAMi, DRA with structured parameters, or a OneMind-level model router that places requests rather than pods?  
*Why:* Multi-machine clusters (UX-6, P-6 'every machine has a superpower') need a single answer to 'where does this model/agent run'; the choice affects whether k3s on small nodes is needed.  
*Method:* Read NVIDIA KAI Scheduler, Kueue, HAMi, DRA KEP docs and KubeCon NA 2026 'Agent Substrate Day' talks; prototype on a 3-node k3s cluster (Beelink, Dell, cloud GPU) with two schedulers; measure placement correctness and overhead on Pi-class nodes.

**Q104 [P1]** What model-routing layer should the OS ship (LiteLLM, RouteLLM, OpenRouter-style local proxy, Envoy AI Gateway, kgateway/agentgateway, a OneMind router) to switch between local models, user-supplied external APIs and fallbacks, with per-user budgets, data-classification rules (never send family/health data off-box) and audit?  
*Why:* AI-8 requires local plus external models; sovereignty requires enforceable 'stays local' rules; the router is also where privacy policy and cost control are enforced.  
*Method:* Compare licenses, arm64 support, footprint and policy hooks of LiteLLM, Envoy AI Gateway, agentgateway (Linux Foundation); prototype routing by data label; measure added latency on Pi 5 and mini PC.

**Q105 [P1]** What is the state of Google's A2A protocol (governance under Linux Foundation, current spec version, adoption, auth model, agent cards) versus MCP-native agent-to-agent patterns, and should OneMind's existing NATS agent discovery and Hermes agents speak A2A, MCP, or stay NATS-native with adapters?  
*Why:* AI-9 says Hermes/NATS discovery carries forward; picking the wrong inter-agent protocol strands the existing agent roster or isolates OneMind from the ecosystem.  
*Method:* Read a2aproject spec and LF announcements, AAIF project list, AGNTCY/ACP status; map NATS subject doctrine to A2A agent cards and MCP tasks; prototype an A2A<->NATS bridge and measure message overhead and offline behavior.

**Q106 [P1]** What is the right human-in-the-loop UX and protocol for approvals: MCP elicitation/MRTR URL mode, push notifications to the phone app (APNs opaque payload per D-005), TAK/ATAK alerts, voice confirmation, approval with biometric (passkey/WebAuthn) signature, and how should approvals be recorded in a tamper-evident audit log?  
*Why:* AI-5 and U-3 (parental controls) require approvals that work offline, on phones and in the field; the protocol choice affects mobile app and audit storage design.  
*Method:* Read MCP elicitation spec, Apple/Google push docs, WebAuthn/passkeys spec; review how Home Assistant, Umbrel and Claude/ChatGPT agent modes implement confirmations; prototype approval round trip and measure latency over Tailscale and LAN-only.

**Q107 [P1]** Which audit-log design gives tamper-evident, queryable records of every agent action on a single box and across a cluster: k8s audit logs + OpenTelemetry GenAI semantic conventions + an append-only signed log (Sigstore Rekor-style transparency log, immudb, hash-chained JetStream stream)? What is the storage cost on a Pi 5 SD/NVMe over a year?  
*Why:* Enterprise/public-safety tiers and the EU CRA/AI Act need evidence of what agents did; families need explainability ('why did the AI unlock the door').  
*Method:* Read OTel GenAI semconv, MCP _meta trace context, k8s audit policy docs, Rekor/immudb docs; prototype hash-chained audit stream on NATS JetStream; measure write amplification and size per 10k tool calls.

**Q108 [P1]** What 'personal data' connectors and protocols should the OS standardize on for ingestion (Solid pods, ActivityPub, CalDAV/CardDAV, IMAP/JMAP, Google Takeout, Apple export formats, Health Connect/HealthKit export), and what do third-party API terms (Strava's 2026 AI ban, Google, Apple, Garmin, Oura) allow regarding AI use of their data?  
*Why:* UX-3 (cloud app integrations as AI context) was already broken by Strava's policy; each major integration must be legally checked before it is built or advertised.  
*Method:* Read the current API terms of Strava, Google, Apple HealthKit, Garmin, Oura, Withings, Plaid-class finance APIs; tabulate allowed AI uses; review Solid and JMAP specs; check what Umbrel/Olares/HA ship.

**Q109 [P1]** How do Apple Intelligence (App Intents, Private Cloud Compute attestation), Android AICore/Gemini Nano and Android's app-functions API, Windows MCP/agent workspace, and ChromeOS expose the OS to on-device agents, and which design ideas (intents registry, attested off-device compute, per-app agent sandboxes) should OneMind copy?  
*Why:* M-5 positions OneMind as an alternative to Apple/Google; their OS-agent contracts are the incumbent benchmark for safety and developer ergonomics.  
*Method:* Read Apple developer docs (App Intents, PCC security guide), Android AppFunctions/AICore docs, Microsoft Windows MCP registry/agent workspace docs; compare permission prompts and isolation guarantees in a table.

**Q110 [P1]** How does Home Assistant's Assist pipeline (Wyoming protocol, openWakeWord/microWakeWord, Whisper/faster-whisper/Speech-to-Phrase, Piper TTS, LLM conversation agents, HA Voice PE hardware) perform on Pi 5, mini PC and Jetson, and should OneMind adopt Wyoming as its voice protocol or build on an alternative (LiveKit Agents, Pipecat, NVIDIA Riva)?  
*Why:* Voice is a primary interface for homestead/field/family users and the existing OneMind voice pipeline must carry forward; reusing HA's ecosystem avoids rebuilding satellites.  
*Method:* Read Wyoming protocol spec and HA voice docs; benchmark end-to-end latency and accuracy (WER) per tier with faster-whisper sizes and Piper voices; check licenses of Riva vs open stack; test offline operation.

**Q111 [P1]** Which small on-device models (1–8B, VLMs, speech, embedding) are licensed for commercial redistribution preinstalled on hardware OneMind sells (Llama community license, Gemma terms, Qwen Apache-2.0, Mistral, Phi MIT, NVIDIA Open Model License, gpt-oss Apache-2.0), and what are the EU AI Act general-purpose-model obligations for a distributor/deployer?  
*Why:* H-1 hardware sales with bundled models create redistribution and compliance obligations; the wrong default model could block EU sales.  
*Method:* Read each model license text and acceptable-use policies; read EU AI Act Articles 3, 25, 50, 53 and Commission GPAI guidelines/code of practice; get a summary matrix reviewed for legal follow-up.

**Q112 [P1]** How should Agent Skills (SKILL.md, now an open standard and 'Skills over MCP' extension) be used as the OS's documentation/operations layer for agents, versus MCP tools, versus CLI with --help/JSON output? What did Olares's '12 skills compiled into CLI' and Omarchy's agent-native desktop learn about versioning skills with binaries?  
*Why:* AI-2 lists MCP, CLI, API, SSH; choosing the primary agent surface for OS self-management (AI-4) affects how the OS is documented and tested.  
*Method:* Read agentskills spec, MCP skills extension SEP, Olares CLI source, Omarchy repo; build the same 'install app + diagnose failure' task three ways (MCP tools, skill+CLI, raw API) and measure agent success rate with local and frontier models.

**Q113 [P1]** How should the OS register itself and its apps with external agents (Claude, ChatGPT, Gemini, Cursor, Goose) securely over the internet: Tailscale/Headscale-only, MCP Server Cards, a OneMind-run relay, Cloudflare-style tunnels, or WireGuard; and how is the private registry exposed (MCP Registry OpenAPI sub-registry) without leaking the device inventory?  
*Why:* U-5 remote access plus AI-3 'external AIs when allowed' creates an internet-facing attack surface on home devices; also decides whether OneMind needs a cloud relay (conflicts with M-1 timing).  
*Method:* Read MCP Registry OpenAPI and Server Cards SEP, Tailscale/Headscale and Tailscale's MCP/aperture-type features, Umbrel remote MCP guidance; prototype exposing the gateway to claude.ai via tailnet funnel vs relay; threat-model each.

**Q114 [P1]** Is kagent (CNCF), Kubernetes-native agent frameworks (Dapr Agents, KAgent, LangGraph Platform self-hosted), or a custom OneMind operator the right way to run long-lived agents (Hermes, OS agent, per-user assistants) as Kubernetes resources with lifecycle, secrets, tool bindings and scaling to zero on small boxes?  
*Why:* Agent runtime choice determines how agents are packaged in the app store and whether they survive A/B updates and restores cleanly.  
*Method:* Read kagent, Dapr Agents, LangGraph self-hosted docs and CRDs; deploy each on k3s on the Beelink (8 GB) and measure idle RAM; port one Hermes agent to the best candidate.

**Q115 [P1]** How should secrets used by agents (API keys, OAuth refresh tokens for cloud integrations, device credentials) be stored and brokered so the LLM never sees them: Kubernetes secrets + encryption at rest, OpenBao/Vault, SOPS, 1Password-style brokers, MCP URL-mode elicitation; and how do these survive A/B rollback and restic restore?  
*Why:* U-4 secret management and AI-3 auto-registration intersect; leaked tokens via model context are a top agent risk; must be compatible with the backup/restore design in ADR-001 D5.  
*Method:* Read MCP security best practices, OpenBao docs (license, arm64), k3s secrets-encryption docs; prototype a token broker that injects credentials at the gateway; test restore onto a clean box.

**Q116 [P1]** How does the AI layer behave fully offline/air-gapped (off-grid homestead, disaster, contested environment): model and skill updates via sneakernet, signed model artifacts (OCI artifacts + cosign, ModelKit/KitOps), registry mirrors, and degraded modes when the GPU box is down?  
*Why:* Sovereignty and off-grid users (N-6) require AI that works with no internet; the update/signing pipeline for models must match the Rugix/OS signing design.  
*Method:* Read KitOps/ModelPack (CNCF) specs, OCI artifact and cosign docs, Ollama/vLLM offline loading; run an air-gapped k3s install with model bundle import on a test box and document the procedure.

**Q117 [P1]** What supply-chain risks exist in the MCP/agent ecosystem (malicious MCP servers, tool poisoning, rug-pull tool description changes, typosquatted skills, compromised npm/PyPI packages) and what vetting pipeline must the OneMind app/plugin store run (SBOM, signature, sandbox scan, tool-description diffing, pinned hashes)?  
*Why:* A-5/A-6 community plugins plus AI-3 auto-registration turn every plugin into a potential injection vector with OS privileges; CRA also requires vulnerability handling.  
*Method:* Read published research on MCP tool poisoning (Invariant Labs, Trail of Bits), MCP Registry verification model, Sigstore/SLSA docs; scan the top 200 public MCP servers for risky patterns with an automated tool; design store pipeline.

**Q118 [P1]** How do agents need to see and operate the dashboard itself: should the OneMind UI be built so every UI action is an MCP tool/MCP App (ui:// resources) and vice versa, and how do MCP Apps sandboxed iframes, Backstage Actions Registry, and HA's entity model inform a 'UI = API = agent tool' architecture?  
*Why:* P-2 calls the front door the missing piece; designing UI and agent surfaces from one action registry avoids two diverging control planes.  
*Method:* Read MCP Apps extension (ext-apps repo), Backstage actions/mcp-actions docs, HA websocket API; prototype a dashboard module whose buttons call the same action registry the gateway exposes.

**Q119 [P1]** How should evaluation of the AI layer be done continuously (agent task success, tool selection accuracy, injection resistance, latency per tier) as part of CI for each OS release, and which open harnesses (MCP-Bench, tau-bench, AgentDojo, BFCL, Inspect) fit?  
*Why:* A sole developer (M-6) needs automated guard rails; regressions in agent behavior across model or OS updates must be caught before shipping signed images.  
*Method:* Read harness repos and licenses; build a OneMind eval suite of 50 OS tasks; run against local models per tier and frontier APIs in GitHub Actions/self-hosted runners; track metrics per release.

**Q120 [P1]** How should the existing proven-concept cluster (DOKS + Argo CD + NATS + Authentik + onemind-mcp + Backstage MCP + kubernetes-mcp-server + Hermes) be audited as the reference for the AI layer: which agent integrations already work, what failed (e.g., Hermes Bedrock 429s, truncation), and which components port unchanged to a single-box k3s?  
*Why:* The founder asked for the cluster to be the proof of concept; real operational data on what agents did well/badly informs the gateway and router design.  
*Method:* Read-only inspection via onemind-backstage and onemind-kubernetes MCP tools, Argo CD app manifests, NATS subject doctrine and Hermes logs; produce a component-by-component portability and lessons-learned table.

**Q121 [P2]** What are the measured limits of local VLM/VLA models for drone and robot perception-to-action on Jetson (e.g., GR00T N-series, OpenVLA, SmolVLA, pi0-class, Cosmos Reason), and how should the OS separate slow LLM 'deliberation' agents from fast deterministic controllers?  
*Why:* Defines the physical-AI architecture for the moat and the hardware tiers to sell for robotics; P2-horizon but the separation principle affects the device API now.  
*Method:* Read model cards and papers; benchmark inference latency on Jetson Orin/Thor and RTX; build a reference architecture with LLM planner -> skill library -> ROS 2 controllers, tested in Isaac Sim.

**Q122 [P2]** How will on-device NPUs (Hailo, Intel/AMD NPUs, Qualcomm, RK3588, Apple-class unified memory boxes, future RISC-V accelerators) be exposed uniformly to containers and the model router, and which abstraction (ONNX Runtime EPs, OpenVINO, IREE, WebNN, DRA drivers) is most likely to last 5–10 years?  
*Why:* Hardware-agnosticism against NVIDIA lock-in is a stated sovereignty goal; the accelerator abstraction must survive vendor churn across the 5–10 year plan.  
*Method:* Read ONNX Runtime EP matrix, OpenVINO, IREE, DRA driver ecosystem, Hailo k8s plugins; test same model across Hailo on Pi 5, Intel NPU, RTX via ONNX Runtime; track vendor kernel driver upstream status.

**Q123 [P2]** How do MCP, A2A, MHS and Agent Skills governance and versioning cadences (AAIF/LF, SEP process, breaking-change history 2024–2026) predict churn over 5–10 years, and what abstraction layer lets OneMind swap protocols without rewriting apps (e.g., internal capability schema with protocol adapters)?  
*Why:* MCP already had major breaking changes in 2026; the long-horizon plan must assume protocol churn and isolate apps from it.  
*Method:* Analyze MCP spec changelogs and SEP history, A2A release history, AAIF charter; quantify breaking changes per year; design and document an adapter-based capability schema.

**Q124 [P2]** What regulatory and liability regimes over 5–10 years apply to an OS whose agents act on homes, vehicles, drones and public-safety data (EU AI Act high-risk categories, CRA, US state AI laws, CJIS for public safety, COPPA for kids' features), and what design artifacts (risk logs, human oversight, logging, model cards) must be built in now?  
*Why:* Enterprise/public-safety and family segments carry the highest compliance load; retrofitting oversight and logging later is costly.  
*Method:* Read EU AI Act text and Annex III, CRA, CJIS Security Policy (latest), COPPA rule amendments, Colorado/California AI laws; map each obligation to an OS feature; flag items needing legal counsel.

## Kubernetes & platform: distro lifecycle/governance, topology scaling (single-node to multi-site federation), edge frameworks, GitOps + app store coexistence, app packaging, storage, backups, networking, NATS edge buffering, observability, DOKS-to-OneMind migration, Backstage vs consumer dashboard

**Q125 [P0]** Is Kubernetes (k3s) on every tier actually justified, or should Lite/Pi/robot nodes run a Docker/Podman (Quadlet/systemd) runtime with k3s only on Pro/Omni boxes? Measure the idle RAM, CPU, flash-write volume (bytes/day) and boot-to-ready time of k3s (SQLite/kine), k0s, MicroK8s, Talos and plain Podman+Quadlet running the same 10-app reference set on a Pi 5 (4 GB/8 GB), a Beelink U55 (i3-5005U/8 GB) and a Jetson Orin Nano.  
*Why:* ADR-001 D4 picks k3s everywhere, but HAOS and Umbrel (the two most proven appliances) use Docker, and requirement N-9 says this is still undecided. This decides the whole app runtime.  
*Method:* Hardware benchmark on Pi 5, Beelink U55, Dell 5540 and a Jetson; measure with /proc, iostat, smartctl/eMMC wear counters and systemd-analyze; publish the scripts in the repo

**Q126 [P0]** How do the lifecycles and governance of k3s, RKE2, k0s, Talos/Omni and MicroK8s compare: release cadence, how many minors are supported and for how long, who funds maintainers (SUSE, Mirantis, Sidero, Canonical), contributor concentration (bus factor), CNCF status, license, and what happens to downstream users if the vendor is acquired or pivots (Rancher/SUSE history, Mirantis k0s)?  
*Why:* OneMind sells hardware with a 5–10 year support promise (R-3, EU CRA). The distro's governance risk is foundation-level and is UNVERIFIED in ADR-001 §5 (SUSE k3s lifecycle).  
*Method:* Primary docs (k3s/RKE2 release & support matrix pages, SUSE lifecycle pages, k0s docs, Talos support policy), GitHub contributor analytics (CNCF devstats, git shortlog over 3 years), CNCF TOC records

**Q127 [P0]** Should OneMind replace 'mutable Debian + Rugix A/B + k3s installed on top' with Talos Linux (immutable, API-only, Kubernetes-native, A/B built in, SBC support including Pi and Jetson via overlays/extensions) as the base for boxes? Compare Talos on Pi 5, x86 and Jetson Orin against the ADR-001 stack for update and rollback, NVIDIA driver extensions, read-only root, Secure Boot/TPM (UKI), footprint, and support for non-Kubernetes host needs (BLE, LoRa, serial radios, CAN, ROS 2 DDS).  
*Why:* This directly challenges D1 to D4. Talos merges the OS image and k8s lifecycle into one signed artifact, which could remove the two-layer update problem entirely. Its MPL-2.0 license and Sidero's governance also need checking.  
*Method:* Talos docs (Image Factory, system extensions, SBC overlays, nvidia-container-toolkit extension), sidero-labs/talos source review, hardware test on Pi 5 + Dell 5540 + Jetson; compare against the ADR spike #1 results

**Q128 [P0]** How exactly do the OS A/B layer (Rugix/RAUC) and the Kubernetes layer interact during an update? Specifically: where does k3s's binary and data dir (/var/lib/rancher) live; can a k3s minor upgrade be shipped inside the OS image vs via system-upgrade-controller; what happens to etcd/SQLite schema and CRDs when the OS rolls back to a slot with an older k3s; and how is the 'healthy before commit' gate implemented (systemd unit + kubectl readiness checks + timeout)?  
*Why:* ADR-001 D3 promises 'commit only after k3s + core pods are healthy' and separate k3s upgrades. A rollback to an older k3s against a newer datastore could brick the cluster. No competitor has solved this (Olares has no rollback).  
*Method:* Read Rugix (rugix/rugix) and RAUC source for commit/boot-count hooks; k3s docs on downgrade and datastore migrations; build a prototype on the Dell 5540 and force failures (bad kubelet, failed CNI, rollback after a k3s minor bump)

**Q129 [P0]** For single-node k3s using SQLite (kine), what does `k3s etcd-snapshot` cover (if anything), what is the supported backup/restore path, and is embedded etcd on a single node (cluster-init) a better default given flash wear, RAM and future HA join? Measure write amplification of SQLite vs etcd on SD/eMMC/NVMe.  
*Why:* Flagged UNVERIFIED in ADR-001 §5 and spike #3. The datastore choice decides whether a single box can later grow into an HA cluster without reinstalling.  
*Method:* k3s docs + k3s-io/kine and k3s source (pkg/etcd, datastore code), hardware test: snapshot, wipe, restore onto clean box; measure writes with iostat/blktrace over 72h

**Q130 [P0]** What is the growth path from 1 box to 3-node HA to many boxes per household/site, and how does a consumer do it without touching kubeconfig? Can single-node SQLite convert to embedded etcd in place? How do joining tokens, node roles (server vs agent), quorum loss with 2 nodes, and removing a dead node work in k3s/RKE2/k0s/Talos? What UX do Olares (multi-node), Harvester and Talos Omni use for 'add a node'?  
*Why:* UX-6 (multiple machines in one interface), M-4 (person to enterprise) and N-1 (everything is a node) all depend on this. 2-node households are common and have no quorum.  
*Method:* Distro docs + source (k3s cluster-init/join code, Olares installer scripts in beclab/Olares), hardware test with Pi 5 + Beelink + Dell: join, kill leader, recover

**Q131 [P0]** Which multi-site / federation model fits sovereign, intermittently connected sites (homestead, vehicle, field team, enterprise HQ): one cluster stretched over Tailscale, many independent clusters managed by Fleet/Argo CD ApplicationSets/Flux/Open Cluster Management/Karmada/Liqo/Rancher, or edge frameworks (KubeEdge, OpenYurt, SuperEdge, Akri)? Compare behavior under days-long disconnection, bandwidth needs, and autonomy (does the edge keep running and accept local changes when cut off?).  
*Why:* Federation is a P-4 product surface and the TAK/off-grid users depend on partition tolerance. Choosing wrong locks in the multi-site architecture for years.  
*Method:* Primary docs and CNCF project health data for each; lab test with 2–3 k3s clusters joined over Tailscale/Headscale with netem-simulated partitions (tc) of hours/days

**Q132 [P0]** Are KubeEdge or OpenYurt still worth adopting in 2026 (release activity, maintainers, CNCF graduation status, Raspberry Pi/Jetson support, MQTT/device twin model) versus treating robots/drones as plain k3s agents or as non-k8s NATS leaf nodes with an MCP/MHS adapter? What do real robotics fleets (NVIDIA Isaac/Fleet Command, Formant, InOrbit, Open-RMF, Viam, Foxglove) use on the robot itself?  
*Why:* M-7/N-1/N-7 require robots and drones to be first-class nodes. Running kubelet on a flight controller companion computer may be wrong; the industry pattern needs evidence.  
*Method:* GitHub activity analysis, CNCF landscape, vendor docs (Viam RDK, Formant agent, Open-RMF), reverse-engineer agent architectures from open repos; test KubeEdge edgecore on Jetson

**Q133 [P0]** How should GitOps (Argo CD or Flux) coexist with a consumer one-click app store? Study how Olares Market, Umbrel's app framework, CasaOS/ZimaOS, Cosmos Cloud, Runtipi, Rancher Apps, Portainer and Kubeapps model installed apps: is installed-app state stored in Git, CRDs, a DB, or Helm releases? Can a user click-install and an admin still see a declarative, diffable source of truth? Which engine (Argo CD, Flux helm-controller, Helm SDK directly, Sveltos, Kapp-controller, Carvel) fits a 2 GB node?  
*Why:* The founder's cluster already runs Argo CD; requirement A-1 needs a consumer store; P-9 needs cluster support. Picking the wrong reconciliation model causes drift and duplicated state.  
*Method:* Reverse-engineer beclab/Olares app-service and market code, getumbrel/umbrel app install code, IceWhaleTech CasaOS-AppManagement; measure Argo CD vs Flux controller RAM on k3s

**Q134 [P0]** What is the OneMind app package format? Compare Helm charts, Olares Application Chart (OAC: OlaresManifest.yaml), umbrel-app.yml + docker-compose, CasaOS x-casaos compose extensions, Cosmos/Runtipi formats, Kubernetes Application CRD/KubeVela OAM and Timoni/CUE: what metadata each has (permissions, ports, storage, GPU needs, dependencies, AI/MCP exposure, backup hooks, entrance/ingress, multi-user). Can a converter import Umbrel and CasaOS catalogs (hundreds of apps) into the OneMind format automatically, and what is the license status of those catalogs?  
*Why:* A-1, A-3, AI-3 (install = register for AI with permissions). The manifest schema is a long-lived public contract that is very costly to change later.  
*Method:* Read the spec docs and schemas (beclab OAC docs, getumbrel/umbrel-apps repo, IceWhaleTech CasaOS-AppStore), write a prototype converter over the full catalogs and report the success rate; check catalog repo licenses

**Q135 [P0]** Which storage stack per tier: local-path, Longhorn (v1 vs V2/SPDK data engine), OpenEBS (LocalPV-ZFS, LVM, Mayastor), ZFS on host (Umbrel FailSafe), Rook-Ceph, TopoLVM? Measure RAM/CPU overhead on Pi 5 and mini PCs, rebuild time after a node loss, behavior on single-disk boxes, snapshot/clone support (CSI VolumeSnapshot), and how each survives an A/B OS rollback (kernel module/ZFS version mismatch between slots).  
*Why:* D5 picks local-path + Longhorn. Longhorn's ~4 vCPU/4 GiB per node is huge for Lite boxes; ZFS kernel-module/DKMS coupling with A/B images is a real rollback hazard.  
*Method:* Hardware benchmark (fio, rebuild tests) on Pi 5 + Beelink + Dell; docs for Longhorn/OpenEBS/Rook resource requirements; review Umbrel's ZFS handling in umbrelOS image builds

**Q136 [P0]** What is the complete, tested backup and disaster-recovery design for a OneMind box: restic vs Kopia vs Velero (+ kopia/restic uploader) vs k8up vs Longhorn backup vs etcd snapshots. Cover per-user encryption keys, application-consistent backups (database hooks for Postgres/SQLite apps), backing up CRDs/secrets/Helm state, restore onto different hardware (Pi to x86), cross-box backup ('back up to your friend's OneMind'), and automated restore verification.  
*Why:* Backups are one of Zeus's top concerns. D5 chooses restic but leaves Longhorn encryption, hostPath and multi-user keys unverified; restore-onto-new-hardware is what sells trust.  
*Method:* Read Velero, k8up, Kopia and restic docs/source; full DR drill: back up a box running 10 apps, destroy it, restore onto a different arch, verify app data; compare Umbrel and HAOS backup format docs

**Q137 [P0]** Networking stack choice per tier: Flannel (k3s default) vs Cilium vs Calico on Pi 5/Jetson (eBPF kernel requirements, RAM), NetworkPolicy support for per-app isolation, ServiceLB (klipper) vs MetalLB vs kube-vip for LAN IPs, Traefik vs Envoy Gateway vs Cilium Gateway for Gateway API, and mDNS/'.local' discovery so a browser at a local address just works (P-1). What do Olares and Umbrel do for local DNS and TLS on the LAN?  
*Why:* D4 says Traefik replaces ingress-nginx (EOL March 2026). Per-app isolation (U-4, D6) needs NetworkPolicy; LAN discovery is core UX.  
*Method:* Docs + hardware benchmark of Flannel vs Cilium on Pi 5; reverse-engineer Olares (l4-bfl-proxy, DNS) and Umbrel (mDNS, umbrel.local) networking code

**Q138 [P0]** How do remote access and the mesh work together: Tailscale vs self-hosted Headscale vs NetBird vs Nebula vs Netmaker vs WireGuard + innernet, plus Cloudflare Tunnel/frp for public exposure? Compare self-hosting ability, license, DERP/relay self-hosting, ACL/identity integration with Authentik (OIDC), Kubernetes operator support (Tailscale operator), multi-cluster connectivity, and behavior on offline LANs (no coordination server reachable).  
*Why:* U-5 and N-6 (native mesh, off-grid) plus the founder's current reliance on Tailscale. Coordination-server dependence conflicts with sovereignty and off-grid operation.  
*Method:* Project docs and licenses, Headscale feature-parity matrix, lab test with internet cut while the LAN stays up; review how Olares (Headscale-based tailnet) and Umbrel (Tailscale app) implement it

**Q139 [P0]** How should NATS JetStream be deployed across edge to core: leaf nodes vs superclusters/gateways vs stretched clusters; JetStream domains, mirrors and sources for store-and-forward when a robot/vehicle/homestead is offline for days; storage and RAM limits on Pi/Jetson; subject-mapping/account isolation per tenant and per user; and how the existing OneMind NATS subject doctrine maps to multi-site?  
*Why:* NATS is an existing proven asset (AI-9, Hermes leaf connectivity) and the natural transport for disconnected ops, telemetry and agent discovery. The leaf/domain topology is a foundation decision for federation.  
*Method:* NATS docs (leafnodes, JetStream domains, mirrors), nats-server source; lab test with leaf node on Pi 5 disconnected 48h with telemetry load, measure replay and disk usage; read current cluster NATS config

**Q140 [P0]** What exactly does the current DOKS cluster run (namespaces, Helm releases, Argo CD Applications, CRDs, PVC sizes, LoadBalancers, ingress rules, Authentik/TAK/NATS/Backstage/Hermes dependencies, secrets management, DO-specific annotations, backup jobs), and what is the measured effort to move it to a OneMind k3s node: which items need more than the 3 changes listed in ADR-001 D4 (e.g. TAK Server Postgres/certs, CloudTAK, cert-manager DNS-01 with DO, external-dns, alerts to Matrix/Telegram)?  
*Why:* The cluster is the proof of concept (P-9) and the brief asks how it becomes the OneMind model. The '3 changes' claim must be tested, not assumed.  
*Method:* Read-only inventory via the onemind-kubernetes MCP / kubectl get -A, Argo CD app list, Backstage catalog; then migrate a copy of 2–3 apps to k3s on the Dell 5540 (ADR spike #7) and log every change

**Q141 [P0]** What role should Backstage play: keep it as the operator/developer portal (catalog, TechDocs, scaffolder, MCP via the existing onemind-backstage server) for Pro/enterprise, replace it with a consumer dashboard, or feed the consumer dashboard from the Backstage catalog model? Compare Backstage resource cost (Node.js + Postgres RAM) on a 4–8 GB box, its plugin ecosystem, and what Olares Control Hub, Umbrel, Homarr, Homepage, Cockpit, Portainer and Rancher Dashboard expose.  
*Why:* P-2 says Backstage is too shallow for consumers, yet it is the existing proven asset. A clear split avoids building two catalogs.  
*Method:* Measure Backstage RAM/CPU on k3s; review Backstage catalog model docs and the onemind-backstage MCP; reverse-engineer Olares Control Hub and Umbrel UI APIs

**Q142 [P0]** How should multi-tenancy be modeled on one box for a family (U-1 'everyone gets their own umbrel') and later for orgs: namespace-per-user (Olares model), vcluster/Capsule/HNC, or app-level users only? How does Olares map a user to namespaces, quotas, RBAC and identity (its Authelia/LLDAP stack), and how would Authentik (existing) provide OIDC to the Kubernetes API, Argo CD, apps and the capability gateway?  
*Why:* Multi-user, parental controls (U-3) and per-app isolation are core requirements; the tenancy model is baked into the app manifest and storage layout.  
*Method:* Reverse-engineer beclab/Olares user and namespace controllers; docs for Capsule, vcluster, HNC; prototype Authentik OIDC to k3s API server on test box

**Q143 [P0]** Where do GPU and accelerator workloads fit on k3s across vendors: NVIDIA device plugin vs GPU Operator vs DRA (Dynamic Resource Allocation, GA status in k8s 1.34+) with the NVIDIA DRA driver; time-slicing/MPS/MIG on consumer RTX; Jetson's integrated GPU on k3s (L4T containerd runtime config); AMD ROCm, Intel Arc/NPU, Hailo and Rockchip NPU device plugins; plus scheduling (KAI Scheduler, Kueue, Volcano) on a 1–3 node home cluster.  
*Why:* N-8 (NVIDIA partner) vs sovereignty/no lock-in; AI-8 automatic GPU detection; the GPU Operator does not list Debian (ADR D2 risk).  
*Method:* NVIDIA docs (k8s-device-plugin, GPU Operator platform support, DRA driver), AMD/Intel/Hailo device-plugin repos; hardware test on Jetson + a cloud RTX GPU on k3s with Debian 13

**Q144 [P0]** Is the Jetson flavor (L4T/Ubuntu 24.04) better served by running k3s on JetPack directly, by Talos/Kairos/Balena/Mender-based images, or by keeping Jetsons as non-k8s robot nodes managed over NATS? What A/B mechanism does NVIDIA itself support on Jetson (L4T rootfs A/B, OTA tools, capsule updates), and how do they combine with k3s and containerd?  
*Why:* ADR-001 §5 lists the Jetson A/B method as unverified; robotics is the moat (M-7), so the robot node lifecycle must be solid.  
*Method:* NVIDIA Jetson Linux developer guide (rootfs A/B, OTA), Kairos/Talos Jetson docs, balenaOS Jetson device types; hardware test on Jetson Orin Nano/AGX

**Q145 [P1]** How should the k3s/RKE2 control plane and add-ons be versioned and upgraded across thousands of customer boxes without a central operator: system-upgrade-controller plans vs baked into OS image vs Talos-style API; Kubernetes version-skew rules (never skip a minor) for boxes left offline for 1–2 years; and how do Olares, Rancher Fleet, Talos Omni and Kairos handle 'box that missed 4 minor releases'?  
*Why:* R-1 says users update when they want, so some boxes will lag for years. Kubernetes skew policy makes catching up a multi-step risk that must be designed in.  
*Method:* Kubernetes version-skew policy docs, system-upgrade-controller source, Kairos upgrade docs; test on a box jumping from k3s 1.33 to 1.37 stepwise and directly

**Q146 [P1]** What observability stack fits a single 4–8 GB box and scales to a fleet: VictoriaMetrics/VictoriaLogs vs Prometheus+Loki+Grafana vs OpenTelemetry Collector + ClickHouse (the founder's existing data plane), with alerts delivered natively in the OneMind app (UX-4) rather than external services? Measure RAM, disk/day and flash writes, and define what telemetry is shared upstream (opt-in) for support.  
*Why:* UX-4 requires a built-in alert system; R-2 needs support telemetry; heavy stacks are infeasible on Lite boxes.  
*Method:* Benchmark on Pi 5 and Beelink with the reference app set; VictoriaMetrics/OTel docs; review how Olares Dashboard and HAOS diagnostics collect metrics

**Q147 [P1]** What is the security baseline for k3s/RKE2 on an appliance, and how far does each hit the CIS benchmark and NSA/CISA hardening guidance out of the box: secrets encryption at rest with TPM-sealed keys, Pod Security Admission, Kyverno vs OPA Gatekeeper vs ValidatingAdmissionPolicy (CEL) RAM cost, image signature verification (cosign/Sigstore policy-controller, Notary) for the app store, audit logging, and runtime detection (Falco/Tetragon) on Pi/Jetson?  
*Why:* D6 day-1 security, public-safety tier (RKE2), EU CRA obligations from 2027-12-11, and an open app store that installs third-party containers.  
*Method:* Run kube-bench against k3s and RKE2 defaults on test box; docs for Kyverno/Gatekeeper/VAP; measure RAM; review Sigstore policy-controller

**Q148 [P1]** How do the app store's AI/MCP capability registration and Kubernetes objects line up: should every installed app get an auto-generated MCP endpoint described by a CRD (e.g. a 'Capability' resource), with RBAC/ServiceAccount-scoped tokens and human-in-the-loop approval, and are there existing projects doing MCP-on-Kubernetes (kagent, ToolHive, MCP gateways, Kubernetes MCP servers, Agent Substrate work shown at KubeCon NA 2026)?  
*Why:* AI-1/AI-3/AI-5 are the differentiator; the capability layer should reuse k8s RBAC and admission rather than inventing parallel auth.  
*Method:* Review kagent, stacklok/toolhive, containers/kubernetes-mcp-server, KubeCon NA 2026 talks/repos; prototype a CRD + controller that exposes one app over MCP

**Q149 [P1]** Should OneMind build its own operator/control plane (a 'OneMind controller' with CRDs for App, User, Node, Capability, Backup, Bundle) like Olares's app-service/bfl, or compose existing CNCF projects (Argo CD, Crossplane, KubeVela, Cluster API)? What is the maintenance cost for a solo developer (M-6) of each path?  
*Why:* M-6 demands guard rails for one developer without capping growth; owning too much control-plane code is the main sustainability risk.  
*Method:* Reverse-engineer beclab/Olares framework components (app-service, bfl, system-server) and count LOC/commit rate; compare with KubeVela/Crossplane docs and maintenance burden

**Q150 [P1]** How should container images and the app catalog be distributed for offline and air-gapped sites: an on-box registry mirror (Zot, Harbor, Spegel peer-to-peer image sharing, k3s embedded registry mirror), preloaded image tarballs in the OS image, OCI artifacts for Helm charts, and sneakernet updates via USB? What does k3s air-gap install and RKE2 air-gap support look like in practice?  
*Why:* Off-grid/homestead/TAK users (N-6, domains) and public-safety air-gapped networks need installs and updates without internet.  
*Method:* k3s/RKE2 air-gap docs, Spegel and Zot docs/source, lab test: install and update 10 apps with internet blocked using USB-delivered bundles

**Q151 [P1]** For the hardened public-safety/enterprise tier, is RKE2 actually needed, or does k3s with hardening (CIS profile, SELinux, FIPS-validated Go crypto in newer Go releases) meet the same requirements? Verify RKE2's current FIPS 140-3 status, STIG availability (DISA STIG for RKE2), SELinux policies on Debian (RKE2 SELinux targets RHEL-family), and RKE2 rollback/downgrade documentation.  
*Why:* D4 adds RKE2 as a second distro, which doubles testing for a solo developer; RKE2 SELinux on Debian may not even be supported. ADR §5 lists RKE2 rollback as unverified.  
*Method:* RKE2 docs (security, FIPS, SELinux), DISA STIG library, rancher/rke2-selinux repo; install RKE2 on Debian 13 with SELinux enforcing and run kube-bench

**Q152 [P1]** How should robotics middleware coexist with Kubernetes networking: ROS 2 DDS (Fast DDS/Cyclone DDS) multicast discovery across pod networks, Zenoh as a bridge (rmw_zenoh), hostNetwork vs Multus/macvlan, real-time scheduling (PREEMPT_RT kernel, CPU pinning via kubelet static CPU manager) and access to devices (USB cameras, CAN, serial, MAVLink radios) via device plugins or Akri/smarter-device-manager?  
*Why:* M-7 requires the platform be optimized for robotics from day one; DDS multicast and real-time constraints are the known pain points of ROS on Kubernetes.  
*Method:* ROS 2 and Zenoh docs, papers/talks on ROS 2 on k8s, Akri docs; hardware test on Jetson with ROS 2 Jazzy/Kilted nodes in pods talking to a Pi 5

**Q153 [P1]** How should the k8s Gateway API, TLS and identity be done for LAN-only boxes without public DNS: per-box local CA with trust onboarding on phones/laptops, ACME via a OneMind DNS service (like Olares's olares.cn/terminus domains or Umbrel's approach), Tailscale HTTPS certs, or self-signed with pinning in the mobile app? What does each mean for sovereignty (dependency on a OneMind-run service)?  
*Why:* P-1/UX-8 require that opening the box in a browser or phone app just works securely, which is a known hard problem for local-first products.  
*Method:* Reverse-engineer Olares DNS/cert flow and Umbrel's HTTPS behavior; docs for cert-manager, step-ca, Tailscale cert; test on iOS/Android trust flows

**Q154 [P1]** What is the per-box resource budget for the OneMind platform layer itself (k3s, CNI, ingress, NATS, identity, backup agent, metrics, dashboard, capability gateway, GitOps controller) on Lite (Pi 5 4 GB), Pro (mini PC 16–32 GB) and Omni (GPU box) tiers, and which components must be optional/swappable per edition to keep Lite under e.g. 1.5 GB idle?  
*Why:* D-002 says design all tiers together with no tier left behind; the platform overhead decides which hardware is sellable as Lite.  
*Method:* Assemble the full reference platform on k3s and measure on each tier; compare with Olares's published minimum requirements and Umbrel's footprint

**Q155 [P1]** How should the founder's cluster be restructured as the reference 'OneMind Cloud/Omni' deployment: keep DOKS as a hub (Argo CD hub-and-spoke managing home boxes, NATS hub, Authentik as federation IdP, TAK Server) vs move everything onto owned hardware, and what is the measured monthly cost and latency of each given current cloud credits and the current backup setup?  
*Why:* M-1 says local-first with OneMind cloud later; the existing cluster can be either the hub of the federation or a migration source. This is the 1–2 year infrastructure plan.  
*Method:* Read-only cluster inventory + DO billing; Argo CD multi-cluster docs; prototype a home k3s box registered to the DOKS Argo CD over Tailscale

**Q156 [P1]** How do Kubernetes-native app platforms handle app data on uninstall/reinstall, app upgrades with schema migrations, and rollbacks of an individual app (Helm rollback vs PVC snapshot + rollback)? What do Umbrel (per-app data dirs), Olares and CasaOS do, and what must the OneMind manifest declare (pre-upgrade backup hook, migration jobs) to make per-app rollback safe?  
*Why:* R-1 safe user-controlled updates apply to apps, not just the OS; Helm rollback does not roll back data.  
*Method:* Reverse-engineer app upgrade code in getumbrel/umbrel and beclab/Olares; test Helm rollback + CSI VolumeSnapshot restore on Longhorn/OpenEBS

**Q157 [P1]** Is there a credible lighter control plane for constrained nodes that still speaks the Kubernetes API (k3s agent-only, Virtual Kubelet, KubeEdge edgecore, k0s worker, 'kine + kubelet' only), and how much RAM does a k3s agent actually use on a Pi Zero 2 W / CM5 / Jetson Orin Nano class device?  
*Why:* N-1/N-2 everything is a node including tiny sensors; we need the floor below which a device becomes a NATS/MCP-only peripheral instead of a k8s node.  
*Method:* Hardware measurement on Pi Zero 2 W, CM5 and Orin Nano; Virtual Kubelet and KubeEdge docs

**Q158 [P1]** How should OneMind handle Kubernetes and dependency supply chain for EU CRA: SBOMs (SPDX/CycloneDX) for the OS image, k3s and every catalog app, vulnerability scanning (Trivy/Grype) in the app-store pipeline, VEX statements, and declared support periods per component? Which upstreams (k3s, Longhorn, Traefik, NATS, Authentik) publish SBOMs and signed images today?  
*Why:* EU CRA reporting applies since 2026-09-11 and main obligations from 2027-12-11; selling boxes with an app store makes OneMind the manufacturer of record.  
*Method:* EU CRA text and ENISA guidance; check each upstream's release assets for SBOM/cosign signatures; prototype a Trivy + syft pipeline over the catalog

**Q159 [P1]** Which Kubernetes-adjacent projects in the stack carry license or governance risk over 10 years (relicensing events like HashiCorp BSL, Redis, Elastic; Traefik Labs, Synadia/NATS licensing and the 2025 CNCF dispute, Authentik enterprise features, Longhorn/SUSE, Backstage/Spotify), and what are fallback forks or alternatives (OpenBao, Valkey, NATS forks, Keycloak/Zitadel/Kanidm)?  
*Why:* D-001 open-core Apache-2.0 and the 5–10 year horizon require knowing where the stack could be pulled out from under OneMind.  
*Method:* License files and changelogs, CNCF/LF announcements, news archives of relicensing events, GitHub ownership/maintainer analysis

**Q160 [P2]** Should the OneMind app runtime support WebAssembly and lightweight sandboxes (SpinKube/runwasi, Kata Containers, gVisor, Firecracker microVMs, KubeVirt for full VMs like Home Assistant OS or Windows) for untrusted community apps and AI agent sandboxes, and what is the overhead on ARM boards?  
*Why:* A-6 community apps and the Olares 'sandbox' category; agents executing code need stronger isolation than namespaces; KubeVirt also enables running HAOS as a VM.  
*Method:* Project docs (SpinKube, Kata, gVisor, KubeVirt ARM64 support), benchmark on Pi 5 and Dell 5540

**Q161 [P2]** What does a 5–10 year Kubernetes roadmap look like: trends in Kubernetes at the edge (DRA, in-place pod resize, sidecar containers, Gateway API maturity, cgroup v2 only, user namespaces), the likelihood k3s remains maintained vs consolidation into RKE2/Talos, and the possibility of non-Kubernetes orchestration rising for edge (Nomad, wasmCloud, Zenoh-based systems)? Which design choices keep OneMind portable across orchestrators (OCI images, a OneMind app manifest abstraction, NATS as the bus)?  
*Why:* The 5–10 year plan must survive orchestrator churn; an abstraction layer decided now keeps future options open.  
*Method:* Kubernetes KEPs and SIG roadmaps, CNCF annual surveys, KubeCon NA 2026 keynotes, project health metrics; architecture review of portability layers

**Q162 [P2]** How should a federation of sovereign OneMind sites share data and services between different owners (family to community to municipal/public-safety mutual aid) without a central authority: NATS account/operator trust chains, SPIFFE/SPIRE federated identity, OpenID Federation, multi-cluster service mesh (Cilium ClusterMesh, Linkerd multicluster, Istio ambient), and TAK federation patterns?  
*Why:* P-4 Federation, M-4 public safety and the 'industry standard for sovereign operations' ambition require cross-owner trust, not just multi-cluster under one admin.  
*Method:* Docs for NATS decentralized JWT auth, SPIFFE federation, Cilium ClusterMesh; TAK Server federation docs; lab test of two independently owned k3s sites sharing a NATS stream

**Q163 [P2]** At what scale and in which deployment shapes (warehouse, campus, vehicle convoy, drone swarm base station, municipal) does the single k3s cluster model break, and what is the reference architecture for 50–1,000 nodes per site including load balancing, storage (Ceph), and fleet management (Rancher/Fleet, Talos Omni, Spectro Cloud Palette Edge, Azure Arc/AWS EKS Anywhere as comparisons)?  
*Why:* M-4 enterprise and warehouse deployments and H-4 OEM; commercial edge platforms show what enterprises will expect.  
*Method:* Vendor reference architectures and docs, k3s scaling docs (E2 says ~1,200 agents), case studies; analyze Palette Edge and Omni feature sets

**Q164 [P2]** What would it take for OneMind's hardware to be certified by upstreams (CNCF Kubernetes conformance for the OneMind distro, SUSE/Rancher partner validation, NVIDIA-Certified Systems, Raspberry Pi 'Powered by' partnership) and does shipping a certified Kubernetes distro under the OneMind name have trademark or conformance obligations?  
*Why:* H-1 to H-4 and the 'industry standard' goal; certification affects enterprise sales and partner programs like NVIDIA Inception (D-006).  
*Method:* CNCF Certified Kubernetes program rules (cncf/k8s-conformance repo), NVIDIA-Certified Systems program docs, Raspberry Pi partner program pages

## Hardware & business: OEM/ODM, certification & regulatory (FCC/CE/UKCA/RoHS/WEEE, EU CRA, RED), supply chain & BOM, export controls/tariffs, competitor business models, NVIDIA programs, open-core licensing, trademarks, pricing tiers

**Q165 [P0]** Under the EU Cyber Resilience Act (Reg. 2024/2847), is a OneMind box (hardware + OS + app store) a 'default' product, an 'important product' Class I/II (e.g. router/OS/hypervisor categories in Annex III/IV), or 'critical'? Which conformity route (self-assessment Module A vs. harmonised standard vs. notified body) applies to (a) the OS image distributed free, (b) the sold box, (c) the Robotics/Edge tier?  
*Why:* Determines whether ADR-001's 'ship our own image' (D1) makes OneMind the CRA manufacturer of an operating system, which Annex III lists as Class I, potentially requiring harmonised standards or third-party assessment before EU sales from 2027-12-11.  
*Method:* Read CRA text (EUR-Lex), Commission implementing regulation on technical descriptions of Annex III/IV categories (2025), CEN/CENELEC JTC13 draft harmonised standards status; compare how Umbrel/HA Nabu Casa/Start9 publicly position CRA readiness.

**Q166 [P0]** How does the CRA 'open-source software steward' and non-monetised open-source exemption apply if the core is Apache-2.0 but monetised via boxes, paid tiers and support? Does publishing a free OS image while selling hardware make the free image a 'commercial activity' product?  
*Why:* D-001 open core Apache-2.0 assumes the free tier is low-liability; if the free image is in scope, SBOM, vulnerability handling, 5-year support-period and 24h ENISA reporting obligations apply to every release channel (stable/beta in D3).  
*Method:* CRA recitals 15-19 and Art. 24 (steward), Commission FAQ/guidance on CRA open source (2025-2026), Eclipse ORC WG / OpenSSF CRA guidance, Linux Foundation Europe analyses.

**Q167 [P0]** What minimum 'support period' must be declared under the CRA (Art. 13(8): at least 5 years unless shorter expected use) and how does it interact with Debian 13 free LTS ending 2030-06-30, Raspberry Pi kernel support, and JetPack/L4T Ubuntu 24.04 lifecycles? Who pays for the gap (Freexian ELTS, Ubuntu Pro for Devices, in-house backports)?  
*Why:* Challenges D2: a box sold in late 2027 on Debian 13 would need security support into 2032+; the base-OS choice must be costed against the legally declared support period.  
*Method:* CRA Art. 13; Debian LTS/ELTS (Freexian) pricing pages and contracts; request a quote for Ubuntu Pro for Devices; NVIDIA Jetson Linux lifecycle/roadmap pages; Raspberry Pi OS kernel LTS policy.

**Q168 [P0]** What does Ubuntu Pro for Devices actually cost per unit at 1k/10k/100k volumes and what terms (IoT app store, kernel livepatch, 10-12 yr ESM) apply, versus Freexian Debian ELTS per-package pricing for a fleet of appliances?  
*Why:* ADR-001 open item 'Pro for Devices pricing unpublished' is the main economic argument for Debian over Ubuntu; without a number the base decision rests on an assumption.  
*Method:* Contact Canonical sales for written quote; Freexian ELTS offer documents; interview OEMs using each (e.g. Advantech, Siemens Industrial OS based on Debian).

**Q169 [P0]** Which EU Radio Equipment Directive delegated act (2022/30) cybersecurity requirements (EN 18031-1/-2/-3, mandatory since 2025-08-01) apply to boxes with Wi-Fi/Bluetooth/LoRa/mesh radios, and does using a pre-certified module (e.g. Intel AX210 M.2, Pi CM5 radio) avoid re-testing the final product?  
*Why:* Native mesh (N-6) and radios in every box trigger RED; EN 18031 compliance includes access control, update mechanisms and default-password rules that constrain the OS design now.  
*Method:* Read EN 18031-1/2/3 and OJ citation (with restrictions), RED Art. 3.3(d)(e)(f); talk to a notified body (TUV, SGS, Element); check Raspberry Pi and Seeed compliance documentation for CM5/Jetson carrier boards.

**Q170 [P0]** For a first SKU, what is the realistic cost and timeline for FCC Part 15B (unintentional radiator) SDoC, Part 15C if radios are integrated, CE (EMC/LVD/RED), UKCA, ISED, RoHS 3, REACH SVHC and WEEE/battery producer registration, assuming (a) a white-label mini PC already certified by the ODM, (b) a custom carrier board around Pi CM5 or Jetson Orin module?  
*Why:* Decides whether the first hardware tier must be a rebadged certified mini PC (lowest risk) or a custom board; feeds H-1/H-2 timing and Open Question 4.  
*Method:* Quotes from 2-3 test labs; FCC rules on modular approval and re-labeling (KDB 996369, 784748); EU WEEE national registers (DE stiftung ear, FR) fee schedules; Raspberry Pi 'Powered by Raspberry Pi' and compliance support docs.

**Q171 [P0]** How do Umbrel (Umbrel Home/Pro), Olares (Olares One), ZimaCube/ZimaBoard (IceWhale), Home Assistant Green/Yellow (Nabu Casa), Start9 (Server One/Pure), Framework and System76 source hardware: own design vs ODM rebadge, which ODMs, which certifications appear in their FCC IDs/manuals, and what MOQs did they publicly disclose?  
*Why:* H-2 requires knowing competitors' boxes; copy-the-proven-pattern rule from ADR-001 applies to hardware too.  
*Method:* FCC ID database lookups (fccid.io), teardowns, Kickstarter/Indiegogo campaign updates (ZimaCube, Olares One), product manuals, import records (ImportYeti/Panjiva bills of lading), founders' interviews and blog posts.

**Q172 [P0]** What are the revenue models and unit economics of Umbrel, Olares, Nabu Casa, Start9, IceWhale, Framework and System76 (hardware margin, subscription such as Home Assistant Cloud, app store revenue share, enterprise/OEM licensing, VC funding), and which have proven sustainable?  
*Why:* Validates the open-core + boxes + support/education model (Strategy section) and pricing for Lite/Pro/Omni; Nabu Casa's subscription-funded model vs Umbrel's hardware-plus-noncommercial license are opposite bets.  
*Method:* Public statements, Crunchbase/PitchBook funding, Nabu Casa's published Open Home Foundation reports, Framework/System76 interviews, Olares 'Manufacture with Olares' OEM program terms, Kickstarter backer totals.

**Q173 [P0]** What license and contributor policy best protects OneMind against a cloud/hardware competitor rebadging the Apache-2.0 core (the reason Umbrel chose PolyForm Noncommercial and Olares added a non-commercial clause)? Compare Apache-2.0 + trademark policy (HA model), AGPL-3.0, BSL/FSL with change date, and Apache core + proprietary 'Omni' modules; also DCO vs CLA.  
*Why:* D-001 (Apache-2.0) is a founder decision but RS-1 requires evidence; the license choice also affects CRA steward status, NVIDIA/OEM partnerships and enterprise adoption.  
*Method:* Read Umbrel and Olares LICENSE history in git (when and why they changed), HA/Open Home Foundation trademark policy, Sentry FSL rationale, HashiCorp/Elastic/Redis relicensing case studies, OSI positions; legal blog analyses.

**Q174 [P0]** Is 'OneMind' / 'OneMind OS' registrable as a trademark in the US (USPTO classes 9, 42, 38, 35) and EU (EUIPO) and UK given existing marks (e.g. OneMind brands in health/tech), and what is the conflict risk with onemindos.dev domains?  
*Why:* Trademark is the main moat under Apache-2.0; a conflict found after hardware packaging is printed is expensive.  
*Method:* USPTO TESS/Trademark Center search, EUIPO eSearch, WIPO Global Brand Database, UKIPO; clearance opinion from a trademark attorney; domain/WHOIS review.

**Q175 [P0]** What is the current and forecast price trajectory (2025-2027) for DDR5/LPDDR5X SODIMM and soldered memory, NVMe SSDs, and consumer/workstation GPUs (RTX 50-series, RTX PRO), given AI-driven HBM capacity shifts and DRAM contract price increases reported in 2025-2026?  
*Why:* BOM for Pro/Omni tiers is dominated by RAM/GPU; volatility dictates whether OneMind ships fixed-config SKUs, BYO-RAM barebones, or GPU-optional bundles.  
*Method:* TrendForce/DRAMeXchange contract price reports, Micron/SK hynix/Samsung earnings calls, PCPartPicker price history, distributor (Arrow, Mouser) pricing APIs.

**Q176 [P0]** What full landed BOM (board, RAM, SSD, case, PSU, packaging, certification amortisation, freight, duty, payment fees, warranty reserve) results for candidate SKUs: Lite (Pi 5 8/16GB or N150/N305 mini PC), Pro (Ryzen 7/8000-series or Intel Core Ultra mini PC, 32-64GB), Omni (Ryzen AI Max+ 395 128GB or RTX GPU box), Edge (Jetson Orin Nano/NX carrier), Robotics (Jetson AGX Orin/Thor)?  
*Why:* Pricing tiers (P-5, H-3) cannot be set without unit cost; drives the first SKU choice (Open Question 4).  
*Method:* Spreadsheet model from Alibaba/ODM quotes (Beelink, Minisforum, GMKtec, Topton, Seeed, Connect Tech, Auvidea), Raspberry Pi and NVIDIA Jetson distributor prices, HTS duty rates, Stripe/Shopify fees; validate against Umbrel Home and Olares One retail prices.

**Q177 [P0]** What US tariffs (Section 301 lists, IEEPA 'reciprocal' tariffs, Section 232 semiconductor actions as of late 2026) apply to mini PCs (HTS 8471.50/8471.41), single-board computers, carrier boards and Jetson modules depending on country of origin (China, Taiwan, Vietnam, Malaysia, Thailand, UK for Raspberry Pi), and what is the substantial-transformation rule if final assembly happens in the US or Mexico?  
*Why:* Tariffs can swing landed cost 10-145%; country-of-origin strategy determines ODM selection and whether 'assembled in USA' is viable for public-safety buyers.  
*Method:* USITC HTS database, Federal Register tariff notices, CBP rulings (CROSS) on computer assembly substantial transformation, customs broker consultation.

**Q178 [P0]** Which US export control classifications (EAR ECCNs such as 5A992/5D992 for encryption, 4A090/3A090 for advanced compute, 'AI diffusion' rule successors) apply to OneMind boxes and the OS image with encryption, and which apply to Jetson AGX Thor / RTX PRO boxes exported to non-US customers? Is License Exception ENC self-classification sufficient?  
*Why:* Selling sovereignty hardware internationally and shipping an encrypted OS requires correct classification; GPU boxes may hit compute thresholds affecting EU/LatAm/MENA sales.  
*Method:* BIS EAR Part 740.17, Supplement 1 to Part 774, BIS rules on advanced computing (Oct 2022, Oct 2023, Jan 2025 and any 2025-2026 revisions), NVIDIA product ECCN listings, export counsel.

**Q179 [P0]** What are NVIDIA Jetson module lifecycles (Orin Nano/NX/AGX EOL dates, Thor availability), pricing at volume, the Jetson Partner Ecosystem / Preferred Partner tiers, and the requirements to ship a custom carrier board with JetPack (BSP porting, NVIDIA design review, flashing tools licensing)?  
*Why:* Robotics is the moat (M-7); the L4T flavor in D2 locks OneMind to NVIDIA's lifecycle and BSP; need to know if a small company can get design-in support.  
*Method:* NVIDIA Jetson product lifecycle page, Jetson Partner program docs, carrier board design guides, interviews/forums with Connect Tech, Seeed, Auvidea, Forecr; NVIDIA developer forum on JetPack licensing.

**Q180 [P0]** Which ODMs (Beelink, Minisforum, GMKtec, AceMagic, Topton, Kontron, Advantech, OnLogic, Seeed, ASRock Industrial) offer white-label/custom-BIOS mini PCs with: custom logo/packaging, BIOS settings (Secure Boot keys, TPM, auto power-on), firmware update cooperation, coreboot/open firmware, MOQ <500, and documented component lifecycle (BOM lock)?  
*Why:* OEM path (H-4) and phase-2 Secure Boot/TPM (D6) need ODM firmware cooperation; consumer mini PC brands often change components silently, breaking an image-based OS.  
*Method:* RFQs via Alibaba and direct sales contacts, OnLogic/Advantech lifecycle policies, coreboot supported boards list, Star Labs/Protectli/System76 firmware approach as references.

**Q181 [P0]** Should Lite/Pro/Omni/Edge/Robotics be differentiated by hardware only, by software features (closed modules), by support/SLA, or by subscription (remote access relay, backups, AI credits)? What price points and attach rates do comparable products achieve (Umbrel Home ~$399, Olares One, HA Green ~$99 + HA Cloud $6.50/mo, Start9 Server One)?  
*Why:* P-5 tiers and open-core boundary must be defined before UX and licensing; avoids tier sprawl for a solo developer (M-6).  
*Method:* Competitor pricing pages (archived via Wayback Machine for history), Nabu Casa subscriber disclosures, Olares One crowdfunding tiers, survey of target segments (homestead, TAK/public safety, SMB).

**Q182 [P0]** For public-safety and government buyers (TAK users, state/local agencies), what procurement requirements apply: NDAA Section 889 component bans, TAA-compliant country of origin, FIPS 140-3 validated crypto, CJIS, StateRAMP/FedRAMP for any cloud component, and DIU Blue UAS list for drone components?  
*Why:* Public safety is a target segment and justifies RKE2 tier (D4); TAA/NDAA rules can exclude China-assembled mini PCs entirely, reshaping ODM choice.  
*Method:* FAR 52.204-25, TAA designated countries list, NIST CMVP for RKE2/BoringCrypto FIPS validation status, DIU Blue UAS framework, interviews with TAK vendors (e.g. PAR Government, Ultra/Persistent Systems).

**Q183 [P0]** Does RKE2's FIPS claim map to a currently valid FIPS 140-3 certificate (not just 140-2, which sunsets in 2026), and would a Debian 13-based OS image need its own validated crypto module (e.g. via Ubuntu Pro FIPS, SafeLogic, wolfSSL) to sell into federal/state public safety?  
*Why:* Challenges D2+D4: Debian has no FIPS-validated OpenSSL; Ubuntu Pro FIPS does. This could flip the base OS for the hardened tier.  
*Method:* NIST CMVP certificate search, SUSE RKE2 FIPS docs, Canonical FIPS docs, FIPS 140-2 sunset date (Sept 2026) confirmation.

**Q184 [P0]** What is the SBOM, vulnerability disclosure and coordinated-update tooling and process cost required to meet CRA Art. 14 (24h early warning to ENISA single reporting platform) and US expectations (CISA SBOM minimum elements), and which existing tools (Debian security tracker feeds, Rugix/RAUC metadata, Syft/Grype, OpenVEX) cover a Debian+k3s+app-store stack?  
*Why:* CRA reporting has applied since 2026-09-11; even pre-revenue releases may be in scope; process must exist before first sale.  
*Method:* CRA Art. 14 and ENISA SRP documentation, CISA SBOM guidance, tool evaluation (hands-on Syft/Grype/Trivy on a built image), review how Yocto/Debian generate SPDX.

**Q185 [P0]** Which Apache-2.0-incompatible or problematic licenses exist in the intended stack and app catalog (NVIDIA proprietary drivers/CUDA EULA redistribution terms, JetPack/L4T license for redistributing images, Rugix/RAUC LGPL, Raspberry Pi firmware blobs, Umbrel PolyForm app manifests, Olares AGPL components), and can OneMind legally redistribute a prebuilt image containing them?  
*Why:* Shipping an image (D1) is redistribution; NVIDIA driver/L4T redistribution terms and reuse of competitor catalogs (A-3) could block the plan.  
*Method:* Read NVIDIA Software License Agreement and Jetson Linux license, CUDA EULA Attachment A redistributables, Raspberry Pi firmware license, SPDX scan of a candidate image with ScanCode/FOSSology, Umbrel apps repo license.

**Q186 [P0]** Should the first commercial SKU be an embedded-longevity platform (AMD Ryzen Embedded, Intel IoT-line SKUs with 10-yr availability, Pi CM5 industrial) rather than consumer mini PCs, given CRA support periods and image-based OS needing stable hardware?  
*Why:* Challenges implicit plan of rebadging Beelink-class consumer boxes; component churn breaks signed images and inflates support cost.  
*Method:* Compare lifecycle guarantees and price premiums from OnLogic, ASRock Industrial, Kontron vs consumer ODMs; total cost model over 5 years including RMAs and image validation.

**Q187 [P0]** What is the market size and willingness to pay for each target segment (homestead/off-grid, privacy families, TAK/public safety, SMB, EU sovereignty buyers, robotics developers), and which segment gives the fastest path to first 100 paying hardware customers?  
*Why:* Open Question 4 (first hardware tier and segment) blocks SKU and BOM decisions; prevents building all tiers at once (D-002 risk for a solo dev).  
*Method:* Umbrel/HA community size and sales signals (Reddit, Discord, GitHub stars, Kickstarter results), TAK user base data (tak.gov stats), homestead market reports, structured interviews with 20+ prospects.

**Q188 [P1]** What are Raspberry Pi's long-term availability commitments for Pi 5 and CM5 (stated 'in production until at least' dates), allocation behavior during shortages, and terms of the Raspberry Pi Approved Design Partner / Powered by Raspberry Pi programs for a commercial appliance vendor?  
*Why:* Lite tier and OS profiles (P-8) on Pi depend on supply; 2021-2023 shortages prioritized industrial customers, which OneMind may or may not qualify as.  
*Method:* Raspberry Pi product obsolescence statements, Raspberry Pi Trading annual reports/IPO prospectus (2024 LSE listing), Design Partner program pages, interviews with Umbrel/HA on Pi supply.

**Q189 [P1]** What does NVIDIA Inception actually provide (cloud credits, hardware discounts, DGX/Jetson dev kit pricing, go-to-market), what are eligibility requirements (incorporation, website, employees), and what is the path from Inception to NVIDIA Partner Network (NPN) OEM/Solution Provider and to being an 'NVIDIA-Certified System' vendor?  
*Why:* D-006 assumes Inception; N-8 envisions NVIDIA-customized machines; must know what NVIDIA will and won't grant a startup and the obligations (e.g. certified system testing).  
*Method:* NVIDIA Inception FAQ and terms, NPN program guide, NVIDIA-Certified Systems program docs and test suite, interviews with Inception alumni.

**Q190 [P1]** Is there a credible non-NVIDIA accelerator path for the Edge/Robotics tiers (AMD Ryzen AI / Strix Halo with ROCm, Intel Arc/NPU with OpenVINO, Hailo-8/10 on Pi, Rockchip RK3588 NPU, Qualcomm RB3/RB5 robotics) with acceptable supply, Linux support and pricing?  
*Why:* Conversation flagged NVIDIA lock-in as opposite of sovereignty; D2's L4T flavor assumes Jetson is the only robotics target. A second accelerator vendor hedges export controls and price shocks.  
*Method:* Vendor Linux driver upstreaming status (kernel.org, Mesa, ROCm support matrices), ROS 2 hardware support lists, Hailo/Qualcomm developer program terms, benchmark hardware tests on candidate boards.

**Q191 [P1]** What warranty, RMA and support cost per unit should be budgeted (failure rates for mini PCs/SBCs/SSDs, return rates for consumer electronics DTC, cost of advance replacement), and what legal minimums apply (EU 2-year legal guarantee, Magnuson-Moss in US, UK Consumer Rights Act)?  
*Why:* R-2/R-3 support system and pricing must include warranty reserve; small hardware startups often fail on RMA logistics.  
*Method:* Backblaze drive stats, Puget Systems reliability reports, SquareTrade data, Framework/System76 public warranty terms, EU Directive 2019/771, 3PL quotes for returns handling.

**Q192 [P1]** What fulfillment and distribution model fits (DTC via own store with 3PL, Amazon, distributors like Arrow/Mouser for Pi/Jetson-based kits, regional resellers in EU), and what are the costs for EU VAT OSS/IOSS, EPR (packaging, WEEE, batteries) per country, and authorised representative requirements?  
*Why:* W-4 cart and H-1 distributor ambition require EU logistics; EPR registrations are per-country and block marketplace listings if missing.  
*Method:* EU OSS/IOSS rules, EPR requirements in DE/FR/ES/IT, Amazon EPR enforcement docs, 3PL quotes (ShipBob, Floship), interview HA Green/Start9 on distribution.

**Q193 [P1]** What are FCC Part 15 / RED and aviation (FAA Part 107, Remote ID, EU U-space/EASA C-class) obligations if OneMind sells or bundles drones or drone ground-station kits, and what does the 2024-2025 US actions on DJI/Chinese drones (NDAA FY2025 Section 162, FCC Covered List) mean for supported hardware?  
*Why:* Drones are part of the moat; bundling or certifying drone hardware changes regulatory exposure and supported-hardware strategy.  
*Method:* FAA Remote ID rules, EASA drone class regulations, FCC Covered List updates, NDAA text, Blue UAS cleared list.

**Q194 [P1]** What product-liability, safety and machinery regulations apply when OneMind software controls physical robots/actuators (EU Machinery Regulation 2023/1230 applicable 2027-01-20, AI Act high-risk categories, new EU Product Liability Directive 2024/2853 covering software), and what insurance is needed?  
*Why:* AI agents operating hardware (AI-4, MHS) creates liability for the software vendor; affects how the AI capability layer and HITL (AI-5) must be designed and documented.  
*Method:* EU Machinery Regulation, AI Act Annex I/III, PLD 2024/2853 transposition timeline, insurer quotes for tech E&O/product liability, ISO 10218/ISO 13482 relevance.

**Q195 [P1]** Is the app store (Market) itself a CRA-relevant distribution channel, and what liability does OneMind take for third-party apps (community and repackaged OSS apps) it distributes, compared to how Umbrel, Olares Market and HA add-ons handle it?  
*Why:* A-1/A-6 hundreds of apps; if OneMind is 'importer/distributor' or 'manufacturer' of repackaged apps, obligations multiply.  
*Method:* CRA definitions (manufacturer, distributor, substantial modification), Commission CRA FAQ, Umbrel/Olares app store terms of service, legal opinion.

**Q196 [P1]** Can OneMind legally reuse or derive from Umbrel's app store manifests and Olares Market charts (A-3) given PolyForm Noncommercial and AGPL/non-commercial clauses, versus re-packaging from upstream projects directly?  
*Why:* App catalog breadth is a core goal; copying the wrong artifacts creates IP exposure for a commercial product.  
*Method:* Read licenses in getumbrel/umbrel-apps and beclab/apps repos (git history), compare to upstream app licenses, legal review.

**Q197 [P1]** What incorporation, entity and jurisdiction structure best fits (US Delaware C-corp vs LLC, EU subsidiary for CRA authorised representative and sovereignty marketing, foundation for the open-source core like Open Home Foundation), and what is required for NVIDIA Inception, grants (EU Horizon/NGI, US SBIR/AFWERX for public safety/defense) and hardware sales?  
*Why:* D-006 needs incorporation; sovereignty positioning in Europe may favor an EU entity; a foundation protects community trust long-term (5-10y).  
*Method:* NVIDIA Inception eligibility, NGI Zero/NLnet funding terms, SBIR/STTR and AFWERX solicitations, Open Home Foundation structure documents, startup counsel.

**Q198 [P1]** How much does geopolitical risk (Taiwan contingency, China rare-earth/gallium export limits, US-China chip restrictions, EU Chips Act) threaten each candidate supply chain, and what dual-sourcing/assembly-location strategy (Taiwan, Vietnam, Mexico, EU, US) is realistic at low volume?  
*Why:* Mission is sovereignty and longevity 'given world events'; a single-country supply chain contradicts the brand and is a business continuity risk.  
*Method:* CSIS/Rhodium/SIA reports, US Commerce and MOFCOM export control notices, EMS provider quotes in Mexico/Vietnam/EU (e.g. Kimball, Jabil small-batch, European EMS).

**Q199 [P1]** What does the OEM/'Manufacture with Olares' and Umbrel's hardware partnerships offer third parties (licensing fees, branding, image customization), and should OneMind offer an OEM program for robotics/drone makers to preinstall OneMind (H-4) from year 2-3?  
*Why:* OEM licensing may be a higher-margin revenue stream than own hardware and fits robotics moat; requires image customization and signing-key design decided now (D3 signing).  
*Method:* Olares OEM program pages and contracts if available, HA 'Works with Home Assistant' program terms, Balena/Mender/Foundries.io OEM pricing as reference.

**Q200 [P1]** How should signing keys, secure-boot fuse keys and update infrastructure be governed for sold hardware (HSM, key escrow, multi-person approval, what happens to devices if the company fails), and what commitments (e.g. unlockable bootloader, published keys on bankruptcy, escrow) do sovereignty customers expect?  
*Why:* Phase-2 Jetson/Pi fusing is irreversible; vendor failure would brick or orphan boxes, contradicting the sovereignty promise and CRA end-of-support obligations.  
*Method:* Review Umbrel signing docs, Purism/System76/Start9 policies, software escrow providers, CRA end-of-support obligations, cases like Insteon/Revolv shutdowns.

**Q201 [P1]** What remote access/relay, backup storage and AI-credit services (Tailscale-like, OneMind cloud later per M-1) could be offered as subscriptions, and what are their per-user infrastructure costs on DigitalOcean versus competitors (HA Cloud, Umbrel's lack thereof, Olares Space)?  
*Why:* Recurring revenue funds support (R-2) and CRA maintenance over the 5-10 year support period; hardware-only margins rarely do.  
*Method:* Nabu Casa pricing and economics statements, Olares Space pricing, Tailscale/headscale cost modeling, DO bandwidth/storage pricing.

**Q202 [P2]** What funding/credits and partner programs (DigitalOcean Hatch, AWS Activate, Google for Startups, NLnet, Sovereign Tech Fund/Agency, Raspberry Pi partner, SUSE/Rancher partner, Canonical partner) could subsidize CI image builds, hardware test labs and certification?  
*Why:* Solo founder with limited cash; image build farms for multiple architectures and hardware test benches are costly.  
*Method:* Program terms pages, application requirements, alumni outcomes.

**Q203 [P2]** What do the 2025-2026 supply-chain signals (TSMC capacity, Intel N-series and AMD Ryzen embedded roadmaps with 7-10 year availability, Raspberry Pi RP-series, Arm Neoverse/RISC-V SBCs) imply for a 5-10 year hardware roadmap, and when is RISC-V (e.g. SiFive, SpacemiT, Milk-V) viable for a Lite/Edge SKU?  
*Why:* 5-10 year plan and 'last given world events' requires hedging x86/Arm/RISC-V; embedded SKUs offer longer availability than consumer mini PCs.  
*Method:* AMD Embedded/Intel IoT longevity program pages, Debian RISC-V official port status (trixie), RISC-V International roadmaps, hardware tests on a RISC-V SBC.

**Q204 [P2]** How do Framework (repairability, marketplace, mainboard reuse) and System76 (own firmware, Pop!_OS/COSMIC, Thelio made in Colorado) structure hardware longevity, open firmware and US manufacturing, and what of that is transferable to a sovereign appliance brand?  
*Why:* Repairability and US/EU assembly are differentiators for sovereignty and public-safety buyers; also EU right-to-repair/Ecodesign rules.  
*Method:* System76 open-firmware repos and Thelio manufacturing posts, Framework marketplace and repair docs, EU Ecodesign/Right to Repair Directive 2024/1799.

**Q205 [P2]** What 5-10 year product-line evolution do comparable companies show (HA Blue -> Yellow -> Green -> Voice; Umbrel Home -> Pro; Olares One; ZimaBoard -> ZimaCube), including how often they refreshed SKUs and supported old ones with OS updates?  
*Why:* Informs SKU cadence and how many hardware generations one image pipeline must support simultaneously (R-3).  
*Method:* Product announcement history, HA OS supported boards list over time, Umbrel release notes, Zima product pages, Wayback Machine.

## Security, sovereignty & world context 2026-2036 (supply chain, boot trust, zero trust, sovereignty policy, geopolitics, off-grid resilience, public-safety compliance, privacy law, long-term threat landscape)

**Q206 [P0]** For each candidate base (Debian 13 + Rugix, Buildroot + RAUC as in HAOS, Yocto/Poky, Fedora IoT/CoreOS bootc, Flatcar, Talos, Kairos, Ubuntu Core), what does the full end-to-end chain of trust look like from firmware to running container? Is it signed boot, then a verified/read-only root (dm-verity or EROFS with fs-verity), then signed update bundles, then signed container images verified at admission? Where does each one break today?  
*Why:* ADR-001 picks Debian 13 + Rugix but puts Secure Boot/TPM in Phase 2. If retrofitting measured boot or dm-verity onto a Rugix/Debian image needs a different partition layout or bootloader, the foundation choice has to change now, not later.  
*Method:* Read primary docs and source: Rugix (rugix.org, GitHub rugix/rugix boot-flows and bundle signing), RAUC verity bundles, systemd-boot/UKI + systemd-measure, Fedora bootc, Talos and Kairos Trusted Boot docs. Build a matrix and confirm on the Dell 5540 by building a UKI-booted Rugix image with dm-verity root.

**Q207 [P0]** Can Rugix (the version Umbrel uses) boot a Unified Kernel Image under UEFI Secure Boot with a OneMind-owned db key and PCR-sealed LUKS (systemd-cryptenroll TPM2 PCR 7+11) while keeping A/B rollback? What happens to the sealed key after an A/B switch: does it need re-sealing or a signed PCR policy (systemd-pcrlock / signed PCR 11 policy)?  
*Why:* If A/B slot switching invalidates TPM-sealed disk keys, either users get locked out after every update or the encryption is weak. This decides whether Rugix stays the updater.  
*Method:* Reverse-engineer Rugix's bootloader integration (grub/tryboot/systemd-boot backends) in source. Hardware test on the Dell 5540 (TPM 2.0) with systemd 257+ in Debian 13: update, force-fail, roll back, and confirm unattended unlock in every state.

**Q208 [P0]** What does Raspberry Pi 5 secure boot actually provide (RP1/BCM2712 OTP key, signed boot.img, rpi-eeprom signing, revoke/lock options), and is it compatible with Rugix's tryboot A/B flow and an encrypted data partition when there is no TPM? Which of these steps are irreversible?  
*Why:* Pi 5 is the Lite tier and a field/sensor node. With no TPM, disk-encryption key custody on Pi is unsolved, and the OTP fusing is permanent. This affects what can be promised for sold Pi devices.  
*Method:* Primary sources: raspberrypi/usbboot secure-boot-recovery5 docs, rpi-eeprom release notes, Raspberry Pi secure-boot whitepaper. Test on a sacrificial Pi 5 with fusing done only at the end. Check how Umbrel handles Pi encryption (likely none) by inspecting its image.

**Q209 [P0]** On Jetson Orin/Thor (JetPack 6/7), what does the fuse-based secure boot + OP-TEE + disk-encryption + A/B (UEFI capsule, rootfs A/B, nvbootctrl) stack provide? Can OneMind keep its own keys rather than NVIDIA's? How do NVIDIA's OTA tools interact with any third-party A/B updater (Rugix, RAUC, Mender, Kairos)?  
*Why:* Robotics is the moat, and the Jetson flavor has an unresolved A/B method (ADR open item). If NVIDIA's chain demands its own updater, the dual-flavor plan needs one unified update and signing service.  
*Method:* NVIDIA Jetson Linux Developer Guide (Security, Secure Boot, Disk Encryption, OTA/Image-based update sections); meta-tegra and Mender/RAUC Jetson integration repos; test on an Orin Nano dev kit with non-fused keys first.

**Q210 [P0]** Which signing and transparency stack should OneMind build into its release pipeline: Sigstore (cosign keyless vs KMS/HSM keys, Rekor), TUF (go-tuf / RSTUF), in-toto attestations, SLSA L3 provenance? Can the offline device verify all of it with no internet (bundled TUF root, offline Rekor proofs/bundles)?  
*Why:* Devices live off-grid. Keyless Sigstore assumes reachable Fulcio/Rekor. Air-gap verification needs to be designed into the update format from day one.  
*Method:* Read the Sigstore bundle spec, cosign offline verification docs, the TUF spec (and Uptane for vehicles/robots), and SLSA v1.x. Prototype cosign verify-blob --bundle offline on a k3s node, and check how Talos/Flatcar/Bottlerocket ship TUF roots.

**Q211 [P0]** How do Debian's reproducible-builds status, snapshot.debian.org pinning, and debsig/apt signing compare with Yocto/Buildroot reproducibility and Fedora/bootc for producing a bit-for-bit reproducible, auditable OneMind image with a complete SBOM (SPDX/CycloneDX) per release?  
*Why:* CRA and public-safety buyers will ask for SBOMs and reproducibility. If Debian-based images can't be reproduced, that's an argument for Yocto/Buildroot.  
*Method:* reproduce.debian.net trixie statistics, Yocto SPDX 3.0 output docs, mkosi reproducibility docs. Build the same Rugix image twice and diffoscope it.

**Q212 [P0]** What are the EU Cyber Resilience Act's concrete obligations for OneMind across three roles: an Apache-2.0 open-source steward, a manufacturer of sold boxes, and an importer of third-party apps from the app store? Which product class applies (default, important class I/II; routers, smart-home hubs, OS?), what conformity route (self-assessment vs notified body), what support-period minimum, and what is the 24h/72h vulnerability reporting flow?  
*Why:* 'Operating systems' are listed as Important Class I products under the CRA. Selling OneMind boxes in the EU after 2027-12-11 may require harmonised-standard compliance or third-party assessment, which shapes release engineering now.  
*Method:* Regulation (EU) 2024/2847 Annex III/IV text, Commission implementing acts on product categories, ENISA single reporting platform docs, CEN/CENELEC harmonised standards drafts, OpenSSF/Eclipse ORC CRA guidance for stewards.

**Q213 [P0]** Which Debian 13, k3s/RKE2, Rugix and NVIDIA component lifecycles can OneMind actually match against the support period it must declare for sold hardware (CRA's at least 5 years; buyers expect 7–10)? What does Freexian ELTS cost to cover 2030–2035, and what is SUSE's k3s/RKE2 support lifecycle?  
*Why:* R-3 requires long-term maintainability. The ADR's open item on SUSE k3s lifecycle and Ubuntu Pro for Devices pricing directly determines total cost and declared support periods.  
*Method:* Debian LTS/ELTS pages and Freexian quotes, SUSE Rancher support matrix and lifecycle pages, the NVIDIA JetPack lifecycle page, Canonical Pro for Devices (ask sales for a quote). Build a lifecycle Gantt chart for 2026–2036.

**Q214 [P0]** How exposed is each base choice to a single-vendor or single-jurisdiction kill switch? Examples: NVIDIA L4T licensing and export terms, Canonical, SUSE (k3s/RKE2/Longhorn ownership), Raspberry Pi Ltd firmware blobs, GitHub/Docker Hub hosting. What is the fork-and-continue plan for each, with the Huawei→HarmonyOS lesson (losing GMS overnight in 2019) as the reference case?  
*Why:* Sovereignty is the brand promise. Each dependency needs a documented exit path before the foundation is approved.  
*Method:* Review licenses (NVIDIA Jetson Software License, L4T EULA, Raspberry Pi firmware licence, k3s Apache-2.0 + SUSE trademark policy), the CNCF governance status of k3s, and a historical case study of Huawei's Entity List listing (BIS Federal Register 2019-05-21) and the HarmonyOS response.

**Q215 [P0]** Is there any FIPS 140-3 validated cryptographic module that OneMind can legally ship on a Debian 13 base, or does a FIPS/CJIS/FedRAMP-capable tier force Ubuntu Pro FIPS, RHEL, SLE Micro, or Chainguard/Wolfi FIPS images? Does that overturn 'Debian for every tier'?  
*Why:* This directly challenges D2. A hardened public-safety tier might need a different base OS than the consumer tier.  
*Method:* NIST CMVP search (module vendor + OE = Debian), the OpenSSL 3.x FIPS provider certificate and its operational-environment caveats, the SUSE/Canonical/Red Hat FIPS pages, and the RKE2 FIPS go-boringcrypto docs.

**Q216 [P0]** What zero-trust architecture should OneMind standardize across a single box, family mesh, and multi-site clusters: SPIFFE/SPIRE workload identity, mTLS service mesh (Linkerd/Cilium/Istio ambient) vs WireGuard (Tailscale/Headscale/NetBird/Nebula), the Authentik IdP with passkeys, and per-agent capability tokens for the MCP layer? Which components still work fully offline?  
*Why:* AI-1/AI-3 give agents permissioned access to everything. Without a workload and agent identity model, the AI capability layer becomes the main attack surface.  
*Method:* NIST SP 800-207/207A, SPIFFE spec, Headscale/NetBird/Nebula self-hosting docs, and the MCP 2026-07-28 authorization spec (OAuth 2.1, resource indicators). Prototype offline enrollment of a new node with SPIRE + k3s.

**Q217 [P0]** What is the threat model for an AI-native OS where an agent can install apps, read all data and drive robots (prompt injection via app data, tool poisoning in MCP servers, confused-deputy, data exfiltration through external models, malicious community plugins)? What do OWASP LLM Top 10 / Agentic Top 10, MITRE ATLAS and the MCP security best practices prescribe as OS-level mitigations (sandboxing, egress policy, human-in-the-loop for physical actuation)?  
*Why:* This is unique to OneMind and not covered by HAOS or Umbrel precedent. It decides kernel/LSM features (Landlock, seccomp, AppArmor, gVisor/Kata) that the base must support.  
*Method:* OWASP GenAI project docs, MITRE ATLAS, published MCP CVEs and tool-poisoning research (2025–2026), and the Anthropic MHS safety docs once available. Red-team the existing onemind-mcp server and Hermes agents in the DOKS cluster.

**Q218 [P0]** Is AppArmor (Debian default, HAOS) sufficient for per-app isolation of untrusted community apps, or should OneMind require SELinux (RKE2's model), gVisor or Kata microVMs for third-party apps? What does each cost on a Pi 5 and an 8 GB Beelink?  
*Why:* The app store will host hundreds of community apps (A-1/A-6). The isolation boundary decides the base's LSM and kernel config, and SELinux on Debian is weakly maintained.  
*Method:* k3s/RKE2 SELinux docs, Debian SELinux policy status, gVisor/Kata ARM64 support docs, benchmarks on Pi 5 and Beelink U55 (memory and startup overhead per pod), and a container-escape CVE review from 2023–2026.

**Q219 [P0]** What does internet-shutdown and off-grid resilience require of the base OS? Consider fully offline install and update (sideloaded signed bundles via USB), local OCI registry mirroring, local NTP/GPS time and certificate validity without network time, offline license and identity, and DNS without upstream. What do Access Now #KeepItOn data and real events (Iran 2025, Myanmar, Ukraine, the 2025 Iberian blackout, Hurricane Helene) say the device must survive?  
*Why:* Homestead/off-grid is a core segment. Many 'secure' designs fail offline (expired certs, OCSP, Rekor, ACME). Offline must be a tested mode, not an assumption.  
*Method:* Access Now #KeepItOn reports, after-action reports from the Helene/Iberia outages, k3s air-gap install docs, Zarf (Defense Unicorns) air-gap packaging, and Rugix offline bundle install. Test: a 30-day no-internet soak on the Beelink with a GPS/PPS time source.

**Q220 [P0]** How does the founder's existing DOKS cluster (Argo CD, Authentik, Tailscale, NATS, Backstage, CloudTAK) score today against the proposed edge security baseline (CIS k8s benchmark, Pod Security Admission, network policies, secrets encryption, image signing/admission, audit logs)? Which gaps carry into the OneMind image as the 'proven concept'?  
*Why:* The cluster is cited as proof of concept. If its security posture is weak, copying its Helm/Argo patterns into the image copies its weaknesses.  
*Method:* Read-only inspection via the onemind-kubernetes and onemind-backstage MCP tools (namespaces, PSA labels, NetworkPolicies, RBAC). Run kube-bench, Trivy k8s and Kubescape against the cluster (read-only). Compare with the RKE2 CIS profile.

**Q221 [P0]** How does OneMind handle CVE response at fleet scale while never auto-updating (R-1)? What is the policy for exploited-in-the-wild vulnerabilities (CRA 24h reporting, CISA KEV), how are users notified offline, are 'security-only' channels or live kernel patching (kpatch/livepatch on Debian) needed, and what do HAOS and Umbrel actually do in an emergency?  
*Why:* 'Never auto-update' conflicts with CRA duties and real-world botnet speed. The update policy needs an emergency path decided now.  
*Method:* HAOS and Umbrel release histories and security advisories (GitHub), CRA Art. 14, Debian DSA cadence for trixie, kpatch availability on Debian, and the Synology/QNAP emergency-update precedents.

**Q222 [P0]** How should hardware security modules and key ceremonies be run for a one-person company that will sign OS images, app bundles and device certificates for 10 years? Compare YubiHSM 2, Nitrokey HSM, cloud KMS, and a Sigstore/TUF threshold-signing setup. What is the bus-factor and succession plan if the founder's keys are lost or he is compelled to sign?  
*Why:* M-6 says there is a sole developer. A single compromised or lost root key ends the platform's integrity. Key ceremonies and threshold signing should be designed before the first signed release.  
*Method:* TUF root key rotation spec, Sigstore root signing ceremony docs, the Debian/Tor/Tails key-management practices, YubiHSM/Nitrokey docs, and Rugix/RAUC multi-key and revocation support in source.

**Q223 [P1]** Is Uptane (the automotive TUF profile with director + image repos and primary/secondary ECUs) a better model than plain TUF for robots and drones whose sub-controllers (flight controller, motor MCUs, Jetson) all need signed updates?  
*Why:* Robots have multiple compute units. A single-image A/B updater does not cover PX4/ArduPilot flight controllers or MCU firmware. The update architecture should cover all of a node's firmware.  
*Method:* Uptane standard v2.x, the aktualizr/OTA Community Edition source, and PX4/ArduPilot secure-boot and signed-firmware docs (ArduPilot secure bootloader). Reverse-engineer how DJI and Skydio describe their signed firmware chains.

**Q224 [P1]** How do US export controls (EAR ECCN 5A002/5D002 for encryption, 3A090/4A090 for advanced compute and AI chips, the AI Diffusion Rule's status and replacements, and Jetson Thor/Orin classification) affect selling OneMind GPU and Jetson boxes and distributing the OS image with strong crypto worldwide?  
*Why:* H-1/H-3 plan to sell NVIDIA-based boxes internationally. ECCN classification and License Exception ENC/TSU filing are needed before the first shipment and the first public download.  
*Method:* BIS EAR text (Parts 734.3(b)(3), 740.13(e), 740.17, 742.15), NVIDIA product ECCN listings, current BIS rules on AI chips as of 2026, and TSU notification procedure for open-source crypto.

**Q225 [P1]** What is the realistic 2026–2036 risk to Pi 5, Intel/AMD mini PCs, and Jetson supply from a Taiwan contingency, tariffs, or a China rare-earth/gallium export ban? Which alternative SoCs (Rockchip RK3588, NXP i.MX 9, MediaTek Genio, RISC-V such as SiFive/SpacemiT/Milk-V, Qualcomm IQ9) should the OS support so it stays portable?  
*Why:* A foundation tied to TSMC-only silicon and one Pi supplier is a single point of failure. Portability to non-TSMC or non-Chinese silicon is a strategic requirement for '5–10 years to last'.  
*Method:* Foundry data for each SoC (TSMC/Samsung/SMIC/Intel), CSIS/RAND Taiwan-contingency reports, the US CHIPS Act fab timelines, and China MOFCOM export-control notices. Test Debian 13 + k3s boot on an RK3588 board and check upstream kernel support status.

**Q226 [P1]** What do the EU digital-sovereignty programs (EuroStack, Gaia-X, IPCEI-CIS, the Sovereign Tech Fund/Agency, the EU Cloud Sovereignty Framework, the openDesk/ZenDiS stack in Germany, the Schleswig-Holstein Linux migration, the Danish and French public-sector moves off Microsoft) actually procure, fund or certify? Could OneMind qualify as a supplier or grantee?  
*Why:* The conversation names European governments as a market. Knowing the procurement criteria (open-source licence, EU hosting, certification such as BSI C5 or SecNumCloud) shapes the licence, hosting and certification roadmap.  
*Method:* Official EU Commission and member-state documents, the EuroStack report (2025), Gaia-X Trust Framework, ZenDiS openDesk docs, the Sovereign Tech Agency funding calls, and procurement tenders on TED.

**Q227 [P1]** Which data-localization and sovereignty laws (GDPR Chapter V transfers, the EU Data Act's device-data access and switching rules from Sept 2025, China PIPL, India DPDP Act, Russia 242-FZ, US state laws, the CLOUD Act) impose obligations on a local-first box that optionally syncs to a OneMind cloud or relay? Does the EU Data Act make OneMind a 'data holder' for connected-device data?  
*Why:* M-1 says a OneMind cloud option comes later. The EU Data Act applies to connected products sold from 2025–2026 and requires user data-access by design, which fits local-first well but needs to be designed in.  
*Method:* Primary regulation texts (EUR-Lex 2023/2854 Data Act Art. 3–5), EDPB guidance, and legal-analysis summaries from major firms. Map each obligation to a product feature.

**Q228 [P1]** For kids' and family accounts (U-1/U-2/U-3), what do COPPA (as amended in 2025, effective 2026), GDPR Art. 8, the UK Age Appropriate Design Code, the EU DSA minors guidance, and US state age-verification/app-store accountability laws (Utah, Texas, Louisiana, California AB 1043) require of an OS or app store that hosts child profiles and parental controls? Does a self-hosted OS with no OneMind backend still count as an 'operator' or 'app store'?  
*Why:* Parental controls and kids' education are explicit requirements, and the 2025–2026 OS/app-store age-signal laws target operating systems directly.  
*Method:* FTC COPPA Rule final amendments (Federal Register 2025), the text of California AB 1043 (Digital Age Assurance Act) and the Utah/Texas App Store Accountability Acts, ICO AADC code. Compare how Apple/Google/Umbrel handle age signals.

**Q229 [P1]** What exactly does CJIS Security Policy v6.x require (MFA, FIPS 140-validated encryption in transit and at rest, audit logging, personnel screening, the 'agency-controlled' boundary) for an on-prem/edge box that stores or brokers CJI or TAK data for a police or fire agency? Which of these can a self-installed OneMind RKE2 node meet, and which need an organizational process?  
*Why:* Public safety is a target segment, and RKE2 is chosen for the 'hardened tier'. CJIS decides whether that tier needs FIPS-validated crypto modules across the whole image, not just RKE2.  
*Method:* FBI CJIS Security Policy (latest version, 2024–2026 modernization), the CJIS Requirements Companion Document, the RKE2 FIPS docs, and the CMVP validated modules list (e.g. Debian/Ubuntu FIPS modules, BoringCrypto, AWS-LC, OpenSSL 3 FIPS provider certificates).

**Q230 [P1]** What do FedRAMP 20x (or Rev5 Moderate/High), the DoD Iron Bank / Platform One hardened-container requirements, DISA STIGs (RKE2 STIG, Ubuntu/RHEL STIGs; is there a Debian STIG?) and NIST SP 800-53/800-171 imply for selling OneMind to government or the defense industrial base? Is there a realistic path (e.g. Iron Bank image submission, a STIG-able profile) in 1–3 years?  
*Why:* Edge and TAK customers in government will ask for STIG and Iron Bank provenance. Debian has no official DISA STIG, which may again push the hardened tier off Debian.  
*Method:* DISA STIG library (public.cyber.mil), the RKE2 STIG, the Iron Bank onboarding guide (repo1.dso.mil), FedRAMP 20x pilot docs, and NIST 800-171r3.

**Q231 [P1]** What are the TAK ecosystem's formal security requirements for third-party servers and clients: the TAK Product Center certificate and enrollment model, the CoT/Protobuf over TLS 8089 data-channel requirements, TAK Server STIG/hardening guides, FirstNet Certified app/device requirements, and ATAK plugin signing? Can a OneMind box legally redistribute TAK Server (DoD/TPC licence) inside an image?  
*Why:* TAK is a core differentiator (situational awareness profile P-8). Licence and distribution limits on TAK Server and FirstNet certification affect whether it's preinstalled or user-supplied.  
*Method:* tak.gov licensing and documentation, the TAK Server configuration guide (security sections), the open-source TAK Server GitHub (TAK-Product-Center/Server) licence, FirstNet Certified program requirements (firstnet.com developer docs), and the CloudTAK repo licence.

**Q232 [P1]** What does the long-term threat landscape for home and edge Linux devices look like in 2026–2036: botnets (Mirai successors, Raptor Train, Volt/Flax Typhoon router and NAS campaigns), ransomware on NAS (QNAP/Synology/Asustor), supply-chain backdoors (the xz-utils CVE-2024-3094 pattern), firmware implants (LogoFAIL, BlackLotus, PKfail)? Which of these would have hit a Debian + Rugix + k3s box with default settings?  
*Why:* This grounds security priorities in real attacks and tests whether the proposed baseline (read-only root, no SSH password, signed updates) would actually have stopped them.  
*Method:* CISA KEV catalog, FBI/CISA advisories on Volt Typhoon and Flax Typhoon, Binarly PKfail/LogoFAIL reports, the xz-utils post-mortems, and Synology/QNAP security advisories. Map each to an attack path on the proposed stack.

**Q233 [P1]** How do PKfail-style test Platform Keys, the Microsoft UEFI CA 2011 expiry in 2026 (with rotation to the 2023 CA and shim/SBAT revocations) and DBX update failures affect Secure Boot on the cheap mini PCs (Beelink, Minisforum, GMKtec) OneMind would sell or support? Should OneMind enroll its own PK/KEK on boxes it sells instead of relying on shim?  
*Why:* x86 Secure Boot is in Phase 2. The 2026 certificate rotation is happening now, and cheap OEM firmware is often broken, which affects hardware vendor selection.  
*Method:* Microsoft KB on the Secure Boot certificate rotation (2026 expiry), the Binarly PKfail database (check specific Beelink/Minisforum models), shim SBAT docs, and a Beelink U55/Dell 5540 firmware test using sbctl to enroll custom keys.

**Q234 [P1]** What does right-to-repair law (EU Ecodesign/ESPR and the Right to Repair Directive 2024/1799, the EU battery regulation's replaceable-battery rules from 2027, US state laws in NY, CA, MN, OR and CO including parts-pairing bans) require of OneMind's hardware and of fused secure boot? Does irreversible fusing conflict with an owner's right to install their own OS?  
*Why:* Sovereignty means users own their devices. Fusing Pi/Jetson keys could contradict the brand and possibly Oregon's parts-pairing law. A user-owned key enrollment model may be required.  
*Method:* Text of Directive (EU) 2024/1799, ESPR delegated acts for servers and smartphones, Oregon SB 1596 and Minnesota's Digital Fair Repair Act, and the iFixit/Repair.org trackers. Compare with Framework, Pixel (relockable bootloader with custom keys) and GrapheneOS models.

**Q235 [P1]** Can OneMind offer an owner-controlled key model like Pixel's AVB custom root of trust, in which the owner (not OneMind) can take over the signing keys of a purchased box, for x86 (custom PK), Pi 5 (customer-burned OTP) and Jetson (fuse with customer PKC)? What should the default and 'sovereign mode' key-custody options be, including a recovery kit?  
*Why:* This resolves the tension between secure boot and sovereignty. It decides manufacturing-line provisioning and the recovery-kit design (ADR D5 item 3).  
*Method:* Android Verified Boot docs (avb_custom_key), GrapheneOS install docs, the Purism PureBoot/Heads model, System Transparency, and the Pi/Jetson provisioning docs. Design and test a take-ownership flow on the Dell 5540.

**Q236 [P1]** Should OneMind ship Meshtastic, Reticulum/RNS (LXMF, Sideband, Nomad Network), MeshCore or LoRaWAN (ChirpStack) as the native mesh layer (N-6)? Compare security (Meshtastic's PKC since 2.5 and past key-reuse issues, Reticulum's crypto design), throughput, licensing (GPL-3 and Reticulum's licence terms), TAK integration (ATAK Meshtastic plugin) and legal limits (ISM duty cycle, no encryption on ham bands).  
*Why:* Mesh is a requirement and shapes kernel drivers, radio hardware SKUs and how the NATS subject doctrine is bridged over low-bandwidth links.  
*Method:* Meshtastic firmware and security docs and CVEs, the Reticulum manual and repo licence, the MeshCore repo, the ChirpStack docs, FCC Part 15/97 and ETSI EN 300 220 duty-cycle rules. Bench test: two Pi 5 + LoRa HATs bridging NATS messages over Meshtastic vs Reticulum.

**Q237 [P1]** What admission and runtime policy stack works on k3s from Pi 5 upward: Kyverno or OPA Gatekeeper with sigstore image verification, Falco or Tetragon for runtime detection, and Trivy Operator for continuous scanning? Does it stay within the RAM budget of a 4–8 GB Lite node?  
*Why:* Image signing is worthless without enforced verification. On Lite hardware the policy stack might not fit, which affects the edition design.  
*Method:* Project docs and resource benchmarks. Install each on a Pi 5 8 GB and the Beelink U55 running k3s and measure idle and peak memory and CPU.

**Q238 [P1]** How should the OneMind app store vet third-party and community apps to avoid becoming a malware channel? Compare F-Droid reproducible builds, the Flathub verification process, Umbrel and Olares app review, Home Assistant's add-on security rating, and the npm/PyPI malware incident record. What signing, provenance (SLSA), sandbox-rating and kill-switch/revocation mechanics should exist, and do they work offline?  
*Why:* A-1/A-6 scale to hundreds of community apps. Store compromise is the most likely large-scale incident, and a revocation design must exist before launch.  
*Method:* Read the F-Droid inclusion policy, Flathub verification docs, umbrel-apps and Olares market submission guidelines, and the HA add-on security rating source code. Review the 2024–2026 OSS registry malware reports (Socket, Phylum, ReversingLabs).

**Q239 [P1]** What do privacy laws require for the AI-context feature where all apps' data is available to local and external models (AI-1/UX-3)? Consider GDPR lawful basis and DPIA for household and child data, CCPA/CPRA ADMT rules (2025–2026), the EU AI Act obligations (Aug 2025 GPAI, Aug 2026 high-risk) for a deployer or provider of an AI system on a sold device, and third-party API terms such as Strava's AI-use ban.  
*Why:* Shipping external-model routing by default could make OneMind a data processor or an AI Act provider. The defaults and consent UX need to be decided before the AI layer is built.  
*Method:* EU AI Act text (Regulation 2024/1689) Art. 3, 25, 50 and Annex III, CPPA ADMT final regulations, EDPB opinions on AI models, and the Strava API agreement text.

**Q240 [P1]** How should OneMind physically and logically harden robots and drones as 'nodes' (N-1/N-7)? Consider the US drone policy context (the FY2025 NDAA DJI provisions and FCC Covered List additions, Blue UAS/AUVSI Green UAS lists, Remote ID Part 89), secure MAVLink 2 signing, ROS 2 SROS2/DDS-Security, and the EU drone regulation. Which of these constrain the base OS and update system?  
*Why:* Robotics is the moat. Blue/Green UAS eligibility and NDAA-compliant component sourcing (for example no Chinese flight controllers) affect hardware choices and the market for public-safety drones.  
*Method:* Text of NDAA FY2025 Sec. 162 and FCC Covered List updates, DIU Blue UAS framework docs, AUVSI Green UAS requirements, MAVLink signing docs, the ROS 2 SROS2 docs, and EASA U-space regulations.

**Q241 [P2]** Is RISC-V a credible OneMind target by 2030 (Debian riscv64 became an official trixie architecture; k3s/containerd riscv64 builds; RVA23 boards; UEFI/secure boot on RISC-V)? What would OneMind have to do now (multi-arch CI, no x86/ARM-only binaries in core) to keep that door open?  
*Why:* RISC-V is the most geopolitically neutral ISA. Multi-arch discipline is cheap to start and expensive to retrofit.  
*Method:* Debian release notes for trixie riscv64, k3s release assets, RISC-V International RVA23 profile ratification, and test boards (Milk-V Jupiter, SpacemiT K1/K3). Run k3s on one.

**Q242 [P2]** What do satellite direct-to-cell and small-terminal options (Starlink Direct to Cell/T-Mobile T-Satellite, Starlink Mini, AST SpaceMobile, Iridium NTN Direct/Skylo, Apple/Globalstar, the EU IRIS² timeline) offer an off-grid OneMind node for backhaul by 2030? What are the sovereignty risks (single-operator dependency, the Starlink-Ukraine precedent of operator-controlled geofencing)?  
*Why:* Off-grid deployments need a backhaul plan. Relying on a single operator who can switch off service contradicts the sovereignty pitch, so the OS should treat backhaul as pluggable.  
*Method:* FCC filings and operator docs, 3GPP NTN Release 17/18/19 specs, the EU IRIS² programme schedule, and reporting on Starlink service restrictions in Ukraine (primary statements). Field-test a Starlink Mini with a Beelink on battery.

**Q243 [P2]** Should OneMind consider remote attestation (TPM quotes, Keylime, Veraison, the IETF RATS architecture, NVIDIA Jetson attestation) so a cluster or federation admits only nodes in a known-good measured state? Would this work across Pi (no TPM), x86 and Jetson, and what privacy risks does it create for home users?  
*Why:* Federation (P-4) and enterprise/public-safety clusters will want to know that a node isn't tampered with. It needs measured boot from day one even if attestation comes later.  
*Method:* Keylime docs, IETF RATS RFC 9334, the Veraison project, the NVIDIA attestation SDK for Jetson/GPU, and Pi TPM HAT options (Infineon SLB9672). Test Keylime on the Dell 5540.

**Q244 [P2]** Over a 10-year horizon, which crypto-agility steps are needed for post-quantum migration (NIST FIPS 203/204/205 ML-KEM/ML-DSA/SLH-DSA, CNSA 2.0 timelines that require PQ firmware/software signing by 2025–2030, OpenSSH/OpenSSL 3.5 hybrid KEX, WireGuard's PQ options)? Can Rugix/RAUC bundle signing, UEFI Secure Boot, the Pi OTP and Jetson fuses be migrated to PQ signatures, or are fused classical keys a dead end?  
*Why:* Devices sold in 2027 could still run in 2037. Fusing RSA/ECDSA keys into hardware with no PQ path is irreversible. CNSA 2.0 would force PQ signing for national-security customers.  
*Method:* NIST FIPS 203–205, the NSA CNSA 2.0 FAQ and timeline, OpenSSL 3.5 release notes, LMS/XMSS stateful hash-based signature support in firmware (NIST SP 800-208), and the Pi/Jetson key-type documentation.

**Q245 [P2]** Looking ahead 5–10 years, which scenarios (US–China decoupling and component bans, an EU sovereign-tech mandate, a major regional grid or internet outage, AI-regulation divergence, a GitHub/Docker Hub access block in some jurisdictions) should drive OneMind's foundation contingencies? What is the minimum self-hosted build and distribution infrastructure (own package mirror, OCI registry, git forge, CI, update CDN plus torrent/IPFS fallback) needed to keep shipping under each one?  
*Why:* The user wants a plan that lasts given world events. This turns geopolitical risk into concrete infrastructure decisions for the build pipeline.  
*Method:* Scenario analysis from CSIS, RAND, Atlantic Council and ECFR reports, plus precedents (GitHub restrictions on sanctioned regions, Docker Hub rate limits and sanctions blocks, the Huawei Android cutoff). Design an air-gapped rebuild drill: rebuild the full OneMind image from a local Debian mirror plus Forgejo plus a local registry with internet off.

## Product, UX, apps & ecosystem (dashboard/front door, clients, XR, multi-user, education, app catalog, internal apps, plugins/community, website, docs, onboarding, 5-10 yr product roadmap)

**Q246 [P0]** How exactly do umbrelOS 2.x, Olares (Desktop/Market/Control Hub/Settings), CasaOS/ZimaOS, Home Assistant, TrueNAS SCALE, Unraid and Synology DSM structure their front door? For each, record the framework, how the backend API is shaped (REST/tRPC/GraphQL/WebSocket), how apps are launched (iframe, subdomain, path proxy, new tab), how auth/SSO is passed to apps, and how long first boot takes until the 'install an app' moment.  
*Why:* P-2/UX-1 call the dashboard the missing piece. Picking the shell architecture (SPA over a k8s API facade, versus a desktop-metaphor like Olares) has to be grounded in what is proven, and it fixes the contract every app must follow.  
*Method:* Clone umbrel (ui/, umbreld tRPC), beclab/Olares (apps/desktop, framework), IceWhaleTech/CasaOS-UI, home-assistant/frontend and TrueNAS webui. Run each in a VM, capture the network traffic and routing with browser devtools, and time first boot to first app install. Write a comparison matrix.

**Q247 [P0]** Can a Kubernetes-backed appliance give a non-technical user a dashboard as simple as Umbrel's Docker-Compose one? Which k8s concepts (namespaces, PVCs, ingress, pod restarts, image pulls) does Olares leak into its UI and error messages, and what abstraction layer (an app CRD or operator, plus a status reducer) hides them?  
*Why:* This challenges D4 (k3s on every tier) from the UX side. If k8s failure modes can't be hidden, the Lite tier's simple promise (P-1) breaks, and a Docker/Compose Lite runtime (N-9) comes back into consideration.  
*Method:* Install Olares and umbrelOS on the same hardware. Inject failures (full disk, image pull failure, OOM, a node that can't be reached) and screenshot the UI and error text from each. Read the Olares app-service and bfl source for how status is mapped. Prototype a CRD and status reducer on k3s.

**Q248 [P0]** Should the OneMind dashboard and control plane run inside k3s as pods, or as a host-level daemon outside the cluster (like umbreld or the HA Supervisor) so it survives a broken cluster and can repair it? What do Olares, Rancher Desktop and Talos/Omni do, and how does that interact with the 'commit the A/B slot only when k3s plus core pods are healthy' rule?  
*Why:* This sets the recovery UX. If the dashboard lives in k3s, a broken k3s means a dark screen with no repair path. It also directly shapes the D3 health-check commit logic.  
*Method:* Read the source of umbreld, HA Supervisor, Olares bfl/olaresd and the Talos/Omni architecture docs. Break k3s on a test box (corrupt the datastore, block the API server) and record which UIs can still recover.

**Q249 [P0]** What is the app package format: Umbrel-style docker-compose plus umbrel-app.yml, Olares Helm charts with OlaresManifest.yaml, CasaOS compose with x-casaos, a Helm/OCI artifact, or a OneMind manifest that converts to all of them? It must also declare the AI/MCP capabilities, permissions, ports, GPU/device needs, backup hooks, and the minimum hardware tier.  
*Why:* A-1/A-2/AI-3/N-3 all depend on one manifest. Changing it later costs the whole catalog, so it is effectively a foundation decision.  
*Method:* Pull the umbrel-apps, beclab/apps (Olares market), CasaOS-AppStore, Runtipi/appstore, Cosmos and Yunohost-apps repos. Diff the manifest schemas field by field. Prototype automatic conversion of 20 popular apps (Nextcloud, Immich, Jellyfin, Ollama, Open WebUI, Home Assistant, Frigate, Node-RED and others) into Helm charts plus a OneMind manifest, and measure how much needs fixing by hand.

**Q250 [P0]** What do the licenses of the competitor app-store repos (umbrel-apps, beclab/apps, CasaOS-AppStore, Runtipi, Unraid Community Applications templates, TrueNAS apps, Yunohost) and of each top-200 upstream app (AGPL, SSPL, BSL, Fair-code/n8n, Elastic, PolyForm, commercial) allow? Specifically: can OneMind copy or adapt manifests, redistribute images, ship the apps preinstalled on boxes it sells, or charge for them?  
*Why:* A-3 calls for seeding the catalog from Olares/Umbrel categories, but Umbrel is PolyForm-Noncommercial and Olares has conflicting licenses. Bundling non-free apps on hardware sold commercially (H-1) is a legal risk.  
*Method:* Read LICENSE files and git history for each store repo. Build a spreadsheet of the top 200 apps with SPDX IDs and redistribution and 'as a service' clauses. Check how Umbrel and Olares handle n8n/Sustainable-Use and SSPL apps. Flag items that need a lawyer.

**Q251 [P0]** How should the 'every app is AI context' capability layer show up in the UX? That covers per-app MCP permission grants, scopes (read/write/act), human-in-the-loop approval prompts, audit trails, and revocation. Compare Umbrel 2.0's MCP integration, Olares agent permissions, Claude Desktop/Code permission dialogs, Android runtime permissions and iOS privacy prompts.  
*Why:* AI-1/AI-3/AI-5 are the differentiator. Without a permission UX that families and enterprises trust, this is a security liability. It also shapes the manifest (Q4) and identity model.  
*Method:* Install Umbrel 2.0 and test its MCP/agent flows. Read the MCP 2026-07-28 spec's authorization and elicitation sections. Map the Android and iOS permission models. Produce wireframes and a scope taxonomy, and test them with five non-technical users.

**Q252 [P0]** What identity and multi-user model supports 'everyone gets their own space' (U-1), child accounts and parental controls (U-3), and enterprise SSO? Compare Olares (one Kubernetes namespace and Authelia/LLDAP per user), Umbrel (single user), HA (users with admin flag), Synology DSM, and Authentik. Then decide whether per-user apps are separate instances or shared multi-tenant apps.  
*Why:* Per-user instances multiply RAM use, which hits Pi and Lite boxes. Shared apps leak data between family members. This is hard to retrofit and touches Authentik, which OneMind already runs.  
*Method:* Read the Olares multi-user and app-mode (shared vs per-user) source and docs. Measure RAM for three users times ten apps on Olares versus a shared-app design. Prototype Authentik family groups with OIDC claims passed to Nextcloud, Immich and Jellyfin.

**Q253 [P0]** How does a self-signed box get trusted HTTPS on the LAN for browsers and mobile apps, especially iOS? Compare Umbrel's umbrel.local over HTTP, Olares' per-user domains with Let's Encrypt, Start9's root CA install, HA, and Tailscale MagicDNS certificates. What does this mean for WebXR, PWAs, passkeys and service workers, which all need a secure context?  
*Why:* WebXR (UX-9), PWA push and WebAuthn need HTTPS. The first-run certificate UX is a known adoption killer.  
*Method:* Test each approach on Chrome, Safari iOS, Quest Browser and the Android XR browser. Document which APIs fail without a secure context. Read the Start9 and Olares certificate code.

**Q254 [P0]** What exactly is a OneMind 'plugin' versus an 'app' versus an 'integration' versus a 'profile' versus a 'bundle'? Define the extension points (dashboard widget, MCP tool, NATS subject handler, device driver, alert rule, Backstage plugin) and the sandboxing for each: WASM (Extism, Wasmtime), a container, a JS iframe, or a Lua/Starlark script.  
*Why:* Without a crisp extension model, A-5/A-6/A-7/P-8 collide. WASM vs container is a foundation choice for safely running untrusted community code on boxes that control robots.  
*Method:* Survey extension models in HA (integrations vs add-ons), Grafana plugins, Backstage plugins, Omarchy, Zed/VS Code, Envoy/Extism WASM and Fermyon Spin. Prototype one widget plugin and one MCP-tool plugin in WASM and in a container, and measure isolation, startup and RAM.

**Q255 [P0]** Should Backstage remain part of the product (developer portal, catalog, MCP server already live in the cluster) or be limited to OneMind's internal and enterprise tier? What does it cost on a 4-8 GB box, and can its software-catalog model be the 'infrastructure map' (UX-7) and multi-machine view (UX-6) data source?  
*Why:* The brief points to Backstage as the proven concept but also calls it too shallow (P-2). The decision affects whether the dashboard reuses the catalog schema or builds its own.  
*Method:* Measure the RAM and CPU of the existing Backstage deployment through the onemind-kubernetes MCP (pods_top). Read the Backstage catalog model and the new frontend system docs. Prototype mapping Backstage entities to dashboard tiles. Compare with Olares Control Hub's data model.

**Q256 [P0]** For cloud-app integrations (UX-3), which major consumer APIs forbid passing their data to AI or LLMs, or impose other restrictions? Cover Strava, Garmin Connect, Oura, Whoop, Withings, Fitbit/Google Health, Apple HealthKit, Health Connect, Dexcom, Spotify, Google and Microsoft calendars, Plaid/finance aggregators, and banks. What architecture keeps OneMind compliant, for example data stays on device, the user exports it, or local-only models?  
*Why:* This is a founder-requested wellness and finance focus. Strava's AI ban is already flagged from secondary sources and needs primary verification. Violating API terms could get OneMind's developer keys banned and cut off thousands of users.  
*Method:* Read each provider's current API agreement and developer policy, cite clause numbers, and record the date read. Check Apple's HealthKit guideline 5.1.3 and Google Health Connect policy on AI use. Look at how Gadgetbridge and open-source tools do local export instead.

**Q257 [P0]** What does onboarding look like from unboxing (or flashing) to first value in Umbrel Home, Olares One, HA Green, Start9 Server, ZimaCube and Synology? Count steps, time, failure points, and whether it needs an account, a phone app or a cloud. What is the OneMind first-boot flow for each edition and profile, including QR device onboarding (N-4)?  
*Why:* P-1 'just works' and P-7 BYO plus turnkey depend on first-run UX. Owning the image (D1) lets the first-boot wizard be designed now.  
*Method:* Buy or borrow at least two devices, or use VM images. Record the onboarding on video and time it. Read the HA onboarding and Umbrel setup source. Write a OneMind first-boot spec covering the BYO-flash path (Raspberry Pi Imager/Etcher integration) and the turnkey path.

**Q258 [P0]** How should OS profiles (P-8: TAK situational awareness, greenhouse, family, AI node) be represented: separate images, one image with a first-boot profile choice, or app bundles applied later? How do Balena fleets, HA blueprints, Umbrel app bundles and Olares templates handle this, and how does it relate to the 'superpower per machine' idea (P-6)?  
*Why:* Separate images multiply build, test and CRA support burden. One image plus profiles is cheaper but may not fit a tiny Pi deployment. This touches the image pipeline decision (D1/D3).  
*Method:* Review balenaOS fleet configs, HA blueprints and packages, Umbrel and Olares bundle docs, and NixOS/Kairos profile approaches. Prototype one image with a profile chosen at first boot on a Pi 5, and measure its footprint versus a stripped TAK-only image.

**Q259 [P0]** Should the TAK situational-awareness profile use CloudTAK (already live at onemindos.dev) as the dashboard's map module, or integrate with ATAK/iTAK clients only? What are the licensing (TAK Product Center, ATAK-CIV, the CloudTAK license), export-control and distribution limits on bundling TAK Server or CloudTAK into a sold box?  
*Why:* TAK is a stated moat. Bundling it on hardware sold commercially or abroad may hit TAK.gov distribution terms or ITAR/EAR rules, which shapes the profile and edition strategy.  
*Method:* Read the TAK.gov licensing and distribution terms, the CloudTAK repo LICENSE (dfpc-coe) and ATAK-CIV terms. Check EAR classification statements. Review the existing onemindos.dev CloudTAK deployment and its app-registry plan.

**Q260 [P0]** How do Synology, Ubiquiti, HA (Green/Yellow) and Umbrel present editions, pricing and hardware bundles in-product and on the store? Cover upsells, license keys, feature flags and subscriptions. Should Lite/Pro/Omni (P-5) be software feature gates, hardware tiers, or support and service tiers, given the Apache-2.0 open-core decision (D-001)?  
*Why:* Edition boundaries decide what is open source versus paid. That shapes the codebase layout, licensing and dashboard feature flags early.  
*Method:* Survey the pricing pages and license terms of Synology, Unraid (license tiers), TrueNAS (Community vs Enterprise), Portainer BE, Proxmox subscriptions, Nabu Casa, Olares One and GitLab open core. Map OneMind features to the tier boundaries with the founder.

**Q261 [P1]** What do real parental-control systems do (Apple Screen Time and Family Sharing, Google Family Link, Microsoft Family Safety, Pi-hole/AdGuard group policies, Firewalla, Circle Home Plus, Bark, Qustodio), and which of their controls can a self-hosted box enforce on a child's own phone or laptop without an MDM certificate from Apple or Google? What do COPPA, GDPR-K, the UK Age Appropriate Design Code and US state laws require of an operator that stores children's data?  
*Why:* U-2/U-3 are founder priorities. The technical feasibility of on-device control (MDM, Family Link APIs, DNS-level control) decides whether the promise can be kept. Child-data law sets compliance scope for selling to families.  
*Method:* Read Apple's Screen Time API and MDM docs, Android Device Policy and Family Link developer docs, and the open-source MDMs (MicroMDM, NanoMDM, Headwind MDM). Test DNS and Tailscale-ACL-based controls on a test child device. Write a legal summary from primary statute text.

**Q262 [P1]** Which mobile and desktop client architecture gets one developer to iOS, Android, macOS, Windows, Linux and web (UX-8) with push alerts (D-005 APNs), offline/LAN discovery (mDNS), Tailscale integration and biometric unlock? Compare the Umbrel app, HA Companion (native iOS/Kotlin), Olares LarePass (Flutter), Tailscale clients, and options such as PWA, Capacitor, React Native/Expo, Flutter, Tauri 2 mobile and Kotlin Multiplatform.  
*Why:* UX-5/UX-8 promise phone-first control. Choosing the wrong stack wastes a solo developer's year. PWA push and background limits on iOS may force native apps.  
*Method:* Reverse-engineer the HA Companion, LarePass and Umbrel mobile apps (APK decompile with jadx, plus GitHub source). Build a 2-day spike in Tauri 2 and Expo testing LAN discovery, Tailscale reachability, APNs/FCM push via ntfy/UnifiedPush and passkey login on a Pixel and an iPhone.

**Q263 [P1]** How do users reach their box remotely without a OneMind-operated cloud (M-1)? Compare Umbrel (Tailscale app), Olares (FRP/Cloudflare tunnel via its own domain service), HA (Nabu Casa paid relay), Start9 (Tor plus LAN certs), Synology QuickConnect and Unraid Connect. What is the onboarding UX and the business model behind each, and should a paid OneMind relay or DNS service exist later?  
*Why:* U-5 and every client depend on this. Nabu Casa shows a relay can fund the open-source project. It is a 5-10 year revenue line to plan for, but it conflicts with local-first if it is required.  
*Method:* Read the docs and source of each remote-access path. Time the onboarding flow for each on a fresh install. Read Nabu Casa's public financial and funding statements and HA Open Home Foundation reports for revenue proof.

**Q264 [P1]** What is the right catalog seed list and category taxonomy for launch? Merge the Olares Market categories, Umbrel App Store categories, CasaOS and Unraid CA, and awesome-selfhosted. Rank by install counts or GitHub stars, RAM footprint, ARM64 availability, GPU need and license, and pick the 30 launch apps per edition (Lite/Pro/Omni) and per profile (TAK, homestead, family, AI).  
*Why:* A-1/A-3/P-5/P-8 require an app list traced to evidence. Arm64 and RAM fit decide what Pi and Lite can offer, so they feed the hardware tiers.  
*Method:* Scrape the store repos and the awesome-selfhosted YAML. Query the Docker Hub/GHCR manifest for arm64 variants. Pull public install metrics where they exist (Umbrel shows install counts; Unraid CA has download stats). Build a scored dataset.

**Q265 [P1]** How did Home Assistant (HACS, add-ons, integrations), Obsidian (community plugins with a review queue), VS Code Marketplace/Open VSX, Omarchy, Raycast and Umbrel community app stores grow their community ecosystems? What are their governance, review, signing, malware incidents, discoverability, and the economics for authors?  
*Why:* A-5/A-6 depend on a plugin ecosystem. The design choices (central review vs third-party stores, signing, sandboxing) are security-critical because plugins get AI and device access.  
*Method:* Read the HACS, Obsidian obsidian-releases review process, Open VSX governance and Umbrel community-store docs. Collect public malware or supply-chain incident reports (VS Code extension malware, Obsidian plugin issues, npm). Interview or read retrospectives from maintainers.

**Q266 [P1]** Which existing dashboard projects (Homarr 1.x, Homepage, Dashy, Glance, Heimdall, Organizr, HA Lovelace) should OneMind fork, embed or replace for the customizable dashboard (UX-2)? Compare their widget APIs, service-integration count, licenses, and how their config could be imported so users can migrate in one click.  
*Why:* UX-2 says to replace Homepage/Homarr. Importing their configs is a cheap migration hook, and their 100-plus integrations could be reused if the license allows.  
*Method:* Clone each repo. Read the licenses and the integration/widget code. Write a converter from the Homepage services.yaml and the Homarr board export into a OneMind dashboard schema. Count working integrations.

**Q267 [P1]** Which internal OneMind app should be built first, and is a single unified app (A-4) better than separate apps? Use Todoist/ClickUp replacement needs, the existing Obsidian and Todoist workflow, finance (Actual, Firefly III, Maybe), wellness, family (Mealie, Grocy), OSINT (SpiderFoot, Maltego CE), and mesh (Meshtastic UI) to decide which internal apps to build versus integrate as open-source apps.  
*Why:* Open Question 5 in REQUIREMENTS. A solo developer (M-6) can't build nine apps, so build-versus-integrate per domain is the main scope lever in the 1-2 year plan.  
*Method:* For each domain, compile the top three open-source apps with maturity, license, API surface and MCP availability. Score how much each fits OneMind's NATS/MCP capability layer. Ask the founder to rank pain points, and produce a build/integrate/defer matrix.

**Q268 [P1]** What do Kolibri, Kiwix (ZIM libraries), Project N.O.M.A.D., Internet-in-a-Box, RACHEL, Khan Academy Lite and Moodle each provide for offline, kids' and homestead education? What are their sizes, hardware needs, licenses and update model? How should they plug into OneMind, and how do they relate to Circle.so (W-2), which is a hosted, non-sovereign platform?  
*Why:* U-2 and W-2 both target education. Offline education is a strong sovereignty and off-grid differentiator (N.O.M.A.D. is a named competitor). Circle.so conflicts with local-first and needs a reason to keep it.  
*Method:* Install Kolibri, Kiwix-serve with a Wikipedia ZIM, and N.O.M.A.D. on a Pi 5 and the Beelink. Measure storage and RAM. Read licenses and the N.O.M.A.D. repo. Compare Circle.so against self-hosted options (Discourse, Moodle, Canvas LMS, Frappe LMS) on features, export and cost.

**Q269 [P1]** What does each competitor's website and commerce stack run on (umbrel.com, olares.com, home-assistant.io and Nabu Casa store, start9.com, zimaspace.com, frame.work, system76.com, pine64.org)? Covers CMS, docs engine, store, forum, support desk, analytics and download hosting. Is Astro/Starlight plus Shopify (or a sovereign alternative such as Medusa/Saleor) plus Discourse the right OneMind stack?  
*Why:* W-1 through W-9. The website is a prerequisite for NVIDIA Inception (D-006) and hardware sales, and must fit a solo developer's operating budget.  
*Method:* Fingerprint each site with Wappalyzer/BuiltWith, HTTP headers, robots and sitemaps, and page source. Read their docs repos on GitHub. Price Shopify vs Medusa/Saleor self-hosted vs Lemon Squeezy for hardware plus digital goods, including tax and EU VAT handling.

**Q270 [P1]** Which support desk and feedback tooling fits (Zammad, FreeScout, Chatwoot, Zoho Desk, Discourse as support, GitHub Discussions)? How do HA, Umbrel and Synology run support at scale, for example diagnostic bundle upload, remote support sessions or community moderators? What in-product diagnostics (a one-click redacted support bundle) does OneMind need on day one?  
*Why:* R-2 requires a strong support system. Selling hardware creates warranty and support obligations, and diagnostics must be designed into the OS image early.  
*Method:* Read HA system-health/diagnostics and Synology support-center docs. Look at Umbrel's troubleshooting flow. Trial Zammad and FreeScout self-hosted on k3s. Read Zoho Desk/Forms API terms for the W-5/W-6 integration.

**Q271 [P1]** How will the dashboard present many machines and clusters at once (UX-6), mirror one device to another, and draw an automatic infrastructure map (UX-7)? Compare Olares multi-node, Unraid Connect, TrueNAS Connect, Portainer, Rancher, the Proxmox datacenter view, Netbox and Tailscale's admin map, plus discovery via LLDP, mDNS, NATS presence and the k8s API.  
*Why:* This multi-node UX is what separates OneMind from single-box competitors, and it depends on the federation design (P-4) chosen now.  
*Method:* Test Proxmox, Portainer and Rancher multi-cluster UIs. Read the Netbox and Scanopy/NetAlertX discovery code. Prototype the map from the existing DOKS cluster plus Tailscale API plus NATS discovery subjects.

**Q272 [P1]** How should the native alert system (UX-4) work: in-OS rules engine, notification routing to the app, push, Matrix/Telegram (already used by the cluster), email and TAK CoT? Compare HA automations and notify, the Prometheus Alertmanager UX, Uptime Kuma, ntfy and Gotify, and decide whether the alert model sits on NATS JetStream subjects.  
*Why:* Alerts are a daily-use hook and a public-safety requirement. The cluster already routes alerts to Matrix and Telegram, so the product version must extend that pattern.  
*Method:* Read the current cluster alerting config through the onemind-kubernetes MCP. Prototype alert events on NATS subjects delivered to ntfy/UnifiedPush and APNs, and as CoT to TAK. Measure delivery latency and offline behavior.

**Q273 [P1]** How should hardware capability detection (N-3) be surfaced to users, for example an 'it will run' badge on each app, a robotics-sim readiness score or a box benchmark? What do Ollama/Umbrel GPU detection, LM Studio's hardware compatibility hints, Steam's system requirements check, NVIDIA Isaac Sim requirements and Olares app requirements do?  
*Why:* This links the app manifest (minimum tier) to the hardware tiers (H-3) and the recommendation engine (A-8). It is a key Pro/Omni upsell surface.  
*Method:* Read the Umbrel and Olares source for resource checks. Collect official requirements for Isaac Sim/Lab, Ollama models, Frigate and Immich ML. Build a probe (lscpu, nvidia-smi, lspci, /proc/meminfo, NPU detection) and test it on the Beelink, Dell 5540, a Pi 5 and a Jetson.

**Q274 [P1]** What is the robotics and drone UX inside the OS? Cover fleet view, live telemetry, teleop, mission planning, sim launch, and AI 'drive this robot' with HITL. Compare Foxglove, Formant, Freedom Robotics, QGroundControl, Mission Planner, the AWS RoboMaker legacy, NVIDIA Isaac's UI and Open-RMF web. Which should OneMind embed, and what does the MHS/MCP control surface look like to a user?  
*Why:* Robotics is the moat (M-7), yet no competitor has a consumer-grade robotics front door. Decisions on WebRTC video, a ROS 2 bridge and permission prompts must exist in the shell architecture from day one.  
*Method:* Run Foxglove, QGroundControl and Open-RMF web against a ROS 2 sim (Gazebo/Isaac) on a GPU box. Read the licenses (Foxglove Studio went closed source in 2024, so check Lichtblick). Track the MHS waitlist spec. Wireframe the robot-card UX.

**Q275 [P1]** What is the community growth playbook that worked for Home Assistant, Umbrel, Omarchy, Obsidian, Proxmox and Framework? Cover where they launched, forum vs Discord vs Reddit, contributor funnels, ambassador and partner programs, YouTube and creator partnerships, conference presence, and measured growth curves such as stars, installs and analytics opt-in. What metrics should OneMind track from day one without breaking privacy?  
*Why:* This underpins the 'become the industry standard' mission and the educational focus. Privacy-respecting telemetry (opt-in, like HA analytics) must be designed into the OS.  
*Method:* Pull GitHub star histories, analytics.home-assistant.io data, and Reddit and Discord member counts over time. Read founder retrospectives (Paulus Schoutsen's 'state of the open home', Umbrel blog, DHH on Omarchy). Design an opt-in telemetry schema.

**Q276 [P1]** How should documentation be built and versioned across the OS image, apps, SDK, hardware and profiles (W-3)? Compare the HA docs (Jekyll to Astro?), developers.home-assistant.io, Olares docs (VitePress), Umbrel docs, Starlight and Docusaurus, plus llms.txt and MCP-servable docs so agents can read them. How do in-OS help and the docs site share one source?  
*Why:* Docs are a support-load reducer (R-2) and AI context (AI-1). Agent-readable docs are a cheap AI-native differentiator.  
*Method:* Inspect each docs repo's tooling and build. Test the llms.txt and docs-MCP patterns (Mintlify, Context7). Prototype Starlight with versioning plus a docs MCP server.

**Q277 [P1]** What accessibility, localization and elder/child usability standards (WCAG 2.2 AA, EN 301 549 for EU public sector, Section 508 for US public safety buyers) must the dashboard and mobile apps meet to sell to families, schools, governments and public safety, and what does each competitor currently achieve?  
*Why:* Public-sector buyers (M-4) require accessibility conformance (VPAT/ACR). Retrofitting is expensive, so the design-system choice should account for it now.  
*Method:* Run axe/Lighthouse audits on the Umbrel, Olares, HA and CasaOS UIs. Read EN 301 549 and Section 508 procurement requirements. Pick a design system with documented a11y support (Radix, React Aria, Shoelace).

**Q278 [P1]** Is the dashboard plus app-store model even the right primary interface, or should OneMind be agent-first (talk to Hermes/Claude, which uses MCP) with the GUI as fallback? What did Umbrel 2.0's MCP agent, Olares' agent apps, Rabbit and Humane failures, and HA Assist adoption data show about how often users actually use agents over GUIs?  
*Why:* This challenges the P-2/UX-1 assumption that a GUI dashboard is the centerpiece. It drives where the solo developer spends the first year.  
*Method:* Read the HA Assist usage stats (analytics.home-assistant.io voice data, State of the Open Home talks), Umbrel 2.0 release notes and community feedback, and Rabbit and Humane post-mortems. Run a small usability study with family members comparing GUI and agent tasks.

**Q279 [P1]** What would it take to sell hardware with a OneMind-branded app in Apple's App Store and Google Play, given policies on remote device control, VPN entitlements, home automation, AI chat and sideloaded-app distribution? Is F-Droid or Accrescent plus TestFlight enough for the sovereign audience?  
*Why:* UX-8 and the iOS push decision (D-005) depend on store approval. Rejection risk, especially for Network Extension and VPN entitlements with Tailscale-like features, affects the remote-access design.  
*Method:* Read the App Store Review Guidelines (sections 2.5, 4.2, 5.4 VPN), the Google Play device-control and VPN policies, and F-Droid inclusion policy. Study how the HA Companion, Tailscale, Umbrel and LarePass apps got approved.

**Q280 [P1]** How do Olares' 'Studio' (dev environment) and Wise (reader/RAG) and HA's developer tools support third-party developers building apps on-box? What SDK, local dev loop, emulator or simulator, and publishing flow should OneMind ship (P-4 SDK) so community developers and AI coding agents can build OneMind apps?  
*Why:* The community ecosystem (A-6) only grows if building is easy. AI agents writing apps against a clear SDK and manifest is a multiplier for a solo founder.  
*Method:* Install Olares Studio and HA devcontainer. Read the Umbrel app-framework docs. Prototype a CLI (onemind app init/dev/publish) generating a manifest plus Helm chart and test it by having a coding agent build a sample app end to end.

**Q281 [P1]** What data portability and exit guarantees should the product make (export all user data, apps and configs; move to plain Debian/k3s; leave OneMind), and how do Umbrel, Olares, HA and Synology handle lock-in? Can 'no lock-in' be a verifiable product feature?  
*Why:* Sovereignty (M-2) is the brand promise. A verifiable exit path is a trust and marketing asset and constrains the data model and backup format (D5).  
*Method:* Test exporting and migrating from each competitor to a vanilla setup. Read the backup formats (SecureTar, Umbrel backups, Olares restic layout). Specify a OneMind export format and test the restore onto a vanilla k3s cluster.

**Q282 [P1]** Who are the first 100 paying customers, by segment (homesteaders, privacy families, TAK/public safety teams, small businesses, robotics hobbyists), and which single product surface plus profile plus hardware tier gets them to pay within 12 months? What do the Umbrel Home, HA Green and Start9 launch data and Kickstarter/Crowd Supply campaigns (ZimaCube, Olares One) show about price points and conversion?  
*Why:* Open Question 4 (first hardware tier and customer segment) blocks the 1-2 year roadmap and decides which UX gets built first.  
*Method:* Collect the Kickstarter/Crowd Supply campaign data (backers, pledge levels, timelines) for Olares One, ZimaCube, ZimaBoard and other comparable boxes. Gather public sales statements. Run founder customer-discovery interviews with 10 people per segment, using a scripted questionnaire.

**Q283 [P2]** What is the real state of XR access in 2026-2027 for reaching a home box: WebXR support in the Quest Browser, Android XR (Galaxy XR and partner glasses), visionOS Safari, Snap Spectacles, Meta Ray-Ban Display and Xreal? Which immersive dashboard and TAK/robot-teleop patterns work today (spatial panels, 3D maps, video passthrough), and which need native apps?  
*Why:* UX-9 and robotics teleop are moat-adjacent. They need to know whether a web-only XR strategy is enough or whether native Android XR/visionOS apps are required, and on what timeline.  
*Method:* Read the vendor WebXR compatibility pages and the Android XR SDK and visionOS docs. Build a three.js/WebXR prototype that loads the dashboard and a ROS 2 camera stream via Foxglove/WebRTC, and test it on whatever headsets can be borrowed or bought. Review projects such as ATAK XR plugins and NVIDIA CloudXR.

**Q284 [P2]** How should an Omarchy-based desktop edition (UX-10) relate to the box OS? Would it be a client that pairs with a box, its own node joining the cluster, or both? What has Omarchy shipped for agent-native desktop features, and how do the Arch rolling release and Hyprland's pace conflict with OneMind's support and CRA obligations?  
*Why:* Supporting a rolling desktop distro is a long-term maintenance cost. It challenges whether the desktop edition should exist or be a thin Omarchy plugin set.  
*Method:* Read the Omarchy repo history and release cadence and its plugin/menu extension points. Install it on the Dell 5540, pair it with a k3s box via Tailscale and NATS, and record the breakages over 30 days of updates.

**Q285 [P2]** What are the 5- and 10-year platform shifts that could obsolete OneMind's product surfaces? Consider agent-first interfaces replacing dashboards, AR glasses replacing phones, Apple and Google 'private cloud compute' and local-AI boxes, EU DMA-forced sideloading and app-store openness, Matter/Thread, and humanoid home robots. What does a OneMind product roadmap look like for 2027, 2029 and 2031-2036 under each scenario?  
*Why:* The founder asked for a 5-10 year plan. The shell and app model should be chosen so it survives a shift from 'click dashboards' to 'agents and voice and XR'.  
*Method:* Review primary sources: EU DMA enforcement decisions, Apple PCC docs, Matter spec roadmap, analyst reports (IDC/Gartner AR shipments, humanoid-robot forecasts from Goldman/Morgan Stanley), and NVIDIA GTC and KubeCon 2026 keynotes. Write scenario-based roadmaps with leading indicators to watch.

## gap-fill

**Q286 [P0]** The canonical Blueprint says 'build a portable operating platform first (Core + Client + SDK), prove local operation and recovery, then package a supported Linux appliance', while ADR-001 D1 says 'ship our own image, including on BYO hardware'. Which order is right for a sole developer in the first 180 days, and what is the evidence? Compare how Umbrel (Umbrel on Docker installer, then umbrelOS image), Home Assistant (HA Core, then Supervised, then HAOS), Olares (script installer, no image) and Start9 (StartOS image from day one) actually sequenced platform vs image, and what each sequence cost them.  
*Why:* This is the biggest unresolved contradiction between the canonical prior planning (context/02) and ADR-001. It decides what gets built first, whether onemind-core is the product's centre, and why 'an OS is now the best option' (explicit founder ask) versus continuing as a cluster plus portal.  
*Method:* Read the project histories: HA release notes and blog 2013-2018 (hass.io launch), Umbrel GitHub history (umbrel repo pre-2.0 Docker installer vs umbrelOS), Olares install docs, Start9 history. Build a timeline of each project's first image release vs first user install. Map the Blueprint ownership acceptance test (second operator installs, enrolls, exports, restores) to both orders and estimate engineer-weeks for each.

**Q287 [P0]** What becomes of the existing first-party code (onemind-core: Python/FastAPI + PostgreSQL mission ledger + Dapr workflows; onemind-mcp; Hermes; NATS subject/account contracts; bus schemas) inside the OS? Does each component fit the Lite tier RAM budget (Dapr sidecars, Postgres, Python services on a Pi 5), which Blueprint Core contracts and acceptance tests A01-A24 does the ADR-001 stack satisfy or break, and what must be rewritten, wrapped or dropped?  
*Why:* P-4 lists Core as a product surface and AI-9 says existing assets carry forward, but no generated question checks that the Blueprint Core contracts, Dapr and the Python Core survive the move to an appliance. Without this the 180-day plan cannot reuse existing work.  
*Method:* Read context/01 and context/02 (Blueprint §§ on Core, acceptance tests A01-A24, ADR 0001/0002/0003). Measure onemind-core + Postgres + Dapr idle RAM on k3s on a Pi 5 and Beelink. Produce a component-by-component carry-forward table (keep / wrap / replace / drop) with acceptance tests mapped to each.

**Q288 [P0]** Is Fedora IoT (rpm-ostree/bootc + greenboot health checks + zezere/FDO provisioning) a better fit than Debian + Rugix specifically for the founder's raised question? Greenboot already implements health-check-gated commit with automatic rollback, which is ADR-001's main 'improvement'. Does Fedora IoT support Pi 5 today, Jetson, k3s, NVIDIA (akmods on ostree), and what is its support window (13-month Fedora cadence) versus CentOS Stream/RHEL image mode?  
*Why:* The founder explicitly raised Fedora CoreOS/IoT; the generated questions bundle it with many others and never name greenboot, the closest existing implementation of ADR-001's 'healthy before commit' rule.  
*Method:* Read docs.fedoraproject.org/iot (greenboot, FDO onboarding, supported hardware), greenboot source on GitHub, Fedora Pi 5 support tracker, Fedora release lifecycle. Hands-on: install Fedora IoT on the Dell 5540 and a Pi 5, add a k3s greenboot check, break k3s, observe rollback. Write a direct one-page answer to Zeus's question.

**Q289 [P0]** What is the legal and practical status of GPL obligations for OneMind images and sold boxes: kernel and GPLv2 source offers, and especially GPLv3 'Installation Information' (anti-tivoization) for GPLv3 components (e.g. GRUB, Bash, coreutils, Samba) on consumer devices with locked Secure Boot or fused Pi/Jetson keys? Does fusing OneMind keys into a consumer product sold to households require handing owners signing ability?  
*Why:* D6 plans fused secure boot for OneMind hardware. GPLv3 §6 applies to 'User Products'; this could force the owner-key model or force replacing GPLv3 components, which changes the image contents.  
*Method:* Read GPLv3 §6 text and FSF FAQ on User Products, Software Freedom Conservancy enforcement cases (Vizio), how Debian-based appliance vendors comply (Umbrel, Proxmox, Synology GPL source pages), and get a legal summary flagged for counsel.

**Q290 [P0]** What hardware inventory facts are still unconfirmed and block the test plans: Beelink U55 CPU (i3-5005U vs N100, via lscpu), Mac model and chip, Android phone model and Android version, Dell 5540 TPM/Secure Boot state and BIOS version? Produce exact founder-run commands and a template to record results in the repo.  
*Why:* HARDWARE.md and D-004 mark these as unconfirmed; every hands-on benchmark in the question bank depends on them.  
*Method:* Write a short script/checklist (lscpu, lsblk, dmidecode, fwupdmgr get-devices, mokutil --sb-state, tpm2_getcap; system_profiler on Mac; adb getprop on Android) for Zeus to run; record outputs in research-output/.

**Q291 [P0]** For each of the 92 requirement IDs and decisions D-001 to D-006, which research-output file and which question answers it, and which IDs remain 'designed but unvalidated'? Build the traceability matrix early, re-run it after each research wave, and list any requirement that research recommends changing (with the evidence) for Zeus to decide.  
*Why:* REQUIREMENTS.md forbids silently dropping any requirement and the mission requires traceability; a running matrix is the only way to prove nothing was lost across hundreds of questions.  
*Method:* Parse REQUIREMENTS.md IDs; tag every question and output section with IDs; generate a matrix (ID -> questions -> files -> status); run as a completeness gate in the workflow loop.

**Q292 [P0]** What should the first 180 days actually deliver for each tier, given D-002 (all tiers designed together) and the critique that earlier plans were too big for one engineer? Define the minimal vertical slice per tier (Edge Pi, Lite x86, Robotics Jetson), the acceptance tests each must pass, what is explicitly deferred, and the go/no-go gates for buying hardware (Pi 5, Jetson) and for incorporation and Inception application.  
*Why:* The founder asked for a clear path and plan; the generated questions are thorough on what to research but never force a scoped, sequenced first-180-day plan with gates, which is the primary deliverable.  
*Method:* Synthesize from answered P0 questions; reuse the Blueprint first vertical slice and ownership acceptance test; estimate effort per item; review with an adversarial 'too big for one engineer' critic before finalizing.

**Q293 [P1]** ADR 0002 in the existing repo selected Backstage -> reviewed Git -> Argo CD -> KubeVela/Crossplane as the delivery chain, and OpenChoreo retirement is approved but unproven. Should KubeVela and Crossplane exist on an appliance at all, what do they cost in RAM and operator burden on Lite/Pro boxes, and how does that chain coexist with the Market App Controller described in DASHBOARD.md?  
*Why:* The generated set compares GitOps engines but never tests the founder's own recorded ADR 0002 chain against the appliance. A mismatch would leave two control planes.  
*Method:* Read the omos ADR 0002 summary in context/01-02; KubeVela and Crossplane resource docs; deploy both on k3s on the Beelink and measure; decide hub-only vs on-box with a written rationale.

**Q294 [P1]** Full code-level teardown of Project N.O.M.A.D. (named competitor, Apache-2.0): what base OS, installer, app set (Kiwix, Kolibri, Ollama, maps, etc.), update method, offline content pipeline, hardware targets, business model and community size? What can OneMind adopt directly given the compatible license?  
*Why:* RS-2 names N.O.M.A.D. as a competitor to surpass; the generated set mentions it only as an education source. Being Apache-2.0, it is the one competitor whose code OneMind may legally reuse.  
*Method:* Clone the N.O.M.A.D. repo; read install scripts, compose files, content download tooling, release history and issues; install it in a VM and on a Pi 5; record footprint, offline behaviour and update flow.

**Q295 [P1]** How do Olares Files, Vault, Desktop and LarePass work at code level: what storage backend sits under Files (JuiceFS? local? S3 mounts), what Vault is built on (Bitwarden-compatible server?), how the Desktop windowing shell is built, and how LarePass handles identity, DID/keys, VPN and backup? What must OneMind's Files and Vault modules match?  
*Why:* RS-3 requires reviewing all Olares built-ins; the generated set covers Wise, Studio, Market and Control Hub but not Files, Vault, Desktop or LarePass identity, which map directly to OneMind's Files, Vault and Family modules (APPS.md).  
*Method:* Clone beclab/Olares and related repos (files, vault, desktop, larepass); trace storage drivers and key handling; install Olares in a VM and capture API calls from Files and Vault; note licenses per directory (study only).

**Q296 [P1]** How does umbrelOS 2.0 'Machines' (Linux/Windows/Android VMs in the browser) work: hypervisor (QEMU/KVM, libvirt, crosvm?), display streaming (noVNC/SPICE/WebRTC), GPU/USB passthrough, storage, and how it coexists with read-only root and A/B? Should OneMind offer VMs via KubeVirt, libvirt on host, or Incus, and on which tiers (Pi 5 KVM support)?  
*Why:* DASHBOARD.md lists Machines for later and the conversation flagged it as an Umbrel 2.0 feature, but no question examines it. VM support affects kernel config and host services in the image now.  
*Method:* Reverse-engineer the umbrelOS 2.0 image and umbreld source for the Machines feature (study only, PolyForm-NC); read KubeVirt and Incus docs and ARM64 support; benchmark a Windows VM and HAOS VM on the Dell 5540 via KubeVirt vs libvirt.

**Q297 [P1]** Should OneMind use the founder-flagged repos (morluto/rea, storytold/craft-anything) as reverse-engineering tooling for competitor teardowns, and should OneMind adopt qybaihe/bla-style defenses to protect its own closed modules? Verify the repos' legitimacy (organic star counts, maintainers, supply-chain safety of their npx installers), their licenses, what they can actually extract from Umbrel/Olares/HAOS images, and the legal limits (DMCA §1201 and §1201(f) interoperability, EU Software Directive Art. 6, PolyForm-NC terms, clean-room doctrine).  
*Why:* RS-5 explicitly requires reviewing these repos and no generated question covers them. Using them unsafely or illegally could taint OneMind's Apache-2.0 code.  
*Method:* GitHub API analysis (stargazer timeline, contributor accounts, release signing), static review of install scripts without running them, sandboxed VM trial on an Apache-licensed target only, legal primary sources (17 U.S.C. §1201, Directive 2009/24/EC), and a written clean-room protocol for OneMind.

**Q298 [P1]** For the phone side of the mission: on current GrapheneOS releases, which Pixel models are supported and until when, and does ATAK-CIV (and the Meshtastic ATAK plugin, TAK video, iTAK equivalents) run reliably? Reproduce the Pixel Tablet crash report the founder found, test sandboxed Google Play vs no Play, location and battery settings, and document a OneMind-recommended EUD loadout. Compare Samsung S24U with Knox (locked US bootloader) as the alternative.  
*Why:* The conversation started with phones and ATAK EUDs; W14 requires it; the generated set has no question on GrapheneOS or EUD compatibility.  
*Method:* GrapheneOS FAQ and device support page, ATAK-CIV release notes, TAK forums and GitHub issues for GrapheneOS crashes; hands-on test on a Pixel (and Pixel Tablet if available) with a written test matrix; Samsung Knox and bootloader docs.

**Q299 [P1]** What does AI-6 'biometric structures, native and AI-integrated' mean in practice, and what is legal? Options: passkeys/WebAuthn with platform biometrics, on-box face recognition (Frigate, Immich, CompreFace), speaker identification for per-family-member voice assistants, wearable biometrics (heart rate) as wellness context. Which laws apply (Illinois BIPA, Texas CUBI, Washington biometric law, GDPR Art. 9, EU AI Act prohibited/high-risk biometric categories, COPPA for children's biometrics)?  
*Why:* AI-6 has no generated question at all. Biometric processing of family members and children carries some of the heaviest legal penalties in the US and EU.  
*Method:* Statute text (740 ILCS 14, Tex. Bus. & Com. Code §503.001, RCW 19.375, GDPR Art. 9, AI Act Art. 5 and Annex III), FTC biometric policy statement 2023; review Frigate/Immich face features and wespeaker/pyannote speaker ID on Pi 5/mini PC; draft consent and storage rules.

**Q300 [P1]** What exactly is the UX-6 'mirror feature' (mirror one device to another)? Candidate meanings: hot-standby replication of a whole box (failover), app/data replication between boxes, configuration cloning to a new device, or screen/session mirroring between clients. For each, what do Synology (Hybrid Share, Active Backup, SHA high availability), TrueNAS replication, Proxmox replication/HA, Umbrel backups-to-another-Umbrel and k3s multi-node offer, and which is feasible on 1-2 home boxes?  
*Why:* The requirement is ambiguous and no generated question pins it down; the answer affects storage, backup and federation design.  
*Method:* Ask Zeus to choose among the candidate meanings (record the answer). Read Synology HA, TrueNAS replication, Proxmox HA docs; prototype app-volume replication between the Dell 5540 and Beelink with restic/ZFS send or Longhorn DR volumes and measure failover time.

**Q301 [P1]** How should OneMind OS run in the N-5 'cloud' and 'hybrid' deployment modes before a OneMind cloud exists: official cloud images (DigitalOcean/AWS/Hetzner marketplace, cloud-init), a VPS 'cloud node' joined to a home box over Tailscale, or a hosted relay? What do Umbrel, Olares (Olares Space), Cloudron, YunoHost and Coolify ship for cloud installs, and which design hooks are needed now so a future OneMind cloud does not require a re-architecture?  
*Why:* N-5 lists cloud and hybrid modes and M-1 defers a OneMind cloud; no generated question covers running OneMind on cloud VMs or the hooks for a later cloud.  
*Method:* DigitalOcean Marketplace vendor docs, cloud-init docs, Cloudron/YunoHost/Coolify VPS install docs, Olares Space docs; prototype the A/B image as a DO custom image and as a hybrid node joined to the Beelink.

**Q302 [P1]** For P-7 bring-your-own hardware: what hardware compatibility list and detection process does OneMind need (Realtek/Intel NIC and Wi-Fi firmware in the image, NVMe quirks, UEFI vs legacy BIOS, Secure Boot states, eMMC-only mini PCs, USB boot), and how do HAOS (generic-x86-64 image), umbrelOS, TrueNAS, Proxmox and Unraid run community HCLs and installer pre-checks? Should there be a 'OneMind Certified/Works with OneMind' program for third-party hardware?  
*Why:* BYO free install is a requirement, but the generated set focuses on OneMind-built boxes; failures on random hardware are the main support cost for appliance OSes.  
*Method:* Read HAOS generic-x86 docs and issue tracker (top hardware issues), Proxmox/TrueNAS hardware guides, Unraid forums; test the prototype image on the Beelink U55, Dell 5540, a Mac in a VM and two other donor PCs; design a pre-install hardware probe report.

**Q303 [P1]** What does M-5 (long-term alternative to Apple and Google) require concretely for migration: importing iCloud Photos/Google Photos (Takeout, iCloud export), contacts and calendars (CardDAV/CalDAV on iOS and Android), email (self-hosted mail deliverability from residential IPs, port 25 blocks, relay services), password managers, and device backups? Which self-hosted apps (Immich, Nextcloud, Stalwart, Mailcow, Vaultwarden) cover each, and what is the measured friction for a non-technical family?  
*Why:* M-5 is a mission-level requirement with no generated question on the actual switching path; email deliverability in particular decides whether 'replace Google' is honest marketing.  
*Method:* Run a full migration of a test Google account and test Apple ID into a k3s box (Takeout, icloudpd, DAVx5, iOS CalDAV); measure time and failures; read Spamhaus PBL and ISP port-25 policies; test outbound mail via a relay; interview 3-5 families after a trial.

**Q304 [P1]** What power and energy design does an off-grid/homestead OneMind box need: measured idle and load watts per tier (Pi 5, N150, Beelink, Dell, RTX box, Jetson), 12/24 V DC input options, UPS/battery integration with graceful shutdown (NUT, k3s drain, journaled writes), solar charge-controller telemetry (Victron VE.Direct, Modbus) as an app, and wake-on-schedule to save power?  
*Why:* Homestead/off-grid is a core segment and N-6 is native mesh off-grid, but no generated question measures power or graceful shutdown, which protects data and A/B slots during brownouts.  
*Method:* Measure with a USB-C/AC power meter across idle/load for each device; read NUT docs and Victron protocol docs; test k3s + Rugix behaviour on UPS low-battery shutdown and power return; compare HA Green and Umbrel Home published power figures.

**Q305 [P1]** Should OneMind boxes be Matter controllers / Thread border routers and run Home Assistant as the IoT engine (APPS.md proposes this)? Which install form works on a k3s image (HA Container loses Supervisor add-ons), what does Connectivity Standards Alliance membership and Matter certification cost, what does 'Works with Home Assistant' require, and how are Zigbee/Z-Wave/Thread USB radios passed through safely?  
*Why:* IoT & Home is a domain module and greenhouse automation a named profile, yet the generated set never covers Matter/Thread certification or HA-on-k3s packaging.  
*Method:* CSA membership and certification fee pages, Works with Home Assistant program terms, HA install-type docs and the HA community k8s charts; hands-on: HA Container on k3s on the Beelink with a ZBT-2/Thread radio, test Matter commissioning and an A/B OS update.

**Q306 [P1]** How should the OSINT & Intel module be built legally and ethically: which source categories (RSS/news, social platforms, ADS-B/AIS, satellite imagery, public records, dark-web monitoring) are permitted under platform terms and law (CFAA and hiQ v. LinkedIn, GDPR on personal data in OSINT, EU DSA researcher access), how do SpiderFoot, Maltego CE, OpenCTI and IntelOwl handle sources and licensing, and how does the existing NATS-to-ClickHouse 'time machine' data plane scale on a single box?  
*Why:* OSINT is a named domain and internal app (A-4) and the founder has an in-progress data plane; no generated question covers OSINT legality, sources or data-plane fit on an appliance.  
*Method:* Read source platforms' API terms, case law summaries (hiQ, Van Buren), GDPR guidance on OSINT; review SpiderFoot/OpenCTI/IntelOwl licenses and architectures; benchmark ClickHouse + NATS ingest on the Dell 5540 with a 30-day feed sample.

**Q307 [P1]** What regulations apply to the Wellness module's health data on a self-hosted box: FTC Health Breach Notification Rule (amended 2024, applies to health apps), state consumer health data laws (Washington My Health My Data Act, Nevada, Connecticut), GDPR Art. 9 special category data, EU European Health Data Space, and whether HIPAA ever applies? Which wearable and health APIs (Garmin, Oura, Withings, Whoop, Dexcom, Health Connect, HealthKit) permit local storage and AI use, verified from primary terms?  
*Why:* Wellness is called a major focus; the generated questions cover API terms broadly but not the health-data regulatory regime that applies to a vendor shipping a health app, even if self-hosted.  
*Method:* 16 CFR Part 318, RCW 19.373, GDPR Art. 9, EHDS Regulation text; each API's developer agreement with clause numbers and access date; legal summary flagged for counsel.

**Q308 [P1]** How should the Finance module get account data in a sovereign way: US CFPB Section 1033 open-banking rule status, EU PSD2/PSD3 and FIDA, aggregator options (Plaid, MX, SimpleFIN Bridge, GoCardless Bank Account Data, Teller) and their terms on AI use and self-hosting, OFX/QFX direct connect, and how Actual Budget, Firefly III and Maybe handle sync? What security and liability obligations come with storing bank credentials or tokens on a home box?  
*Why:* Finance is a named internal app; the generated set only touches finance APIs in passing and never the open-banking law or aggregator terms that decide feasibility.  
*Method:* CFPB 1033 final rule and litigation status, PSD2 RTS and PSD3 proposals, aggregator developer terms, Actual/Firefly/Maybe repos and licenses; prototype SimpleFIN or GoCardless sync into a self-hosted ledger.

**Q309 [P1]** How should the Projects & Tasks and Knowledge modules integrate with the founder's actual daily system (Obsidian vault as main UI and task engine, Todoist SO/GE/LE/HP projects, Notion migration in progress) without lock-in: Obsidian's license and plugin API for a OneMind sync plugin, Todoist API terms for import/sync, Markdown-vault-as-database patterns, and which open-source PM apps (Plane, Vikunja, Focalboard, AppFlowy) already expose MCP?  
*Why:* A-4 names project management replacing ClickUp/Todoist and the founder's real workflow is Obsidian + Todoist; the generated question on internal apps does not test against that workflow, which is the first dogfood user.  
*Method:* Obsidian license/terms and developer docs, Todoist API docs and terms, Plane/Vikunja/AppFlowy licenses and APIs; prototype a vault-to-OneMind sync with a task round-trip to Todoist.

**Q310 [P1]** How should OneMind protect itself against the failure modes that killed earlier home-server and smart-home products: Sandstorm (business failure), Helm personal server (shutdown), Amahi, WD My Cloud EOL and 2021 remote wipe, Revolv and Insteon shutdowns, Google Stadia/Nest Secure EOL, Synology/QNAP ransomware waves, FreedomBox's slow adoption? What concrete design and business commitments (offline operation after company death, published keys/escrow, data export) follow?  
*Why:* Copying winners is the founder's rule, but no generated question studies the losers; their post-mortems show which sovereignty promises must be engineered in.  
*Method:* Read post-mortems and primary announcements (Sandstorm blog 'what happened', Helm shutdown notice, WD advisories, Insteon closure, FreedomBox Foundation reports); extract failure causes and map each to an OneMind mitigation with requirement IDs.

**Q311 [P1]** Code-level teardowns of the remaining named appliance competitors not covered elsewhere: StartOS (Start9), HexOS, Cloudron, YunoHost, Cosmos Cloud, Runtipi, Puter, Coolify/Dokploy and ClawBox. For each: base OS, install/update/rollback, app format and catalog license, identity, backups, AI features, hardware, business model and team size.  
*Why:* W1 requires these teardowns but the generated questions cover them only by name inside broader questions; the matrix in 02-competitors/ will be incomplete otherwise.  
*Method:* Clone each public repo, read build/install scripts, update modules and manifests with file paths; install each in a VM; record findings in one row per product with sources.

**Q312 [P1]** What chaos, soak and fleet-scale tests must gate a OneMind release: Chaos Mesh/Litmus on k3s (pod kill, network partition, disk full, clock skew), 30-day soak on each tier, repeated power-cuts during update, and a simulated fleet of thousands of devices fetching updates (update server and CDN load, staged rollouts, kill switch)? What do HAOS, balena and Mender publish about staged rollout and canary practice?  
*Why:* Individual failure tests exist in the generated set, but there is no release-level chaos and fleet-scale test plan, which is what keeps a sole developer from shipping a fleet-wide brick.  
*Method:* Chaos Mesh and LitmusChaos docs; balena/Mender staged rollout docs; build a k6 or Locust load test of a static signed-bundle server with 10k simulated clients; define pass/fail gates per tier.

**Q313 [P1]** What is the full cost model of running OneMind as a company for 5 years: CI image build farm (multi-arch, self-hosted vs GitHub Actions), signing HSMs, update CDN egress at 1k/10k/100k devices, test lab hardware, certification, Debian ELTS/Canonical/NVIDIA fees, support staff per 1,000 customers, insurance and legal? At what unit volumes does each tier break even, and how do the DigitalOcean credits change year 1?  
*Why:* Cost modeling exists for BOM and per-device OS support, but there is no company-level operating-cost and break-even model, which the 5-10 year plan needs.  
*Method:* Price lists (GitHub Actions, Cloudflare R2/CDN, DigitalOcean, YubiHSM), comparable company disclosures (Nabu Casa, Framework), support ratio benchmarks; build a spreadsheet with sensitivity analysis and sources.

**Q314 [P1]** How should a sole founder plus AI coding agents plus one outside contributor structure the OneMind codebase and process so the 180-day plan is realistic: monorepo vs polyrepo, which components AI agents can safely author (image recipes, Helm charts, UI) vs which need human review (signing, bootloader, update logic), CI gates, branch protection, contributor onboarding (DCO/CLA), and measured AI-agent productivity on OS/infra work from public studies?  
*Why:* M-6 is about guard rails for one developer; the existing infra already relies on AI agents and a second contributor, but no generated question designs the engineering process itself.  
*Method:* Review how HAOS, Umbrel and Talos organize repos and CI; read published studies on AI coding agent productivity (METR, GitHub research); audit the existing omos repo PR workflow (read-only); propose a repo layout and review policy.

**Q315 [P2]** Is there freedom-to-operate risk from patents on A/B and delta OS updates, OTA for robots/vehicles, QR device onboarding, AI-agent control of devices, and mesh networking? Which patent families do Mender (Northern.tech), Canonical, Sonatus, Airbiquity, Harman, Samsung and the Open Invention Network cover, and would OIN membership protect OneMind?  
*Why:* Selling hardware and an OTA platform creates patent exposure that no generated question addresses; OIN membership is free and protects Linux System components.  
*Method:* Google Patents and USPTO searches by CPC classes (G06F8/65 software updates, H04W4/50), OIN Linux System definition and membership terms, published litigation (e.g. OTA patent suits against automakers).

**Q316 [P2]** When (if ever) should OneMind build its own Android distribution or managed EUD: level 1 (launcher + device-owner app on stock Android), level 2 (GrapheneOS/AOSP fork with OneMind keys and relockable bootloader), or Linux phones (postmarketOS, FuriLabs FLX1, Droidian)? What do public-safety buyers need for EUD fleet management (Android Enterprise, FirstNet certification, open-source MDM such as Headwind), and what does each level cost to maintain monthly?  
*Why:* The 'OneMind EUD' idea was raised and deferred; public-safety and parental-control requirements (U-3) both depend on device management, which no generated question covers for phones.  
*Method:* Android Enterprise and device-owner docs, GrapheneOS build docs and release cadence, CalyxOS/iodéOS team sizes, postmarketOS and FuriLabs device support, Headwind MDM docs; estimate effort from those projects' commit history.

**Q317 [P2]** What lessons does HarmonyOS NEXT offer OneMind beyond the 2019 kill-switch case: its 'super device' distributed model (distributed soft bus, device virtualization, cross-device task continuation), the cost of leaving Android app compatibility, and how OpenHarmony (open-source, Apache-2.0) governance works? Is any OpenHarmony component usable for OneMind's 'every machine is a node' model?  
*Why:* The conversation named HarmonyOS as the platform-sovereignty lesson; its distributed-device model is the closest existing design to N-1/P-6/UX-6, and OpenHarmony is Apache-2.0.  
*Method:* OpenHarmony docs and Gitee repos (distributed soft bus, DSoftBus), Huawei developer docs, academic papers on HarmonyOS distributed architecture, OpenAtom Foundation governance pages.

**Q318 [P2]** How does A-8 (in-platform hardware and software recommendations and comparisons) get trustworthy data: benchmark crowdsourcing from opt-in telemetry, curated lab results, vendor data, affiliate-linked shopping? How do Umbrel, Olares Market, PCPartPicker, LM Studio and Steam hardware surveys source data, and what FTC Endorsement Guides and EU UCPD rules apply when recommendations carry affiliate links (W-4)?  
*Why:* A-8 and W-4 affiliate links have no generated question; mixing recommendations with affiliate revenue is a trust and legal risk for a sovereignty brand.  
*Method:* FTC 16 CFR Part 255 and 2023 Endorsement Guides, EU Unfair Commercial Practices Directive guidance, Amazon Associates operating agreement; review how LM Studio and PCPartPicker present compatibility; design an opt-in benchmark schema.

**Q319 [P2]** What physical-environment ratings do the Edge and Robotics boxes need for greenhouses, barns, vehicles and field kits (operating temperature, humidity, condensation, dust/water IP rating, vibration MIL-STD-810H, 12 V vehicle ignition sensing, fanless thermal design), and what do rugged carrier vendors (Connect Tech, Forecr, OnLogic Karbon, Seeed reComputer Industrial) offer at what price?  
*Why:* HARDWARE.md proposes a greenhouse/mesh Edge box and a rugged Robotics box with no environmental requirements researched; consumer mini PCs fail in these conditions.  
*Method:* Vendor datasheets, IEC 60529 and MIL-STD-810H summaries, case studies from agritech deployments; thermal test of a Pi 5 and Jetson Orin Nano in a sealed enclosure at 40°C.

**Q320 [P2]** Who are the right website, education and forms vendors given sovereignty: Circle.so (data residency, export, API, pricing, AI features) vs self-hosted alternatives (Discourse, Frappe LMS, Moodle); Zoho Forms (data centre regions, DPA, API) vs self-hosted (Formbricks, Tally alternatives); headless CMS (Payload, Strapi, Directus, Ghost); and sales tax/VAT handling for a hardware cart (Shopify, Medusa, Stripe Tax)? Does using hosted Circle and Zoho contradict the brand, and what is the exit path?  
*Why:* W-2 and W-5 name specific hosted vendors; generated questions compare stacks but never test the sovereignty contradiction or data export of these specific vendors.  
*Method:* Circle.so and Zoho Forms terms, DPA and export docs, pricing pages; Payload/Directus/Ghost licenses; build a cost and lock-in table; ask Zeus which trade-off he accepts.

**Q321 [P2]** What sequenced learning curriculum should Zeus follow so he can make and review the foundation decisions himself: Linux boot chain, partitions and filesystems, image builders, A/B updates, systemd, k3s internals, NATS, PKI and signing, Secure Boot/TPM, ROS 2 and Jetson? Which primary resources (official docs, courses, books) are best, and how should lessons map to the build milestones?  
*Why:* W17 requires a founder learning path and the conversation recorded that Zeus is learning as he goes; no generated question produces it.  
*Method:* Survey official docs and well-regarded courses (Linux Foundation LFS courses, Bootlin embedded Linux training materials, k3s docs, NATS by Example, ROS 2 tutorials, NVIDIA DLI Jetson courses); sequence them against the 180-day plan with estimated hours.

**Q322 [P2]** How should 'open the box straight from a Mac' (UX-8) work natively: Bonjour/mDNS discovery, Finder SMB/WebDAV mounts, Time Machine target support (Samba vfs_fruit), a menu-bar app (Tauri/Swift), Apple Shortcuts integration, and Mac-to-box AI agent access? What do Synology, Umbrel and TrueNAS provide on macOS?  
*Why:* UX-8 names the Mac explicitly and the founder's daily machine is a Mac, but no generated question covers macOS-native integration beyond generic client frameworks.  
*Method:* Samba vfs_fruit docs, Apple Time Machine network requirements, Synology/Umbrel macOS docs; prototype SMB + Time Machine target on the k3s box and test from the Mac.

**Q323 [P2]** How should cameras and recordings (Frigate NVR, doorbells, greenhouse and security cameras, robot cameras) be handled legally and technically: audio-recording consent laws (two-party consent states), GDPR household exemption limits when cameras see public space or neighbours, retention, AI detection on Coral/Hailo/GPU, and keeping footage local while giving agents access?  
*Why:* Security cameras are part of the homestead mission (context/01) and a top self-hosted app category, but no generated question covers their legal or AI-access constraints.  
*Method:* State wiretap statutes summary, CJEU Ryneš ruling and EDPB video guidelines 3/2019, Frigate docs; benchmark Frigate detection on Pi 5 + Hailo and Beelink + Coral.

## Second brief: kernel/image ownership, Mac dev path, ecosystem, physical AI (added 2026-11-10, F-1…F-10)

**Q324 [P0]** What does "OneMind owns its kernel" realistically mean for a sole developer with AI agents? Compare a stock distro kernel, an upstream LTS kernel with a OneMind config (the HAOS/ChromeOS approach), vendor BSP kernels (Raspberry Pi, NVIDIA L4T), and a patched kernel (PREEMPT_RT, security). Cover maintenance hours per year, security patch latency, and board and NVIDIA compatibility.  
*Why:* F-7: the founder wants no limitations. This is "a very big determination".  
*Method:* kernel.org/CIP SLTS lifecycles; HAOS `Documentation/kernel.md`; ChromeOS and SteamOS kernel practices; the L4T kernel sources and update cadence.

**Q325 [P0]** Is any non-Linux kernel path (Zircon/Fuchsia, seL4, Redox, HarmonyOS HongMeng-style microkernel) viable for OneMind in 5–10 years, or is "own image + own kernel config on Linux" the only realistic route? What did Huawei and Google spend to build theirs?  
*Why:* F-7; it prevents a costly detour.  
*Method:* official project docs, public statements and costs, driver ecosystems.

**Q326 [P0]** Which image build tool best fits Debian/L4T appliance images built from a Mac via CI: debos, mkosi, Rugix Bakery, bootc/osbuild, Kairos, Buildroot or Yocto? Consider reproducibility, signing, multi-arch, and Pi 5 and Jetson support.  
*Why:* F-7/F-8.  
*Method:* tool docs and repos; a VM lab build of a minimal image.

**Q327 [P0]** What is the best development setup on an Apple Silicon Mac for building OneMind? Options include UTM/QEMU, Lima/Colima, OrbStack, Docker buildx multi-arch, k3d/kind, cross-compiling kernels, and remote x86/arm64 builders and GitHub Actions arm64 runners. Which steps cannot be done on macOS (e.g. Jetson flashing via SDK Manager, Isaac Sim)?  
*Why:* F-8.  
*Method:* official docs for each tool; NVIDIA SDK Manager host requirements; Isaac Sim requirements.

**Q328 [P1]** How did Android, ROS, Home Assistant, SteamOS, the NVIDIA Jetson partner ecosystem, Viam and Foxglove become the default platforms third parties build on? What SDK, certification, distribution and revenue terms made it work, and what should the OneMind Marketplace copy?  
*Why:* F-4/F-5.  
*Method:* developer docs, partner program terms, public metrics.

**Q329 [P1]** What is the minimal end-to-end "connect a robot → use OneMind OS" flow (discovery, QR/USB/network onboarding, adapter or driver auto-install, capability detection, safety gates, MHS/MCP exposure)? Which robot platforms (LeRobot SO-100/101, Unitree, TurtleBot 4, PX4 drones, Jetson-based kits) should be first-class at launch?  
*Why:* F-3.  
*Method:* vendor SDK docs, ROS 2 drivers, MHS preview info, Matter/DPP commissioning patterns.

**Q330 [P1]** What does NVIDIA's announced 2025–2026 roadmap (GTC, CES, KubeCon NA 2026: Jetson Thor and its successors, GR00T, Cosmos, Isaac, Omniverse, Newton, NIM, DGX Spark/Station) imply for OneMind's hardware tiers and software support windows? How can OneMind support new releases on day one while staying hardware-agnostic?  
*Why:* F-1/F-2.  
*Method:* NVIDIA newsroom, developer blogs, release notes, product pages.

**Q331 [P2]** Which physical-AI shifts expected for 2028–2036 (humanoids at home, on-device VLA and world models, robot-as-a-service, new safety regulation) would break or strengthen the chosen foundation? What design hedges keep OneMind the default OS through them?  
*Why:* F-1/F-4.  
*Method:* primary roadmaps and regulations, credible forecasts labelled SECONDARY, scenarios from W15.

**Q332 [P1]** How should hybrid self-hosted + cloud work (F-6) without lock-in? Options include an optional OneMind Cloud relay, burst GPU, backups and fleet management. How do balenaCloud, Olares Space, Umbrel and Home Assistant Cloud handle it?  
*Why:* F-6.  
*Method:* vendor docs and pricing.

**Q333 [P0]** What exactly should the second ultracode build session implement first, and in what order, to prove the core: image pipeline, kernel config, signed A/B updates, k3s, capability layer, dashboard MVP, robot onboarding MVP? What are its acceptance tests?  
*Why:* F-9.  
*Method:* synthesize from 01, 20 and 28; Blueprint A01–A24.

**Q334 [P0]** Can one foundation (base OS + image + k3s/RKE2 + capability layer) be **as simple as a Raspberry Pi** for a 4–8 GB Pi 5 greenhouse node **and** scale to a multi-node GPU enterprise cluster running Isaac Sim, with no product switch? Measure the footprint on the smallest supported node, and say what must be optional or lazy-loaded. Which competitors achieve "same product at every scale" (balena, Talos/Omni, Red Hat Device Edge → OpenShift, Ubuntu Core → Ubuntu Pro, Olares), and how?  
*Why:* F-14, the founder's core promise.  
*Method:* vendor docs; VM lab footprint measurement; k3s resource profiling; minimal vs full profile design.

**Q335 [P0]** Which plugin extension points must the OneMind base OS expose from day one so that every plugin type can be added without forking the OS? The types are Market apps, dashboard widgets, desktop and shell plugins, device, driver and protocol adapters, AI skills, agents and tools, automations, and OS/image profiles. What do the proven ecosystems (Omarchy, Home Assistant + HACS, Olares OAC, Umbrel community stores, Backstage, Obsidian, VS Code, Grafana, WordPress, ROS) teach about manifests, sandboxing, signing, review tiers, compatibility ranges, malware incidents and community growth?  
*Why:* A-5 and A-6, plus the founder's explicit priority. It shapes the foundation.  
*Method:* read each ecosystem's plugin docs and validator code; collect security incident reports; draft a OneMind plugin manifest and test it against the 7 plugin types.
