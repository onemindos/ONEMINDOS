# SPDX-License-Identifier: Apache-2.0
# Phase 9: a failure in the join phase rolls back. storage.mirror.add of vdd is held before device-add;
# the new member's mapping is closed by hand, so "btrfs device add" fails; the engine must take the
# disk back to blank and leave the set as it was.
. ./common.sh
wait_service
set_status
mkdir -p /run/onemind/storage && touch /run/onemind/storage/hold-before-device-add
start_op '{"kind":"add","device":"/dev/vdd"}' lab-add-rollback
i=0
until journalctl -u onemind-storage -o cat --no-pager --since "-1min" | grep -q 'held before a step'; do sleep 0.2; i=$((i + 1)); [ $i -lt 150 ] || break; done
echo "journal: $(op_state lab-add-rollback)"
cryptsetup close onemind-data-vdd && echo "closed the new member's mapping by hand"
rm -f /run/onemind/storage/hold-before-device-add
wait_final lab-add-rollback
journal lab-add-rollback
set_status
lsblk -no NAME,TYPE,FSTYPE /dev/vdd | sed 's/^/  vdd after rollback: /'
corpus_check
