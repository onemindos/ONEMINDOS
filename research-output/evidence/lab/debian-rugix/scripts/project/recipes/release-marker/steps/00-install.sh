#!/bin/bash
set -euo pipefail
echo "${RECIPE_PARAM_VERSION}" > /etc/onemind-release
