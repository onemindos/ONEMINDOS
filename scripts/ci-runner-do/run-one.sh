#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Container entrypoint: run as an ephemeral just-in-time (JIT) runner for exactly one job, then exit.
# The one line on stdin is the encoded JIT config (one runner, labels self-hosted + onemind-do, group
# onemind-local, single use). It arrives on stdin, never in argv or the environment of a process list.
set -eu
IFS= read -r ACTIONS_RUNNER_INPUT_JITCONFIG
[ -n "$ACTIONS_RUNNER_INPUT_JITCONFIG" ] || { echo "no JIT config on stdin" >&2; exit 2; }
export ACTIONS_RUNNER_INPUT_JITCONFIG
cd "$HOME/actions-runner"
exec ./run.sh
