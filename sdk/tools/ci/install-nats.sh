#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Install the deployment-pinned NATS server in this CI job's own directory.
set -euo pipefail

# shellcheck source=deploy/pins.env
. "$(dirname "$0")/../../../deploy/pins.env"
case "$(uname -m)" in
  x86_64) arch=amd64 ;;
  aarch64|arm64) arch=arm64 ;;
  *) echo "unsupported NATS architecture: $(uname -m)" >&2; exit 2 ;;
esac
case "$(uname -s)" in
  Linux)
    os=linux; sum_var="NATS_SHA256_${arch}"; checksum=(sha256sum) ;;
  Darwin)
    os=darwin; sum_var="NATS_SHA256_darwin_${arch}"; checksum=(shasum -a 256) ;;
  *) echo "unsupported NATS runner OS: $(uname -s)" >&2; exit 2 ;;
esac
pkg="nats-server-${NATS_VERSION}-${os}-${arch}"
bin=$(mktemp -d "${RUNNER_TEMP:?}/nats.XXXXXX")
archive="$bin/nats.tgz"
trap 'rm -f "$archive"' EXIT
curl -fsSL --retry 3 -o "$archive" "https://github.com/nats-io/nats-server/releases/download/${NATS_VERSION}/${pkg}.tar.gz"
printf '%s  %s\n' "${!sum_var}" "$archive" | "${checksum[@]}" -c -
tar -xOzf "$archive" "$pkg/nats-server" > "$bin/nats-server"
chmod 0755 "$bin/nats-server"
"$bin/nats-server" --version
printf '%s\n' "$bin" >> "${GITHUB_PATH:?}"
