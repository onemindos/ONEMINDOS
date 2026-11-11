#!/bin/bash
# Host-side test driver. Usage: run-tests.sh t2|t3|t4|t5|t6   (T1 = run-vm.sh start + state)
# Requires: build VM "bootc-build" running (registry), test VM started with run-vm.sh.
set -uo pipefail
S=$(cd "$(dirname "$0")" && pwd); source "$S/lab.sh"
export LIMA_HOME=${LIMA_HOME:-$LAB/lima}
ts() { date -u +%H:%M:%S; }
# point the channel the device tracks (onemind/lab:stable) at a variant
channel() { limactl shell bootc-build -- sudo skopeo copy -q --src-tls-verify=false --dest-tls-verify=false \
  docker://localhost:5000/onemind/lab:$1 docker://localhost:5000/onemind/lab:stable; echo "[$(ts)] channel stable -> $1"; }
reboot_vm() { vssh 'sudo systemctl reboot' ; wait_down 120; wait_up 300; }

case "$1" in
t2) channel v2
    vssh 'sudo bootc upgrade' ; state; reboot_vm; state ;;
t3) channel v3-bad
    vssh 'sudo bootc upgrade'; state; echo "[$(ts)] rebooting into v3-bad, then hands off"
    vssh 'sudo systemctl reboot'; t0=$SECONDS
    # observe only: poll every 5s, never intervene, up to 15 minutes
    last=""; while (( SECONDS - t0 < 900 )); do
      cur=$(vssh 'echo "$(cat /usr/share/onemind/version) up=$(cut -d" " -f1 /proc/uptime) $(sudo grub2-editenv /boot/grub2/grubenv list | grep -E "boot_counter|boot_success" | tr "\n" " ")"' 2>/dev/null) || cur="(down)"
      [ "$cur" != "$last" ] && echo "[$(ts)] +$((SECONDS-t0))s $cur"; last=$cur
      case "$cur" in v2*) n=$((${n:-0}+1)); [ $n -ge 12 ] && break;; *) n=0;; esac
      sleep 5; done
    state
    vssh 'sudo journalctl --no-pager -o short-monotonic -u greenboot-healthcheck -b -1 | tail -25; echo ---; journalctl --list-boots --no-pager | tail -8' ;;
# T4 power cut. $2 = phase: pull | deploy | finalize
t4) phase=${2:-pull}; channel v4-big; state
    pid=$(cat "$LAB/vm/qemu.pid")
    if [ "$phase" = finalize ]; then
      vssh 'sudo bootc upgrade' | tail -2; state
      echo "[$(ts)] reboot; SIGKILL QEMU 1s later (inside ostree-finalize-staged at shutdown)"
      vssh 'sudo systemctl reboot'; sleep 1; kill -9 "$pid"
    else
      vssh 'sudo rm -f /var/tmp/up.log; sudo systemd-run --unit=lab-upgrade-$RANDOM bash -c "bootc upgrade >/var/tmp/up.log 2>&1"'
      t0=$SECONDS
      if [ "$phase" = deploy ]; then
        until vssh "sudo grep -q 'Deploying' /var/tmp/up.log" 2>/dev/null || (( SECONDS-t0 > 300 )); do sleep 0.3; done
      else sleep 4; fi
      vssh 'echo "--- ostree repo tmp (partial objects):"; sudo du -sh /sysroot/ostree/repo/tmp 2>/dev/null; echo "--- up.log so far:"; sudo cat /var/tmp/up.log' 2>/dev/null | cut -c1-300
      echo "[$(ts)] SIGKILL QEMU (phase=$phase)"; kill -9 "$pid"
    fi
    sleep 2; echo "[$(ts)] power restored"; "$S/run-vm.sh" start; wait_up 300; state
    vssh 'echo "--- ostree fsck:"; sudo ostree fsck 2>&1 | tail -3; echo "--- deployments:"; sudo ostree admin status 2>&1 | head -12; systemctl is-system-running'
    vssh 'echo "--- BLS entries:"; sudo grep -H -E "^(title|version|options)" /boot/loader/entries/*.conf | sed "s/root=UUID=[^ ]*//;s/boot=UUID=[^ ]*//" | cut -c1-200'
    if [ "${3:-}" = noupgrade ]; then
      echo "[$(ts)] plain reboot, no upgrade: which deployment boots next?"; reboot_vm; state
      vssh 'sudo ostree admin status 2>&1 | head -8'
    fi
    echo "[$(ts)] recovery: bootc upgrade again"; vssh 'sudo bootc upgrade 2>&1 | tail -3'; reboot_vm; state ;;
t6) vssh 'cat /var/lib/onemind-test/data.txt' ;;
esac
