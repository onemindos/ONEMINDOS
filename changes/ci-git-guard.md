---
pr: pending
branch: ci/git-guard
---
scripts/git-guard.sh refuses a commit when the shared git config sets core.worktree (which silently redirects every worktree to another agent's folder) or when git's top level is not where you stand, and prints the fix. A one-line pre-commit hook install is documented in docs/learning/mac-dev-loop.md, with a test.
