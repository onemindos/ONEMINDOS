# SPDX-License-Identifier: Apache-2.0
# Phase 13: the detached member is back. The set must still report degraded (the needs-scrub
# marker: the returned disk holds stale copies of what was written while it was away), and
# storage.mirror.repair must bring it back to protected with every file intact.
. ./common.sh
wait_service
journalctl -b -u lab-data-assemble -o cat --no-pager | grep -E '^\{' | cut -c1-300
set_status
show_plan '{"kind":"repair"}' | head -3
start_op '{"kind":"repair"}' lab-repair-2
wait_final lab-repair-2
journal lab-repair-2
api GET /v1/operations/lab-repair-2 | jq -r '.steps[0].output' | grep -i -E 'corrected|uncorrectable|error summary' | sed 's/^/  scrub: /'
set_status
corpus_check
