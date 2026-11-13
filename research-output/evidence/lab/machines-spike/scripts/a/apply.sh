#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-machines-spike option A: create one machine. apply.sh <name> <namespace>. Records the create time.
set -euo pipefail; source "$(dirname "$0")/../common.sh"
NAME=$1 NS=$2; URL="http://$(cat $W/nodeip):8099/fedora.qcow2"
kubectl get ns "$NS" >/dev/null 2>&1 || kubectl create ns "$NS"
UD=$(sed 's/^/            /' $W/user-data.yaml)
python3 - "$S/a/machine.yaml" "$NAME" "$NS" "$URL" "$UD" > $W/a-$NAME.yaml <<'PY'
import sys
t = open(sys.argv[1]).read()
for k, v in (("@NAME@", sys.argv[2]), ("@NS@", sys.argv[3]), ("@URL@", sys.argv[4]), ("@USERDATA@", sys.argv[5])):
    t = t.replace(k, v)
print(t)
PY
ts > $W/created-a-$NAME; kubectl apply -f $W/a-$NAME.yaml
echo "A $NAME in $NS created $(utc)"
