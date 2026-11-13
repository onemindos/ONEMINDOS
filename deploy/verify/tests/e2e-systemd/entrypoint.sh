#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# PID 1 of the e2e "machine" container, before systemd. Under cgroup v2 a cgroup that holds
# processes cannot hand controllers to its children, and `docker exec` puts its processes in the
# container's root cgroup: a long `docker exec install.sh` then keeps k3s's kubelet from getting the
# cpu/memory/pids controllers ("kubepods has some missing controllers"). Same fix as kind and k3d:
# move PID 1 into a leaf cgroup and enable every controller for the children first; runc then puts
# later `docker exec` processes into a child cgroup too. A real machine needs none of this.
if [ -f /sys/fs/cgroup/cgroup.controllers ]; then
  mkdir -p /sys/fs/cgroup/init.scope
  echo $$ > /sys/fs/cgroup/init.scope/cgroup.procs
  read -r controllers < /sys/fs/cgroup/cgroup.controllers
  for c in $controllers; do
    echo "+$c" > /sys/fs/cgroup/cgroup.subtree_control 2>/dev/null || true
  done
fi
exec /sbin/init
