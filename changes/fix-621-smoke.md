---
pr: 621
branch: fix-621/smoke
---
The hub gateway starts on an image-built box again: it failed on first boot with 226/NAMESPACE because its ReadWritePaths= listed /data/onemind/files and the unit tried to make that folder in an ExecStartPre=+, which systemd never reaches when a read-write path is missing. onemind-firstboot now makes the folder (0750, owned by onemind, contents untouched) on every hub boot before it starts the gateway. Found by the image smoke test on the landing train (PR #621).
