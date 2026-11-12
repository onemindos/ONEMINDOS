#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Golden-path harness: bring up a REAL hub in a fresh Debian 13 VM with deploy/install.sh --role hub,
# then run the Playwright suite (tests/e2e) from the host and deploy/verify/verify.sh on the hub.
#
#   tests/e2e/harness/run.sh --backend lima   # macOS / Linux with Lima (local runs)
#   tests/e2e/harness/run.sh --backend qemu   # Linux with QEMU/KVM (GitHub ubuntu-24.04 runners)
#
#   --out DIR      artifacts (default tests/e2e/out): install.log (tokens redacted), verify.txt,
#                  playwright-report/, test-results/ (screenshots, videos), audit.jsonl, journals
#   --port N       host port forwarded to the hub gateway's :8080 (default 18080)
#   --keep         leave the VM running afterwards (print how to reach and delete it)
#   --reuse        lima: use an existing VM of the same name (install.sh re-runs; it is idempotent)
#   --no-verify    skip deploy/verify/verify.sh      --no-playwright  skip the Playwright suite
#
# Secrets: the owner token (printed once by install.sh) and a generated agent token are kept in
# <out>/secrets (0700, never uploaded) and inside the VM under /root/e2e; on GitHub they are masked.
# The VM, its tokens and its CA are throwaway: nothing here is reused outside this run.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
E2E=$(cd "$HERE/.." && pwd)
ROOT=$(cd "$E2E/../.." && pwd)

BACKEND="" OUT="$E2E/out" PORT=${E2E_HOST_PORT:-18080} KEEP=0 REUSE=0 VERIFY=1 PLAYWRIGHT=1
NAME=${E2E_VM_NAME:-onemind-e2e} SSH_PORT=${E2E_SSH_PORT:-2222} APP=${E2E_APP:-ntfy} AGENT_ID=e2e-agent

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '[e2e %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --backend) BACKEND=${2:-}; shift 2 ;;
    --out) OUT=${2:-}; shift 2 ;;
    --port) PORT=${2:-}; shift 2 ;;
    --keep) KEEP=1; shift ;;
    --reuse) REUSE=1; shift ;;
    --no-verify) VERIFY=0; shift ;;
    --no-playwright) PLAYWRIGHT=0; shift ;;
    -h|--help) sed -n '4,19p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done
case "$BACKEND" in lima|qemu) ;; *) die "--backend lima or --backend qemu is required" ;; esac
printf '%s' "$PORT" | grep -Eqx '[0-9]{2,5}' || die "--port must be a number"
printf '%s' "$NAME" | grep -Eqx '[a-z0-9][a-z0-9-]{0,40}' || die "E2E_VM_NAME must be a short lowercase name"

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
SECRETS="$OUT/secrets" WORK="$OUT/vm"
install -d -m0700 "$SECRETS"
mkdir -p "$WORK"
exec > >(tee -a "$OUT/harness.log") 2>&1
START=$SECONDS

# ------------------------------------------------------------------------------------------
# Backends: vm_up, vm_sh CMD (stdin passes through), vm_down, vm_sh_argv (for fetch-audit.sh)
# ------------------------------------------------------------------------------------------
lima_up() {
  command -v limactl >/dev/null || die "limactl not found (brew install lima)"
  if limactl list -q 2>/dev/null | grep -qx "$NAME"; then
    [ "$REUSE" = 1 ] || die "a Lima VM named $NAME exists: pass --reuse, or limactl delete -f $NAME"
    log "lima: reusing $NAME"
    limactl start --tty=false "$NAME" >/dev/null 2>&1 || true
    return 0
  fi
  log "lima: starting $NAME (template:debian-13, 4 vCPU, 8 GiB) with $PORT -> guest 8080 only"
  # No host mounts (the repo is copied in), and only the gateway port is forwarded.
  limactl start --tty=false --name "$NAME" --cpus 4 --memory 8 --disk 30 \
    --set ".mounts=[] | .portForwards=[{\"guestPort\":8080,\"hostIP\":\"127.0.0.1\",\"hostPort\":$PORT},{\"guestPortRange\":[1,65535],\"ignore\":true}]" \
    template:debian-13
}
lima_sh() { limactl shell --workdir / "$NAME" bash -c "$1"; }
lima_down() { limactl delete -f "$NAME" >/dev/null 2>&1 || true; }

lock_value() { # lock_value KEY: a value from the e2e_vm block of os/versions.lock.yaml
  awk -v k="$1" '/^e2e_vm:/{f=1;next} f&&/^[^ #]/{f=0} f&&$1==k":"{print $2; exit}' "$ROOT/os/versions.lock.yaml"
}

SSH_OPTS=()
qemu_up() {
  for t in qemu-system-x86_64 qemu-img ssh ssh-keygen curl sha512sum; do command -v "$t" >/dev/null || die "needs $t"; done
  local url sum cache base accel seed
  url=$(lock_value amd64_url) sum=$(lock_value amd64_sha512)
  [ -n "$url" ] && [ -n "$sum" ] || die "e2e_vm amd64_url/amd64_sha512 missing from os/versions.lock.yaml"
  cache=${E2E_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/onemind-e2e}; mkdir -p "$cache"
  base="$cache/$(basename "$url")"
  if ! { [ -f "$base" ] && echo "$sum  $base" | sha512sum -c --status; }; then
    log "qemu: downloading $(basename "$url")"
    curl -fsSL --retry 3 --proto '=https' -o "$base.part" "$url"
    echo "$sum  $base.part" | sha512sum -c --status || { rm -f "$base.part"; die "sha512 mismatch for $url"; }
    mv "$base.part" "$base"
  fi
  rm -f "$WORK/disk.qcow2"
  qemu-img create -q -f qcow2 -F qcow2 -b "$base" "$WORK/disk.qcow2" 30G
  rm -f "$SECRETS/id_ed25519" "$SECRETS/id_ed25519.pub"
  ssh-keygen -q -t ed25519 -N '' -C onemind-e2e -f "$SECRETS/id_ed25519"
  cat > "$WORK/user-data" <<EOF
#cloud-config
hostname: onemind-hub
ssh_pwauth: false
users:
  - name: e2e
    sudo: "ALL=(ALL) NOPASSWD:ALL"
    shell: /bin/bash
    lock_passwd: true
    ssh_authorized_keys: ["$(cat "$SECRETS/id_ed25519.pub")"]
EOF
  printf 'instance-id: onemind-e2e-%s\nlocal-hostname: onemind-hub\n' "$(date -u +%s)" > "$WORK/meta-data"
  seed="$WORK/seed.img"
  if command -v cloud-localds >/dev/null; then cloud-localds "$seed" "$WORK/user-data" "$WORK/meta-data"
  elif command -v genisoimage >/dev/null; then genisoimage -quiet -output "$seed" -volid cidata -joliet -rock "$WORK/user-data" "$WORK/meta-data"
  elif command -v xorriso >/dev/null; then xorriso -as mkisofs -quiet -output "$seed" -volid cidata -joliet -rock "$WORK/user-data" "$WORK/meta-data"
  else die "needs cloud-localds, genisoimage or xorriso for the cloud-init seed"; fi
  if [ -r /dev/kvm ] && [ -w /dev/kvm ]; then accel=(-accel kvm -cpu host)
  else log "qemu: WARNING no usable /dev/kvm, falling back to TCG (very slow)"; accel=(-accel tcg -cpu max); fi
  log "qemu: booting Debian 13 genericcloud (4 vCPU, 8 GiB), ssh :$SSH_PORT, gateway :$PORT"
  qemu-system-x86_64 -machine q35 "${accel[@]}" -smp 4 -m 8192 \
    -drive "file=$WORK/disk.qcow2,if=virtio,format=qcow2" \
    -drive "file=$seed,if=virtio,format=raw,readonly=on" \
    -netdev "user,id=n0,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22,hostfwd=tcp:127.0.0.1:$PORT-:8080" \
    -device virtio-net-pci,netdev=n0 -display none -serial "file:$OUT/serial.log" \
    -daemonize -pidfile "$WORK/qemu.pid"
  SSH_OPTS=(-q -p "$SSH_PORT" -i "$SECRETS/id_ed25519" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
            -o LogLevel=ERROR -o ConnectTimeout=5 -o BatchMode=yes e2e@127.0.0.1)
  local i
  for i in $(seq 1 240); do ssh "${SSH_OPTS[@]}" true 2>/dev/null && break; sleep 5; done
  [ "$i" -lt 240 ] || die "the VM did not come up on ssh in 20 minutes (see serial.log)"
  ssh "${SSH_OPTS[@]}" 'cloud-init status --wait >/dev/null 2>&1 || true'
}
# shellcheck disable=SC2029  # the command is meant to expand on the VM
qemu_sh() { ssh "${SSH_OPTS[@]}" "$1"; }
qemu_down() { [ -f "$WORK/qemu.pid" ] && kill "$(cat "$WORK/qemu.pid")" 2>/dev/null; rm -f "$WORK/qemu.pid"; }

vm_up() { "${BACKEND}_up"; }
vm_sh() { "${BACKEND}_sh" "$1"; }
vm_down() { "${BACKEND}_down"; }

cleanup() {
  local rc=$?
  if [ "$KEEP" = 1 ]; then
    log "VM kept: gateway at http://127.0.0.1:$PORT (owner token in $SECRETS/owner.token)"
    [ "$BACKEND" = lima ] && log "delete with: limactl delete -f $NAME"
    [ "$BACKEND" = qemu ] && log "stop with: kill \$(cat $WORK/qemu.pid)"
  else
    vm_down
  fi
  exit "$rc"
}
trap cleanup EXIT

mask() { [ -n "${GITHUB_ACTIONS:-}" ] && printf '::add-mask::%s\n' "$1"; return 0; }
sha256() { openssl dgst -sha256 -r | cut -d' ' -f1; }

# ------------------------------------------------------------------------------------------
# 1. VM and repository
# ------------------------------------------------------------------------------------------
vm_up
log "copying the working tree into the VM"
(cd "$ROOT" && git ls-files -co --exclude-standard -z \
  | while IFS= read -r -d '' f; do [ -e "$f" ] && printf '%s\0' "$f"; done \
  | COPYFILE_DISABLE=1 tar --null -T - -czf -) \
  | vm_sh 'rm -rf ~/onemind && mkdir ~/onemind && tar --warning=no-unknown-keyword -xzf - -C ~/onemind'

# ------------------------------------------------------------------------------------------
# 2. deploy/install.sh --role hub (the real thing, as a developer would run it)
# ------------------------------------------------------------------------------------------
log "running deploy/install.sh --role hub inside the VM"
T0=$SECONDS
set +e
vm_sh 'cd ~/onemind && sudo bash -c "deploy/install.sh --role hub > /root/e2e-install.log 2>&1"'
INSTALL_RC=$?
set -e
INSTALL_S=$((SECONDS - T0))
# The log holds the owner token (printed once) and the k3s join token: redact both before saving it.
vm_sh "sudo sed -E 's/^( {4})[0-9a-f]{64}\$/\\1<owner token redacted>/; s/(--token )[^ ]+/\\1<join token redacted>/' /root/e2e-install.log" > "$OUT/install.log" || true
[ "$INSTALL_RC" = 0 ] || { tail -n 40 "$OUT/install.log"; die "install.sh failed (rc $INSTALL_RC) after ${INSTALL_S}s"; }
log "install.sh rc 0 in ${INSTALL_S}s"

# The owner token: from this install's output, or kept from an earlier run of this VM (--reuse).
# shellcheck disable=SC2016  # expands inside the VM
vm_sh 'sudo bash -c '\''umask 077; install -d -m0700 /root/e2e
  t=$(awk "/^OWNER TOKEN/{f=1;next} f&&NF{print \$1; exit}" /root/e2e-install.log)
  [ -n "$t" ] && printf %s "$t" > /root/e2e/owner.token; test -s /root/e2e/owner.token'\''' \
  || die "no owner token: the hub was installed before this harness ran (uninstall it or delete the VM)"
(umask 077; vm_sh 'sudo cat /root/e2e/owner.token' > "$SECRETS/owner.token")
mask "$(cat "$SECRETS/owner.token")"

# An agent principal (contract §3 static token, kind agent), as the owner would add one by hand.
[ -s "$SECRETS/agent.token" ] || (umask 077; openssl rand -hex 32 | tr -d '\n' > "$SECRETS/agent.token")
mask "$(cat "$SECRETS/agent.token")"
AGENT_HASH=$(sha256 < "$SECRETS/agent.token")
vm_sh "sudo grep -q 'sha256:$AGENT_HASH' /etc/onemind/tokens.yaml || printf '  \"sha256:%s\": {id: $AGENT_ID, kind: agent, role: agent}\n' $AGENT_HASH | sudo tee -a /etc/onemind/tokens.yaml >/dev/null"
vm_sh "sudo bash -c 'umask 077; cat > /root/e2e/agent.token'" < "$SECRETS/agent.token"

# §10.3 "nothing unscanned runs": the hub refuses installs without a fresh passing scan.json.
# The §9.4 app-gate that writes it on the hub is not merged yet (PR #25), so this run gives the
# test app a scan record; every other app stays unscanned and the suite checks it is blocked.
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '{"scanned_at": "%s", "result": "pass", "images": [], "smoke": "skipped",\n "e2e_fixture": "tests/e2e/harness/run.sh: stands in for the 9.4 app-gate until it runs on the hub"}\n' "$NOW" \
  | vm_sh "sudo bash -c 'cat > /opt/onemind/apps/$APP/scan.json'"

HUB="http://127.0.0.1:$PORT"
for i in $(seq 1 60); do curl -fsS "$HUB/healthz" >/dev/null 2>&1 && break; sleep 2; done
[ "$i" -lt 60 ] || die "the gateway is not reachable from the host at $HUB"
log "gateway reachable from the host at $HUB"

# The suite reads the hub's audit log through this script (no shell, fixed command).
{
  printf '#!/bin/sh\n# Generated by tests/e2e/harness/run.sh: print the hub audit log.\n'
  if [ "$BACKEND" = lima ]; then printf 'exec limactl shell --workdir / %q sudo cat /var/lib/onemind/audit.jsonl\n' "$NAME"
  else printf 'exec ssh'; printf ' %q' "${SSH_OPTS[@]}"; printf ' sudo cat /var/lib/onemind/audit.jsonl\n'; fi
} > "$WORK/fetch-audit.sh"
chmod 0700 "$WORK/fetch-audit.sh"

# ------------------------------------------------------------------------------------------
# 3. Playwright from the host, then verify.sh on the hub (it re-checks the whole audit chain)
# ------------------------------------------------------------------------------------------
PW_RC=0 VERIFY_RC=0
if [ "$PLAYWRIGHT" = 1 ]; then
  log "Playwright: dashboard + MCP agent + audit against $HUB"
  (cd "$E2E" && { [ -d node_modules ] || npm ci --ignore-scripts --no-audit --no-fund; } \
    && npx playwright install ${E2E_PW_WITH_DEPS:+--with-deps} chromium >/dev/null)
  rm -f "$OUT/golden-actions.jsonl"   # lib/runlog.ts: the action ids of this run only
  set +e
  (cd "$E2E" && E2E_HUB_URL="$HUB" E2E_OWNER_TOKEN_FILE="$SECRETS/owner.token" \
    E2E_AGENT_TOKEN_FILE="$SECRETS/agent.token" E2E_AGENT_ID="$AGENT_ID" E2E_APP="$APP" \
    E2E_AUDIT_FETCH="$WORK/fetch-audit.sh" E2E_OUT="$OUT" npx playwright test --project=unit --project=golden)
  PW_RC=$?
  set -e
fi
if [ "$VERIFY" = 1 ]; then
  log "deploy/verify/verify.sh on the hub"
  set +e
  vm_sh "cd ~/onemind && sudo deploy/verify/verify.sh http://127.0.0.1:8080 --app $APP --token-file /root/e2e/owner.token --agent-token-file /root/e2e/agent.token --audit-file /var/lib/onemind/audit.jsonl" > "$OUT/verify.txt" 2>&1
  VERIFY_RC=$?
  set -e
  tail -n 3 "$OUT/verify.txt"
fi

# ------------------------------------------------------------------------------------------
# 4. Evidence
# ------------------------------------------------------------------------------------------
vm_sh 'sudo cat /var/lib/onemind/audit.jsonl' > "$OUT/audit.jsonl" 2>/dev/null || true
vm_sh 'sudo journalctl -u onemind-gateway -u onemindd -u onemind-nats --no-pager -n 3000' > "$OUT/journal.txt" 2>&1 || true
vm_sh 'sudo k3s kubectl get nodes,pods,ns -A -o wide' > "$OUT/k8s.txt" 2>&1 || true
{
  printf 'backend: %s\nhost: %s %s\n' "$BACKEND" "$(uname -s)" "$(uname -m)"
  # shellcheck disable=SC2016  # expands inside the VM
  printf 'guest: %s\n' "$(vm_sh '. /etc/os-release; printf "%s, kernel %s, %s" "$PRETTY_NAME" "$(uname -r)" "$(dpkg --print-architecture)"')"
  printf 'commit: %s%s\n' "$(git -C "$ROOT" rev-parse --short HEAD)" "$(git -C "$ROOT" diff --quiet HEAD -- . ':!tests/e2e/out' || echo ' (+ uncommitted changes)')"
  printf 'install.sh: rc %s in %ss\n' "$INSTALL_RC" "$INSTALL_S"
  [ "$PLAYWRIGHT" = 1 ] && printf 'playwright: rc %s\n' "$PW_RC"
  [ "$VERIFY" = 1 ] && printf 'verify.sh: rc %s, %s\n' "$VERIFY_RC" "$(grep -E '^Summary:' "$OUT/verify.txt" | tail -n1)"
  printf 'total: %ss\n' "$((SECONDS - START))"
} | tee "$OUT/summary.txt"

[ "$PW_RC" = 0 ] && [ "$VERIFY_RC" = 0 ] || die "golden path FAILED (playwright rc $PW_RC, verify.sh rc $VERIFY_RC)"
log "golden path green"
