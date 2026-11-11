# Pinned versions (LAB-secureboot-rauc)

Added 2026-11-11 by SYNC5 (critic N11). Nothing was re-run. Every value is copied from this spike's own files: `logs/versions.txt` (captured at run time), `image-packages.txt` and `logs/driver-run2.log`. This file is not listed in `SHA256SUMS`.

| Item | Version / pin | From |
|---|---|---|
| Host | macOS 27.2, arm64; Lima (`limactl`) 2.3.0; host QEMU 11.1.3 (not used for the guest) | `logs/versions.txt` |
| Lab VM | Lima `debian-13` template, aarch64, `vz`; Debian 13.7; kernel 6.12.115+deb13.1-cloud-arm64 | `logs/versions.txt` |
| VM tools | mmdebstrap 1.5.7-1+deb13u1; qemu-system-x86 and qemu-user-binfmt 1:10.0.13+ds-0+deb13u1; ovmf 2025.02-8+deb13u1; sbsigntool 0.9.4-3.2+deb13u1; efitools 1.9.2-3.5; python3-virt-firmware 24.11-2; python3-pefile 2024.8.26-2.1; systemd and systemd-ukify 257.13-1~deb13u1; swtpm and swtpm-tools 0.7.1-1.5; tpm2-tools 5.7-1+b1; openssl 3.5.7-1~deb13u3; python3 3.13.5-1; gdisk 1.0.10-2+b1; dosfstools 4.2-1.2; e2fsprogs 1.47.2-3+b12; mtools 4.0.48-1; squashfs-tools 1:4.6.1-1+b1 | `logs/versions.txt` |
| RAUC (bundle signing, in the VM) | rauc 1.13-3+deb13u1 | `logs/versions.txt` |
| Firmware | `OVMF_CODE_4M.secboot.fd` sha256 `1a46295574430cfb7f825ee3e4dc64b052acbef08e310377ed7c64cb757a9dc1`; `OVMF_VARS_4M.fd` sha256 `5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e` | `logs/versions.txt` |
| Guest image (Debian 13 amd64) | linux-image-amd64 6.12.116-1; systemd, systemd-boot-efi and systemd-cryptsetup 257.13-1~deb13u1; rauc and rauc-service 1.13-3+deb13u1; cryptsetup-bin 2:2.7.5-2; tpm2-tools 5.7-1; efibootmgr 18-2; initramfs-tools 0.148.4. Full list in `image-packages.txt` | `logs/versions.txt`, `image-packages.txt` |
| Guest machine | `qemu-system-x86_64 -machine q35,smm=on -accel tcg,thread=multi -cpu max -smp 4 -m 2048 -nic none`, secure pflash (`OVMF_CODE_4M.secboot.fd`), swtpm | `logs/driver-run2.log` |
| Upstream sources read (not built) | rauc/rauc `4fb7c798d6ae412344fb8f8d310d773046af3441` (v1.15.2 tree); tianocore/edk2 `fbe0805b2091393406952e84724188f8c1941837` (edk2-stable202502) | `logs/versions.txt` |
