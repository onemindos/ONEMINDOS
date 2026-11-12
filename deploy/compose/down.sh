#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Stop the OneMind Mac hub. Pass -v to also delete the volumes (ledger, audit log, NATS data).
set -euo pipefail
cd "$(dirname "$0")"
docker compose down "$@"
