# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash disable=SC2034
# Shared by up, down, status and cycle (sourced). Nothing here stores a token: doctl and gh use the
# operator's own logins.
REPO=${REPO:-onemindos/ONEMINDOS}
ORG=${ORG:-${REPO%%/*}}
TAG=onemind-ci-do
FW=onemind-ci-do
HARD_MAX_DROPLETS=8
log() { echo "$(date '+%F %T') $*"; }
need() { command -v "$1" >/dev/null || { echo "install $1 first" >&2; exit 1; }; }
# Our droplets only: tagged AND named onemind-do-<n>. Prints "ID NAME IP", one per line.
droplets() {
  doctl compute droplet list --tag-name "$TAG" --format ID,Name,PublicIPv4 --no-header 2>/dev/null |
    awk '$2 ~ /^onemind-do-[0-9]+$/ {print $1, $2, $3}'
}
# price_hourly SIZE: USD per hour from DigitalOcean's own size list (never a hard-coded price)
price_hourly() { doctl compute size list --format Slug,PriceHourly --no-header | awk -v s="$1" '$1 == s {print $2}'; }
sshd() {   # sshd IP COMMAND...: key from the operator's agent; host keys learned on first contact into a per-run file
  local ip=$1; shift
  ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="${KNOWN_HOSTS:-/dev/null}" \
      -o ConnectTimeout=15 -o ServerAliveInterval=30 "root@$ip" "$@"
}
destroy_all() {   # destroy every droplet of ours and the firewall; never anything else
  local id name ip left fwid
  while read -r id name ip; do
    log "destroying $name ($id)"; doctl compute droplet delete --force "$id" >/dev/null || echo "WARNING: could not delete $name" >&2
  done < <(droplets)
  left=$(droplets | wc -l | tr -d ' ')
  fwid=$(doctl compute firewall list --format ID,Name --no-header 2>/dev/null | awk -v n="$FW" '$2 == n {print $1}')
  if [ -n "$fwid" ] && [ "$left" = 0 ]; then doctl compute firewall delete --force "$fwid" >/dev/null 2>&1 && log "firewall $FW removed"; fi
  [ "$left" = 0 ] || { echo "WARNING: $left droplet(s) still exist: run down again" >&2; return 1; }
}
