#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# PK-7 (fresh Debian 13 box, same canonical domain): restore the online backup, then sign in with the SAME passkey
# (the key stays in the "phone" = owner.cred, copied over; it is not part of the backup) on both access paths.
set -euo pipefail; T=PK-7; . /root/aklab/lib.sh
stamp "PK-7: restore on a fresh Debian 13 install"
run "grep -E '^PRETTY_NAME=' /etc/os-release; uptime -s; cut -c1-8 /etc/machine-id; dpkg -l | grep -c kanidm || true"
run "bash /root/aklab/setup2.sh deb /root/aklab/debs"
run "bash /root/aklab/netns.sh >/dev/null; grep -E '^(domain|origin)' /etc/kanidmd/server.toml"
run "sha256sum /root/aklab/restore-input.json.gz"
run "install -d -m 0750 /var/lib/private/kanidmd; maxrss kanidmd database restore -c /etc/kanidmd/server.toml /root/aklab/restore-input.json.gz 2>&1 | tail -4"
run "systemctl enable --now kanidmd; for i in \$(seq 1 30); do systemctl is-active -q kanidmd && break; sleep 1; done; systemctl is-active kanidmd"
run "sleep 3; curl -sS --cacert /etc/kanidm/ca.pem https://idm.onemind.test:8443/status; echo"
W(){ ip netns exec $1 env HOME=/root python3 -I /root/aklab/wa.py "${@:2}"; }
C=https://idm.onemind.test:8443
run "python3 -I -c \"import json,hashlib,base64; c=json.load(open('$SEC/owner.cred'))[0]; print('owner passkey fingerprint', hashlib.sha256(base64.urlsafe_b64decode(c['id']+'==')).hexdigest()[:16])\""
T=PK-7; stamp "restored box, LAN path"
run "W nsl signin $C owner owner.cred ok"
stamp "restored box, mesh path"
run "W nsm signin $C owner owner.cred ok"
stamp "restored box: people and groups came back"
run "$PY signin adult1 passkey || true"
