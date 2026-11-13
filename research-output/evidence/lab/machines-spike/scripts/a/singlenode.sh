#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-machines-spike option A: the single-node settings that M5 judges (pre-registered in README §4.2).
set -euo pipefail
kubectl -n kubevirt patch kubevirt kubevirt --type merge -p '{"spec":{"infra":{"replicas":1}}}'
kubectl -n kubevirt scale deploy virt-operator --replicas=1
for _ in $(seq 1 60); do
  n=$(kubectl -n kubevirt get pods --no-headers 2>/dev/null | grep -cE '^virt-(api|controller|operator)-' || true)
  [ "$n" = 3 ] && kubectl -n kubevirt wait kv kubevirt --for condition=Available --timeout=10s >/dev/null 2>&1 && break; sleep 10; done
kubectl -n kubevirt get pods -o wide | sed -E 's/([0-9]+\.){3}[0-9]+/<ip>/g'
