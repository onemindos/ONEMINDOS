#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# AK-0: environment record. usage: ak0.sh <label>
set -euo pipefail; T=AK-0; . /root/aklab/lib.sh
stamp "environment: $1"
run "grep -E '^PRETTY_NAME=' /etc/os-release; cat /etc/debian_version; uname -rm; nproc; free -m | head -2; df -h / | tail -1"
run "chromium --version; chromedriver --version | head -1; python3 -c 'import selenium; print(\"selenium\", selenium.__version__)'"
run "sha256sum /root/aklab/debs/*.deb"
