# SPDX-License-Identifier: Apache-2.0
# Shared helpers for the storage-actions lab (run as root inside the VM).
set -eu
SOCK=/run/onemind/storage.sock
LAB=/root/lab
api() { m=$1; p=$2; shift 2; curl -sS --unix-socket "$SOCK" -X "$m" -H 'Content-Type: application/json' "http://storage$p" "$@"; }
show_plan() {
  api POST /v1/plans -d "$1" | jq -r '"plan: kind=\(.kind) blocked=\(.blocked) profiles=\(.data_profile)/\(.metadata_profile) encrypted=\(.encrypted) sha=\(.plan_sha256[0:12])",
    (.checks[] | select(.ok | not) | "  FAILED \(.id): \(.detail)"), (.warnings // [] | .[] | "  warning: \(.)"),
    (.steps // [] | to_entries[] | "  \(.key + 1). [\(.value.phase)] \(.value.id): \(.value.cmd | join(" "))")'
}
start_op() { # body, action id: approve the plan we just rendered (the gateway's job in the product)
  sha=$(api POST /v1/plans -d "$1" | jq -r .plan_sha256)
  echo "$1" | jq -c --arg s "$sha" --arg id "$2" '. + {plan_sha256: $s, action_id: $id}' | api POST /v1/operations -d @- | jq -c '{id, state, next, error, reason, message}'
}
op_state() { api GET "/v1/operations/$1" | jq -r '"\(.state) next=\(.next)/\(.steps | length) step=\(.plan.steps[.next].id // "-") resumes=\(.resumes // 0)"'; }
wait_final() {
  i=0
  while [ $i -lt 900 ]; do
    s=$(api GET "/v1/operations/$1" | jq -r .state)
    case $s in running|rolling_back) sleep 1; i=$((i + 1)) ;; *) echo "final state: $s"; return 0 ;; esac
  done
  echo "final state: timeout"
}
journal() {
  api GET "/v1/operations/$1" | jq -r '.steps as $r | .plan.steps | to_entries[] |
    "  \(.key + 1). \(.value.id) [\(.value.phase)] \($r[.key].state) attempts=\($r[.key].attempts // 0) \($r[.key].note // "")"'
  api GET "/v1/operations/$1" | jq -c '{state, error, resumes, relocated, rollback: ((.rollback // []) | map(.cmd | join(" ")))}'
}
set_status() { api GET /v1/status | jq -c ".mirror | {state, reasons, encrypted, generation, members: [(.members // [])[] | \"\\(.devid):\\(.path // \"missing\")\"], profiles: [(.profiles // [])[] | \"\\(.kind)=\\(.profile)\"]}"; }
corpus_check() { (cd /data/corpus && sha256sum -c --quiet "$LAB/corpus.sha256") && echo "corpus OK: $(wc -l < "$LAB/corpus.sha256") files match their checksums"; }
tokens() { for d in "$@"; do printf '%s token: ' "$d"; cryptsetup token export --token-id 30 "$d" 2>/dev/null | jq -c '{generation, partuuid}' || echo none; echo "  own partuuid: $(blkid -s PARTUUID -o value "$d")"; done; }
recovery_opens() { for d in "$@"; do cryptsetup open --test-passphrase --key-file "$LAB/recovery.key" "$d" && echo "recovery key opens $d"; done; }
cut_power() { # sysrq b: reboot at once, no sync, no unmount (the lab's power cut)
  echo "POWER CUT $(date -u +%T)"
  sync -f /root || true # flush only the system disk, so this log line survives; /data is cut dirty
  echo 1 > /proc/sys/kernel/sysrq
  echo b > /proc/sysrq-trigger
}
wait_service() { # the boot unlocks each member (argon2id, a few seconds) before the service starts
  i=0
  until [ -S "$SOCK" ] && systemctl is-active -q onemind-storage; do sleep 1; i=$((i + 1)); [ $i -lt 120 ] || break; done
}
