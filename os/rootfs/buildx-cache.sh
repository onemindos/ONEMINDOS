#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Run one `docker buildx build` with a BuildKit layer cache. The cache only skips steps whose inputs are unchanged;
# what gets built is the same (the reproducible-build check, os/rootfs/repro-check.sh, still builds with --no-cache).
#   sh os/rootfs/buildx-cache.sh <scope> [--read-only] -- docker buildx build ... .
# The cache flags are appended to the command. Two caches, either or both:
#   - The GitHub Actions cache (type=gha,scope=<scope>), only when the job exposes the runtime token
#     (ACTIONS_RUNTIME_TOKEN plus ACTIONS_RESULTS_URL or ACTIONS_CACHE_URL; the workflows use
#     crazy-max/ghaction-github-runtime for that). A plain `run:` step does not have them, and buildx then drops a
#     type=gha cache without a word: that is why the image workflows' old inline cache flags never imported or
#     exported anything. It is written only when BUILDX_CACHE_WRITE=true (the workflows set it on pushes, the nightly
#     and manual runs): pull requests read the base branch's cache and write none, so they cannot push it out of the
#     repository's 10 GB cache.
#   - A local directory (type=local): BUILDX_CACHE=<dir> keeps <dir>/<scope> on a build machine, so builds there reuse
#     layers across worktrees, runs and `docker builder prune`. A build reads it, writes a fresh copy beside it and
#     swaps that in on success, so stale layers never pile up. Needs a builder that can export a cache (the
#     docker-container driver, or the docker driver with the containerd image store, as on the build machines).
# --read-only reads the caches and writes none. With neither cache set up, the command runs unchanged.
set -eu
[ $# -ge 3 ] || { echo "usage: buildx-cache.sh <scope> [--read-only] -- docker buildx build ..." >&2; exit 2; }
scope=$1; shift
case "$scope" in ''|*[!A-Za-z0-9._-]*) echo "buildx-cache.sh: bad scope '$scope'" >&2; exit 2 ;; esac
ro=0; [ "$1" = --read-only ] && { ro=1; shift; }
[ "$1" = -- ] || { echo "buildx-cache.sh: expected -- before the build command" >&2; exit 2; }
shift

if [ -n "${ACTIONS_RUNTIME_TOKEN:-}" ] && [ -n "${ACTIONS_RESULTS_URL:-}${ACTIONS_CACHE_URL:-}" ]; then
  set -- "$@" --cache-from "type=gha,scope=$scope"
  if [ "$ro" = 0 ] && [ "${BUILDX_CACHE_WRITE:-}" = true ]; then
    set -- "$@" --cache-to "type=gha,mode=max,scope=$scope"
  fi
  echo "buildx-cache: GitHub Actions cache, scope $scope ($( [ "$ro" = 0 ] && [ "${BUILDX_CACHE_WRITE:-}" = true ] && echo read+write || echo read only))" >&2
fi

dir=${BUILDX_CACHE:-}; new=""
if [ -n "$dir" ]; then
  mkdir -p "$dir"
  [ -f "$dir/$scope/index.json" ] && set -- "$@" --cache-from "type=local,src=$dir/$scope"
  if [ "$ro" = 0 ]; then
    new="$dir/.$scope.new.$$"
    set -- "$@" --cache-to "type=local,dest=$new,mode=max"
  fi
  echo "buildx-cache: local cache $dir/$scope ($( [ -f "$dir/$scope/index.json" ] && echo warm || echo cold))" >&2
fi

rc=0; "$@" || rc=$?
[ -n "$new" ] || exit "$rc"
if [ "$rc" != 0 ] || [ ! -f "$new/index.json" ]; then rm -rf "$new"; exit "$rc"; fi
# Swap the fresh copy in under a lock (two worktrees on one machine may finish the same scope together). The copy
# it replaces is kept for 6 hours: a build that started on it may still read its layers.
lock="$dir/.$scope.lock"; i=0
find "$dir" -maxdepth 1 -name ".$scope.lock" -mmin +10 -exec rmdir {} + 2>/dev/null || true   # left by a killed build
until mkdir "$lock" 2>/dev/null; do
  i=$((i + 1)); [ "$i" -le 60 ] || { echo "buildx-cache: $lock busy, keeping the old cache" >&2; rm -rf "$new"; exit 0; }
  sleep 1
done
old="$dir/.$scope.old.$$"
if [ -d "$dir/$scope" ]; then mv "$dir/$scope" "$old"; touch "$old"; fi
mv "$new" "$dir/$scope"
rmdir "$lock"
find "$dir" -maxdepth 1 -name ".*.old.*" -mmin +360 -exec rm -rf {} + 2>/dev/null || true
find "$dir" -maxdepth 1 -name ".*.new.*" -mmin +360 -exec rm -rf {} + 2>/dev/null || true
exit 0
