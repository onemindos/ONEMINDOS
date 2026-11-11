# Pinned versions (LAB-ubuntu-secureboot, U-SB / LT-VM-20)

Added 2026-11-11 by SYNC5 (critic N11). **The kit has not been executed** (verdict BLOCKED, README R.1), so this file lists the pins the kit declares and the lab-VM tools the environment probe recorded. It has no guest package list yet: a real run must capture `image-packages.txt` and a run-time `logs/versions.txt`, as `../secureboot-1152/` did. This file is not listed in `SHA256SUMS`.

| Item | Version / pin | From |
|---|---|---|
| Lab VM (probe only, deleted 15:56Z) | Lima `debian-13` template, arm64, `vz`; Debian 13.7; kernel 6.12.115+deb13.1-cloud-arm64 | `logs/env-probe.log` |
| VM tools (probe) | mmdebstrap 1.5.7-1+deb13u1; qemu-system-x86 1:10.0.13+ds-0+deb13u1; ovmf 2025.02-8+deb13u1; sbsigntool 0.9.4-3.2+deb13u1; efitools 1.9.2-3.5; python3-virt-firmware 24.11-2; systemd-ukify 257.13-1~deb13u1; swtpm 0.7.1-1.5; ubuntu-keyring 2023.11.28.1-0.2 | `logs/env-probe.log` |
| RAUC (to be built) | **v1.15.2 at `4fb7c798d6ae412344fb8f8d310d773046af3441`**, the same commit as `../secureboot-1152/` | `scripts/build-rauc.sh` l. 9–10 |
| RAUC amd64 build chroot (planned) | Ubuntu 26.04 `resolute` from `archive.ubuntu.com` (`resolute`, `resolute-updates` main universe) and `security.ubuntu.com` (`resolute-security`) | `scripts/build-rauc.sh` l. 33–38 |
| Guest image (planned) | Ubuntu 26.04 `resolute` amd64 via `mmdebstrap`; `linux-image-virtual` (an Ubuntu kernel); `dracut` as the initramfs generator; systemd-boot-efi, systemd-cryptsetup, cryptsetup-bin, tpm2-tools, efibootmgr. Exact versions are whatever the archive serves on the run day and must be logged then | `scripts/build.sh` l. 22, 68, 80–81 |
| Reference versions from the same archive (another spike, morning of 2026-11-11) | Ubuntu 26.04.1 LTS; kernel linux-image-7.0.0-43-generic 7.0.0-43.43; systemd 259.9-0ubuntu0.1. **Not U-SB evidence**, only what the archive served earlier that day | `../ubuntu-2604-leg/versions.md` |
| Guest machine (planned) | As `../secureboot-1152/`: q35 with SMM, TCG, secure OVMF pflash, swtpm, no network device | README §3 |
