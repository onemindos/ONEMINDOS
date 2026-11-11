# Pinned versions and hashes (LAB-rauc-k3s-gate)

## Host and lab VM

| Item | Version / pin |
|---|---|
| Host | Apple M5 Max, macOS 27.2 (Darwin), 128 GB RAM; Lima 2.3.0; host QEMU 11.1.3 (not used for the guest) |
| Lab VM | Lima `template:debian-13` (`vz`, arm64), Debian 13.7, kernel 6.12.115+deb13.1-cloud-arm64, 10 vCPU / 16 GiB / 80 GiB; only host mount: the lab work folder |
| VM tools | mmdebstrap 1.5.7-1+deb13u1, qemu-system-x86 / qemu-user-binfmt 1:10.0.13+ds-0+deb13u1, ovmf 2025.02-8+deb13u1, rauc 1.13-3+deb13u1, grub-common 2.12-9+deb13u2, squashfs-tools 1:4.6.1-1+b1, openssl 3.5.7-1~deb13u3, socat 1.8.0.3-1+deb13u1 |
| Firmware | `OVMF_CODE_4M.fd` sha256 `624e06de18b4fa535e90db7160d00d3d07d206422b89999bf1e27d920264e4e0`; `OVMF_VARS_4M.fd` sha256 `5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e` |
| Guest machine | `qemu-system-x86_64 -machine q35 -accel tcg,thread=multi -cpu max -smp 4 -m 3072`, `-nic user,model=virtio-net-pci,restrict=on`, `-device i6300esb -action watchdog=reset`, virtio disk `cache=writeback` |

## Image inputs

| Item | Version / pin |
|---|---|
| Debian | 13 "trixie" amd64 minbase from deb.debian.org + debian-security (build day 2026-11-11); full list in `image-packages.txt` |
| Guest kernel | linux-image 6.12.116+deb13-amd64 |
| RAUC in image | rauc + rauc-service 1.13-3+deb13u1 (no newer RAUC in trixie-backports on 2026-11-11) |
| k3s | v1.37.2+k3s1 (`f6973cb`), the same release as `../debian-rugix/` |

k3s artifacts, verified at build time against the release's `sha256sum-amd64.txt` (identical to the values recorded by the Rugix spike):

| File | sha256 |
|---|---|
| `k3s` (amd64) | 265b3ee6a3198ef14033c63ef46cbb32370d83795199fb6d1b01f21575eddbda |
| `k3s-airgap-images-amd64.tar.zst` | 35a5af1e69b57b8b627a4f6b1c29ea104209b661067b8c97fd40dc3f860bfcd2 |
| `k3s-images.txt` | 15b696115bae3642056cef479bf5bfe758a13eaf54b925662f0560758b7c393d |
| `sha256sum-amd64.txt` | 7e877d2b7f7382ec8beda56492ecccc439a053839c54609bf393f1280d6dc1b8 |

## Build outputs

The artifacts (14 GiB sparse disk, 7 × ~521 MB bundles) are not committed. Their hashes for the tested build are in `SHA256SUMS`. Builds are not byte-reproducible (random keys, ext4 UUIDs, timestamps).
