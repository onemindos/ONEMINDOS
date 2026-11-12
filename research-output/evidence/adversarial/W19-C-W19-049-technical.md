# Refuter (technical): W19 DC-16 ADR-001 EFFECT [C-W19-049]

**Refuter:** independent, technical lens. **Date:** 2026-11-11. Read: the conclusion (§1, "ADR-001 effect"), claim rows C-W19-001…009, C-LAB-debian-rugix-012, C-TD-umbrelos-053 and C-STEEL-KRU-013.

## Target
The flip condition is not met, and ADR-001 D1/D3 are confirmed. Reserve from release 1: (1) SYSEXT_LEVEL; (2) `/var/lib/extensions` and `/var/lib/confexts` on the data partition, merged before k3s; (3) a OneMind module-signing key (CONFIG_MODULE_SIG); (4) dm-verity signing of extension images.

## Strongest counter-argument
Items (3) and (4) quietly assume **OneMind builds and signs its own kernel**. That is a much bigger ADR decision than "an addition".
- Debian's signed kernel trusts Debian's keys. A OneMind module key either goes into a OneMind-built kernel's built-in keyring (which means a OneMind kernel, plus a shim or db-key chain for Secure Boot) or into MOK, which "may only be confirmed directly from the console at boot time" (C-STEEL-KRU-013). Neither is cheap.
- For (4), the Flatcar reference shows the gap is real today: the sysext verity key is not in the kernel's built-in trusted keys, so the kernel logs `failed: Required key not available` and systemd falls back to userspace verification. Building with `CONFIG_DM_VERITY_VERIFY_ROOTHASH_SIG=y` only changed the error text (flatcar/Flatcar#2187, open, 2026-10-29). Signature *enforcement* in the kernel needs the key in a kernel keyring. That again means a OneMind kernel, or reliance on systemd's userspace check, which is weaker under lockdown.
- The reservation list also lacks a **confext write-routing directory** (`/var/lib/extensions.mutable/etc`, or k3s state moved off `/etc`). Without it, merging any confext makes `/etc` read-only (saved man page L155-L157; systemd#31392). The data-partition layout must reserve it from release 1, just like items (1) and (2).
- It also lacks a boot-partition or DT-overlay slot for HAT-class hardware (see W19-C-W19-047-technical.md).

## NEW sources
- flatcar/Flatcar#2187: https://github.com/flatcar/Flatcar/issues/2187 (Alpha 4722.0.0 / Beta 4694.1.0 / nightly 4866.0.0, open).
- systemd/systemd#31392: https://github.com/systemd/systemd/issues/31392
- systemd/systemd#36378: https://github.com/systemd/systemd/issues/36378
- k3s kubeconfig in `/etc/rancher/k3s/`: https://docs.k3s.io/cluster-access

## Verdict: **WEAKENED**
The direction is right: D1/D3 survive and the flip condition is not met for userspace plugins. But "confirmed with an addition" understates what items 3 and 4 commit to: a OneMind-built kernel and key chain, or MOK enrollment. That should be stated as its own ADR decision, cross-referenced to the kernel and Secure Boot decisions. Add a fifth reservation: confext write routing on the data partition.

## What would flip it
- **Back to UPHELD:** T-W19-01 on Debian 13 + RAUC + Secure Boot shows that (a) the stock Debian signed kernel can enforce OneMind-signed sysext verity via the secondary or platform keyring without rebuilding the kernel, or that systemd's userspace verification is accepted as sufficient; (b) a OneMind-signed module loads under lockdown without a per-device console MOK step; (c) k3s runs with a confext merged in mutable mode.
- **To REFUTED:** Secure Boot + RAUC cannot verify sysext verity with the OneMind key at all (the author's own flip condition). Or the only workable path needs per-device MOK enrollment at a console, which is incompatible with fleet provisioning.
