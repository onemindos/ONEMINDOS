#!/bin/bash
set -euo pipefail
install -D -m 755 "${RECIPE_DIR}/files/health-gate" /usr/lib/onemind/health-gate
install -D -m 755 "${RECIPE_DIR}/files/k3s-healthy" /usr/lib/onemind/k3s-healthy
install -D -m 755 "${RECIPE_DIR}/files/10-k3s-healthy" /etc/rugix/hooks/system-commit/pre-commit/10-k3s-healthy
install -m 644 "${RECIPE_DIR}/files/onemind-health-gate.service" /etc/systemd/system/
echo "ONEMIND_GATE_TIMEOUT=${RECIPE_PARAM_TIMEOUT}" > /etc/default/onemind-health-gate
systemctl enable onemind-health-gate.service
# Hardware watchdog: reboot (and so fall back) if the trial system hangs hard.
mkdir -p /etc/systemd/system.conf.d
printf '[Manager]\nRuntimeWatchdogSec=30s\n' > /etc/systemd/system.conf.d/onemind-watchdog.conf
