#!/bin/bash
# Runs INSIDE the VM as root. Deploys workload.yaml, loads 100k rows into PostgreSQL.
set -euo pipefail
K="k3s kubectl"
$K apply -f /tmp/kfr/workload.yaml | grep -v '^namespace' || true
$K -n kfr create secret generic kfr-secret --from-literal=pgpass="$(head -c 18 /dev/urandom | base64)" \
  --from-literal=marker="throwaway-$(head -c 6 /dev/urandom | od -An -tx1 | tr -d ' \n')" --dry-run=client -o yaml | $K apply -f -
$K -n kfr rollout status sts/pg --timeout=300s
$K -n kfr rollout status deploy/filler --timeout=300s
$K -n kfr rollout status deploy/writer --timeout=300s
until $K -n kfr exec pg-0 -- pg_isready -U postgres >/dev/null 2>&1; do sleep 2; done
$K -n kfr exec pg-0 -- psql -U postgres -qc "CREATE TABLE IF NOT EXISTS t(id int primary key, v text);
 INSERT INTO t SELECT g, md5(g::text) FROM generate_series(1,100000) g ON CONFLICT DO NOTHING; CHECKPOINT;"
echo workload-ready
