---
pr: 446
branch: claude/235-smb-shares-2
status_rows:
  - UMB-FILES-5 | in-progress | part 2: Samba in the image (off until a share is approved), host calls that write and check its config, per-person SMB passwords, a separate Time Machine folder, a lab kit; real Mac and Windows proof pending
---
Network shares, part 2 (FILES-SHARE-01, #235, D-017): the box side. Samba and its helper libraries ship in the image with the Debian units masked; a new onemind-smb unit starts only while an approved share has written its config, speaks SMB2 and newer only with no guests, and is limited in the kernel to LAN, mesh and loopback peers. The host service gets three calls (list shares, apply the whole list, set a password): it renders and checks the Samba config with testparm before anything live changes, keeps one locked account per person, and removes the config, accounts and passwords when the last share goes. The gateway now talks to it over its socket instead of the placeholder, makes the folders as its own user, and gives each person a generated SMB password shown once. Time Machine shares live outside the Files home. The File sharing screen shows how to connect and sets the password. A lab kit covers what only a real Mac and Windows PC can prove.
