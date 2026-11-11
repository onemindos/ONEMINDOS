# Lesson 05: The Official Route, Umbrel vs Olares, and Why Not Fedora (incl. CoreOS) or Arch

**For:** Zeus (learning track) · **Date:** 2026-11-11
**Sources:** the research branch `research/ultracode-foundation` (PR #1, rev. 4.1): `research-output/01-FOUNDATION-DECISION.md`, `02-competitors/olares.md`, `02-competitors/umbrelos.md`, `12-dashboard-clients-xr.md` (Z-32); on main: `research/platform/base-os-and-orchestration.md` §A.1 and `research/platform/fedora-iot-and-redhat-edge-deep-dive.md`.
**Status:** founder recommendation. **Z-38 (base OS) is still open** until it is logged as a founder decision.
**Builds on:** [03](03-base-os-debian-vs-ubuntu.md), [04](04-install-modes-and-cloud.md)

---

## 1. Your image vs installing on top
| | **Your image** (Umbrel's way) | **Install on top** (Olares's way) |
|---|---|---|
| Who controls the OS | You: sealed and signed | The customer or the cloud; you add apps on top |
| Bad update | Rolls back by itself to the other OS copy | Stays broken until fixed |
| Update security | Signed by you | Olares: MD5 checksum only [C-TD-olares-004] |
| OS changes underneath | You choose when to upgrade | Can break you (Olares on Debian 13, #4171) [C-TD-olares-050] |
| Needs Canonical's permission? | Only if the image is Ubuntu; **not for Debian** | No: unmodified Ubuntu is allowed |

## 2. Umbrel vs Olares, and what OneMind takes
- **umbrelOS** owns the OS: a Debian 13 image with A/B updates and signing [C-TD-umbrelos-003]. It is reliable and simple, but it runs on one box, with no Kubernetes and no robots.
- **Olares** installs on Ubuntu (its ISO writes Ubuntu) or Debian [C-TD-olares-007, C-TD-olares-041]. It has k3s and multi-node, but no rollback and no signatures.
- **OneMind takes Umbrel's owned, signed image plus Olares's k3s app platform.** The research's verdict: Olares is the reference for the app platform, not for the OS image or update safety. HAOS and umbrelOS are the references there.

## 3. The official route (recommended)
**Your own Debian 13 image is the product. Install-on-top is a second mode for machines you don't own.**

```
Boxes you sell or ship (Pi 5, mini PC, hubs, field kits)  → OneMind Debian image   (full freedom, no permission needed)
Your cloud hub                                         → OneMind image as a cloud VM, or your DOKS cluster today
Customer clouds / company servers / GPU servers           → install on their unmodified Ubuntu/Debian (allowed, no Canonical needed)
Jetson robots                                          → NVIDIA's Ubuntu now (ask Canonical) → Yocto meta-tegra (no Ubuntu at all)
Industrial / enterprise (year 2)                       → AlmaLinux / RHEL bootc profile (Fedora IoT as CI canary)
```

**How you get around Ubuntu's restriction:**
- You never ship your own modified Ubuntu on the core boxes, because they run Debian.
- Where Ubuntu is required, you install on top of the customer's unmodified copy, which is allowed.
- On robots, the plan tests **Yocto meta-tegra**, which NVIDIA officially supports. If it passes, the robots don't need Ubuntu at all, and you have full freedom everywhere.

## 4. Why not Fedora
Fedora's editions (from getfedora.org): Workstation, KDE Plasma, Server, Cloud, **CoreOS** and **IoT**.

- **Fedora IoT** (scored 48–52 in the research):
  - each release is supported only about 13 months
  - its bootc image doesn't boot on the Pi 5 yet (iot-distro bug #82 open)
  - in the lab, rollback took 32 minutes against a 15-minute target [C-W2-054], and a power cut silently downgraded a healthy box [C-LAB-fedora-bootc-011]
  - no shipping product was found on it
- **Fedora CoreOS** (FCOS: the auto-updating, container-focused server/cluster OS; `base-os-and-orchestration.md` §A.1):
  - **Good:** automatic updates with rollback (Zincati + rpm-ostree, with update windows and staged rollouts), built for cloud and cluster nodes. It is k0s-tested.
  - **Against OneMind's needs:**
    - **no long-term release**: it is a stream that moves to each new Fedora
    - **Pi 4 is the only Pi with a guide**: no Pi 5 and no Jetson
    - it is **mid-migration**: a working group formed in Sep 2026 to merge CoreOS into Fedora's bootc (issue #2214, aimed at Fedora 46), so building on it today means riding that change
  - It wasn't among the finalists. Its future (bootc) is what OneMind kept.
- **What OneMind keeps from Fedora:** the **RHEL-family bootc** line (AlmaLinux 10, RHEL 10 image mode) scored **64**, a near-tie with Ubuntu 65 and Debian 63. It becomes the **Industrial profile in year 2**, with Fedora IoT as the early-warning CI canary. If bootc passes on a real Pi 5 (test W2-HW-3), it can still win the core.

## 5. Why not Arch
Arch is a rolling release with no long-term support. Omarchy, built on Arch, shipped about 32 releases in a year, and its Arch mirror runs a month behind [C-W11-047…050]. The research rejected an Arch-based OneMind image for that reason (Z-32). Arch can't meet "support to 2036" (gate G3); that reading is mine, not the research's. Every update also risks breaking a box sitting in a closet or a field.

## Check yourself
1. What's the difference between Fedora CoreOS and Fedora IoT, and why does neither fit the Pi 5 tier today?
2. What does OneMind take from Umbrel, and what from Olares?
3. Name the three ways OneMind avoids needing Canonical's permission.
4. Which Fedora-lineage option is still in the running, and what single test decides it?
