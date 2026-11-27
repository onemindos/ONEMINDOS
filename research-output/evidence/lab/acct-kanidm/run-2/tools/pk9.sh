#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# PK-9 (extra, F-33 naming): can the canonical sign-in name be "onemind.local" (the LAN name in the design)?
# A fresh Kanidm database whose domain/RP ID is onemind.local; LAN client resolves it to the LAN-side address,
# the "mesh" client resolves the SAME name to the mesh-side address through its own (unicast) resolver file.
set -euo pipefail; T=PK-9; . /root/aklab/lib.sh
export CANON=onemind.local
W(){ ip netns exec $1 env HOME=/root python3 -I /root/aklab/wa.py "${@:2}"; }
stamp "PK-9: canonical name onemind.local"
run "systemctl stop kanidmd; mv /var/lib/private/kanidmd /var/lib/private/kanidmd.before-pk9; bash /root/aklab/setup2.sh deb /root/aklab/debs >/dev/null 2>&1; bash /root/aklab/netns.sh >/dev/null; grep -E '^(domain|origin)' /etc/kanidmd/server.toml"
run "systemctl restart kanidmd; sleep 6; systemctl is-active kanidmd; ip netns exec nsm curl -sS --cacert /etc/kanidm/ca.pem https://onemind.local:8443/status; echo; ip netns exec nsl getent hosts onemind.local; ip netns exec nsm getent hosts onemind.local"
run "rm -f $SEC/*.cred $SEC/idm_admin.password; kanidmd scripting recover-account idm_admin -c /etc/kanidmd/server.toml 2>/dev/null | python3 -I -c 'import json,sys,os; d=json.load(sys.stdin); fd=os.open(\"$SEC/idm_admin.password\",os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600); os.write(fd,d[\"output\"].encode()); print(\"recover-account status:\", d[\"status\"])'"
run "printf 'uri = \"https://onemind.local:8443\"\nca_path = \"/etc/kanidm/ca.pem\"\n' > /etc/kanidm/config; rm -rf /root/.cache/kanidm_tokens; admin_login"
run "k person create owner 'Home Owner'"
run "reset_token owner owner.reset"
O=https://onemind.local:8443
run "W nsl enrol $O owner owner.cred"
run "W nsm signin $O owner owner.cred ok"
run "W nsl signin $O owner owner.cred ok"
run "W nsm signin https://mesh.onemind.local:8443 owner owner.cred ok"
stamp "PK-9 end"
