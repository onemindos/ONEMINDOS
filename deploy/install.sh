#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# OneMind developer install (P6, contract sdk/contracts/poc-v0.md §6; brief 30 D-B2.4, REC-DEC-30).
# UNSUPPORTED DEVELOPER INSTALL, NO OS ROLLBACK: packages are upgraded in place on a stock OS.
#
#   sudo deploy/install.sh --role hub  [--hub http://<this-box>:8080] [--box-name NAME] [--lan-addr IP]
#   sudo deploy/install.sh --role node --join 'onemind-join:v1?…' [--hub-addr IP]
#   sudo deploy/install.sh --uninstall [--purge]
#   deploy/install.sh --role hub --dry-run [--target debian13|rpi5|jetson|do]   # plan only
#   sudo BUNDLE/src/deploy/install.sh --role hub --bundle BUNDLE                # offline bundle
#
# Networking (docs/architecture/NETWORKING.md, CORE-NET-11): the hub runs the mesh coordinator
# (Headscale + embedded DERP), joins its own mesh first, then runs k3s and the NATS leaf listener on
# its mesh address and serves HTTPS with its own box CA. A node joins only through an owner-approved
# one-time code (`onemind fabric ticket` on the hub, or Add a device on the dashboard).
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
# shellcheck source=deploy/backup.sh
. "$SCRIPT_DIR/backup.sh"

PREFIX=/opt/onemind
ETC=/etc/onemind
STATE=/var/lib/onemind
CACHE=/var/cache/onemind
TOOLS=$PREFIX/toolchain
BIN=/usr/local/bin
BANNER="unsupported developer install, no OS rollback"

ROLE="" HUB="" JOIN="" HUB_ADDR="" BOX="" LAN_ADDR="" UNINSTALL=0 PURGE=0 ONEMINDD_BIN="" DASH_DIST="" BIND="127.0.0.1" FORCE_OS=0
DRY_RUN=0 TARGET="" ARCH_OVERRIDE="" BUNDLE="" GATEWAY_RUNTIME="" WITH_AGENT=0
HS_PORT=8444   # Headscale's own TLS listener until onemind-edge fronts it on :443 (NETWORKING.md §4.2)

usage() {
  cat <<EOF
Usage:
  $0 --role hub  [--hub URL] [--box-name NAME] [--lan-addr IP] [--gateway-bind ADDR] [--with-agent-token]
                 [--dashboard-dist DIR] [--onemindd-bin FILE]
  $0 --role node --join 'onemind-join:v1?…' [--hub-addr IP] [--onemindd-bin FILE]
  $0 --uninstall [--purge]
  $0 ... --dry-run [--target debian13|rpi5|jetson|do [--arch amd64|arm64]]
  $0 ... --bundle DIR

  --role hub|node        hub: mesh coordinator, k3s server, NATS, onemindd, gateway + dashboard.
                         node: mesh client, NATS leaf, onemindd, and the k3s agent for a worker.
  --hub URL              hub gateway URL that app pods use (default http://<lan addr>:8080).
  --box-name NAME        the box's name: https://NAME.local and <app>.NAME.local (default: hostname).
  --lan-addr IP          the hub's LAN IPv4 (default: the address of the default route).
  --join PAYLOAD         the join code text from `onemind fabric ticket` or the dashboard's QR (node).
  --hub-addr IP          the hub's LAN IPv4, when this LAN has no working mDNS for NAME.local (node).
  --with-agent-token     hub: also issue an API token for an AI agent (principal dev-agent: may
                         request actions, never approve). Like the owner token it is printed once
                         and only its sha256 is stored. On a re-run it is added if none exists.
  --gateway-bind ADDR    plain-HTTP listen address of the gateway (default 127.0.0.1: local tools and the
                         health gate). The LAN is served by HTTPS on 443/8443 only, so a wider address
                         here is narrowed to loopback by the gateway (H-05).
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
    --join) JOIN=${2:-}; shift 2 ;;
    --hub-addr) HUB_ADDR=${2:-}; shift 2 ;;
    --box-name) BOX=${2:-}; shift 2 ;;
    --lan-addr) LAN_ADDR=${2:-}; shift 2 ;;
    --token) die "--token was the v0 shared join secret; joins now need an owner-approved code: on the hub run 'onemind fabric ticket', then use --join" ;;
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
    plan "systemctl disable --now onemind-gateway-token.timer onemind-gateway onemindd onemind-nats; remove their unit files"
    plan "rm $BIN/onemindd $BIN/onemind $BIN/nats-server"
    plan "run k3s-uninstall.sh / k3s-agent-uninstall.sh if present (k3s and its data)"
    plan "rm /etc/apt/apt.conf.d/52onemind-security-only /etc/needrestart/conf.d/50-onemind.conf"
    plan "rm -r $PREFIX $ETC $CACHE /var/lib/onemind-nats"
    if [ "$PURGE" = 1 ]; then plan "rm -r $STATE /var/lib/onemindd; userdel onemind"; else plan "keep $STATE"; fi
    return 0
  fi
  log "stopping and removing OneMind services"
  systemctl disable --now onemind-gateway-token.timer 2>/dev/null || true
  rm -f /etc/systemd/system/onemind-gateway-token.timer
  if command -v tailscale >/dev/null 2>&1; then tailscale logout >/dev/null 2>&1 || true; fi
  for u in onemind-gateway onemind-gateway-token onemindd onemind-nats onemind-nats-leaf onemind-headscale onemind-nats-accounts.path tailscaled; do
    case "$u" in *.path) ;; *) u="$u.service" ;; esac
    systemctl disable --now "$u" 2>/dev/null || true
    rm -f "/etc/systemd/system/$u"
  done
  rm -rf /etc/systemd/system/onemindd.service.d  # the backup drop-in (deploy/backup.sh)
  rm -rf /etc/systemd/system/onemind-nats-reload.service /etc/systemd/system/tailscaled.service.d \
    /etc/systemd/system/onemind-nats.service.d /etc/systemd/system/k3s.service.d /etc/systemd/system/k3s-agent.service.d
  systemctl daemon-reload
  rm -f "$BIN/onemindd" "$BIN/onemind" "$BIN/nats-server" "$BIN/headscale" /usr/bin/tailscale /usr/sbin/tailscaled /etc/default/tailscaled
  rm -rf /var/lib/tailscale /var/lib/private/onemind-headscale /var/lib/onemind-headscale /var/lib/onemind-nats-leaf
  hosts_block ""
  if [ -x "$BIN/k3s-uninstall.sh" ]; then log "removing k3s server (and its data)"; "$BIN/k3s-uninstall.sh"; fi
  if [ -x "$BIN/k3s-agent-uninstall.sh" ]; then log "removing k3s agent"; "$BIN/k3s-agent-uninstall.sh"; fi
  rm -f /etc/apt/apt.conf.d/52onemind-security-only /etc/needrestart/conf.d/50-onemind.conf /etc/tmpfiles.d/onemind-backup.conf
  rm -rf "$PREFIX" "$ETC" "$CACHE" /var/lib/onemind-nats /var/lib/private/onemind-nats /usr/lib/onemind/restic
  if [ "$PURGE" = 1 ]; then
    rm -rf "$STATE" /var/lib/onemindd /var/lib/onemind-backup
    id onemind >/dev/null 2>&1 && userdel onemind
    log "purged $STATE (database, audit log)"
  else
    [ -d "$STATE" ] && log "kept $STATE (gateway database and audit log); --purge deletes it"
  fi
  log "unattended-upgrades and needrestart stay installed (Debian defaults apply again)"
  log "uninstall done"
}
# The coordinator names in /etc/hosts (NETWORKING.md §5.4: LAN first). Empty address = remove.
hosts_block() {
  local begin="# BEGIN onemind fabric (managed by onemind fabric join)" end="# END onemind fabric"
  awk -v b="$begin" -v e="$end" '$0==b{skip=1;next} $0==e{skip=0;next} !skip' /etc/hosts > /etc/hosts.onemind.new
  [ -n "$1" ] && printf '%s\n%s control.onemind.internal join.onemind.internal\n%s\n' "$begin" "$1" "$end" >> /etc/hosts.onemind.new
  cat /etc/hosts.onemind.new > /etc/hosts; rm -f /etc/hosts.onemind.new
}
if [ "$UNINSTALL" = 1 ]; then uninstall; exit 0; fi

# ------------------------------------------------------------------------------------------
# Arguments and platform
# ------------------------------------------------------------------------------------------
case "$ROLE" in hub|node) ;; *) usage >&2; die "--role hub or --role node is required" ;; esac
NODE_ROLE=""
if [ "$ROLE" = node ]; then
  [ -n "$JOIN" ] || die "--join is required for --role node: on the hub run 'onemind fabric ticket' (or Add a device on the dashboard)"
  # (Length checked apart from the characters: BSD grep, used for --dry-run on a Mac, caps {m,n} at 255.)
  { [ "${#JOIN}" -ge 30 ] && [ "${#JOIN}" -le 640 ] && one_line "$JOIN" 'onemind-join:v1[?][A-Za-z0-9%=&._:/-]+'; } \
    || die "--join does not look like a OneMind join code"
  case "$JOIN" in *role=leaf*) NODE_ROLE=leaf ;; *) NODE_ROLE=worker ;; esac
fi
for a in "$HUB_ADDR" "$LAN_ADDR"; do
  [ -z "$a" ] || printf '%s' "$a" | grep -Eqx '([0-9]{1,3}[.]){3}[0-9]{1,3}' || die "addresses must be IPv4 (got: $a)"
done
if [ -n "$BOX" ]; then printf '%s' "$BOX" | grep -Eqx '[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?' || die "--box-name must be a lowercase DNS label"; fi
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
# avahi + libnss-mdns: NAME.local and <app>.NAME.local (NETWORKING.md §9.1); sqlite3: Headscale backups.
APT_PKGS="ca-certificates curl tar gzip iproute2 unattended-upgrades needrestart apt-listchanges avahi-daemon avahi-utils libnss-mdns sqlite3"
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

# k3s over the mesh: node IP and API on the hub's mesh address, pod traffic in WireGuard (H-17).
# Traefik and ServiceLB are off: the gateway owns :443/:80 and reaches apps on their ClusterIPs
# (proxy.py); ServiceLB would otherwise DNAT LAN traffic for 80/443 to Traefik.
k3s_server_config() {
  local ip=${HUB_MESH_IP:-<the hub mesh address>}
  printf '# Written by deploy/install.sh (NETWORKING.md §8)\nwrite-kubeconfig-mode: "0600"\nagent-token: "%s"\nsecrets-encryption: true\nkube-apiserver-arg:\n  - "admission-control-config-file=/etc/rancher/k3s/psa.yaml"\nnode-ip: "%s"\nadvertise-address: "%s"\ntls-san: ["hub.onemind.internal", "%s"]\nflannel-backend: "wireguard-native"\nflannel-iface: "tailscale0"\ndisable: ["traefik", "servicelb"]\n' \
    "$1" "$ip" "$ip" "$ip"
}

k3s_server() {
  local cfg=/etc/rancher/k3s/config.yaml agent_token new_cfg
  if [ "$DRY_RUN" = 1 ]; then
    step "k3s server (the hub)"
    plan "generate the k3s agent token once (32 random bytes) -> $ETC/k3s-agent-token (0600)"
    plan "install deploy/k8s/psa.yaml -> /etc/rancher/k3s/psa.yaml (0600): cluster-wide Pod Security defaults (H-01)"
    k3s_server_config "<the agent token, generated on the machine>" | show_file "$cfg" 0600
    plan "INSTALL_K3S_SKIP_DOWNLOAD=true INSTALL_K3S_EXEC=server sh $CACHE/k3s-install-$K3S_INSTALL_COMMIT.sh (if k3s changed or is not running)"
    plan "wait until the k3s node is Ready (up to 180 s)"
    return 0
  fi
  install -d -m0700 /etc/rancher/k3s
  # A separate agent token: nodes can join as agents but can never join as servers (D-B6.2).
  if [ -f "$ETC/k3s-agent-token" ]; then agent_token=$(cat "$ETC/k3s-agent-token")
  else agent_token=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n'); (umask 077; printf '%s' "$agent_token" > "$ETC/k3s-agent-token"); fi
  # A cluster made before the mesh (flannel VXLAN on the LAN) cannot be switched in place (NETWORKING.md §8).
  if [ -d /var/lib/rancher/k3s/server/db ] && ! grep -q '^flannel-backend: "wireguard-native"' "$cfg" 2>/dev/null; then
    die "this hub's k3s cluster predates the mesh; back it up, run --uninstall, then install again"
  fi
  # H-01: cluster-wide Pod Security defaults (deploy/k8s/psa.yaml). H-12: Secrets encrypted in
  # the k3s datastore (and so in every backup of it).
  cmp -s "$SCRIPT_DIR/k8s/psa.yaml" /etc/rancher/k3s/psa.yaml 2>/dev/null \
    || { install -m0600 "$SCRIPT_DIR/k8s/psa.yaml" /etc/rancher/k3s/psa.yaml; K3S_CHANGED=1; }
  new_cfg=$(k3s_server_config "$agent_token")
  k3s_mesh_dropin k3s
  if [ "$(cat "$cfg" 2>/dev/null)" != "$new_cfg" ]; then (umask 077; printf '%s\n' "$new_cfg" > "$cfg"); K3S_CHANGED=1; fi
  if [ "${K3S_CHANGED:-0}" = 1 ] || ! systemctl is-active --quiet k3s; then
    log "k3s $K3S_VERSION server: install/restart"
    # FORCE_RESTART: upstream's script restarts only when the binary or unit changed, not config.yaml.
    INSTALL_K3S_SKIP_DOWNLOAD=true INSTALL_K3S_SELINUX_WARN=true INSTALL_K3S_SKIP_SELINUX_RPM=true \
      INSTALL_K3S_FORCE_RESTART=true INSTALL_K3S_EXEC=server sh "$CACHE/k3s-install-$K3S_INSTALL_COMMIT.sh" >/dev/null
  fi
  log "waiting for the k3s node to be Ready"
  local i
  for i in $(seq 1 90); do
    "$BIN/k3s" kubectl get nodes 2>/dev/null | grep -qw Ready && break
    [ "$i" = 90 ] && die "k3s did not become Ready in 180 s (journalctl -u k3s)"
    sleep 2
  done
  for i in $(seq 1 60); do [ -s /var/lib/rancher/k3s/server/agent-token ] && break; sleep 1; done
  # A hub first installed with Traefik keeps its LoadBalancer Service after k3s uninstalls the chart,
  # and kube-proxy then rejects :80/:443 on the node addresses, in front of the gateway. Its
  # load-balancer finalizer belonged to ServiceLB, which is off now, so it is cleared first.
  if "$BIN/k3s" kubectl -n kube-system get service/traefik >/dev/null 2>&1; then
    "$BIN/k3s" kubectl -n kube-system patch service/traefik --type=merge -p '{"metadata":{"finalizers":null}}' >/dev/null 2>&1 || true
    "$BIN/k3s" kubectl -n kube-system delete service/traefik deployment/traefik --ignore-not-found --wait=false >/dev/null 2>&1 || true
  fi
  # The CA hash nodes pin in their 1-hour bootstrap token (K10<sha256 of /cacerts>::id.secret).
  K3S_CA_HASH="K10$(curl -fsk https://127.0.0.1:6443/cacerts | sha256sum | cut -d' ' -f1)"
  secrets_encryption_check
}

# H-12: `secrets-encryption: true` encrypts what is written from now on. Secrets written before
# it was turned on (an install from before this change) stay in clear until rewritten, so they
# are rewritten once.
secrets_encryption_check() {
  local st="" i
  for i in $(seq 1 30); do
    st=$("$BIN/k3s" secrets-encrypt status 2>/dev/null || true)
    printf '%s' "$st" | grep -q 'Encryption Status: Enabled' && break
    sleep 2
  done
  printf '%s' "$st" | grep -q 'Encryption Status: Enabled' \
    || die "k3s secrets encryption is not enabled (k3s secrets-encrypt status)"
  if [ ! -f "$ETC/k3s-secrets-reencrypted" ]; then
    log "k3s: rewriting existing Secrets so they are stored encrypted"
    # k3s itself updates a few Secrets right after start (the node password), so a replace of a
    # stale copy can answer "Conflict". Read again and retry; replacing is safe to repeat.
    local ok=""
    for i in 1 2 3 4 5; do
      if "$BIN/k3s" kubectl get secrets -A -o json | "$BIN/k3s" kubectl replace -f - >/dev/null; then
        ok=1; break
      fi
      sleep 2
    done
    [ -n "$ok" ] || die "rewriting existing Secrets failed"
    : > "$ETC/k3s-secrets-reencrypted"
  fi
}

# k3s waits for this machine's mesh address before it starts (NETWORKING.md §5.2).
k3s_mesh_dropin() {
  local d="/etc/systemd/system/$1.service.d"
  install -d -m0755 "$d"
  cat > "$d/onemind-mesh.conf.new" <<'EOF'
# Written by deploy/install.sh: k3s runs on the mesh address (NETWORKING.md §5.2, §8).
[Unit]
After=tailscaled.service
Wants=tailscaled.service
[Service]
ExecStartPre=/usr/local/bin/onemindd mesh wait-ip --timeout 120s
EOF
  if ! cmp -s "$d/onemind-mesh.conf.new" "$d/onemind-mesh.conf" 2>/dev/null; then
    mv "$d/onemind-mesh.conf.new" "$d/onemind-mesh.conf"; systemctl daemon-reload; K3S_CHANGED=1
  else rm -f "$d/onemind-mesh.conf.new"; fi
}

# The agent's server, 1-hour token, mesh node-ip and flannel interface are in
# /etc/rancher/k3s/config.yaml, written by `onemind fabric join` after the owner approved.
k3s_agent() {
  local cfg=/etc/rancher/k3s/config.yaml server
  if [ "$DRY_RUN" = 1 ]; then
    step "k3s agent (joins the hub over the mesh)"
    plan "read the server URL from $cfg (written by 'onemind fabric join' after the owner approved)"
    plan "k3s-agent drop-in: wait for the mesh address first; INSTALL_K3S_SKIP_DOWNLOAD=true INSTALL_K3S_EXEC=agent sh $CACHE/k3s-install-$K3S_INSTALL_COMMIT.sh"
    plan "(only if the config or k3s changed, or k3s-agent is not running)"
    return 0
  fi
  server=$(sed -n 's/^server: "\(.*\)"$/\1/p' "$cfg" 2>/dev/null)
  [ -n "$server" ] || die "$cfg has no server: the join did not deliver k3s credentials"
  k3s_mesh_dropin k3s-agent
  if [ "${K3S_CHANGED:-0}" = 1 ] || ! systemctl is-active --quiet k3s-agent; then
    log "k3s $K3S_VERSION agent: joining $server over the mesh"
    K3S_URL="$server" INSTALL_K3S_SKIP_DOWNLOAD=true INSTALL_K3S_SELINUX_WARN=true INSTALL_K3S_SKIP_SELINUX_RPM=true \
      INSTALL_K3S_FORCE_RESTART=true INSTALL_K3S_EXEC=agent sh "$CACHE/k3s-install-$K3S_INSTALL_COMMIT.sh" >/dev/null
  fi
}

# ------------------------------------------------------------------------------------------
# 3. NATS (contract §12.9, H-06; NETWORKING.md §7)
#    hub: clients on loopback only; nodes reach it as leaves over the mesh, TLS with the box CA, each
#    with its own nkey in its own account (core/onemind_core/natsconf.py, FB-3 lab E2).
#    node: a local leaf (onemind-nats-leaf.service), configured by `onemind fabric join`.
# ------------------------------------------------------------------------------------------
nats_binary() {
  local tgz="nats-server-$NATS_VERSION-linux-$ARCH.tar.gz"
  fetch "https://github.com/nats-io/nats-server/releases/download/$NATS_VERSION/$tgz" "$(pick NATS_SHA256)" "$CACHE/$tgz"
  if [ "$DRY_RUN" = 1 ]; then
    plan "extract nats-server -> $BIN/nats-server (if the version differs)"
    return 0
  fi
  if ! "$BIN/nats-server" --version 2>/dev/null | grep -q "${NATS_VERSION#v}"; then
    tar -xzf "$CACHE/$tgz" -C "$CACHE" "nats-server-$NATS_VERSION-linux-$ARCH/nats-server"
    install -m0755 "$CACHE/nats-server-$NATS_VERSION-linux-$ARCH/nats-server" "$BIN/nats-server"
    rm -rf "$CACHE/nats-server-$NATS_VERSION-linux-$ARCH"
  fi
}

nats_install() {
  [ "$DRY_RUN" = 1 ] && step "NATS $NATS_VERSION on the hub (loopback :4222; leaf listener on the mesh address, TLS, per-node accounts)"
  nats_binary
  if [ "$DRY_RUN" = 1 ]; then
    plan "hub accounts file $STATE/nats/accounts.conf (python -m onemind_core.natsconf), linked beside nats.conf"
    plan "write $ETC/nats.conf: listen 127.0.0.1:4222, leafnodes on <mesh address>:7422 with TLS (box CA, verify)"
    plan "install $SCRIPT_DIR/systemd/onemind-nats.service, a mesh drop-in, onemind-nats-accounts.path and -reload.service; enable and restart"
    return 0
  fi
  # The accounts file the gateway owns; NATS includes it through a link beside nats.conf, because
  # nats-server resolves include paths relative to the including file.
  install -d -m0755 -o onemind -g onemind "$STATE/nats"
  runuser -u onemind -- "$PREFIX/venv/bin/python" -m onemind_core.natsconf "$STATE/nats/accounts.conf"
  ln -sfn "$STATE/nats/accounts.conf" "$ETC/nats-accounts.conf"
  cat > "$ETC/nats.conf" <<EOF
# OneMind hub NATS (deploy/install.sh; NETWORKING.md §7). Do not edit: rewritten on install.
server_name: hub
listen: 127.0.0.1:4222
http: 127.0.0.1:8222
max_payload: 1MB
# A dead leaf link shows within about a minute instead of 3-7 (FB-3 lab, observation "outage detection").
ping_interval: "20s"
ping_max: 2
write_deadline: "10s"
leafnodes {
  listen: "$HUB_MESH_IP:7422"
  tls {
    cert_file: "/run/credentials/onemind-nats.service/nats.crt"
    key_file: "/run/credentials/onemind-nats.service/nats.key"
    ca_file: "/run/credentials/onemind-nats.service/ca.crt"
    verify: true
    timeout: 5
  }
}
include "nats-accounts.conf"
EOF
  chmod 0644 "$ETC/nats.conf"
  install -m0644 "$SCRIPT_DIR/systemd/onemind-nats.service" /etc/systemd/system/onemind-nats.service
  install -d -m0755 /etc/systemd/system/onemind-nats.service.d
  cat > /etc/systemd/system/onemind-nats.service.d/onemind-mesh.conf <<'EOF'
# Written by deploy/install.sh: the leaf listener is bound to the hub's mesh address, and the TLS
# files come from the gateway's box CA without giving the NATS user access to that directory.
[Unit]
After=tailscaled.service
Wants=tailscaled.service
[Service]
ExecStartPre=+/usr/local/bin/onemindd mesh wait-ip --timeout 120s
LoadCredential=nats.crt:/var/lib/onemind/tls/nats.crt
LoadCredential=nats.key:/var/lib/onemind/tls/nats.key
LoadCredential=ca.crt:/var/lib/onemind/tls/ca.crt
EOF
  install -m0644 "$SCRIPT_DIR/systemd/onemind-nats-accounts.path" /etc/systemd/system/onemind-nats-accounts.path
  install -m0644 "$SCRIPT_DIR/systemd/onemind-nats-reload.service" /etc/systemd/system/onemind-nats-reload.service
  systemctl daemon-reload
  systemctl enable onemind-nats onemind-nats-accounts.path >/dev/null 2>&1
  systemctl restart onemind-nats
  systemctl restart onemind-nats-accounts.path
}

nats_leaf_install() {  # node
  [ "$DRY_RUN" = 1 ] && step "NATS leaf on this node (local bus on loopback; linked to the hub over the mesh by 'onemind fabric join')"
  nats_binary
  if [ "$DRY_RUN" = 1 ]; then
    plan "system user onemind-nats; $ETC/nats (0750); install $SCRIPT_DIR/systemd/onemind-nats-leaf.service"
    return 0
  fi
  id onemind-nats >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin onemind-nats
  install -d -m0750 -o onemind-nats -g onemind-nats "$ETC/nats"
  install -m0644 "$SCRIPT_DIR/systemd/onemind-nats-leaf.service" /etc/systemd/system/onemind-nats-leaf.service
  systemctl daemon-reload
}

# ------------------------------------------------------------------------------------------
# 3b. Mesh (NETWORKING.md §4, §5): Tailscale client everywhere, Headscale on the hub.
#     Nothing talks to Tailscale Inc: no log upload, no DERP map from them, the client trusts
#     only the box CA for the coordinator.
# ------------------------------------------------------------------------------------------
tailscale_install() {
  local tgz="tailscale_${TAILSCALE_VERSION}_$ARCH.tgz" d
  [ "$DRY_RUN" = 1 ] && step "Mesh client: Tailscale $TAILSCALE_VERSION (static tarball, sha256-pinned; no log upload)"
  fetch "https://pkgs.tailscale.com/stable/$tgz" "$(pick TAILSCALE_SHA256)" "$CACHE/$tgz"
  if [ "$DRY_RUN" = 1 ]; then
    plan "install tailscale, tailscaled and tailscaled.service (never replacing a Tailscale client this machine already had); SSL_CERT_FILE = the box CA"
    return 0
  fi
  if !/usr/sbin/tailscaled --version 2>/dev/null | head -1 | grep -qxF "$TAILSCALE_VERSION"; then
    d="$CACHE/tailscale_${TAILSCALE_VERSION}_$ARCH"; rm -rf "$d"
    tar -xzf "$CACHE/$tgz" -C "$CACHE"
    install -m0755 "$d/tailscale" /usr/bin/tailscale
    install -m0755 "$d/tailscaled" /usr/sbin/tailscaled
    install -m0644 "$d/systemd/tailscaled.service" /etc/systemd/system/tailscaled.service
    rm -rf "$d"
  fi
  printf '# Written by deploy/install.sh (NETWORKING.md S12: no log upload to Tailscale Inc)\nPORT="41641"\nFLAGS="--no-logs-no-support"\n' > /etc/default/tailscaled
  install -d -m0755 /etc/systemd/system/tailscaled.service.d
  cat > /etc/systemd/system/tailscaled.service.d/onemind.conf <<'EOF'
# Written by deploy/install.sh: the coordinator's certificate is checked against the box CA only.
[Service]
Environment=SSL_CERT_FILE=/etc/onemind/identity/ca.pem
Environment=TS_NO_LOGS_NO_SUPPORT=true
EOF
  systemctl daemon-reload
  systemctl enable tailscaled >/dev/null 2>&1
}

hs() { "$BIN/headscale" -c "$ETC/headscale/config.yaml" "$@"; }

headscale_install() {  # hub
  local f="headscale_${HEADSCALE_VERSION}_linux_$ARCH" i
  [ "$DRY_RUN" = 1 ] && step "Mesh coordinator: Headscale $HEADSCALE_VERSION on the hub (TLS :$HS_PORT, embedded DERP)"
  fetch "https://github.com/juanfont/headscale/releases/download/v$HEADSCALE_VERSION/$f" "$(pick HEADSCALE_SHA256)" "$CACHE/$f"
  if [ "$DRY_RUN" = 1 ]; then
    plan "install -> $BIN/headscale; write $ETC/headscale/config.yaml; unit onemind-headscale (dynamic user); enable and start"
    return 0
  fi
  cmp -s "$CACHE/$f" "$BIN/headscale" 2>/dev/null || install -m0755 "$CACHE/$f" "$BIN/headscale"
  install -d -m0755 "$ETC/headscale"
  cat > "$ETC/headscale/config.yaml" <<EOF
# Generated by deploy/install.sh (NETWORKING.md §4.2). Do not edit: rewritten on install.
server_url: https://control.onemind.internal:$HS_PORT
listen_addr: 0.0.0.0:$HS_PORT
metrics_listen_addr: 127.0.0.1:9091
grpc_listen_addr: 127.0.0.1:50443
grpc_allow_insecure: false
tls_cert_path: /run/credentials/onemind-headscale.service/tls.crt
tls_key_path: /run/credentials/onemind-headscale.service/tls.key
noise:
  private_key_path: /var/lib/onemind-headscale/noise_private.key
prefixes:
  v4: 100.64.0.0/10
  v6: fd7a:115c:a1e0::/48
  allocation: sequential
derp:
  server:
    enabled: true
    region_id: 999
    region_code: onemind-hub
    region_name: OneMind hub
    verify_clients: true
    stun_listen_addr: 0.0.0.0:3478
    private_key_path: /var/lib/onemind-headscale/derp_server_private.key
    automatically_add_embedded_derp_region: true
    ipv4: $LAN_ADDR
  urls: []
  paths: []
  auto_update_enabled: false
disable_check_updates: true
ephemeral_node_inactivity_timeout: 30m
database:
  type: sqlite
  sqlite:
    path: /var/lib/onemind-headscale/db.sqlite
    write_ahead_log: true
policy:
  mode: database
dns:
  magic_dns: true
  base_domain: onemind.internal
  override_local_dns: false
  nameservers:
    global: []
unix_socket: /run/onemind-headscale/headscale.sock
unix_socket_permission: "0770"
logtail:
  enabled: false
log:
  level: info
EOF
  install -m0644 "$SCRIPT_DIR/systemd/onemind-headscale.service" /etc/systemd/system/onemind-headscale.service
  systemctl daemon-reload
  systemctl enable onemind-headscale >/dev/null 2>&1
  systemctl restart onemind-headscale
  for i in $(seq 1 30); do [ -S /run/onemind-headscale/headscale.sock ] && hs users list >/dev/null 2>&1 && return 0; sleep 1; done
  die "Headscale did not start (journalctl -u onemind-headscale)"
}

# The hub enrolls itself with a key it mints over Headscale's local socket (NETWORKING.md §5.2),
# then gives the gateway a Headscale API key (0600, the gateway's user) for approved joins.
mesh_hub() {
  local uid key
  if [ "$DRY_RUN" = 1 ]; then
    step "The hub joins its own mesh"
    plan "mint a single-use key over Headscale's local socket (10 min, tags hub and k3s), tailscale up, wait for the mesh address"
    plan "give the gateway a Headscale API key ($ETC/headscale.key, 0600, user onemind)"
    return 0
  fi
  hosts_block 127.0.0.1
  systemctl restart tailscaled
  if ! /usr/local/bin/onemindd mesh wait-ip --timeout 5s >/dev/null 2>&1; then
    hs users list -o json | grep -q '"name": *"onemind-machines"' || hs users create onemind-machines >/dev/null
    uid=$(hs users list -o json | "$PREFIX/venv/bin/python" -I -c 'import json,sys; print(next(u["id"] for u in json.load(sys.stdin) if u["name"] == "onemind-machines"))')
    key=$(hs preauthkeys create --user "$uid" --tags tag:onemind-hub,tag:onemind-k3s --expiration 10m -o json \
          | "$PREFIX/venv/bin/python" -I -c 'import json,sys; print(json.load(sys.stdin)["key"])')
    install -d -m0700 /run/onemind
    (umask 077; printf '%s' "$key" > /run/onemind/hub-authkey)
    log "mesh: the hub joins its own coordinator"
    tailscale up --reset --login-server "https://control.onemind.internal:$HS_PORT" --auth-key file:/run/onemind/hub-authkey \
      --hostname hub --accept-routes=false --accept-dns=false --ssh=false --timeout 60s
    rm -f /run/onemind/hub-authkey
  fi
  HUB_MESH_IP=$(/usr/local/bin/onemindd mesh wait-ip --timeout 60s) || die "the hub did not get a mesh address (tailscale status)"
  log "mesh: hub is $HUB_MESH_IP on the mesh"
  if [ ! -s "$ETC/headscale.key" ]; then
    (umask 077; hs apikeys create --expiration 90d | tail -n1 | tr -d '\r\n' > "$ETC/headscale.key.new")
    chown onemind:onemind "$ETC/headscale.key.new"; chmod 0600 "$ETC/headscale.key.new"; mv "$ETC/headscale.key.new" "$ETC/headscale.key"
  fi
}

# The box CA and the server certificates it issues (core/onemind_core/ca.py), made as the gateway's
# user so the CA key never belongs to anyone else. Prints nothing secret.
box_certs() {
  local extra=""
  if [ "$DRY_RUN" = 1 ]; then
    step "Box CA and HTTPS certificates (as the gateway's user, under $STATE/tls)"
    plan "python -m onemind_core.ca: the CA, the HTTPS certificate for the box and app names, Headscale's control certificate, the NATS leaf listener certificate"
    return 0
  fi
  [ -n "${HUB_MESH_IP:-}" ] && extra="--nats-ip $HUB_MESH_IP"
  # shellcheck disable=SC2086
  BOX_CA_SHA=$(runuser -u onemind -- "$PREFIX/venv/bin/python" -m onemind_core.ca --dir "$STATE/tls" --box "$BOX" --control $extra)
  install -d -m0755 "$ETC/identity"
  install -m0644 "$STATE/tls/ca.crt" "$ETC/identity/ca.pem"
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
  nats_url=nats://127.0.0.1:4222   # hub: its NATS; node: its local leaf (NETWORKING.md §7)
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
# copy_src_tree SRC_DIR DEST_DIR: web sources (dashboard/, ui/src/). Only the top-level dependency
# and build output stay behind: copy_tree's unanchored --exclude=data would also drop
# dashboard/src/data/, because tar matches an exclude against every path component.
copy_src_tree() {
  rm -rf "$2.new"; mkdir -p "$2.new"
  tar -C "$1" --exclude=./node_modules --exclude=./dist -cf - . | tar -C "$2.new" -xf -
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
  # 0751: the hub NATS reads nats/accounts.conf inside; nothing in it can be listed or read by others.
  install -d -m0751 -o onemind -g onemind "$STATE"
}

# Offline bundle: unpack the runtime deploy/bundle.sh built with this same uv step for /opt/onemind.
gateway_runtime_from_bundle() {
  local stamp="$PREFIX/.gateway-runtime-sha256" sum new="$PREFIX/.runtime.new"
  if [ "$DRY_RUN" = 1 ]; then
    step "Gateway runtime from the bundle"
    plan "unpack ${GATEWAY_RUNTIME##*/} (Python 3.12 + venv, built for $PREFIX) -> $PREFIX/python, $PREFIX/venv"
    plan "copy sdk/schema and sdk/policy -> $PREFIX/sdk and apps/ -> $PREFIX/apps"
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
    if [ -f "$new/opt/onemind/venv/pyvenv.cfg" ] && [ -d "$new/opt/onemind/python" ]; then
      :
    else
      die "${GATEWAY_RUNTIME##*/} does not hold opt/onemind/{python,venv}"
    fi
    rm -rf "$PREFIX/python" "$PREFIX/venv" "$PREFIX/core"
    mv "$new/opt/onemind/python" "$PREFIX/python"; mv "$new/opt/onemind/venv" "$PREFIX/venv"; rm -rf "$new"
    printf '%s\n' "$sum" > "$stamp"
  fi
  "$PREFIX/venv/bin/python" -c 'import onemind_core' || die "the bundle's gateway runtime does not run here"
  install -d -m0755 "$PREFIX/sdk"
  copy_tree "$SRC/sdk/schema" "$PREFIX/sdk/schema"
  copy_tree "$SRC/sdk/policy" "$PREFIX/sdk/policy"   # the install sandbox rules (H-02), as in the build-on-box path
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
    plan "copy sdk/schema and sdk/policy -> $PREFIX/sdk and apps/ -> $PREFIX/apps"
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
  copy_tree "$SRC/sdk/policy" "$PREFIX/sdk/policy"
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
  # The dashboard imports the design system from source (../ui/src), so both trees count.
  sum=$(cd "$SRC" && find dashboard ui/src -path dashboard/node_modules -prune -o -path dashboard/dist -prune -o -type f -print0 \
        | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)
  if [ -f "$stamp" ] && [ "$(cat "$stamp")" = "$sum" ]; then log "dashboard: up to date"; return 0; fi
  node_toolchain
  log "dashboard: npm ci + vite build with Node $NODE_VERSION (as user onemind, no install scripts)"
  copy_src_tree "$SRC/dashboard" "$CACHE/dashboard-src"
  copy_src_tree "$SRC/ui/src" "$CACHE/ui/src"   # ../ui/src as seen from dashboard-src
  # npm packages are third-party code: never run them as root. --ignore-scripts skips dependency
  # lifecycle scripts (esbuild's is an optional speed-up; its platform binary comes as a package).
  install -d -o onemind -g onemind -m0700 "$CACHE/npm-home"
  chown -R onemind:onemind "$CACHE/dashboard-src" "$CACHE/ui"
  (cd "$CACHE/dashboard-src" && runuser -u onemind -- env -i PATH="$NODE_DIR/bin:/usr/bin:/bin" HOME="$CACHE/npm-home" \
     npm_config_cache="$CACHE/npm-home/cache" npm_config_update_notifier=false sh -ec \
     'npm ci --ignore-scripts --no-audit --no-fund --loglevel=error >/dev/null; npm run build >/dev/null')
  copy_tree_plain "$CACHE/dashboard-src/dist" "$PREFIX/dashboard"
  printf '%s\n' "$sum" > "$stamp"
  rm -rf "$CACHE/dashboard-src" "$CACHE/ui"
}
copy_tree_plain() { rm -rf "$2.new"; mkdir -p "$2.new"; cp -R "$1/." "$2.new/"; rm -rf "$2"; mv "$2.new" "$2"; chmod -R a+rX "$2"; }

# The gateway's own Kubernetes identity (H-03): deploy/k8s/gateway-rbac.yaml. Cluster-wide it may
# only manage app-* namespaces and bind onemind-app-deployer inside them (fenced by a
# ValidatingAdmissionPolicy); its token is a 24-hour bound token renewed every 6 hours by
# onemind-gateway-token.timer. The k3s admin kubeconfig stays root-only.
gateway_kubeconfig() {
  local k="$BIN/k3s kubectl"
  if [ "$DRY_RUN" = 1 ]; then
    step "Gateway Kubernetes identity (H-03)"
    plan "kubectl apply -f deploy/k8s/gateway-rbac.yaml (app-* namespaces only; fenced by a ValidatingAdmissionPolicy)"
    plan "write $PREFIX/bin/onemind-gateway-kubeconfig: issues a 24-hour token into $ETC/gateway.kubeconfig (0640 root:onemind)"
    plan "enable onemind-gateway-token.timer (renews it every 6 hours)"
    return 0
  fi
  $k apply -f "$SCRIPT_DIR/k8s/gateway-rbac.yaml" >/dev/null
  # Earlier installs: the cluster-wide admin binding and the never-expiring token Secret.
  $k delete clusterrolebinding onemind-gateway-admin --ignore-not-found=true >/dev/null
  $k -n onemind-system delete secret onemind-gateway-token --ignore-not-found=true >/dev/null
  install -d -m0755 "$PREFIX/bin"
  cat > "$PREFIX/bin/onemind-gateway-kubeconfig" <<EOF
#!/bin/sh
# Written by deploy/install.sh: a fresh 24-hour token for the OneMind gateway (H-03).
set -eu
token=\$($BIN/k3s kubectl -n onemind-system create token onemind-gateway --duration=24h)
ca=\$(base64 -w0 < /var/lib/rancher/k3s/server/tls/server-ca.crt)
umask 027
cat > "$ETC/gateway.kubeconfig.new" <<KUBECONFIG
apiVersion: v1
kind: Config
clusters: [{name: k3s, cluster: {server: "https://127.0.0.1:6443", certificate-authority-data: "\$ca"}}]
users: [{name: onemind-gateway, user: {token: "\$token"}}]
contexts: [{name: onemind-gateway, context: {cluster: k3s, user: onemind-gateway}}]
current-context: onemind-gateway
KUBECONFIG
chgrp onemind "$ETC/gateway.kubeconfig.new"
mv "$ETC/gateway.kubeconfig.new" "$ETC/gateway.kubeconfig"
EOF
  chmod 0755 "$PREFIX/bin/onemind-gateway-kubeconfig"
  "$PREFIX/bin/onemind-gateway-kubeconfig" || die "could not issue the gateway's Kubernetes token"
  install -m0644 "$SCRIPT_DIR/systemd/onemind-gateway-token.service" /etc/systemd/system/onemind-gateway-token.service
  install -m0644 "$SCRIPT_DIR/systemd/onemind-gateway-token.timer" /etc/systemd/system/onemind-gateway-token.timer
  systemctl daemon-reload
  systemctl enable --now onemind-gateway-token.timer >/dev/null 2>&1
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
# Install sandbox (H-02, H-03): the rule file, and the ServiceAccount bound in each app-<id>.
ONEMIND_SANDBOX_RULES=$PREFIX/sdk/policy/app-objects.yaml
ONEMIND_SANDBOX_GATEWAY_SA=onemind-system/onemind-gateway
ONEMIND_NATS_URL=nats://127.0.0.1:4222
ONEMIND_HOST=$BIND
ONEMIND_PORT=8080
# §11.2: the URL app pods use to reach this gateway (written into each agent app's Secret as
# ONEMIND_GATEWAY_URL). The wave-2 gateway reads it from ONEMIND_PUBLIC_URL (core/README.md).
ONEMIND_PUBLIC_URL=$1
# Networking (core/onemind_core/netconf.py; NETWORKING.md): HTTPS with the box CA on 443 and 8443,
# :80 redirects, onemind.local and <app>.$BOX.local over mDNS, the mesh and fabric joins.
ONEMIND_NET_BOX_NAME=$BOX
ONEMIND_NET_LAN_ADDR=$LAN_ADDR
ONEMIND_NET_TLS=1
ONEMIND_NET_TLS_DIR=$STATE/tls
ONEMIND_NET_HTTP_REDIRECT_PORT=80
ONEMIND_NET_MDNS=1
ONEMIND_MESH_ENABLED=1
ONEMIND_MESH_HEADSCALE_URL=https://127.0.0.1:$HS_PORT
ONEMIND_MESH_CONTROL_URL=https://control.onemind.internal:$HS_PORT
ONEMIND_MESH_HEADSCALE_KEY_FILE=$ETC/headscale.key
ONEMIND_MESH_HUB_IP=${HUB_MESH_IP:-<the hub mesh address>}
ONEMIND_FABRIC_HUB_URL=https://$BOX.local
ONEMIND_FABRIC_NATS_ACCOUNTS_FILE=$STATE/nats/accounts.conf
ONEMIND_FABRIC_K3S=1
ONEMIND_FABRIC_K3S_CA_HASH=${K3S_CA_HASH:-<K10 + sha256 of the k3s CA>}
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
if [ "$ROLE" = hub ] || [ "$NODE_ROLE" = worker ]; then memory_cgroup_check; fi
apt_setup
if [ "$DRY_RUN" = 1 ]; then
  step "mDNS (avahi): NAME.local and <app>.NAME.local"
  plan "systemctl enable --now avahi-daemon"
else
  systemctl enable --now avahi-daemon >/dev/null 2>&1 || warn "avahi-daemon did not start: NAME.local names will not resolve"
fi
if [ "$ROLE" = hub ]; then
  k3s_binary
  LAN_ADDR=${LAN_ADDR:-$(primary_ip)}
  [ "$DRY_RUN" = 1 ] && LAN_ADDR=${LAN_ADDR:-"<this machine's address>"}
  [ -n "$LAN_ADDR" ] || die "could not find this machine's LAN address; pass --lan-addr"
  BOX=${BOX:-$(hostname | cut -d. -f1 | tr 'A-Z_' 'a-z-' | tr -cd 'a-z0-9-' | cut -c1-63 | sed 's/^-*//;s/-*$//')}
  [ -n "$BOX" ] || BOX=onemind
  onemindd_install
  gateway_user
  gateway_python
  box_certs              # CA + HTTPS + Headscale's control certificate
  tailscale_install
  headscale_install
  mesh_hub               # the hub joins its own mesh first: k3s and NATS use its mesh address
  box_certs              # + the NATS leaf listener certificate for that address
  k3s_server
  nats_install
  dashboard_build
  gateway_kubeconfig
  gateway_tokens
  # App pods reach the gateway over HTTPS on :8443 (box CA): with HTTPS on, the plain-HTTP port is
  # bound to loopback and the LAN never sees it (H-05).
  HUB_URL=${HUB:-"https://$LAN_ADDR:8443"}
  gateway_service "$HUB_URL"
  if [ "$DRY_RUN" = 1 ]; then
    step "Backups (restic, onemind-local storage class, backup agent)"
    plan "install restic $RESTIC_VERSION (pinned by sha256), apply the onemind-local storage class and the shared PostgreSQL manifests, create the job key and start the backup agent"
    step "Finish"
    plan "check that no new API token is on disk, then print it once (and the agent token with --with-agent-token)"
    plan "print how to join another machine: 'onemind fabric ticket', then install.sh --role node --join <code>"
    do_firewall_reminder
    exit 0
  fi
  backup_setup
  no_raw_tokens_on_disk
  banner
  log "hub ready: https://$BOX.local (and https://onemind.local), box CA sha256 $BOX_CA_SHA"
  log "mesh: hub $HUB_MESH_IP; k3s and the NATS leaf listener run on it"
  if [ -n "$OWNER_TOKEN" ]; then
    printf '\nOWNER TOKEN (shown once; only its sha256 is stored in %s):\n\n    %s\n\n' "$ETC/tokens.yaml" "$OWNER_TOKEN"
  fi
  if [ -n "$AGENT_TOKEN" ]; then
    printf 'AGENT TOKEN for an AI agent (dev-agent: may request actions, never approve; shown once):\n\n    %s\n\n' "$AGENT_TOKEN"
  fi
  if [ -n "$OWNER_TOKEN$AGENT_TOKEN" ]; then
    printf 'Save them in a password manager now. Lost? Remove %s and run this again.\n\n' "$ETC/tokens.yaml"
  fi
  printf 'Trust the box CA on your computer: download https://%s.local/v1/tls/ca.crt and check its sha256 is %s\n\n' "$BOX" "$BOX_CA_SHA"
  printf 'Join another machine: make a one-time code here (or Add a device on the dashboard), then approve:\n\n'
  printf '    ONEMIND_TOKEN=<owner token> onemind fabric ticket [--role leaf]\n\n'
  if [ -n "$BUNDLE" ]; then
    printf 'On that machine, from an offline bundle for its architecture (deploy/bundle.sh --arch ...):\n\n'
    printf "    sudo BUNDLE/src/deploy/install.sh --role node --join '<the code>' --bundle BUNDLE\n\n"
  fi
  printf 'Check this hub:  ONEMIND_TOKEN=<owner token> deploy/verify/verify.sh http://127.0.0.1:8080\n'
  printf 'Check a machine: sudo deploy/verify/node-check.sh   (services, k3s, NATS auth, own heartbeat)\n'
  printf 'Hermes agent (contract §7) model credentials, created by the owner at install time:\n\n'
  printf '    sudo k3s kubectl create namespace app-hermes-agent --dry-run=client -o yaml | sudo k3s kubectl apply -f -\n'
  printf '    read -rs KEY   # paste the key; it stays out of shell history and the process list\n'
  printf "    printf '<PROVIDER>_API_KEY=%%s\\\\n' \"\$KEY\" | sudo k3s kubectl -n app-hermes-agent create secret generic hermes-agent-credentials --from-env-file=/dev/stdin\n\n"
  do_firewall_reminder
else
  if [ "$NODE_ROLE" = worker ]; then k3s_binary; fi
  onemindd_install
  tailscale_install
  nats_leaf_install
  if [ "$DRY_RUN" = 1 ]; then
    step "Join (the owner approves this machine on the hub)"
    plan "onemind fabric join <the code> (waits for approval; then mesh, NATS leaf credentials and, for a worker, the k3s agent config)"
    [ "$NODE_ROLE" != worker ] || k3s_agent
    step "Finish"
    plan "print that the node joined as a $NODE_ROLE"
    do_firewall_reminder
    exit 0
  fi
  log "joining: the owner approves this machine on the hub (dashboard Approvals or onemind fabric approve)"
  # shellcheck disable=SC2086
  "$BIN/onemind" fabric join "$JOIN" ${HUB_ADDR:+--hub-addr "$HUB_ADDR"}
  [ "$NODE_ROLE" = worker ] && k3s_agent
  banner
  log "node joined as a $NODE_ROLE: mesh up, NATS leaf to the hub over the mesh"
  log "check it: sudo $SCRIPT_DIR/verify/node-check.sh"
  do_firewall_reminder
fi
