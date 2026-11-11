#!/bin/bash
# H3: simulated power cut (kill -9 QEMU) (a) while an update is downloading/staging, (b) during shutdown finalization of a staged update.
cd /root/w2; S=./dut.sh; T0=$(date +%s); log(){ echo "[$(( $(date +%s)-T0 ))s] $*"; }
state(){ $S ssh "sudo bootc status --format=json | jq -c '{booted:.status.booted.image.image.image,staged:.status.staged.image.image.image,rollback:.status.rollback.image.image.image}'; systemctl is-active greenboot-healthcheck; sudo grub2-editenv list | tr '\n' ' '"; }
waitgreen(){ for i in $(seq 1 90); do s=$($S ssh "systemctl is-active greenboot-healthcheck" 2>/dev/null); [ "$s" = active -o "$s" = failed ] && break; sleep 10; done; }
log "pre-state"; state
log "H3a: start large switch (different base, ~1 GB of layers) in background, kill QEMU after 20 s"
$S ssh "nohup sudo bootc switch quay.io/fedora/fedora-bootc:45 >/tmp/sw.log 2>&1 &" ; sleep 20
$S ssh "tail -c 300 /tmp/sw.log" ; $S kill; log "QEMU killed (H3a)"; sleep 3
$S boot; $S wait 120; waitgreen; log "H3a post-state:"; state
log "H3b: stage small bad update, reboot, kill QEMU 2 s into shutdown (during ostree-finalize-staged)"
$S ssh "sudo bootc switch ${REG}/onemind-lab:bad 2>&1 | tail -1"; state
$S ssh "sudo systemctl reboot" ; sleep 2; $S kill; log "QEMU killed (H3b)"; sleep 3
$S boot; $S wait 120; waitgreen; log "H3b post-state (if booted bad, greenboot will roll back as in H2):"; state
$S ssh "sudo journalctl -b -1 --no-pager | grep -iE 'finaliz|ostree' | tail -5; sudo journalctl --list-boots --no-pager | tail -4"
log done
