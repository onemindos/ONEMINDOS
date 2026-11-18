#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Runs inside a VM as `runner` (CI-10 and CI-13, issue 299): register as an EPHEMERAL runner, take exactly
# one job, then wipe the work folder. The registration token arrives on stdin (so it is not on the Mac's
# command line) and expires after an hour.
# Arguments: ORG_URL RUNNER_GROUP [INSTANCE, default 1] [LABEL, default onemind-local].
#   Worker VMs (one job per fresh clone): INSTANCE 1, LABEL onemind-local.
#   The gate VM (several runner processes side by side): INSTANCE gate-1, gate-2, ..., LABEL onemind-gate.
set -eu
url=$1 group=$2 n=${3:-1} label=${4:-onemind-local}
case $label in onemind-local|onemind-gate) ;; *) echo "unknown label: $label" >&2; exit 2 ;; esac
case $n in *[!a-z0-9-]*|'') echo "bad instance: $n" >&2; exit 2 ;; esac
IFS= read -r token
cd "$HOME/actions-runner-$n"
rm -rf _work _diag/* .runner .credentials .credentials_rsaparams 2>/dev/null || true
./config.sh --unattended --ephemeral --replace --url "$url" --token "$token" \
  --runnergroup "$group" --labels "$label" --name "$label-$(hostname)-$n" --work _work >/dev/null
unset token
rc=0
./run.sh || rc=$?     # returns after the one job (ephemeral)
rm -rf _work _diag/* .runner .credentials .credentials_rsaparams 2>/dev/null || true
exit $rc
