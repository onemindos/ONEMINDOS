<!-- SPDX-License-Identifier: Apache-2.0 -->
# LT-SMB-01 · File sharing: a Mac and a Windows PC open a member's share

**Status:** kit-ready (needs a running OneMind box built with FILES-SHARE-01 part 2, and a Mac and a Windows PC) · **Serves:** #235 "Done when" (a Mac and a Windows PC can open a member's share and see only that member's files; default-deny egress kept), D-017 · **Design:** [docs/leap/core/FILE-SHARING.md](../../docs/leap/core/FILE-SHARING.md)

> **Explain it like I'm the founder.** The tests in the repo prove that the gateway files the request, that the host service writes a correct Samba config, and that the image carries Samba switched off. They cannot prove that a real Mac and a real Windows PC like the result. This kit does that: about 40 minutes, a box you can reach, two household members, and one Mac and one Windows PC on the same network. Nothing here touches the internet.

## Before you start
- A OneMind box running an image or a `deploy/` install that includes this change, with at least two household members (call them Alex and Bo here; use the real account names).
- Sign in to the dashboard as the owner. File sharing is the **File sharing** screen (Launchpad). If it says "not available yet", read the reason: Samba or the host service is missing, and the rest of this kit cannot start.

## A. Turn it on (owner, in the dashboard)
1. File sharing, **Ask to share Alex's files**, then **Ask to share Bo's files**. Open each request in **Approvals** and approve it (this is the owner's approval; nothing is shared before it).
2. File sharing, **Ask for a Time Machine share for Alex** (500 GB). Approve it.
3. Each member signs in to the dashboard themselves, opens File sharing and presses **Set a new SMB password for me**. Write the password down: it is shown once.
4. **Check:** on the box, `systemctl is-active onemind-smb` says `active`, and `systemctl is-enabled smbd nmbd winbind` says `masked` for all three.

## B. Script check from a Linux machine on the same network (5 min)
```bash
BOX=<the box's address> USER_A=alex PASS_A=<Alex's SMB password> USER_B=bo PASS_B=<Bo's SMB password> sh lab-kits/LT-SMB-01/smb-check.sh
```
Expected: six `PASS` lines (Alex sees and writes their share; Bo is refused Alex's share; a wrong password, anonymous and SMB1 are refused).

## C. Mac (10 min)
1. Finder, Go, Connect to Server, `smb://<the box's address>/alex`. Sign in as Alex with the SMB password. **Expect:** exactly Alex's files, nothing of Bo's, nothing of the Shared folder.
2. Copy a file in; in the dashboard Files screen, signed in as Alex, **it appears in My files**.
3. Try `smb://<the box's address>/bo` signed in as Alex. **Expect:** refused.
4. System Settings, General, Time Machine, Add Backup Disk. **Expect:** `alex-timemachine` is listed (it is announced by mDNS). Pick it, sign in as Alex, let the first backup run for a few minutes. **Expect:** it starts and its folder is not inside Alex's My files in the dashboard.

## D. Windows (10 min)
1. File Explorer, This PC, Map network drive, folder `\\<the box's address>\alex`, "Connect using different credentials", sign in as Alex. **Expect:** exactly Alex's files.
2. Open `\\<the box's address>\bo`. **Expect:** refused.
3. In an administrator PowerShell, `Get-SmbConnection` shows dialect 3.x (never 1.x or 2.0).

## E. Off and egress (5 min, on the box)
1. In the dashboard, **Stop sharing** every share (it asks twice). **Expect:** `systemctl is-active onemind-smb` says `inactive` within seconds, `ss -ltn 'sport = :445'` prints no listener, and `/data/onemind/samba/smb.conf` no longer exists.
2. With a share on again, from a machine **outside** the LAN and mesh (for example a phone on mobile data, no mesh), `nc -vz <the box's public address if it has one> 445`. **Expect:** no connection. (If the box has no public address, skip it: the unit's `IPAddressDeny=any` and the smb.conf `hosts allow` list are the rule, and they are checked in `test/unit/test_smb_image.py` and `internal/smb`.)
3. `journalctl -u onemind-smb --since "10 min ago" | grep -i "connect.*refused"` shows nothing outbound: Samba made no connection of its own.

## Result
Copy [`../common/RESULT-TEMPLATE.md`](../common/RESULT-TEMPLATE.md), fill it in with the pass or fail of each numbered check (A4, B, C1 to C4, D1 to D3, E1 to E3), run `lab-kits/common/redact.sh` on it before it goes in the repo (no passwords, no real addresses), and attach it to #235.
