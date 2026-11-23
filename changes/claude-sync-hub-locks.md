---
pr: pending
branch: claude/sync-hub-locks
---
Hub sync, part 2b (#699): advisory locks with a time limit, the shape WebDAV class 2 needs so macOS can mount a share read-write and office apps can mark a document as open. POST /v1/sync/locks takes a lock on a file or folder (a folder lock covers what is inside), refused with 423 when someone else's live lock covers the path; the holder refreshes or releases it, an owner may clear a stale one, and every lock expires on its own. Locks only warn: a sync commit over someone else's lock goes through and lists the lock, so the client can tell the person.
