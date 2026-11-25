#!/bin/bash
# AK-4b: the owner's OIDC sign-in with the browser-enrolled passkey (the first try in AK-4 failed in the lab client: the
# browser exports the credential id with base64 padding, the API client compares without; fixed in wa.py tosoft).
set -euo pipefail; T=AK-4; . /root/aklab/lib.sh
C=onemind_testapp; RED=https://app.onemind.test/oauth2/callback
stamp "AK-4b: retry owner OIDC after the lab-client fix"
run "env HOME=/root python3 -I /root/aklab/wa.py tosoft owner owner.cred"
run "\$PY oidc owner $C $RED passkey 'openid groups profile email'"
run "env HOME=/root python3 -I /root/aklab/wa.py fromsoft owner owner.cred"
