#!/bin/bash
# Runs INSIDE the VM as root. API churn plus DB writes for $1 seconds (load phase of the footprint test).
END=$(( $(date +%s) + ${1:-120} )); i=0
while [ "$(date +%s)" -lt "$END" ]; do
  i=$((i+1)); k3s kubectl -n kfr create configmap churn-$i --from-literal=a=$i >/dev/null 2>&1
  k3s kubectl -n kfr delete configmap churn-$i --wait=false >/dev/null 2>&1
  [ $((i % 10)) -eq 0 ] && k3s kubectl -n kfr exec pg-0 -- psql -U postgres -qc "UPDATE t SET v=md5(v) WHERE id % 97 = $((i % 97));" >/dev/null 2>&1
done; echo "churn_iterations=$i"
