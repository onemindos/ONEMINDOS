#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-fb4-fleet-rings T1-T6 and E1-E4 (after fleet-up.sh).
set -uo pipefail; S=$(cd "$(dirname "$0")" && pwd); . $S/fleet-lib.sh
RUN=${1:?run id}; R=$OUT/fleet-run-$RUN; RS=$R/res; mkdir -p $RS; exec > >(tee $R/tests.log) 2>&1
HUBIP=$(cat $W/hubip); T1START=$(cat $W/t1start)
mask(){ sed -e "s/$HUBIP/<hub-ip>/g" -e 's/10\.4[23]\.[0-9]*\.[0-9]*/<pod-ip>/g'; }
clusters(){ kc hub -n fleet-default get clusters.fleet.cattle.io -o json | jq -c '[.items[]|{site:.metadata.labels.site,ring:.metadata.labels.ring,ready:((.status.conditions//[])|map(select(.type=="Ready"))|.[0].status)}]'; }
# ---- T1
for i in $(seq 180); do C=$(clusters); [ "$(echo "$C" | jq '[.[]|select(.ready=="True")]|length')" = 3 ] && break; sleep 5; done
T1SEC=$(( $(date +%s)-T1START )); C=$(clusters); NREADY=$(echo "$C" | jq '[.[]|select(.ready=="True")]|length')
DROPS=$(iptables -L DOCKER-USER -n -v -x | awk '/fb4 hub->/{s+=$1} END{print s+0}'); SEEN=$(iptables -L DOCKER-USER -n -v -x | awk '/site->hub api/{print $1}')
[[ $NREADY -eq 3 && $T1SEC -le 900 && $DROPS -eq 0 ]] && V=PASS || V=FAIL
res $RS T1 $V "$(jq -n --argjson c "$C" --argjson s $T1SEC --argjson d $DROPS --argjson n ${SEEN:-0} '{clusters:$c,seconds_to_ready:$s,hub_to_site_new_conn_dropped_pkts:$d,site_to_hub_api_new_conns_counted:$n}')"
# ---- bundle versions, produced with the pinned fleet CLI
mkbundle(){ local v=$1 img=$2 d=$W/bundles/$1; mkdir -p $d
  cat > $d/fleet.yaml <<Y
defaultNamespace: demo
rolloutStrategy:
  maxUnavailable: 0
  maxUnavailablePartitions: 0
  partitions:
    - {name: ring0, clusterSelector: {matchLabels: {ring: "0"}}}
    - {name: ring1, clusterSelector: {matchLabels: {ring: "1"}}}
    - {name: ring2, clusterSelector: {matchLabels: {ring: "2"}}}
Y
  cat > $d/demo.yaml <<Y
apiVersion: v1
kind: ConfigMap
metadata: {name: demo-version}
data: {version: "$v"}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: demo}
spec:
  replicas: 1
  progressDeadlineSeconds: 120
  selector: {matchLabels: {app: demo}}
  template:
    metadata: {labels: {app: demo}, annotations: {fb4/version: "$v"}}
    spec:
      containers:
        - name: demo
          image: $img
          resources: {requests: {cpu: 1m, memory: 8Mi}, limits: {memory: 32Mi}}
Y
  printf 'targets:\n- clusterSelector:\n    matchLabels:\n      fb4: "yes"\n' > $W/bundles/targets.yaml
  (cd $d && fleet apply -n fleet-default -o $W/bundles/$v.bundle.yaml --targets-file $W/bundles/targets.yaml demo . ) || return 1
  cp $W/bundles/$v.bundle.yaml $R/bundle-$v.yaml; }
apply(){ log "APPLY $1"; kc hub apply -f - < $W/bundles/$1.bundle.yaml; }
PAUSE=$(docker exec k3d-box-1-server-0 crictl images 2>/dev/null | awk '/pause/{print $1":"$2; exit}')
echo "pause image on nodes: $PAUSE"; BAD=${PAUSE%%:*}:fb4-does-not-exist
for v in v1 v3 v4; do mkbundle $v $PAUSE; done; mkbundle v2-bad $BAD
ls $W/bundles; head -40 $W/bundles/v1.bundle.yaml
waitall(){ local want=$1 lim=$2 t0=$(date +%s); while :; do local row=$(snap); local n=0; for s in $SITES; do [[ $row == *"$s=$want|ok"* ]] && n=$((n+1)); done
  [ $n -eq 3 ] && { echo $(( $(date +%s)-t0 )); return 0; }; [ $(( $(date +%s)-t0 )) -ge $lim ] && { echo -1; return 1; }; sleep 15; done; }
# ---- T2
apply v1; S2=$(waitall v1 900 | tail -1); [[ $S2 -ge 0 ]] && V=PASS || V=FAIL
res $RS T2 $V "$(jq -n --argjson s $S2 --arg last "$(tail -1 $R/poll.csv)" '{seconds_all_v1_available:$s,last_poll:$last}')"
# ---- T3
apply v2-bad; t0=$(date +%s); GOT=-1
while [ $(( $(date +%s)-t0 )) -lt 900 ]; do row=$(snap); [[ $row == *"box-1=v2-bad"* ]] && { GOT=$(( $(date +%s)-t0 )); break; }; sleep 15; done
LEAK=0; t1=$(date +%s); if [ $GOT -ge 0 ]; then while [ $(( $(date +%s)-t1 )) -lt 600 ]; do row=$(snap)
  [[ $row == *"site-b=v2-bad"* || $row == *"site-a=v2-bad"* ]] && LEAK=1; sleep 15; done; fi
B1=$(st box-1); [[ $GOT -ge 0 && $LEAK -eq 0 && $B1 == "v2-bad|no" ]] && V=PASS || V=FAIL
BST=$(kc hub -n fleet-default get bundle demo -o json | jq -c '.status.summary // {}')
res $RS T3 $V "$(jq -n --argjson g $GOT --argjson l $LEAK --arg b "$B1" --argjson bs "$BST" '{seconds_until_box1_shows_v2bad:$g,later_ring_received_v2bad:($l==1),box1_after_10min:$b,bundle_summary:$bs}')"
# ---- T4
apply v1; t0=$(date +%s); OK4=-1; LEAK=0
while [ $(( $(date +%s)-t0 )) -lt 600 ]; do row=$(snap); [[ $row == *"site-b=v2-bad"* || $row == *"site-a=v2-bad"* ]] && LEAK=1
  [[ $row == *"box-1=v1|ok"* ]] && { OK4=$(( $(date +%s)-t0 )); break; }; sleep 15; done
[[ $OK4 -ge 0 && $LEAK -eq 0 ]] && V=PASS || V=FAIL
res $RS T4 $V "$(jq -n --argjson s $OK4 --argjson l $LEAK '{seconds_box1_back_on_v1:$s,later_ring_touched:($l==1)}')"
# ---- T5 ring order
apply v3; t0=$(date +%s); declare -A F3 O3; for s in $SITES; do F3[$s]=-1; O3[$s]=-1; done
while [ $(( $(date +%s)-t0 )) -lt 1200 ]; do row=$(snap); e=$(( $(date +%s)-t0 ))
  for s in $SITES; do [[ ${F3[$s]} -lt 0 && $row == *"$s=v3|"* ]] && F3[$s]=$e; [[ ${O3[$s]} -lt 0 && $row == *"$s=v3|ok"* ]] && O3[$s]=$e; done
  [[ ${O3[box-1]} -ge 0 && ${O3[site-b]} -ge 0 && ${O3[site-a]} -ge 0 ]] && break; sleep 15; done
ALL=$([[ ${O3[box-1]} -ge 0 && ${O3[site-b]} -ge 0 && ${O3[site-a]} -ge 0 ]] && echo 1 || echo 0)
ORD=$([[ ${F3[site-b]} -ge ${O3[box-1]} && ${F3[site-a]} -ge ${O3[site-b]} && ${F3[box-1]} -le ${F3[site-b]} && ${F3[site-b]} -le ${F3[site-a]} ]] && echo 1 || echo 0)
[[ $ALL -eq 1 && $ORD -eq 1 ]] && V=PASS || V=FAIL
res $RS T5 $V "$(jq -n --argjson a ${F3[box-1]} --argjson b ${F3[site-b]} --argjson c ${F3[site-a]} --argjson oa ${O3[box-1]} --argjson ob ${O3[site-b]} --argjson oc ${O3[site-a]} '{first_seen_v3_s:{"box-1":$a,"site-b":$b,"site-a":$c},first_available_v3_s:{"box-1":$oa,"site-b":$ob,"site-a":$oc}}')"
# ---- T6 partition (E1 recorded during the outage)
log "STOP site-b"; k3d cluster stop site-b 2>&1 | tail -1; apply v4; t0=$(date +%s); A4=-1
while [ $(( $(date +%s)-t0 )) -lt 300 ]; do row="$(date -u +%FT%TZ),box-1=$(st box-1),site-b=offline,site-a=$(st site-a)"; echo "$row" | tee -a $R/poll.csv
  [[ $A4 -lt 0 && $row == *"site-a=v4"* ]] && A4=$(( $(date +%s)-t0 )); sleep 15; done
CL6=$(clusters); log "START site-b"; k3d cluster start site-b 2>&1 | tail -1; t1=$(date +%s); S6=$(waitall v4 900 | tail -1)
[[ $S6 -ge 0 ]] && V=PASS || V=FAIL
res $RS T6 $V "$(jq -n --argjson s $S6 '{seconds_after_restart_all_v4_available:$s}')"
res $RS E1 OBS "$(jq -n --argjson a $A4 --argjson c "$CL6" '{site_a_got_v4_while_site_b_offline_after_s:$a,clusters_during_outage:$c}')"
# ---- E2 footprint
for c in hub box-1 site-b site-a; do docker exec k3d-$c-server-0 crictl stats -o json 2>/dev/null | jq -c --arg c $c '[.stats[]|{c:$c,name:.attributes.labels["io.kubernetes.container.name"],pod:.attributes.labels["io.kubernetes.pod.name"],ns:.attributes.labels["io.kubernetes.pod.namespace"],mem_mib:(((.memory.workingSetBytes.value // "0")|tonumber)/1048576|floor)}]|map(select(.ns=="cattle-fleet-system" or .ns=="cattle-fleet-local-system"))'; done | jq -s 'add' > $RS/e2-raw.json
docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' | tee $R/docker-stats.txt
res $RS E2 OBS "$(jq -c . $RS/e2-raw.json)"
# ---- E3 drift
kc site-a -n demo delete cm demo-version; t0=$(date +%s); BACK=-1
while [ $(( $(date +%s)-t0 )) -lt 300 ]; do [[ $(st site-a) == v4* ]] && { BACK=$(( $(date +%s)-t0 )); break; }; sleep 15; done
res $RS E3 OBS "$(jq -n --argjson b $BACK '{seconds_until_deleted_configmap_restored:$b,note:"-1 = not restored within 300 s"}')"
# ---- E4 what the hub sees
kc hub -n fleet-default get bundle demo -o json | jq '{summary:.status.summary,display:.status.display,partitions:.status.partitions}' > $RS/e4-bundle.json
kc hub -n fleet-default get clusters.fleet.cattle.io -o json | jq '[.items[]|{site:.metadata.labels.site,display:.status.display,summary:.status.summary,agentLastSeen:.status.agent.lastSeen}]' > $RS/e4-clusters.json
res $RS E4 OBS "$(jq -n --slurpfile b $RS/e4-bundle.json --slurpfile c $RS/e4-clusters.json '{bundle:$b[0],clusters:$c[0]}')"
iptables -L DOCKER-USER -n -v -x | mask > $R/docker-user-final.txt
jq -s '{spike:"fb4-fleet-rings",run:"'$RUN'",verdict:(if ([.[]|select(.id|test("^T"))|.verdict]|all(.=="PASS")) then "PASS" else "FAIL" end),results:.}' $RS/T*.json $RS/E1.json $RS/E2.json $RS/E3.json $RS/E4.json > $R/results.json
jq -r '.verdict, (.results[]|"\(.id) \(.verdict)")' $R/results.json; log "== fleet tests $RUN end"
