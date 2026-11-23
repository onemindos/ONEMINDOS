---
pr: 969
branch: claude/ready-files-webdav-dav
---
WebDAV for Finder and Linux file managers, part 2 of files-webdav (#722): /dav/Home and /dav/Shared open a person's Files spaces with an app password (Finder Connect to Server https://onemind.local/dav/, GNOME Files davs://onemind.local/dav/; Windows stays on SMB). It answers only on the LAN and the mesh (anything else gets 404), refuses gateway tokens and guests, keeps every path inside its space (no symbolic link is followed), stops a revoked password on the next request, refuses writes in the read-only Cloud import folder, and sends deletes and overwrites to the Trash. Whole files stream to disk within the Files upload limit and quota, with its own rate limit and wrong-password back-off.
