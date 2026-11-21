#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# GPU variant rootfs step (S-5), run inside the Containerfile after the board's files are copied. Does four things:
#   1. adds Debian's non-free component (same pinned snapshot) just long enough to install the NVIDIA driver,
#   2. builds the kernel modules for the image's kernel (DKMS), so nothing compiles on the box,
#   3. installs the NVIDIA Container Toolkit from the pinned, hash-checked files in gpu/toolkit.txt,
#   4. records every closed package and its licence in /usr/lib/onemind/gpu-licences.txt, and a 'gpu=nvidia' line.
# Debian's own apt sources are put back afterwards, so the image's package list is the SBOM of what was added.
set -eu
D=/tmp/onemind/board/gpu
SRC=/etc/apt/sources.list.d/onemind-snapshot.sources

# the packages to install, each with a licence row
PKGS=$(sed 's/#.*//' "$D/packages.txt" | tr -s ' \t\n' '\n' | sed '/^$/d' | sort -u)
for p in $PKGS; do
  grep -q "^$p|" "$D/licences.txt" || { echo "gpu: package $p has no row in licences.txt" >&2; exit 1; }
done

# 1. non-free from the same snapshot; the file is restored at the end
[ -f "$SRC" ] || { echo "gpu: $SRC not found (the GPU variant is for the Debian leg)" >&2; exit 1; }
cp "$SRC" /tmp/onemind-sources.orig
sed -i 's/^Components: .*/Components: main non-free/' "$SRC"
apt-get update

# 2. driver and modules for the image's kernel
# shellcheck disable=SC2012  # same kernel pick as the Containerfile
kver=$(ls /lib/modules | sort -V | tail -n1)
# shellcheck disable=SC2086  # a word list on purpose
apt-get install -y $PKGS
dkms status | grep -q "^nvidia.*$kver.*installed" || dkms autoinstall -k "$kver"
dkms status | grep -q "^nvidia.*$kver.*installed" || { echo "gpu: NVIDIA modules not built for $kver" >&2; exit 1; }
depmod "$kver"

# 3. container toolkit, pinned by hash
mkdir -p /tmp/nvtk
BASE=https://nvidia.github.io/libnvidia-container/stable/deb/amd64
n=0
while IFS='|' read -r f sha; do
  case "$f" in ''|'#'*) continue ;; esac
  curl -fsSL --retry 5 -o "/tmp/nvtk/$f" "$BASE/$f"
  echo "$sha  /tmp/nvtk/$f" | sha256sum -c - >/dev/null || { echo "gpu: hash mismatch for $f" >&2; exit 1; }
  n=$((n + 1))
done < "$D/toolkit.txt"
[ "$n" -eq 4 ] || { echo "gpu: expected 4 toolkit files, found $n" >&2; exit 1; }
apt-get install -y /tmp/nvtk/*.deb
rm -rf /tmp/nvtk
command -v nvidia-container-runtime >/dev/null   # k3s finds this on its PATH and adds the 'nvidia' runtime itself

# 4. back to the stock sources; licences and the build marker
cp /tmp/onemind-sources.orig "$SRC"; rm -f /tmp/onemind-sources.orig
rm -rf /var/lib/apt/lists/*
mkdir -p /usr/lib/onemind
cp "$D/licences.txt" /usr/lib/onemind/gpu-licences.txt
printf 'gpu=nvidia driver=%s toolkit=1.19.1-1 kernel=%s\n' \
  "$(dpkg-query -W -f='${Version}' nvidia-kernel-dkms)" "$kver" > /usr/lib/onemind/gpu-info.txt
systemctl enable onemind-nvidia-setup.service >/dev/null
cat /usr/lib/onemind/gpu-info.txt
