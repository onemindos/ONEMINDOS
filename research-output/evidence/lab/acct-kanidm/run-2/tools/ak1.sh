#!/bin/bash
# AK-1 host service. usage: ak1.sh pre|post   (pre: install + enable + start; post: after a reboot)
set -euo pipefail; T=AK-1; . /root/aklab/lib.sh
CHK='systemctl list-unit-files --no-legend | grep -E "k3s|containerd|docker|podman|crio" || echo "no k3s/container units"; for b in k3s kubectl docker podman containerd ctr crio runc; do command -v $b || true; done; echo "(no container binaries listed above = none installed)"'
if [ "$1" = pre ]; then
  stamp "AK-1 part 1: install and first start"
  run "grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release; cat /etc/debian_version; uname -rm; nproc; free -m | head -2"
  run "bash /root/aklab/setup2.sh deb /root/aklab/debs; bash /root/aklab/netns.sh"
  run "dpkg-query -W -f='\${Package} \${Version} \${Installed-Size}KiB\n' kanidmd kanidm"
  run "kanidmd version; kanidm version"
  run "systemctl cat kanidmd | grep -E '^(ExecStart|DynamicUser|StateDirectory|Type)='"
  run "systemctl enable --now kanidmd"
  run "for i in \$(seq 1 30); do systemctl is-active -q kanidmd && break; sleep 1; done; systemctl is-active kanidmd; systemctl is-enabled kanidmd"
  run "sleep 3; curl -sS --cacert /etc/kanidm/ca.pem https://idm.onemind.test:8443/status; echo"
  run "kanidmd scripting healthcheck -c /etc/kanidmd/server.toml"
  run "$CHK"
  T=AK-9; stamp "idle RSS after first start (30 s settle)"; sleep 30; run "rss"
else
  stamp "AK-1 part 2: after reboot"
  run "uptime -s; cat /proc/sys/kernel/random/boot_id; systemctl is-system-running || true"
  run "systemctl is-active kanidmd; systemctl is-enabled kanidmd; systemctl show kanidmd -p ActiveEnterTimestamp -p ExecMainStartTimestamp -p NRestarts"
  run "curl -sS --cacert /etc/kanidm/ca.pem https://idm.onemind.test:8443/status; echo"
  run "kanidmd scripting healthcheck -c /etc/kanidmd/server.toml"
  run "$CHK"
  run "systemd-analyze blame --no-pager | grep -E 'kanidmd|network-online|networking' || true"
fi
