# 27 · Founder learning path (W17)

**Date:** 2026-11-11 · **Tier:** C (secondary sources allowed when labelled; primary sources for everything the build depends on) · **Status:** draft 1
**Serves requirements:** F-8, F-7, F-9, M-6, M-8, RS-1, RS-7, D-002, W-2 (input)
**Claims:** `evidence/claims/W17.csv` (C-W17-001…030), plus reused rows from W5, W7, W8, W18, the teardowns and the labs. **Sources:** `evidence/sources/W17.md`. **Question-bank statuses:** `evidence/qbank/W17.md` (Q321).
**Consistent with:** `01-FOUNDATION-DECISION.md` revision 4.1 (synced 2026-11-11, SYNC5-c; first written against revision 2, when the core was Debian 13) and `28-…` §9 (Mac setup). **What moved:** since `01` rev. 4 the base-OS decision of record is **Ubuntu 26.04 LTS + RAUC A/B**, narrow (it wins 11 of 14 weight-shake runs) and conditional on Canonical's permission (Z-01) and G5. One image definition builds a **Ubuntu 26.04 leg and a Debian 13 leg** at parity until the base is locked before the first box ships (`01` §1, §3.1.6). RAUC A/B, k3s on platform nodes, NATS leaf below, and Jetson on L4T Ubuntu 24.04 are unchanged. **For this path:** every module teaches skills that apply to both legs. Where a module says "Debian", it is the Debian leg. Do the exercises in the Debian 13 VM as written, and keep a second Lima VM on Ubuntu 26.04 so you can repeat L1–L5 on the decision of record.

> ### Explain it like I'm the founder
> You already run the hard half of OneMind: Kubernetes, NATS, GitOps and the agents. What you have not done yet is the layer *under* Kubernetes: how a box boots, how its disk is laid out, how a whole operating system is built as one file, swapped for a new one, and rolled back when the new one is broken. That layer is what turns "a cluster with a portal" into "an OS".
> So this path skips what you know and goes deep where the build is going next. There are 12 short modules, in the same order as the build. Each one says **why you need it now**, **what to read** (free, official material first), **one hands-on exercise** in the Linux VM on your Mac, the **words** you'll meet, and **questions to check yourself**. When you can do a module's exercise, you can review that part of the build yourself, which is the point: you should be able to approve or reject the foundation decisions, not just trust them.
> The fastest single resource is **Bootlin's free training slides** (the embedded Linux industry's standard course, published openly) [C-W17-001]. The single most important module is **L5, A/B updates with RAUC**, because that is what keeps boxes in people's homes from bricking.

---

## Contents

1. [How to use this path](#1-how-to-use-this-path)
2. [The map: modules in build order](#2-the-map-modules-in-build-order)
3. [The modules (L0–L11)](#3-the-modules-l0l11)
4. [What competitors do: whose code teaches what](#4-what-competitors-do-whose-code-teaches-what)
5. [Resource catalogue](#5-resource-catalogue)
6. [Warnings: stale or blocked resources, and two inconsistencies found](#6-warnings-stale-or-blocked-resources-and-two-inconsistencies-found)
7. [Recommendations → requirement IDs](#7-recommendations--requirement-ids)
8. [Glossary](#8-glossary)

---

## 1. How to use this path

**Who it is for.** Zeus: strong in Kubernetes, NATS JetStream, GitOps, Python and TAK; still learning Linux, OS and platform engineering (context/04). So Kubernetes and NATS modules (L6, L7) teach only what is *different* on a box; the Linux, image, update, security and robotics modules start from the beginning.

**Time budget (assumption).** About **4 hours a week** of study next to building, so roughly 6 months for L0–L11. This is an assumption, not a measured figure; `20-PLAN-180-DAYS.md` (not yet written) owns the real capacity plan. If the build moves faster, read the module in the week its build step starts; never more than one module ahead.

**Shape of every module.**

| Part | What it is |
|---|---|
| Why now | The build step and the lab test that need this knowledge |
| Read | Primary resources first, in order; time estimates are rough |
| Do | One exercise in the Lima VM (L0) or on real hardware; it mirrors a test in `22-…` |
| Words | Vocabulary you'll meet (also in §8) |
| Check yourself | Questions you should be able to answer without notes |
| Done when | A concrete pass condition |

**Rules for the labs.** Run everything inside the Linux VM, never on macOS directly, and never with real signing keys. Third-party installers run only in a throwaway VM with no folders shared from the Mac (`--mount-none`), as in `28-…` §9.3.

---

## 2. The map: modules in build order

```
Build plan (01, 28)                          Learning module                      Lab / gate it prepares you for
────────────────────────────────────────────  ───────────────────────────────────  ─────────────────────────────────────
Week 0   Mac + Lima dev VM                     L0  Your Mac as a Linux workbench    T-W18-1 (which Mac? nested virt?)
Wk 1–4   Core as a script on plain Debian (P6) L1  Boot chain + systemd             —
                                               L2  Disks, partitions, filesystems   01 §4.3 layout review
Wk 2–6                                         L3  The kernel and its config        T-W18-4 (kernel bump dry run)
Wk 3+    Same Dockerfile layers → image        L4  Image builds                     first bootable image in QEMU
Wk 4–10  A/B + health gate + signing           L5  A/B updates with RAUC  ★         rollback spike, efi+k3s+power-cut spike
Wk 6–12  k3s on a read-only root, backups      L6  k3s for a Kubernetes person      fresh-box restore drill
Wk 8–12  NATS leaf below k3s                   L7  NATS at the edge                 leaf outage / store-and-forward test
Wk 10–18 LUKS2, signing chain, Secure Boot     L8  Security                         X-2R on real firmware (F-SB-1…3)
Wk 14–20 Robot runtime profile                 L9  Real time                        cyclictest acceptance (12 h)
                                               L10 ROS 2                            LAB-W7-2 (shared memory in use)
Wk 16–24 Jetson flavor                         L11 Jetson                           T-W3-06, LAB-W7-6 (meta-tegra)
Year 1+  Optional depth: Yocto, own kernel config (K2), Isaac Sim on a cloud GPU
```

The week numbers are this file's mapping onto the sequence that `01-…` and `28-…` §8 already set (platform script on Debian in weeks 1–4, image from about week 3, RAUC A/B, k3s, then robotics within 180 days). They are not the plan itself; re-map when `20-…` exists.

---

## 3. The modules (L0–L11)

### L0 · Your Mac as a Linux workbench (week 0)

**Why now.** Everything below runs in Linux. macOS can't build kernels or OS images natively, so the dev setup in `28-…` §9 puts a Debian 13 VM on the Mac with Lima [C-W18-053]. You need to be at home in it before anything else.

**Read.**
1. Lima docs, the `vz` VM type page: it uses Apple's Virtualization.framework and cannot run an Intel guest on an Apple-silicon Mac (or the reverse) [C-W18-053]. Nested virtualization (running QEMU *with* acceleration inside the VM) needs an M3 or later and macOS 15+ [C-W18-054].
2. Docker's multi-platform build guide: the three ways to build for another CPU (emulation, native builders, cross-compiling) [C-W17-012].
3. `28-…` §9.2 "What runs where".

**Do.** Create the `onemind-dev` VM from `28-…` §9.3; inside it install Docker CE and QEMU; build a tiny `arm64` and `amd64` container from one Dockerfile with `docker buildx build --platform linux/amd64,linux/arm64`; check `ls -l /dev/kvm`.

**Words.** VM, hypervisor, guest/host, Virtualization.framework, Rosetta, binfmt, nested virtualization, buildx, multi-arch image.

**Check yourself.** Why can't the Mac build an x86 OS image at native speed? What changes if your Mac is an M1 rather than an M3? Why do releases get built in CI on native runners and not on your Mac?

**Done when.** `/dev/kvm` exists in the VM (or you know your Mac can't do it, and that answers T-W18-1), and one Dockerfile produces images for both CPUs.

### L1 · The boot chain and systemd (weeks 1–2)

**Why now.** Weeks 1–4 install OneMind Core as a script on plain Debian (`28-…` §8). Every service you add is a systemd unit, and the health gate later (L5) is a systemd unit whose ordering decides whether rollback works [C-LAB-rauc-k3s-gate-001].

**Read.**
1. Linux Foundation, *Introduction to Linux* (LFS101), free; skim what you know, do the command-line and processes chapters [C-W17-003].
2. systemd `bootup(7)`: firmware → boot loader → kernel → initrd → `sysinit.target` → `basic.target` → `multi-user.target` [C-W17-028].
3. Bootlin's *Embedded Linux system development* slides, the parts on boot loaders, the kernel and the root filesystem [C-W17-001, C-W17-002].

**Do.** In the VM: `systemd-analyze critical-chain`, `systemctl list-dependencies multi-user.target`, write a unit with `After=`, `Wants=`, `Type=notify` and `OnFailure=`, and watch it in `journalctl -b`.

**Words.** Firmware (UEFI), boot loader, kernel, initrd/initramfs, PID 1, unit, target, `Type=notify`, `After=` vs `Requires=`, journal.

**Check yourself.** What runs between power-on and your first unit? Why must the OneMind health gate *not* be ordered after `k3s.service`? (Answer in `01-…` §4.2 item 5: k3s is `Type=notify` with no start timeout, so a hung k3s would hang the gate too.)

**Done when.** You can draw the boot chain of the VM from memory and explain each arrow.

### L2 · Disks, partitions and filesystems (weeks 2–3)

**Why now.** The disk layout in `01-…` §4.3 is the one decision that cannot change later without reflashing every box. You should be able to review it line by line.

**Read.**
1. The UAPI Group's *Discoverable Partitions Specification* and *Unified Kernel Images* (short, precise) [C-W17-008].
2. `systemd-cryptenroll(1)`: how a LUKS2 data partition gets a recovery key, a TPM2 key or a FIDO2 key [C-W17-007].
3. `01-…` §4.3, then HAOS's layout in its teardown (kernel/system A and B, bootstate, overlay, data) [C-TD-home-assistant-os-007].

**Do.** In the VM, make a 4 GiB disk image, partition it like §4.3 with `sgdisk` (ESP, boot-a/b, system-a/b, data), put LUKS2 on the data partition with `cryptsetup`, add a recovery key with `systemd-cryptenroll --recovery-key`, mount a root partition read-only and see what breaks when a program tries to write `/etc`.

**Words.** GPT, partition type GUID, ESP, FAT32/VFAT, ext4/EROFS/squashfs, read-only root, overlay, bind mount, LUKS2, keyslot, recovery key.

**Check yourself.** Why are there two system partitions but one data partition? What goes in `/data` and what may never go in the system slot? Why did k3s need six bind mounts on a read-only root [C-LAB-rauc-k3s-gate-004]?

**Done when.** You can explain each of the seven partitions in §4.3 and what is lost if each is wiped.

### L3 · The kernel and its configuration (weeks 2–6)

**Why now.** OneMind's launch kernel route is K1: the base's stock kernel on x86/arm64 (Canonical's on the Ubuntu leg, Debian's on the Debian leg; `01` §1), Raspberry Pi's kernel on the Pi, NVIDIA's L4T kernel on Jetson, plus a **kernel contract** checked in CI (`28-…` §6.2). The Secure Boot release may move x86/arm64 to a OneMind-built LTS kernel (K2) [01 §7.1 R2-10]. You need enough to read a kernel config and run the T-W18-4 bump dry-run.

**Read.**
1. Kernel docs, *Kernel Build System* (Kconfig, Kbuild, configuration targets, external modules) [C-W17-027].
2. Bootlin's *Linux kernel and driver development* slides, first third (modules, device tree, how drivers bind) [C-W17-001].
3. Optional, for the curious: *Linux From Scratch*, which builds a whole system from source; read it, don't run it [C-W17-005].

**Do.** In the VM, build 6.18.y for arm64 with `defconfig`, then turn on `CONFIG_PREEMPT_RT` with `scripts/config`, and compare. W18 measured this at about 5.5 minutes native and under 2 minutes for an x86 cross-build on an M5-class Mac [C-W18-066]. Then `modinfo` a module and find out which key signed it (L8 comes back to this).

**Words.** Kernel vs userland, LTS kernel, vendor BSP kernel, Kconfig, `.config`, config fragment, module, out-of-tree module, DKMS, device tree, kernel command line.

**Check yourself.** Why can't the Jetson flavor use Debian's kernel? Why does Secure Boot plus a third-party driver push OneMind toward building its own kernel [C-DEC-008…010]? What does "kernel contract" check, and why is it cheaper than owning a kernel?

**Done when.** You can read a `.config` diff and say which options the contract requires (cgroups v2, overlayfs, dm-verity, TPM, RT on the robot profile).

### L4 · Image builds (weeks 3–6)

**Why now.** From about week 3, the same Dockerfile layers that install Core on plain Debian also produce the OS image (`28-…` §8). This is the umbrelOS pattern: a multi-stage Docker build of Debian trixie (OneMind builds the same layers on `ubuntu:26.04` too, one leg each) with the base image pinned by digest and apt pinned to snapshot.debian.org dates [C-TD-umbrelos-003].

**Read.**
1. Docker's multi-stage build docs, then the multi-platform guide again [C-W17-012].
2. snapshot.debian.org: what a dated apt snapshot is and why it makes builds repeatable [C-W17-029]; reproducible-builds.org's docs for the "why".
3. The image-builder comparison in `28-…` §7 (Rugix Bakery, debos, mkosi, Buildroot, Yocto, bootc, NVIDIA's flash tools).
4. Bootlin's *Buildroot* and *Yocto* slides, chapters 1–2 only, so you understand what HAOS and balenaOS do and why `01-…` did not pick them for the core [C-W17-001].

**Do.** Write a Dockerfile `FROM debian:trixie` that installs systemd, a kernel and `rauc`, export its filesystem (`docker export`), turn it into a raw disk image with your L2 layout, and boot it in QEMU inside the VM. The real pipeline uses a proper tool (see §6 on which one); doing it by hand once shows you what the tool does.

**Words.** rootfs, base image, layer, multi-stage build, digest pinning, apt snapshot, reproducible build, disk image (raw/qcow2), Buildroot, Yocto/OpenEmbedded, BSP layer, mkosi, bootc.

**Check yourself.** What makes two builds a month apart produce the same bytes? Why is a Dockerfile a good image definition for a beginner *and* an AI agent? Why does Yocto need a 140 GB Linux build host [C-W18-050] while a Dockerfile build runs on your Mac?

**Done when.** Your hand-made image boots to a login prompt in QEMU.

### L5 · A/B updates with RAUC ★ (weeks 4–10)

**Why now.** This is the core of "an OS, not a script": two copies of the system, install into the idle one, boot it once on trial, and keep it only if a health gate says yes [01 §4.2]. The first go/no-go gate in the plan is a rollback spike, and the `efi` + k3s + power-cut spike must pass before the first image ships.

**Read (in this order).**
1. RAUC docs, *RAUC Basics*: slots, bundles, target-slot selection, boot-slot selection [C-W17-009].
2. RAUC docs, *Integration*: `system.conf`, the keyring on the device and the signing key on the build host (PEM or PKCS#11/HSM), and the three bootloader backends `grub`, `efi` and `custom` [C-W17-009]. Read the EFI section twice: it finds the booted slot from the `BootCurrent` variable and expects two VFAT partitions with EFI-stub kernels or UKIs [C-W17-010].
3. Raspberry Pi's `tryboot`: a one-shot flag that boots the other partition once and clears itself; `tryboot_a_b=1` switches at partition level [C-W17-011, C-W3-066].
4. HAOS's real RAUC setup, the best worked example: `system.conf` with kernel/rootfs A and B slots [C-TD-home-assistant-os-008], verity bundles with a compatible check [C-TD-home-assistant-os-009], separate release and dev CAs [C-TD-home-assistant-os-012], and GRUB's "boot only if OK=1 and TRY<3" logic [C-TD-home-assistant-os-016].
5. OneMind's own lab write-ups: `evidence/lab/rauc/`, `rauc-k3s-gate/`, `secureboot-rauc/`. They show where a naive gate commits a broken update [C-LAB-rauc-k3s-gate-006…008].

**Do.** In the VM: build two RAUC bundles (a good one and one whose k3s never starts), sign them with a throwaway CA, install the good one, then the bad one, and watch the gate refuse the bad one and fall back. Then kill QEMU in the middle of an install and confirm the old slot still boots. This is a rerun of the existing lab scripts, not new design.

**Words.** Slot (A/B), active/inactive slot, bundle, manifest, `compatible`, verity bundle, keyring, signing certificate, boot attempts/try counter, mark-good/mark-bad, health gate, commit, rollback, tryboot, `BootNext`/`BootCurrent`, UKI.

**Check yourself.** What exactly is "committed", and who decides? Why does the gate use *fresh* signals (heartbeat newer than this boot) rather than "pods are Running"? Why 3 tries rather than 1? Why does an old, validly signed kernel need a version-match rule [C-LAB-secureboot-rauc-018]? What happens to a Pi if the update is interrupted mid-write?

**Done when.** You can explain the boot → update → trial → commit-or-rollback sequence in `04-…` to someone else, and the bad-bundle exercise rolls back on its own.

### L6 · k3s for someone who already runs Kubernetes (weeks 6–12)

**Why now.** You know Kubernetes on DOKS. On a box, four things are new: the datastore lives on the box, the node can be physically stolen, the root is read-only, and an OS rollback can move k3s backwards.

**Read.**
1. k3s *Architecture*: server (control plane + datastore) vs agent (kubelet, runtime, CNI only) [C-W17-013]. This is why robots and field kits run **agent only** [01 §4.5].
2. k3s *Backup and Restore*: for SQLite the vendor says "take a copy" of the db folder, and the token must come with it or the backup is useless [C-W17-014]. Then read why OneMind does an online `sqlite3 .backup` instead, and the lab that restored a whole box [C-W5-009].
3. k3s *CIS Hardening Guide* [C-W17-015].
4. Olares's choices for contrast: k3s pinned to a version, external etcd, and most bundled add-ons disabled [C-TD-olares-021, C-TD-olares-023].
5. Optional: *Kubernetes The Hard Way*, if you have never built a control plane by hand; it is for learning, not production [C-W17-016].

**Do.** Install k3s in the VM with the bind mounts from `01-…` §4.2 item 1b, back it up with the OneMind method (online SQLite backup + token + restic), destroy the VM, restore onto a fresh one with the **same node name**, and check the data.

**Words.** Server/agent, kine, SQLite/etcd datastore, token, node password, `--cluster-init`, local-path provisioner, `Retain` reclaim policy, secrets encryption, CIS benchmark, Pod Security.

**Check yourself.** Why does a single box use SQLite and not etcd? What breaks if you restore without the token? Why can't k3s be upgraded inside the read-only slot by the system-upgrade-controller [C-W3-065]? What does the k3s-minor guard protect against after a rollback?

**Done when.** The fresh-box restore brings your test app back with identical data.

### L7 · NATS at the edge (weeks 8–12)

**Why now.** Below k3s, small devices (sensors, a Pi on an SD card) run a NATS leaf that stores data during an outage and forwards it later; OneMind's lab delivered 600/600 messages after a hub outage [C-W8-050]. You know NATS clusters; leaf nodes, JetStream domains and per-device credentials are the new part.

**Read.**
1. NATS docs, *Leaf nodes*: an outbound-only connection (works behind a firewall), clients connect without special config, the account decides which subjects cross, and a leaf with its own JetStream needs its own **domain** [C-W17-017].
2. NATS docs, decentralized JWT auth and operator mode [C-W17-018].
3. NATS by Example (SECONDARY; runnable examples including leaf nodes with JWT auth) [C-W17-019].

**Do.** Run a hub in the VM and a leaf in a second container with its own JetStream domain, cut the link, publish 500 messages, restore it, and source the leaf's stream into the hub. This repeats the W8-1 lab.

**Words.** Leaf node, hub, account, JetStream domain, sourcing/mirroring, operator, NKey, user JWT, credentials file, revocation.

**Check yourself.** Why must each device's leaf credential be revocable on its own? What collides if two JetStream systems share a domain? Why is a leaf "a forwarding pipe, not a peer bus"?

**Done when.** The outage test shows no lost and no duplicated messages.

### L8 · Security: from signing keys to Secure Boot (weeks 10–18)

**Why now.** Signed releases start with release 1, LUKS2 data from the first boot, and the Secure Boot release follows [01 §4.7]. You will be the person holding the root key, so you must understand the chain.

**Read.**
1. The signing chain in `01-…` §4.2 item 7 (offline root, 2-of-3 release signers, expiry, revocation), then HAOS's CA split [C-TD-home-assistant-os-012].
2. *A Practical Guide to TPM 2.0* (Arthur and Challener, 2015), an open-access book (SECONDARY: open-access status not opened on the publisher's page) [C-W17-022]; chapters on PCRs, sealing and keys only.
3. `systemd-cryptenroll(1)` again, the TPM2 and PCR options [C-W17-007], and the UKI spec [C-W17-008].
4. The X-2R lab README in `evidence/lab/secureboot-rauc/`: it booted signed UKIs, rolled back, refused a tampered kernel and unlocked the disk by TPM, and also found the downgrade gap [C-LAB-secureboot-rauc-012…018].
5. Supply chain: SLSA (read version 1.2, the current one) [C-W17-020] and Sigstore's Cosign quickstart [C-W17-021]; HAOS now signs its release checksums with Cosign [C-TD-home-assistant-os-015].
6. Law, once: the CRA lists operating systems as an "important" Class I product [C-W6-011]; read `07-…` §CRA for what that means for OneMind.

**Do.** In the VM, with OVMF and swtpm: enroll your own throwaway PK/KEK/db keys, sign a UKI, boot it with Secure Boot on, seal a LUKS2 key to PCR 7 + a signed PCR 11 policy, then flip Secure Boot off and confirm the disk will not unlock. (This is the X-2R lab; reuse its script.)

**Words.** Root of trust, offline root key, HSM/hardware token, certificate chain, revocation, Secure Boot, PK/KEK/db/dbx, shim, MOK, SBAT, UKI, TPM, PCR, sealing, measured boot, SBOM, provenance, SLSA, Sigstore/Cosign.

**Check yourself.** Secure Boot answers "is this ours?", not "is this current?". What closes the gap? Why does a key in UEFI db not let you sign kernel modules for Debian's kernel [C-DEC-009, C-DEC-010]? What is in your emergency kit if the TPM dies?

**Done when.** You can run a key ceremony on paper: which key lives where, who can sign a release, and how a stolen release key is revoked.

### L9 · Real time (weeks 14–16)

**Why now.** The robot profile offers an RT kernel with a per-unit acceptance test, and anything tighter than about 1 ms goes to a microcontroller [01 §4.7]. You need to know what "real time" can and can't promise.

**Read.**
1. Kernel docs, PREEMPT_RT: theory of operation, how RT kernels differ, and hardware considerations [C-W17-006].
2. Bootlin's *Real-time Linux with PREEMPT_RT* slides [C-W17-001].
3. `08-…` on DC-14: Pi 5 spikes over 1 ms under memory stress, and two "identical" Orin modules differed by about 10 µs vs 90+ µs [C-REF-DC-technical-001, C-REF-DC-technical-002].

**Do.** Run `cyclictest` on the VM's RT kernel from L3 with and without a stress load. The numbers in a VM mean nothing; the point is learning the tool before T-W18-7 on real hardware.

**Words.** Latency, jitter, worst case, PREEMPT_RT, priority inheritance, threaded IRQs, CPU isolation (`isolcpus`), SCHED_FIFO, cyclictest, MCU.

**Check yourself.** Why is the *worst* case the only number that matters? Why does a GPU or memory-heavy app on the same board hurt a control loop?

**Done when.** You can read a cyclictest histogram and state a latency budget.

### L10 · ROS 2 (weeks 14–20)

**Why now.** "Connect a robot, use OneMind" means ROS 2 runs on the box. The current LTS, **Lyrical Luth** (May 2026, supported to May 2031), is Tier 1 only on Ubuntu 26.04; **Debian 13 and Ubuntu 24.04 are Tier 3**, which means building from source [C-W7-027, C-W7-029]. That is why ROS runs in containers on the Debian host, not as host packages.

**Read.**
1. ROS 2 docs, *Get Started* and the beginner CLI tutorials (nodes, topics, services, parameters, `ros2 bag`), then *colcon* (building a workspace). docs.ros.org blocks automated readers, so this run read the source repository at a pinned commit; in a browser the site works normally [C-W17-030].
2. The Lyrical supported-platforms page: the tier table and the middleware table (Fast DDS, Connext, Cyclone DDS and Zenoh are Tier 1) [C-W7-027].
3. `01-…` §4.7: the signed "robot runtime" profile (host network, host IPC, `SYS_NICE`) and why Fast DDS shared-memory failures are silent [C-REF-DC-technical-003].

**Do.** In the VM, run two ROS 2 containers (talker and listener) with host IPC, then without it, and prove which one actually used shared memory. That is the check in LAB-W7-2.

**Words.** Node, topic, service, action, parameter, launch file, workspace, colcon, distro (Jazzy/Kilted/Lyrical), REP 2000 tiers, DDS, RMW, Zenoh, QoS, shared memory transport.

**Check yourself.** Why can't OneMind just `apt install` ROS on Debian 13? What happens when the NVIDIA driver on the host moves but the robot container doesn't [C-REF-DC-technical-004]?

**Done when.** You can run, inspect and record a ROS 2 graph in containers.

### L11 · Jetson (weeks 16–24)

**Why now.** The Robotics flavor runs on NVIDIA L4T for the first beta, every Jetson is flashed A/B at the factory, and the meta-tegra (Yocto) route is tested within 180 days (LAB-W7-6) [01 §4.1, §4.2].

**Read.**
1. NVIDIA's Jetson archive: the current line is JetPack 7.2.1 / Jetson Linux R39.2.1 [C-W17-024]. Read the Jetson Linux Developer Guide sections on flashing, the boot flow, rootfs A/B and image-based OTA.
2. Jetson AI Lab tutorials: *Getting Started*, *SSD + Docker Setup*, *RAM Optimization*, and *Quick Start Guide with Yocto* (JetPack 7.2.1, AGX Thor, AGX Orin and Orin Nano), the last being NVIDIA's own on-ramp to the meta-tegra route [C-W17-025].
3. Isaac ROS *Getting Started*: officially only Jetson Thor/Orin on JetPack 7.2, x86 with an Ampere-or-newer GPU on Ubuntu 24.04, and DGX Spark [C-W17-023].
4. balenaOS's Orin build from OE4T meta-tegra, as a competitor that already ships the non-Ubuntu route [C-TD-balenaos-042].
5. NVIDIA DLI's self-paced catalogue, "Simulation and Physical AI" category, filtered to free courses. The catalogue page does not list titles or prices itself, so pick there [C-W17-026].

**Do.** On the Orin Nano Super when it arrives: install JetPack from the USB ISO on the Mac (no Ubuntu host needed) [C-W18-023], move the root to NVMe, run one Isaac ROS container, and record `cat /etc/nv_tegra_release`. Then try T-W18-6 (flashing from an arm64 Ubuntu VM with USB pass-through), which is still untested.

**Words.** Module vs carrier board, JetPack, Jetson Linux/L4T, BSP, flashing, recovery mode, initrd flash, rootfs A/B, OTA payload, fuses, CUDA/TensorRT, meta-tegra.

**Check yourself.** Why does a Jetson need a different flavor? Why do its software support periods end before the hardware stops shipping (finding 8 in `00-…`)? What does `OTA_MAX_RETRY_COUNT=0` do to a failed update [C-W3-051]?

**Done when.** You can flash, update and roll back a Jetson, and say which parts NVIDIA controls and which OneMind controls.

### After the 180 days (optional depth)

- **Yocto properly** (Bootlin *Yocto* course, full) if LAB-W7-6 makes meta-tegra the Jetson default.
- **Own kernel config (K2)** (Bootlin kernel slides, full) if the Secure Boot release triggers it.
- **Isaac Sim/Lab** on a cloud RTX GPU when robotics simulation boxes come in (needs an RTX-class GPU on Linux/Windows [C-W18-058]).
- **Fedora IoT / bootc** for the year-2 Industrial profile (F-12): the `w2-fedora-bootc-greenboot` lab is the starting exercise.

---

## 4. What competitors do: whose code teaches what

Reading real code at pinned commits is the "proven competitors" rule applied to learning. Licence rule: study the pattern; never copy code from umbrelOS (PolyForm Noncommercial) or Olares (AGPL) into OneMind.

| Competitor (code at pinned SHA in its teardown) | What its code teaches best | Their constraints | Constraint fit with OneMind | Read during |
|---|---|---|---|---|
| **Home Assistant OS** | Buildroot images, the RAUC `system.conf`, verity bundles, CA split, GRUB try counter, Pi 5 tryboot backend [C-TD-home-assistant-os-003, -008, -009, -012, -016, -017] | Small team, appliance, Docker not Kubernetes, no robotics | **High for L2, L5, L8** (same engine as OneMind); low for L6 | L2, L5, L8 |
| **umbrelOS** | A Debian trixie OS image defined as a multi-stage Dockerfile with digest and snapshot pinning [C-TD-umbrelos-003, C-W18-015] | Small team, Pi 5 + x86, Docker apps, Rugix updater | **High for L4** (same base and build style); different update engine | L4 |
| **Olares** | k3s choices at scale: pinned version, external etcd, add-ons disabled [C-TD-olares-021, C-TD-olares-023] | Kubernetes-first, script install, no OS image | **Medium for L6** (Kubernetes yes, appliance no) | L6 |
| **balenaOS** | The OS root as a container image; Jetson Orin from meta-tegra instead of NVIDIA's Ubuntu [C-TD-balenaos-010, C-TD-balenaos-042] | Yocto, fleet SaaS, balena engine, no k3s | **Medium for L11** (Jetson route), low elsewhere | L11 |
| **Fedora IoT** | bootc/ostree images, greenboot health checks [C-W2-017] | Red Hat lineage, Pi 5 not mainstream | **Low now, high for the year-2 Industrial profile** | after 180 days |

---

## 5. Resource catalogue

Cost is "free" unless stated. "Freshness" says how close the material is to what OneMind actually runs.

| Resource | Covers | Type | Cost / licence | Freshness for OneMind | Claim |
|---|---|---|---|---|---|
| Bootlin training materials (bootlin.com/docs) | Embedded Linux, kernel/drivers, Yocto, Buildroot, boot time, PREEMPT_RT, debugging | PRIMARY (vendor course) | Free, CC BY-SA 3.0 | Updated per session; generic, not Debian-specific | C-W17-001, 002 |
| Linux Foundation LFS101 | Linux command line and basics | PRIMARY | Free | Distro-neutral | C-W17-003 |
| systemd man pages (`bootup`, `systemd-cryptenroll`) | Boot, units, LUKS2 enrolment | PRIMARY | Free | Current | C-W17-028, 007 |
| UAPI Group specs | Partitions, UKIs, boot loader spec | PRIMARY | Free | Current | C-W17-008 |
| Kernel docs (docs.kernel.org) | Kbuild, Kconfig, PREEMPT_RT internals | PRIMARY | Free | Current (rc build) | C-W17-027, 006 |
| Linux From Scratch | Building a system from source | PRIMARY | Free online | Maintained (systemd book) | C-W17-005 |
| The Debian Administrator's Handbook | Debian administration | PRIMARY | Free, CC BY-SA / GPL | **Stale: Debian 11 edition** | C-W17-004 |
| Docker build docs | Multi-stage, multi-platform | PRIMARY | Free | Current | C-W17-012 |
| snapshot.debian.org, reproducible-builds.org | Pinned, repeatable builds | PRIMARY | Free | Current | C-W17-029 |
| Lima docs | The Mac dev VM | PRIMARY | Free | Current | C-W18-053, 054 |
| RAUC docs | A/B updates, signing, backends | PRIMARY | Free | Current (1.15.x dev docs) | C-W17-009, 010 |
| Raspberry Pi docs (`tryboot`) | Pi A/B boot | PRIMARY | Free | Current | C-W17-011 |
| k3s docs | Architecture, backup, CIS hardening | PRIMARY | Free | Current | C-W17-013, 014, 015 |
| Kubernetes The Hard Way | Control plane by hand | PRIMARY | Free | Learning only | C-W17-016 |
| NATS docs | Leaf nodes, domains, JWT auth | PRIMARY | Free | Current | C-W17-017, 018 |
| NATS by Example | Runnable NATS examples | SECONDARY | Free | Current | C-W17-019 |
| A Practical Guide to TPM 2.0 | TPM concepts and code | SECONDARY (status) | Open access, noncommercial | 2015, concepts still valid | C-W17-022 |
| SLSA, Sigstore docs | Supply chain, signing | PRIMARY | Free | Read SLSA 1.2 | C-W17-020, 021 |
| ROS 2 docs (docs.ros.org; source repo) | ROS 2 tutorials, platform tiers | PRIMARY | Free | Lyrical LTS | C-W7-027, 029 |
| Jetson Linux docs, Jetson AI Lab | Flashing, A/B, OTA, Jetson tutorials | PRIMARY | Free | JetPack 7.2.1 | C-W17-024, 025 |
| Isaac ROS docs | Accelerated ROS on Jetson/x86 | PRIMARY | Free | JetPack 7.2, Lyrical | C-W17-023 |
| NVIDIA DLI catalogue | Physical AI courses | PRIMARY | Mixed free/paid (not itemised on page) | Unknown per course | C-W17-026 |
| OneMind's own lab write-ups (`evidence/lab/`) | RAUC, k3s gate, Secure Boot, restore, NATS leaf | LAB | Free | Exactly OneMind's design | lab claim rows |

---

## 6. Warnings: stale or blocked resources, and two inconsistencies found

1. **The Debian Administrator's Handbook online edition is for Debian 11**, two releases behind trixie [C-W17-004]. Use it for concepts only; check commands against Debian 13's own man pages.
2. **Several official sites block automated readers** (docs.ros.org, wiki.debian.org/SecureBoot, the Linux Foundation RT wiki, raspberrypi.com docs, Springer) [C-W17-030]. They open normally in a browser. This run used source repos at pinned SHAs instead; nothing was bypassed.
3. **Inconsistency: RAUC's ESP-type advice vs the §4.3 layout (for W3, not changed here).** RAUC's docs say the boot-slot partitions *may omit* the ESP type GUID so firmware does not auto-create boot entries that fight RAUC [C-W17-010]. `01-…` §4.3 gives boot-a/b the ESP type and handles the side effect with rule SB-2 (remove firmware auto-entries and re-check every boot). Both can work, and X-2R passed with the ESP type in OVMF. On real PC firmware (F-SB-1…3 on the Dell 5540) the RAUC-documented option should be tested as a variant. Reported as a follow-up; this file does not change the decision.
4. **Resolved (rev. 4.1 sync): `30-…` BD-05 names the builder:** a Containerfile-defined rootfs plus OneMind's own assembler, using the tools the passing labs used; Rugix Bakery (`28-…` §7) is superseded. The original open point follows. **Open point: which tool builds the image now that the engine is RAUC.** `28-…` §7 chose Rugix Bakery, partly because it "pairs with the Rugix updater"; revision 2 of `01-…` switched the engine to RAUC and does not restate the image builder. L4 teaches the shared part (a Dockerfile-defined rootfs, the umbrelOS pattern) and the hand-made path. `30-NEXT-ULTRACODE-BUILD-BRIEF.md` should name the builder explicitly: Rugix Bakery producing images that carry RAUC, or mkosi (the W18 runner-up, strongest on UKIs and verity).
5. **The week mapping is provisional** until `20-PLAN-180-DAYS.md` exists.

---

## 7. Recommendations → requirement IDs

| ID | Recommendation | Requirement IDs |
|---|---|---|
| REC-W17-01 | Follow modules L0–L11 in build order, at most one module ahead of the build; each module's "done when" is the learning gate before reviewing that build step | F-9, M-6, M-8, RS-7 |
| REC-W17-02 | Make L0 (Lima VM) day-one work; it also answers T-W18-1 (which Mac, nested virtualization) | F-8, D-002 |
| REC-W17-03 | Treat L5 (RAUC A/B) and L8 (signing and Secure Boot) as must-complete before the first public image, because the founder holds the release keys | R-1, R-3, F-7, U-4 |
| REC-W17-04 | Learn k3s and NATS only as deltas from the DOKS cluster (L6, L7): datastore on the box, agent-only field nodes, leaf domains, per-device credentials | N-9, P-9, AI-9, N-6 |
| REC-W17-05 | Learn ROS 2 in containers, not on the Debian host (Lyrical is Tier 3 on Debian 13), and Jetson on real hardware once bought | M-7, N-7, N-8, F-1, F-2 |
| REC-W17-06 | Read competitor code at the pinned SHAs in §4 as the worked examples; patterns only, never copied code from non-Apache-compatible licences | RS-2, RS-1, D-001 |
| REC-W17-07 | Reuse the module format (goal, vocabulary, lab, check yourself) later for the public education programme | W-1, W-2 |
| REC-W17-08 | Route the two §6 findings to their owners: the ESP-type variant to W3/`22-…`, the image-builder choice to `30-…` | F-7, F-9 |

---

## 8. Glossary

| Term | Meaning |
|---|---|
| **A/B update** | Two copies of the OS; update the idle copy, boot it on trial, keep it only if healthy, otherwise go back. |
| **Agent (k3s)** | A node that runs workloads but holds no control plane or datastore [C-W17-013]. |
| **BSP** | Board Support Package: the vendor's kernel, drivers and boot firmware for a board (e.g. NVIDIA L4T). |
| **Bundle (RAUC)** | One signed file containing the new OS images plus a manifest. |
| **Bind mount** | Making a writable folder from the data partition appear at a path inside the read-only root. |
| **Boot chain** | Firmware → boot loader → kernel → initrd → systemd → services. |
| **colcon** | The tool that builds a ROS 2 workspace. |
| **Commit / mark-good** | Telling the boot system "this new slot is healthy, keep it". |
| **Compatible (RAUC)** | A string that must match between bundle and device, so a Pi bundle never lands on a PC. |
| **Config fragment** | A small file of kernel options merged into a base config. |
| **cyclictest** | A tool that measures how late a periodic task wakes up; the standard real-time latency test. |
| **DDS / RMW** | The messaging middleware under ROS 2 and the layer that lets you swap it. |
| **Device tree** | A data file telling an ARM kernel what hardware a board has. |
| **Digest pinning** | Referring to a container image by its content hash, so it can never silently change. |
| **dm-verity** | A kernel feature that checks every block of a read-only partition against a signed hash tree. |
| **ESP** | EFI System Partition: the FAT partition UEFI firmware boots from. |
| **Fresh signal** | Health evidence produced after this boot (not leftover status from before the update). |
| **Health gate** | The OneMind service that decides whether to commit a trial boot. |
| **initrd / initramfs** | A small temporary root filesystem the kernel uses to find and unlock the real one. |
| **JetPack / L4T** | NVIDIA's Jetson software stack and its Linux (Jetson Linux, "Linux for Tegra"). |
| **JetStream domain** | A name that keeps one JetStream system separate from another across a leaf link [C-W17-017]. |
| **Kernel contract** | The list of kernel features OneMind requires, checked automatically in CI for every kernel it ships. |
| **Keyring (RAUC)** | The CA certificates on the device that bundles must be signed under. |
| **kine** | k3s's shim that lets Kubernetes use SQLite instead of etcd. |
| **Leaf node** | A NATS server that dials out to a hub and forwards subjects both ways [C-W17-017]. |
| **LTS kernel** | A kernel series kernel.org maintains with fixes for years. |
| **LUKS2** | Linux disk encryption format; can hold several keys (passphrase, recovery, TPM, FIDO2) [C-W17-007]. |
| **meta-tegra** | The community Yocto layer for NVIDIA Jetson. |
| **MOK** | Machine Owner Key, added through shim with a console confirmation. |
| **PCR** | A TPM register that records measurements of what booted; keys can be sealed to its values. |
| **PREEMPT_RT** | The kernel option that makes Linux real time; mainline since 6.12. |
| **Recovery key** | A random LUKS2 key printed or scanned as a QR code, for when the TPM can't unlock. |
| **Rootfs** | The root filesystem: everything under `/`. |
| **SBAT** | A revocation scheme that lets a whole generation of signed boot components be blocked. |
| **Secure Boot** | UEFI refusing to run boot code not signed by a trusted key. |
| **Slot** | One copy of a partition in an A/B scheme. |
| **SLSA** | A framework of levels for build integrity and provenance [C-W17-020]. |
| **snapshot.debian.org** | A dated archive of Debian packages, used to pin a build in time [C-W17-029]. |
| **TPM** | Trusted Platform Module: a chip that measures boot and holds keys. |
| **tryboot** | Raspberry Pi's one-shot "boot the other partition once" flag [C-W17-011]. |
| **UKI** | Unified Kernel Image: kernel + initrd + command line in one signed EFI file [C-W17-008]. |
| **Yocto / OpenEmbedded** | A framework that builds a whole Linux image from source with board layers. |
