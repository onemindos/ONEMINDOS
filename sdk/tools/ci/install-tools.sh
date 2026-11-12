#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Install the app-gate tools on a linux/amd64 CI runner, each pinned by version and sha256
# (brief 30 §2 rule 2; the same pins are recorded in os/versions.lock.yaml under tools.app_gate).
# Usage: sdk/tools/ci/install-tools.sh <bin-dir> [tool ...]   (default: every tool)
# ClamAV comes from the runner's Ubuntu archive (apt verifies its signatures); see the workflows.
set -euo pipefail

bin=${1:?usage: install-tools.sh <bin-dir> [tool ...]}
shift
tools=("$@")
[ ${#tools[@]} -gt 0 ] || tools=(trivy crane cosign k3d kubectl kustomize kubeconform gitleaks)
mkdir -p "$bin"
dl=$(mktemp -d)
trap 'rm -rf "$dl"' EXIT

fetch() { # url sha256 file
  curl -fsSL --retry 3 -o "$dl/$3" "$1"
  echo "$2  $dl/$3" | sha256sum -c - >/dev/null
}

for tool in "${tools[@]}"; do
  case "$tool" in
    trivy)  # v0.76.2, brief 30 D-B1.5
      fetch https://github.com/aquasecurity/trivy/releases/download/v0.76.2/trivy_0.76.2_Linux-64bit.tar.gz \
        bc0fc726e017b8927a62b2d3531d7a84ee01769daf5c99ed866dced54089fdbf trivy.tgz
      tar -xzf "$dl/trivy.tgz" -C "$bin" trivy ;;
    crane)
      fetch https://github.com/google/go-containerregistry/releases/download/v0.22.1/go-containerregistry_Linux_x86_64.tar.gz \
        0ab7a1d6932a213aed964ce97666c3077fe691c8606413674a8b3e0b9ec4cda0 crane.tgz
      tar -xzf "$dl/crane.tgz" -C "$bin" crane ;;
    cosign)
      fetch https://github.com/sigstore/cosign/releases/download/v3.1.4/cosign-linux-amd64 \
        424e2c97d0b45fd7a6b608a87f090f35633f4c23ece5f092d48bba11aaf4bbfa cosign
      install -m 0755 "$dl/cosign" "$bin/cosign" ;;
    k3d)
      fetch https://github.com/k3d-io/k3d/releases/download/v5.9.0/k3d-linux-amd64 \
        06d8f25bc3a971c4eb29e0ff08429b180402db0f4dec838c9eac427e296800a0 k3d
      install -m 0755 "$dl/k3d" "$bin/k3d" ;;
    kubectl)  # same minor as the k3s pin in os/versions.lock.yaml
      fetch https://dl.k8s.io/release/v1.37.2/bin/linux/amd64/kubectl \
        c04487523e7aa7d1493f7808174c899db93d7a9cf57531420cd76b9bd415f8f4 kubectl
      install -m 0755 "$dl/kubectl" "$bin/kubectl" ;;
    kustomize)
      fetch https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv5.8.3/kustomize_v5.8.3_linux_amd64.tar.gz \
        cb9e31198d3f63b44848bd0afc4c8efc56e6cfef9c93a4a39a211940e6decd61 kustomize.tgz
      tar -xzf "$dl/kustomize.tgz" -C "$bin" kustomize ;;
    kubeconform)
      fetch https://github.com/yannh/kubeconform/releases/download/v0.8.0/kubeconform-linux-amd64.tar.gz \
        9bc2bffbf71f261128533edaf912153948b7ff238f9a531ae6d34466ec287883 kubeconform.tgz
      tar -xzf "$dl/kubeconform.tgz" -C "$bin" kubeconform ;;
    gitleaks)  # os/versions.lock.yaml tools.gitleaks
      fetch https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz \
        551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb gitleaks.tgz
      tar -xzf "$dl/gitleaks.tgz" -C "$bin" gitleaks ;;
    *) echo "unknown tool: $tool" >&2; exit 2 ;;
  esac
  echo "installed $tool"
done
