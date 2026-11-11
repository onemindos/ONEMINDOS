# Pinned versions and hashes (W18 Mac toolchain spike)

Compiled 2026-11-11 by the HYG agent from this folder's README, `spike.log` and `start.log`, and the `SHA256SUMS-lab` the spike wrote in `<lab-dir>/w18-mac-toolchain/` at 2026-11-10T20:20-05:00 (after the run). Nothing was re-run.

| Item | Version / pin | Source |
|---|---|---|
| Host | Apple M5 Max, macOS 27.2; Lima 2.3.0 (`vz`, `nestedVirtualization=true`) | README |
| Lab VM | Lima `template:debian-13` (Debian 13 cloud image 20261103-2651), arm64, 10 vCPU / 16 GiB, no host mounts | README, `start.log` |
| Guest kernel | 6.12.115+deb13.1-cloud-arm64 (Debian 6.12.115-2, 2026-11-01) | `spike.log` line 2 |
| Kernel built | Linux 6.18.62 from kernel.org, `linux-6.18.62.tar.xz` sha256 `490a7aedf1b355c565d3a6c05333ccccb5da82064eca46b590448a7099d7d651` (matched kernel.org `sha256sums.asc`) | `spike.log` |
| Toolchain | Debian 13 `build-essential`, `gcc-x86-64-linux-gnu`, `qemu-user-static`, `binfmt-support` (package versions were not logged) | `spike.log` |
| Outputs | arm64 `Image` 41,355,776 bytes; x86_64 `bzImage` 14,377,984 bytes (not committed; not hashed at run time) | `artifacts.txt` |

## Run-time hashes vs the committed copies

| File | sha256 at run time | Now | Same? |
|---|---|---|---|
| README.md | `b3a07a02adcb77a45c16ba5db27c2f5489ade9f8236b1114e1d09f0492ca2785` | same | yes, but this README holds both the criteria and the results, so its hash proves nothing about pre-registration |
| run-spike.sh | `20835023…43f9` | same | yes |
| spike.log, start.log, artifacts.txt | listed in `SHA256SUMS-lab` | differ | masked (guest home path) |

Gaps: toolchain package versions and output-image hashes were not recorded; a re-run should log `dpkg -l` and `sha256sum` of `Image`/`bzImage`. `SHA256SUMS` here hashes the committed files as they are now.
