# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# NVIDIA downloads for the Jetson board, sourced by build-flash-package.sh and build-ota-bundle.sh.
# Same values as os/versions.lock.yaml `jetson:` (test/unit/test_jetson_orin.py checks they match).
# sha256 read 2026-11-12 by hashing NVIDIA's files; the two BSP tarballs also equal meta-tegra's
# SRC_URI[sha256sum] (wrynose 39.2.1, scarthgap 36.5.2).
# shellcheck disable=SC2034
pins_for() {
  case "$1" in
  39.2.1)
    L4T_URL=https://developer.download.nvidia.com/embedded/L4T/r39_Release_v2.1/release
    L4T_BSP=Jetson_Linux_R39.2.1_aarch64.tbz2
    L4T_BSP_SHA256=2e5619088ba88e85dab25247f033d70659b6f676ff835176a07766dcb0fdbe6b
    L4T_ROOTFS=Tegra_Linux_Sample-Root-Filesystem_R39.2.1_aarch64.tbz2
    L4T_ROOTFS_SHA256=58a6485b56c6d6b5ee8478e902eed0ed4984fd73135b88b76aeaa5c1f44be66e
    L4T_OTA_TOOLS=ota_tools_R39.2.1_aarch64.tbz2
    L4T_OTA_TOOLS_SHA256=bc84c2ef0e7e43ccd496691c134b3931c21858272ed75fa0e4b9c853eca2a441
    L4T_AB_XML=tools/kernel_flash/flash_l4t_t234_nvme_rootfs_ab.xml
    L4T_BSP_ARG=R39-2 ;;
  36.5.2)
    L4T_URL=https://developer.download.nvidia.com/embedded/L4T/r36_Release_v5.2/releases
    L4T_BSP=Jetson_Linux_R36.5.2_aarch64.tbz2
    L4T_BSP_SHA256=752326264c5e16826d3044a78e59ae06109467d37705143b94e664c91a471f47
    L4T_ROOTFS=Tegra_Linux_Sample-Root-Filesystem_R36.5.2_aarch64.tbz2
    L4T_ROOTFS_SHA256=077da9b27b1d3bc2247c2b73ce10cce880bdefe1f048d2a64df878d855a5b435
    L4T_OTA_TOOLS=ota_tools_R36.5.2_aarch64.tbz2
    L4T_OTA_TOOLS_SHA256=dc867412c8fa9cad6dad60742a1e6c6821297b943f7697c4356d74d73188bac9
    L4T_AB_XML=UNVERIFIED   # r36 file name not read: build-flash-package.sh globs *t234*nvme*rootfs_ab.xml
    L4T_BSP_ARG=R36-5 ;;
  *) echo "pins.sh: no pins for L4T $1 (pinned: 39.2.1, 36.5.2)" >&2; return 1 ;;
  esac
}
