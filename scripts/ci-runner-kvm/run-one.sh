#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Runs inside a job VM as `runner` (CI-14), started by onemind-ci-job.service: run as an ephemeral
# just-in-time (JIT) runner for exactly one job, then stop. The host left one file, /run/onemind-ci/job,
# holding the encoded JIT config (one runner, labels self-hosted + onemind-kvm, group onemind-local,
# single use); it is deleted before the runner starts. The unit then powers the VM off.
set -eu
f=/run/onemind-ci/job
IFS= read -r ACTIONS_RUNNER_INPUT_JITCONFIG < "$f"
rm -f "$f"
export ACTIONS_RUNNER_INPUT_JITCONFIG
cd "$HOME/actions-runner"
exec ./run.sh
