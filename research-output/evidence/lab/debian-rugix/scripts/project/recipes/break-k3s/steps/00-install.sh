#!/bin/bash
set -euo pipefail
echo "K3S_EXTRA_ARGS=${RECIPE_PARAM_ARGS}" > /etc/default/k3s
cat /etc/default/k3s
