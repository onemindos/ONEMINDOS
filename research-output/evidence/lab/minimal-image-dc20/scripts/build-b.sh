#!/bin/bash
# LAB-minimal-image-dc20 leg B: Buildroot 2025.02.19 LTS x86_64 EFI image, timed.
# Run as a normal user INSIDE the disposable Lima VM (never on the host):
#   bash build-b.sh
# Layout: /var/lab/dc20/in/buildroot (git tag 2025.02.19), /var/lab/dc20/legB (configs),
#         /var/lab/dc20/in/k3s (verified binary). Output: /var/lab/dc20/out/legB
set -euo pipefail
BR=${BR:-/var/lab/dc20/in/buildroot-2025.02.19}; L=/var/lab/dc20/legB; O=/var/lab/dc20/build-b; OUT=/var/lab/dc20/out/legB
mkdir -p "$OUT" "$L/overlay/usr/local/bin"
install -m 0755 /var/lab/dc20/in/k3s "$L/overlay/usr/local/bin/k3s"
J=$(nproc)
t(){ local name=$1; shift; local s=$(date +%s); "$@"; local e=$(date +%s); echo "$name $((e-s))" | tee -a "$OUT/times.txt"; }
: > "$OUT/times.txt"
cd "$BR"
echo "buildroot $(git rev-parse HEAD) $(git describe --tags)" > "$OUT/versions.txt"
make O=$O BR2_DEFCONFIG=$L/onemind_dc20_defconfig defconfig >/dev/null
cp $O/.config "$OUT/dot-config"
# M4(i) clean build including all source downloads (dl/ empty)
t clean_with_downloads make O=$O -j$J > "$OUT/build-clean.log" 2>&1
cp $O/images/disk.img $O/images/rootfs.ext2 $O/images/bzImage "$OUT/"
# M2 Buildroot's own SBOM
make O=$O show-info > "$OUT/show-info.json" 2>/dev/null
python3 utils/generate-cyclonedx < "$OUT/show-info.json" > "$OUT/buildroot.cdx.json"
make O=$O legal-info >/dev/null 2>&1 && cp $O/legal-info/manifest.csv "$OUT/legal-manifest.csv" || echo "legal-info failed" >> "$OUT/times.txt"
# M4(iii) incremental: one package changed (openssh rebuilt) + rootfs/image regenerated
make O=$O openssh-dirclean >/dev/null
t incremental_one_package make O=$O -j$J > "$OUT/build-inc-openssh.log" 2>&1
# M4(ii) clean build with downloads cached
make O=$O clean >/dev/null
make O=$O BR2_DEFCONFIG=$L/onemind_dc20_defconfig defconfig >/dev/null
t clean_downloads_cached make O=$O -j$J > "$OUT/build-clean-cached.log" 2>&1
du -sh "$BR/dl" $O | tee -a "$OUT/times.txt"
echo DONE
