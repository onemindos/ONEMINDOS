#!/bin/bash
# Runs INSIDE the VM as root. Usage: guest-measure.sh LABEL [SECONDS]
# Prints memory, CPU (averaged over SECONDS) and disk footprint.
LABEL=$1; S=${2:-120}; HZ=$(getconf CLK_TCK); NCPU=$(nproc)
echo "===== $LABEL  $(date -u +%FT%TZ)  window=${S}s ncpu=$NCPU"
pidof_args() { pgrep -o -f "$1" || true; }
ticks() { [ -n "$1" ] && [ -r /proc/$1/stat ] && awk '{print $14+$15}' /proc/$1/stat || echo 0; }
K3S=$(pidof_args '^/usr/local/bin/k3s server'); CTD=$(pidof_args '^containerd ')
read -r _ u n s i w x y z _ < /proc/stat; T1=$((u+n+s+i+w+x+y+z)); I1=$((i+w))
K1=$(ticks "$K3S"); C1=$(ticks "$CTD")
sleep "$S"
read -r _ u n s i w x y z _ < /proc/stat; T2=$((u+n+s+i+w+x+y+z)); I2=$((i+w))
K2=$(ticks "$K3S"); C2=$(ticks "$CTD")
awk -v t=$((T2-T1)) -v id=$((I2-I1)) -v nc=$NCPU 'BEGIN{printf "cpu_system_busy_pct_of_one_core=%.1f\n", (t-id)/t*100*nc}'
awk -v d=$((K2-K1)) -v hz=$HZ -v s=$S 'BEGIN{printf "cpu_k3s_server_pct_of_one_core=%.1f\n", d/hz/s*100}'
awk -v d=$((C2-C1)) -v hz=$HZ -v s=$S 'BEGIN{printf "cpu_containerd_pct_of_one_core=%.1f\n", d/hz/s*100}'
MT=$(awk '/^MemTotal/{print $2}' /proc/meminfo); MA=$(awk '/^MemAvailable/{print $2}' /proc/meminfo)
echo "mem_total_mib=$((MT/1024)) mem_available_mib=$((MA/1024)) mem_used_mib=$(((MT-MA)/1024))"
grep -E '^(AnonPages|Cached|Shmem|SReclaimable|SUnreclaim):' /proc/meminfo | tr -s ' '
[ -n "$K3S" ] && echo "rss_k3s_server_mib=$(( $(awk '/VmRSS/{print $2}' /proc/$K3S/status)/1024 ))"
[ -n "$CTD" ] && echo "rss_containerd_mib=$(( $(awk '/VmRSS/{print $2}' /proc/$CTD/status)/1024 ))"
echo "rss_all_containerd_shims_mib=$(ps -eo rss,args | awk '/containerd-shim/ && !/awk/{s+=$1} END{print int(s/1024)}')"
for cg in /sys/fs/cgroup/system.slice/k3s.service /sys/fs/cgroup/kubepods /sys/fs/cgroup/kubepods.slice; do
  [ -r $cg/memory.current ] && echo "cgroup_mem_mib[$cg]=$(( $(cat $cg/memory.current)/1048576 ))"
done
echo "top_rss_processes (KiB):"; ps -eo rss,comm --sort=-rss | head -12
df -BM --output=used,size / | tail -1 | awk '{print "disk_root_used="$1" of "$2}'
for p in /usr/local/bin/k3s /var/lib/rancher/k3s /var/lib/rancher/k3s/agent/containerd /var/lib/rancher/k3s/data /var/lib/rancher/k3s/server/db /var/lib/rancher/k3s/storage; do
  [ -e $p ] && du -sm $p 2>/dev/null | awk '{print "du_mib["$2"]="$1}'
done
command -v k3s >/dev/null && k3s kubectl get pods -A --no-headers 2>/dev/null | awk '{c[$4]++} END{for(k in c) print "pods_"k"="c[k]}'
