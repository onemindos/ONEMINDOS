# Sources · LIC (licence matrix, outreach drafts)

**Accessed:** 2026-11-11 (UTC) · **Owner:** LIC · **Claims:** [`../claims/LIC.csv`](../claims/LIC.csv) (C-LIC-001…055) · **Archive:** [`LIC/`](LIC/) holds saved text with a `SHA256SUMS` file and `ORIGINAL-HASHES.txt`. Email addresses in saved texts are masked as `<email-masked>`, so each file's saved hash differs from the original; both hashes are recorded. Wayback save requests are denied in this environment and no existing captures were used.

## 1. NVIDIA primary texts (load-bearing; archived)

| # | Source | How obtained | Original sha256 | Archive | Claims |
|---|---|---|---|---|---|
| 1 | `nvidia-l4t-core_39.2.1-20260806224157_arm64.deb` from NVIDIA's public Jetson apt feed (`repo.download.nvidia.com/jetson/som/pool/main/n/nvidia-l4t-core/`) | `curl`, unpacked with bsdtar into an isolated scratch folder; no package code was run | deb `277a6fb25f2c06cc2dee6d352bef3abb15929739f396fea1cee70d1dea83008b` | — | C-LIC-001, 006, 048 |
| 2 | `Tegra_Software_License_Agreement-Tegra-Linux.txt` inside (1) ("NVIDIA Driver License Agreement", v. 2025-02-25). md5 `376d20bd5275442226fcdf54e4844ddf`, identical to meta-tegra's `LIC_FILES_CHKSUM` | gunzip of `/usr/share/doc/nvidia-l4t-core/…txt.gz` | `828f46b4982622a4558a96f21f531dc5cf36d1d942255cd886be56bad3797aa4` | [`LIC/01-nvidia-tegra-sla-r39.2.1.txt`](LIC/01-nvidia-tegra-sla-r39.2.1.txt) | C-LIC-001…005, 048 |
| 3 | `/usr/share/doc/nvidia-l4t-core/copyright` inside (1) | as above | `1b648a06caf4c771b732a8ef2d56c6de94c1852d8eb85bb76e849a6b18065830` | [`LIC/02-…`](LIC/02-nvidia-l4t-core-39.2.1-copyright.txt) | C-LIC-006 |
| 4 | `cuda-cudart-13-2_13.2.86-1_arm64.deb`, `/usr/share/doc/cuda-cudart-13-2/copyright` (CUDA EULA, last updated 2026-01-26) | as above | deb `550a1c3c915637b5c0d6538b9eba87471742c4be854438ab8a050caabdea8001`; text `088381bc2d891e719a2a9398645b00bb45f3b24231473a8283ac7e3e66b8a028` | [`LIC/03-…`](LIC/03-cuda-cudart-13.2.86-copyright-eula.txt) | C-LIC-007…010 |
| 5 | https://docs.nvidia.com/cuda/eula/index.html (web copy, page "last updated on Nov 02, 2026", EULA dated January 26, 2026) | HTML to text | see `ORIGINAL-HASHES.txt` | [`LIC/04-…`](LIC/04-docs-nvidia-cuda-eula.txt) | C-LIC-007…010 |
| 6 | `NVIDIA-ISAAC-ROS/isaac_ros_common@7bec6ae5db…:LICENSE` (NVIDIA Isaac ROS Software License) | raw.githubusercontent at the pinned SHA | see `ORIGINAL-HASHES.txt` | [`LIC/12-…`](LIC/12-isaac-ros-software-license.txt) | C-LIC-021 |
| 7 | `gitlab.com/nvidia/nv-tegra/3rdparty/canonical/linux-noble@78272943bba3…:COPYING` (L4T r39.2.1 kernel; repo and commit taken from meta-tegra `linux-noble-nvidia-tegra.inc` L22-L25) | raw at the pinned SHA | see `ORIGINAL-HASHES.txt` | [`LIC/20-…`](LIC/20-l4t-kernel-linux-noble-COPYING.txt) | C-LIC-017 |
| — | https://developer.nvidia.com/embedded/jetson-linux-r3921 | returned HTTP 404 on 2026-11-11; not used | — | — | — |

## 2. Distribution and trademark policies (archived)

| # | Source | Archive | Claims |
|---|---|---|---|
| 8 | https://canonical.com/legal/intellectual-property-policy (IPRights Policy, 15 July 2015) | [`LIC/05-…`](LIC/05-canonical-iprights-policy.txt) | C-LIC-011 |
| 9 | https://www.debian.org/trademark | [`LIC/06-…`](LIC/06-debian-trademark-policy.txt) | C-LIC-012 |
| 10 | https://www.debian.org/social_contract | [`LIC/07-…`](LIC/07-debian-social-contract.txt) | context for the Debian row |
| 11 | https://www.redhat.com/en/about/trademark-guidelines-and-policies (last modified 2026-06-10) | [`LIC/08-…`](LIC/08-redhat-trademark-guidelines.txt) | C-LIC-013 |
| 12 | https://www.centos.org/legal/trademarks/ | [`LIC/09-…`](LIC/09-centos-trademark-guidelines.txt) | C-LIC-014 |
| 13 | https://docs.fedoraproject.org/en-US/legal/trademark-guidelines/ | **UNVERIFIED (blocked):** an Anubis proof-of-work page was served instead. Not bypassed. Captured as [`LIC/21-…`](LIC/21-fedora-trademark-BLOCKED-anubis.txt) | C-LIC-049 |
| 14 | https://almalinux.org/legal/ | HTTP 404; AlmaLinux trademark terms remain UNVERIFIED | — |

## 3. Firmware and other non-standard licences (archived)

| # | Source (pinned) | Archive | Claims |
|---|---|---|---|
| 15 | `raspberrypi/firmware@016253866bbd6c77fcb2a744a97d81e79ad4884f:boot/LICENCE.broadcom` | [`LIC/10-…`](LIC/10-raspberrypi-firmware-LICENCE.broadcom.txt) | C-LIC-015 |
| 16 | `raspberrypi/rpi-eeprom` (tag v2026.10.30-2712) `LICENSE` | [`LIC/11-…`](LIC/11-rpi-eeprom-LICENSE.txt) | C-LIC-016 |
| 17 | `gitlab.com/kernel-firmware/linux-firmware@69e51bb26f3fa3e118dd770f1962a93bed690dc1:WHENCE` (excerpt) and `LICENCE.cypress` (head) | [`LIC/18-…`](LIC/18-linux-firmware-WHENCE-excerpt.txt), [`LIC/19-…`](LIC/19-linux-firmware-LICENCE.cypress-head.txt) | C-LIC-020, 055 |
| 18 | `open-webui/open-webui` (v0.13.3) `LICENSE` | [`LIC/13-…`](LIC/13-open-webui-license.txt) | C-LIC-022 |
| 19 | `hailo-ai/hailort@e7727f7482477e448f4c93b33dc62f9e5a30c3e7:hailort/hailo_firmware_eula` | [`LIC/14-…`](LIC/14-hailo-firmware-eula.txt) | C-LIC-025 |
| 20 | `airockchip/rknn-toolkit2` (master) `LICENSE` | [`LIC/15-…`](LIC/15-rknn-sdk-license.txt) | C-LIC-024 |
| 21 | `emqx/emqx` (6.3.2) `LICENSE` (BSL 1.1) | [`LIC/16-…`](LIC/16-emqx-bsl-1.1.txt) | matrix row (reconfirms C-W8-013) |
| 22 | `markqvist/Reticulum` (1.6.0) `LICENSE` | [`LIC/17-…`](LIC/17-reticulum-license.txt) | matrix row (reconfirms C-W8-014) |

## 4. Licence files read at pinned SHAs (not archived: the permalink is the archive)

All 135 GitHub permalinks in [`../license-matrix.csv`](../license-matrix.csv) were checked on 2026-11-11 and each returned HTTP 200 from `raw.githubusercontent.com` at its commit SHA. The non-GitHub permalinks also returned 200: GitLab (linux-noble, cryptsetup v2.8.8 `f1dbcce1…`, AppArmor `bda75d45…`) and Salsa (Debian `linux` debian/6.12.116-1 `7ce8fe4c…`, GRUB debian/2.12-9+deb13u4 `720b9277…`). The CIP kernel COPYING was read at `linux-cip@c8fba740567363d02e64b657c2e6b26d86c5f84d` on git.kernel.org.

Method for every row: `gh api repos/<o>/<r>/releases/latest` (or the default branch when a repo has no releases), then `gh api repos/<o>/<r>/commits/<tag>` for the SHA, then `gh api repos/<o>/<r>/license?ref=<sha>` for the file path. The **file text** was decoded and read. The SPDX ID in the matrix comes from that text, not from GitHub's detector, which returned `NOASSERTION` or nothing for 48 of the 137 repositories queried.

## 5. Re-used claims from other workstreams (not re-fetched)

C-W2-001…006, C-W2-041, C-W2-050, C-REF-DC-cost-001…003 and 007…008, C-W8-011, C-W8-013, C-W8-014, C-W8-031, C-TD-olares-047, C-TD-villageos-025, C-TD-flagged-032, C-W18-056. These are cited in `license-matrix.md` and `outreach-drafts.md` as their owners recorded them.
