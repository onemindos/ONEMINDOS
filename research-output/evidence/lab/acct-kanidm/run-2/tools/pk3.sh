#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# PK-3..PK-6: the same passkey over both access paths; what happens with other names.
# nsl = LAN client (canonical name -> LAN-side address), nsm = away client (canonical name -> mesh-side address).
set -euo pipefail; T=PK-3; . /root/aklab/lib.sh
bash /root/aklab/netns.sh >/dev/null
W(){ ip netns exec $1 env HOME=/root python3 -I /root/aklab/wa.py "${@:2}"; }
C=https://idm.onemind.test:8443; ALIAS=https://idm.mesh.test:8443; SUB=https://mesh.idm.onemind.test:8443
note "the passkey enrolled offline in PK-2 lives in a virtual authenticator exported to owner.cred; each sign-in below is a NEW browser given that passkey, like one phone used at home and away"
run "python3 -I -c \"import json,hashlib,base64; c=json.load(open('$SEC/owner.cred'))[0]; i=c['id']; print('owner passkey fingerprint', hashlib.sha256(base64.urlsafe_b64decode(i+'==')).hexdigest()[:16], 'rp_id', c['rp_id'])\""
T=PK-3; stamp "PK-3: sign in over the MESH path (away from home), canonical name"
run "W nsm signin $C owner owner.cred ok" 
T=PK-4; stamp "PK-4: sign in over the LAN path, canonical name, the same passkey"
run "W nsl signin $C owner owner.cred ok"
T=PK-5; stamp "PK-5: a second host name OUTSIDE the canonical domain ($ALIAS), same server, valid TLS"
run "ip netns exec nsm curl -sS --cacert /etc/kanidm/ca.pem -o /dev/null -w 'TLS ok, http=%{http_code}\n' $ALIAS/status"
run "W nsm signin $ALIAS owner owner.cred refused"
note "and enrolling a passkey from that name"
run "reset_token owner owner.reset"
run "W nsm enrol $ALIAS owner owner2.cred refused"
T=PK-6; stamp "PK-6: a host name UNDER the canonical domain ($SUB)"
run "W nsm signin $SUB owner owner.cred ok"
note "enrolling a NEW passkey from the sub-domain name, then using it on the canonical name"
run "reset_token owner owner.reset"
run "W nsm enrol $SUB owner owner2.cred ok"
T=PK-6; run "W nsl signin $C owner owner2.cred ok"
