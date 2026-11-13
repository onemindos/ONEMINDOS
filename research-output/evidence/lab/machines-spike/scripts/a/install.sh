#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-machines-spike option A: install KubeVirt + CDI from the verified release manifests (E3 timing).
set -euo pipefail; source "$(dirname "$0")/../common.sh"
exec > >(tee -a "$OUT/a-install.log") 2>&1
t0=$(ts); echo "install start $(utc)"
kubectl apply -f $W/dl/kubevirt-operator.yaml
kubectl -n kubevirt wait deploy virt-operator --for condition=Available --timeout=15m
kubectl apply -f $W/dl/kubevirt-cr.yaml
if [ "$(cat $W/accel)" = tcg ]; then
  kubectl -n kubevirt patch kubevirt kubevirt --type merge -p '{"spec":{"configuration":{"developerConfiguration":{"useEmulation":true}}}}'; fi
kubectl apply -f $W/dl/cdi-operator.yaml
kubectl -n cdi wait deploy cdi-operator --for condition=Available --timeout=15m
kubectl apply -f $W/dl/cdi-cr.yaml
kubectl -n kubevirt wait kv kubevirt --for condition=Available --timeout=20m
kubectl wait cdi cdi --for condition=Available --timeout=20m
echo "E3 install_ready_s $(python3 -c "print(round($(ts)-$t0))") $(utc)"
kubectl get pods -n kubevirt; kubectl get pods -n cdi
kubectl get nodes -o jsonpath='{.items[0].status.allocatable}'; echo
kubectl get nodes -o json | jq '.items[0].metadata.labels | with_entries(select(.key|test("kubevirt")))'
