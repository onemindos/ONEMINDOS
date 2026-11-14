#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Kiwix library manager (REC-NOMAD-01). Downloads the ZIM files named in KIWIX_ZIMS from the
# Kiwix mirror, checks each against the mirror's .sha256 file and its free-space need, then
# rebuilds library.xml from exactly that list. kiwix-serve runs with --monitorLibrary and
# reloads the new library by itself.
# It never deletes a ZIM file: removing content is the owner's decision (README "Remove a book").
set -u
DATA=${DATA:-/data}
MIRROR=${KIWIX_MIRROR:-https://download.kiwix.org/zim}
RESERVE_MB=${KIWIX_RESERVE_MB:-1024}
LIB="$DATA/library.xml"
NEW="$DATA/.library.new.xml"
log() { echo "library-sync: $*"; }
empty_library() { printf '<library version="20110515">\n</library>\n' > "$1"; }

case "$MIRROR" in
  https://*) ;;
  *) log "KIWIX_MIRROR must be an https:// URL, got '$MIRROR'"; exit 1 ;;
esac
case "$RESERVE_MB" in
  ''|*[!0-9]*) log "KIWIX_RESERVE_MB must be a whole number, got '$RESERVE_MB'"; exit 1 ;;
esac
[ -f "$LIB" ] || empty_library "$LIB"

empty_library "$NEW"
ok=0; failed=0
for z in ${KIWIX_ZIMS:-}; do
  # <folder>/<file>.zim under the mirror's zim/ tree, nothing else: no URL, no "..", no spaces.
  if ! echo "$z" | grep -Eq '^[a-z0-9_-]+/[A-Za-z0-9_.-]+\.zim$' || echo "$z" | grep -q '\.\.'; then
    log "skip '$z': expected <folder>/<file>.zim, for example wikipedia/wikipedia_en_medicine_mini_2026-10.zim"
    failed=$((failed+1)); continue
  fi
  name=$(basename "$z"); f="$DATA/$name"; url="$MIRROR/$z"
  if [ ! -f "$f" ]; then
    # The last response after redirects decides: its status must be 200 and it must give a size.
    size=$(wget -S --spider "$url" 2>&1 | awk '$1 ~ /^HTTP\// {st=$2; s=0} tolower($1)=="content-length:" {s=$2} END {print (st=="200") ? s+0 : 0}')
    have=$(stat -c %s "$f.part" 2>/dev/null || echo 0)
    free_kb=$(df -Pk "$DATA" | awk 'NR==2 {print $4}')
    need_kb=$(( (size - have) / 1024 + RESERVE_MB * 1024 ))
    if [ "$size" -le 0 ]; then
      log "$z not found on the mirror (or no size given); it is retried on the next run"
      failed=$((failed+1)); continue
    fi
    if [ "$free_kb" -lt "$need_kb" ]; then
      log "not enough space for $name: needs $((need_kb / 1024)) MiB with the reserve, $((free_kb / 1024)) MiB free"
      failed=$((failed+1)); continue
    fi
    log "downloading $z ($((size / 1048576)) MiB)"
    if ! wget -q -c -O "$f.part" "$url" || ! wget -q -O "$f.sha256" "$url.sha256"; then
      log "download of $z failed; it resumes on the next run"
      rm -f "$f.sha256"; failed=$((failed+1)); continue
    fi
    want=$(cut -d' ' -f1 "$f.sha256"); got=$(sha256sum "$f.part" | cut -d' ' -f1)
    rm -f "$f.sha256"
    if [ -z "$want" ] || [ "$want" != "$got" ]; then
      log "checksum mismatch for $z (mirror says $want, file is $got): file discarded"
      rm -f "$f.part"; failed=$((failed+1)); continue
    fi
    mv "$f.part" "$f"
    log "verified $name"
  fi
  if kiwix-manage "$NEW" add "$f" >/dev/null 2>&1; then
    ok=$((ok+1))
  else
    log "kiwix-manage could not read $name"; failed=$((failed+1))
  fi
done
mv "$NEW" "$LIB"
log "library has $ok book(s), $failed problem(s)"
