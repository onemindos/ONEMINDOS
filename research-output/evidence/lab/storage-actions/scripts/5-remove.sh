# SPDX-License-Identifier: Apache-2.0
# Phase 5: storage.mirror.remove of vdd with wipe (3 -> 2: metadata raid1c3 -> raid1 first).
. ./common.sh
show_plan '{"kind":"remove","member":"/dev/vdd","wipe":true}'
start_op '{"kind":"remove","member":"/dev/vdd","wipe":true}' lab-remove-1
wait_final lab-remove-1
journal lab-remove-1
set_status
lsblk -no NAME,TYPE,FSTYPE /dev/vdd | sed 's/^/  vdd after wipe: /'
corpus_check
