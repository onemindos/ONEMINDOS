#!/bin/bash
set -euo pipefail
install -m 644 "${RECIPE_DIR}/files/dhcp.network" /etc/systemd/network/
systemctl enable systemd-networkd.service
