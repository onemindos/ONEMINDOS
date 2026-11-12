# Pinned versions and hashes (LAB-rauc-1152)

## Host and lab VM

| Item | Version / pin |
|---|---|
| Host | Apple M5 Max, macOS 27.2 (Darwin), 128 GB RAM; Lima 2.3; host QEMU not used for the guest |
| Lab VM | Lima `template:debian-13` (`vz`, arm64), Debian 13.7, kernel 6.12.115+deb13.1-cloud-arm64, 12 vCPU / 24 GiB / 100 GiB; only host mount the lab work folder; deleted after the spike |
| VM tools | mmdebstrap 1.5.7-1+deb13u1, qemu-system-x86 / qemu-user-binfmt 1:10.0.13+ds-0+deb13u1, ovmf 2025.02-8+deb13u1, grub-common 2.12-9+deb13u2, squashfs-tools 1:4.6.1-1+b1, openssl 3.5.7-1~deb13u3, meson 1.7.0-1, ninja-build 1.12.1-1+b1, gcc 4:14.2.0-1, git 1:2.47.3-0+deb13u1 (`logs/versions.txt`) |
| Debian RAUC in the VM (T12 control and D1) | rauc 1.13-3+deb13u1 (arm64), the only candidate with trixie, trixie-updates, trixie-backports and trixie-security enabled |
| Firmware | `OVMF_CODE_4M.fd` sha256 `624e06de18b4fa535e90db7160d00d3d07d206422b89999bf1e27d920264e4e0`; `OVMF_VARS_4M.fd` sha256 `5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e` (same as `../rauc-k3s-gate/`) |
| Guest machine | Same as `../rauc-k3s-gate/versions.md`: q35, TCG, `-cpu max -smp 4 -m 3072`, user net `restrict=on`, `i6300esb` + `-action watchdog=reset` |

## RAUC builds

| Item | Pin / hash |
|---|---|
| Source | `https://github.com/rauc/rauc.git` tag `v1.15.2`, tag object `f1ceebd68b4edcf681c23d6a49aa5322d483c4d9`, commit `4fb7c798d6ae412344fb8f8d310d773046af3441` (checked by `build-rauc.sh` before building). `git archive` of the commit: sha256 `0332ba2a5db8a1c43de00951033f463e6b8a6290faba55669a66b2d8f608cf75` |
| Meson options | `--prefix=/usr --buildtype=release -Dtests=false -Dhtmldocs=false -Dmanpages=false` and explicit systemd/D-Bus directories (see `scripts/build-rauc.sh`); all other options default (service, network, streaming, json, gpt=auto) |
| arm64 build (VM native; creates and inspects bundles) | `rauc --version` = `rauc v1.15.2`; binary sha256 `7f076b8b8ab7882dd4522952d511354c9d23690280945965ec14ad0009639d1f`. Rebuilding with `build-rauc-pi.sh` in the same VM gave the same sha256 |
| amd64 build (amd64 `mmdebstrap --variant=buildd` chroot, trixie main, via qemu-user) | `rauc --version` = `rauc 1.15.2` (no `v`: git is not in that chroot, so the version comes from meson); installed tree tar sha256 `0c241e9c9e066d239c4d751eb1c5d76351d1cc494b839e56c3496635709145c3`; files: `/usr/bin/rauc`, `rauc.service`, `rauc-service.sh`, the D-Bus service, policy and interface files, `rauc.catalog` |
| amd64 build deps | libglib2.0-dev 2.84.4-3~deb13u5, libssl-dev 3.5.7-1~deb13u2, libcurl4-openssl-dev 8.14.1-2+deb13u5, libjson-glib-dev 1.10.6+ds-2, libdbus-1-dev 1.16.2-2, libfdisk-dev 2.41.5-0+deb13u1, libnl-genl-3-dev 3.7.0-2, meson 1.7.0-1, ninja-build 1.12.1-1 |
| T12 unfixed control | tag `v1.15.1`, commit `fac72b8347eed46f300d3a8a06e847ce1aa9d677`, arm64 native, `-Dtests=false` |
| Pi desk pre-flight only | the same commit built with `-Dservice=false` (CLI install path for a chroot); never put in an image |

## Image inputs (x86 suite)

| Item | Version / pin |
|---|---|
| Debian | 13 "trixie" amd64 minbase from deb.debian.org + debian-security, build day 2026-11-11; 171 packages, list in `image-packages.txt` |
| Guest kernel | linux-image 6.12.116+deb13-amd64 (6.12.116-1) |
| RAUC in image | upstream 1.15.2 above; **Debian `rauc` / `rauc-service` not installed** (build aborts otherwise). Runtime libraries from Debian: libglib2.0-0t64 2.84.4-3~deb13u5, libssl3t64 3.5.7-1~deb13u3, libcurl4t64 8.14.1-2+deb13u7, libjson-glib-1.0-0 1.10.6+ds-2, libfdisk1 2.41.5-0+deb13u1, libnl-genl-3-200 3.7.0-2, dbus 1.16.2-2 |
| `system.conf` | as `../rauc-k3s-gate/` plus `bundle-formats=verity` |
| k3s | v1.37.2+k3s1; same artifacts and sha256 as `../rauc-k3s-gate/versions.md` (re-verified against `sha256sum-amd64.txt` at build time) |

## Pi 5 kit inputs

| Item | Pin / hash |
|---|---|
| Raspberry Pi OS Lite (64-bit) | 2026-10-06, trixie; `2026-10-06-raspios-trixie-arm64-lite.img.xz` sha256 `483db18a48da399b5b7022ffae9a07bc6d99daab30e593aedac09b69ff422843` (matches the published `.sha256`); extracted `.img` sha256 `b8a393dc1c3701450b5fffbfe74368a98fb6eab7415ce456cc0cead886ea8780` (matches `extract_sha256` in Imager's OS list) |
| k3s arm64 | v1.37.2+k3s1 `k3s-arm64` sha256 `a779ccf1e5e2e33a62f5a29c2f1c0bbf99431e100579d4c10f0aa0742a6aa84b`; `k3s-airgap-images-arm64.tar.zst` sha256 `ca384f1a77aa83024bd82ad26fa4774971adb038e656a3b5b9af926be445a442` (from the release's `sha256sum-arm64.txt`; pinned in `prepare-disk.sh`) |
| RAUC | built on the Pi from the same tag and commit by `build-rauc-pi.sh` |

## Build outputs

The 14 GiB disk image and the 8 bundles (about 520 MB each) are not committed; their hashes are in `SHA256SUMS`. Builds are not byte-reproducible (random keys, ext4 UUIDs, timestamps).
