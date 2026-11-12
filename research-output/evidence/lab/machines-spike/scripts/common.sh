# shellcheck shell=bash disable=SC2034
# SPDX-License-Identifier: Apache-2.0
# LAB-machines-spike: helpers sourced by the step scripts (root, inside the lab VM only).
LAB=${LAB:?"set LAB to <lab-dir>/machines-spike"}; OUT=$LAB/run; S=$LAB/scripts; W=/opt/machlab
KEY=$W/ssh/id_ed25519
SSHO=(-i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -o LogLevel=ERROR -o BatchMode=yes)
ts(){ date +%s.%N; }
utc(){ date -u +%FT%TZ; }
podname(){ # opt ns machine -> the pod that runs the machine
  case $1 in a) kubectl -n "$2" get pod -l "vm.kubevirt.io/name=$3" -o jsonpath='{.items[0].metadata.name}';;
             b) kubectl -n "$2" get pod -l "app=$3" -o jsonpath='{.items[0].metadata.name}';; esac; }
endpoint(){ # opt ns machine -> "ip port" for SSH into the guest
  local ip; ip=$(kubectl -n "$2" get pod "$(podname "$@")" -o jsonpath='{.status.podIP}')
  case $1 in a) echo "$ip 22";; b) echo "$ip 2222";; esac; }
gssh(){ local ep; read -r -a ep <<<"$(endpoint "$1" "$2" "$3")"; shift 3; ssh "${SSHO[@]}" -p "${ep[1]}" "lab@${ep[0]}" "$@"; }
agent_ok(){
  case $1 in
    a) [ "$(kubectl -n "$2" get vmi "$3" -o jsonpath='{.status.conditions[?(@.type=="AgentConnected")].status}' 2>/dev/null)" = True ];;
    b) kubectl -n "$2" exec "deploy/$3" -c qemu -- env QGA_TIMEOUT=5 qga.py guest-ping 2>/dev/null | grep -q '"return": {}';;
  esac; }
SUB=/apis/subresources.kubevirt.io/v1/namespaces
freeze(){ case $1 in
  a) echo "{\"unfreezeTimeout\":\"${UNFREEZE:-5m}\"}" | kubectl replace --raw "$SUB/$2/virtualmachineinstances/$3/freeze" -f -;;
  b) kubectl -n "$2" exec "deploy/$3" -c qemu -- qga.py guest-fsfreeze-freeze;; esac; }
thaw(){ case $1 in
  a) echo '{}' | kubectl replace --raw "$SUB/$2/virtualmachineinstances/$3/unfreeze" -f -;;
  b) kubectl -n "$2" exec "deploy/$3" -c qemu -- qga.py guest-fsfreeze-thaw;; esac; }
fstatus(){ case $1 in # prints frozen / thawed
  a) s=$(kubectl -n "$2" get vmi "$3" -o jsonpath='{.status.fsFreezeStatus}'); echo "${s:-thawed}";;
  b) kubectl -n "$2" exec "deploy/$3" -c qemu -- qga.py guest-fsfreeze-status | python3 -c 'import json,sys;print(json.load(sys.stdin)["return"])';; esac; }
diskdir(){ local pv; pv=$(kubectl -n "$1" get pvc "$2" -o jsonpath='{.spec.volumeName}')
  kubectl get pv "$pv" -o jsonpath='{.spec.local.path}{.spec.hostPath.path}'; }
podcg(){ python3 - "$(kubectl -n "$1" get pod "$2" -o jsonpath='{.metadata.uid}')" <<'PY'
import os, sys
uid = sys.argv[1]; want = (f"pod{uid}", f"pod{uid.replace('-', '_')}.slice")
for root, dirs, _ in os.walk("/sys/fs/cgroup"):
    hit = [d for d in dirs if d.endswith(want)]
    if hit: print(os.path.join(root, hit[0])); break
    dirs[:] = [d for d in dirs if d.startswith("kubepods")]
PY
}
nqemu(){ ps -eo comm= | grep -c '^qemu' || true; }
