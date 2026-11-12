# Pinned versions · LAB-minimal-image-dc20 (run 2026-11-11, UTC)

| Item | Version / pin | How verified |
|---|---|---|
| Host | Apple M5 Max, 128 GB, macOS; Lima 2.3.0 | `limactl --version` |
| Build VM | Lima `vz`, Debian 13.7 arm64 cloud image 20261103-2651, kernel 6.12.115+deb13.1-cloud-arm64, 12 vCPU, 24 GiB, 100 GiB, no host mounts | `/etc/debian_version`, `uname -r` |
| Leg A tool | mkosi 25.3 (Debian package 25.3-7), systemd/systemd-repart 257.13-1~deb13u1, qemu-user-binfmt 1:10.0.13+ds-0+deb13u1 | `mkosi --version`, `dpkg-query` |
| Leg A content | Debian 13.7 (trixie) amd64 from deb.debian.org on 2026-11-11; kernel `linux-image-6.12.116+deb13-amd64` 6.12.116-1; 139 binary / 85 source packages | image `/etc/debian_version`; `sbom/legA-debian-deb-packages.txt` |
| Leg B tool | Buildroot **2025.02.19** (LTS), git `4f924fd52841608d68ac3dcb83fccee8b8c90316`; internal glibc toolchain (gcc 13.4.0, binutils 2.43.1, glibc 2.41-167-gf247c0a2) | `git rev-parse HEAD` |
| Leg B content | Linux 6.12.112 (variant: 6.12.117), systemd 256.17, busybox 1.37.0, OpenSSH 9.9p2, OpenSSL 3.5.9, iptables 1.8.11 (nft), iproute2 6.14.0, util-linux 2.40.4, e2fsprogs 1.47.2, GRUB 2.12 (x86_64-efi); 27 target packages | `sbom/legB-buildroot-cdx-components.csv`, `sbom/legB-legal-manifest.csv` |
| Shared | k3s **v1.37.2+k3s1** amd64 (sha256 checked against the release `sha256sum-amd64.txt`) | `SHA256SUMS` |
| Scanners | syft **1.57.1**, grype **0.121.3** (arm64 tarballs, checked against release `checksums.txt`); grype DB schema v6.1.10, **built 2026-11-11T06:21:32Z**, auto-update off for every scan | `results/grype-descriptor.json` |
| Test VM | QEMU 10.0.13 (Debian package, inside the Lima VM) `qemu-system-x86_64 -machine q35 -accel tcg,thread=multi -cpu max -smp 4 -m 4096`, OVMF 2025.02-8+deb13u1 (`OVMF_CODE_4M.fd`), user-mode NIC | `scripts/boot-test.sh` |

Note: the host has QEMU 11.1 from Homebrew; this spike used the Debian QEMU inside the disposable VM so that no guest ran on the host. Neither leg set `SOURCE_DATE_EPOCH`/reproducible-build options, so output hashes in `SHA256SUMS` identify this run's artefacts but will not reproduce bit-for-bit.
