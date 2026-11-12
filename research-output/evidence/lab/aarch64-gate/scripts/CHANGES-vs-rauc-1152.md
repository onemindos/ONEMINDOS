# What changed from `../../rauc-1152/scripts/`

The full unified diff is `../scripts-vs-rauc-1152.diff`. In words:

## Unchanged (byte-identical)

`guest/onemind-health-gate`, `guest/onemind-k3s-check`, `guest/rauc-pre-install`, `guest/bad-hang-init`, `guest/k3s.service`, `guest/onemind-health-gate.service`, `guest/onemind-api.service`, `guest/onemind-api-respond`, `guest/manifests/*`. The gate logic, the trial marker, the 3-try GRUB slot logic and the test sequence are the same as in the x86 suite.

## Architecture inputs (planned in README §1 and §4)

| File | Change |
|---|---|
| `guest/grub.cfg.in` | `console=ttyS0` → `console=ttyAMA0` (the `virt` machine's PL011 serial port) |
| `build-rauc.sh` | Native arm64 build only; the amd64 qemu-user chroot and T12 are dropped (T12 already ran on arm64 in rauc-1152). Adds `meson install --destdir` of the arm64 build for the image |
| `build.sh` | `mmdebstrap --arch=arm64`, `linux-image-arm64`, `grub-efi-arm64-bin`; k3s `k3s-arm64` + `k3s-airgap-images-arm64.tar.zst` checked against `sha256sum-arm64.txt`; `grub-mkstandalone -O arm64-efi` → `BOOTAA64.EFI`; `compatible=onemind-lab-aarch64`; serial autologin on `ttyAMA0`; new T0 checks: `file` must say `ARM aarch64` for `rauc`, `k3s`, `grub-editenv`, and the `i6300esb` module must exist |
| `run-tests.py` | `qemu-system-aarch64 -machine virt -cpu host` with `LAB_ACCEL` (`kvm` default, `hvf` for the host fallback) and firmware paths from `LAB_CODE_FD` / `LAB_VARS_FD`; 60 MiB/s write throttle on the guest disk; T8 kill delay 2 s instead of 6 s; T1 also requires `uname -m` = `aarch64` |
| `debug-boot.py` | AAVMF paths; QEMU is killed in a `finally` block |
| `trim-logs.sh` | Also keeps the `ARCH=` line |

## Driver fixes made during the spike (README §8, deviations)

| Change | Why |
|---|---|
| T1 strips bracketed-paste escape fragments (`[?2004l`) before matching `rauc v1.15.2` | Run 1: the fragment landed at the start of the version line, so the line-anchored match failed although the guest printed `rauc v1.15.2` (same class of bug as rauc-1152 deviation 4) |
| `LAB_WRITE_BPS` environment override (0 = off) | Used only for one diagnostic boot (debug 5); every test run used the frozen 60 MiB/s |
| On exit the driver kills the QEMU processes it started (tracked list, never by name) | Run 1: stopping the driver left its QEMU running, which kept writing the disk and loading the CPU |
