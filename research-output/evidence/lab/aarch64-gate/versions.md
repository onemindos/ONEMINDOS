# Pinned versions and hashes (LAB-aarch64-gate)

## Host and virtualization

| Item | Version / pin |
|---|---|
| Host | Apple M5 Max, macOS 27.2, 128 GB RAM; Lima 2.3.0; Homebrew QEMU 11.1.3 |
| Build VM | Lima `template:debian-13` (the Debian 13 arm64 cloud image), `vz`, `nestedVirtualization: true`, 10 vCPU / 16 GiB / 80 GiB; Debian 13.7, kernel 6.12.115+deb13.1-cloud-arm64; only host mount `<lab-dir>/aarch64-gate`; deleted after the spike |
| Build VM tools | mmdebstrap 1.5.7-1+deb13u1, grub-common / grub-efi-arm64-bin 2.12-9+deb13u2, qemu-system-arm 1:10.0.13+ds-0+deb13u1, qemu-efi-aarch64 2025.02-8+deb13u1 (`logs/versions.txt`) |
| Guest machine (runs 1–2, nested KVM in the build VM) | `qemu-system-aarch64` 10.0.13 `-machine virt -accel kvm -cpu host -smp 4 -m 3072`, Debian AAVMF: `AAVMF_CODE.fd` sha256 `5d3147294c56ce8cb636c57c181776a89bc7ba254274c35698dc5795758052d3`, `AAVMF_VARS.fd` sha256 `b3b855c5a80310168051164986855692d1bdb06e67619856177965cd87c6774f` |
| Guest machine (run 3, host HVF, Debian AAVMF) | host QEMU 11.1.3 `-accel hvf`, same AAVMF files copied out of the VM (same hashes): **hung in the firmware** (§8) |
| Guest machine (run 4 = the result run, and run 5) | host QEMU 11.1.3 `-machine virt -accel hvf -cpu host -smp 4 -m 3072`, Homebrew QEMU's bundled EDK2 (`edk2-stable202408`): `edk2-aarch64-code.fd` sha256 and `edk2-arm-vars.fd` sha256 in `logs/firmware-host.sha256` |
| All guest runs | `-nodefaults -display none`, `-nic user,model=virtio-net-pci,restrict=on`, `-device i6300esb -action watchdog=reset`, virtio disk `cache=writeback,throttling.bps-write=62914560` (60 MiB/s), serial on PL011 (`ttyAMA0`) |

## RAUC

| Item | Pin / hash |
|---|---|
| Source | `https://github.com/rauc/rauc.git` tag `v1.15.2`, tag object `f1ceebd68b4edcf681c23d6a49aa5322d483c4d9`, commit `4fb7c798d6ae412344fb8f8d310d773046af3441` (checked by `build-rauc.sh`); `git archive` sha256 `0332ba2a5db8a1c43de00951033f463e6b8a6290faba55669a66b2d8f608cf75` |
| Build | native arm64 in the build VM, meson 1.7.0-1, gcc 14.2.0, `-Dtests=false -Dhtmldocs=false -Dmanpages=false`, prefix `/usr`; build deps in `logs/rauc-arm64-builddeps.txt` |
| Binary | `rauc --version` = `rauc v1.15.2`; sha256 `7f076b8b8ab7882dd4522952d511354c9d23690280945965ec14ad0009639d1f`, **identical** to the arm64 binary of `../rauc-1152/` (H3); installed tree tar sha256 `35347bc6185c9ec89f535fd0b8185c9c6ac82c21bb2574c8ad3b16b05df6fcaf` |
| Runtime libraries in the image (Debian) | libglib2.0-0t64 2.84.4-3~deb13u5, libssl3t64 3.5.7-1~deb13u3, libcurl4t64 8.14.1-2+deb13u7, libfdisk1 2.41.5-0+deb13u1, dbus 1.16.2-2; Debian `rauc` / `rauc-service` **not installed** |

## Image inputs

| Item | Version / pin |
|---|---|
| Debian | 13 "trixie" **arm64** minbase from deb.debian.org + debian-security, build day 2026-11-11; 171 packages (`image-packages.txt`) |
| Guest kernel | linux-image-6.12.116+deb13-arm64 6.12.116-1 ("Linux kernel ARM64 boot executable Image, little-endian, **4K pages**"); ships `kernel/drivers/watchdog/i6300esb.ko.xz` |
| systemd | 257.13-1~deb13u1 |
| GRUB | grub-efi-arm64-bin 2.12-9+deb13u2, `grub-mkstandalone -O arm64-efi` → `/EFI/BOOT/BOOTAA64.EFI` |
| k3s | v1.37.2+k3s1 arm64: `k3s-arm64` sha256 `a779ccf1e5e2e33a62f5a29c2f1c0bbf99431e100579d4c10f0aa0742a6aa84b`, `k3s-airgap-images-arm64.tar.zst` sha256 `ca384f1a77aa83024bd82ad26fa4774971adb038e656a3b5b9af926be445a442`, both `OK` against the release's `sha256sum-arm64.txt` (saved copy: `../../sources/LAB-aarch64-gate/`), and equal to the Pi 5 kit pins in `../rauc-1152/versions.md` |
| `system.conf` | as `../rauc-1152/`, `compatible=onemind-lab-aarch64`, `bundle-formats=verity` |

## Build outputs

The 14 GiB disk image and the 8 bundles (about 490 MB each) are not committed; their hashes are in `SHA256SUMS`. Builds are not byte-reproducible (random lab keys, ext4 UUIDs, timestamps). The lab signing keys stayed inside the build VM and were deleted with it; only the public lab CA certificate is hashed.
