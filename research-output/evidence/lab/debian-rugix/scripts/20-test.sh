#!/usr/bin/env bash
# LAB-debian-rugix test runner (host side). Boots the Bakery image in QEMU and runs
# T0 (first boot), T1 (good update commits), T2 (bad update rolls back by itself),
# T2b (manual commit refused on bad slot), T3 (power cut mid-write).
#
# Usage: LAB=<lab dir> ARCH=amd64|arm64 ./20-test.sh [t0|t1|t2|t3|all]
# Network: QEMU user-mode with restrict=on (no route to host LAN or internet);
# only SSH is forwarded to 127.0.0.1:$PORT.
set -uo pipefail
LAB=${LAB:?}; ARCH=${ARCH:-amd64}; PORT=${PORT:-22622}
BUILD="$LAB/work/project/build"
OUT="$LAB/run-$ARCH"; mkdir -p "$OUT"
KEY="$LAB/keys/lab_ed25519"
QSHARE=$(brew --prefix qemu)/share/qemu
SERIAL="$OUT/serial.log"; EVENTS="$OUT/events.log"
BOOT_TIMEOUT=${BOOT_TIMEOUT:-1200}

ev() { echo "$(date -u +%FT%TZ) $*" | tee -a "$EVENTS"; }
SSH() { ssh -q -i "$KEY" -p "$PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=5 -o ServerAliveInterval=5 -o ServerAliveCountMax=3 -o BatchMode=yes root@127.0.0.1 "$@"; }
SCP() { scp -q -i "$KEY" -P "$PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes "$@"; }

prep_disk() {
  rm -f "$OUT/disk.qcow2" "$OUT/vars.fd"
  qemu-img convert -O qcow2 "$BUILD/v1-$ARCH/system.img" "$OUT/disk.qcow2"
  qemu-img resize -q "$OUT/disk.qcow2" 24G
  if [ "$ARCH" = amd64 ]; then cp "$QSHARE/edk2-i386-vars.fd" "$OUT/vars.fd"
  else truncate -s 64M "$OUT/vars.fd"; fi
  ev "disk prepared from v1-$ARCH/system.img"
}

start_vm() {
  local common=(-m 4096 -smp 4 -display none -daemonize -pidfile "$OUT/qemu.pid"
    -drive "file=$OUT/disk.qcow2,if=virtio,format=qcow2,cache=writeback"
    -netdev "user,id=n0,restrict=on,hostfwd=tcp:127.0.0.1:$PORT-:22" -device virtio-net-pci,netdev=n0
    -chardev "file,id=ser0,path=$SERIAL,append=on" -serial chardev:ser0)
  if [ "$ARCH" = amd64 ]; then
    qemu-system-x86_64 -machine q35 -accel tcg,thread=multi -cpu max "${common[@]}" \
      -drive "if=pflash,format=raw,readonly=on,file=$QSHARE/edk2-x86_64-code.fd" \
      -drive "if=pflash,format=raw,file=$OUT/vars.fd" \
      -device i6300esb -action watchdog=reset 2>>"$OUT/qemu.err" || { ev "FAIL qemu start: $(tail -n 3 "$OUT/qemu.err")"; return 1; }
  else
    qemu-system-aarch64 -machine virt -accel hvf -cpu host "${common[@]}" \
      -drive "if=pflash,format=raw,readonly=on,file=$QSHARE/edk2-aarch64-code.fd" \
      -drive "if=pflash,format=raw,file=$OUT/vars.fd" 2>>"$OUT/qemu.err" || { ev "FAIL qemu start: $(tail -n 3 "$OUT/qemu.err")"; return 1; }
  fi
  ev "qemu started pid=$(cat "$OUT/qemu.pid")"
}

stop_vm() { [ -f "$OUT/qemu.pid" ] && kill "$(cat "$OUT/qemu.pid")" 2>/dev/null; sleep 2; rm -f "$OUT/qemu.pid"; }

wait_ssh() {
  local t0=$SECONDS
  until SSH true 2>/dev/null; do
    [ $((SECONDS - t0)) -gt "$BOOT_TIMEOUT" ] && { ev "FAIL ssh timeout"; return 1; }
    sleep 5
  done
  ev "ssh up after $((SECONDS - t0))s"
}

boot_id() { SSH cat /proc/sys/kernel/random/boot_id 2>/dev/null; }

# Wait until the boot id differs from $1 and SSH answers (i.e. the VM rebooted).
wait_reboot() {
  local old=$1 t0=$SECONDS cur
  while :; do
    cur=$(boot_id || true)
    [ -n "$cur" ] && [ "$cur" != "$old" ] && break
    [ $((SECONDS - t0)) -gt "$BOOT_TIMEOUT" ] && { ev "FAIL reboot timeout"; return 1; }
    sleep 5
  done
  ev "rebooted (new boot id) after $((SECONDS - t0))s"
}

# Wait until the health gate has finished on the current boot.
wait_gate() {
  local t0=$SECONDS
  until SSH 'systemctl show -p ActiveState --value onemind-health-gate' 2>/dev/null | grep -qE '^(active|failed)$'; do
    [ $((SECONDS - t0)) -gt "$BOOT_TIMEOUT" ] && { ev "FAIL gate wait timeout"; return 1; }
    sleep 5
  done
}

state() {
  SSH 'echo "release=$(cat /etc/onemind-release)"; rugix-ctrl system info | jq -c "{active:(.boot.activeGroup // .boot.active_group), default:(.boot.defaultGroup // .boot.default_group), state:.state.status}"; /usr/lib/onemind/k3s-healthy; tail -n 4 /var/log/onemind/health-gate.log' 2>&1 | tee -a "$EVENTS"
}

expect() { # expect <label> <grep -E pattern on state output>
  local s; s=$(SSH 'echo "release=$(cat /etc/onemind-release)"; rugix-ctrl system info | jq -c "{active:(.boot.activeGroup // .boot.active_group), default:(.boot.defaultGroup // .boot.default_group)}"' 2>&1)
  if grep -qE "$2" <<<"$(tr '\n' ' ' <<<"$s")"; then ev "PASS $1 :: $(tr '\n' ' ' <<<"$s")"; else ev "FAIL $1 :: $(tr '\n' ' ' <<<"$s") (wanted /$2/)"; fi
}

wait_k3s() {
  local t0=$SECONDS
  until SSH /usr/lib/onemind/k3s-healthy >/dev/null 2>&1; do
    [ $((SECONDS - t0)) -gt 900 ] && { ev "FAIL k3s not healthy in 900s"; return 1; }
    sleep 10
  done
  ev "k3s healthy after $((SECONDS - t0))s since check start"
}

install_update() { # install_update <variant>; installs and reboots into the trial slot
  ev "copy bundle $1"
  SCP "$BUILD/$1-$ARCH/system.rugixb" root@127.0.0.1:/root/bundle.rugixb || return 1
  local bid; bid=$(boot_id)
  ev "install $1 (--reboot yes)"
  SSH 'rugix-ctrl update install --insecure-skip-bundle-verification --reboot yes /root/bundle.rugixb' >>"$EVENTS" 2>&1
  wait_reboot "$bid"
}

t0() {
  ev "=== T0 first boot of v1"
  prep_disk; start_vm; wait_ssh || return 1
  wait_k3s; wait_gate; state
  expect T0 'release=v1 .*"active":"a","default":"a"'
}

t1() {
  ev "=== T1 good update v2-good"
  install_update v2good || return 1
  wait_gate; state
  expect T1-trial-committed 'release=v2-good .*"active":"b","default":"b"'
  local bid; bid=$(boot_id); SSH 'systemctl reboot' ; wait_reboot "$bid"; wait_gate
  expect T1-sticky-after-reboot 'release=v2-good .*"active":"b","default":"b"'
}

t2() {
  ev "=== T2 bad update v2-bad"
  local before; before=$(SSH 'cat /etc/onemind-release')
  install_update v2bad || return 1   # now on the trial slot
  local trial_bid; trial_bid=$(boot_id)
  SSH 'cat /etc/onemind-release; systemctl is-active k3s; true' | tee -a "$EVENTS"
  ev "T2b: manual commit attempt on bad slot (must be refused)"
  if SSH 'rugix-ctrl system commit' >>"$EVENTS" 2>&1; then ev "FAIL T2b manual commit succeeded"; else ev "PASS T2b manual commit refused"; fi
  ev "waiting for the gate to roll back by itself (no further commands)"
  wait_reboot "$trial_bid" || return 1
  wait_k3s; wait_gate; state
  expect T2-rolled-back "release=$before "
  SSH "grep -E 'TRIAL|ROLLBACK|COMMIT' /var/log/onemind/health-gate.log | tail -n 6" | tee -a "$EVENTS"
}

t3() {
  ev "=== T3 power cut during write"
  local before; before=$(SSH 'cat /etc/onemind-release')
  local target=v2good; [ "$before" = v2-good ] && target=v1
  SCP "$BUILD/$target-$ARCH/system.rugixb" root@127.0.0.1:/root/bundle.rugixb || return 1
  SSH 'sync; (setsid -f sh -c "rugix-ctrl update install --insecure-skip-bundle-verification --reboot set /root/bundle.rugixb >/root/update.log 2>&1; echo EXIT=\$? >>/root/update.log") </dev/null >/dev/null 2>&1'
  local t0=$SECONDS start="" w pid
  while :; do
    pid=$(SSH 'pgrep -xn rugix-ctrl' 2>/dev/null)
    if [ -n "$pid" ]; then
      w=$(SSH "awk '/^write_bytes:/{print \$2}' /proc/$pid/io" 2>/dev/null)
      # Baseline = first sample. The boot slot (256 MiB partition) is written first, so
      # cutting after CUT_MIB (default 384) of writes lands inside the system slot.
      if [ -z "$start" ] && [ -n "$w" ]; then start=$w; fi
      if [ -n "$start" ] && [ -n "$w" ] && [ $((w - start)) -ge $((${CUT_MIB:-384}*1024*1024)) ]; then
        ev "POWER CUT: SIGKILL qemu after $(( (w - start) / 1048576 )) MiB written by rugix-ctrl (pid $pid)"
        kill -9 "$(cat "$OUT/qemu.pid")"; rm -f "$OUT/qemu.pid"; break
      fi
    elif SSH 'grep -q EXIT= /root/update.log' 2>/dev/null; then
      ev "FAIL T3 install finished before the cut"; SSH cat /root/update.log >>"$EVENTS"; return 1
    fi
    [ $((SECONDS - t0)) -gt 900 ] && { ev "FAIL T3 never reached cut point"; return 1; }
    sleep 0.5
  done
  sleep 2; start_vm; wait_ssh || return 1; wait_k3s; wait_gate; state
  expect T3-old-slot-boots "release=$before "
  ev "T3: reinstall $target after the power cut"
  install_update "$target" || return 1
  wait_gate; state
  expect T3-reinstall-commits "release=${target/v2good/v2-good} "
}

# T2c: install <variant>, then without further commands report whether the gate
# committed it (gate service finished on the trial boot) or rolled back (VM rebooted).
t2c() {
  local variant=$1 before; before=$(SSH 'cat /etc/onemind-release')
  ev "=== T2c $variant (previous release: $before)"
  install_update "$variant" || return 1
  local trial_bid; trial_bid=$(boot_id); local t0=$SECONDS cur outcome=""
  while [ $((SECONDS - t0)) -lt 900 ]; do
    cur=$(boot_id || true)
    if [ -n "$cur" ] && [ "$cur" != "$trial_bid" ]; then outcome=rolled-back; break; fi
    if SSH 'systemctl show -p ActiveState --value onemind-health-gate' 2>/dev/null | grep -qx active; then outcome=committed; break; fi
    sleep 5
  done
  ev "T2c $variant outcome=${outcome:-timeout}"
  wait_gate; state
  SSH "grep -E 'TRIAL|HEALTHY|ROLLBACK|COMMIT' /var/log/onemind/health-gate.log | tail -n 6" | tee -a "$EVENTS"
  if [ "$variant" = v2noagent ]; then expect T2c-hardened-rolls-back "release=$before "; fi
}

case "${1:-all}" in
  t0) t0 ;; t1) t1 ;; t2) t2 ;; t3) t3 ;; stop) stop_vm ;;
  t2c) t2c v2noagent ;; t2c-naive) t2c v2noagentnaive ;;
  all) t0 && t1 && t2 && t3 && t2c v2noagent && t2c v2noagentnaive; stop_vm ;;
esac
