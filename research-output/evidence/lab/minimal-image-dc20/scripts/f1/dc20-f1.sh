#!/bin/sh
# Test-only payload added to a COPY of each image (not part of the measured image).
# Results go to a file on disk (read back from the disk copy) and to the kernel log.
# Writing to /dev/ttyS0 directly fails once serial-getty takes the port (run 2 lost them).
OUTF=/var/log/dc20-f1.out; : > $OUTF
exec > $OUTF 2>&1
mark(){ echo "$*"; echo "$*" > /dev/kmsg; }
mark "DC20-F1 BEGIN $(uname -r) $(cat /etc/os-release | grep ^PRETTY_NAME)"
mark "DC20-F1 uptime-at-start $(cut -d' ' -f1 /proc/uptime)"
/usr/local/bin/k3s check-config 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | tee /var/log/dc20-check-config.txt | grep -E "STATUS|missing|fail" | head -40
mark "DC20-F1 check-config done"
/usr/local/bin/k3s server --write-kubeconfig-mode 644 --disable traefik,metrics-server,local-storage --disable-network-policy > /var/log/k3s-f1.log 2>&1 &
i=0
while [ $i -lt 900 ]; do
  if /usr/local/bin/k3s kubectl get node 2>/dev/null | grep -q " Ready "; then
    mark "DC20-F1 NODE-READY after ${i}s (uptime $(cut -d' ' -f1 /proc/uptime))"
    /usr/local/bin/k3s kubectl get node -o wide; free -m; break
  fi
  sleep 10; i=$((i+10))
done
[ $i -ge 900 ] && { mark "DC20-F1 NODE-NOT-READY after 900s"; tail -40 /var/log/k3s-f1.log; }
mark "DC20-F1 END"
sync; poweroff -f
