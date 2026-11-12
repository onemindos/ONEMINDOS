# Pinned versions (LAB-rauc)

Added 2026-11-11 by SYNC5 (critic N11). Nothing was re-run. Every value is copied from this spike's own files: `logs/versions.txt` (captured at run time), `image-packages.txt`, `scripts/build.sh` and `logs/driver-run4.log`. This file is not listed in `SHA256SUMS`.

| Item | Version / pin | From |
|---|---|---|
| Host | macOS 27.2, arm64; Lima (`limactl`) 2.3.0; host QEMU 11.1.3 (not used for the guest) | `logs/versions.txt` |
| Lab VM | Lima `debian-13` template, aarch64, `vz`; Debian 13.7; kernel 6.12.115+deb13.1-cloud-arm64 | `logs/versions.txt` |
| VM tools | mmdebstrap 1.5.7-1+deb13u1; qemu-system-x86 and qemu-user-binfmt 1:10.0.13+ds-0+deb13u1; ovmf 2025.02-8+deb13u1; grub-common 2.12-9+deb13u2; openssl 3.5.7-1~deb13u3; python3 3.13.5-1; gdisk 1.0.10-2+b1; dosfstools 4.2-1.2; e2fsprogs 1.47.2-3+b12; mtools 4.0.48-1; squashfs-tools 1:4.6.1-1+b1 | `logs/versions.txt` |
| RAUC (bundle signing, in the VM) | rauc 1.13-3+deb13u1 (Debian archive); `rauc-service` not installed in the VM | `logs/versions.txt` |
| Firmware | `OVMF_CODE_4M.fd` sha256 `624e06de18b4fa535e90db7160d00d3d07d206422b89999bf1e27d920264e4e0`; `OVMF_VARS_4M.fd` sha256 `5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e` | `logs/versions.txt` |
| Guest image (Debian 13 amd64) | linux-image-amd64 6.12.116-1 (6.12.116+deb13-amd64); systemd 257.13-1~deb13u1; rauc and rauc-service 1.13-3+deb13u1; grub-efi-amd64-bin 2.12-9+deb13u2; initramfs-tools 0.148.4. Full list in `image-packages.txt` | `image-packages.txt` |
| Guest machine | `qemu-system-x86_64 -machine q35 -accel tcg,thread=multi -cpu max -smp 4 -m 2048 -nic none`, OVMF pflash, virtio disk `cache=writeback` | `logs/driver-run4.log` |
| Core platform in the guest | A heartbeat service standing in for k3s (no k3s binary) | `scripts/build.sh` |
| Upstream sources read (not built) | rauc/rauc `2d17b27041db7fa8b13a61c5e168f49310a06566` (latest release then v1.15.2, 2026-03-27); home-assistant/operating-system `ab7d0f1a0174760353780a21be2befecbc80a672`; home-assistant/supervisor `040f14cd8aa2902401d30aaeb0cb71215854c78c` | `logs/versions.txt` |
