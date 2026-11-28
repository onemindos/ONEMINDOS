#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# AK-8 TOTP replay.
set -euo pipefail; T=AK-8; . /root/aklab/lib.sh
stamp "AK-8: TOTP replay (adult2 has password + TOTP, enrolled in AK-3)"
run "\$PY totp-replay adult2"
