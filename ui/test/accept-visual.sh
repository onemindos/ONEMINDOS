#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Accept the visual baseline a ui-quality run produced: download its visual-baseline-<browser>
# artifacts into ui/test/visual/<browser>/ (replacing what is there) and show what changed.
# Review the images, then commit them in a PR; reviewers see each changed PNG as an image diff.
#   ui/test/accept-visual.sh <run-id> [browser ...]     (needs gh, logged in with read access)
set -euo pipefail

run=${1:?usage: accept-visual.sh <run-id> [chromium firefox webkit]}
shift
browsers=("$@")
[ ${#browsers[@]} -gt 0 ] || browsers=(chromium firefox webkit)
repo=${GH_REPO:-onemindos/ONEMINDOS}
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

for b in "${browsers[@]}"; do
  case "$b" in chromium|firefox|webkit) ;; *) echo "unknown browser: $b" >&2; exit 2 ;; esac
  if ! gh run download "$run" -R "$repo" -n "visual-baseline-$b" -D "$tmp/$b"; then
    echo "run $run has no visual-baseline-$b artifact (that engine's baseline did not change)"
    continue
  fi
  # Only PNG snapshots are taken from the artifact.
  if find "$tmp/$b" -type f ! -name '*.png' | grep -q .; then
    echo "visual-baseline-$b contains files other than PNGs; refusing" >&2
    exit 1
  fi
  rm -rf "${here:?}/visual/$b"
  mkdir -p "$here/visual/$b"
  cp "$tmp/$b"/*.png "$here/visual/$b/"
  echo "accepted visual-baseline-$b from run $run"
done
git -C "$here" status --short -- visual
