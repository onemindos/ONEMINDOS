#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Point apt at a pinned, dated archive (brief 30 §2 rule 2).
#   configure-apt.sh debian <SNAPSHOT>   -> snapshot.debian.org/<SNAPSHOT> for trixie, -updates, -security
#   configure-apt.sh ubuntu none         -> the live Ubuntu archive (gap: handbook/findings.md F-03)
# deb822 fields: sources.list(5) (Check-Valid-Until, Signed-By); snapshot URL scheme:
# https://snapshot.debian.org/ ("/archive/<archive>/<YYYYMMDDTHHMMSSZ>/").
set -eu
LEG=$1; SNAP=$2
cat > /etc/apt/apt.conf.d/90onemind <<'CONF'
APT::Install-Recommends "false";
APT::Install-Suggests "false";
Acquire::Retries "8";
Acquire::http::Timeout "120";
CONF
case "$LEG" in
debian)
  [ "$SNAP" != none ] || { echo "debian leg needs a snapshot timestamp" >&2; exit 1; }
  rm -f /etc/apt/sources.list /etc/apt/sources.list.d/*
  cat > /etc/apt/sources.list.d/onemind-snapshot.sources <<SRC
Types: deb
URIs: http://snapshot.debian.org/archive/debian/$SNAP
Suites: trixie trixie-updates
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
Check-Valid-Until: no

Types: deb
URIs: http://snapshot.debian.org/archive/debian-security/$SNAP
Suites: trixie-security
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
Check-Valid-Until: no
SRC
  ;;
ubuntu) : ;;   # keep the image's own ubuntu.sources (live archive)
*) echo "unknown leg $LEG" >&2; exit 1 ;;
esac
echo "apt configured for leg=$LEG snapshot=$SNAP"
