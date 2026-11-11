# Lab spike W2-L1: Fedora bootc + greenboot, health-gated rollback with k3s

**Owner:** W2 · **Pre-registered:** 2026-11-10, before any test was run · **Serves:** DC-01, DC-12, DC-17 (partial) · **Requirements:** F-12, F-11, R-1, R-2, AI-4, F-14

## Goal
Show, in a disposable VM, whether the Fedora bootc lineage already does what ADR-001 says OneMind must build on top of Rugix: an atomic OS update that is **committed only after k3s is healthy**, and that **rolls back automatically** when the health check fails. Also observe the behaviour on a simulated power cut while an update is being staged, and record k3s idle footprint on this base.

## Environment (no host credentials, no private networks)
- Host: Apple Silicon Mac. Lab host: Lima `vz` VM `w2lab`, Fedora Cloud 45 aarch64, 8 vCPU / 16 GiB / 80 GiB, **no host mounts, no SSH agent forwarding**. Only public registries (quay.io, get.k3s.io/GitHub releases) are contacted.
- Device under test: a **nested** QEMU/KVM aarch64 VM booted from a qcow2 disk built with `bootc-image-builder` from a OneMind test Containerfile, UEFI firmware (edk2), serial console logged to a file.
- All versions and image digests are recorded in `versions.txt` when the run happens.

## Hypotheses
- **H1** A Containerfile `FROM quay.io/fedora/fedora-bootc:45` (or `quay.io/fedora/fedora-iot:45`) that adds k3s and a greenboot `required.d` check gating on the k3s API `/readyz` boots, reaches GREEN, and k3s is Ready.
- **H2** `bootc switch` to a deliberately broken image (k3s disabled, so the required check fails) results in greenboot rebooting up to `GREENBOOT_MAX_BOOT_ATTEMPTS` (default 3) times, then GRUB falling back and greenboot running `bootc rollback`, so the device ends on the previous (good) deployment **without any human action**.
- **H3** Killing the VM (power cut) while `bootc upgrade`/`switch` is still staging leaves the device booting the old deployment.
- **H4** k3s idle RSS on this base is in line with the k3s docs' single-server profile (order of 1–2 GB total used memory on the node with only system pods).

## Pass / fail criteria (written before running)
| ID | Pass | Fail |
|---|---|---|
| H1 | `greenboot-healthcheck.service` succeeds; `kubectl get nodes` shows Ready; `bootc status` shows the image digest | Image does not boot, or greenboot is RED with k3s healthy |
| H2 | After `bootc switch` to the bad image and one reboot, the system ends **booted on the good digest** within **15 minutes** and with **0 manual commands** after the first reboot; journal shows greenboot rollback | Device stays on the bad image, loops forever, or needs a console |
| H3 | After kill -9 of QEMU during staging, next boot = good digest, GREEN | Unbootable or boots a half-written deployment |
| H4 | Measurement recorded (pass = recorded with method) | Not measured |

## What this spike cannot show
- Raspberry Pi 5, Jetson or real eMMC/SD behaviour (QEMU is not a Pi; the Pi bootc boot bug is a hardware/firmware-layout issue). Those are founder-hardware tests in `22-HARDWARE-LAB-TEST-PLAN.md`.
- Real-time latency (QEMU timing is meaningless for that).
- Debian + Rugix behaviour: that is W3's spike. This spike gives the bootc side of the comparison.

## Result
See `RESULT.md` (written after the run) and raw logs in this folder.
