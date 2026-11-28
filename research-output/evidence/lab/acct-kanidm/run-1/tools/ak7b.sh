#!/bin/bash
# AK-7 part 2 (fresh Debian 13 box, same domain): restore, start, sign in with the SAME passkey.
set -euo pipefail; T=AK-7; . /root/aklab/lib.sh
stamp "AK-7 part 2: restore on a fresh Debian 13 install"
run "grep -E '^PRETTY_NAME=' /etc/os-release; uptime -s; cat /etc/machine-id | cut -c1-8; dpkg -l | grep -c kanidm || true"
run "bash /root/aklab/setup.sh /root/aklab/debs"
run "systemctl is-enabled kanidmd || true; systemctl is-active kanidmd || true"
run "grep -E '^(domain|origin)' /etc/kanidmd/server.toml"
run "sha256sum /root/aklab/restore-input.json.gz"
run "install -d -m 0750 /var/lib/private/kanidmd; maxrss kanidmd database restore -c /etc/kanidmd/server.toml /root/aklab/restore-input.json.gz 2>&1 | tail -4"
run "systemctl enable --now kanidmd; for i in \$(seq 1 30); do systemctl is-active -q kanidmd && break; sleep 1; done; systemctl is-active kanidmd"
run "sleep 3; curl -sS --cacert /etc/kanidm/ca.pem https://idm.onemind.test:8443/status; echo"
note "the owner's virtual authenticator file is the one from AK-2, copied over unchanged"
run "\$PY passkey-fp owner"
run "\$PY signin owner passkey"
T=AK-9; stamp "restored box"; sleep 20; run "rss"; run "du -sh /var/lib/private/kanidmd /var/lib/private/kanidmd/kanidm.db* 2>/dev/null"
