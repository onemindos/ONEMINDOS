#!/bin/bash
set -euo pipefail
install -m 644 "${RECIPE_DIR}/files/k3s.service" /etc/systemd/system/k3s.service
install -D -m 644 "${RECIPE_DIR}/files/onemind-state.toml" /etc/rugix/state/onemind.toml
: > /etc/default/k3s
mkdir -p /var/lib/rancher /etc/rancher/node /var/log/onemind
systemctl enable k3s.service
