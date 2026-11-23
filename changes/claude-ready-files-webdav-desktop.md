---
pr: pending
branch: claude/ready-files-webdav-desktop
---
Open in Finder from the desktop app, part 3 of files-webdav (#722): the menu-bar menu and the box card now say Open in Finder on a Mac (Finder mounts the box's WebDAV folder, https://<box>/dav/, and asks for an app password), Open in Files on Linux (davs://<box>/dav/) and Open in Explorer on Windows, which stays on the SMB share because Microsoft deprecated its WebDAV client. The menu also shows the box's connection state (online, not reachable or checking). The mount address is built only from the paired box address, so nothing else can reach the AppleScript.
