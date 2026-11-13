# SPDX-License-Identifier: Apache-2.0
# Helpers for LAB-fb4-fleet-rings (inside the VM only).
. $(dirname "${BASH_SOURCE[0]}")/lib.sh
W=/opt/fb/fleet; KD=$W/kube; NET=fb4net; SUBNET=198.51.100.0/24
IMG=rancher/k3s:v1.37.2-k3s1; PIN_DIGEST=sha256:21ea6e0fac4e3930c2ce8aa40ddd41a8b18cb3e9a0222c030dc005e7e88c4332
SITES="box-1 site-b site-a"; declare -A RING=([box-1]=0 [site-b]=1 [site-a]=2) AGENTS=([hub]=0 [box-1]=0 [site-b]=0 [site-a]=1)
kc(){ local c=$1; shift; docker exec -i k3d-$c-server-0 kubectl "$@"; }
ip_of(){ docker inspect -f "{{(index .NetworkSettings.Networks \"$NET\").IPAddress}}" $1; }
st(){ local v d; v=$(kc $1 -n demo get cm demo-version -o jsonpath='{.data.version}' 2>/dev/null); [ -z "$v" ] && v=none
  d=$(kc $1 -n demo get deploy demo -o json 2>/dev/null | jq -r 'if (.status.updatedReplicas==1 and .status.availableReplicas==1 and ((.status.unavailableReplicas//0)==0) and .status.observedGeneration==.metadata.generation) then "ok" else "no" end' 2>/dev/null); [ -z "$d" ] && d=absent
  echo "$v|$d"; }
snap(){ local row="$(date -u +%FT%TZ)"; for s in $SITES; do row="$row,$s=$(st $s)"; done; echo "$row" | tee -a $R/poll.csv; }
