#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run from the repository root on a Linux Docker host with the pinned restic
# binary (ONEMIND_RESTIC). Only the initial image pull needs registry access.
set -euo pipefail

: "${ONEMIND_RESTIC:?set ONEMIND_RESTIC to the pinned restic binary}"
tmp="$(mktemp -d)"
network="onemind-copy-test-$(openssl rand -hex 8)"
container="$network"
cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || true
    docker network rm "$network" >/dev/null 2>&1 || true
    rm -rf "$tmp"
}
trap cleanup EXIT

umask 077
MINIO_ROOT_USER="$(openssl rand -hex 12)"
MINIO_ROOT_PASSWORD="$(openssl rand -hex 24)"
export MINIO_ROOT_USER MINIO_ROOT_PASSWORD
printf '%s\n' "$MINIO_ROOT_USER" > "$tmp/access"
printf '%s\n' "$MINIO_ROOT_PASSWORD" > "$tmp/secret"
docker network create --internal "$network" >/dev/null
docker run -d --name "$container" --network "$network"     -e MINIO_ROOT_USER -e MINIO_ROOT_PASSWORD     ghcr.io/coollabsio/minio@sha256:a4938f37f1be1841b8e7b627ad0207b265345fd0d063e42d7410c78af0e63e68 server /data >/dev/null
address="$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$container")"
export ONEMIND_COPY_S3_ENDPOINT="http://$address:9000"
export ONEMIND_COPY_S3_BUCKET="one-mind-copy"
export ONEMIND_COPY_S3_ACCESS_FILE="$tmp/access"
export ONEMIND_COPY_S3_SECRET_FILE="$tmp/secret"
curl -fsS --retry 25 --retry-connrefused --retry-delay 1 --max-time 2     "$ONEMIND_COPY_S3_ENDPOINT/minio/health/ready" >/dev/null
go test -tags integration -race -count=1 -run '^TestIntegrationSovereignCopies$' -v ./internal/backup
