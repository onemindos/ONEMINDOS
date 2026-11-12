#!/bin/bash
set -euo pipefail
echo "ONEMIND_GATE_FRESHNESS=0" >> /etc/default/onemind-health-gate
cat /etc/default/onemind-health-gate
