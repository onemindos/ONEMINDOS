# SPDX-License-Identifier: Apache-2.0
# Shared helpers for the storage-mirror lab. Runs as root inside the lab VM only.
set -euo pipefail
KEY=/root/lab.key   # random, lab-only, never leaves the VM (TPM2 + recovery key replace it in STOR-1)
say() { printf '\n### %s\n' "$*"; }
run() { printf '$ %s\n' "$*"; "$@"; }
# apply_plan runs exactly the commands a plan lists, after showing it.
# This is what an approved storage.* action will do in STOR-4; here a person runs it.
apply_plan() {
  local json; json=$(onemind storage plan "$@" --json)
  onemind storage plan "$@"
  if [ "$(jq -r .blocked <<<"$json")" = true ]; then echo "plan blocked, not applying"; return 1; fi
  say "applying plan $(jq -r .plan_sha256 <<<"$json")"
  jq -r '.steps[].cmd | @sh' <<<"$json" | while read -r line; do printf '$ %s\n' "$line"; eval "$line"; done
}
# capture saves the raw tool output the Go tests replay (internal/storage/testdata).
capture() {
  local n=$1 d=/root/fixtures; mkdir -p $d
  findmnt --json --mountpoint /data -o SOURCE,FSTYPE,OPTIONS,UUID > $d/$n.findmnt.json || true
  btrfs filesystem show --raw /data > $d/$n.show.txt
  btrfs filesystem df -b /data > $d/$n.df.txt
  btrfs device stats /data > $d/$n.stats.txt
  lsblk --json --bytes --paths -o NAME,KNAME,PKNAME,TYPE,SIZE,MODEL,SERIAL,WWN,TRAN,ROTA,RM,RO,FSTYPE,LABEL,UUID,PARTLABEL,MOUNTPOINTS > $d/$n.lsblk.json
}
