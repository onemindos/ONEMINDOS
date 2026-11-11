#!/bin/bash
# Runs INSIDE the VM as root. Prints the state fingerprint compared before backup and after restore.
K="k3s kubectl"
echo "node=$($K get node omos-box --no-headers 2>/dev/null | awk '{print $2}')"
$K get nodes --no-headers | awk '{print "node_list="$1":"$2}'
for d in deploy/filler deploy/writer sts/pg; do echo "$d ready=$($K -n kfr get $d -o jsonpath='{.status.readyReplicas}/{.spec.replicas}')"; done
echo "pg_rows=$($K -n kfr exec pg-0 -- psql -U postgres -tAc 'select count(*) from t' 2>/dev/null)"
echo "pg_md5=$($K -n kfr exec pg-0 -- psql -U postgres -tAc "select md5(string_agg(id||':'||v, ',' order by id)) from t" 2>/dev/null)"
echo "configmap=$($K -n kfr get cm kfr-config -o jsonpath='{.data.marker}')"
echo "secret_marker_sha256=$($K -n kfr get secret kfr-secret -o jsonpath='{.data.marker}' | base64 -d | sha256sum | cut -c1-16)"
W=$($K -n kfr get pod -l app=writer -o jsonpath='{.items[0].metadata.name}')
echo "blob_sha256=$($K -n kfr exec "$W" -- sha256sum /data/blob 2>/dev/null | cut -c1-16)"
