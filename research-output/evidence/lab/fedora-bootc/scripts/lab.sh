#!/bin/bash
# Host-side helpers: ssh into the test VM and wait for it.
LAB=${LAB:?"set LAB to <lab-dir>/fedora-bootc"}
vssh() { ssh -q -i "$LAB/vm/lab_ed25519" -p 2222 -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5 -o BatchMode=yes lab@127.0.0.1 "$@"; }
# wait_up <timeout-seconds>: prints seconds until SSH answers
wait_up() { local t0=$SECONDS; until vssh true 2>/dev/null; do
  (( SECONDS - t0 > ${1:-300} )) && { echo "TIMEOUT"; return 1; }; sleep 3; done; echo "up after $((SECONDS-t0))s"; }
# wait_down: until SSH stops answering (VM rebooting)
wait_down() { local t0=$SECONDS; while vssh true 2>/dev/null; do
  (( SECONDS - t0 > ${1:-120} )) && { echo "still up"; return 1; }; sleep 2; done; }
state() { vssh 'echo "marker=$(cat /usr/share/onemind/version) uptime=$(cut -d" " -f1 /proc/uptime)"; sudo grub2-editenv /boot/grub2/grubenv list 2>/dev/null | grep -E "boot_counter|boot_success|greenboot" | tr "\n" " "; echo'
  vssh 'sudo bootc status --format=json' | jq -c '{booted:.status.booted.image.image.image, bootedDigest:.status.booted.image.imageDigest, staged:.status.staged.image.imageDigest, rollback:.status.rollback.image.imageDigest}'; }
