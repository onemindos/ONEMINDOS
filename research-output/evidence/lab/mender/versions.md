# Pinned versions and hashes (LAB-mender)

Everything that is not the update engine is pinned to the same versions as `../rauc-k3s-gate/versions.md`.

## Host and lab VM

| Item | Version / pin |
|---|---|
| Host | Apple M5 Max, macOS 27.2 (Darwin), 128 GB RAM; Lima 2.3.0; host QEMU 11.1.3 (not used for the guest) |
| Lab VM | Lima `template:debian-13` (`vz`, arm64), Debian 13.7, kernel 6.12.115+deb13.1-cloud-arm64, 8 vCPU / 12 GiB / 80 GiB; only host mount: the lab work folder |
| VM tools | mmdebstrap 1.5.7-1+deb13u1, qemu-system-x86 / qemu-user-binfmt 1:10.0.13+ds-0+deb13u1, ovmf 2025.02-8+deb13u1, grub-common 2.12-9+deb13u2, gdisk 1.0.10-2+b1, openssl 3.5.7-1~deb13u3, socat 1.8.0.3-1+deb13u1, **mender-artifact 4.4.2-1+debian+trixie** (Mender `workstation-tools` repository) |
| Firmware | `OVMF_CODE_4M.fd` sha256 `624e06de18b4fa535e90db7160d00d3d07d206422b89999bf1e27d920264e4e0`; `OVMF_VARS_4M.fd` sha256 `5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e` (identical to the RAUC spike) |
| Guest machine | `qemu-system-x86_64 -machine q35 -accel tcg,thread=multi -cpu max -smp 4 -m 3072`, `-nic user,model=virtio-net-pci,restrict=on`, `-device i6300esb -action watchdog=reset`, virtio disk `cache=writeback` (identical) |

## Image inputs

| Item | Version / pin |
|---|---|
| Debian | 13 "trixie" amd64 minbase from deb.debian.org + debian-security (build day 2026-11-11); full list in `image-packages.txt` |
| Guest kernel | linux-image 6.12.116+deb13-amd64 (identical) |
| Mender client | **mender-update 5.2.0-1+debian+trixie**, mender-auth 5.2.0-1+debian+trixie (dependency; its daemon masked), mender-flash 1.1.0-1+debian+trixie, from `https://downloads.mender.io/repos/device-components` suite `debian/trixie/stable` (Release file dated 2026-10-14). APT key fetched from `https://downloads.mender.io/repos/debian/gpg`, fingerprint `E6C857345575F9218396566224072B80A1B29B00` checked at build time; key file sha256 in `SHA256SUMS` |
| Mender client source (for code citations) | `mendersoftware/mender` tag 5.2.0 = `0f4eb08e9d7114e5159de16656962fa2478cb580` (released 2026-10-23) |
| GRUB integration | `mendersoftware/grub-mender-grubenv` @ `d7c3ec217e281727f56c3651799f805637cb2cda` (2026-01-22), the commit pinned by mender-convert 5.3.0; boot logic unmodified; lab additions `07_onemind_lab_echo_grub.cfg` (echo only) and `11_bootargs_grub.cfg` (kernel arguments, as mender-convert generates) |
| mender-convert (for layout and pins only; not run) | `mendersoftware/mender-convert` tag 5.3.0 = `85e8c506cd59dc4a8e66ad07fbe28a3c33488c46` (2026-10-01) |
| GRUB EFI | `grub-mkstandalone` from Debian grub-efi-amd64-bin 2.12-9+deb13u2 (same as RAUC) |
| k3s | v1.37.2+k3s1, same files and hashes as the RAUC and Rugix spikes |

k3s artifacts, verified at build time against the release's `sha256sum-amd64.txt`:

| File | sha256 |
|---|---|
| `k3s` (amd64) | 265b3ee6a3198ef14033c63ef46cbb32370d83795199fb6d1b01f21575eddbda |
| `k3s-airgap-images-amd64.tar.zst` | 35a5af1e69b57b8b627a4f6b1c29ea104209b661067b8c97fd40dc3f860bfcd2 |
| `k3s-images.txt` | 15b696115bae3642056cef479bf5bfe758a13eaf54b925662f0560758b7c393d |
| `sha256sum-amd64.txt` | 7e877d2b7f7382ec8beda56492ecccc439a053839c54609bf393f1280d6dc1b8 |

## Build outputs

Not committed: the 14 GiB sparse disk and 7 Mender artifacts (~480 MiB each, `zstd_fast`). Hashes of the tested build (`build-run3`) are in `SHA256SUMS`. Builds are not byte-reproducible (random keys, ext4 UUIDs, timestamps). The lab signing keys (ECDSA P-256) stayed inside the VM and were deleted with it; only the public verification key is hashed.
