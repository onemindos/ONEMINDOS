# SPDX-License-Identifier: Apache-2.0
# Phase 6: storage.mirror.replace of member $1 by blank disk $2 (action id $3), with a power cut in the
# middle of btrfs replace.
. ./common.sh
body=$(jq -cn --arg m "$1" --arg d "$2" '{kind: "replace", member: $m, device: $d, wipe: true}')
show_plan "$body"
start_op "$body" "$3"
i=0
last=""
while [ $i -lt 1200 ]; do
  s=$(btrfs replace status -1 /data 2>/dev/null || true)
  [ "$s" != "$last" ] && echo "  seen: $s" && last=$s
  case $s in *"% done"*) case $s in *finished*|*canceled*) ;; *) break ;; esac ;; esac
  sleep 0.02; i=$((i + 1))
done
echo "  $s"
echo "journal: $(op_state "$3")"
case $s in
  *"% done"*) case $s in *finished*) ;; *) cut_power ;; esac ;;
esac
echo "MISSED: no replace was running; not cutting power"
