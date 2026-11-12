#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Full run, in the pre-registered order of setup; writes logs under out/run-$1/.
set -uo pipefail; S=$(cd "$(dirname "$0")" && pwd); RUN=${1:?run id}
. $S/lib.sh; O=$OUT/run-$RUN; mkdir -p $O; rm -rf $R/res $R/mesh $R/nats-t $R/t5 $R/e2
{
log "== run $RUN start"; uname -srm; nproc; free -m | head -2
$S/net-up.sh && $S/mesh-up.sh && $S/nats-up.sh || { log "setup failed"; exit 1; }
F=$OUT/../fetch.log; PINS=$(grep -c "sha256 OK pin" $F); UPF=$(grep -c "sha256 OK upstream-file" $F); FAILS=$(grep -c "T0 FAIL" $F)
VERS=$(grep -A12 "== versions" $F | grep -vE "^\s+(path|mod)|^[0-9a-f]{64}" | tr '\n' ';')
[[ $PINS -eq 5 && $UPF -eq 4 && $FAILS -eq 0 && $VERS == *"go1.27.4"*"v0.29.7"*"1.104.6"*"v2.15.2"*"0.5.1"* ]] && V=PASS || V=FAIL
res T0 $V "$(jq -n --argjson p $PINS --argjson u $UPF --arg v "$VERS" --arg d "$(sha256sum $B/derper | cut -c1-64)" '{pinned_hash_matches:$p,upstream_checksum_file_matches:$u,versions:$v,derper_built_sha256:$d}')"
# T1a verdict from mesh-up evidence
NODES=$(jq -c '[.[]|{n:.given_name,o:.online,t:(.tags // .forced_tags)}]' $R/nodes.json)
ONL=$(jq '[.[]|select(.online==true)]|length' $R/nodes.json); REUSE=$(cat $R/t1a-reuse.result)
SINGLE=$(jq '[.[]|select((.reusable // false)==false and .used==true)]|length' $R/preauthkeys.json)
[[ $ONL -eq 3 && $REUSE == refused && $SINGLE -eq 3 ]] && V=PASS || V=FAIL
res T1a $V "$(jq -n --argjson n "$NODES" --arg r "$REUSE" --argjson s $SINGLE --arg why "$(tail -1 $R/t1a-reuse.log)" '{nodes:$n,reused_key:$r,reuse_error:$why,single_use_keys_used:$s}')"
$S/mesh-tests.sh
$S/nats-tests.sh
$S/footprint.sh | tail -1
$S/nats-outage.sh | tail -1
$S/e2-leaf-perms.sh
log "== run $RUN end"
} 2>&1 | tee $O/run.log
python3 -I $S/summarize.py $R $O/results.json | tee -a $O/run.log
cp -r $R/res $R/mesh $R/nats-t $R/t5 $R/e2 $R/nodes.json $O/ 2>/dev/null
jq 'map(del(.key))' $R/preauthkeys.json > $O/preauthkeys-redacted.json
for f in headscale derper tailscaled natshub; do cp $R/cloud-$f.log $O/ 2>/dev/null; done
for n in home-a home-b; do cp $R/$n-tailscaled.log $R/$n-natsleaf.log $O/ 2>/dev/null; done
cp $R/hs/policy.hujson $R/hs/derp.yaml $O/; sed -E 's/(password: )"[0-9a-f]{32}"/\1"<generated-at-run-time>"/' $R/nats/hub.conf > $O/hub.conf.masked
