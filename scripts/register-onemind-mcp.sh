#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
set -eu

usage() {
    printf 'Usage: %s claude|codex CONTEXT\n' "${0##*/}" >&2
    exit 2
}

[ "$#" -eq 2 ] || usage
case "$1" in
    claude|codex) client=$1 ;;
    *) usage ;;
esac
context=$2
case "$context" in
    [!A-Za-z0-9]*|*[!A-Za-z0-9_.-]*|'') usage ;;
esac

for command in onemind "$client"; do
    command -v "$command" >/dev/null || {
        printf '%s must be on PATH.\n' "$command" >&2
        exit 1
    }
done

# Verify the saved agent credential before writing the client registration.
unset ONEMIND_TOKEN ONEMIND_HUB
onemind mcp doctor --context "$context"

case "$client" in
    claude) exec claude mcp add --scope user onemind -- onemind mcp --context "$context" ;;
    codex) exec codex mcp add onemind -- onemind mcp --context "$context" ;;
esac
