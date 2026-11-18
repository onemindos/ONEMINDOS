#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Runs inside the VM as `runner` (CI-10, issue 299): register as an EPHEMERAL runner, take exactly one
# job, then wipe the work folder. The registration token arrives on stdin (so it is not on the Mac's
# command line) and expires after an hour. Arguments: ORG_URL RUNNER_GROUP [INSTANCE, default 1].
set -eu
url=$1 group=$2 n=${3:-1}
IFS= read -r token
cd "$HOME/actions-runner-$n"
rm -rf _work _diag/* .runner .credentials .credentials_rsaparams 2>/dev/null || true
./config.sh --unattended --ephemeral --replace --url "$url" --token "$token" \
  --runnergroup "$group" --labels onemind-local --name "onemind-local-$(hostname)-$n" --work _work >/dev/null
unset token
rc=0
./run.sh || rc=$?     # returns after the one job (ephemeral)
rm -rf _work _diag/* .runner .credentials .credentials_rsaparams 2>/dev/null || true
exit $rc
