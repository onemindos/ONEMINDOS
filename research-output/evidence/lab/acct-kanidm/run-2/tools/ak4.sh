#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# AK-4 OIDC client with group scope and claim maps.
set -euo pipefail; T=AK-4; . /root/aklab/lib.sh
C=onemind_testapp; RED=https://app.onemind.test/oauth2/callback
stamp "AK-4: OIDC client"
run "admin_relogin"
run "k system oauth2 create $C 'OneMind test app' https://app.onemind.test"
run "k system oauth2 add-redirect-url $C $RED"
run "k system oauth2 update-scope-map $C onemind_owners openid profile email groups"
run "k system oauth2 update-scope-map $C onemind_adults openid profile groups"
run "k system oauth2 update-scope-map $C onemind_children openid groups"
run "k system oauth2 update-claim-map $C onemind_role onemind_owners owner"
run "k system oauth2 update-claim-map $C onemind_role onemind_adults adult"
run "k system oauth2 update-claim-map $C onemind_role onemind_children child"
run "kanidm system oauth2 show-basic-secret $C -D idm_admin 2>/dev/null | tail -1 > $SEC/$C.client_secret; chmod 600 $SEC/$C.client_secret; test -s $SEC/$C.client_secret && echo 'client secret kept in the secrets dir'"
run "k system oauth2 get $C | grep -vE 'secret|key' "
note "the owner passkey is the browser-enrolled one from PK-2: hand its key to the API client, then carry the counter back"
run "env HOME=/root python3 -I /root/aklab/wa.py tosoft owner owner.cred"
run "\$PY oidc owner $C $RED passkey 'openid groups profile email'"
run "env HOME=/root python3 -I /root/aklab/wa.py fromsoft owner owner.cred"
run "\$PY oidc adult1 $C $RED passkey 'openid groups profile'"
run "\$PY oidc child1 $C $RED passkey 'openid groups'"
note "the scope map is enforced: a child asking for 'profile' (only owners and adults have it) is refused"
run "\$PY oidc child1 $C $RED passkey 'openid groups profile'"
note "guest1 is only in onemind_guests, which has no scope map: must be refused"
run "\$PY oidc guest1 $C $RED passkey"
