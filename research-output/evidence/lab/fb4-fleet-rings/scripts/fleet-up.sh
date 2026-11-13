#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-fb4-fleet-rings setup: Docker, k3d clusters on a documentation-range network, Fleet manager on hub,
# hub->site NEW-connection drop rule, agent-initiated registration of three downstream clusters.
set -uo pipefail; S=$(cd "$(dirname "$0")" && pwd); . $S/fleet-lib.sh
RUN=${1:?run id}; R=$OUT/fleet-run-$RUN; mkdir -p $R/res $KD; exec > >(tee $R/up.log) 2>&1
log "== fleet setup $RUN"
for c in hub box-1 site-b site-a; do k3d cluster delete $c >/dev/null 2>&1; done; docker network rm $NET >/dev/null 2>&1
iptables -S DOCKER-USER | grep fb4 | sed 's/^-A/iptables -D/' | sh
systemctl enable --now docker >/dev/null 2>&1; modprobe br_netfilter; sysctl -w net.bridge.bridge-nf-call-iptables=1
docker network inspect $NET >/dev/null 2>&1 || docker network create --subnet $SUBNET --gateway ${SUBNET%0/24}1 $NET   # k3d needs a gateway on the network
docker pull -q $IMG; GOT=$(docker image inspect $IMG -f '{{join .RepoDigests " "}}'); echo "k3s image RepoDigests: $GOT"
[[ $GOT == *"$PIN_DIGEST"* ]] && echo "k3s image digest matches os/versions.lock.yaml pin" || echo "k3s image digest DIFFERS from pin $PIN_DIGEST"
K3S=(--k3s-arg "--disable=traefik@server:*" --k3s-arg "--disable=servicelb@server:*" --k3s-arg "--disable=local-storage@server:*" --k3s-arg "--disable=metrics-server@server:*")
for c in hub box-1 site-b site-a; do
  t0=$(date +%s); k3d cluster create $c --image $IMG --network $NET --no-lb --servers 1 --agents ${AGENTS[$c]} "${K3S[@]}" \
    --kubeconfig-update-default=false --kubeconfig-switch-context=false --wait --timeout 900s > $R/k3d-create-$c.log 2>&1 || { tail -5 $R/k3d-create-$c.log; log "cluster $c FAILED"; exit 1; }
  k3d kubeconfig get $c > $KD/$c.yaml; log "cluster $c created in $(( $(date +%s)-t0 )) s"; free -m | sed -n 2p
done
HUBIP=$(ip_of k3d-hub-server-0); echo "$HUBIP" > $W/hubip
docker exec k3d-hub-server-0 cat /var/lib/rancher/k3s/server/tls/server-ca.crt > $W/hub-ca.pem
helm show values $B/dl/fleet-0.16.3.tgz > $R/fleet-chart-values.yaml; grep -n -E '^apiServer(URL|CA)' $R/fleet-chart-values.yaml
helm --kubeconfig $KD/hub.yaml install fleet-crd $B/dl/fleet-crd-0.16.3.tgz -n cattle-fleet-system --create-namespace --wait 2>&1 | tail -1
t0=$(date +%s); helm --kubeconfig $KD/hub.yaml install fleet $B/dl/fleet-0.16.3.tgz -n cattle-fleet-system --wait --timeout 20m \
  --set apiServerURL=https://$HUBIP:6443 --set-file apiServerCA=$W/hub-ca.pem 2>&1 | tail -2; log "fleet manager installed in $(( $(date +%s)-t0 )) s"
kc hub -n cattle-fleet-system get pods -o wide | sed "s/$HUBIP/<hub-ip>/g"
# T1: hub must never open a connection to a site; count site->hub API connections as proof the rule sees bridged traffic
for s in $SITES; do for n in $(docker ps --format '{{.Names}}' | grep "^k3d-$s-"); do ip=$(ip_of $n)
  iptables -I DOCKER-USER 1 -s $HUBIP -d $ip -m conntrack --ctstate NEW -m comment --comment "fb4 hub->$n" -j DROP; done; done
iptables -I DOCKER-USER 1 -s $SUBNET -d $HUBIP -p tcp --dport 6443 -m conntrack --ctstate NEW -m comment --comment "fb4 site->hub api (count)" -j RETURN
iptables -L DOCKER-USER -n -v -x | sed "s/$HUBIP/<hub-ip>/g"
kc hub create namespace fleet-default   # standalone Fleet: the registration namespace is created by the operator (docs use 'clusters')
kc hub apply -f - <<Y
kind: ClusterRegistrationToken
apiVersion: fleet.cattle.io/v1alpha1
metadata: {name: fb4-token, namespace: fleet-default}
spec: {ttl: 4h}
Y
for i in $(seq 120); do kc hub -n fleet-default get secret fb4-token >/dev/null 2>&1 && break; sleep 5; done
kc hub -n fleet-default get secret fb4-token -o jsonpath='{.data.values}' | base64 -d > $W/agent-values.yaml
echo "agent values keys: $(grep -oE '^[a-zA-Z]+' $W/agent-values.yaml | tr '\n' ' ')"
T1START=$(date +%s); echo $T1START > $W/t1start
for s in $SITES; do t0=$(date +%s)
  helm --kubeconfig $KD/$s.yaml install fleet-agent $B/dl/fleet-agent-0.16.3.tgz -n cattle-fleet-system --create-namespace \
    --values $W/agent-values.yaml --set-string labels.ring=${RING[$s]} --set-string labels.fb4=yes --set-string labels.site=$s 2>&1 | tail -1
  log "agent on $s installed in $(( $(date +%s)-t0 )) s"; done
log "== fleet setup $RUN end"
