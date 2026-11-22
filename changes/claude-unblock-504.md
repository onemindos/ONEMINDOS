---
pr: 912
branch: claude/unblock-504
---
Rescue console Help (#504, FD-07, first part): the rescue console now serves the offline help pack read-only under /help/, behind its existing LAN and owner check, so the owner can read the recovery steps when k3s and the gateway are down. The pack is plain HTML with no JavaScript (help home, rescue console, emergency kit), ships in the image at /usr/share/onemind/help, and is served with a policy that forbids script, with no listing and no file outside the pack. A test keeps the shipped pack offline, script-free and free of broken links.
