#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# AK-10 revocation reaches apps.
set -euo pipefail; T=AK-10; . /root/aklab/lib.sh
C=onemind_testapp; RED=https://app.onemind.test/oauth2/callback
stamp "AK-10: revocation"
run "admin_relogin"
run "\$PY oidc adult1 $C $RED passkey 'openid groups profile'"
run "k group remove-members onemind_adults adult1"
run "\$PY oidc adult1 $C $RED passkey 'openid groups profile'"
