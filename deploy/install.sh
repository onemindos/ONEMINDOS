#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# OneMind OS developer install (P6), contract sdk/contracts/poc-v0.md section 6.
#
# UNSUPPORTED DEVELOPER INSTALL, NO OS ROLLBACK (REC-DEC-30).
# It puts the OneMind stack on top of a stock OS (Debian 13, Raspberry Pi OS
# trixie, Jetson L4T Ubuntu, a DigitalOcean Debian 13 droplet). The real product
# is the read-only A/B image from os/; this script exists so we can prove the
# stack on real hardware today.
#
#   sudo ./deploy/install.sh --role hub  [--gateway-image-tar FILE | --gateway-image REF] [--onemindd-bin FILE]
#   sudo ./deploy/install.sh --role node --hub <host-or-url> --token <join-token> [--onemindd-bin FILE]
#   ./deploy/install.sh --role hub --dry-run --target debian13     # print every step, change nothing
#
# Run it from a clone of the repo (it reads apps/, dashboard/dist and
# deploy/systemd/ by path). It is idempotent: running it again converges.
set -euo pipefail

# ---------------------------------------------------------------- pins
# Sources: research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md (k3s v1.37.2+k3s1,
# NATS v2.15.2); hashes re-checked against the upstream release checksum files
# on 2026-11-11 (k3s sha256sum-<arch>.txt, nats SHA256SUMS) and matching
# research-output/evidence/lab/{k3s-footprint-restore,w8-nats-leaf-buffer}.
K3S_VERSION="v1.37.2+k3s1"
K3S_URL_BASE="https://github.com/k3s-io/k3s/releases/download/v1.37.2%2Bk3s1"
K3S_INSTALLER_URL="https://raw.githubusercontent.com/k3s-io/k3s/v1.37.2%2Bk3s1/install.sh"
K3S_INSTALLER_SHA256="ed01f89fd977bf20ac1516bbebf8370bf3ddbaa55dac8aba610956a4c78cc00b"
K3S_SHA256_AMD64="265b3ee6a3198ef14033c63ef46cbb32370d83795199fb6d1b01f21575eddbda"
K3S_SHA256_ARM64="a779ccf1e5e2e33a62f5a29c2f1c0bbf99431e100579d4c10f0aa0742a6aa84b"
NATS_VERSION="v2.15.2"
NATS_URL_BASE="https://github.com/nats-io/nats-server/releases/download/v2.15.2"
NATS_SHA256_AMD64="67cb8e10bc6f0c4b47f75a728529a20953dbae2a4f9a4a52ae8517d65ae303ff"
NATS_SHA256_ARM64="bc2c788dcbf2849af749564e06a0d48c19bced851f2d68a2e21c54d078949b28"

# ---------------------------------------------------------------- paths
ONEMIND_ETC=/etc/onemind
ONEMIND_OPT=/opt/onemind
ONEMIND_VAR=/var/lib/onemind
GATEWAY_PORT=8080
NATS_PORT=4222
K3S_API_PORT=6443

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---------------------------------------------------------------- options
ROLE=""
HUB=""
JOIN_TOKEN=""
NATS_URL_OVERRIDE=""
DRY_RUN=0
ASSUME_YES=0
TARGET=""
ARCH_OVERRIDE=""
ONEMINDD_BIN=""
ONEMINDD_URL=""
ONEMINDD_SHA256=""
SKIP_ONEMINDD=0
GATEWAY_IMAGE=""
GATEWAY_IMAGE_TAR=""
SKIP_GATEWAY=0
DASHBOARD_DIST=""
BUNDLE=""
APPS_DIR=""
FORCE_OS=0

usage() {
  cat <<'EOF'
Usage: install.sh --role hub|node [options]

Roles
  --role hub                 k3s server + NATS + OneMind gateway/dashboard + onemindd
  --role node                k3s agent joining the hub + onemindd
Joining (node only)
  --hub HOST|URL             the hub's address (e.g. beelink.lan or https://192.0.2.10:6443)
  --token JOIN               the join token the hub printed (omj1.<nats>.<k3s>)
  --nats-url URL             override the NATS URL (default nats://<token>@<hub>:4222)
Components
  --bundle DIR               output of ./deploy/bundle.sh on the Mac (onemindd, gateway image, dashboard)
  --onemindd-bin FILE        onemindd binary built from cmd/onemindd for this arch
  --onemindd-url URL --onemindd-sha256 HEX
                             download onemindd from a release (placeholder until releases exist)
  --skip-onemindd            do not install onemindd (the machine will not appear in Nodes)
  --gateway-image-tar FILE   gateway image tar built from core/Dockerfile (imported into k3s)
  --gateway-image REF        gateway image reference to pull instead
  --skip-gateway             hub without the gateway/dashboard (k3s + NATS only)
  --dashboard-dist DIR       built dashboard (default: <repo>/dashboard/dist)
  --apps-dir DIR             app catalog (default: <repo>/apps)
Behaviour
  --dry-run                  print every step and change nothing (no root needed)
  --target T                 pretend to be T (debian13|rpi5|jetson|do) - for --dry-run on another machine
  --arch amd64|arm64         override the detected architecture (with --target)
  --force                    continue on an OS this script does not know
  --yes                      do not ask for confirmation
  -h, --help                 this help
EOF
}

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
log() { printf '==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --role) ROLE="${2:-}"; shift 2 ;;
    --hub) HUB="${2:-}"; shift 2 ;;
    --token) JOIN_TOKEN="${2:-}"; shift 2 ;;
    --nats-url) NATS_URL_OVERRIDE="${2:-}"; shift 2 ;;
    --bundle) BUNDLE="${2:-}"; shift 2 ;;
    --onemindd-bin) ONEMINDD_BIN="${2:-}"; shift 2 ;;
    --onemindd-url) ONEMINDD_URL="${2:-}"; shift 2 ;;
    --onemindd-sha256) ONEMINDD_SHA256="${2:-}"; shift 2 ;;
    --skip-onemindd) SKIP_ONEMINDD=1; shift ;;
    --gateway-image) GATEWAY_IMAGE="${2:-}"; shift 2 ;;
    --gateway-image-tar) GATEWAY_IMAGE_TAR="${2:-}"; shift 2 ;;
    --skip-gateway) SKIP_GATEWAY=1; shift ;;
    --dashboard-dist) DASHBOARD_DIST="${2:-}"; shift 2 ;;
    --apps-dir) APPS_DIR="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --target) TARGET="${2:-}"; shift 2 ;;
    --arch) ARCH_OVERRIDE="${2:-}"; shift 2 ;;
    --force) FORCE_OS=1; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
done

case "$ROLE" in hub|node) ;; *) usage >&2; die "--role hub|node is required" ;; esac
DASHBOARD_DIST_DEFAULT="$REPO_DIR/dashboard/dist"
APPS_DIR="${APPS_DIR:-$REPO_DIR/apps}"

# ---------------------------------------------------------------- dry-run helpers
# Every state-changing step goes through run/write_file/install_file, so
# --dry-run prints the complete plan and touches nothing.
STEP=0
step() { STEP=$((STEP + 1)); printf '\n[%02d] %s\n' "$STEP" "$*"; }

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  + %s\n' "$*"
  else
    printf '  + %s\n' "$*"
    "$@"
  fi
}

# write_file PATH MODE  (content on stdin); secrets=1 hides the content in dry-run
write_file() {
  local path="$1" mode="$2" secret="${3:-0}" content
  content="$(cat)"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  + write %s (mode %s)\n' "$path" "$mode"
    if [ "$secret" -eq 1 ]; then
      printf '      <secret content, generated on the machine, not shown>\n'
    else
      printf '%s\n' "$content" | sed 's/^/      | /'
    fi
    return 0
  fi
  if [ -f "$path" ] && [ "$(cat "$path")" = "$content" ]; then
    printf '  = %s unchanged\n' "$path"
    return 0
  fi
  printf '  + write %s (mode %s)\n' "$path" "$mode"
  install -d -m 0755 "$(dirname "$path")"
  local tmp
  tmp="$(mktemp "$path.XXXXXX")"
  chmod "$mode" "$tmp"
  printf '%s\n' "$content" > "$tmp"
  mv -f "$tmp" "$path"
}

# download URL DEST SHA256 - verifies the hash before the file is used
download() {
  local url="$1" dest="$2" sha="$3"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  + download %s\n      -> %s (sha256 must be %s)\n' "$url" "$dest" "$sha"
    return 0
  fi
  if [ -f "$dest" ] && [ "$(sha256sum "$dest" | cut -d' ' -f1)" = "$sha" ]; then
    printf '  = %s already present, sha256 ok\n' "$dest"
    return 0
  fi
  printf '  + download %s\n' "$url"
  local tmp
  tmp="$(mktemp "$dest.XXXXXX")"
  curl -fsSL --retry 3 -o "$tmp" "$url"
  local got
  got="$(sha256sum "$tmp" | cut -d' ' -f1)"
  if [ "$got" != "$sha" ]; then
    rm -f "$tmp"
    die "sha256 mismatch for $url: expected $sha, got $got"
  fi
  printf '    sha256 ok %s\n' "$got"
  mv -f "$tmp" "$dest"
}

# sha256 pins per architecture
k3s_sha() { if [ "$ARCH" = arm64 ]; then echo "$K3S_SHA256_ARM64"; else echo "$K3S_SHA256_AMD64"; fi; }
nats_sha() { if [ "$ARCH" = arm64 ]; then echo "$NATS_SHA256_ARM64"; else echo "$NATS_SHA256_AMD64"; fi; }

random_hex() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
sha256_hex() { printf '%s' "$1" | sha256sum | cut -d' ' -f1; }
OWNER_TOKEN="" AGENT_TOKEN="" FRESH_TOKENS=0

# ---------------------------------------------------------------- banner
banner() {
  cat <<EOF
==========================================================================
  OneMind OS - UNSUPPORTED DEVELOPER INSTALL, NO OS ROLLBACK
  (P6, REC-DEC-30). This installs k3s, NATS and OneMind services on top of
  the existing OS. A bad change here is NOT rolled back automatically.
  Use spare hardware. The supported install is the A/B image from os/.
==========================================================================
EOF
}

# ---------------------------------------------------------------- detection
OS_ID="" OS_VERSION_ID="" OS_PRETTY="" BOARD="" ARCH="" TARGET_KIND=""

detect() {
  if [ -n "$TARGET" ]; then
    [ "$DRY_RUN" -eq 1 ] || die "--target is only for --dry-run; on a real machine the OS is detected"
    case "$TARGET" in
      debian13) OS_ID=debian; OS_VERSION_ID=13; OS_PRETTY="Debian GNU/Linux 13 (trixie)"; BOARD=x86_64-efi; ARCH=amd64 ;;
      rpi5) OS_ID=debian; OS_VERSION_ID=13; OS_PRETTY="Raspberry Pi OS (trixie)"; BOARD=rpi5; ARCH=arm64 ;;
      jetson) OS_ID=ubuntu; OS_VERSION_ID=22.04; OS_PRETTY="Ubuntu 22.04 (NVIDIA L4T)"; BOARD=jetson-orin; ARCH=arm64 ;;
      do) OS_ID=debian; OS_VERSION_ID=13; OS_PRETTY="Debian GNU/Linux 13 (trixie)"; BOARD=vm-do; ARCH=amd64 ;;
      *) die "--target must be debian13|rpi5|jetson|do" ;;
    esac
    [ -z "$ARCH_OVERRIDE" ] || ARCH="$ARCH_OVERRIDE"
    TARGET_KIND="$TARGET"
    return 0
  fi
  [ -r /etc/os-release ] || die "/etc/os-release not found: this is not a supported Linux"
  # shellcheck disable=SC1091
  . /etc/os-release
  OS_ID="${ID:-unknown}"; OS_VERSION_ID="${VERSION_ID:-unknown}"; OS_PRETTY="${PRETTY_NAME:-unknown}"
  case "$(uname -m)" in
    x86_64|amd64) ARCH=amd64 ;;
    aarch64|arm64) ARCH=arm64 ;;
    *) die "unsupported CPU architecture $(uname -m) (need x86_64 or aarch64)" ;;
  esac
  [ -z "$ARCH_OVERRIDE" ] || ARCH="$ARCH_OVERRIDE"
  # Board detection follows contract section 2.
  local model="" vendor="" virt=""
  [ -r /proc/device-tree/model ] && model="$(tr -d '\0' < /proc/device-tree/model)"
  [ -r /sys/class/dmi/id/sys_vendor ] && vendor="$(cat /sys/class/dmi/id/sys_vendor)"
  command -v systemd-detect-virt >/dev/null 2>&1 && virt="$(systemd-detect-virt 2>/dev/null || true)"
  if printf '%s' "$model" | grep -q 'Raspberry Pi 5'; then BOARD=rpi5
  elif [ -e /etc/nv_tegra_release ]; then BOARD=jetson-orin
  elif [ "$vendor" = "DigitalOcean" ]; then BOARD=vm-do
  elif [ -n "$virt" ] && [ "$virt" != "none" ]; then BOARD=vm
  elif [ -d /sys/firmware/efi ] && [ "$ARCH" = amd64 ]; then BOARD=x86_64-efi
  elif [ -d /sys/firmware/efi ] && [ "$ARCH" = arm64 ]; then BOARD=arm64-efi
  else BOARD=unknown
  fi
  case "$BOARD" in
    rpi5) TARGET_KIND=rpi5 ;;
    jetson-orin) TARGET_KIND=jetson ;;
    vm-do) TARGET_KIND='do' ;;
    *) TARGET_KIND=debian13 ;;
  esac
  if printf '%s' "$model" | grep -q 'Raspberry Pi' && [ "$BOARD" != rpi5 ]; then
    warn "this Raspberry Pi is not a Pi 5; only the Pi 5 is a v0 board (lesson 06 section 5)"
  fi
}

check_supported() {
  local ok=0
  case "$TARGET_KIND" in
    debian13|do|rpi5) [ "$OS_ID" = debian ] && [ "$OS_VERSION_ID" = 13 ] && ok=1 ;;
    jetson) [ "$OS_ID" = ubuntu ] && case "$OS_VERSION_ID" in 22.04|24.04) ok=1 ;; esac ;;
  esac
  if [ "$ok" -ne 1 ]; then
    if [ "$FORCE_OS" -eq 1 ]; then
      warn "unsupported OS '$OS_PRETTY' on board '$BOARD'; continuing because of --force"
    else
      die "unsupported OS '$OS_PRETTY' on board '$BOARD'. Supported: Debian 13, Raspberry Pi OS trixie (Pi 5), Jetson L4T Ubuntu 22.04/24.04, DigitalOcean Debian 13. Use --force to try anyway."
    fi
  fi
}

# ---------------------------------------------------------------- join helpers
HUB_HOST=""
parse_hub() {
  local h="$1"
  h="${h#*://}"; h="${h%%/*}"
  case "$h" in
    \[*\]*) h="${h%%]*}"; h="${h#[}" ;;  # [v6]:port
    *:*:*) ;;                              # bare IPv6
    *) h="${h%%:*}" ;;
  esac
  [ -n "$h" ] || die "cannot read a host from --hub '$1'"
  HUB_HOST="$h"
}

NATS_TOKEN="" K3S_JOIN=""
parse_join_token() {
  local t="$1"
  case "$t" in
    omj1.*.*)
      local rest="${t#omj1.}"
      NATS_TOKEN="${rest%%.*}"
      K3S_JOIN="${rest#*.}"
      ;;
    *) K3S_JOIN="$t"; NATS_TOKEN="" ;;
  esac
  [ -n "$K3S_JOIN" ] || die "the join token is empty"
}

# ---------------------------------------------------------------- steps
step_prereqs() {
  step "Install prerequisites (curl, ca-certificates, iptables, ...)"
  local pkgs="curl ca-certificates iptables tar gzip coreutils python3"
  local missing="" p
  for p in curl sha256sum tar iptables python3; do
    command -v "$p" >/dev/null 2>&1 || missing=1
  done
  if [ "$DRY_RUN" -eq 1 ] || [ -n "$missing" ]; then
    run env DEBIAN_FRONTEND=noninteractive apt-get update -q
    # shellcheck disable=SC2086
    run env DEBIAN_FRONTEND=noninteractive apt-get install -y -q $pkgs
  else
    printf '  = prerequisites present\n'
  fi
  run install -d -m 0755 "$ONEMIND_OPT" "$ONEMIND_OPT/bin"
  run install -d -m 0700 "$ONEMIND_ETC" "$ONEMIND_VAR"
}

step_pi_cgroups() {
  [ "$TARGET_KIND" = rpi5 ] || return 0
  step "Raspberry Pi 5: make sure the memory cgroup is on (k3s needs it)"
  local cmdline=/boot/firmware/cmdline.txt
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  + if /sys/fs/cgroup/cgroup.controllers lacks "memory": append "cgroup_enable=memory cgroup_memory=1" to %s, then ask for a reboot and stop\n' "$cmdline"
    return 0
  fi
  if grep -qw memory /sys/fs/cgroup/cgroup.controllers 2>/dev/null; then
    printf '  = memory cgroup enabled\n'
    return 0
  fi
  [ -f "$cmdline" ] || die "$cmdline not found; enable the memory cgroup by hand"
  if ! grep -q 'cgroup_enable=memory' "$cmdline"; then
    run cp "$cmdline" "$cmdline.onemind-backup"
    run sed -i '1 s/$/ cgroup_enable=memory cgroup_memory=1/' "$cmdline"
  fi
  printf '\n  The memory cgroup is enabled on the next boot. Reboot, then run this command again.\n'
  exit 3
}

step_k3s() {
  local bin_name=k3s
  [ "$ARCH" = arm64 ] && bin_name=k3s-arm64
  step "k3s $K3S_VERSION ($([ "$ROLE" = hub ] && echo server || echo agent)), binary and installer verified by sha256"
  if [ "$DRY_RUN" -eq 0 ] && command -v k3s >/dev/null 2>&1 \
     && k3s --version 2>/dev/null | grep -qF "$K3S_VERSION" \
     && systemctl is-active --quiet "$([ "$ROLE" = hub ] && echo k3s || echo k3s-agent)"; then
    printf '  = k3s %s already installed and running\n' "$K3S_VERSION"
    return 0
  fi
  download "$K3S_URL_BASE/$bin_name" /usr/local/bin/k3s "$(k3s_sha)"
  run chmod 0755 /usr/local/bin/k3s
  download "$K3S_INSTALLER_URL" "$ONEMIND_OPT/k3s-install.sh" "$K3S_INSTALLER_SHA256"
  if [ "$ROLE" = hub ]; then
    # SQLite datastore (BD-11); secrets encrypted at rest; kubeconfig root-only.
    run env INSTALL_K3S_SKIP_DOWNLOAD=true INSTALL_K3S_VERSION="$K3S_VERSION" \
      INSTALL_K3S_EXEC="server --write-kubeconfig-mode 0600 --secrets-encryption --node-label onemind.io/role=hub" \
      sh "$ONEMIND_OPT/k3s-install.sh"
  else
    # The token goes through the environment, never the process list or a file in the repo.
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '  + env INSTALL_K3S_SKIP_DOWNLOAD=true INSTALL_K3S_VERSION=%s K3S_URL=https://%s:%s K3S_TOKEN=<from join token> INSTALL_K3S_EXEC="agent --node-label onemind.io/role=node" sh %s\n' \
        "$K3S_VERSION" "$HUB_HOST" "$K3S_API_PORT" "$ONEMIND_OPT/k3s-install.sh"
    else
      printf '  + k3s installer (agent) joining https://%s:%s\n' "$HUB_HOST" "$K3S_API_PORT"
      INSTALL_K3S_SKIP_DOWNLOAD=true INSTALL_K3S_VERSION="$K3S_VERSION" \
        K3S_URL="https://$HUB_HOST:$K3S_API_PORT" K3S_TOKEN="$K3S_JOIN" \
        INSTALL_K3S_EXEC="agent --node-label onemind.io/role=node" \
        sh "$ONEMIND_OPT/k3s-install.sh"
    fi
  fi
}

step_secrets_hub() {
  step "Generate hub secrets once (NATS token, owner and agent API tokens), root-only in $ONEMIND_ETC"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  + if missing: create %s/nats.token and %s/tokens.yaml (0600) from /dev/urandom\n' "$ONEMIND_ETC" "$ONEMIND_ETC"
    return 0
  fi
  if [ ! -s "$ONEMIND_ETC/nats.token" ]; then
    (umask 077; random_hex > "$ONEMIND_ETC/nats.token")
    printf '  + created %s/nats.token\n' "$ONEMIND_ETC"
  else
    printf '  = %s/nats.token exists\n' "$ONEMIND_ETC"
  fi
  if [ ! -s "$ONEMIND_ETC/tokens.yaml" ]; then
    # Contract section 3: ONEMIND_TOKENS_FILE maps each token to a principal {id, kind, role}.
    # Only the sha256 of each token is stored (core/ accepts "sha256:<hex>" keys); the
    # tokens themselves are printed once at the end and kept nowhere on disk.
    OWNER_TOKEN="$(random_hex)"; AGENT_TOKEN="$(random_hex)"
    (umask 077; cat > "$ONEMIND_ETC/tokens.yaml" <<EOF
# Generated by deploy/install.sh on this machine (sha256 hashes only). Never copy into the repo.
# To issue new tokens: delete this file and run install.sh --role hub again.
tokens:
  "sha256:$(sha256_hex "$OWNER_TOKEN")": {id: owner, kind: person, role: owner}
  "sha256:$(sha256_hex "$AGENT_TOKEN")": {id: dev-agent, kind: agent, role: agent}
EOF
    )
    printf '  + created %s/tokens.yaml (owner + dev-agent, hashes only)\n' "$ONEMIND_ETC"
    FRESH_TOKENS=1
  else
    printf '  = %s/tokens.yaml exists (tokens are not shown again; delete the file and re-run to issue new ones)\n' "$ONEMIND_ETC"
  fi
  NATS_TOKEN="$(cat "$ONEMIND_ETC/nats.token")"
}

step_nats() {
  local tarball="nats-server-$NATS_VERSION-linux-$ARCH.tar.gz"
  step "NATS $NATS_VERSION on the hub (:$NATS_PORT, token auth), tarball verified by sha256"
  download "$NATS_URL_BASE/$tarball" "$ONEMIND_OPT/$tarball" "$(nats_sha)"
  run tar -xzf "$ONEMIND_OPT/$tarball" -C "$ONEMIND_OPT" --no-same-owner
  run install -m 0755 "$ONEMIND_OPT/nats-server-$NATS_VERSION-linux-$ARCH/nats-server" "$ONEMIND_OPT/bin/nats-server"
  run install -d -m 0700 "$ONEMIND_VAR/nats"
  write_file "$ONEMIND_ETC/nats.conf" 0600 1 <<EOF
# OneMind hub NATS (v0: nodes publish straight here; leaf nodes come later)
listen: "0.0.0.0:$NATS_PORT"
http: "127.0.0.1:8222"
server_name: onemind-hub
authorization { token: "$NATS_TOKEN" }
jetstream { store_dir: "$ONEMIND_VAR/nats", max_memory_store: 64MB, max_file_store: 1GB }
EOF
  write_file /etc/systemd/system/onemind-nats.service 0644 <<EOF
[Unit]
Description=OneMind hub NATS server ($NATS_VERSION)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=$ONEMIND_OPT/bin/nats-server -c $ONEMIND_ETC/nats.conf
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$ONEMIND_VAR/nats
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
  run systemctl daemon-reload
  run systemctl enable onemind-nats.service
  run systemctl restart onemind-nats.service
}

# --bundle DIR: the folder ./deploy/bundle.sh made on the Mac for this machine's arch.
# Explicit --onemindd-bin / --gateway-image-tar / --dashboard-dist still win.
apply_bundle() {
  if [ -n "$BUNDLE" ]; then
    if [ "$DRY_RUN" -eq 0 ]; then
      [ -d "$BUNDLE" ] || die "bundle not found: $BUNDLE"
      [ -f "$BUNDLE/onemindd-linux-$ARCH" ] || die "bundle $BUNDLE has no onemindd-linux-$ARCH: build it with ./deploy/bundle.sh --arch $ARCH"
      if [ -f "$BUNDLE/SHA256SUMS" ]; then
        printf '  checking %s/SHA256SUMS\n' "$BUNDLE"
        (cd "$BUNDLE" && sha256sum --quiet -c SHA256SUMS) || die "bundle checksum mismatch in $BUNDLE (copy it again)"
      fi
    fi
    [ -n "$ONEMINDD_BIN" ] || ONEMINDD_BIN="$BUNDLE/onemindd-linux-$ARCH"
    if [ "$ROLE" = hub ]; then
      if [ -z "$GATEWAY_IMAGE_TAR" ] && [ -z "$GATEWAY_IMAGE" ]; then
        GATEWAY_IMAGE_TAR="$BUNDLE/onemind-gateway-linux-$ARCH.tar"
        GATEWAY_IMAGE="onemind/gateway:dev"
      fi
      [ -n "$DASHBOARD_DIST" ] || DASHBOARD_DIST="$BUNDLE/dashboard"
    fi
  fi
  [ -n "$DASHBOARD_DIST" ] || DASHBOARD_DIST="$DASHBOARD_DIST_DEFAULT"
}

resolve_onemindd() {
  ONEMINDD_SRC=""
  if [ "$SKIP_ONEMINDD" -eq 1 ]; then return 0; fi
  if [ -n "$ONEMINDD_BIN" ]; then
    ONEMINDD_SRC="$ONEMINDD_BIN"
  elif [ -n "$ONEMINDD_URL" ]; then
    [ -n "$ONEMINDD_SHA256" ] || die "--onemindd-url needs --onemindd-sha256"
    ONEMINDD_SRC="url"
  else
    local c
    for c in "$REPO_DIR/dist/onemindd-linux-$ARCH" "$REPO_DIR/cmd/onemindd/dist/onemindd-linux-$ARCH"; do
      if [ -f "$c" ]; then ONEMINDD_SRC="$c"; break; fi
    done
  fi
  if [ -z "$ONEMINDD_SRC" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      ONEMINDD_SRC="$REPO_DIR/cmd/onemindd/dist/onemindd-linux-$ARCH"
      warn "no onemindd binary found; the dry run assumes $ONEMINDD_SRC (on the Mac: ./deploy/bundle.sh --arch $ARCH, or make -C cmd/onemindd build)"
    else
      die "no onemindd binary. On the Mac run ./deploy/bundle.sh --arch $ARCH, copy the bundle here and pass --bundle DIR (or --onemindd-bin FILE, or --skip-onemindd)"
    fi
  fi
}

step_onemindd() {
  [ "$SKIP_ONEMINDD" -eq 0 ] || { warn "skipping onemindd: this machine will not appear in Nodes"; return 0; }
  step "onemindd node agent as a systemd service (role $ROLE, local API :7480)"
  if [ "$ONEMINDD_SRC" = url ]; then
    download "$ONEMINDD_URL" "$ONEMIND_OPT/bin/onemindd" "$ONEMINDD_SHA256"
    run chmod 0755 "$ONEMIND_OPT/bin/onemindd"
  else
    if [ "$DRY_RUN" -eq 0 ] && [ ! -f "$ONEMINDD_SRC" ]; then die "onemindd binary not found: $ONEMINDD_SRC"; fi
    run install -m 0755 "$ONEMINDD_SRC" "$ONEMIND_OPT/bin/onemindd"
  fi
  run ln -sf "$ONEMIND_OPT/bin/onemindd" /usr/local/bin/onemindd
  local nats_url
  if [ "$ROLE" = hub ]; then
    nats_url="nats://$NATS_TOKEN@127.0.0.1:$NATS_PORT"
  elif [ -n "$NATS_URL_OVERRIDE" ]; then
    nats_url="$NATS_URL_OVERRIDE"
  elif [ -n "$NATS_TOKEN" ]; then
    nats_url="nats://$NATS_TOKEN@$HUB_HOST:$NATS_PORT"
  else
    nats_url="nats://$HUB_HOST:$NATS_PORT"
    warn "join token has no NATS part; using $nats_url without auth"
  fi
  write_file "$ONEMIND_ETC/onemindd.env" 0600 1 <<EOF
ONEMIND_NATS_URL=$nats_url
ONEMIND_NODE_ROLE=$ROLE
EOF
  # The hardened unit lives in deploy/systemd/ (its own README explains every option).
  # It runs /usr/local/bin/onemindd and reads /etc/onemind/onemindd.env.
  local unit="$REPO_DIR/deploy/systemd/onemindd.service"
  [ "$DRY_RUN" -eq 1 ] || [ -f "$unit" ] || die "missing $unit (run install.sh from a full clone of the repo)"
  run install -m 0644 "$unit" /etc/systemd/system/onemindd.service
  run systemctl daemon-reload
  run systemctl enable onemindd.service
  run systemctl restart onemindd.service
}

step_gateway() {
  [ "$SKIP_GATEWAY" -eq 0 ] || { warn "skipping gateway and dashboard (--skip-gateway)"; return 0; }
  local image
  step "OneMind gateway + dashboard on k3s (namespace onemind-system, host port :$GATEWAY_PORT)"
  if [ -n "$GATEWAY_IMAGE_TAR" ]; then
    [ "$DRY_RUN" -eq 1 ] || [ -f "$GATEWAY_IMAGE_TAR" ] || die "gateway image tar not found: $GATEWAY_IMAGE_TAR"
    run k3s ctr -n k8s.io images import "$GATEWAY_IMAGE_TAR"
    image="${GATEWAY_IMAGE:-onemind/gateway:dev}"
  elif [ -n "$GATEWAY_IMAGE" ]; then
    image="$GATEWAY_IMAGE"
  elif [ "$DRY_RUN" -eq 1 ]; then
    warn "no gateway image given; the dry run assumes --bundle (on the Mac: ./deploy/bundle.sh --arch $ARCH)"
    run k3s ctr -n k8s.io images import "<bundle>/onemind-gateway-linux-$ARCH.tar"
    image="onemind/gateway:dev"
  else
    die "the hub needs the gateway image. On the Mac run ./deploy/bundle.sh --arch $ARCH, copy the bundle here and pass --bundle DIR (or --gateway-image-tar FILE, or --skip-gateway)"
  fi
  # App catalog and dashboard are copied (not linked) so the pod never reads the git checkout.
  [ "$DRY_RUN" -eq 1 ] || [ -d "$APPS_DIR" ] || die "apps dir not found: $APPS_DIR"
  run install -d -m 0755 "$ONEMIND_OPT/apps" "$ONEMIND_OPT/dashboard"
  run cp -a "$APPS_DIR/." "$ONEMIND_OPT/apps/"
  if [ "$DRY_RUN" -eq 1 ] || [ -f "$DASHBOARD_DIST/index.html" ]; then
    run cp -a "$DASHBOARD_DIST/." "$ONEMIND_OPT/dashboard/"
  else
    warn "no built dashboard at $DASHBOARD_DIST (run 'npm ci && npm run build' in dashboard/ on the Mac and copy dist/ here); the gateway will serve the API only"
  fi
  # Secret with the tokens file and the NATS URL (created from root-only files, never from the repo)
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  + kubectl create namespace onemind-system (if missing)\n'
    printf '  + kubectl -n onemind-system create secret generic onemind-gateway --from-file=tokens.yaml=%s/tokens.yaml --from-literal=nats-url=<nats url with token> (applied, not stored)\n' "$ONEMIND_ETC"
  else
    k3s kubectl get namespace onemind-system >/dev/null 2>&1 || run k3s kubectl create namespace onemind-system
    printf '  + kubectl apply secret onemind-system/onemind-gateway (from %s)\n' "$ONEMIND_ETC"
    k3s kubectl -n onemind-system create secret generic onemind-gateway \
      --from-file=tokens.yaml="$ONEMIND_ETC/tokens.yaml" \
      --from-literal=nats-url="nats://$NATS_TOKEN@127.0.0.1:$NATS_PORT" \
      --dry-run=client -o yaml | k3s kubectl apply -f - >/dev/null
  fi
  local manifest
  manifest="$(sed -e "s|__GATEWAY_IMAGE__|$image|g" \
                  -e "s|__APPS_DIR__|$ONEMIND_OPT/apps|g" \
                  -e "s|__DASHBOARD_DIR__|$ONEMIND_OPT/dashboard|g" \
                  "$SCRIPT_DIR/hub/gateway.yaml")"
  printf '%s\n' "$manifest" | write_file "$ONEMIND_ETC/gateway.yaml" 0644
  run k3s kubectl apply -f "$ONEMIND_ETC/gateway.yaml"
  if [ "$DRY_RUN" -eq 0 ]; then
    printf '  waiting for http://127.0.0.1:%s/healthz ' "$GATEWAY_PORT"
    for _ in $(seq 1 90); do
      if curl -fsS "http://127.0.0.1:$GATEWAY_PORT/healthz" >/dev/null 2>&1; then printf ' ok\n'; return 0; fi
      printf '.'; sleep 2
    done
    printf '\n'
    warn "gateway did not answer within 180 s; check: sudo k3s kubectl -n onemind-system get pods; sudo k3s kubectl -n onemind-system logs deploy/onemind-gateway"
  fi
  return 0
}

wait_k3s_ready() {
  [ "$DRY_RUN" -eq 0 ] || { printf '  + wait until k3s answers and the node is Ready\n'; return 0; }
  for _ in $(seq 1 60); do
    if k3s kubectl get --raw /readyz >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  die "k3s did not become ready in 120 s: journalctl -u k3s -n 100"
}

print_summary_hub() {
  local addr
  addr="$( (hostname -I 2>/dev/null || true) | awk '{print $1}')"
  [ -n "$addr" ] || addr="<this-hub-address>"
  step "Done. Join information (printed once; it is not stored anywhere outside $ONEMIND_ETC)"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  + print: join token omj1.<nats-token>.<k3s-node-token>, owner token, agent token\n'
    return 0
  fi
  local k3s_tok
  k3s_tok="$(cat /var/lib/rancher/k3s/server/node-token)"
  cat <<EOF

  Dashboard / API : http://$addr:$GATEWAY_PORT/
  Verify          : ./deploy/verify/verify.sh http://$addr:$GATEWAY_PORT <owner-token> <agent-token>

  Join a node (run on the node, from a repo clone):
    sudo ./deploy/install.sh --role node --hub $addr --token omj1.$NATS_TOKEN.$k3s_tok --bundle <bundle-dir-for-its-arch>

EOF
  if [ "$FRESH_TOKENS" -eq 1 ]; then
    printf '  API tokens (shown ONCE; only their sha256 hashes are stored in %s/tokens.yaml).\n' "$ONEMIND_ETC"
    printf '  Save them in your password manager now:\n'
    printf '    owner     : %s   (sign in to the dashboard with this one)\n' "$OWNER_TOKEN"
    printf '    dev-agent : %s   (for AI agents: can request actions, never approve)\n' "$AGENT_TOKEN"
  fi
  if [ "$TARGET_KIND" = 'do' ]; then
    cat <<'EOF'

  DigitalOcean: ports 4222 (NATS), 6443 (k3s API) and 8080 (gateway) must NOT be open to the
  internet. Put a DigitalOcean Cloud Firewall in front of the droplet that allows them only
  from your VPC / Tailscale range, and SSH only from your own address.
EOF
  fi
  return 0
}

confirm() {
  [ "$DRY_RUN" -eq 0 ] && [ "$ASSUME_YES" -eq 0 ] || return 0
  if [ -t 0 ]; then
    printf 'Continue with the %s install on %s (%s, %s)? [y/N] ' "$ROLE" "$BOARD" "$OS_PRETTY" "$ARCH"
    local a; read -r a
    case "$a" in y|Y|yes) ;; *) die "aborted" ;; esac
  else
    die "not a terminal: pass --yes to confirm"
  fi
}

main() {
  banner
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\nDRY RUN: nothing will be changed.\n'
  else
    [ "$(id -u)" -eq 0 ] || die "run as root (sudo), or use --dry-run"
  fi
  detect
  check_supported
  printf '\nRole: %s | Board: %s | Arch: %s | OS: %s\n' "$ROLE" "$BOARD" "$ARCH" "$OS_PRETTY"
  if [ "$ROLE" = node ]; then
    [ -n "$HUB" ] || die "--role node needs --hub <host-or-url>"
    [ -n "$JOIN_TOKEN" ] || die "--role node needs --token <join-token> (printed by the hub install)"
    parse_hub "$HUB"
    parse_join_token "$JOIN_TOKEN"
    printf 'Hub: %s (k3s https://%s:%s, NATS :%s)\n' "$HUB_HOST" "$HUB_HOST" "$K3S_API_PORT" "$NATS_PORT"
  else
    [ -z "$HUB" ] && [ -z "$JOIN_TOKEN" ] || die "--hub/--token are for --role node"
  fi
  if [ "$TARGET_KIND" = jetson ]; then
    warn "Jetson: k3s runs workloads, but GPU pods need the NVIDIA container runtime configured for k3s's containerd (not done in v0)"
  fi
  apply_bundle
  resolve_onemindd
  confirm

  step_prereqs
  step_pi_cgroups
  if [ "$ROLE" = hub ]; then
    step_secrets_hub
    step_nats
    step_k3s
    wait_k3s_ready
    step_onemindd
    step_gateway
    print_summary_hub
  else
    step_k3s
    step_onemindd
    step "Done. Check this node with: sudo ./deploy/verify/node-check.sh"
  fi
}

main
