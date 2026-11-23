---
pr: pending
branch: claude/ready-files-webdav
---
App passwords for WebDAV, part 1 of files-webdav (#722): the owner and adults can make, list and revoke per-device app passwords at /v1/files/app-passwords and in Settings, Account and security. Each one has scopes (My files and Shared, read only or read and write), is shown once, is kept only as a hash and is never logged. Guests, children, agents and gateway tokens never get one, and a revoked password fails on the very next check. The WebDAV door for Finder and Linux file managers that takes these passwords, LAN and mesh only, comes in the next PR on #722, then Open in Finder in the desktop app.
