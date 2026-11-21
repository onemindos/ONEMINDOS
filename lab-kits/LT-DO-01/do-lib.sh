#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Shared helpers for the LT-DO-01 scripts. Source it; do not run it.
# The DigitalOcean token is read by doctl from DIGITALOCEAN_ACCESS_TOKEN. This kit never stores,
# prints or accepts a token as an argument: you type "export DIGITALOCEAN_ACCESS_TOKEN=..." yourself.
TAG=${ONEMIND_DO_TAG:-onemind-lt-do-01}
FW_NAME=${ONEMIND_DO_FW:-onemind-lt-do-01-fw}
export TAG FW_NAME

die() { echo "ERROR: $*" >&2; exit 1; }

# run: print the command; execute it unless DRY_RUN=1.
run() {
  echo "+ $*"
  [ "${DRY_RUN:-0}" = 1 ] || "$@"
}

need_token() {
  [ "${DRY_RUN:-0}" = 1 ] && return 0
  [ -n "${DIGITALOCEAN_ACCESS_TOKEN:-}" ] || die "set DIGITALOCEAN_ACCESS_TOKEN in your shell first (never put it in a file)"
}

need_doctl() {
  command -v doctl >/dev/null 2>&1 || die "doctl not found (brew install doctl)"
}
