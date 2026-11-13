#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-machines-spike option A: uninstall CDI + KubeVirt in the documented order, then list leftovers (E3).
set -uo pipefail; source "$(dirname "$0")/../common.sh"
exec > >(tee -a "$OUT/a-remove.log") 2>&1
t0=$(ts); echo "remove start $(utc)"
kubectl delete -f $W/dl/cdi-cr.yaml --wait --timeout=10m
kubectl delete -f $W/dl/cdi-operator.yaml --wait --timeout=10m
kubectl -n kubevirt delete kubevirt kubevirt --wait --timeout=10m
kubectl delete -f $W/dl/kubevirt-operator.yaml --wait --timeout=10m
echo "E3 remove_s $(python3 -c "print(round($(ts)-$t0))")"
sleep 30
echo "== leftovers (empty sections mean none)"
echo "-- crds"; kubectl get crd -o name | grep -iE 'kubevirt|cdi' || true
echo "-- webhooks"; kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations -o name | grep -iE 'virt|cdi' || true
echo "-- apiservices"; kubectl get apiservices -o name | grep -iE 'kubevirt|cdi' || true
echo "-- namespaces"; kubectl get ns -o name | grep -E 'kubevirt|cdi' || true
echo "-- pods"; kubectl get pods -A --no-headers | grep -E 'virt-|cdi-' || true
echo "-- clusterroles/bindings"; kubectl get clusterroles,clusterrolebindings -o name | grep -iE 'kubevirt|cdi' || true
echo "-- node labels"; kubectl get nodes -o json | jq -c '.items[0].metadata.labels | with_entries(select(.key|test("kubevirt|cdi")))'
echo "-- node allocatable devices"; kubectl get nodes -o json | jq -c '.items[0].status.allocatable | with_entries(select(.key|test("kubevirt")))'
echo "-- host paths"; ls -d /var/run/kubevirt* /var/lib/kubevirt* /var/run/kubevirt-private 2>/dev/null || true
