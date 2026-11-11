#!/bin/bash
# greenboot REQUIRED check: the OS update is only "good" when k3s API is ready, the node is Ready and CoreDNS is available.
# Waits up to 300 s (k3s cold start on first boot pulls images).
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
for i in $(seq 1 60); do
  if /usr/bin/k3s kubectl get --raw=/readyz >/dev/null 2>&1 \
     && /usr/bin/k3s kubectl get nodes --no-headers 2>/dev/null | grep -q ' Ready' \
     && /usr/bin/k3s kubectl -n kube-system get deploy coredns -o jsonpath='{.status.availableReplicas}' 2>/dev/null | grep -q '^[1-9]'; then
    echo "k3s healthy after $((i*5))s"; exit 0
  fi
  sleep 5
done
echo "k3s NOT healthy after 300s"; exit 1
