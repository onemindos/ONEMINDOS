#!/bin/bash
# AK-2 offline first boot. Run through the QEMU guest agent while the VM's virtual cable is out.
set -euo pipefail; T=AK-2; . /root/aklab/lib.sh
stamp "AK-2: host booted with the virtual NIC link down (Proxmox link_down=1)"
run "uptime -s; systemctl is-active kanidmd; systemctl show kanidmd -p ActiveEnterTimestamp"
run "for i in \$(ls /sys/class/net | grep -v '^lo\$'); do ip link set \$i down; done; ip -br link; ip -4 route"
run "ping -c1 -W2 1.1.1.1 || echo 'no route out: offline'"
run "getent ahosts deb.debian.org || echo 'no DNS: offline'"
run "curl -sS --cacert /etc/kanidm/ca.pem https://idm.onemind.test:8443/status; echo"
note "recover idm_admin (the new password goes straight into the secrets dir; not printed)"
run "kanidmd scripting recover-account idm_admin -c /etc/kanidmd/server.toml 2>/dev/null | python3 -I -c 'import json,sys,os; d=json.load(sys.stdin); fd=os.open(\"$SEC/idm_admin.password\",os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600); os.write(fd,d[\"output\"].encode()); print(\"recover-account status:\", d[\"status\"])'"
run "admin_login"
run "k person create owner 'Home Owner'"
run "reset_token owner owner.reset"
run "\$PY enrol owner owner.reset passkey"
run "\$PY signin owner passkey"
run "ip -br link; ping -c1 -W2 1.1.1.1 || echo 'still offline'"
stamp "AK-2 end"
