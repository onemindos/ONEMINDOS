# SPDX-License-Identifier: Apache-2.0
# Grow the corpus so a replace takes long enough to cut in the middle of it.
. ./common.sh
for i in $(seq 25 54); do head -c 50M /dev/urandom > /data/corpus/f$i; done
(cd /data/corpus && sha256sum f*) > "$LAB/corpus.sha256"; sync
corpus_check
btrfs filesystem df /data | sed 's/^/  /'
