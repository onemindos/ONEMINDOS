#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-machines-spike option B: create one machine. apply.sh <name> <namespace>. Records the create time.
set -euo pipefail; source "$(dirname "$0")/../common.sh"
NAME=$1 NS=$2; ACCEL=$(cat $W/accel); PRIV=$(cat $W/b-privileged 2>/dev/null || echo false)
kubectl get ns "$NS" >/dev/null 2>&1 || kubectl create ns "$NS"
sed -e "s/@NAME@/$NAME/g" -e "s/@NS@/$NS/g" -e "s/@ACCEL@/$ACCEL/g" -e "s/@PRIV@/$PRIV/g" "$S/b/machine.yaml" > $W/b-$NAME.yaml
ts > $W/created-b-$NAME; kubectl apply -f $W/b-$NAME.yaml
echo "B $NAME in $NS: accel=$ACCEL privileged=$PRIV created $(utc)"
