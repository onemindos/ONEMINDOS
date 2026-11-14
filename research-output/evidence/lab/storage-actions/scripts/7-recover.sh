# SPDX-License-Identifier: Apache-2.0
# After the replace bug (logs 10, 11): the boot with the fixed assembly, then storage.mirror.repair
# (scrub, soft-convert, tokens re-stamped at one generation, marker cleared). vdc, which holds a
# prepared LUKS2 header but no data, is blanked by hand (lab reset; a "wipe disk" action is a follow-up).
. ./common.sh
wait_service
journalctl -b -u lab-data-assemble -o cat --no-pager | grep assemble:
set_status
show_plan '{"kind":"repair"}'
start_op '{"kind":"repair"}' lab-repair-1
wait_final lab-repair-1
journal lab-repair-1
set_status
corpus_check
tokens /dev/vdb1 /dev/vdd1 /dev/vdc1
for m in $(lsblk -nlo NAME,TYPE /dev/vdc | awk '$2 == "crypt" {print $1}'); do cryptsetup close "$m"; done
wipefs -aq /dev/vdc1; sgdisk --zap-all /dev/vdc >/dev/null; udevadm settle
lsblk -no NAME,TYPE,FSTYPE /dev/vdc | sed 's/^/  vdc reset: /'
