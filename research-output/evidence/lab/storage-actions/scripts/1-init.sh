# SPDX-License-Identifier: Apache-2.0
# Phase 1: first boot. onemind-data on vdb becomes LUKS2 + btrfs (onemindd storage init, H-11);
# the recovery key is taken once through the socket; a checksummed corpus is written.
. ./common.sh
mkdir -p "$LAB"
install -m 0755 ./onemindd /usr/local/bin/onemindd
install -m 0755 ./assemble.sh /usr/local/sbin/lab-data-assemble
. ./units.sh
sgdisk --zap-all /dev/vdb >/dev/null && sgdisk --new=1:0:0 --typecode=1:8309 --change-name=1:onemind-data /dev/vdb >/dev/null && udevadm settle
echo "== onemindd storage init"
onemindd storage init --device /dev/vdb1 --tpm2 no
cryptsetup luksDump /dev/vdb1 | grep -E '^\s+[0-9]+: (luks2|onemind-storage)|PBKDF:|Memory:' | sed 's/^/  /'
cryptsetup close onemind-data
echo "== recovery key: shown once through the socket"
systemctl start onemind-storage.service; sleep 1
api GET /v1/status | jq -c '{operations_available, recovery_key_pending, mirror_state: .mirror.state}'
api POST /v1/recovery-key/take | jq -j .recovery_key > "$LAB/recovery.key" # no newline: it is typed at a prompt
printf 'taken: %s characters, format %s\n' "$(wc -c < "$LAB/recovery.key")" "$(sed 's/[a-z]/x/g' "$LAB/recovery.key")"
printf 'second take: '; api POST /v1/recovery-key/take | jq -c .
systemctl stop onemind-storage.service
echo "== assemble (as at boot) and start the service"
systemctl start lab-data-assemble.service onemind-storage.service; sleep 1
journalctl -u lab-data-assemble -o cat --no-pager | grep assemble:
findmnt -no SOURCE,FSTYPE /data
ls -l /data/onemind/storage/keys/set.key | awk '{print "set key:", $1, $3, $NF}'
echo "== corpus"
mkdir -p /data/corpus
for i in $(seq 1 24); do head -c 50M /dev/urandom > /data/corpus/f$i; done
(cd /data/corpus && sha256sum f*) > "$LAB/corpus.sha256"; sync
corpus_check
set_status
