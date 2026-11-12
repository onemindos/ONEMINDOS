# SPDX-License-Identifier: Apache-2.0
# After a boot: what the assembly decided, and the set as the storage service sees it.
. ./common.sh
wait_service
journalctl -b -u lab-data-assemble -o cat --no-pager | grep -E '^\{|level=(WARN|ERROR)|unlocked' | cut -c1-400
ls /run/onemind/storage/ 2>/dev/null | sed 's/^/  run marker: /'
set_status
api GET /v1/status | jq -c '.mirror | {needs_scrub, mounted_degraded}'
corpus_check || true
