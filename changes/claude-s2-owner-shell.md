---
pr: pending
branch: claude/s2-owner-shell
---
The owner shell on every OneMind image (Debian-bones step 2): openssh-server, sudo and libpam-systemd are in the base layer. SSH is public key only, for the user admin only, with host keys on the data partition; the cloud boards' copies of that policy and of the host key unit moved into the shared layer. On hardware sshd starts only once the owner has added a key (onemind-owner key-add), and the firewall opens tcp/22 to the LAN and the mesh only while sshd runs (a new empty chain that sshd fills, like Samba). The console login on tty2 and sudo use an admin password that onemind-owner password writes to the extrausers shadow file on the data partition, so no password is ever baked into the image; the Samba account writer now keeps that line. New first-boot check F15 (criteria pre-registered first) covers key login, refused password login, no sshd without a key, a tty2 style login and the kiosk session.
