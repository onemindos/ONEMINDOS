#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# LT-PI5-02: run ON the Pi after each step; prints the evidence the result template asks for.
# Read-only: it changes nothing on the device. Always pipe it through the redactor:
#   sh collect-evidence.sh <label> | sh redact.sh > step-<label>.txt   (copy it from lab-kits/common next to this script)
set -eu
label=${1:-step}
echo "== LT-PI5-02 evidence: $label =="
echo "-- date (UTC)"; date -u +%Y-%m-%dT%H:%M:%SZ
echo "-- model / kernel / page size"
tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo "model: unknown"; echo
uname -r; getconf PAGESIZE
echo "-- EEPROM bootloader"
rpi-eeprom-update 2>/dev/null | head -5 || echo "rpi-eeprom-update not installed"
echo "-- bootc status"
bootc status 2>&1 || echo "bootc not found"
echo "-- ostree deployments"
ostree admin status 2>&1 || echo "ostree not found"
echo "-- greenboot (this boot and the previous one)"
rpm -q greenboot 2>/dev/null || echo "greenboot rpm not found"
journalctl -u greenboot-healthcheck -b 0 --no-pager 2>&1 | tail -n 30 || true
journalctl -u greenboot-healthcheck -b -1 --no-pager 2>&1 | tail -n 30 || true
echo "-- k3s"
k3s --version 2>/dev/null | head -1 || echo "k3s not found"
systemctl is-active k3s 2>&1 || true
