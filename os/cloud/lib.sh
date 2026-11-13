# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=sh
# Shared helpers of the os/cloud import scripts (sourced, not run).
need() { for c in "$@"; do command -v "$c" >/dev/null || { echo "missing command: $c" >&2; exit 2; }; done; }
# Check a file against the SHA256SUMS that sits next to it (CI artifact or `make cloud-image`).
verify() {
  d=$(dirname "$1"); n=$(basename "$1")
  if [ -f "$d/SHA256SUMS" ] && grep -q "  $n\$" "$d/SHA256SUMS"; then
    ( cd "$d" && grep "  $n\$" SHA256SUMS | sha256sum -c - ) || { echo "sha256 mismatch: $1" >&2; exit 1; }
  else
    echo "WARNING: no SHA256SUMS entry for $n next to it; not verified" >&2
  fi
}
# file.ext.xz -> file.ext (kept next to it), after checking the .xz.
unxz_keep() {
  case "$1" in
    *.xz) verify "$1"; out=${1%.xz}; [ -f "$out" ] || xz -dkT0 "$1"; echo "$out" ;;
    *) echo "$1" ;;
  esac
}
# 0.1.0-dev.42 -> 0-1-0-dev-42 (image names on GCE and elsewhere allow [a-z0-9-] only)
slug() { echo "$1" | tr 'A-Z._+' 'a-z---'; }
