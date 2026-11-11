# Owning the kernel and the image, and building from a Mac {#sec-kernel}

> **Explain it like I'm the founder.** You said: *"I technically want my own kernel, and everything on top of it, or our own image if necessary."* The research answer is: **own the image, own the kernel's *contract*, own the update and signing chain, own the SDK. Do not write a kernel, and do not compile one at launch.** That is exactly what Umbrel and Home Assistant own, and a small team has kept it running in production for years. Writing or forking a kernel is what Google and Huawei did with thousands of engineers, and it would not help any of your goals. And your Mac is a fine build machine, as long as every build runs inside a Linux virtual machine.

## Kernel families: Darwin, BSD, Linux and microkernels (F-15) {#sec-kernel-families}

- **Linux** is *monolithic*: drivers, filesystems and networking run inside the kernel. It is GPLv2, so anyone shipping it must offer the source [C-W18-069]. Containers are built from Linux features (namespaces and cgroups), which is why Kubernetes is Linux-native.
- **Darwin/XNU** (macOS, iOS) is a *hybrid*: Apple describes XNU as combining the Mach kernel from Carnegie Mellon with FreeBSD components and the IOKit driver API, under the Apple Public Source License 2.0 [C-W18-030].
- **The BSDs** are monolithic Unix kernels under permissive licences; FreeBSD's container primitive is the jail [C-W18-032].
- **Microkernels** (seL4, Zircon, HongMeng, Redox) keep only the minimum in the kernel and run drivers as separate processes: safer in theory, but every driver must be written for that kernel.

| Family | Pi 5 / Jetson | NVIDIA / CUDA | Kubernetes | ROS 2 | Verdict |
|---|---|---|---|---|---|
| **Linux** | Mainline device trees and vendor kernels for both [C-W18-018, C-W18-019] | CUDA 13.5 on Debian, Ubuntu, RHEL and Fedora; on Jetson, Ubuntu 24.04 only [C-CIT4-003] | Control plane runs only on Linux [C-W18-029] | Tier 1 on Ubuntu [C-W18-034] | **Choose** |
| FreeBSD | No Pi 5 or Jetson evidence | Driver for x64 only, no CUDA [C-W18-028] | Not a node OS [C-W18-029] | Not listed [C-W18-034] | Reject. TrueNAS moved new work to Linux because innovation lands "on Linux first" [C-W18-033] |
| Darwin/XNU | Apple hardware only | No CUDA: absent from the supported-OS tables of the CUDA 13.5 guide, which list only Linux distributions [C-CIT4-003] | No Linux containers natively; Apple runs each in a small VM [C-W18-031] | macOS Tier 3 [C-W18-034] | Reject as a product kernel; it is your **development host** |
| seL4 | Pi 4B/5B configs verified, but boot and IOMMU outside the proof [C-W18-035] | None | None | None | Reject for the OS; maybe a future verified safety island |
| Zircon (Fuchsia) | One consumer device class (SECONDARY) [C-W18-039] | None | None | None | Reject |
| HongMeng (HarmonyOS) | Huawei devices; kept Linux ABI compatibility to reuse drivers [C-W18-036] | None | None | None | Reject; learn the lesson |
| Redox | VMs and a few PCs; version 0.9.0 [C-W18-040] | None | None | None | Reject (research OS) |

**What Darwin means for developing on the Mac:** macOS cannot run a Linux container or build a Linux kernel by itself; every Linux container on a Mac runs inside a Linux VM (Docker Desktop, OrbStack, Lima, Colima, Apple's `container`) [C-W18-031]. The Mac is the editor, the terminal and the VM host; Linux does the building.

## What "our own OS" realistically means {#sec-own-os}

| Product | Kernel | Owns | Team | Constraint fit |
|---|---|---|---|---|
| umbrelOS | Debian's stock kernel on PCs [C-W18-012]; Raspberry Pi's on Pi [C-W18-013] | Image, update chain, apps, UI; **no kernel build** | Small company | **High** |
| Home Assistant OS | Upstream LTS 6.18 with its own config [C-W18-008]; Pi fork on Pi 5 [C-W18-009] | Image, **kernel config**, update chain, apps | Funded team; about one kernel bump a week, mostly one maintainer [C-W18-010] | **High** |
| Talos Linux | Builds its own kernel from latest stable [C-W18-045] | Everything | Vendor | Medium |
| ChromeOS | Own branches, rebases every 3–6 months [C-W18-043] | Everything | Google | Low: copy the config discipline, not the effort |
| SteamOS 3 | Valve's (SECONDARY); Arch + RAUC + casync A/B [C-W18-044] | Image, kernel, updates | Valve + Collabora | Low-medium |
| Android (GKI) | Vendor kernels fragmented until GKI moved board code into modules [C-W18-041] | Everything | Google + OEMs | Low; the lesson is central |
| HarmonyOS NEXT | Own microkernel, Linux-ABI compatible [C-W18-036] | Everything | Huawei | None |

**OneMind owns:** the **image** (layers, partition layout, profiles), the **kernel contract** (required features checked in CI) and later the kernel config, the **update and signing chain**, and the **SDK and app platform**.

## The kernel route (decision S5) {#sec-kernel-route}

| Route | What it is | Solo-founder cost | Score |
|---|---|---|---|
| **K1 · board maintainer's kernel** | The base's own on PCs (Canonical's, or Debian's on the Debian leg), Canonical's `linux-raspi` or Raspberry Pi's on Pi 5, NVIDIA's on Jetson | Lowest: refresh and rebuild, no kernel compile | **71** |
| K2 · OneMind-configured upstream LTS | Home Assistant's way | About one bump a week per kernel line (HAOS: 51 bumps a year [C-W18-010]) | 66 |
| K3 · CIP super-long-term kernel | Industrial 10-year line, to mid-2035 [C-W18-003] | Like K2 on a slower branch | 61 |
| K4 · patched OneMind kernel | K2 plus own patches | Highest; not needed for real time | 46 |
| K5 · microkernel or new kernel | seL4, Zircon, own | Not feasible | Not ranked |

![The kernel route: K1 at launch, a OneMind-built LTS kernel (K2-hybrid) only when Secure Boot is enforced with out-of-tree drivers and the shim route fails.](img/kernel-route.png){width=100%}

**Why K1 now and K2 later.** A Secure Boot key placed in the PC firmware cannot sign kernel modules for a stock kernel: the kernel trusts only built-in and "machine owner" keys for modules [C-DEC-008, C-DEC-010]. **Revision 4 found a route that may avoid that:** a OneMind *shim* (the small first-stage loader) carrying OneMind's own certificate, which the stock kernel then trusts for modules through its "machine" keyring, with no console step. It is read from source only, not yet run, so it becomes the **first arm** of the Secure Boot test T-W19-03 (`01` R4-10). Only if it fails does the release that *enforces* Secure Boot with NVIDIA or driver-pack modules move x86 and generic arm64 to a OneMind-built LTS kernel (K2-hybrid), keeping NVIDIA's L4T on Jetson. A second trigger: if the base's kernel security fixes lag upstream by more than 7 days on median, K2 comes early (`20-…` §4.1).

**Real time is no longer a custom kernel.** PREEMPT_RT has been a normal option in mainline Linux since 6.12 on x86, arm64 and RISC-V [C-W18-005]; Debian ships an RT kernel package [C-W18-006]; and our lab switched it on for both architectures without a single patch [C-W18-067]. It becomes an image profile with a per-unit latency test.

**Kernel lifetimes that matter:** kernel.org 6.12 and 6.18 LTS to December 2028 [C-W18-001]; CIP 6.12 to mid-2035 [C-W18-003]; NVIDIA's JetPack 7.2 kernel is 6.8, not an upstream LTS [C-W18-019].

## Image build tooling {#sec-image-tooling}

The image is defined like a container build on a snapshot-pinned base, Ubuntu 26.04 or Debian 13 by leg (the umbrelOS pattern [C-W2-043]), then assembled into A/B disk images and RAUC bundles per board family. umbrelOS uses a Dockerfile root filesystem plus Rugix Bakery [C-W18-015]; Home Assistant uses Buildroot; Kairos uses one Dockerfile and its own tool to produce ISO, raw and UKI images [C-TD-kairos-007]; Jetson uses NVIDIA's flash tools. `28-…` §7 compares debos, mkosi, Rugix Bakery, Buildroot, Yocto, bootc/osbuild and Kairos; the lab used **mkosi** for the minimal Debian image [C-LAB-minimal-image-dc20-011].

## Platform first or image first? {#sec-platform-first}

Both, in that order: develop the platform first as a script on plain Debian and in a VM, and produce the image from the same layers from about week 3 (`28-…` §8). Precedent is mixed: Home Assistant shipped its platform years before its OS [C-W18-062], while Umbrel shipped a Pi image first [C-W18-063]. The script path is a developer loop with a written sunset at image GA (Z-24), because Home Assistant and Umbrel both dropped theirs [C-REF-DC-longevity-004, C-REF-DC-longevity-005]. A self-contained container or VM developer preview may stay, as Home Assistant kept its Container install, used by about 17% of opted-in installs [C-REF3-DC-technical-004], while dropping Core [C-REF3-DC-technical-005].

## The Mac development setup and CI/CD (F-8) {#sec-mac}

![From the Mac to a signed release. Every build runs in Linux; signing is offline.](img/mac-ci.png){width=100%}

- **On an M3-or-newer Mac, a free Lima VM gives full Linux with KVM inside it** [C-W18-054, C-W18-065]. In our lab it compiled a full arm64 kernel in 5.5 minutes and cross-compiled an x86 kernel in under 2 [C-W18-066].
- **k3d or kind** for local Kubernetes app work; **Docker buildx** for multi-arch images.
- **A Jetson dev kit can now be set up from a Mac** with NVIDIA's new USB installer [C-W18-023]. Production Jetson flashing and fusing still need a Linux host [C-W18-021].
- **Isaac Sim needs an RTX GPU** [C-W18-058], so it runs on a rented cloud GPU, not the Mac.
- **CI on native x86 and arm64 runners** builds the root filesystem from one definition in two legs (`FROM ubuntu:26.04` and `FROM debian:trixie`, at parity until the base lock), assembles images and bundles, runs the QEMU update/rollback/power-cut/restore battery, and produces an SBOM and provenance. Signing happens offline, 2-of-3, with the module key in an HSM.

## What competitors do (constraint fit) {#sec-kernel-competitors}

| Product | Kernel approach | Constraint fit | OneMind takes |
|---|---|---|---|
| umbrelOS | Distro and vendor kernels, no compile [C-W18-012] | High | K1 at launch |
| Home Assistant OS | Upstream LTS + own config, ~51 bumps/year [C-W18-010] | High | K2 when Secure Boot is enforced; the kernel-contract idea |
| Talos | Own kernel from latest stable [C-W18-045] | Medium | Not needed |
| ChromeOS, Android, HarmonyOS | Own branches or own kernel | Low / none | Config discipline and the "stable module interface" lesson only |

**Requirements served:** F-7, F-8, F-15, D-002, M-6, R-3, N-7 (`28-…` §14).
