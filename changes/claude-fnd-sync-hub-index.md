---
pr: 811
branch: claude/fnd-sync-hub-index
---
Hub sync contract, part 1 (#698): a file index in FILES (new tables files_index and files_index_roots, files schema v2) gives every file, folder and symlink an id that survives renames and moves inside a root, plus its parent, size, mtime, sha256 content hash and a monotonic revision per root. FILES writes record what they touched, and a scanner plus a Linux inotify watcher catch writes made over SMB or WebDAV (a rename seen on disk keeps its ids, matched by inode). GET /v1/sync/changes?root=&cursor= pages the per-root feed (each entry once at its latest state, deletions included, next_cursor and has_more); a cursor is bound to its root and caller (another one is 422) and one older than the pruned deletions is 410. /v1/events gains a bounded sync.root_changed wake-up (root and revision only, at most one per root per poll). Stat and list now carry id, revision and hash, and onemind sync changes prints the feed read-only.
