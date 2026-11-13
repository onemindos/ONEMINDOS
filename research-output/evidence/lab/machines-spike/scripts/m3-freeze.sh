#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-machines-spike M3 (+ E1, E7): guest-agent freeze, a write that must block, a raw copy taken
# while frozen and checked read-only, thaw. Then E1 (copy without a freeze).
#   m3-freeze.sh <a|b> <namespace> <machine>     Root, lab VM only. The guest is never mounted read-write.
set -uo pipefail; source "$(dirname "$0")/common.sh"
OPT=$1 NS=$2 NAME=$3; R=$OUT/m3-$OPT; mkdir -p "$R"; exec > >(tee "$R/m3.log") 2>&1
DISK=$(diskdir "$NS" "$NAME-disk")/disk.img
echo "disk <pvc-dir>/disk.img: apparent $(du -h --apparent-size "$DISK" | cut -f1), allocated $(du -h "$DISK" | cut -f1)"
COPY=$W/copy-$OPT.img; MNT=$W/mnt-$OPT; mkdir -p "$MNT"
rel(){ python3 -c "print(round($1-$2,2))"; }

check_copy(){ # <img> <marker text> <tag>: read-only fs check + marker lookup on a no-log-replay mount
  local img=$1 mark=$2 tag=$3 L P FS rc opts found during
  L=$(losetup -r -f -P --show "$img"); sleep 1
  P=$(lsblk -b -rno NAME,SIZE,FSTYPE "$L" | awk '$3~/^(btrfs|ext4|xfs)$/' | sort -k2 -n | tail -1 | cut -d' ' -f1)
  FS=$(blkid -o value -s TYPE "/dev/$P")
  case $FS in
    btrfs) btrfs check --readonly "/dev/$P" > "$R/$tag-fsck.txt" 2>&1; rc=$?; opts=ro,rescue=nologreplay;;
    ext4)  e2fsck -fn "/dev/$P" > "$R/$tag-fsck.txt" 2>&1; rc=$?; opts=ro,noload;;
    xfs)   xfs_repair -n "/dev/$P" > "$R/$tag-fsck.txt" 2>&1; rc=$?; opts=ro,norecovery;;
  esac
  found=absent; during=absent
  if mount -o "$opts" "/dev/$P" "$MNT" 2>"$R/$tag-mount.txt"; then
    f=$(find "$MNT" -maxdepth 4 -path '*/lab/marker' 2>/dev/null | head -1)
    [ -n "$f" ] && { [ "$(cat "$f")" = "$mark" ] && found=present || found="other:$(head -c 40 "$f")"; }
    [ -n "$(find "$MNT" -maxdepth 4 -path '*/lab/during-freeze' 2>/dev/null | head -1)" ] && during=present
    umount "$MNT"; mounted=true
  else mounted=false; fi
  losetup -d "$L"
  jq -n --arg fs "$FS" --argjson rc "$rc" --arg opts "$opts" --arg m "$found" --arg d "$during" --argjson mo $mounted \
    '{fs:$fs, fsck_rc:$rc, fsck_clean:($rc==0), mount_opts:$opts, mounted:$mo, marker:$m, during_freeze_file:$d}'
}

# (b) an SSH session opened BEFORE the freeze; it waits for "go", then writes into the home directory
FIFO=$R/go.fifo; rm -f "$FIFO"; mkfifo "$FIFO"; : > "$R/bg.out"
( gssh $OPT $NS $NAME 'echo READY; read go; s=$(date +%s.%N); echo during > ~/during-freeze; e=$(date +%s.%N); echo "GUEST_WRITE $s $e"' \
    < "$FIFO" >> "$R/bg.out" 2>&1; echo "BG_EXIT $? $(date +%s.%N)" >> "$R/bg.out" ) &
BG=$!; exec 7>"$FIFO"
for _ in $(seq 1 30); do grep -q READY "$R/bg.out" && break; sleep 1; done
grep -q READY "$R/bg.out" || echo "WARN background session not ready"

# (c) marker written without sync, then the freeze immediately
MARK=mk-$(date +%s%N); gssh $OPT $NS $NAME "echo $MARK > ~/marker"; t_m=$(ts)
t_f0=$(ts); freeze $OPT $NS $NAME > "$R/freeze.out" 2>&1; rc_f=$?; t_f1=$(ts)
echo "freeze rc=$rc_f after marker +$(rel $t_f0 $t_m)s, call took $(rel $t_f1 $t_f0)s: $(cat "$R/freeze.out")"
st_f=""; for _ in $(seq 1 30); do st_f=$(fstatus $OPT $NS $NAME 2>/dev/null); [ "$st_f" = frozen ] && break; sleep 1; done
t_st=$(ts); echo "status=$st_f at +$(rel $t_st $t_f0)s"
sleep "$(python3 -c "print(max(0, $t_f0 + 5 - $(ts)))")"; echo go >&7; t_go=$(ts); echo "write released at +$(rel $t_go $t_f0)s"
t_c0=$(ts); cp --sparse=always "$DISK" "$COPY" & CP=$!
sleep "$(python3 -c "print(max(0, $t_f0 + 20 - $(ts)))")"
blocked20=true; grep -q GUEST_WRITE "$R/bg.out" && blocked20=false; kill -0 $BG 2>/dev/null || blocked20=false
echo "at +20s: write blocked=$blocked20"
wait $CP; rc_cp=$?; t_c1=$(ts); echo "copy rc=$rc_cp took $(rel $t_c1 $t_c0)s"
sleep "$(python3 -c "print(max(0, $t_f0 + 30 - $(ts)))")"
t_t0=$(ts); thaw $OPT $NS $NAME > "$R/thaw.out" 2>&1; rc_t=$?; t_t1=$(ts); echo "thaw rc=$rc_t at +$(rel $t_t0 $t_f0)s: $(cat "$R/thaw.out")"
for _ in $(seq 1 30); do grep -q BG_EXIT "$R/bg.out" && break; sleep 0.5; done
exec 7>&-; wait $BG 2>/dev/null
t_done=$(awk '/^BG_EXIT/{print $3}' "$R/bg.out"); [ -n "$t_done" ] || t_done=0
after_thaw=$(rel "$t_done" "$t_t1")
st_t=""; for _ in $(seq 1 30); do st_t=$(fstatus $OPT $NS $NAME 2>/dev/null); [ "$st_t" = thawed ] && break; sleep 1; done
echo "write completed $after_thaw s after thaw; status after thaw=$st_t"; cat "$R/bg.out"
C=$(check_copy "$COPY" "$MARK" frozen-copy); rm -f "$COPY"; echo "frozen copy: $C"

# E1: the same marker test with a copy taken WITHOUT a freeze
MARK2=mk-$(date +%s%N); gssh $OPT $NS $NAME "echo $MARK2 > ~/marker"; t_m2=$(ts)
cp --sparse=always "$DISK" "$COPY"; t_e1=$(ts)
E1=$(check_copy "$COPY" "$MARK2" unfrozen-copy); rm -f "$COPY"; echo "E1 unfrozen copy (started +$(rel $t_e1 $t_m2)s after the marker finished copying): $E1"
gssh $OPT $NS $NAME 'rm -f ~/marker ~/during-freeze; sync'

pa=false; [ $rc_f = 0 ] && [ "$st_f" = frozen ] && pa=true
pb=false; [ $blocked20 = true ] && python3 -c "import sys; sys.exit(0 if 0 <= $after_thaw <= 10 else 1)" && pb=true
pc=false; echo "$C" | jq -e '.fsck_clean and .marker=="present"' >/dev/null && [ $rc_cp = 0 ] && pc=true
pd=false; [ $rc_t = 0 ] && [ "$st_t" = thawed ] && pd=true
jq -n --arg o $OPT --argjson a $pa --argjson b $pb --argjson c $pc --argjson d $pd --argjson copy "$C" --argjson e1 "$E1" \
  --arg mf "$(rel $t_f0 $t_m)" --arg cps "$(rel $t_c1 $t_c0)" --arg at "$after_thaw" --arg thaw_at "$(rel $t_t0 $t_f0)" \
  '{option:$o, a_freeze_status:$a, b_write_blocked:$b, c_consistent_copy:$c, d_thaw:$d, pass:($a and $b and $c and $d),
    marker_to_freeze_s:($mf|tonumber), copy_s:($cps|tonumber), thaw_at_s:($thaw_at|tonumber), write_done_after_thaw_s:($at|tonumber),
    frozen_copy:$copy, e1_unfrozen_copy:$e1}' | tee "$R/m3.json"

# E7: what happens if nobody thaws. A: a short unfreezeTimeout must thaw by itself. B: QEMU's agent has no timeout.
if [ $OPT = a ]; then
  UNFREEZE=60s freeze a $NS $NAME > "$R/e7-freeze.out" 2>&1; t7=$(ts)
  for _ in $(seq 1 60); do sleep 5; s=$(fstatus a $NS $NAME); [ "$s" = thawed ] && break; done
  echo "E7 A: unfreezeTimeout=60s, status=$s at +$(rel "$(ts)" "$t7")s" | tee "$R/e7.txt"
  [ "$s" = thawed ] || thaw a $NS $NAME
else
  echo "E7 B: guest-fsfreeze-freeze has no timeout argument in QEMU's agent; a lost caller leaves the guest frozen until something thaws it (not left frozen here)" | tee "$R/e7.txt"
fi
