# Refuter (technical): W19 DC-16 ANSWER [C-W19-047]

**Refuter:** independent, technical lens (RESEARCH-MISSION.md §2 rule 7). **Date:** 2026-11-11. Read: the conclusion in `29-PLATFORM-ECOSYSTEM-MARKETPLACE.md` §1 and its cited claim rows only; author reasoning and other adversarial files not read first.

## Target
"No OneMind plugin type requires forking the OS, provided nine extension points (E1–E9) ship in release 1."

## Strongest counter-argument
"No fork" holds only for host changes that live in `/usr`, `/opt`, `/etc` or k3s. Three plugin classes change things **outside** those trees, and E1–E9 has no socket for them:

1. **Boot-stage hardware enablement.** A CAN, GPS or camera HAT on Raspberry Pi or Rockchip-class boards needs a device-tree overlay (`dtoverlay=` in the boot partition, or a DT applied by the bootloader). Under RAUC that lives in the slot or boot partition, not in `/usr`. sysext cannot add it. The saved man page also says initrd extensions have limits: "resources that are used in the earliest boot stages of the initrd ... cannot be updated" (`evidence/sources/W19/systemd-sysext.txt` L99-L102). So a driver for root storage or early networking cannot be a sysext.
2. **Vendor BSP kernels.** On Jetson the kernel is NVIDIA's L4T kernel. NVIDIA has no step-by-step guide for signing out-of-tree modules on JetPack, and users report signing-build failures and UEFI rejecting signed kernels on JetPack 6.2.2 (NVIDIA forum threads, NEW sources below). E4 "per OneMind kernel" becomes "per board-vendor kernel". That is a per-board image line, which is a fork in practice even if it is not called one.
3. **E3 has an unstated precondition.** By default a merged confext makes the **whole** `/etc` read-only, not just the confext files (systemd #31392, NEW; same text in the saved man page L155-L157). k3s keeps its admin kubeconfig at `/etc/rancher/k3s/k3s.yaml` and rewrites its certificates "every time it starts" (docs.k3s.io/cluster-access, NEW). So E3 needs `--mutable=` write routing to `/var/lib/extensions.mutable/etc`, or k3s state moved out of `/etc`. Neither is in the E1–E9 list, and Lab W19-1 did not run k3s with a confext merged.

## NEW sources (searched for failure, regressions, abandonment)
- systemd/systemd#31392, "mutable /etc/ layers in confext" (opened 2024-02-19, closed 2024-02-23): "A single `confext` merged into the system will render the whole `/etc` OS-tree Read-Only." Poettering: confext "is not really designed with that usecase in mind". Workaround: `--mutable=auto` plus a symlink at `/var/lib/extensions.mutable/etc`. https://github.com/systemd/systemd/issues/31392
- systemd/systemd#36378 (systemd 256.5, 2025-02-13): with a read-only root, a confext merge **masked `/etc/machine-id`**, leaving journald with "No journal files were found". Fixed by PR #34381. This shows the confext + read-only root combination has had regressions. https://github.com/systemd/systemd/issues/36378
- k3s docs: kubeconfig "stored at `/etc/rancher/k3s/k3s.yaml`"; certificates in it are updated "every time it starts". https://docs.k3s.io/cluster-access
- NVIDIA forum (JetPack 5.1.3): no step-by-step instructions for signing out-of-tree modules. https://forums.developer.nvidia.com/t/unable-to-build-the-jetpack-5-1-3-kernel-for-agx-xavierafter-enabling-the-kernel-signature-related-modules/351955 ; JetPack 6.2.2: the kernel signature was rejected by UEFI. https://forums.developer.nvidia.com/t/jetpack-6-2-2-r36-5-soft-secure-boot-kernel-signature-rejected-by-uefi-both-sbsign-and-l4t-uefi-sign-image-sh/373804 (search-result summaries; the pages were not opened in full. These are supporting sources, not primary.)

## Verdict: **WEAKENED**
E1–E9 is a sound set for userspace, container and bus plugins, and the lab shows the sysext/confext core works. But the claim "no plugin type requires a fork" is too broad: boot-stage hardware (device-tree overlays, initrd drivers) and vendor-kernel boards are not covered. E3 also needs confext mutable mode or k3s state moved out of `/etc`. Suggested restatement: "no **userspace or post-boot driver** plugin needs a fork; boot-stage hardware enablement is release-pipeline-only (as E4), and vendor-kernel boards are separate image lines."

## What would flip it
- **Back to UPHELD:** a T-W19-01 run on a RAUC image with k3s running, a confext merged (mutable mode configured) and k3s restarting cleanly; **plus** either a tenth socket "E10 boot-stage overlay" (signed DT overlays carried in the RAUC bundle or the boot partition, chosen by profile), or an explicit statement that HAT/DT enablement ships only through the OneMind release pipeline.
- **To REFUTED:** a day-one device class (P-8 profiles) whose DT overlay or early-boot driver cannot ship through the release pipeline. Or Jetson in Tier A with an L4T kernel that OneMind cannot rebuild and sign.
