# Base distro verification: Ubuntu 24.04 LTS vs Debian 13 "trixie"

Date of research: 2026-11-10. Every row cites a page that was actually opened (curl / gh api / WebFetch) during this run.
Tags: VERIFIED = read on the primary source; INFERRED = derived from a primary source (reasoning stated); UNVERIFIED = could not open / confirm.

## 1. Facts table

### 1.1 Lifecycles

| Fact | Value | Status | Source |
|---|---|---|---|
| Ubuntu 24.04 LTS release | Apr 2024 | VERIFIED | https://ubuntu.com/about/release-cycle |
| 24.04 standard security maintenance end | May 2029 | VERIFIED | https://ubuntu.com/about/release-cycle |
| 24.04 ESM (Ubuntu Pro) end | May 2034 | VERIFIED (column order read from page layout; page text says LTS = 5y standard + ESM to 10y) | https://ubuntu.com/about/release-cycle |
| 24.04 Legacy add-on end | May 2039 (15 years total) | VERIFIED (page: "up to 15 years ... (ESM and Legacy add-on)"; Legacy = extra 5y after ESM) | https://ubuntu.com/about/release-cycle |
| Ubuntu Pro free tier | "free for personal use on up to five machines" (release-cycle page); "up to 5 physical machines, or 50 machines for official Ubuntu Community members" (Pro page). Personal use only. | VERIFIED | https://ubuntu.com/about/release-cycle , https://ubuntu.com/pro |
| Ubuntu Pro commercial price | Workstation $25/machine/yr; Server (unlimited VMs) $500/machine/yr (no support). With 24/7 support: $300 workstation, $1,775 infra-only server, $3,400 full-support server (per machine/yr). Weekday support = 50% of 24/7. Legacy add-on = Pro price +50%. | VERIFIED (published list price, page of 2026-11-10 fetch) | https://ubuntu.com/pricing/pro |
| Ubuntu Pro for Devices (IoT/appliance) | One-time fee per device covering "its entire lifecycle"; up to 15 years of ESM; price NOT published ("Contact us") | VERIFIED model / price UNVERIFIED | https://ubuntu.com/pro/devices |
| Ubuntu 26.04 LTS release | 2026-04-23 (ISO timestamps on releases.ubuntu.com; page header says "Released: Apr 2026"). 26.04.1 is current. Kernel 7.0. | VERIFIED (date from ISO mtime; kernel via secondary news, cnx-software) | https://releases.ubuntu.com/26.04/ , https://ubuntu.com/about/release-cycle |
| 26.04 support | Standard May 2031, ESM May 2036, Legacy May 2041 | VERIFIED | https://ubuntu.com/about/release-cycle |
| Debian 13 trixie release | 2025-08-09 (13.0); latest point release 13.7 on 2026-09-12 | VERIFIED | https://www.debian.org/releases/ |
| Debian 13 regular (Security Team) EOL | 2028-08-09 | VERIFIED | https://www.debian.org/releases/ |
| Debian 13 LTS end | 2030-06-30 (LTS run by separate volunteers/companies, not the Security Team) | VERIFIED | https://www.debian.org/releases/ , https://www.debian.org/lts/ |
| Debian 13 ELTS (Freexian, paid) end | 2035-06-30 ("up to 10 years", only for packages customers use) | VERIFIED | https://www.debian.org/releases/ , https://www.freexian.com/lts/extended/ |
| wiki.debian.org/LTS | Could not open (anti-bot JS challenge) | UNVERIFIED | https://wiki.debian.org/LTS |
| Debian lifecycle statement | "five years: three years of full support followed by two years of LTS" | VERIFIED | https://www.debian.org/releases/ |

### 1.2 NVIDIA support

| Fact | Value | Status | Source |
|---|---|---|---|
| GPU Operator (docs "latest", 26.7.x Supported, 26.3.x Deprecated) validated OS | Ubuntu 26.04, 24.04, 22.04 LTS (+ RHEL/Rocky family). The word "Debian" appears 0 times on the page. | VERIFIED | https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/platform-support.html |
| GPU Operator and Jetson | "NVIDIA Jetson, or other embedded products with integrated GPUs, are not supported" (discrete GPUs only; IGX Orin dGPU ok) | VERIFIED | same page |
| Container Toolkit tested distros | Ubuntu 22.04 / 24.04 / 26.04 (amd64, arm64 on 24.04/26.04); Debian Linux 11 (amd64) is the only Debian row; no Debian 12/13 row. Install guide says apt instructions "should work for any Debian-derived distribution". | VERIFIED | https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/supported-platforms.html , https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html |
| CUDA Toolkit 13.5 Linux support | x86_64: Ubuntu 26.04/24.04/22.04, Debian 12, Debian 13. arm64-sbsa: Ubuntu 26.04/24.04/22.04, Debian 12, Debian 13. Cross-dev for arm64-sbsa-jetson only on Ubuntu 24.04. | VERIFIED | https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html |
| NVIDIA apt repos | developer.download.nvidia.com/compute/cuda/repos/ has debian13/x86_64, debian13/sbsa, ubuntu2404/x86_64, ubuntu2404/sbsa, ubuntu2604/x86_64 (HTTP 200 each; debian13/arm64 = 404, sbsa is the arm64 server path) | VERIFIED | `curl` on https://developer.download.nvidia.com/compute/cuda/repos/{path}/ |
| Debian's own NVIDIA driver | trixie: nvidia-graphics-drivers 550.163.01-2 (branch 550; "predates Blackwell/RTX 50" per Umbrel build notes). Newer driver needs NVIDIA's debian13 repo. | VERIFIED | https://sources.debian.org/api/src/nvidia-graphics-drivers/ ; https://github.com/getumbrel/umbrel/blob/master/packages/os/umbrelos.Dockerfile |
| JetPack 7.x / Jetson base | "Built on Linux Kernel 6.8 and Ubuntu 24.04 LTS"; supports Orin and Thor; JetPack 7.2 also officially supports Yocto on Jetson | VERIFIED | https://developer.nvidia.com/embedded/jetpack |
| DGX OS 7 base | "customized installation of Ubuntu Linux"; DGX software stack can be installed on regular Ubuntu 24.04 | VERIFIED | https://docs.nvidia.com/dgx/dgx-os-7-user-guide/introduction.html |

### 1.3 Raspberry Pi 5

| Fact | Value | Status | Source |
|---|---|---|---|
| Ubuntu 24.04 on Pi 5 | Server + Desktop supported, "Certified" (SDC). 26.04 same. Preinstalled images 24.04.3/.4/.5 exist. Min boot EEPROM date applies for newer releases. | VERIFIED | https://ubuntu.com/hardware/docs/boards/how-to/ubuntu_supported/raspberry-pi/ , https://ubuntu.com/download/raspberry-pi |
| Debian 13 on Pi 5 (official Debian) | wiki.debian.org/RaspberryPi (last modified 2022-05-31) lists Pi 3/4/400 on arm64 and says nothing about Pi 5. raspi.debian.net (unofficial, edited 2026-01-28) says it is superseded by Debian Cloud Images and "RPi 5 only works with Debian 14 'Forky' (testing) or Sid (unstable)". Net: stock Debian 13 kernel does not officially support Pi 5. | VERIFIED (absence + unofficial statement) | https://wiki.debian.org/RaspberryPi , https://raspi.debian.net/ |
| How Umbrel solves it | Debian trixie base + Raspberry Pi's own repo/kernel on Pi ("The Raspberry Pi repo rebuilds many Debian packages (glibc, ffmpeg, mesa ...) ... replace Debian's") | VERIFIED | https://github.com/getumbrel/umbrel/blob/master/packages/os/README.md |
| Raspberry Pi OS base | Debian Trixie (announced 2025-10-02) | VERIFIED | https://www.raspberrypi.com/news/trixie-the-new-version-of-raspberry-pi-os/ |

### 1.4 Image builders

| Fact | Value | Status | Source |
|---|---|---|---|
| Kairos (kairos-init, latest tag v0.17.3 2026-08-18) | Distro enum in code: Debian, Ubuntu, RHEL, Rocky, Alma, Oracle Linux, Fedora, Arch, Alpine, openSUSE Leap/Tumbleweed, SLES, Hadron. Docs examples use ubuntu:24.04 and "Debian family" handling. Models: generic, rpi3, rpi4, nvidia-jetson-agx-orin / orin-nx (L4T r36.x), nvidia-jetson-thor (L4T r39.x), nvidia-dgx-spark. No rpi5 model listed. | VERIFIED | https://github.com/kairos-io/kairos-init/blob/main/pkg/values/values.go , https://kairos.io/docs/reference/kairos-factory/ |
| Rugix (Ctrl/Bakery) | Bakery template builds "a customized Debian system"; Ctrl also integrates with Yocto/Buildroot/other; Rugix .deb installer for apt systems "such as Debian or Ubuntu". Umbrel uses it (Pi) plus Mender (amd64). No Ubuntu-specific base documented in what was read. | VERIFIED for Debian; Ubuntu base UNVERIFIED | https://rugix.org/docs/ , https://github.com/rugix/rugix , https://github.com/getumbrel/umbrel/blob/master/packages/os/README.md |

### 1.5 Security tooling and kernels

| Fact | Value | Status | Source |
|---|---|---|---|
| Ubuntu | USN list and CVE tracker pages live; Livepatch "free for up to 5 machines, for personal use, or evaluation"; Pro adds esm-apps (universe) | VERIFIED | https://ubuntu.com/security/notices , https://ubuntu.com/security/cves , https://ubuntu.com/security/livepatch |
| Debian | DSAs by Security Team; Debian Security Bug Tracker built from the security-tracker git repo; no vendor livepatch service | VERIFIED (livepatch absence is INFERRED) | https://www.debian.org/security/ , https://security-tracker.debian.org/tracker/ |
| Ubuntu 24.04 kernels | GA 6.8 (linux-meta 6.8.0-149.149 in noble-updates). HWE stack "linux-generic-hwe-24.04"; server defaults to GA, HWE optional. HWE metas published in noble-updates: 6.14, 6.17, 7.0 (linux-meta-hwe-7.0 7.0.0-42.42~24.04.1). | VERIFIED (Launchpad API, 2026-11-10) | https://api.launchpad.net/devel/ubuntu/+archive/primary?ws.op=getPublishedSources&source_name=linux-meta-hwe-7.0&exact_match=true ; https://ubuntu.com/kernel/lifecycle |
| Debian 13 kernels | 6.12 series (6.12.107-1 in trixie); trixie-backports tracks newer (up to 7.2.12-1~bpo13+1 seen) | VERIFIED | https://sources.debian.org/api/src/linux/ , https://www.debian.org/releases/trixie/release-notes/whats-new.en.html |

### 1.6 Snap

| Fact | Value | Status | Source |
|---|---|---|---|
| snapd in Ubuntu 24.04 metapackages | `ubuntu-server-minimal` 1.539.2 (noble-updates) has snapd in **Depends**; `ubuntu-server` has snapd in **Recommends**; `ubuntu-server` Depends on `lxd-installer`; also reverse-depends on snapd: update-manager, ubuntu-cloud-minimal, ubuntu-desktop(-minimal), ubuntu-wsl | VERIFIED (parsed apt Packages.xz for noble and noble-updates main) | http://archive.ubuntu.com/ubuntu/dists/noble-updates/main/binary-amd64/Packages.xz |
| LXD | Recommended install is the snap; requires snapd | VERIFIED | https://documentation.ubuntu.com/lxd/en/latest/installing/ |
| Removal | Possible only by not installing (or removing) ubuntu-server-minimal; an image we build from debootstrap/mmdebstrap need not include it. Third-party reports of purge issues (Launchpad bug 2058810). No official Canonical "how to remove snapd" doc found. Thunderbird is snap-only in 24.04. | PARTIAL: dependency fact VERIFIED; official removal doc UNVERIFIED | https://bugs.launchpad.net/bugs/2058810 , https://documentation.ubuntu.com/release-notes/24.04/ |

### 1.7 Who uses what

| Product | Base | Status | Source |
|---|---|---|---|
| umbrelOS | Debian trixie, pinned to snapshot.debian.org 20261027; kernel/firmware from trixie-backports on amd64/arm64; NVIDIA driver from NVIDIA's debian13 repo; Rugix on Pi, Mender on amd64 | VERIFIED | https://github.com/getumbrel/umbrel/blob/master/packages/os/umbrelos.Dockerfile , .../packages/os/README.md |
| Olares | Linux script install: "Ubuntu 22.04 to 25.04, or Debian 12 or 13"; ISO also offered | VERIFIED | https://github.com/beclab/Olares (README) |
| Proxmox VE | PVE 9 on Debian 13 (Trixie), first release 2025-08; "based on Debian GNU/Linux" | VERIFIED | https://pve.proxmox.com/wiki/FAQ |
| DGX OS | Ubuntu (DGX OS 7 = Ubuntu 24.04) | VERIFIED | see 1.2 |
| Home Assistant OS | Not Debian/Ubuntu; built from source with Buildroot, one image per board | VERIFIED | https://developers.home-assistant.io/docs/operating-system/ |

### 1.8 Governance / policy

| Fact | Value | Status | Source |
|---|---|---|---|
| Debian | Project governed by Debian Constitution (elected DPL, Technical Committee, developer votes); community, no single vendor | VERIFIED | https://www.debian.org/devel/constitution |
| Canonical | Single commercial company (Canonical Ltd.) controls Ubuntu, Pro, snap store | VERIFIED (footer: "Ubuntu and Canonical are registered trademarks of Canonical Ltd."), characterization INFERRED | https://ubuntu.com/pro |
| Universe/Pro policy | Canonical's docs: universe historically had no security commitment; since Pro (GA early 2023) esm-apps covers all universe packages for 10 years, delivered through Pro. Free for personal use up to 5 machines. Community criticism that universe fixes sit behind Pro is opinion (forum threads), not independently verified journalism. | VERIFIED (Canonical side) / opinions UNVERIFIED | https://documentation.ubuntu.com/pro-client/en/latest/explanations/about_esm/ |
| Snap-only apps | Thunderbird is snap-only in 24.04 | VERIFIED | https://documentation.ubuntu.com/release-notes/24.04/ |

## 2. Where Debian wins / Where Ubuntu wins

### Debian 13 wins
- No per-machine licensing. Ubuntu's free Pro tier is personal-use, 5 machines; an appliance product shipping to customers falls on the commercial price list ($25 to $500 per machine per year) or the undisclosed Pro for Devices one-time fee.
- Precedent: umbrelOS (same product category) is Debian trixie, pinned by snapshot date, with backports kernel and NVIDIA's own debian13 repo. Proxmox VE 9 is also Debian 13. Olares installs on Debian 12/13.
- No snapd. ubuntu-server-minimal hard-depends on snapd; Debian has no such coupling.
- Kernel flexibility: 6.12 base with 7.x in trixie-backports (matters for new GPUs, NICs, Pi/x86 hardware).
- Governance: community-run, no vendor can change terms (Pro-gated universe fixes, snap-only packages).
- Security horizon is comparable on free terms: full support to 2028-08-09, LTS to 2030-06-30 (limited package set), ELTS paid to 2035-06-30.
- CUDA 13.5 officially lists Debian 12 and 13 on x86_64 and arm64-sbsa; NVIDIA publishes debian13 repos.

### Ubuntu 24.04 wins
- NVIDIA's own stack is Ubuntu-first: GPU Operator lists only Ubuntu (no Debian anywhere), Container Toolkit tests Ubuntu 22.04/24.04/26.04 (only Debian 11 listed), DGX OS = Ubuntu, JetPack 7 = Ubuntu 24.04 userspace. Jetson/DGX Spark are effectively Ubuntu-only unless NVIDIA's userspace is replaced (Debian on Jetson UNVERIFIED).
- Raspberry Pi 5 is Canonical-certified on 24.04 and 26.04 with ready images; stock Debian 13 does not officially cover Pi 5 (needs Raspberry Pi's kernel/repo, as Umbrel does).
- Longer vendor-backed horizon when paid: standard to May 2029, ESM May 2034, Legacy May 2039; one 15-year story plus Livepatch, FIPS, CIS/STIG (DISA-STIG and CIS "Achieved" for 24.04 per release-cycle page).
- Ubuntu Core 24 exists as a vendor-supported immutable option (supported until 2036 per Canonical's Pi page).
- Kairos documentation examples center on Ubuntu 24.04.
- Canonical gives one vendor to call for support.

## 3. Open gaps (not verified)
- wiki.debian.org/LTS blocked by JS challenge; used debian.org pages instead.
- Whether GPU Operator works on Debian with a host-installed driver (driver.enabled=false): not in any matrix, so unsupported by NVIDIA, untested here.
- Debian userspace on Jetson L4T r36/r39, and how Kairos builds its Jetson models: not verified.
- Pro for Devices price; Rugix on Ubuntu; Debian 13 on Pi 5 with Debian's own kernel today (only the unofficial raspi.debian.net statement, dated 2026-01-28).
- Ubuntu 26.04 kernel 7.0 comes from secondary news (cnx-software), not Canonical's page.

## 4. Recommendation
Debian 13 trixie as the single base for x86, RTX and multi-node cluster images, built as an immutable A/B image from a pinned snapshot.debian.org date (the umbrelOS pattern), kernel from trixie-backports, NVIDIA driver from NVIDIA's debian13 repo (Debian's own is stuck on 550). Pi 5 uses Raspberry Pi's kernel/firmware repo on Debian userspace (Umbrel proves it). Treat Jetson (and DGX Spark) as a separate flavor on NVIDIA's L4T/Ubuntu 24.04 userspace, because NVIDIA only supports that. Use the NVIDIA device plugin with host-installed driver and Container Toolkit rather than relying on GPU Operator's driver container, which NVIDIA only validates on Ubuntu; spike this early.
If NVIDIA-vendor support (GPU Operator validation, enterprise tickets) outranks licensing cost for your customers, flip to Ubuntu 24.04 (then 26.04) and budget for Pro for Devices.

## Sources
- https://ubuntu.com/about/release-cycle
- https://ubuntu.com/pro
- https://ubuntu.com/pricing/pro
- https://ubuntu.com/pro/devices
- https://ubuntu.com/security/livepatch
- https://ubuntu.com/security/notices
- https://ubuntu.com/security/cves
- https://ubuntu.com/kernel/lifecycle
- https://ubuntu.com/download/raspberry-pi
- https://ubuntu.com/hardware/docs/boards/how-to/ubuntu_supported/raspberry-pi/
- https://releases.ubuntu.com/26.04/
- https://documentation.ubuntu.com/pro-client/en/latest/explanations/about_esm/
- https://documentation.ubuntu.com/release-notes/24.04/
- https://documentation.ubuntu.com/lxd/en/latest/installing/
- http://archive.ubuntu.com/ubuntu/dists/noble-updates/main/binary-amd64/Packages.xz
- https://api.launchpad.net/devel/ubuntu/+archive/primary (getPublishedSources queries)
- https://bugs.launchpad.net/bugs/2058810
- https://www.debian.org/releases/
- https://www.debian.org/lts/
- https://www.debian.org/security/
- https://www.debian.org/releases/trixie/release-notes/whats-new.en.html
- https://www.debian.org/devel/constitution
- https://security-tracker.debian.org/tracker/
- https://www.freexian.com/lts/extended/
- https://wiki.debian.org/RaspberryPi
- https://raspi.debian.net/
- https://sources.debian.org/api/src/linux/ and /nvidia-graphics-drivers/
- https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/platform-support.html
- https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/supported-platforms.html
- https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
- https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html
- https://developer.download.nvidia.com/compute/cuda/repos/
- https://developer.nvidia.com/embedded/jetpack
- https://docs.nvidia.com/dgx/dgx-os-7-user-guide/introduction.html
- https://github.com/getumbrel/umbrel (packages/os/umbrelos.Dockerfile, packages/os/README.md)
- https://github.com/beclab/Olares
- https://github.com/kairos-io/kairos-init and https://kairos.io/docs/reference/kairos-factory/
- https://github.com/rugix/rugix and https://rugix.org/docs/
- https://pve.proxmox.com/wiki/FAQ
- https://developers.home-assistant.io/docs/operating-system/
- https://www.raspberrypi.com/news/trixie-the-new-version-of-raspberry-pi-os/
- https://www.cnx-software.com/2026/04/24/ubuntu-26-04-lts-resolute-raccoon-released-with-linux-7-0/ (secondary)
