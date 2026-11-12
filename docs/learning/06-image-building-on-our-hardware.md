# Lesson 06: Image Building on Our Hardware (Beelink, DigitalOcean, Pi, Jetson)

**For:** Zeus (learning track) · **Date:** 2026-11-11
**Status:** founder-requested bring-up plan. It follows locked decision **D-007** (Debian 13 is the shipping base) and adds nothing new to the architecture.
**Sources:** `research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md` §6 B2/B13 and §7; `research-output/22-HARDWARE-LAB-TEST-PLAN.md` §3, §4, §6 and §9; `research-output/evidence/lab/rauc-1152/`; DigitalOcean Custom Images docs (limits page and upload guide, fetched 2026-11-11).
**Builds on:** [03](03-base-os-debian-vs-ubuntu.md), [04](04-install-modes-and-cloud.md), [05](05-official-route-and-why-not-fedora-arch.md)
**Feeds:** milestones BM0 and BM1, gates G0 and G1 (brief 30 §7), and the kits LT-X86-00/01, LT-PI5-01, LT-JET-01 and LT-CLU-01…12.

---

## 1. The idea in one paragraph
There is **one recipe** (a Containerfile on Debian 13) and **one assembler**. The assembler turns that recipe into a different *output* for each machine, called a **board**. A board is the build's name for a family of hardware that boots the same way. Your four machines cover all four kinds of board that release v0 needs. So "getting it right on hardware" means one recipe gives four outputs, and each output passes its test kit on the real machine.

## 2. Your hardware → which board → which kit
| Your machine | Board (brief 30 §6 B2) | Boots with | Output it needs | First kit (22) | What the kit proves |
|---|---|---|---|---|---|
| **Beelink** mini PC | `x86_64-efi` | UEFI → RAUC A/B via GRUB (UKI later) | raw `.img.xz`, then the USB installer ISO | **LT-X86-00**, then **LT-X86-01** | An A/B image with the k3s health gate boots on real x86 and rolls back by itself |
| **DigitalOcean** | `vm` (cloud) | **BIOS only** (see §4) | raw/qcow2 custom image with cloud-init | **LT-CLU-01…12** (read-only, today) | Today: the shape of your live cluster. Later: the image runs as a droplet |
| **Raspberry Pi** (must be a **Pi 5**) | `rpi5` | Pi firmware `tryboot` A/B (no GRUB) | flash image (`.img.xz`) | **LT-PI5-01** (F-PI5) | Updates and rollback work on the Pi's own boot path, which QEMU cannot emulate |
| **Jetson** (Orin Nano Super assumed) | `jetson-orin` (dev kit only) | NVIDIA L4T A/B (`ROOTFS_AB=1`) | NVIDIA flash package, never published (Z-01) | **LT-JET-01** | NVIDIA's A/B slots plus our gate fall back after a bad update or a power cut |

**Vocabulary**
- **A/B:** two copies of the OS. An update writes the copy you are *not* running, then tries it. If it fails, the box boots the old copy.
- **Health gate:** the check that decides whether the new copy is "good". Ours requires *fresh* signs that k3s is healthy, not stale ones (REC-DEC-07).
- **Kit:** a script plus pass/fail criteria that you run on a real machine. The agent cannot touch your hardware, so kits are how hardware results enter the repo.
- **cloud-init:** a small program that a cloud runs at a VM's first boot to install your SSH key and set the network.

## 3. The order (what you do, and what the build session does)
**You, this week (before Day 1, Mon 2026-11-16):**
1. **Beelink, LT-X86-00 (30 min).** Boot it from a **Debian 13 live USB** (nothing gets installed) and run the commands in 22 §3. Record the CPU, TPM yes/no, Secure Boot state and the watchdog driver. Don't record the serial number.
2. **DigitalOcean, LT-CLU-01…12 (about 3 h, read-only).** Follow the rules in 22 §9.1. They map the cluster you already run, so the conversion plan (05 §9) starts from facts.
3. **Pi:** confirm it is a **Pi 5**. Flash the workbench card (Raspberry Pi OS Lite 64-bit, trixie) and check the EEPROM boot order (22 §4, LT-PI5-01 prerequisites).
4. **Jetson:** record the model and the current L4T version (`cat /etc/nv_tegra_release`). NVIDIA's flash tools need a **Linux x86 host** (brief 30 D-B1.8, [C-W18-021]). A Mac can't do it, so plan for an x86 Linux machine.

**You, week 2: the first real image on real hardware.**
5. **Beelink, LT-X86-01 (about 1 h).** The research already built a working A/B image (`evidence/lab/rauc-1152/`, RAUC v1.15.2, verity bundles). Build it in Lima on the Mac, write it to a **spare** USB SSD (check the disk twice), boot the Beelink from it and run the good/bad update tests. This is the first time a OneMind A/B image runs on your own hardware.

**The build session (brief 30), in parallel, in QEMU and CI:**
- **BM0 (weeks 1–2):** repo skeleton (`os/`, `lab-kits/`, `handbook/`), CI, the hygiene gate, the RAUC build job and the QEMU battery.
- **BM1 (weeks 2–4):** `make rootfs` and `make image BOARD=x86_64-efi|arm64-efi|rpi5|vm`, built from the same layers. The real images then replace the lab image on your machines (LT-X86-01/02, LT-PI5-01; LT-PI5-02 before G1).
- **BM2:** the Jetson package (D-B2.5) and LT-JET-01…03.

## 4. Gap found: DigitalOcean cannot boot the `vm` board as planned
DigitalOcean's docs say: "UEFI boot is not supported. Custom images must boot using BIOS." Images must also be under 100 GB uncompressed. The upload guide adds three requirements:
- **Formats:** raw with an MBR or GPT partition table, qcow2, VHDX, VDI or VMDK, optionally gzip or bzip2 compressed.
- **cloud-init:** version 0.7.7 or newer, with the ConfigDrive data source listed **before** NoCloud.
- **SSH:** sshd must start on boot, and an SSH key is mandatory.

Brief 30 defines `vm` "as x86_64-efi", which is UEFI only. That image **will not boot** as a DigitalOcean droplet.
- **Fix (proposed for the build session):** add a BIOS boot variant of the `vm` output for DigitalOcean.
  - It uses GRUB's BIOS target (`i386-pc`) on the same A/B layout. RAUC's GRUB backend is the BD-08 fallback the brief already requires.
  - It adds a `cloud` layer: cloud-init with ConfigDrive first, plus sshd.
- **Consequence:** on DigitalOcean there is **no Secure Boot or measured boot**, because those need UEFI. Treat a droplet as a cloud node whose trust comes from signed bundles and the network, not from the firmware.
- **Option 2 for the cloud (works today):** keep DOKS, or install on top of stock Debian 13 (P6 developer install, labelled unsupported) until the BIOS variant passes.

This is recorded in brief 30's founder box as **BD-DO-1**.

## 5. Unknowns to settle (they change kits, not the architecture)
- **Which Beelink?** Brief 22 assumes the **U55**: likely an i3-5005U, with Intel servicing ended and TPM and Secure Boot unknown. That makes it the "old PC" test node, never a recommended target. If yours is newer (a recent N100 or Ryzen model, for example), it may carry the Secure Boot kits too. LT-X86-00 answers this.
- **The Dell 5540** is the planned Secure Boot box (LT-X86-03/04). If it isn't available, Secure Boot hardware tests wait unless the Beelink turns out to have TPM 2.0 and a custom-key Secure Boot mode.
- **The Pi must be a Pi 5.** A Pi 4 is not a v0 board.
- **The Jetson's model and JetPack version** decide whether LT-JET-01 starts with a reflash.

## 6. Check yourself
1. Why does the Pi need its own kit when x86 already passed rollback in QEMU?
2. Why can't the planned `vm` image boot on DigitalOcean, and what are the two ways around it?
3. What does LT-X86-01 prove that no QEMU run can?
