#!/bin/bash
# Build Kanidm v1.12.0 Debian packages natively on Debian 13 with the project's own PPA automation scripts.
set -euxo pipefail
export CI=true VERBOSE=true DEBIAN_FRONTEND=noninteractive
apt-get update && apt-get install -y git ca-certificates curl
cd /root
git clone --branch v1.12.0 --depth 1 https://github.com/kanidm/kanidm.git
cd kanidm
git submodule update --init --depth 1 platform/debian/kanidm_ppa_automation || (git submodule update --init platform/debian/kanidm_ppa_automation)
git rev-parse HEAD; git submodule status
platform/debian/kanidm_ppa_automation/scripts/install_ci_build_dependencies.sh
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o /root/rustup-init.sh
sh /root/rustup-init.sh -y --profile minimal --default-toolchain 1.96.0
. /root/.cargo/env
rustup toolchain install 1.96
export RUSTFLAGS="-C link-arg=-fuse-ld=lld"
platform/debian/kanidm_ppa_automation/scripts/build_native.sh x86_64-unknown-linux-gnu
platform/debian/kanidm_ppa_automation/scripts/build_debs.sh x86_64-unknown-linux-gnu
sha256sum target/x86_64-unknown-linux-gnu/debian/*.deb
echo BUILD-DONE
