# OneMind OS: Base OS and Orchestration Research

Date: 2026-11-10. Method: official docs, repos, release notes opened via WebFetch/WebSearch. Page text was summarized by a fetch helper, so exact figures worth betting on should be re-checked on the cited page. Anything I could not confirm is marked **UNVERIFIED**. Search-result-only claims are tagged (search) and secondary sources (blogs, press) are tagged (secondary).

---

## PART A: Base OS candidates

### A.0 Quick comparison

| OS | Update model | Rollback | Support length | x86_64 / aarch64 | Pi 5 | Jetson | NVIDIA story | Provisioning | License / backer |
|---|---|---|---|---|---|---|---|---|---|
| Fedora CoreOS | rpm-ostree, OCI transport via quay.io since F42 plan | Multiple OSTree deployments, switch at boot | Streams, no LTS found | x86_64, AArch64, s390x | Only Pi 4 guide | UNVERIFIED | UNVERIFIED (ucore/ublue layers exist) | Ignition | Fedora Project / Red Hat |
| Fedora IoT | rpm-ostree (Atomic) | OSTree | Fedora ~13 mo per release (UNVERIFIED here) | aarch64 reference: Pi 4, Pi 3 | Not official; community Fedora 43 image (search) | UNVERIFIED | UNVERIFIED | Ignition/ cloud-init style (UNVERIFIED) | Fedora Project |
| bootc (Fedora / CentOS Stream / RHEL image mode) | OCI container image is the OS update, transactional | bootc rollback (page did not state; UNVERIFIED) | RHEL 10: 10-year life cycle | Per-distro | n/a | n/a | Bake driver into your image | Image build; ignition not needed | CNCF Sandbox (bootc); Red Hat |
| Universal Blue | bootc images on top of Fedora Atomic | bootc | Community | x86_64, aarch64 (uCore) | n/a | n/a | Proprietary NVIDIA pre-installed on some images | Image-based | Community |
| Talos Linux | Immutable, API-only, image upgrade | Not verified on page; UNVERIFIED | Latest v1.14.5 (2026-10-26) | Yes | `rpi5` overlay (official list) | Only Jetson Nano overlay; Orin PR open | Extensions (OSS + proprietary) + GPU Operator | Machine config via API | MPL-2.0; Sidero |
| Kairos | A/B atomic OCI-image upgrades | A/B | Community; no LTS found | amd64, arm64 | Not in current docs (Pi 3/4 only, search) | Orin NX, AGX Orin, AGX Thor build paths | Via nvidia-l4t on Jetson; GPU Operator guide for Thor | cloud-config, AuroraBoot | CNCF Sandbox; Spectro Cloud |
| Flatcar | Atomic, A/B-style, Nebraska | Update-failure fallback (UNVERIFIED wording) | LTS 18 months, new LTS yearly | amd64, arm64 (search) | Pi 4 only, "early stages" | UNVERIFIED | Prebuilt NVIDIA sysext (amd64 confirmed) | Ignition | Apache-2.0; CNCF Incubating |
| Bottlerocket | Full image A/B | Auto + `signpost rollback-to-inactive` | K8s variants 1.31 to 1.37 | x86_64, aarch64 | Not mentioned | no | NVIDIA variants only for AWS instance types | API/TOML | Apache-2.0/MIT; Amazon. Bare-metal K8s variants no longer supported |
| SUSE SL Micro | transactional updates (details UNVERIFIED) | UNVERIFIED | 6.2 EOL 2029-11-30 (secondary) | yes | UNVERIFIED | Jetson Orin production support | SolidDriver out-of-tree modules on Jetson | UNVERIFIED | SUSE |
| Ubuntu Core | Snap-based, atomic | UNVERIFIED in my fetches | 10 yr, +5 with Pro Legacy add-on | amd64, arm64, armhf | Pi 5 support added in Core 24 | Install guide exists; contents UNVERIFIED | UNVERIFIED | cloud-init supported | Canonical |
| balenaOS | Yocto, A/B rootfs | Auto rollback | Tied to Yocto LTS branches | generic-amd64, aarch64 | Yes (`raspberrypi5`) | Orin family devkits listed | UNVERIFIED | Fleet via balenaCloud | Apache-2.0 (COPYING file); balena |
| NixOS | Declarative generations | Boot-menu generations | 26.05: 7 months, ends 2026-12-31 (search) | yes | Needs unstable image (search) | jetpack-nixos UNVERIFIED | UNVERIFIED | Nix config | Community |
| Debian stable | Package | None native | 13: full to 2028-08-09, LTS 2030-06-30, ELTS 2035-06-30 | page did not list | UNVERIFIED | UNVERIFIED | non-free packages (UNVERIFIED) | preseed/cloud-init UNVERIFIED | Community |
| Omarchy (Arch) | Rolling pacman | Btrfs + Snapper snapshots (secondary) | Rolling | UNVERIFIED | UNVERIFIED | no | UNVERIFIED | Installer | MIT; DHH/37signals |

### A.1 Fedora CoreOS, Fedora IoT, bootc, Universal Blue

- **Fedora CoreOS (FCOS).** Zincati applies updates via rpm-ostree, supports `rollout_wariness` (0.0 eager to 1.0 conservative), and three reboot strategies including weekly UTC maintenance windows. rpm-ostree keeps multiple deployments and switches at boot. Source: https://raw.githubusercontent.com/coreos/fedora-coreos-docs/main/modules/ROOT/pages/auto-updates.adoc. Architectures x86_64, AArch64, s390x; Pi 4 has a guide, no other Pi: https://raw.githubusercontent.com/coreos/fedora-coreos-docs/main/modules/ROOT/pages/platforms.adoc. k0s CI tests FCOS stable: https://docs.k0sproject.io/stable/system-requirements/.
- **bootc status in Fedora (late 2026).** FCOS moved updates to OCI transport (quay.io/fedora/fedora-coreos), accepted for F42, still using rpm-ostree and not bootc yet: https://fedoraproject.org/wiki/Changes/CoreOSOstree2OCIUpdates. On 2026-08-26 a proposal (issue #2214) to unify FCOS and Fedora bootc outputs started; a working group formed Sep 2026 and as of Oct 7 no final technical decisions were recorded: https://github.com/coreos/fedora-coreos-tracker/issues/2214. Search result says the proposal targets Fedora 46 (search). Takeaway: FCOS is in a multi-release transition; building on it today means riding that migration. The proposal itself is Fedora-only; upstream bootc stays distro-agnostic.
- **bootc project.** CNCF Sandbox; transactional in-place OS updates delivered as OCI images; not tied to one distro: https://bootc.dev/.
- **RHEL image mode.** RHEL 8/9/10 have a ten-year life cycle (5 full + 5 maintenance, plus 4 extended-life phase per graphic); even minors get 6 years via ELCP, 10.10 gets 9: https://access.redhat.com/support/policy/updates/errata. The RHEL 10 image-mode doc returned 403, so image-mode specifics (rollback, NVIDIA, arches) are **UNVERIFIED**. RHEL is commercially licensed (subscription): UNVERIFIED on exact terms; CentOS Stream bootc license not fetched.
- **Fedora IoT.** Official aarch64 reference platforms in the search snippet are Pi 4 (4B/CM4) and Pi 3, UEFI-focused (https://doc.fedoraproject.org/nl/iot/reference-platforms/ via search). Pi 5 works on Fedora 43 via community images and a Copr kernel; I found no official IoT Pi 5 image (search; see https://lists.fedoraproject.org/archives/list/arm@lists.fedoraproject.org/thread/GMS3PREWUOROENCSFZTWGUDOXLOB6IH4/).
- **Universal Blue.** Images built from Fedora Atomic OCI images (Aurora, Bazzite, Bluefin, uCore); Bazzite ships proprietary NVIDIA on NVIDIA images; uCore published for x86_64 and aarch64; a May 2026 community dashboard shows non-trivial failed-build rates (secondary): https://github.com/ublue-os, https://castrojo.github.io/bootc-ecosystem/overall/. Treat as community, not LTS.

### A.2 Talos Linux (Sidero)

- Kubernetes-only, immutable, single declarative gRPC API, no shell, runs etcd and control plane: https://docs.siderolabs.com/talos. Latest stable v1.14.5 (2026-10-26), Linux 6.18.58, etcd 3.7.3; v1.15.0-beta.0 on 2026-11-10: https://github.com/siderolabs/talos/releases.
- License MPL-2.0. Omni (fleet mgmt) is BSL 1.1, SaaS or self-hosted. Enterprise: $1,000/node/year, 10-node minimum, FIPS 140-3 builds; Omni can run containers on Talos at single-node edge without Kubernetes: https://www.siderolabs.com/platform/talos-os-for-kubernetes/.
- SBC overlays: `rpi_generic` (Pi 4/CM4), `rpi5` (Pi 5), only `jetson_nano` for Jetson: https://github.com/siderolabs/overlays. Pi 5/CM5 caveat from community: official Image Factory does not support CM5 (search; secondary). Jetson Orin installers (`jetson_orin_nano`, `jetson_agx_orin`) are an open PR, not merged, no GPU support in that PR: https://github.com/siderolabs/sbc-jetson/pull/23.
- NVIDIA: system extensions `nonfree-kmod-nvidia` + `nvidia-container-toolkit` (proprietary) or OSS modules; use GPU Operator v26.3.1+ with driver/toolkit disabled and `hostPaths.driverInstallDir=/usr/local`; GB10 arm64 (DGX Spark) needs `arm64.nobti`: https://docs.siderolabs.com/talos/v1.13/configure-your-talos-cluster/hardware-and-drivers/nvidia-gpu-proprietary.md.
- Provisioning: machine config via API, Image Factory schematics (extensions + overlays). Rollback/A-B specifics: **UNVERIFIED** from fetched pages.
- Support: community free tier; enterprise paid.

### A.3 Kairos (CNCF Sandbox)

- Immutable meta-distribution for bootable Kubernetes OS images, "distribution agnostic", A/B atomic upgrades triggered via container registry, optional P2P mesh bootstrap, contributed by Spectro Cloud: https://raw.githubusercontent.com/kairos-io/kairos/master/README.md, https://kairos.io/docs/.
- Hadron (musl, from-scratch base) is the default prebuilt; Ubuntu/openSUSE/Alma flavors work for custom builds but Ubuntu/openSUSE prebuilt repos are no longer actively updated; k3s and k0s via the provider; Pi 4 build example with arm64: https://kairos.io/docs/reference/image_matrix/.
- Raspberry Pi: current docs list Pi 3 and 4 (64-bit); older docs excluded Pi 5 due to U-Boot (search; secondary on current state): https://kairos.io/docs/installation/raspberry/.
- Jetson: models `nvidia-jetson-agx-orin` and `nvidia-jetson-orin-nx` (L4T r36.x, Ubuntu 22.04) and `nvidia-jetson-thor` (L4T r39.2, Ubuntu 24.04 or Hadron), built with kairos-init >= 0.9.0; Orin Nano not listed; dev docs may be inaccurate: https://kairos.io/docs/installation/nvidia-jetson-images/.
- Release: v4.1.0 (May 2026) adds phone-home with AuroraBoot fleet mode, Hadron v0.2.0, Ubuntu 26.04 in kairos-init: https://kairos.io/blog/2026/05/15/kairos-v4-1-0-hadron-ubuntu-boot-install-foundations/ (search).
- License: not stated on pages I read, **UNVERIFIED** (README says open source). Production adopters: **UNVERIFIED**.

### A.4 Flatcar Container Linux (CNCF Incubating, accepted 2024-08-02)

- Atomic, automatic background updates applied on reboot, Ignition provisioning, Alpha/Beta/Stable channels; LTS channel 18 months, new LTS every 12 months with 6-month overlap; Apache-2.0: https://raw.githubusercontent.com/flatcar/Flatcar/main/README.md. CNCF: https://www.cncf.io/projects/flatcar/.
- Pi 4 support "early stages, not thoroughly tested", UEFI via community firmware (search): https://flatcar.org/docs/latest/installing/bare-metal/raspberry-pi. NVIDIA: prebuilt sysext each release, open and non-open flavors, amd64 confirmed; ARM64 NVIDIA builds appeared in past release notes (search): https://www.flatcar.org/docs/latest/os-config/host-config/using-nvidia/.
- Maintained by the Flatcar Project Contributors (LF Projects); Microsoft/Kinvolk lineage not verified. Arm64 general support wording: **UNVERIFIED** from fetched pages.

### A.5 Bottlerocket

- Full-image update with A/B partitions, TUF-secured, auto rollback plus manual `signpost rollback-to-inactive`; x86_64 and aarch64; K8s variants 1.31-1.37; NVIDIA variants tied to AWS instance types; bare-metal K8s variants "no longer supported"; Apache-2.0/MIT; Amazon-originated: https://github.com/bottlerocket-os/bottlerocket. Not a fit for a self-hosted appliance.

### A.6 SUSE (SL Micro, Elemental)

- Elemental: container-image-based OS management for Rancher, installs OS and provisions K3s/RKE2 clusters; Elemental Toolkit builds OS images: https://raw.githubusercontent.com/rancher/elemental/main/README.md.
- SL Micro 6.2 released 2025-11-04, EOL 2029-11-30 (secondary): https://endoflife.date/suse-linux-micro. Jetson Orin moved to production support on SL Micro 6.0/6.1/6.2 (JetPack 6.2.1/6.2.2), Thor planned for SUSE Linux 16.1, GPU drivers via SolidDriver out-of-tree modules (2026-03-16): https://www.suse.com/c/suse-to-deliver-enterprise-grade-edge-ai-on-nvidia-jetson. Pi 5 and rollback internals: **UNVERIFIED**. Pricing/license: **UNVERIFIED**.

### A.7 Ubuntu Core

- Core 24 (Jun 2024): 10 years security maintenance, +5 via Ubuntu Pro Legacy; Core 26 released 2026-05-14 on Ubuntu 26.04, standard to May 2036, Legacy to May 2041; arches amd64, arm64, armhf: https://documentation.ubuntu.com/core/reference/support-duration/, https://documentation.ubuntu.com/core/reference/release-notes. Pi 5 support added in Core 24; cloud-init supported. Jetson and rollback mechanics: **UNVERIFIED**. Snap-centric packaging is a poor fit for a k8s/OCI app platform (my judgment, not sourced).

### A.8 balenaOS

- Yocto-based, A/B rootfs with bootloader-managed rollback, balenaEngine (Docker fork): https://docs.balena.io/reference/OS/overview/2.x/, https://github.com/balena-os/meta-balena. Supports `raspberrypi5`, multiple Jetson Orin devkits and carrier boards, `generic-amd64`: https://docs.balena.io/reference/hardware/devices/. Strong multi-hardware coverage, but tied to Docker engine/balenaCloud workflow.

### A.9 NixOS, Debian, Omarchy, OTA frameworks, Yocto

- **NixOS.** Boot-menu generations rollback: https://nixos.org/manual/nixos/stable/. 26.05 released 2026-05-30, 7 months of support to 2026-12-31 (search): https://nixos.org/blog/announcements/2026/nixos-2605/. Pi 5 images need nixos-unstable (search): https://wiki.nixos.org/wiki/Raspberry_Pi_5. Short support window conflicts with "long-term support"; powerful for a single-dev declarative build but steep for customers.
- **Debian stable.** Debian 13 "trixie" released 2025-08-09; full support to 2028-08-09, LTS 2030-06-30, ELTS 2035-06-30: https://www.debian.org/releases/, https://wiki.debian.org/LTS. No native atomic update; pair with Mender/RAUC for A/B.
- **Omarchy / Arch (desktop edition option).** "Beautiful, fun & agentic Linux distribution by DHH", MIT, ~46.7k stars: https://github.com/basecamp/omarchy. Hyprland and Arch base are widely known but the repo page I opened did not say so, **UNVERIFIED on those pages**. Extension model (secondary, instagit/third-party summaries of repo): hooks in `~/.config/omarchy/hooks/<event>` and `<event>.d/` (e.g. `theme-set`, `post-update`), themes in `~/.config/omarchy/themes/<name>/`, Btrfs+Snapper snapshots with Limine integration. Manual lives at https://learn.omacom.io/ (not fetched). Rolling release means no LTS and no atomic OTA. It is a desktop/dev-workstation edition, not a server base.
- **Mender.** A/B updates, bootloader reverts if not committed, delta updates, managed or standalone mode, Yocto and Debian-family clients, Northern.tech: https://docs.mender.io/overview/introduction.
- **RAUC.** LGPL-2.1+, symmetric A/B or recovery layouts, signed (optionally encrypted) bundles, HTTP streaming: https://github.com/rauc/rauc.
- **SWUpdate.** GPLv2 + OpenSSL exception, rootfs/kernel/bootloader/MCU updates, delta via librsync, hawkBit connector; A/B not stated on page: https://github.com/sbabic/swupdate.
- **Yocto.** Wrynose (6.0) LTS to April 2030, Scarthgap (5.0) LTS to April 2028; current docs 6.1 (blacksail) dev: https://wiki.yoctoproject.org/wiki/Releases, https://docs.yoctoproject.org/. Highest effort for a sole developer (own BSP per board).

### A.10 What existing products build on

| Product | Base | Evidence |
|---|---|---|
| umbrelOS | Debian-based, Docker Compose apps; Pi 5, x86 (EFI), license PolyForm Noncommercial 1.0.0 (commercial use needs partner agreement) | License/hardware: https://github.com/getumbrel/umbrel. Debian claim from press only (secondary): https://www.cnx-software.com/2026/04/12/umbrelos-a-debian-based-personal-home-cloud-os-with-a-slick-user-interface/. Official page does not state base. |
| Olares | Kubernetes-based, incorporates K3s and KubeSphere; installs on Ubuntu 22.04-25.04 or Debian 12/13 or via ISO (x86-64); AGPL-3.0; GPU pooling with time/memory slicing | https://github.com/beclab/Olares. Exact K8s distro in use not stated on page. |
| Home Assistant OS | Buildroot, RAUC OTA, Docker Engine, Apache-2.0; SBCs plus x86-64 UEFI; A/B not stated on page | https://github.com/home-assistant/operating-system |
| ZimaOS | Evolved from CasaOS, built using Buildroot, x86-64 UEFI only listed; OTA and offline update; RAUC suggested by repo files (inference); license not stated | https://github.com/IceWhaleTech/ZimaOS |
| StartOS | "Open-source Linux distribution", MIT; repo has `debian/` and `apt/` dirs (suggests Debian packaging, not confirmed); arches **UNVERIFIED** | https://github.com/Start9Labs/start-os |

Pattern: consumer appliances (Umbrel, ZimaOS, HAOS) run Docker/Compose, not Kubernetes. Olares is the Kubernetes-based one and ships on Ubuntu/Debian rather than a bespoke immutable OS.

---

## PART B: Orchestration layer

### B.1 Options

| Option | Footprint (sourced) | Arches | Multi-node join | Edge/disconnected | GPU fit |
|---|---|---|---|---|---|
| Docker/Compose | **UNVERIFIED** (not researched) | n/a | none | n/a | nvidia-container-toolkit |
| Podman + Quadlet | systemd generator turns `.container/.kube/.pod/.volume/.network/.build` unit files into services; `AutoUpdate=registry|local`; requires cgroups v2 | n/a | none (single host) | Works offline | CDI (UNVERIFIED here) |
| k3s | Min server 2 CPU/2 GB, agent 1 CPU/512 MB; measured server-with-workload ~1.6 GB RAM both on x86 and Pi 4B (30% core on Pi 4B); idle agent ~270 MB | x86_64, armhf, arm64 | `K3S_TOKEN` + `--server https://...`; HA embedded etcd needs 3 servers | Single binary; SQLite or etcd; SD cards unsuitable | NVIDIA GPU Operator lists K3s as supported distro |
| k0s | Controller 1 GB/1 vCPU, worker 0.5 GB, single node 1 GB/1 vCPU (approximations) | x86_64, aarch64, armv7l, riscv64 (no binaries/CI) | UNVERIFIED | UNVERIFIED | Listed as Mirantis k0s in GPU Operator platform page |
| MicroK8s | "as little as 540 MB"; recommends 4 GB RAM / 20 GB disk; snap-based | arch list not stated on page | multi-node guide exists | UNVERIFIED | Listed in GPU Operator platform page |
| Full k8s (kubeadm etc.) | UNVERIFIED | all | heavy | heavy | broad |
| KubeEdge | EdgeCore "extremely lightweight" (no figures); CNCF graduated (Oct 2024); MetaManager SQLite cache for offline | UNVERIFIED | cloud-edge WebSocket | Designed for it | UNVERIFIED |
| OpenYurt | CNCF Incubating; node pools; v1.7.0 on 2026-05-06; edge autonomy listed | UNVERIFIED | pools | Yes | UNVERIFIED |
| Akri | CNCF Sandbox; exposes leaf devices (ONVIF, udev, OPC UA) as K8s resources | n/a | n/a | n/a | not GPU focused |

Sources: https://docs.k3s.io/installation/requirements, https://docs.k3s.io/reference/resource-profiling (k3s v1.26.5; Pi 4B 8 GB, test is "server with workload" incl. Prometheus/Grafana, not idle), https://docs.k3s.io/datastore/ha-embedded, https://docs.k3s.io/installation/packaged-components, https://docs.k0sproject.io/stable/system-requirements/, https://canonical.com/microk8s/docs/getting-started, https://github.com/kubeedge/kubeedge, https://github.com/openyurtio/openyurt, https://github.com/project-akri/akri, https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html.

k3s on Pi notes: enable cgroup memory flags in cmdline, use SSD not SD/eMMC due to etcd writes (same docs). k3s bundles CoreDNS, Traefik, local-storage, metrics-server, servicelb and auto-applies manifests from the manifests directory.

### B.2 GPU stack

- **NVIDIA GPU Operator 26.7.2** (latest on release notes page; date not shown). K3s support added in 26.3.0, NRI plugin avoids containerd config changes (helps k3s/k0s/RKE2). DRA Driver for NVIDIA GPUs added to the Operator in 26.7.0 via `GPUCluster` resource; needs K8s >= 1.34.2, driver >= 580, CDI runtime: https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/release-notes.html.
- **Platform support:** Ubuntu 22.04/24.04/26.04, RHEL 8/9/10, RHCOS, Rocky, SLES; K8s 1.33-1.37; distros incl. RKE2, K3s, k0s, MicroK8s, OpenShift. ARM64 supported only with NVIDIA GPUs on the PCI bus (DGX Spark, GB200 NVL72, IGX Orin discrete GPU, AWS G5g). **Jetson not supported**: "only supports platforms using discrete GPUs": https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/platform-support.html. Consumer GeForce/RTX 40/50 support: **UNVERIFIED** (page lists RTX PRO / RTX A-series / Quadro RTX).
- **k8s-device-plugin v0.17.1:** time-slicing (no memory isolation), MPS experimental as of v0.15.0, CDI strategies, Tegra needs nvidia-container-toolkit >= 1.11.0: https://github.com/NVIDIA/k8s-device-plugin.
- **DRA driver (k8s-dra-driver-gpu):** ComputeDomains (MNNVL) officially supported; GPU kubelet plugin "not yet officially supported" and disabled by default; needs K8s 1.32+ with DRA: https://github.com/NVIDIA/k8s-dra-driver-gpu. (Operator page above is slightly ahead of the repo README; treat DRA for single GPUs as maturing.)
- **HAMi:** CNCF Incubating, GPU virtualization/sharing across vendors, formerly k8s-vGPU-scheduler: https://github.com/Project-HAMi/HAMi. Specific memory/core-limit mechanics: **UNVERIFIED**.
- **KAI Scheduler:** CNCF Sandbox, Apache-2.0, gang scheduling, hierarchical queues, GPU sharing, DRA support, built on kube-batch: https://github.com/NVIDIA/KAI-Scheduler. Aimed at large clusters; overkill for single boxes.
- **Dynamo:** Apache-2.0 datacenter inference orchestration above vLLM/SGLang/TensorRT-LLM; disaggregated serving, KV-aware routing; Grove is the topology-aware gang-scheduling operator: https://github.com/ai-dynamo/dynamo. Cluster/enterprise tier only.
- **Jetson Kubernetes status.** GPU Operator: not supported, Jetson request issue #1453 closed as not planned (search): https://github.com/NVIDIA/gpu-operator/issues/1453. Community pattern is K3s + standalone device plugin + nvidia-container-toolkit + CDI on JetPack 6.1 (user report, unverified). JetPack 7 series aligns Jetson with SBSA; Thor MIG is a technology preview in JetPack 7.2 (search): https://developer.nvidia.com/embedded/jetpack/downloads/archive-7.2. Kairos docs link a GPU Operator guide for `nvidia.com/gpu` on Thor, but I did not open it, so treat Thor GPU Operator viability as **UNVERIFIED**. Treat Jetson k8s as "works with effort, not an NVIDIA-supported matrix".
- **Edge disconnected operation.** Plain k3s agents/servers keep running pods when the control plane is unreachable (general Kubernetes behavior; not sourced here). KubeEdge/OpenYurt add explicit autonomy caches but add components and operational burden.

---

## PART C: Recommendation

### C.1 Matrix by tier

| Tier | OS layer | Orchestrator | Why | Main risk |
|---|---|---|---|---|
| Lite x86 CPU box | Kairos (Ubuntu 24.04 or Hadron flavor), image-based A/B | k3s single node | Same stack as other tiers; k3s min 2 GB; A/B rollback | Kairos is CNCF Sandbox; prebuilt Ubuntu flavor repos not actively updated (build yourself with kairos-init) |
| Pro GPU box (RTX) | Same image + NVIDIA driver baked into the image | k3s + GPU Operator (driver/toolkit disabled if baked) or device plugin | GPU Operator officially supports K3s and Ubuntu | Consumer RTX in GPU Operator matrix **UNVERIFIED**; driver/kernel pinning per image |
| Pi/edge | Pi 4/CM4: Kairos or Talos `rpi_generic`; Pi 5: Talos `rpi5` overlay, balenaOS, or Ubuntu Core 24+ | k3s agent or single node (Pi 4B measured ~1.6 GB with a monitoring workload) | Pi 5 not in Kairos current docs | Pi 5 coverage is the weakest link; NVMe/SSD required |
| Jetson/robotics | Kairos Jetson model (Orin NX, AGX Orin, Thor), or SUSE SL Micro, or balenaOS, all vendor-L4T based | k3s + device plugin + CDI (no GPU Operator on Jetson) | Only Kairos has documented Orin NX, AGX Orin, Thor builds in OCI-image form (Orin Nano missing) | JetPack/L4T lock-in; NVIDIA does not support Operator; Talos Orin not merged |
| Cluster/enterprise | Talos (API-only, immutable) or the same Kairos image, k3s/RKE2 | Kubernetes + GPU Operator + DRA + KAI + HAMi/Dynamo as needed | Talos has official NVIDIA extension path and Image Factory; enterprise support is purchasable | Talos is Kubernetes-only, no general host; Omni is BSL |
| Desktop edition (optional) | Omarchy (Arch, rolling, MIT) | none | Hooks/themes model suits a personalized dev desktop; Btrfs snapshots (secondary) | Rolling with no LTS and no atomic OTA; do not make it the product base |

### C.2 Single best foundation for a sole developer

**k3s everywhere as the app platform, on a Kairos-built immutable image (Ubuntu 24.04 flavor via kairos-init), with the OS layer kept swappable.**

Reasoning, from sources:
1. One orchestrator spans all tiers: k3s runs on x86_64 and arm64, needs 2 GB for a server, is a supported distro for the NVIDIA GPU Operator, and Jetson works with device-plugin CDI.
2. Kairos is the only candidate I verified that covers x86, arm64 (Pi 4), and Jetson Orin NX/AGX Orin/Thor, with OCI-image A/B upgrades, k3s/k0s providers, and distro choice. Ubuntu base keeps NVIDIA drivers, L4T repos, and GPU Operator on supported ground (GPU Operator lists Ubuntu 22/24/26).
3. Your OneMind cluster already uses Argo CD and NATS; k3s keeps the same manifests on the box and in the cluster.
4. "Not limited later": an application layer defined by Helm/Argo manifests works on Talos, RKE2, or a different OS. Only the OS image recipe changes. Talos can be the enterprise-cluster option without rewriting the app platform.

Honest risks and mitigations:
- Kairos maturity (CNCF Sandbox, backed by Spectro Cloud, license text unconfirmed): verify license, pin versions, keep a Talos fallback for cluster tier. User-controlled update timing and LTS: not found in Kairos docs, **UNVERIFIED**; you would implement update policy yourself via the agent/AuroraBoot and consider a longer-lived Ubuntu LTS (Ubuntu 24.04 follows 10-year model for Core; standard Ubuntu LTS length not fetched).
- Pi 5: not in current Kairos docs. Fallback is Talos `rpi5` overlay or balenaOS/Ubuntu Core.
- Jetson: Orin Nano missing from Kairos list; GPU Operator unsupported; Thor path newer.
- If Kairos proves too rough, the lowest-regret alternative is Talos for everything with a Talos-based single-node mode (Omni) plus an OneMind Ubuntu/Kairos image only for Jetson. Talos cannot currently cover Orin (open PR), which is why it is not my primary pick.
- Not recommended as foundation: Bottlerocket (cloud-only), NixOS (7-month support), FCOS/Fedora IoT (mid bootc transition, Pi 5 not official), Yocto (BSP workload), Ubuntu Core (snap model).

### C.3 Next steps to verify before committing

1. Kairos: confirm license, Pi 5 status in latest release, update-timing controls, and a test of k3s + NVIDIA on one RTX box and one Orin.
2. Test GPU Operator on a consumer RTX under K3s (support is UNVERIFIED).
3. Measure idle k3s RAM/CPU on a Pi 5 yourself (published numbers are for Pi 4B with a monitoring workload).
4. Open the Talos Omni edge and Talos upgrade/rollback docs to fill UNVERIFIED rows.

---

## Sources

- https://docs.siderolabs.com/talos
- https://github.com/siderolabs/talos/releases
- https://github.com/siderolabs/overlays
- https://github.com/siderolabs/sbc-raspberrypi
- https://github.com/siderolabs/sbc-jetson/pull/23
- https://docs.siderolabs.com/talos/v1.13/configure-your-talos-cluster/hardware-and-drivers/nvidia-gpu-proprietary.md
- https://www.siderolabs.com/platform/talos-os-for-kubernetes/
- https://kairos.io/docs/
- https://raw.githubusercontent.com/kairos-io/kairos/master/README.md
- https://kairos.io/docs/reference/image_matrix/
- https://kairos.io/docs/installation/nvidia-jetson-images/
- https://kairos.io/docs/installation/raspberry/
- https://kairos.io/blog/2026/05/15/kairos-v4-1-0-hadron-ubuntu-boot-install-foundations/
- https://raw.githubusercontent.com/flatcar/Flatcar/main/README.md
- https://www.cncf.io/projects/flatcar/
- https://flatcar.org/docs/latest/installing/bare-metal/raspberry-pi
- https://www.flatcar.org/docs/latest/os-config/host-config/using-nvidia/
- https://github.com/bottlerocket-os/bottlerocket
- https://raw.githubusercontent.com/coreos/fedora-coreos-docs/main/modules/ROOT/pages/auto-updates.adoc
- https://raw.githubusercontent.com/coreos/fedora-coreos-docs/main/modules/ROOT/pages/platforms.adoc
- https://fedoraproject.org/wiki/Changes/CoreOSOstree2OCIUpdates
- https://github.com/coreos/fedora-coreos-tracker/issues/2214
- https://bootc.dev/
- https://access.redhat.com/support/policy/updates/errata
- https://lists.fedoraproject.org/archives/list/arm@lists.fedoraproject.org/thread/GMS3PREWUOROENCSFZTWGUDOXLOB6IH4/
- https://github.com/ublue-os
- https://castrojo.github.io/bootc-ecosystem/overall/
- https://raw.githubusercontent.com/rancher/elemental/main/README.md
- https://endoflife.date/suse-linux-micro
- https://www.suse.com/c/suse-to-deliver-enterprise-grade-edge-ai-on-nvidia-jetson
- https://documentation.ubuntu.com/core/reference/support-duration/
- https://documentation.ubuntu.com/core/reference/release-notes
- https://docs.balena.io/reference/OS/overview/2.x/
- https://docs.balena.io/reference/hardware/devices/
- https://github.com/balena-os/meta-balena
- https://nixos.org/manual/nixos/stable/
- https://nixos.org/blog/announcements/2026/nixos-2605/
- https://wiki.nixos.org/wiki/Raspberry_Pi_5
- https://www.debian.org/releases/
- https://wiki.debian.org/LTS
- https://github.com/basecamp/omarchy
- https://learn.omacom.io/ (referenced, not fetched)
- https://docs.mender.io/overview/introduction
- https://github.com/rauc/rauc
- https://github.com/sbabic/swupdate
- https://wiki.yoctoproject.org/wiki/Releases
- https://docs.yoctoproject.org/
- https://github.com/getumbrel/umbrel
- https://www.cnx-software.com/2026/04/12/umbrelos-a-debian-based-personal-home-cloud-os-with-a-slick-user-interface/
- https://github.com/beclab/Olares
- https://github.com/home-assistant/operating-system
- https://github.com/IceWhaleTech/ZimaOS
- https://github.com/Start9Labs/start-os
- https://docs.k3s.io/installation/requirements
- https://docs.k3s.io/reference/resource-profiling
- https://docs.k3s.io/datastore/ha-embedded
- https://docs.k3s.io/installation/packaged-components
- https://docs.k0sproject.io/stable/system-requirements/
- https://canonical.com/microk8s/docs/getting-started
- https://github.com/kubeedge/kubeedge
- https://github.com/openyurtio/openyurt
- https://github.com/project-akri/akri
- https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html
- https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/release-notes.html
- https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/platform-support.html
- https://github.com/NVIDIA/k8s-device-plugin
- https://github.com/NVIDIA/k8s-dra-driver-gpu
- https://github.com/Project-HAMi/HAMi
- https://github.com/NVIDIA/KAI-Scheduler
- https://github.com/ai-dynamo/dynamo
- https://github.com/NVIDIA/gpu-operator/issues/1453
- https://developer.nvidia.com/embedded/jetpack/downloads/archive-7.2

Not reachable or not usable: docs.fedoraproject.org (Anubis block), Flatcar docs deep pages, RHEL image-mode docs (403), learn.omarchy.org (DNS).
