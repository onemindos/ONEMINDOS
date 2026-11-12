#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# OneMind developer install (P6, contract sdk/contracts/poc-v0.md §6; brief 30 D-B2.4, REC-DEC-30).
# UNSUPPORTED DEVELOPER INSTALL, NO OS ROLLBACK: packages are upgraded in place on a stock OS.
#
#   sudo deploy/install.sh --role hub  [--hub http://<this-box>:8080]
#   sudo deploy/install.sh --role node --hub http://<hub>:8080 --token <join-token>
#   sudo deploy/install.sh --uninstall [--purge]
#   deploy/install.sh --role hub --dry-run [--target debian13|rpi5|jetson|do]   # plan only
#   sudo BUNDLE/src/deploy/install.sh --role hub --bundle BUNDLE                # offline bundle
#
# Run it from a checkout of this repository (it builds onemindd, the gateway and the dashboard
# from that checkout), or from an offline bundle made by deploy/bundle.sh (nothing is built on the
# box). Re-running it is safe: every step checks what is already there.
# See deploy/README.md for what it installs, where, and why.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SRC=$(cd "$SCRIPT_DIR/.." && pwd)
# shellcheck source=deploy/pins.env
. "$SCRIPT_DIR/pins.env"

PREFIX=/opt/onemind
ETC=/etc/onemind
STATE=/var/lib/onemind
CACHE=/var/cache/onemind
TOOLS=$PREFIX/toolchain
BIN=/usr/local/bin
BANNER="unsupported developer install, no OS rollback"

ROLE="" HUB="" TOKEN="" UNINSTALL=0 PURGE=0 ONEMINDD_BIN="" DASH_DIST="" BIND="0.0.0.0" FORCE_OS=0
DRY_RUN=0 TARGET="" ARCH_OVERRIDE="" BUNDLE="" GATEWAY_RUNTIME="" WITH_AGENT=0

usage() {
  cat <<EOF
Usage:
  $0 --role hub  [--hub URL] [--gateway-bind ADDR] [--with-agent-token] [--dashboard-dist DIR] [--onemindd-bin FILE]
  $0 --role node --hub URL --token JOIN_TOKEN [--onemindd-bin FILE]
  $0 --uninstall [--purge]
  $0 ... --dry-run [--target debian13|rpi5|jetson|do [--arch amd64|arm64]]
  $0 ... --bundle DIR

  --role hub|node        hub: k3s server, NATS, onemindd, gateway + dashboard. node: k3s agent + onemindd.
  --hub URL              hub gateway URL, e.g. http://hub.local:8080 (the host part also gives
                         k3s https://HOST:6443 and NATS nats://HOST:4222). Optional on the hub.
  --token T              the join token the hub install printed (node only).
  --with-agent-token     hub: also issue an API token for an AI agent (principal dev-agent: may
                         request actions, never approve). Like the owner token it is printed once
                         and only its sha256 is stored. On a re-run it is added if none exists.
  --gateway-bind ADDR    gateway listen address (default 0.0.0.0; 127.0.0.1 keeps it local,
                         but then app pods and other machines cannot reach it).
  --onemindd-bin FILE    use a prebuilt static onemindd (make -C cmd/onemindd build) instead of Go.
  --dashboard-dist DIR   use a prebuilt dashboard/dist instead of building it with Node.
  --bundle DIR           use an offline bundle from deploy/bundle.sh (checked against its SHA256SUMS
                         first): onemindd, gateway runtime, dashboard, k3s with airgap images, NATS.
                         Found by itself when this script runs from DIR/src/deploy/.
  --force-os             continue on an OS this script was not written for.
  --uninstall            remove everything this script installed (k3s and its data included).
  --purge                with --uninstall: also delete $STATE (gateway database and audit log).
  --dry-run              print every step this run would take, and change nothing (no root needed).
  --target T             with --dry-run: plan for T instead of this machine. debian13 (a Beelink or
                         any Debian 13 PC), rpi5 (Raspberry Pi OS trixie), jetson (Jetson Linux),
                         do (a DigitalOcean Debian 13 droplet).
  --arch amd64|arm64     with --target: another CPU architecture than the target's usual one.
EOF
}

log()  { printf '==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
# one_line VALUE ERE: VALUE is a single line and matches ERE as a whole. grep -x alone checks each
# line, so "good<newline>KEY=other" would pass and KEY=other would land in an env or config file.
one_line() { case "$1" in *$'\n'*) return 1 ;; esac; printf '%s' "$1" | LC_ALL=C grep -Eqx "$2"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --role) ROLE=${2:-}; shift 2 ;;
    --hub) HUB=${2:-}; shift 2 ;;
    --token) TOKEN=${2:-}; shift 2 ;;
    --gateway-bind) BIND=${2:-}; shift 2 ;;
    --onemindd-bin) ONEMINDD_BIN=${2:-}; shift 2 ;;
    --dashboard-dist) DASH_DIST=${2:-}; shift 2 ;;
    --force-os) FORCE_OS=1; shift ;;
    --with-agent-token) WITH_AGENT=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --purge) PURGE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --target) TARGET=${2:-}; shift 2 ;;
    --arch) ARCH_OVERRIDE=${2:-}; shift 2 ;;
    --bundle) BUNDLE=${2:-}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
done

banner() {
  printf '\n************************************************************\n'
  printf '*  OneMind: %-46s *\n' "$BANNER"
  printf '*  (REC-DEC-30) Packages upgrade in place; nothing can roll *\n'
  printf '*  the OS back. Use the OneMind image for a real box.       *\n'
  printf '************************************************************\n\n'
}

# --dry-run: each step prints what it would change (plan, show_file) and returns before
# changing anything; the real code path below each dry-run block is unchanged.
STEP=0
step() { STEP=$((STEP + 1)); printf '\n[%d] %s\n' "$STEP" "$*"; }
plan() { printf '  + %s\n' "$*"; }
show_file() { # show_file PATH MODE [OWNER]: print the content (stdin) this run would write
  printf '  + write %s (mode %s%s)\n' "$1" "$2" "${3:+, $3}"
  sed 's/^/      | /'
}

if [ "$DRY_RUN" = 1 ]; then
  printf 'DRY RUN: nothing on this machine is changed; this is the plan.\n'
else
  [ "$(id -u)" -eq 0 ] || die "run as root (sudo), or add --dry-run to see the plan"
  [ -z "$TARGET" ] || die "--target is only for --dry-run; a real install detects the machine it runs on"
fi
banner

# ------------------------------------------------------------------------------------------
# Uninstall
# ------------------------------------------------------------------------------------------
uninstall() {
  if [ "$DRY_RUN" = 1 ]; then
    step "Uninstall"
    plan "systemctl disable --now onemind-gateway onemindd onemind-nats; remove their unit files"
    plan "rm $BIN/onemindd $BIN/onemind $BIN/nats-server"
    plan "run k3s-uninstall.sh / k3s-agent-uninstall.sh if present (k3s and its data)"
    plan "rm /etc/apt/apt.conf.d/52onemind-security-only /etc/needrestart/conf.d/50-onemind.conf"
    plan "rm -r $PREFIX $ETC $CACHE /var/lib/onemind-nats"
    if [ "$PURGE" = 1 ]; then plan "rm -r $STATE /var/lib/onemindd; userdel onemind"; else plan "keep $STATE"; fi
    return 0
  fi
  log "stopping and removing OneMind services"
  for u in onemind-gateway onemindd onemind-nats; do
    systemctl disable --now "$u" 2>/dev/null || true
    rm -f "/etc/systemd/system/$u.service"
  done
  systemctl daemon-reload
  rm -f "$BIN/onemindd" "$BIN/onemind" "$BIN/nats-server"
  if [ -x "$BIN/k3s-uninstall.sh" ]; then log "removing k3s server (and its data)"; "$BIN/k3s-uninstall.sh"; fi
  if [ -x "$BIN/k3s-agent-uninstall.sh" ]; then log "removing k3s agent"; "$BIN/k3s-agent-uninstall.sh"; fi
  rm -f /etc/apt/apt.conf.d/52onemind-security-only /etc/needrestart/conf.d/50-onemind.conf
  rm -rf "$PREFIX" "$ETC" "$CACHE" /var/lib/onemind-nats /var/lib/private/onemind-nats
  if [ "$PURGE" = 1 ]; then
    rm -rf "$STATE" /var/lib/onemindd
    id onemind >/dev/null 2>&1 && userdel onemind
    log "purged $STATE (database, audit log)"
  else
    [ -d "$STATE" ] && log "kept $STATE (gateway database and audit log); --purge deletes it"
  fi
  log "unattended-upgrades and needrestart stay installed (Debian defaults apply again)"
  log "uninstall done"
}
if [ "$UNINSTALL" = 1 ]; then uninstall; exit 0; fi

# ------------------------------------------------------------------------------------------
# Arguments and platform
# ------------------------------------------------------------------------------------------
case "$ROLE" in hub|node) ;; *) usage >&2; die "--role hub or --role node is required" ;; esac
if [ "$ROLE" = node ]; then
  [ -n "$HUB" ] || die "--hub is required for --role node"
  [ -n "$TOKEN" ] || die "--token is required for --role node (the hub install prints it)"
  # The token goes into k3s's env file and the URL into config files: allow only plain characters.
  # (Length checked apart: BSD grep, used for --dry-run on a Mac, caps {m,n} at 255.)
  { [ "${#TOKEN}" -ge 8 ] && [ "${#TOKEN}" -le 512 ] && one_line "$TOKEN" '[A-Za-z0-9:._-]+'; } \
    || die "--token has unexpected characters or length"
fi
if [ -n "$HUB" ]; then
  one_line "$HUB" 'https?://[][A-Za-z0-9.:-]+/?' \
    || die "--hub must look like http://HOST:8080 (got: $HUB)"
fi

# TARGET_KIND is the §6 target this machine is: debian13 (any Debian 13 PC or VM, the Beelink),
# rpi5, jetson or do. It decides the Pi 5 memory-cgroup step, the Jetson GPU note and the
# DigitalOcean firewall reminder. JETSON=1 stands in for /etc/nv_tegra_release under --target.
TARGET_KIND="" BOARD="" JETSON=0
if [ -n "$TARGET" ]; then
  case "$TARGET" in
    debian13) ID=debian VERSION_CODENAME=trixie PRETTY_NAME="Debian GNU/Linux 13 (trixie)" BOARD=x86_64-efi ARCH=amd64 ;;
    rpi5)     ID=debian VERSION_CODENAME=trixie PRETTY_NAME="Raspberry Pi OS (trixie)" BOARD=rpi5 ARCH=arm64 ;;
    jetson)   ID=ubuntu VERSION_CODENAME=jammy PRETTY_NAME="Ubuntu 22.04 (Jetson Linux)" BOARD=jetson-orin ARCH=arm64 JETSON=1 ;;
    do)       ID=debian VERSION_CODENAME=trixie PRETTY_NAME="Debian GNU/Linux 13 (trixie)" BOARD=vm-do ARCH=amd64 ;;
    *) die "--target must be debian13, rpi5, jetson or do (got: $TARGET)" ;;
  esac
  TARGET_KIND=$TARGET
  [ -z "$ARCH_OVERRIDE" ] || ARCH=$ARCH_OVERRIDE
else
  [ -z "$ARCH_OVERRIDE" ] || die "--arch goes with --target (a real install uses this machine's architecture)"
  [ -r /etc/os-release ] || die "/etc/os-release not found: not a Linux this script knows (use --dry-run --target to plan for one)"
  ARCH=$(dpkg --print-architecture 2>/dev/null || true)
  if [ -z "$ARCH" ] && [ "$DRY_RUN" = 1 ]; then
    case "$(uname -m)" in x86_64) ARCH=amd64 ;; aarch64|arm64) ARCH=arm64 ;; esac
  fi
  # shellcheck disable=SC1091
  . /etc/os-release
  [ -f /etc/nv_tegra_release ] && JETSON=1
  MODEL="" VENDOR=""
  [ -r /proc/device-tree/model ] && MODEL=$(tr -d '\0' < /proc/device-tree/model)
  [ -r /sys/class/dmi/id/sys_vendor ] && VENDOR=$(cat /sys/class/dmi/id/sys_vendor)
  case "$MODEL" in
    *"Raspberry Pi 5"*) TARGET_KIND=rpi5 BOARD=rpi5 ;;
    *"Raspberry Pi"*) warn "this Raspberry Pi is not a Pi 5; only the Pi 5 is a v0 board" ;;
  esac
  if [ -z "$TARGET_KIND" ]; then
    if [ "$JETSON" = 1 ]; then TARGET_KIND=jetson BOARD=jetson-orin
    elif [ "$VENDOR" = DigitalOcean ]; then TARGET_KIND='do' BOARD=vm-do
    else TARGET_KIND=debian13 BOARD=$(systemd-detect-virt -q 2>/dev/null && echo vm || echo "$ARCH")
    fi
  fi
fi
case "$ARCH" in amd64|arm64) ;; *) die "architecture '$ARCH' is not supported (amd64 or arm64 only)" ;; esac

OS_DESC="${PRETTY_NAME:-unknown}"
OS_OK=0
case "${ID:-}" in
  debian|raspbian) [ "${VERSION_CODENAME:-}" = trixie ] && OS_OK=1 ;;   # Debian 13, Raspberry Pi OS trixie
  ubuntu) [ "$JETSON" = 1 ] && OS_OK=1 ;;                                # Jetson Linux (L4T) Ubuntu
esac
if [ "$OS_OK" = 0 ]; then
  [ "$FORCE_OS" = 1 ] || die "$OS_DESC is not a target of this script (Debian 13, Raspberry Pi OS trixie, Jetson L4T Ubuntu). --force-os to try anyway"
  warn "continuing on $OS_DESC (--force-os)"
fi
log "platform: $OS_DESC, $ARCH, target $TARGET_KIND ($BOARD), role $ROLE"

do_firewall_reminder() {
  [ "$TARGET_KIND" = 'do' ] || return 0
  cat <<'EOF'

  DigitalOcean: this droplet has a public address. Ports 8080 (gateway, plain HTTP), 4222 (NATS,
  no auth in v0), 6443 (k3s API), 10250 (kubelet) and 8472/udp (flannel) must NOT be open to the
  internet. Put a DigitalOcean Cloud Firewall in front of the droplet that allows them only from
  your VPC or Tailscale range, and SSH only from your own address. This script does not change
  any firewall.

EOF
}
do_firewall_reminder
if [ "$TARGET_KIND" = jetson ]; then
  warn "Jetson: k3s runs ordinary pods, but GPU pods need the NVIDIA container runtime set up for k3s's containerd (not done in v0)"
fi

# ------------------------------------------------------------------------------------------
# Offline bundle (deploy/bundle.sh): check it before anything is used or changed
# ------------------------------------------------------------------------------------------
if [ -z "$BUNDLE" ] && [ -f "$SRC/../BUNDLE.txt" ] && [ -f "$SRC/../SHA256SUMS" ]; then
  BUNDLE=$(cd "$SRC/.." && pwd); log "running from the offline bundle $BUNDLE"
fi
if [ -n "$BUNDLE" ]; then
  [ -d "$BUNDLE" ] || die "--bundle $BUNDLE is not a directory"
  BUNDLE=$(cd "$BUNDLE" && pwd)
  { [ -f "$BUNDLE/SHA256SUMS" ] && [ -f "$BUNDLE/BUNDLE.txt" ]; } \
    || die "$BUNDLE is not a deploy/bundle.sh bundle (no SHA256SUMS or BUNDLE.txt)"
  B_ARCH=$(sed -n 's/^arch=//p' "$BUNDLE/BUNDLE.txt"); B_CONTENTS=$(sed -n 's/^contents=//p' "$BUNDLE/BUNDLE.txt")
  [ "$B_ARCH" = "$ARCH" ] || die "the bundle is for $B_ARCH, this machine is $ARCH (deploy/bundle.sh --arch $ARCH)"
  [ "$ROLE" = node ] || [ "$B_CONTENTS" = full ] || die "this bundle was built with --node-only; a hub needs a full bundle"
  if [ "$DRY_RUN" = 1 ]; then
    step "Offline bundle $BUNDLE ($(sed -n 's/^commit=//p' "$BUNDLE/BUNDLE.txt"))"
    plan "sha256sum --strict -c SHA256SUMS, and refuse any file SHA256SUMS does not list"
  else
    log "bundle: checking every file against $BUNDLE/SHA256SUMS"
    (cd "$BUNDLE" && sha256sum --strict --quiet -c SHA256SUMS) || die "bundle checksum mismatch in $BUNDLE: copy it again"
    # Nothing unlisted either (a stray or added file is refused, not silently used).
    [ "$(cd "$BUNDLE" && sed 's/^[0-9a-f]\{64\}  //' SHA256SUMS | LC_ALL=C sort)" = \
      "$(cd "$BUNDLE" && find . -type f ! -path ./SHA256SUMS | LC_ALL=C sort)" ] \
      || die "$BUNDLE has files that SHA256SUMS does not list (or lists files it lacks)"
    log "bundle: ok (commit $(sed -n 's/^commit=//p' "$BUNDLE/BUNDLE.txt"))"
  fi
  # Explicit --onemindd-bin / --dashboard-dist still win.
  [ -n "$ONEMINDD_BIN" ] || ONEMINDD_BIN="$BUNDLE/onemindd-linux-$ARCH"
  if [ "$ROLE" = hub ]; then
    [ -n "$DASH_DIST" ] || DASH_DIST="$BUNDLE/dashboard"
    GATEWAY_RUNTIME="$BUNDLE/gateway-runtime-linux-$ARCH.tar.gz"
  fi
fi

hub_host() { # host part of --hub (scheme, port and path removed)
  local h=${1#*://}; h=${h%%/*}
  case "$h" in \[*\]*) h=${h%%]*}; h=${h#[} ;; *) h=${h%%:*} ;; esac
  printf '%s' "$h"
}
primary_ip() { ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i=="src"){print $(i+1); exit}}'; }

pick() { eval "printf '%s' \"\${$1_$ARCH}\""; }   # pick K3S_SHA256 -> value for this arch

# fetch URL SHA256 DEST: download, check the hash, then move into place (never runs unchecked bytes).
# With a bundle, the same file comes from BUNDLE/downloads/ and gets the same check against the pin.
fetch() {
  local url=$1 sum=$2 dest=$3 tmp from=""
  [ -n "$BUNDLE" ] && [ -f "$BUNDLE/downloads/${dest##*/}" ] && from="$BUNDLE/downloads/${dest##*/}"
  if [ "$DRY_RUN" = 1 ]; then
    if [ -n "$from" ]; then plan "take ${dest##*/} from the bundle"; else plan "download $url"; fi
    printf '      -> %s (sha256 must be %s)\n' "$dest" "$sum"; return 0
  fi
  if [ -f "$dest" ] && echo "$sum  $dest" | sha256sum -c --status; then return 0; fi
  tmp=$(mktemp "$CACHE/dl.XXXXXX")
  if [ -n "$from" ]; then
    log "from the bundle: ${dest##*/}"
    cp "$from" "$tmp"
  else
    log "download $url"
    curl -fsSL --retry 3 --proto '=https' -o "$tmp" "$url"
  fi
  if ! echo "$sum  $tmp" | sha256sum -c --status; then
    rm -f "$tmp"; die "sha256 mismatch for $url (expected $sum)"
  fi
  mv "$tmp" "$dest"
}

if [ "$DRY_RUN" = 1 ]; then
  step "Directories"
  plan "install -d -m0755 $PREFIX $TOOLS $CACHE $ETC"
else
  install -d -m0755 "$PREFIX" "$TOOLS" "$CACHE"
  # 0755: services read their own files here (NATS as a dynamic user, the gateway as "onemind");
  # each secret file below is 0600/0640 on its own.
  install -d -m0755 "$ETC"
fi

# ------------------------------------------------------------------------------------------
# 0. Memory cgroup (k3s needs it; off by default on the Raspberry Pi kernel)
# ------------------------------------------------------------------------------------------
memory_cgroup_check() {
  local cmdline=/boot/firmware/cmdline.txt
  if [ "$DRY_RUN" = 1 ]; then
    step "Memory cgroup (k3s needs it)"
    if [ "$TARGET_KIND" = rpi5 ]; then
      plan "if /sys/fs/cgroup/cgroup.controllers lacks \"memory\" (the Raspberry Pi kernel default):"
      plan "  copy $cmdline to $cmdline.onemind-backup (once)"
      plan "  append \"cgroup_memory=1 cgroup_enable=memory\" to the single line of $cmdline"
      plan "  stop with exit code 3: reboot, then run this command again"
    else
      plan "check that /sys/fs/cgroup/cgroup.controllers lists \"memory\"; stop if it does not"
    fi
    return 0
  fi
  grep -qw memory /sys/fs/cgroup/cgroup.controllers 2>/dev/null && return 0
  if [ -f "$cmdline" ]; then   # Raspberry Pi: k3s needs the memory cgroup (docs.k3s.io, Raspberry Pi)
    if ! grep -q 'cgroup_enable=memory' "$cmdline"; then
      [ -f "$cmdline.onemind-backup" ] || cp -p "$cmdline" "$cmdline.onemind-backup"
      sed -i '1 s/$/ cgroup_memory=1 cgroup_enable=memory/' "$cmdline"
      log "$cmdline updated (the old one is $cmdline.onemind-backup)"
    fi
    printf '\nThe memory cgroup is off; it is turned on at the next boot. Reboot, then run this script again.\n' >&2
    exit 3
  fi
  die "the memory cgroup is not available; k3s cannot run"
}

# ------------------------------------------------------------------------------------------
# 1. OS packages + automatic security updates (contract §10.1, developer installs)
# ------------------------------------------------------------------------------------------
APT_PKGS="ca-certificates curl tar gzip iproute2 unattended-upgrades needrestart apt-listchanges"
apt_security_conf() {
  if [ "${ID:-}" = ubuntu ]; then
    cat <<'EOF'
// OneMind developer install (deploy/install.sh): automatic updates from security origins only.
#clear Unattended-Upgrade::Allowed-Origins;
#clear Unattended-Upgrade::Origins-Pattern;
Unattended-Upgrade::Allowed-Origins { "${distro_id}:${distro_codename}-security"; };
EOF
  else
    cat <<'EOF'
// OneMind developer install (deploy/install.sh): automatic updates from security origins only.
#clear Unattended-Upgrade::Allowed-Origins;
#clear Unattended-Upgrade::Origins-Pattern;
Unattended-Upgrade::Origins-Pattern {
  "origin=Debian,codename=${distro_codename}-security,label=Debian-Security";
  "origin=Debian,codename=${distro_codename},label=Debian-Security";
};
EOF
  fi
}
needrestart_conf() {
  cat <<'EOF'
# OneMind developer install: restart affected services automatically.
$nrconf{restart} = 'a';
EOF
}

apt_setup() {
  local pkgs=$APT_PKGS
  if [ "$DRY_RUN" = 1 ]; then
    step "OS packages and automatic security updates (contract §10.1)"
    plan "apt-get install --no-install-recommends $pkgs (only if one is missing)"
    plan "debconf: unattended-upgrades/enable_auto_updates=true; dpkg-reconfigure unattended-upgrades"
    apt_security_conf | show_file /etc/apt/apt.conf.d/52onemind-security-only 0644
    needrestart_conf | show_file /etc/needrestart/conf.d/50-onemind.conf 0644
    plan "systemctl enable --now apt-daily.timer apt-daily-upgrade.timer"
    return 0
  fi
  # shellcheck disable=SC2086
  if ! dpkg -s $pkgs >/dev/null 2>&1; then
    log "apt: installing $pkgs"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    # shellcheck disable=SC2086
    apt-get install -y -qq --no-install-recommends $pkgs >/dev/null
  fi
  # Debian's documented switch (wiki.debian.org/UnattendedUpgrades): writes 20auto-upgrades.
  echo 'unattended-upgrades unattended-upgrades/enable_auto_updates boolean true' | debconf-set-selections
  DEBIAN_FRONTEND=noninteractive dpkg-reconfigure -f noninteractive unattended-upgrades
  # Security origins only (contract §10.1). '#clear' drops the distro list, then we add ours.
  apt_security_conf > /etc/apt/apt.conf.d/52onemind-security-only
  # needrestart: restart services that still use replaced libraries, without asking.
  install -d -m0755 /etc/needrestart/conf.d
  needrestart_conf > /etc/needrestart/conf.d/50-onemind.conf
  systemctl enable --now apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true
}

# ------------------------------------------------------------------------------------------
# 2. k3s (server on the hub, agent on a node)
# ------------------------------------------------------------------------------------------
k3s_binary() {
  local name=k3s; [ "$ARCH" = arm64 ] && name=k3s-arm64
  [ "$DRY_RUN" = 1 ] && step "k3s $K3S_VERSION binary and its upstream install.sh (both sha256-pinned)"
  fetch "$K3S_URL_BASE/$name" "$(pick K3S_SHA256)" "$CACHE/k3s-$K3S_VERSION-$ARCH"
  if [ "$DRY_RUN" = 1 ]; then
    plan "install -m0755 $CACHE/k3s-$K3S_VERSION-$ARCH $BIN/k3s (if it differs; refuse a k3s this script did not install)"
  elif ! cmp -s "$CACHE/k3s-$K3S_VERSION-$ARCH" "$BIN/k3s" 2>/dev/null; then
    [ -e "$BIN/k3s" ] && ! systemctl list-unit-files k3s.service k3s-agent.service 2>/dev/null | grep -q k3s \
      && die "$BIN/k3s exists but was not installed by this script; remove it first"
    install -m0755 "$CACHE/k3s-$K3S_VERSION-$ARCH" "$BIN/k3s"
    K3S_CHANGED=1
  fi
  fetch "https://raw.githubusercontent.com/k3s-io/k3s/$K3S_INSTALL_COMMIT/install.sh" \
    "$K3S_INSTALL_SHA256" "$CACHE/k3s-install-$K3S_INSTALL_COMMIT.sh"
  # Offline bundle: k3s's own images (pause, CoreDNS, ...), imported by k3s when it starts.
  if [ -n "$BUNDLE" ] && [ -f "$BUNDLE/downloads/k3s-airgap-images-$ARCH.tar.zst" ]; then
    [ "$DRY_RUN" = 1 ] || install -d -m0755 /var/lib/rancher/k3s/agent/images
    fetch "$K3S_URL_BASE/k3s-airgap-images-$ARCH.tar.zst" "$(pick K3S_AIRGAP_SHA256)" \
      "/var/lib/rancher/k3s/agent/images/k3s-airgap-images-$ARCH.tar.zst"
  fi
}

k3s_server_config() { printf '# Written by deploy/install.sh\nwrite-kubeconfig-mode: "0600"\nagent-token: "%s"\n' "$1"; }

k3s_server() {
  local cfg=/etc/rancher/k3s/config.yaml agent_token new_cfg
  if [ "$DRY_RUN" = 1 ]; then
    step "k3s server (the hub)"
    plan "generate the k3s agent token once (32 random bytes) -> $ETC/k3s-agent-token (0600)"
    k3s_server_config "<the agent token, generated on the machine>" | show_file "$cfg" 0600
    plan "INSTALL_K3S_SKIP_DOWNLOAD=true INSTALL_K3S_EXEC=server sh $CACHE/k3s-install-$K3S_INSTALL_COMMIT.sh (if k3s changed or is not running)"
    plan "wait until the k3s node is Ready (up to 180 s)"
    return 0
  fi
  install -d -m0700 /etc/rancher/k3s
  # A separate agent token: nodes can join as agents but can never join as servers (D-B6.2).
  if [ -f "$ETC/k3s-agent-token" ]; then agent_token=$(cat "$ETC/k3s-agent-token")
  else agent_token=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n'); (umask 077; printf '%s' "$agent_token" > "$ETC/k3s-agent-token"); fi
  new_cfg=$(k3s_server_config "$agent_token")
  if [ "$(cat "$cfg" 2>/dev/null)" != "$new_cfg" ]; then (umask 077; printf '%s\n' "$new_cfg" > "$cfg"); K3S_CHANGED=1; fi
  if [ "${K3S_CHANGED:-0}" = 1 ] || ! systemctl is-active --quiet k3s; then
    log "k3s $K3S_VERSION server: install/restart"
    INSTALL_K3S_SKIP_DOWNLOAD=true INSTALL_K3S_SELINUX_WARN=true INSTALL_K3S_SKIP_SELINUX_RPM=true \
      INSTALL_K3S_EXEC=server sh "$CACHE/k3s-install-$K3S_INSTALL_COMMIT.sh" >/dev/null
  fi
  log "waiting for the k3s node to be Ready"
  local i
  for i in $(seq 1 90); do
    "$BIN/k3s" kubectl get nodes 2>/dev/null | grep -qw Ready && break
    [ "$i" = 90 ] && die "k3s did not become Ready in 180 s (journalctl -u k3s)"
    sleep 2
  done
  for i in $(seq 1 60); do [ -s /var/lib/rancher/k3s/server/agent-token ] && break; sleep 1; done
}

k3s_agent() {
  local host env=/etc/systemd/system/k3s-agent.service.env; host=$(hub_host "$HUB")
  if [ "$DRY_RUN" = 1 ]; then
    step "k3s agent (joins the hub)"
    plan "K3S_URL=https://$host:6443 K3S_TOKEN=<the --token value> INSTALL_K3S_SKIP_DOWNLOAD=true INSTALL_K3S_EXEC=agent sh $CACHE/k3s-install-$K3S_INSTALL_COMMIT.sh"
    plan "(only if the hub URL or token changed, or k3s-agent is not running; the token lands in $env, 0600)"
    return 0
  fi
  # Re-join when the hub URL or token changed: "active" alone only means it is retrying.
  if ! grep -qxF "K3S_URL='https://$host:6443'" "$env" 2>/dev/null || ! grep -qxF "K3S_TOKEN='$TOKEN'" "$env" 2>/dev/null; then
    K3S_CHANGED=1
  fi
  if [ "${K3S_CHANGED:-0}" = 1 ] || ! systemctl is-active --quiet k3s-agent; then
    log "k3s $K3S_VERSION agent: joining https://$host:6443"
    K3S_URL="https://$host:6443" K3S_TOKEN="$TOKEN" \
      INSTALL_K3S_SKIP_DOWNLOAD=true INSTALL_K3S_SELINUX_WARN=true INSTALL_K3S_SKIP_SELINUX_RPM=true \
      INSTALL_K3S_EXEC=agent sh "$CACHE/k3s-install-$K3S_INSTALL_COMMIT.sh" >/dev/null
  fi
}

# ------------------------------------------------------------------------------------------
# 3. NATS on the hub (contract §1 :4222; v0 shortcut: no auth/TLS, nodes publish directly)
# ------------------------------------------------------------------------------------------
nats_conf() {
  cat <<'EOF'
# OneMind hub NATS (deploy/install.sh). v0 shortcut: no auth/TLS, no leaf nodes (contract header).
listen: 0.0.0.0:4222
http: 127.0.0.1:8222
max_payload: 1MB
EOF
}

nats_install() {
  local tgz="nats-server-$NATS_VERSION-linux-$ARCH.tar.gz"
  [ "$DRY_RUN" = 1 ] && step "NATS $NATS_VERSION on the hub (:4222)"
  fetch "https://github.com/nats-io/nats-server/releases/download/$NATS_VERSION/$tgz" "$(pick NATS_SHA256)" "$CACHE/$tgz"
  if [ "$DRY_RUN" = 1 ]; then
    plan "extract nats-server -> $BIN/nats-server (if the version differs)"
    nats_conf | show_file "$ETC/nats.conf" 0644
    plan "install $SCRIPT_DIR/systemd/onemind-nats.service; systemctl enable onemind-nats; restart"
    return 0
  fi
  if ! "$BIN/nats-server" --version 2>/dev/null | grep -q "${NATS_VERSION#v}"; then
    tar -xzf "$CACHE/$tgz" -C "$CACHE" "nats-server-$NATS_VERSION-linux-$ARCH/nats-server"
    install -m0755 "$CACHE/nats-server-$NATS_VERSION-linux-$ARCH/nats-server" "$BIN/nats-server"
    rm -rf "$CACHE/nats-server-$NATS_VERSION-linux-$ARCH"
  fi
  nats_conf > "$ETC/nats.conf"
  chmod 0644 "$ETC/nats.conf"
  install -m0644 "$SCRIPT_DIR/systemd/onemind-nats.service" /etc/systemd/system/onemind-nats.service
  systemctl daemon-reload
  systemctl enable onemind-nats >/dev/null 2>&1
  systemctl restart onemind-nats
}

# ------------------------------------------------------------------------------------------
# 4. Toolchains (pinned, under /opt/onemind/toolchain; only what this role needs)
# ------------------------------------------------------------------------------------------
go_toolchain() {
  GO_DIR=$TOOLS/go-$GO_VERSION
  [ "$DRY_RUN" = 0 ] && [ -x "$GO_DIR/bin/go" ] && return 0
  fetch "https://go.dev/dl/go$GO_VERSION.linux-$ARCH.tar.gz" "$(pick GO_SHA256)" "$CACHE/go$GO_VERSION.tgz"
  [ "$DRY_RUN" = 1 ] && { plan "extract Go $GO_VERSION -> $GO_DIR"; return 0; }
  rm -rf "$GO_DIR.tmp"; mkdir -p "$GO_DIR.tmp"
  tar -xzf "$CACHE/go$GO_VERSION.tgz" -C "$GO_DIR.tmp" --strip-components=1
  mv "$GO_DIR.tmp" "$GO_DIR"
}

node_toolchain() {
  local na=x64; [ "$ARCH" = arm64 ] && na=arm64
  NODE_DIR=$TOOLS/node-$NODE_VERSION
  [ "$DRY_RUN" = 0 ] && [ -x "$NODE_DIR/bin/node" ] && return 0
  fetch "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-$na.tar.gz" "$(pick NODE_SHA256)" "$CACHE/node-$NODE_VERSION.tgz"
  [ "$DRY_RUN" = 1 ] && { plan "extract Node $NODE_VERSION -> $NODE_DIR"; return 0; }
  rm -rf "$NODE_DIR.tmp"; mkdir -p "$NODE_DIR.tmp"
  tar -xzf "$CACHE/node-$NODE_VERSION.tgz" -C "$NODE_DIR.tmp" --strip-components=1
  mv "$NODE_DIR.tmp" "$NODE_DIR"
}

uv_toolchain() {
  local ua=x86_64; [ "$ARCH" = arm64 ] && ua=aarch64
  UV=$TOOLS/uv-$UV_VERSION/uv
  [ "$DRY_RUN" = 0 ] && [ -x "$UV" ] && return 0
  fetch "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$ua-unknown-linux-gnu.tar.gz" "$(pick UV_SHA256)" "$CACHE/uv-$UV_VERSION.tgz"
  [ "$DRY_RUN" = 1 ] && { plan "extract uv $UV_VERSION -> $TOOLS/uv-$UV_VERSION"; return 0; }
  mkdir -p "$TOOLS/uv-$UV_VERSION"
  tar -xzf "$CACHE/uv-$UV_VERSION.tgz" -C "$TOOLS/uv-$UV_VERSION" --strip-components=1
}

# ------------------------------------------------------------------------------------------
# 5. onemindd (+ the onemind CLI) as a systemd service, on every machine
# ------------------------------------------------------------------------------------------
onemindd_env() { printf '# Written by deploy/install.sh (contract §1)\nONEMIND_NATS_URL=%s\nONEMIND_NODE_ROLE=%s\n' "$1" "$ROLE"; }

onemindd_install() {
  local out="$CACHE/build" nats_url
  if [ "$ROLE" = hub ]; then nats_url=nats://127.0.0.1:4222; else nats_url="nats://$(hub_host "$HUB"):4222"; fi
  if [ "$DRY_RUN" = 1 ]; then
    step "onemindd node agent + onemind CLI (systemd service, local API :7480)"
    if [ -n "$ONEMINDD_BIN" ]; then
      plan "use the prebuilt $ONEMINDD_BIN (and onemind-linux-$ARCH next to it, if there)"
    else
      go_toolchain
      plan "go build -trimpath ./cmd/onemindd ./cmd/onemind (CGO_ENABLED=0, from $SRC)"
    fi
    plan "install -m0755 onemindd onemind -> $BIN/ (if they differ)"
    onemindd_env "$nats_url" | show_file "$ETC/onemindd.env" 0644
    plan "install $SCRIPT_DIR/systemd/onemindd.service; systemctl enable onemindd; restart if anything changed"
    return 0
  fi
  mkdir -p "$out"
  if [ -n "$ONEMINDD_BIN" ]; then
    log "onemindd: using prebuilt $ONEMINDD_BIN"
    install -m0755 "$ONEMINDD_BIN" "$out/onemindd"
    [ -x "$(dirname "$ONEMINDD_BIN")/onemind-linux-$ARCH" ] && install -m0755 "$(dirname "$ONEMINDD_BIN")/onemind-linux-$ARCH" "$out/onemind"
  else
    # No onemindd release artifact is published yet, so it is built from this checkout.
    go_toolchain
    log "onemindd: building from source with Go $GO_VERSION"
    local bin
    for bin in onemindd onemind; do
      (cd "$SRC" && env CGO_ENABLED=0 GOTOOLCHAIN=local GOFLAGS=-mod=readonly \
        GOCACHE="$CACHE/go-build" GOMODCACHE="$CACHE/go-mod" GOPATH="$CACHE/go" HOME="$CACHE" \
        "$GO_DIR/bin/go" build -trimpath -buildvcs=false \
        -ldflags "-s -w -buildid= -X github.com/onemindos/onemindos/internal/version.Version=0.1.0+devinstall" \
        -o "$out/$bin" "./cmd/$bin")
    done
  fi
  local changed=0
  cmp -s "$out/onemindd" "$BIN/onemindd" 2>/dev/null || { install -m0755 "$out/onemindd" "$BIN/onemindd"; changed=1; }
  [ -f "$out/onemind" ] && install -m0755 "$out/onemind" "$BIN/onemind"
  onemindd_env "$nats_url" > "$ETC/onemindd.env.new"
  cmp -s "$ETC/onemindd.env.new" "$ETC/onemindd.env" 2>/dev/null || changed=1
  mv "$ETC/onemindd.env.new" "$ETC/onemindd.env"; chmod 0644 "$ETC/onemindd.env"
  cmp -s "$SCRIPT_DIR/systemd/onemindd.service" /etc/systemd/system/onemindd.service 2>/dev/null || changed=1
  install -m0644 "$SCRIPT_DIR/systemd/onemindd.service" /etc/systemd/system/onemindd.service
  systemctl daemon-reload
  systemctl enable onemindd >/dev/null 2>&1
  if [ "$changed" = 1 ] || ! systemctl is-active --quiet onemindd; then systemctl restart onemindd; fi
}

# ------------------------------------------------------------------------------------------
# 6. Gateway + dashboard on the hub (contract §3, §5)
# ------------------------------------------------------------------------------------------
copy_tree() { # copy_tree SRC_DIR DEST_DIR: replace DEST with SRC, leaving dev clutter behind
  rm -rf "$2.new"; mkdir -p "$2.new"
  tar -C "$1" --exclude=.venv --exclude=data --exclude=node_modules --exclude=dist \
      --exclude=__pycache__ --exclude=.pytest_cache -cf - . | tar -C "$2.new" -xf -
  rm -rf "$2"; mv "$2.new" "$2"
}

gateway_user() {
  if [ "$DRY_RUN" = 1 ]; then
    step "Gateway user"
    plan "useradd --system --home-dir $STATE --shell /usr/sbin/nologin onemind (if missing)"
    plan "install -d -m0750 -o onemind -g onemind $STATE"
    return 0
  fi
  id onemind >/dev/null 2>&1 || useradd --system --home-dir "$STATE" --shell /usr/sbin/nologin onemind
  install -d -m0750 -o onemind -g onemind "$STATE"
}

# Offline bundle: unpack the runtime deploy/bundle.sh built with this same uv step for /opt/onemind.
gateway_runtime_from_bundle() {
  local stamp="$PREFIX/.gateway-runtime-sha256" sum new="$PREFIX/.runtime.new"
  if [ "$DRY_RUN" = 1 ]; then
    step "Gateway runtime from the bundle"
    plan "unpack ${GATEWAY_RUNTIME##*/} (Python 3.12 + venv, built for $PREFIX) -> $PREFIX/python, $PREFIX/venv"
    plan "copy sdk/schema -> $PREFIX/sdk/schema and apps/ -> $PREFIX/apps"
    return 0
  fi
  [ -f "$GATEWAY_RUNTIME" ] || die "the bundle has no ${GATEWAY_RUNTIME##*/}"
  sum=$(sha256sum "$GATEWAY_RUNTIME" | cut -d' ' -f1)
  if [ "$(cat "$stamp" 2>/dev/null)" = "$sum" ]; then
    log "gateway: runtime from the bundle is up to date"
  else
    log "gateway: unpacking the bundle's prebuilt runtime into $PREFIX"
    rm -rf "$new"; mkdir -p "$new"
    tar -xzf "$GATEWAY_RUNTIME" -C "$new" --no-same-owner
    [ -f "$new/opt/onemind/venv/pyvenv.cfg" ] && [ -d "$new/opt/onemind/python" ] \
      || die "${GATEWAY_RUNTIME##*/} does not hold opt/onemind/{python,venv}"
    rm -rf "$PREFIX/python" "$PREFIX/venv" "$PREFIX/core"
    mv "$new/opt/onemind/python" "$PREFIX/python"; mv "$new/opt/onemind/venv" "$PREFIX/venv"; rm -rf "$new"
    printf '%s\n' "$sum" > "$stamp"
  fi
  "$PREFIX/venv/bin/python" -c 'import onemind_core' || die "the bundle's gateway runtime does not run here"
  install -d -m0755 "$PREFIX/sdk"
  copy_tree "$SRC/sdk/schema" "$PREFIX/sdk/schema"
  copy_tree "$SRC/apps" "$PREFIX/apps"
  chmod -R a+rX "$PREFIX"
}

gateway_python() {
  if [ -n "$GATEWAY_RUNTIME" ]; then gateway_runtime_from_bundle; return 0; fi
  if [ "$DRY_RUN" = 1 ]; then
    step "Gateway (core/) into $PREFIX/venv"
    uv_toolchain
    plan "copy core/ -> $PREFIX/core; uv sync --frozen --no-dev --no-editable --managed-python --python 3.12"
    plan "  (uv.lock hash-checks every wheel; uv downloads Python 3.12 into $PREFIX/python and checks its hash)"
    plan "copy sdk/schema -> $PREFIX/sdk/schema and apps/ -> $PREFIX/apps"
    return 0
  fi
  uv_toolchain
  log "gateway: installing core/ with uv $UV_VERSION into $PREFIX/venv"
  copy_tree "$SRC/core" "$PREFIX/core"
  (cd "$PREFIX/core" && env UV_CACHE_DIR="$CACHE/uv" UV_PYTHON_INSTALL_DIR="$PREFIX/python" \
     UV_PROJECT_ENVIRONMENT="$PREFIX/venv" UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
     "$UV" sync --frozen --no-dev --no-editable --managed-python --python 3.12 --quiet)
  install -d -m0755 "$PREFIX/sdk"
  copy_tree "$SRC/sdk/schema" "$PREFIX/sdk/schema"
  copy_tree "$SRC/apps" "$PREFIX/apps"
  chmod -R a+rX "$PREFIX"
}

dashboard_build() {
  local stamp="$PREFIX/dashboard/.onemind-source-sha256" sum
  if [ "$DRY_RUN" = 1 ]; then
    step "Dashboard -> $PREFIX/dashboard (served by the gateway)"
    if [ -n "$DASH_DIST" ]; then plan "copy the prebuilt $DASH_DIST"; return 0; fi
    node_toolchain
    plan "as user onemind: npm ci --ignore-scripts && npm run build (skipped when dashboard/ is unchanged)"
    return 0
  fi
  if [ -n "$DASH_DIST" ]; then
    [ -f "$DASH_DIST/index.html" ] || die "--dashboard-dist $DASH_DIST has no index.html"
    log "dashboard: using prebuilt $DASH_DIST"
    copy_tree_plain "$DASH_DIST" "$PREFIX/dashboard"; return 0
  fi
  sum=$(cd "$SRC/dashboard" && find . -path ./node_modules -prune -o -path ./dist -prune -o -type f -print0 \
        | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)
  if [ -f "$stamp" ] && [ "$(cat "$stamp")" = "$sum" ]; then log "dashboard: up to date"; return 0; fi
  node_toolchain
  log "dashboard: npm ci + vite build with Node $NODE_VERSION (as user onemind, no install scripts)"
  copy_tree "$SRC/dashboard" "$CACHE/dashboard-src"
  # npm packages are third-party code: never run them as root. --ignore-scripts skips dependency
  # lifecycle scripts (esbuild's is an optional speed-up; its platform binary comes as a package).
  install -d -o onemind -g onemind -m0700 "$CACHE/npm-home"
  chown -R onemind:onemind "$CACHE/dashboard-src"
  (cd "$CACHE/dashboard-src" && runuser -u onemind -- env -i PATH="$NODE_DIR/bin:/usr/bin:/bin" HOME="$CACHE/npm-home" \
     npm_config_cache="$CACHE/npm-home/cache" npm_config_update_notifier=false sh -ec \
     'npm ci --ignore-scripts --no-audit --no-fund --loglevel=error >/dev/null; npm run build >/dev/null')
  copy_tree_plain "$CACHE/dashboard-src/dist" "$PREFIX/dashboard"
  printf '%s\n' "$sum" > "$stamp"
  rm -rf "$CACHE/dashboard-src"
}
copy_tree_plain() { rm -rf "$2.new"; mkdir -p "$2.new"; cp -R "$1/." "$2.new/"; rm -rf "$2"; mv "$2.new" "$2"; chmod -R a+rX "$2"; }

# The gateway's own Kubernetes identity: a ServiceAccount bound to the built-in "admin" role
# (full control inside namespaces) plus namespace create/delete. It is not cluster-admin: it
# cannot touch nodes, CRDs or cluster roles. The k3s admin kubeconfig stays root-only.
gateway_kubeconfig() {
  local k="$BIN/k3s kubectl" ca token i
  if [ "$DRY_RUN" = 1 ]; then
    step "Gateway Kubernetes identity"
    plan "kubectl apply: namespace onemind-system, ServiceAccount onemind-gateway + token Secret,"
    plan "  ClusterRole/Binding for namespaces, ClusterRoleBinding to \"admin\" (deploy/README.md explains the scope)"
    plan "write $ETC/gateway.kubeconfig (0640 root:onemind) with that ServiceAccount's token"
    return 0
  fi
  $k apply -f - >/dev/null <<'EOF'
apiVersion: v1
kind: Namespace
metadata: {name: onemind-system, labels: {app.kubernetes.io/part-of: onemind}}
---
apiVersion: v1
kind: ServiceAccount
metadata: {name: onemind-gateway, namespace: onemind-system}
---
apiVersion: v1
kind: Secret
type: kubernetes.io/service-account-token
metadata:
  name: onemind-gateway-token
  namespace: onemind-system
  annotations: {kubernetes.io/service-account.name: onemind-gateway}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: {name: onemind-gateway-namespaces}
rules:
  - apiGroups: [""]
    resources: [namespaces]
    verbs: [get, list, watch, create, update, patch, delete]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: onemind-gateway-namespaces}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: onemind-gateway-namespaces}
subjects: [{kind: ServiceAccount, name: onemind-gateway, namespace: onemind-system}]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: onemind-gateway-admin}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: admin}
subjects: [{kind: ServiceAccount, name: onemind-gateway, namespace: onemind-system}]
EOF
  for i in $(seq 1 30); do
    token=$($k -n onemind-system get secret onemind-gateway-token -o jsonpath='{.data.token}' 2>/dev/null | base64 -d || true)
    [ -n "$token" ] && break; sleep 1
  done
  [ -n "$token" ] || die "the gateway ServiceAccount token was not issued"
  ca=$($k -n onemind-system get secret onemind-gateway-token -o jsonpath='{.data.ca\.crt}')
  (umask 027
   cat > "$ETC/gateway.kubeconfig.new" <<EOF
apiVersion: v1
kind: Config
clusters: [{name: k3s, cluster: {server: "https://127.0.0.1:6443", certificate-authority-data: "$ca"}}]
users: [{name: onemind-gateway, user: {token: "$token"}}]
contexts: [{name: onemind-gateway, context: {cluster: k3s, user: onemind-gateway}}]
current-context: onemind-gateway
EOF
  )
  chgrp onemind "$ETC/gateway.kubeconfig.new"; mv "$ETC/gateway.kubeconfig.new" "$ETC/gateway.kubeconfig"
}

# API tokens (contract §3): 256 random bits each, printed once at the end, and only their sha256
# is stored (core/onemind_core/auth.py reads "sha256:<hex>" keys). No raw token stays on disk.
OWNER_TOKEN="" AGENT_TOKEN=""
new_token() { od -An -N32 -tx1 /dev/urandom | tr -d ' \n'; }
token_hash() { printf '%s' "$1" | sha256sum | cut -d' ' -f1; }
tokens_header() {
  cat <<'EOF'
# OneMind gateway principals (contract §3; v0 static tokens, Kanidm later: BD-03).
# Keys are "sha256:<hex of token>", so this file holds no usable secret.
# Add a principal: printf %s "$TOKEN" | sha256sum  ->  "sha256:<hex>": {id: ..., kind: ..., role: ...}
tokens:
EOF
}
gateway_tokens() {
  local f="$ETC/tokens.yaml"
  if [ "$DRY_RUN" = 1 ]; then
    step "API tokens (contract §3; printed once, only their sha256 is stored)"
    { tokens_header
      printf '  "sha256:<sha256 of the owner token>": {id: owner, kind: person, role: owner}\n'
      [ "$WITH_AGENT" = 0 ] || printf '  "sha256:<sha256 of the agent token>": {id: dev-agent, kind: agent, role: agent}\n'
    } | show_file "$f (only if missing; with --with-agent-token an agent line is added if none exists)" 0640 root:onemind
    return 0
  fi
  if [ -f "$f" ]; then
    log "tokens: $f exists, owner token kept (it was printed at the first install)"
  else
    OWNER_TOKEN=$(new_token)
    (umask 027
     { tokens_header; printf '  "sha256:%s": {id: owner, kind: person, role: owner}\n' "$(token_hash "$OWNER_TOKEN")"; } > "$f")
    chgrp onemind "$f"
  fi
  if [ "$WITH_AGENT" = 1 ]; then
    if grep -q 'kind: agent' "$f"; then
      log "tokens: an agent principal exists, kept"
    else
      AGENT_TOKEN=$(new_token)
      printf '  "sha256:%s": {id: dev-agent, kind: agent, role: agent}\n' "$(token_hash "$AGENT_TOKEN")" >> "$f"
      log "tokens: added the agent principal dev-agent"
    fi
  fi
}

# Before printing new tokens: make sure none of them reached a file (only hashes may be on disk).
no_raw_tokens_on_disk() {
  local pats
  # One token per line, no empty line (an empty pattern would match every file).
  pats=$(for t in "$OWNER_TOKEN" "$AGENT_TOKEN"; do [ -z "$t" ] || printf '%s\n' "$t"; done)
  [ -n "$pats" ] || return 0
  # The tokens reach grep on stdin (-f -), never as arguments: any local user can read /proc/*/cmdline.
  if printf '%s\n' "$pats" | grep -rqsF -f - "$ETC" "$STATE" "$CACHE" /etc/systemd/system /etc/rancher 2>/dev/null; then
    die "a raw API token was found on disk under $ETC, $STATE or $CACHE; not printing it (remove $ETC/tokens.yaml and re-run)"
  fi
}

gateway_env() {
  cat <<EOF
# Written by deploy/install.sh (core/README.md "Environment"; contract §1, §3, §11).
ONEMIND_TOKENS_FILE=$ETC/tokens.yaml
ONEMIND_DATA_DIR=$STATE
ONEMIND_DB_URL=sqlite:///$STATE/onemind.db
ONEMIND_AUDIT_PATH=$STATE/audit.jsonl
ONEMIND_APPS_DIR=$PREFIX/apps
ONEMIND_APP_SCHEMA=$PREFIX/sdk/schema/onemind.app.schema.json
ONEMIND_DASHBOARD_DIST=$PREFIX/dashboard
ONEMIND_EXECUTOR=kubernetes
ONEMIND_KUBECTL=$PREFIX/bin/kubectl
KUBECONFIG=$ETC/gateway.kubeconfig
ONEMIND_NATS_URL=nats://127.0.0.1:4222
ONEMIND_HOST=$BIND
ONEMIND_PORT=8080
# §11.2: the URL app pods use to reach this gateway (written into each agent app's Secret as
# ONEMIND_GATEWAY_URL). The wave-2 gateway reads it from ONEMIND_PUBLIC_URL (core/README.md).
ONEMIND_PUBLIC_URL=$1
EOF
}
kubectl_wrapper() { printf '#!/bin/sh\n# kubectl from k3s for the OneMind gateway (deploy/install.sh)\nexec %s kubectl "$@"\n' "$BIN/k3s"; }

gateway_service() {
  local url=$1
  if [ "$DRY_RUN" = 1 ]; then
    step "Gateway service (:8080, systemd unit onemind-gateway, user onemind)"
    gateway_env "$url" | show_file "$ETC/gateway.env" 0640 root:onemind
    kubectl_wrapper | show_file "$PREFIX/bin/kubectl" 0755
    plan "install $SCRIPT_DIR/systemd/onemind-gateway.service; systemctl enable onemind-gateway; restart"
    plan "wait for http://127.0.0.1:8080/healthz (up to 60 s)"
    return 0
  fi
  gateway_env "$url" > "$ETC/gateway.env"
  chmod 0640 "$ETC/gateway.env"; chgrp onemind "$ETC/gateway.env"
  # kubectl for the gateway: the k3s multi-call binary run as "kubectl" (same version as the
  # cluster). A wrapper, not a symlink, so it never falls back to the root-only k3s.yaml.
  install -d -m0755 "$PREFIX/bin"
  kubectl_wrapper > "$PREFIX/bin/kubectl"
  chmod 0755 "$PREFIX/bin/kubectl"
  install -m0644 "$SCRIPT_DIR/systemd/onemind-gateway.service" /etc/systemd/system/onemind-gateway.service
  systemctl daemon-reload
  systemctl enable onemind-gateway >/dev/null 2>&1
  systemctl restart onemind-gateway
  local i
  for i in $(seq 1 60); do
    curl -fsS "http://127.0.0.1:8080/healthz" >/dev/null 2>&1 && return 0
    sleep 1
  done
  die "the gateway did not answer /healthz in 60 s (journalctl -u onemind-gateway)"
}

# ------------------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------------------
K3S_CHANGED=0
memory_cgroup_check
apt_setup
k3s_binary
if [ "$ROLE" = hub ]; then
  k3s_server
  nats_install
  onemindd_install
  gateway_user
  gateway_python
  dashboard_build
  gateway_kubeconfig
  gateway_tokens
  if [ "$DRY_RUN" = 1 ]; then HUB_URL=${HUB:-"http://<this machine's address>:8080"}; else HUB_URL=${HUB:-"http://$(primary_ip):8080"}; fi
  gateway_service "$HUB_URL"
  if [ "$DRY_RUN" = 1 ]; then
    step "Finish"
    plan "check that no new API token is on disk, then print it once (and the agent token with --with-agent-token)"
    plan "print the join command with the k3s agent token"
    do_firewall_reminder
    exit 0
  fi
  JOIN=$(cat /var/lib/rancher/k3s/server/agent-token)
  no_raw_tokens_on_disk
  banner
  log "hub ready: dashboard and API at $HUB_URL (and http://127.0.0.1:8080 on this box)"
  if [ -n "$OWNER_TOKEN" ]; then
    printf '\nOWNER TOKEN (shown once; only its sha256 is stored in %s):\n\n    %s\n\n' "$ETC/tokens.yaml" "$OWNER_TOKEN"
  fi
  if [ -n "$AGENT_TOKEN" ]; then
    printf 'AGENT TOKEN for an AI agent (dev-agent: may request actions, never approve; shown once):\n\n    %s\n\n' "$AGENT_TOKEN"
  fi
  if [ -n "$OWNER_TOKEN$AGENT_TOKEN" ]; then
    printf 'Save them in a password manager now. Lost? Remove %s and run this again.\n\n' "$ETC/tokens.yaml"
  fi
  printf 'Join another machine (run there, from a checkout of this repo):\n\n'
  printf '    sudo deploy/install.sh --role node --hub %s --token %s\n\n' "$HUB_URL" "$JOIN"
  if [ -n "$BUNDLE" ]; then
    printf 'or from an offline bundle for that machine'"'"'s architecture (deploy/bundle.sh --arch ...):\n\n'
    printf '    sudo BUNDLE/src/deploy/install.sh --role node --hub %s --token %s --bundle BUNDLE\n\n' "$HUB_URL" "$JOIN"
  fi
  printf 'Check this hub:  ONEMIND_TOKEN=<owner token> deploy/verify/verify.sh http://127.0.0.1:8080\n'
  printf 'Check a machine: sudo deploy/verify/node-check.sh   (services, k3s, NATS auth, own heartbeat)\n'
  printf 'Hermes agent (contract §7) model credentials, created by the owner at install time:\n\n'
  printf '    sudo k3s kubectl create namespace app-hermes-agent --dry-run=client -o yaml | sudo k3s kubectl apply -f -\n'
  printf '    read -rs KEY   # paste the key; it stays out of shell history and the process list\n'
  printf "    printf '<PROVIDER>_API_KEY=%%s\\\\n' \"\$KEY\" | sudo k3s kubectl -n app-hermes-agent create secret generic hermes-agent-credentials --from-env-file=/dev/stdin\n\n"
  do_firewall_reminder
else
  k3s_agent
  onemindd_install
  if [ "$DRY_RUN" = 1 ]; then
    step "Finish"
    plan "print where this node sends its k3s join and heartbeats"
    do_firewall_reminder
    exit 0
  fi
  banner
  log "node joined: k3s agent -> https://$(hub_host "$HUB"):6443, heartbeats -> nats://$(hub_host "$HUB"):4222"
  log "check it: sudo $SCRIPT_DIR/verify/node-check.sh"
  do_firewall_reminder
fi
