#!/bin/bash
# Runs INSIDE the disposable w4lab VM as root. See README.md for criteria.
set -u
K3S_VER="v1.37.2+k3s1"
NGINX=docker.io/library/nginx:1.29-alpine
REDIS=docker.io/library/redis:8-alpine
DISK=$(lsblk -ndo NAME,TYPE | awk '$2=="disk"{print $1; exit}')

ts(){ date -u +%H:%M:%S; }
memavail(){ awk '/MemAvailable/{printf "%.0f", $2/1024}' /proc/meminfo; }
wsect(){ awk -v d="$DISK" '$3==d{print $10}' /proc/diskstats; }
cpu(){ awk '/^cpu /{print $2+$3+$4+$6+$7+$8, $2+$3+$4+$5+$6+$7+$8}' /proc/stat; }
measure(){ # $1 label, $2 seconds
  local l=$1 s=$2
  sync; local w0; w0=$(wsect); read -r b0 t0 < <(cpu)
  sleep "$s"
  sync; local w1; w1=$(wsect); read -r b1 t1 < <(cpu)
  local mb=$(( (w1-w0)*512/1024/1024 ))
  local perday=$(awk -v b=$(( (w1-w0)*512 )) -v s="$s" 'BEGIN{printf "%.2f", b/s*86400/1e9}')
  local cpup=$(awk -v a=$((b1-b0)) -v t=$((t1-t0)) 'BEGIN{printf "%.1f", 100*a/t}')
  echo "RESULT $l memavail_mib=$(memavail) writes_mib_${s}s=$mb writes_gb_per_day=$perday cpu_pct_all_cores=$cpup"
  free -m | sed 's/^/  /'
}

echo "== $(ts) host: $(uname -r) $(nproc) cpu, disk=$DISK"; free -m
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq podman curl jq >/dev/null
podman --version
systemctl stop unattended-upgrades apt-daily.timer apt-daily-upgrade.timer 2>/dev/null
sleep 60
measure A_bare_os 600

echo "== $(ts) Podman reference app"
podman pull -q $NGINX >/dev/null; podman pull -q $REDIS >/dev/null
podman image inspect --format '{{.Name}} {{.Digest}}' $NGINX $REDIS 2>/dev/null || podman images --digests
podman run -d --name web -p 8080:80 $NGINX >/dev/null
podman run -d --name cache $REDIS >/dev/null
sleep 120
measure B_podman_app 600
podman rm -f web cache >/dev/null; podman rmi -a -f >/dev/null 2>&1

echo "== $(ts) k3s $K3S_VER install (binary + sha256)"
cd /root
U="https://github.com/k3s-io/k3s/releases/download/${K3S_VER//+/%2B}"
curl -sfL -o k3s-arm64 "$U/k3s-arm64"; curl -sfL -o sums.txt "$U/sha256sum-arm64.txt"
grep ' k3s-arm64$' sums.txt | sha256sum -c - || { echo "CHECKSUM FAIL"; exit 1; }
install -m 0755 k3s-arm64 /usr/local/bin/k3s
for c in kubectl crictl ctr; do ln -sf k3s /usr/local/bin/$c; done
mkdir -p /etc/rancher/k3s
cat >/etc/systemd/system/k3s.service <<'EOF'
[Unit]
Description=k3s
After=network-online.target
[Service]
Type=notify
ExecStart=/usr/local/bin/k3s server --write-kubeconfig-mode 644
KillMode=process
Delegate=yes
LimitNOFILE=1048576
Restart=always
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
t0=$(date +%s)
systemctl start k3s
until kubectl get nodes 2>/dev/null | grep -q ' Ready'; do sleep 1; done
t1=$(date +%s)
echo "RESULT C_k3s_node_ready_seconds=$((t1-t0))"
until [ "$(kubectl get pods -n kube-system --no-headers 2>/dev/null | wc -l)" -ge 5 ] && \
      ! kubectl get pods -n kube-system --no-headers 2>/dev/null | grep -v -E 'Running|Completed' | grep -q .; do sleep 2; done
t2=$(date +%s)
echo "RESULT C_k3s_kube_system_ready_seconds=$((t2-t0))"
kubectl get pods -A -o wide
sleep 180
measure C_k3s_default_idle 600
echo "k3s.service cgroup memory: $(( $(cat /sys/fs/cgroup/system.slice/k3s.service/memory.current)/1048576 )) MiB"
echo "kubepods cgroup memory: $(( $(cat /sys/fs/cgroup/kubepods.slice/memory.current 2>/dev/null || cat /sys/fs/cgroup/kubepods/memory.current)/1048576 )) MiB"
ps -o rss=,comm= -C k3s-server,k3s,containerd | sort -rn | head -5

echo "== $(ts) k3s + reference app"
kubectl create deployment web --image=$NGINX >/dev/null
kubectl create deployment cache --image=$REDIS >/dev/null
kubectl rollout status deploy/web --timeout=300s; kubectl rollout status deploy/cache --timeout=300s
sleep 120
measure D_k3s_default_app 600
echo "k3s.service cgroup memory: $(( $(cat /sys/fs/cgroup/system.slice/k3s.service/memory.current)/1048576 )) MiB"

echo "== $(ts) k3s slim (disable traefik,servicelb,metrics-server) + app"
sed -i 's#--write-kubeconfig-mode 644#--write-kubeconfig-mode 644 --disable=traefik,servicelb,metrics-server#' /etc/systemd/system/k3s.service
systemctl daemon-reload; systemctl restart k3s
until kubectl get nodes 2>/dev/null | grep -q ' Ready'; do sleep 1; done
sleep 240
kubectl get pods -A
measure E_k3s_slim_app 600
echo "k3s.service cgroup memory: $(( $(cat /sys/fs/cgroup/system.slice/k3s.service/memory.current)/1048576 )) MiB"
du -sh /var/lib/rancher/k3s/server/db 2>/dev/null
echo "== $(ts) done"
