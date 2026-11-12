#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copy one run's evidence into the repo folder, masked and trimmed.
# Masks: pre-auth key prefixes, node/machine/disco public keys, link-local IPv6, the lab
# CA/cert fingerprints, any host path or user name, and generated NATS passwords.
set -euo pipefail; SRC=${1:?run dir}; mkdir -p "${2:?dest dir}"; DST=$(cd "$2" && pwd)
m(){ sed -E \
  -e 's/hskey-auth-[A-Za-z0-9_-]+(\*\*\*)?/hskey-auth-<masked>/g' \
  -e 's/(nodekey|mkey|discokey|privkey|nlpub):[0-9a-f]{6,}(…|\.\.\.)?/\1:<masked>/g' \
  -e 's/\[[A-Za-z0-9+\/]{5}\]/[<k>]/g' \
  -e 's/fe80::[0-9a-f:]+/fe80::<ll>/g' \
  -e 's/SHA-256: [0-9a-f]{64}/SHA-256: <lab-cert>/g' \
  -e 's#/Users/[^ "'"'"']+#<host-path>#g' -e 's/[a-z]+\.guest/<user>/g' \
  -e 's/(password: )"[0-9a-f]{32}"/\1"<generated>"/g' -e 's/:[0-9a-f]{32}@/:<generated>@/g' ; }
trim(){ # keep the lines that carry evidence; cap length
  grep -E "$2" "$1" | m | head -n "${3:-300}"; }
cd "$SRC"
for f in run.log results.json nodes.json preauthkeys-redacted.json policy.hujson derp.yaml hub.conf.masked; do [ -f $f ] && m < $f > "$DST/$f"; done
mkdir -p "$DST/mesh" "$DST/nats" "$DST/t5" "$DST/e2" "$DST/res"
for f in mesh/*; do m < $f | head -n 400 > "$DST/mesh/$(basename $f)"; done
for f in nats-t/*; do case $f in *hub-dump.tsv) cp $f "$DST/nats/";; *.conf) m < $f > "$DST/nats/$(basename $f)";; *) m < $f | head -n 600 > "$DST/nats/$(basename $f)";; esac; done
cp t5/* "$DST/t5/"; for f in e2/*; do m < $f > "$DST/e2/$(basename $f)"; done; cp res/* "$DST/res/"
mkdir -p "$DST/logs"
trim cloud-headscale.log "INF|WRN|ERR" 200 > "$DST/logs/headscale-trimmed.log"
trim cloud-derper.log "." 120 > "$DST/logs/derper-trimmed.log"
trim cloud-natshub.log "Leafnode|JetStream|TLS|ERR|WRN|Listening|reload|Server is ready|version" 300 > "$DST/logs/nats-hub-trimmed.log"
for n in home-a home-b; do
  trim $n-natsleaf.log "Leafnode|JetStream|ERR|WRN|Listening|version|domain" 200 > "$DST/logs/nats-leaf-$n-trimmed.log"
  trim $n-tailscaled.log "magicsock|derp|DERP|netcheck|endpoints|control:|LinkChange|Switching|wgengine: Reconfig|disco|health" 400 > "$DST/logs/tailscaled-$n-trimmed.log"; done
trim cloud-tailscaled.log "magicsock|derp|DERP|control:|health" 200 > "$DST/logs/tailscaled-hub-trimmed.log"
# a masked copy must not leak: fail if any obvious pattern survives
if grep -rqE "/Users/|[0-9a-f]{32}@|hskey-auth-[A-Za-z0-9]{6}|nodekey:[0-9a-f]{8}" "$DST"; then echo "MASK CHECK FAILED"; grep -rlE "/Users/|[0-9a-f]{32}@|hskey-auth-[A-Za-z0-9]{6}|nodekey:[0-9a-f]{8}" "$DST"; exit 1; fi
echo "masked copy ok: $(find "$DST" -type f | wc -l) files, $(du -sh "$DST" | cut -f1)"
