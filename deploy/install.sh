#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# OneMind developer install (P6, contract sdk/contracts/poc-v0.md §6; brief 30 D-B2.4, REC-DEC-30).
# UNSUPPORTED DEVELOPER INSTALL, NO OS ROLLBACK: packages are upgraded in place on a stock OS.
#
#   sudo deploy/install.sh --role hub  [--hub http://<this-box>:8080] [--box-name NAME] [--lan-addr IP]
#   sudo deploy/install.sh --role node --join 'onemind-join:v1?…' [--hub-addr IP]
#   sudo deploy/install.sh --uninstall [--purge]
#
# Networking (docs/architecture/NETWORKING.md, CORE-NET-11): the hub runs the mesh coordinator
# (Headscale + embedded DERP), joins its own mesh first, then runs k3s and the NATS leaf listener on
# its mesh address and serves HTTPS with its own box CA. A node joins only through an owner-approved
# one-time code (`onemind fabric ticket` on the hub, or Add a device on the dashboard).
#
# Run it from a checkout of this repository (it builds onemindd, the gateway and the dashboard
# from that checkout). Re-running it is safe: every step checks what is already there.
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

ROLE="" HUB="" JOIN="" HUB_ADDR="" BOX="" LAN_ADDR="" UNINSTALL=0 PURGE=0 ONEMINDD_BIN="" DASH_DIST="" BIND="0.0.0.0" FORCE_OS=0
HS_PORT=8444   # Headscale's own TLS listener until onemind-edge fronts it on :443 (NETWORKING.md §4.2)

usage() {
  cat <<EOF
Usage:
  $0 --role hub  [--hub URL] [--box-name NAME] [--lan-addr IP] [--gateway-bind ADDR]
                 [--dashboard-dist DIR] [--onemindd-bin FILE]
  $0 --role node --join 'onemind-join:v1?…' [--hub-addr IP] [--onemindd-bin FILE]
  $0 --uninstall [--purge]

  --role hub|node        hub: mesh coordinator, k3s server, NATS, onemindd, gateway + dashboard.
                         node: mesh client, NATS leaf, onemindd, and the k3s agent for a worker.
  --hub URL              hub gateway URL that app pods use (default http://<lan addr>:8080).
  --box-name NAME        the box's name: https://NAME.local and <app>.NAME.local (default: hostname).
  --lan-addr IP          the hub's LAN IPv4 (default: the address of the default route).
  --join PAYLOAD         the join code text from `onemind fabric ticket` or the dashboard's QR (node).
  --hub-addr IP          the hub's LAN IPv4, when this LAN has no working mDNS for NAME.local (node).
  --gateway-bind ADDR    gateway listen address (default 0.0.0.0; 127.0.0.1 keeps it local,
                         but then app pods and other machines cannot reach it).
  --onemindd-bin FILE    use a prebuilt static onemindd (make -C cmd/onemindd build) instead of Go.
  --dashboard-dist DIR   use a prebuilt dashboard/dist instead of building it with Node.
  --force-os             continue on an OS this script was not written for.
  --uninstall            remove everything this script installed (k3s and its data included).
  --purge                with --uninstall: also delete $STATE (gateway database and audit log).
EOF
}

log()  { printf '==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

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
    --uninstall) UNINSTALL=1; shift ;;
    --purge) PURGE=1; shift ;;
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

[ "$(id -u)" -eq 0 ] || die "run as root (sudo)"
banner

# ------------------------------------------------------------------------------------------
# Uninstall
# ------------------------------------------------------------------------------------------
uninstall() {
  log "stopping and removing OneMind services"
  if command -v tailscale >/dev/null 2>&1; then tailscale logout >/dev/null 2>&1 || true; fi
  for u in onemind-gateway onemindd onemind-nats onemind-nats-leaf onemind-headscale onemind-nats-accounts.path tailscaled; do
    case "$u" in *.path) ;; *) u="$u.service" ;; esac
    systemctl disable --now "$u" 2>/dev/null || true
    rm -f "/etc/systemd/system/$u"
  done
  rm -rf /etc/systemd/system/onemind-nats-reload.service /etc/systemd/system/tailscaled.service.d \
    /etc/systemd/system/onemind-nats.service.d /etc/systemd/system/k3s.service.d /etc/systemd/system/k3s-agent.service.d
  systemctl daemon-reload
  rm -f "$BIN/onemindd" "$BIN/onemind" "$BIN/nats-server" "$BIN/headscale" /usr/bin/tailscale /usr/sbin/tailscaled /etc/default/tailscaled
  rm -rf /var/lib/tailscale /var/lib/private/onemind-headscale /var/lib/onemind-headscale /var/lib/onemind-nats-leaf
  hosts_block ""
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
  printf '%s' "$JOIN" | grep -Eqx 'onemind-join:v1[?][A-Za-z0-9%=&._:/-]{20,600}' || die "--join does not look like a OneMind join code"
  case "$JOIN" in *role=leaf*) NODE_ROLE=leaf ;; *) NODE_ROLE=worker ;; esac
fi
for a in "$HUB_ADDR" "$LAN_ADDR"; do
  [ -z "$a" ] || printf '%s' "$a" | grep -Eqx '([0-9]{1,3}[.]){3}[0-9]{1,3}' || die "addresses must be IPv4 (got: $a)"
done
if [ -n "$BOX" ]; then printf '%s' "$BOX" | grep -Eqx '[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?' || die "--box-name must be a lowercase DNS label"; fi
if [ -n "$HUB" ]; then
  printf '%s' "$HUB" | grep -Eqx 'https?://[][A-Za-z0-9.:-]+/?' \
    || die "--hub must look like http://HOST:8080 (got: $HUB)"
fi

ARCH=$(dpkg --print-architecture 2>/dev/null || true)
case "$ARCH" in amd64|arm64) ;; *) die "architecture '$ARCH' is not supported (amd64 or arm64 only)" ;; esac

# shellcheck disable=SC1091
. /etc/os-release
OS_DESC="${PRETTY_NAME:-unknown}"
OS_OK=0
case "${ID:-}" in
  debian|raspbian) [ "${VERSION_CODENAME:-}" = trixie ] && OS_OK=1 ;;   # Debian 13, Raspberry Pi OS trixie
  ubuntu) [ -f /etc/nv_tegra_release ] && OS_OK=1 ;;                     # Jetson Linux (L4T) Ubuntu
esac
if [ "$OS_OK" = 0 ]; then
  [ "$FORCE_OS" = 1 ] || die "$OS_DESC is not a target of this script (Debian 13, Raspberry Pi OS trixie, Jetson L4T Ubuntu). --force-os to try anyway"
  warn "continuing on $OS_DESC (--force-os)"
fi
log "platform: $OS_DESC, $ARCH, role $ROLE"

hub_host() { # host part of --hub (scheme, port and path removed)
  local h=${1#*://}; h=${h%%/*}
  case "$h" in \[*\]*) h=${h%%]*}; h=${h#[} ;; *) h=${h%%:*} ;; esac
  printf '%s' "$h"
}
primary_ip() { ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i=="src"){print $(i+1); exit}}'; }

pick() { eval "printf '%s' \"\${$1_$ARCH}\""; }   # pick K3S_SHA256 -> value for this arch

# fetch URL SHA256 DEST: download, check the hash, then move into place (never runs unchecked bytes).
fetch() {
  local url=$1 sum=$2 dest=$3 tmp
  if [ -f "$dest" ] && echo "$sum  $dest" | sha256sum -c --status; then return 0; fi
  tmp=$(mktemp "$CACHE/dl.XXXXXX")
  log "download $url"
  curl -fsSL --retry 3 --proto '=https' -o "$tmp" "$url"
  if ! echo "$sum  $tmp" | sha256sum -c --status; then
    rm -f "$tmp"; die "sha256 mismatch for $url (expected $sum)"
  fi
  mv "$tmp" "$dest"
}

install -d -m0755 "$PREFIX" "$TOOLS" "$CACHE"
# 0755: services read their own files here (NATS as a dynamic user, the gateway as "onemind");
# each secret file below is 0600/0640 on its own.
install -d -m0755 "$ETC"

# ------------------------------------------------------------------------------------------
# 1. OS packages + automatic security updates (contract §10.1, developer installs)
# ------------------------------------------------------------------------------------------
apt_setup() {
  # avahi + libnss-mdns: NAME.local and <app>.NAME.local (NETWORKING.md §9.1); sqlite3: Headscale backups.
  local pkgs="ca-certificates curl tar gzip iproute2 unattended-upgrades needrestart apt-listchanges avahi-daemon avahi-utils libnss-mdns sqlite3"
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
  if [ "${ID:-}" = ubuntu ]; then
    cat > /etc/apt/apt.conf.d/52onemind-security-only <<'EOF'
// OneMind developer install (deploy/install.sh): automatic updates from security origins only.
#clear Unattended-Upgrade::Allowed-Origins;
#clear Unattended-Upgrade::Origins-Pattern;
Unattended-Upgrade::Allowed-Origins { "${distro_id}:${distro_codename}-security"; };
EOF
  else
    cat > /etc/apt/apt.conf.d/52onemind-security-only <<'EOF'
// OneMind developer install (deploy/install.sh): automatic updates from security origins only.
#clear Unattended-Upgrade::Allowed-Origins;
#clear Unattended-Upgrade::Origins-Pattern;
Unattended-Upgrade::Origins-Pattern {
  "origin=Debian,codename=${distro_codename}-security,label=Debian-Security";
  "origin=Debian,codename=${distro_codename},label=Debian-Security";
};
EOF
  fi
  # needrestart: restart services that still use replaced libraries, without asking.
  install -d -m0755 /etc/needrestart/conf.d
  cat > /etc/needrestart/conf.d/50-onemind.conf <<'EOF'
# OneMind developer install: restart affected services automatically.
$nrconf{restart} = 'a';
EOF
  systemctl enable --now apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true
}

# ------------------------------------------------------------------------------------------
# 2. k3s (server on the hub, agent on a node)
# ------------------------------------------------------------------------------------------
k3s_binary() {
  local name=k3s; [ "$ARCH" = arm64 ] && name=k3s-arm64
  fetch "$K3S_URL_BASE/$name" "$(pick K3S_SHA256)" "$CACHE/k3s-$K3S_VERSION-$ARCH"
  if ! cmp -s "$CACHE/k3s-$K3S_VERSION-$ARCH" "$BIN/k3s" 2>/dev/null; then
    [ -e "$BIN/k3s" ] && ! systemctl list-unit-files k3s.service k3s-agent.service 2>/dev/null | grep -q k3s \
      && die "$BIN/k3s exists but was not installed by this script; remove it first"
    install -m0755 "$CACHE/k3s-$K3S_VERSION-$ARCH" "$BIN/k3s"
    K3S_CHANGED=1
  fi
  fetch "https://raw.githubusercontent.com/k3s-io/k3s/$K3S_INSTALL_COMMIT/install.sh" \
    "$K3S_INSTALL_SHA256" "$CACHE/k3s-install-$K3S_INSTALL_COMMIT.sh"
}

memory_cgroup_check() {
  grep -qw memory /sys/fs/cgroup/cgroup.controllers 2>/dev/null && return 0
  local cmdline=/boot/firmware/cmdline.txt
  if [ -f "$cmdline" ]; then   # Raspberry Pi: k3s needs the memory cgroup (docs.k3s.io, Raspberry Pi)
    grep -q 'cgroup_enable=memory' "$cmdline" || sed -i '1 s/$/ cgroup_memory=1 cgroup_enable=memory/' "$cmdline"
    die "the memory cgroup is off; $cmdline was updated. Reboot, then run this script again."
  fi
  die "the memory cgroup is not available; k3s cannot run"
}

k3s_server() {
  local cfg=/etc/rancher/k3s/config.yaml agent_token new_cfg
  install -d -m0700 /etc/rancher/k3s
  # A separate agent token: nodes can join as agents but can never join as servers (D-B6.2).
  if [ -f "$ETC/k3s-agent-token" ]; then agent_token=$(cat "$ETC/k3s-agent-token")
  else agent_token=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n'); (umask 077; printf '%s' "$agent_token" > "$ETC/k3s-agent-token"); fi
  # A cluster made before the mesh (flannel VXLAN on the LAN) cannot be switched in place (NETWORKING.md §8).
  if [ -d /var/lib/rancher/k3s/server/db ] && ! grep -q '^flannel-backend: "wireguard-native"' "$cfg" 2>/dev/null; then
    die "this hub's k3s cluster predates the mesh; back it up, run --uninstall, then install again"
  fi
  # k3s over the mesh: node IP and API on the hub's mesh address, pod traffic in WireGuard (H-17).
  # Traefik and ServiceLB are off: the gateway owns :443/:80 and reaches apps on their ClusterIPs
  # (proxy.py); ServiceLB would otherwise DNAT LAN traffic for 80/443 to Traefik.
  new_cfg=$(printf '# Written by deploy/install.sh (NETWORKING.md §8)\nwrite-kubeconfig-mode: "0600"\nagent-token: "%s"\nnode-ip: "%s"\nadvertise-address: "%s"\ntls-san: ["hub.onemind.internal", "%s"]\nflannel-backend: "wireguard-native"\nflannel-iface: "tailscale0"\ndisable: ["traefik", "servicelb"]\n' \
    "$agent_token" "$HUB_MESH_IP" "$HUB_MESH_IP" "$HUB_MESH_IP")
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
  if ! "$BIN/nats-server" --version 2>/dev/null | grep -q "${NATS_VERSION#v}"; then
    tar -xzf "$CACHE/$tgz" -C "$CACHE" "nats-server-$NATS_VERSION-linux-$ARCH/nats-server"
    install -m0755 "$CACHE/nats-server-$NATS_VERSION-linux-$ARCH/nats-server" "$BIN/nats-server"
    rm -rf "$CACHE/nats-server-$NATS_VERSION-linux-$ARCH"
  fi
}

nats_install() {
  nats_binary
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
  nats_binary
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
  fetch "https://pkgs.tailscale.com/stable/$tgz" "$(pick TAILSCALE_SHA256)" "$CACHE/$tgz"
  if ! /usr/sbin/tailscaled --version 2>/dev/null | head -1 | grep -qxF "$TAILSCALE_VERSION"; then
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
  fetch "https://github.com/juanfont/headscale/releases/download/v$HEADSCALE_VERSION/$f" "$(pick HEADSCALE_SHA256)" "$CACHE/$f"
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
  [ -x "$GO_DIR/bin/go" ] && return 0
  fetch "https://go.dev/dl/go$GO_VERSION.linux-$ARCH.tar.gz" "$(pick GO_SHA256)" "$CACHE/go$GO_VERSION.tgz"
  rm -rf "$GO_DIR.tmp"; mkdir -p "$GO_DIR.tmp"
  tar -xzf "$CACHE/go$GO_VERSION.tgz" -C "$GO_DIR.tmp" --strip-components=1
  mv "$GO_DIR.tmp" "$GO_DIR"
}

node_toolchain() {
  local na=x64; [ "$ARCH" = arm64 ] && na=arm64
  NODE_DIR=$TOOLS/node-$NODE_VERSION
  [ -x "$NODE_DIR/bin/node" ] && return 0
  fetch "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-$na.tar.gz" "$(pick NODE_SHA256)" "$CACHE/node-$NODE_VERSION.tgz"
  rm -rf "$NODE_DIR.tmp"; mkdir -p "$NODE_DIR.tmp"
  tar -xzf "$CACHE/node-$NODE_VERSION.tgz" -C "$NODE_DIR.tmp" --strip-components=1
  mv "$NODE_DIR.tmp" "$NODE_DIR"
}

uv_toolchain() {
  local ua=x86_64; [ "$ARCH" = arm64 ] && ua=aarch64
  UV=$TOOLS/uv-$UV_VERSION/uv
  [ -x "$UV" ] && return 0
  fetch "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$ua-unknown-linux-gnu.tar.gz" "$(pick UV_SHA256)" "$CACHE/uv-$UV_VERSION.tgz"
  mkdir -p "$TOOLS/uv-$UV_VERSION"
  tar -xzf "$CACHE/uv-$UV_VERSION.tgz" -C "$TOOLS/uv-$UV_VERSION" --strip-components=1
}

# ------------------------------------------------------------------------------------------
# 5. onemindd (+ the onemind CLI) as a systemd service, on every machine
# ------------------------------------------------------------------------------------------
onemindd_install() {
  local out="$CACHE/build" nats_url
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
  nats_url=nats://127.0.0.1:4222   # hub: its NATS; node: its local leaf (NETWORKING.md §7)
  printf '# Written by deploy/install.sh (contract §1)\nONEMIND_NATS_URL=%s\nONEMIND_NODE_ROLE=%s\n' "$nats_url" "$ROLE" > "$ETC/onemindd.env.new"
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
  id onemind >/dev/null 2>&1 || useradd --system --home-dir "$STATE" --shell /usr/sbin/nologin onemind
  # 0751: the hub NATS reads nats/accounts.conf inside; nothing in it can be listed or read by others.
  install -d -m0751 -o onemind -g onemind "$STATE"
}

gateway_python() {
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

# Owner token: 256 random bits, printed once, stored only as its sha256 (core/onemind_core/auth.py).
OWNER_TOKEN=""
gateway_tokens() {
  local f="$ETC/tokens.yaml"
  if [ -f "$f" ]; then log "tokens: $f exists, owner token kept (it was printed at the first install)"; return 0; fi
  OWNER_TOKEN=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
  local h; h=$(printf '%s' "$OWNER_TOKEN" | sha256sum | cut -d' ' -f1)
  (umask 027
   cat > "$f" <<EOF
# OneMind gateway principals (contract §3; v0 static tokens, Kanidm later: BD-03).
# Keys are "sha256:<hex of token>", so this file holds no usable secret.
# Add a principal: printf %s "\$TOKEN" | sha256sum  ->  "sha256:<hex>": {id: ..., kind: ..., role: ...}
tokens:
  "sha256:$h": {id: owner, kind: person, role: owner}
EOF
  )
  chgrp onemind "$f"
}

gateway_service() {
  local url=$1
  cat > "$ETC/gateway.env" <<EOF
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
ONEMIND_PUBLIC_URL=$url
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
ONEMIND_MESH_HUB_IP=$HUB_MESH_IP
ONEMIND_FABRIC_HUB_URL=https://$BOX.local
ONEMIND_FABRIC_NATS_ACCOUNTS_FILE=$STATE/nats/accounts.conf
ONEMIND_FABRIC_K3S=1
ONEMIND_FABRIC_K3S_CA_HASH=$K3S_CA_HASH
EOF
  chmod 0640 "$ETC/gateway.env"; chgrp onemind "$ETC/gateway.env"
  # kubectl for the gateway: the k3s multi-call binary run as "kubectl" (same version as the
  # cluster). A wrapper, not a symlink, so it never falls back to the root-only k3s.yaml.
  install -d -m0755 "$PREFIX/bin"
  printf '#!/bin/sh\n# kubectl from k3s for the OneMind gateway (deploy/install.sh)\nexec %s kubectl "$@"\n' "$BIN/k3s" > "$PREFIX/bin/kubectl"
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
apt_setup
systemctl enable --now avahi-daemon >/dev/null 2>&1 || warn "avahi-daemon did not start: NAME.local names will not resolve"
if [ "$ROLE" = hub ]; then
  memory_cgroup_check
  k3s_binary
  LAN_ADDR=${LAN_ADDR:-$(primary_ip)}
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
  HUB_URL=${HUB:-"http://$LAN_ADDR:8080"}
  gateway_service "$HUB_URL"
  banner
  log "hub ready: https://$BOX.local (and https://onemind.local), box CA sha256 $BOX_CA_SHA"
  log "mesh: hub $HUB_MESH_IP; k3s and the NATS leaf listener run on it"
  if [ -n "$OWNER_TOKEN" ]; then
    printf '\nOWNER TOKEN (shown once; only its sha256 is stored in %s):\n\n    %s\n\n' "$ETC/tokens.yaml" "$OWNER_TOKEN"
  fi
  printf 'Trust the box CA on your computer: download https://%s.local/v1/tls/ca.crt and check its sha256 is %s\n\n' "$BOX" "$BOX_CA_SHA"
  printf 'Join another machine: make a one-time code here (or Add a device on the dashboard), then approve:\n\n'
  printf '    ONEMIND_TOKEN=<owner token> onemind fabric ticket [--role leaf]\n\n'
  printf 'Check this hub:  ONEMIND_TOKEN=<owner token> deploy/verify/verify.sh http://127.0.0.1:8080\n'
  printf 'Hermes agent (contract §7) model credentials, created by the owner at install time:\n\n'
  printf '    sudo k3s kubectl create namespace app-hermes-agent --dry-run=client -o yaml | sudo k3s kubectl apply -f -\n'
  printf '    read -rs KEY   # paste the key; it stays out of shell history and the process list\n'
  printf "    printf '<PROVIDER>_API_KEY=%%s\\\\n' \"\$KEY\" | sudo k3s kubectl -n app-hermes-agent create secret generic hermes-agent-credentials --from-env-file=/dev/stdin\n\n"
else
  if [ "$NODE_ROLE" = worker ]; then memory_cgroup_check; k3s_binary; fi
  onemindd_install
  tailscale_install
  nats_leaf_install
  log "joining: the owner approves this machine on the hub (dashboard Approvals or onemind fabric approve)"
  # shellcheck disable=SC2086
  "$BIN/onemind" fabric join "$JOIN" ${HUB_ADDR:+--hub-addr "$HUB_ADDR"}
  [ "$NODE_ROLE" = worker ] && k3s_agent
  banner
  log "node joined as a $NODE_ROLE: mesh up, NATS leaf to the hub over the mesh"
fi
