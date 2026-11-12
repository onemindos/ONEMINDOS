# Pinned versions and hashes (LAB-ubuntu-2604-leg)

## Host and lab VM (identical to `../rauc-k3s-gate/versions.md` unless stated)

| Item | Version / pin |
|---|---|
| Host | Apple M5 Max, macOS 27.2, 128 GB RAM; Lima 2.3.0; host QEMU 11.1.3 (not used for the guest). **Other spikes' lab VMs ran at the same time** (host load average 27–58 during runs before 08:20Z, 3–10 afterwards) |
| Lab VM | Lima `template:debian-13` (`vz`, arm64), Debian 13.7, kernel 6.12.115+deb13.1-cloud-arm64, 10 vCPU / 16 GiB / 80 GiB; only host mount: this spike's lab folder |
| VM tools | mmdebstrap 1.5.7-1+deb13u1, qemu-system-x86 / qemu-user-binfmt 1:10.0.13+ds-0+deb13u1, ovmf 2025.02-8+deb13u1, rauc 1.13-3+deb13u1 (bundle signing, as in the Debian spike), grub-common 2.12-9+deb13u2, openssl 3.5.7-1~deb13u3, Python 3.13.5, **ubuntu-keyring 2023.11.28.1-0.2** (`ubuntu-archive-keyring.gpg` sha256 `80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31`) |
| Firmware | `OVMF_CODE_4M.fd` sha256 `624e06de…e4e0`, `OVMF_VARS_4M.fd` sha256 `5d2ac383…5d1e` (same files as the Debian spike) |
| Guest machine | unchanged: `-machine q35 -accel tcg,thread=multi -cpu max -smp 4 -m 3072`, `-nic user,model=virtio-net-pci,restrict=on`, `-device i6300esb -action watchdog=reset` |

## Image inputs (build day 2026-11-11, archive.ubuntu.com + security.ubuntu.com, `resolute`, `resolute-updates`, `resolute-security`, main + universe)

| Package | U2 (archive RAUC) | U1 / U1p (RAUC from source) | Debian spike (for comparison) |
|---|---|---|---|
| OS | Ubuntu 26.04.1 LTS | Ubuntu 26.04.1 LTS | Debian 13 |
| Kernel | linux-image-7.0.0-43-generic 7.0.0-43.43 (via `linux-image-virtual`) | same | 6.12.116+deb13-amd64 |
| RAUC in image | rauc + rauc-service **1.15.1-1** (universe) | **v1.13** (`1183a39`) built with meson `-Dgpt=enabled -Dtests=false`; U1p adds `abeccdc5`, `a40986fe`, `a45cdb14` (`src/dm.c`) | 1.13-3+deb13u1 |
| systemd / udev | 259.9-0ubuntu0.1 | same | 257.13-1~deb13u1 |
| GRUB (image, used for `grub-mkstandalone` and `grub-editenv`) | grub-common 2.14-2ubuntu2.1, grub-efi-amd64-bin 2.14-2ubuntu1 | same | 2.12 |
| initramfs | initramfs-tools 0.151ubuntu1 (named explicitly; dracut not installed) | same | initramfs-tools |
| coreutils | rust-coreutils 0.10.0-1ubuntu2~26.04.1 (`coreutils` 9.5-1ubuntu2+0.0.0~ubuntu25 is the transitional package) | same | GNU coreutils |
| libc6 / openssl / socat / iptables | 2.43-2ubuntu2.4 / 3.5.5-1ubuntu3.7 / 1.8.1.1-1ubuntu0.1 / 1.8.11-2ubuntu3 | same | see Debian `image-packages.txt` |
| rootfs size (with k3s + air-gap images) | 790 MiB | 805 MiB (build leftovers: binutils, libjansson4, see §9) | 678 MiB (control rebuild, same day) |
| k3s | v1.37.2+k3s1, same four files and hashes as the Debian spike | same | same |

Full lists: `image-packages-u2.txt`, `image-packages-u1p.txt`. Build-time observations: `ubuntu-observations-{u1,u1p,u2}.txt`. Hashes of the build outputs (disk images and bundles, not committed), the k3s inputs, the three RAUC fix patches and the scripts: `SHA256SUMS`. The lab keys stayed inside the VM and were deleted with it.
