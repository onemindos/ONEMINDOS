#!/bin/bash
# Resume after the first attempt was OOM-killed on kanidmd_lib (8 GB VM, 4 parallel jobs): add swap, 2 jobs.
set -euxo pipefail
export CI=true VERBOSE=true CARGO_BUILD_JOBS=2
[ -f /swapfile ] || { fallocate -l 8G /swapfile; chmod 600 /swapfile; mkswap /swapfile; }
swapon /swapfile || true
cd /root/kanidm; . /root/.cargo/env
export RUSTFLAGS="-C link-arg=-fuse-ld=lld"
platform/debian/kanidm_ppa_automation/scripts/build_native.sh x86_64-unknown-linux-gnu
platform/debian/kanidm_ppa_automation/scripts/build_debs.sh x86_64-unknown-linux-gnu
sha256sum target/x86_64-unknown-linux-gnu/debian/*.deb
echo BUILD-DONE
