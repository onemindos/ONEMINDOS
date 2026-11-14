# SPDX-License-Identifier: Apache-2.0
# Phase 4: storage.mirror.add (vdd, metadata to raid1c3) with a power cut in the prepare phase,
# right after the LUKS2 header copy got its own UUID (before its own token and before it joins).
. ./common.sh
mkdir -p /run/onemind/storage && touch /run/onemind/storage/hold-before-luks-open
show_plan '{"kind":"add","device":"/dev/vdd"}'
start_op '{"kind":"add","device":"/dev/vdd"}' lab-add-1
i=0
until journalctl -u onemind-storage -o cat --no-pager | grep -q 'held before a step'; do sleep 0.2; i=$((i + 1)); [ $i -lt 100 ] || break; done
echo "journal: $(op_state lab-add-1)"
tokens /dev/vdd1
cut_power
