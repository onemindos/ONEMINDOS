#!/bin/bash
# Secondary (labelled) leg B variant: bump the kernel to the latest 6.12.y LTS point
# release and time that incremental rebuild. Hash checking is relaxed for the kernel
# tarball only because Buildroot 2025.02.19's linux.hash predates it; the tarball
# sha256 is checked by hand against kernel.org's sha256sums.asc and recorded.
set -euo pipefail
V=${1:?kernel version e.g. 6.12.117}
BR=${BR:-/var/lab/dc20/in/buildroot-2025.02.19}; L=/var/lab/dc20/legB; O=/var/lab/dc20/build-b; OUT=/var/lab/dc20/out/legB-k$V
mkdir -p "$OUT"; cd "$BR"
sed -e "s/6.12.112/$V/" -e 's/^BR2_DOWNLOAD_FORCE_CHECK_HASHES=y/# BR2_DOWNLOAD_FORCE_CHECK_HASHES is not set/' $L/onemind_dc20_defconfig > $L/onemind_dc20_k${V}_defconfig
make O=$O BR2_DEFCONFIG=$L/onemind_dc20_k${V}_defconfig defconfig >/dev/null
make O=$O linux-source > "$OUT/dl.log" 2>&1
sha256sum dl/linux/linux-$V.tar.xz | tee "$OUT/kernel-tarball.sha256"
make O=$O linux-dirclean >/dev/null
s=$(date +%s); make O=$O -j$(nproc) > "$OUT/build-inc-kernel.log" 2>&1; e=$(date +%s)
echo "incremental_kernel_bump_6.12.112_to_$V $((e-s))" | tee "$OUT/times.txt"
cp $O/images/disk.img $O/images/rootfs.ext2 "$OUT/"
make O=$O show-info > "$OUT/show-info.json" 2>/dev/null
python3 utils/generate-cyclonedx < "$OUT/show-info.json" > "$OUT/buildroot.cdx.json"
