export KUBECONFIG=/etc/rancher/k3s/k3s.yaml; S=<home>/<lab-dir>/w5-restore/shared
for i in $(seq 1 90); do m=$(k3s kubectl -n demo exec writer -- cat /data/marker.txt 2>/dev/null) && [ -n "$m" ] && break; sleep 2; done
echo "[$(date -u +%FT%TZ)] host=$(hostname) after ${i}x2s: marker=$m expected=$(cat $S/marker.expected)"
k3s kubectl -n demo get pod writer -o wide
