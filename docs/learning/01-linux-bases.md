# Lesson 01: The Big Four Linux Bases, and What They Mean for OneMind OS

**For:** Zeus (learning track) · **Date:** 2026-11-10
**Sources:** two YouTube explainers Zeus shared ("the big four" Arch/Debian/Fedora/Ubuntu comparison, and youtube.com/watch?v=DB5mk6bQt9A), plus the OneMind research files (`research/platform/base-os-and-orchestration.md`, `research/competitors/*.md`). Video claims are summarized, not independently re-verified.

---

## 1. The big idea: most Linux distros are built on one of four bases
Arch, Debian, Fedora and Ubuntu (which is itself built on Debian). Picking a base means picking its **package format, release rhythm, hardware/driver support, and ecosystem**.

| | Arch | Debian | Fedora | Ubuntu |
|---|---|---|---|---|
| Package manager | pacman (fast, tarballs) | apt (.deb) | dnf5 (.rpm) | apt (.deb) + Snap push |
| Release model | **Rolling**: updates daily, may need manual fixes | Major release ~every 2 yrs, **5 yrs support** | New release every 6 months, **13 months support** | 6-month releases; **LTS every 2 yrs, 5 yrs support (up to 15 with Pro)** |
| Software age | Newest | Older but heavily tested | New, tested | Modern at release |
| Community repo | AUR (~112k packages; check for malware) | None official | COPR, RPM Fusion | PPAs |
| Personality | DIY power users | Rock-solid servers ("Toyota Corolla") | Developer, cutting edge, upstream of Red Hat | Easiest, most popular ("Honda Civic"), corporate |
| Built on it | Manjaro, CachyOS, **Omarchy** | **Proxmox, Kali, Tails, umbrelOS**, Ubuntu | RHEL/Alma/Rocky, **Bazzite/Bluefin/Aurora (atomic)** | Mint, Pop!_OS, Zorin, **NVIDIA JetPack** |
| Main drawback | Any update can break things | Old packages, non-free friction | Ships new tech early, short support | Snap pushed on you, corporate decisions |

## 2. Why this matters *less* for an appliance than for a desktop
The videos compare distros **as desktops you install apps on with a package manager.** OneMind is different:

1. **Users never run `apt`, `dnf` or `pacman`.** Apps run as **containers** (k3s) from the OneMind Market. The package manager is used only by *us*, at build time, to assemble the OS image.
2. **The image is read-only** (immutable). Updates replace the whole image (A/B) with rollback, instead of updating package by package. So complaints like "Arch updates break things" or "Fedora upgrades every 6 months" are about *how often we rebuild and test the image*, not something users deal with.
3. **No desktop needed** on the box. Snap, GNOME and desktop-environment arguments mostly don't apply. Ubuntu's snap problem goes away because we leave `snapd` out of our image.

**What still matters for OneMind:**
- **(a) Hardware and driver support:** NVIDIA, Raspberry Pi, Jetson.
- **(b) Support length:** how long security fixes keep coming for boxes in people's homes.
- **(c) Tools for building images:** Kairos, Rugix, bootc.
- **(d) Stability**, so every box behaves the same.

## 3. What competitors actually use and how

There are **two ways** competitors use a base:
- **Build their own OS image from it.** You flash it like firmware, and they control everything.
- **Install on top of the user's existing Linux.** An installer script turns your Ubuntu/Debian into their platform.

| Product | Base | How they use it | App runtime | Updates | Source |
|---|---|---|---|---|---|
| **Umbrel (umbrelOS 2.0)** | **Debian 13 "trixie"** | Own image; also installs on any x86 or Pi 4/5 | Docker Compose | **Signed A/B via Rugix** (Mender on old devices) | umbrel repo `packages/os/` (verified) |
| **Olares** | **Ubuntu 22.04–25.04 or Debian 12/13** | **Installer on top** of your Linux; Olares One ships it preloaded | **k3s** (Kubernetes) | Olares upgrade tool (not A/B) | Olares docs |
| **Home Assistant OS** | **Buildroot** (minimal custom Linux, not a big-four base) | Own image | Docker (Supervisor + add-ons) | **A/B via RAUC** | home-assistant/operating-system |
| **ZimaOS** | Buildroot | Own image | Docker (CasaOS style) | RAUC inferred, not confirmed | IceWhale repo |
| **CasaOS** | Your Debian/Ubuntu/etc. | Installer on top | Docker | Script | IceWhale |
| **Start9 StartOS** | UNVERIFIED in our research | Own image | Containers | — | — |
| **Proxmox** | Debian | Own image | VMs + LXC | apt | video |
| **NVIDIA Jetson (JetPack 7.2)** | **Ubuntu 24.04** | Own image (L4T) | Docker/containers | apt | NVIDIA docs |
| **ClawBox** | Ubuntu (on Jetson) | Preloaded | — | — | vendor |

**Patterns:**
1. Appliance makers favor **stable bases (Debian, Ubuntu LTS) or tiny custom builds (Buildroot)**. Nobody ships a rolling Arch base, and nobody ships plain Fedora for a box.
2. The good ones (Umbrel, HAOS) use **A/B image updates with rollback**.
3. Only **Olares uses Kubernetes (k3s)**, the same choice OneMind makes, and it sits on Ubuntu/Debian.
4. **Anything NVIDIA is Ubuntu.**

## 4. How OneMind maps onto this

| Need (requirement) | Choice | Why, in big-four terms |
|---|---|---|
| One base for PC, GPU box, Pi, Jetson [N-2, D-002] | **Ubuntu 24.04 LTS** | Same apt/.deb family as Debian (Umbrel's base), but it is the base NVIDIA ships for Jetson and supports for GPUs. One base covers every tier. |
| Long support for boxes in homes [R-3] | Ubuntu LTS: 5 yrs (up to 15 with Pro) | Fedora's 13 months is too short; Arch has no versions at all |
| Safe updates, user-timed [R-1] | **Immutable image + A/B** via Kairos (fallback: Rugix, Umbrel's tool) | Same pattern as Umbrel and HAOS |
| Apps plug and play [A-1] | **k3s containers** | Same as Olares; users never touch apt |
| Avoid Ubuntu's downsides | **No snapd, no desktop** in the image | The video's Ubuntu complaints are desktop-focused |
| Desktop edition [UX-10] | **Omarchy (Arch + Hyprland)** as a *client* | Arch is great for a power-user desktop and bad for a box |
| Close runner-up | **Debian 13** | If NVIDIA weren't central, Debian (Umbrel's choice) would be just as good. Same apt family, so switching costs little. |
| Watch for 2027 | Fedora/CentOS **bootc** | Fedora leads atomic tech (Bazzite, Bluefin) but is mid-transition |

## 5. Vocabulary
- **Distro:** a Linux distribution, meaning the kernel plus tools plus a package manager.
- **Package manager:** the tool that installs software (apt, dnf, pacman).
- **Rolling release:** constant updates, with no version numbers.
- **LTS:** Long-Term Support, a release that gets security fixes for years.
- **Immutable/atomic:** the OS files are read-only, and updates swap the whole system at once.
- **A/B updates:** two copies of the OS. The update goes to the inactive copy, and if it fails to boot, the box switches back.
- **Buildroot/Yocto:** toolkits that build a tiny custom Linux from scratch (used by HAOS and ZimaOS).
- **Container:** an app packaged with everything it needs, isolated from the OS.
- **k3s:** lightweight Kubernetes, which runs and manages containers across one or many machines.

## 6. Check yourself
1. Why does Ubuntu's Snap push barely affect OneMind? *(Users don't install packages; snapd is left out of the image.)*
2. Why not Arch for the box but OK for the desktop edition? *(Rolling updates can break a box nobody is watching.)*
3. What do Umbrel and HAOS share that makes updates safe? *(A/B image updates with rollback.)*
4. What single fact pushes OneMind from Debian to Ubuntu? *(NVIDIA Jetson/JetPack and GPU tooling are built on Ubuntu.)*
