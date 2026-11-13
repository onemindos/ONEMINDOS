---
pr: pending
branch: fix/apprestore-safefs
---
App restore no longer follows symlinks: `swapDir` and `swapFile` (and the rollback and commit steps of `backup.restore.finish`) now work through a parent-folder handle opened without following symlinks, using the same helpers as the rewind restore, so an app that swaps one of its own volume folders for a symlink cannot make the root-run restore write, rename or delete outside the volume. Directory restores are staged in a root-only folder first. Regression tests plant symlinks before the restore and swap them in while it runs.
