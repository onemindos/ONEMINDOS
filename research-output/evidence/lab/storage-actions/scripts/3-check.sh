# SPDX-License-Identifier: Apache-2.0
# After a power cut: what the boot did, how the engine resumed, and whether every byte survived.
. ./common.sh
wait_service
id=$1; shift
echo "== boot"
journalctl -b -u lab-data-assemble -o cat --no-pager | grep assemble:
journalctl -b -u onemind-storage -o cat --no-pager | grep -E 'resuming|paths changed|rolling|held|finished' | sed 's/^time=[^ ]* //' | cut -c1-240
echo "== operation $id"
wait_final "$id"
journal "$id"
echo "== set"
set_status
btrfs filesystem df /data | sed 's/^/  /'
echo "== scrub"
btrfs scrub start -B /data | grep -E 'Error summary|Total to scrub|Status' | sed 's/^/  /'
corpus_check
tokens "$@"
recovery_opens "$@"
