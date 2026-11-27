#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# AK-6 account expiry.
set -euo pipefail; T=AK-6; . /root/aklab/lib.sh
stamp "AK-6: account expiry"
run "admin_relogin"
EXP=$(date -u -d '+3 minutes' +%Y-%m-%dT%H:%M:%SZ)
run "k person validity expire-at guest1 $EXP"
run "k person validity show guest1"
run "\$PY signin guest1 passkey"
run "\$PY session-check guest1"
note "waiting until 30 s after the expiry ($EXP)"
while [ "$(date -u +%s)" -lt $(( $(date -u -d "$EXP" +%s) + 30 )) ]; do sleep 5; done
stamp "after expiry"
run "\$PY signin guest1 passkey refused"
run "\$PY session-check guest1"
T=AK-9; stamp "RSS after AK-3 to AK-6"; run "rss"
