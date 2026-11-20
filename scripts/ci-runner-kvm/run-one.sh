#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Runs inside a job VM as `runner` (CI-14), started by onemind-ci-job.service: register as an EPHEMERAL
# runner, take exactly one job, then stop. The host left one file, /run/onemind-ci/job, holding
# "ORG_URL GROUP NAME" on line 1 and a one-hour registration token on line 2; it is deleted before
# the job starts, so the job never sees the token.
set -eu
f=/run/onemind-ci/job
{ read -r url group name; IFS= read -r token; } < "$f"
rm -f "$f"
cd "$HOME/actions-runner"
./config.sh --unattended --ephemeral --replace --url "$url" --token "$token" \
  --runnergroup "$group" --labels onemind-kvm --name "$name" --work _work >/dev/null
unset token
exec ./run.sh     # returns after the one job (ephemeral); the unit then powers the VM off
