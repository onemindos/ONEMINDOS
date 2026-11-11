#!/usr/bin/env bash
# Build images and bundles inside the Lima VM. Usage: LAB=<lab dir> ./10-build.sh amd64|arm64
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
LAB=${LAB:?}; ARCH=${1:-amd64}
export LIMA_HOME="$LAB/lima"
mkdir -p "$LAB/keys" "$LAB/work/project"
[ -f "$LAB/keys/lab_ed25519" ] || ssh-keygen -q -t ed25519 -N '' -C onemind-lab -f "$LAB/keys/lab_ed25519"
rsync -a --delete --exclude .rugix --exclude build --exclude .downloads "$HERE/project/" "$LAB/work/project/"
PUB=$(cat "$LAB/keys/lab_ed25519.pub")
sed -i '' "s|@LAB_SSH_PUBKEY@|$PUB|" "$LAB/work/project/layers/onemind-base.toml"
limactl shell dr -- sudo bash -c "cd /work/project && \
  ./run-bakery bake image v1-$ARCH && \
  ./run-bakery bake bundle v1-$ARCH && \
  ./run-bakery bake bundle v2good-$ARCH && \
  ./run-bakery bake bundle v2bad-$ARCH && \
  ./run-bakery bake bundle v2noagent-$ARCH && \
  ./run-bakery bake bundle v2noagentnaive-$ARCH && \
  chmod -R a+rX build && \
  find build -maxdepth 2 -type f -exec ls -l {} \; && \
  find build -maxdepth 2 -type f \( -name '*.img' -o -name '*.rugixb' \) -exec sha256sum {} \;"
