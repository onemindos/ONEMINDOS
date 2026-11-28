#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# PK-1: one canonical host name answers on both access paths (LAN-side and mesh-side address), same certificate, same origin.
set -euo pipefail; T=PK-1; . /root/aklab/lib.sh
stamp "PK-1: one canonical name, two access paths"
run "grep -E '^(bindaddress|domain|origin)' /etc/kanidmd/server.toml; ss -ltn | grep 8443"
run "ip -br addr | grep -E 'v-ns|^lo'"
for ns in nsl nsm; do
  run "echo '== $ns resolves:'; ip netns exec $ns getent hosts idm.onemind.test; ip netns exec $ns curl -sS --cacert /etc/kanidm/ca.pem -o /dev/null -w 'status=%{http_code} server_addr=%{remote_ip} client_addr=%{local_ip} tls_verify=%{ssl_verify_result}\n' https://idm.onemind.test:8443/status; ip netns exec $ns curl -sS --cacert /etc/kanidm/ca.pem https://idm.onemind.test:8443/status; echo; ip netns exec $ns curl -sS --cacert /etc/kanidm/ca.pem -o /dev/null -w 'login page http=%{http_code}\\n' https://idm.onemind.test:8443/ui/login"
done
run "echo 'what kanidmd itself logged for those two requests (client address as seen by the server):'; timeout 20 journalctl -u kanidmd --no-pager -o cat | grep 'uri: /ui/login' | grep -oE 'uri: /ui/login|client_address: \"[0-9.]+\"' | paste - - | tail -2"
run "ip netns exec nsl ping -c1 -W2 198.51.100.1 || echo 'the LAN client has no route to the mesh address (paths are separate)'"
run "openssl x509 -in /etc/kanidmd/chain.pem -noout -ext subjectAltName | tail -1"
