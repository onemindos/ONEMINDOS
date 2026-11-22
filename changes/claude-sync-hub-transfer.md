---
pr: pending
branch: claude/sync-hub-transfer
---
Hub sync, part 2a (#699): a sync client can now send a file in content-defined chunks and resume an interrupted upload by sending only the chunks the hub lacks (POST /v1/sync/chunks/missing, PUT /v1/sync/chunks/{hash}, which refuses bytes that do not match the hash). POST /v1/sync/commit makes the file from its chunk list only when it is still at the client's base revision (base_revision or If-Match); otherwise it answers 412 with the current revision, so the second of two devices editing a file never overwrites the first. Commits check write access and the quota. The last versions of each file are kept as chunk lists that share chunks, a file changed over SMB or the Files app is kept as a version before a commit replaces it, and GET /v1/sync/versions lists them. Chunks are stored per root, so asking about chunks reveals nothing about another person's files.
