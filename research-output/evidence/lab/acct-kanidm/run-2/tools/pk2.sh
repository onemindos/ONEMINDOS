#!/bin/bash
# PK-2: owner passkey enrolled with the outside network cut, in a real (headless Chromium) browser on the LAN path,
# then signed in with, still offline. Run through the QEMU guest agent: the VM's virtual cable is out.
set -euo pipefail; T=PK-2; . /root/aklab/lib.sh
bash /root/aklab/netns.sh >/dev/null
W="ip netns exec nsl env HOME=/root python3 -I /root/aklab/wa.py"; O=https://idm.onemind.test:8443
for i in $(seq 1 100); do systemctl is-active -q kanidmd && break; sleep 3; done
stamp "PK-2: offline enrolment, LAN path (host booted with the virtual NIC link down, Proxmox link_down=1)"
run "uptime -s; systemctl is-active kanidmd; systemctl show kanidmd -p ActiveEnterTimestamp"
run "for i in \$(ls /sys/class/net | grep -vE '^(lo|v-ns|c-ns)'); do ip link set \$i down; done; ip -br link | grep -vE 'v-ns|c-ns'; echo 'default route:'; ip -4 route show default; echo '(none above = no way out)'"
run "ping -c1 -W2 1.1.1.1 || echo 'no route out: offline'"
run "getent ahosts deb.debian.org || echo 'no DNS: offline'"
run "ip netns exec nsl curl -sS --cacert /etc/kanidm/ca.pem https://idm.onemind.test:8443/status; echo"
note "recover idm_admin (new password goes straight into the secrets dir; not printed)"
run "kanidmd scripting recover-account idm_admin -c /etc/kanidmd/server.toml 2>/dev/null | python3 -I -c 'import json,sys,os; d=json.load(sys.stdin); fd=os.open(\"$SEC/idm_admin.password\",os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600); os.write(fd,d[\"output\"].encode()); print(\"recover-account status:\", d[\"status\"])'"
run "admin_login"
run "k person create owner 'Home Owner'"
run "reset_token owner owner.reset"
run "$W enrol $O owner owner.cred"
run "$W signin $O owner owner.cred"
run "ip -br link | grep -vE 'v-ns|c-ns'; ping -c1 -W2 1.1.1.1 || echo 'still offline'"
stamp "PK-2 end"
