# SPDX-License-Identifier: Apache-2.0
# Phase 2: storage.mirror.create (vdb -> vdb+vdc, raid1) and a power cut in the middle of the balance.
. ./common.sh
show_plan '{"kind":"create","device":"/dev/vdc"}'
start_op '{"kind":"create","device":"/dev/vdc"}' lab-create-1
i=0
while [ $i -lt 600 ]; do
  n=$(btrfs balance status /data 2>/dev/null | sed -n 's/^\([0-9]*\) out of about.*/\1/p')
  [ "${n:-0}" -ge 1 ] && break
  sleep 0.1; i=$((i + 1))
done
btrfs balance status /data | sed 's/^/  /'
echo "journal: $(op_state lab-create-1)"
cut_power
