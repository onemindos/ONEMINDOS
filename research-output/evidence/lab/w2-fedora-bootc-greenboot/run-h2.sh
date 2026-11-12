#!/bin/bash
# H2: forced bad OS update -> expect automatic greenboot rollback with zero manual commands after the first reboot.
cd /root/w2; S=./dut.sh; T0=$(date +%s); log(){ echo "[$(( $(date +%s)-T0 ))s] $*"; }
log "switching to bad image"; $S ssh "sudo bootc switch ${REG}/onemind-lab:bad 2>&1 | tail -3; sudo bootc status --format=json | jq -c '{booted:.status.booted.image.image.image,staged:.status.staged.image.image.image}'; sudo grub2-editenv list"
log "rebooting (last manual command)"; $S ssh "sudo systemctl reboot" ; sleep 20
last=""
for i in $(seq 1 270); do
  st=$($S ssh "echo \$(sudo bootc status --format=json | jq -r '.status.booted.image.image.image') \$(systemctl is-active greenboot-healthcheck) \$(cat /proc/sys/kernel/random/boot_id | cut -c1-8) \$(sudo grub2-editenv list | tr '\n' ' ')" 2>/dev/null)
  [ -n "$st" ] && [ "$st" != "$last" ] && { log "$st"; last="$st"; }
  case "$st" in *onemind-lab:good\ active*) log "RESULT: back on good image, GREEN"; break;; esac
  sleep 10
done
$S ssh "sudo journalctl --list-boots --no-pager | tail -6; for b in -3 -2 -1 0; do echo \"== boot \$b\"; sudo journalctl -b \$b -u greenboot-healthcheck -u greenboot-rollback --no-pager 2>/dev/null | grep -iE 'fail|rollback|reboot|passed|boot_counter|FALLBACK' | tail -6; done; sudo bootc status --format=json | jq -c '{booted:.status.booted.image.image.image,rollback:.status.rollback.image.image.image}'"
log done
