#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Stop a commit that would land in the wrong checkout. Run it before committing (see the hook one-liner in
# docs/learning/mac-dev-loop.md). Exit 1, with the fix printed, when:
#   1. the SHARED config (<common git dir>/config, which every worktree reads) sets core.worktree: it
#      redirects every worktree's files to one folder, so `git add` and `git commit` act on the wrong tree;
#   2. GIT_DIR or GIT_WORK_TREE is exported: git commands such as `git worktree` or `git config` run with
#      them can write the work tree into the shared config (the likely cause of both incidents);
#   3. the top level git reports is not the folder you are standing in (or above it).
# Why: another agent's `git worktree` or `git config core.worktree` once left that key set, and the next
# commit by a different agent staged the wrong files without any error.
set -u
if [ -n "${GIT_DIR:-}${GIT_WORK_TREE:-}" ]; then
  echo "git-guard: GIT_DIR or GIT_WORK_TREE is set in the environment (GIT_DIR=${GIT_DIR:-} GIT_WORK_TREE=${GIT_WORK_TREE:-})" >&2
  echo "  Use \`git -C <worktree> ...\` instead of exporting them, and run: unset GIT_DIR GIT_WORK_TREE" >&2
  exit 1
fi
common=$(git rev-parse --git-common-dir 2>/dev/null) || { echo "git-guard: not inside a git checkout" >&2; exit 1; }
common=$(cd "$common" && pwd -P)
bad=0
wt=$(git config --file "$common/config" --get core.worktree 2>/dev/null || true)
if [ -n "$wt" ]; then
  echo "git-guard: core.worktree is set in the shared config ($common/config) to: $wt" >&2
  echo "  It points every worktree at that folder. Remove it (it is never needed for a linked worktree):" >&2
  echo "    git config --file '$common/config' --unset core.worktree" >&2
  echo "  Then re-check: git rev-parse --show-toplevel. Never set it with plain 'git config' (use --worktree)." >&2
  bad=1
fi
here=$(pwd -P)
top=$(git rev-parse --show-toplevel 2>/dev/null || true)
top=$(cd "$top" 2>/dev/null && pwd -P || echo "$top")
case "$here/" in
  "$top"/*) ;;
  *)
    echo "git-guard: git thinks the top of this checkout is $top, but you are in $here" >&2
    echo "  Do not commit. Look for core.worktree (git config --show-origin --get core.worktree) and a stray GIT_WORK_TREE/GIT_DIR in the environment." >&2
    bad=1 ;;
esac
[ "$bad" -eq 0 ] || exit 1
