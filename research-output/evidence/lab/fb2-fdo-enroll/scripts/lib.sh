# SPDX-License-Identifier: Apache-2.0
# Shared helpers for LAB-fb2-fdo-enroll and LAB-fb4-fleet-rings (run inside the disposable VM only).
LAB=${LAB:?"set LAB to <lab-dir>"}; OUT=$LAB/out; B=/opt/fb; mkdir -p $OUT $B/bin
export PATH=/opt/go/bin:$B/bin:$PATH
log(){ echo "$(date -u +%FT%TZ) $*"; }
res(){ # res <dir> <id> <PASS|FAIL|BLOCKED|OBS> <json>
  mkdir -p "$1"; jq -n --arg id "$2" --arg v "$3" --argjson d "$4" --arg t "$(date -u +%FT%TZ)" '{id:$id,verdict:$v,at:$t,data:$d}' > "$1/$2.json"; log "RESULT $2 $3"; }
