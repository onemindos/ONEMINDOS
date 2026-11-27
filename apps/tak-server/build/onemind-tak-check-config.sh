#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Refuse a CoreConfig.xml that opens anything but TAK's TLS inputs: an active input with protocol
# quic, tcp, udp or stcp, or any input or connector with tls="false". XML comments are ignored (upstream's
# example keeps its plain-text inputs commented out). Usage: onemind-tak-check-config.sh [CoreConfig.xml]
set -euo pipefail
f="${1:-/data/config/CoreConfig.xml}"
if perl -0777 -pe 's/<!--.*?-->//gs' "$f" \
  | grep -Eq '<input[^>]*protocol="(quic|tcp|udp|stcp)"|<(input|connector)[^>]*tls="false"'; then
  echo "onemind: $f has an active quic, tcp, udp or stcp input or tls=\"false\"; refusing to start" >&2
  exit 1
fi
