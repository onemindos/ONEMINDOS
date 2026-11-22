---
pr: pending
branch: claude/mobile-files-write
---
Phone Files screen can now fetch a file to the phone and hand it to the system share sheet, and add a file from the phone into a folder the person may write (resumable tus upload with a sha-256 check), each shown only when the hub serves the route. Shows the box-wide backup badge when the backups route is served. Share links and per-file backup badges are not built because the hub has no such route yet.
