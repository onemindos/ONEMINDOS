# SPDX-License-Identifier: Apache-2.0
# After the ENOSPC replace (logs 13, 14): vdc is blanked by hand (lab reset; with the fixed engine a
# replace that moved nothing rolls back by itself), the new headroom check refuses the full set, then
# 700 MB of corpus is deleted and a usage-filtered balance compacts the chunks (lab maintenance).
. ./common.sh
wait_service
systemctl restart onemind-storage; wait_service
for m in $(lsblk -nlo NAME,TYPE /dev/vdc | awk '$2 == "crypt" {print $1}'); do cryptsetup close "$m"; done
wipefs -aq /dev/vdc1; sgdisk --zap-all /dev/vdc >/dev/null; udevadm settle
btrfs filesystem show /data | sed 's/^/  /'
show_plan '{"kind":"replace","member":"/dev/vdd","device":"/dev/vdc","wipe":true}' | head -4
rm -f /data/corpus/f4[1-9] /data/corpus/f5[0-4]
(cd /data/corpus && sha256sum f*) > "$LAB/corpus.sha256"; sync
btrfs balance start -dusage=90 /data | sed 's/^/  /'
btrfs filesystem show /data | sed 's/^/  /'
show_plan '{"kind":"replace","member":"/dev/vdd","device":"/dev/vdc","wipe":true}' | head -2
corpus_check
