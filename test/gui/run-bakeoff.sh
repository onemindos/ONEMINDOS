#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Lab-box kit for the GUI runtime bake-off (issue #786). Run from the repo root on a Linux box with docker and
# Python Playwright:  test/gui/run-bakeoff.sh "daily-use hub" [OUT.json]
# Builds the desktop base and the Obsidian test image locally (nothing is pushed), starts the desktop as uid 1000
# with every capability dropped, ports on 127.0.0.1 only, runs test/gui/bakeoff.py, then removes the container.
set -eu
label=${1:?usage: run-bakeoff.sh HOST_LABEL [OUT.json]}
out=${2:-bakeoff-neko.json}
name=onemind-bakeoff-$$
work=$(mktemp -d)
BAKEOFF_PASSWORD=$(od -An -N12 -tx1 /dev/urandom | tr -d ' \n')
export BAKEOFF_PASSWORD
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; rm -rf "$work"; }
trap cleanup EXIT INT TERM

python3 -I sdk/tools/app-factory base-build desktop --out "$work/base" --tag local
docker build -t onemind-bakeoff/obsidian:local --build-arg DESKTOP_BASE=ghcr.io/onemindos/bases/desktop:local test/gui/obsidian
docker run -d --name "$name" --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges --shm-size 1g \
  -p 127.0.0.1:8080:8080 -p 127.0.0.1:52000:52000/udp \
  -e NEKO_DESKTOP_SCREEN=1280x720@30 -e NEKO_MEMBER_PROVIDER=multiuser \
  -e NEKO_MEMBER_MULTIUSER_ADMIN_PASSWORD="$BAKEOFF_PASSWORD" -e NEKO_MEMBER_MULTIUSER_USER_PASSWORD="$BAKEOFF_PASSWORD" \
  -e NEKO_SESSION_IMPLICIT_HOSTING=true -e NEKO_WEBRTC_UDPMUX=52000 -e NEKO_WEBRTC_NAT1TO1=127.0.0.1 -e NEKO_WEBRTC_ICELITE=true \
  onemind-bakeoff/obsidian:local >/dev/null
i=0; until curl -fsS http://127.0.0.1:8080/health >/dev/null 2>&1; do i=$((i+1)); [ $i -lt 90 ] || { docker logs "$name" | tail -40; exit 1; }; sleep 2; done
python3 -I test/gui/bakeoff.py run --runtime neko --url http://127.0.0.1:8080 --container "$name" --host-label "$label" --out "$out"
