<!-- SPDX-License-Identifier: Apache-2.0 -->
# File sharing: SMB shares per person and a Time Machine target

**Date:** 2026-11-20 · **Issue:** #235 (FILES-SHARE-01; backlog UMB-FILES-5, UMB-CLIENT-9 server side) · **Status:** PR 1 built (share model, approval, screen); PR 2 built (Samba on the box, host operation, passwords, Time Machine folder, lab kit) · **Decision:** F-45 is settled as D-017: Samba ships built into the OS image (PR #445)

> **Explain it like I am the founder**
> Your Mac or Windows PC can open a folder on the OneMind box like a network drive. The box does that with Samba, the standard program for it. Each person gets their own share that shows only their own files, and a Mac can also back itself up to the box with Time Machine. All of it is off until you approve it, and it only answers on your home network and your mesh, never the internet. Samba runs as root-owned system software, so the gateway (which faces the network) never starts it or edits its settings itself. The gateway only keeps the list of who is shared and who approved it, and hands that list to a small root helper on the box.

## 1. What PR 1 built

| Piece | Where | What it does |
|---|---|---|
| Share table | `core/onemind_core/smbshares.py`, table `fileshare_shares` | One row per share: kind (`home` or `timemachine`), person, SMB name, Time Machine size cap, state (`applying`, `active`), the approving action and owner |
| `files.share.create` | same, a feature action (risk `actuate`) | Requested through `POST /v1/actions`, approved only by an owner. Agents cannot request it. The check runs at the request and again at approval |
| `GET /v1/shares/smb` | `core/onemind_core/routers/shares.py` | `service` (`available`, the reason when not, off by default, reach `lan` + `mesh`), `people` (who has files of their own), `shares` (an owner sees all, anyone else sees their own) |
| `POST /v1/shares/smb/{id}/stop` | same | Owner only, audited (`fileshare.stopped`). Taking exposure away needs no approval. If the box cannot confirm the removal the share stays listed |
| `SmbHost` | `smbshares.py` | The seam to the box: it receives the whole desired list each time. Only `NoSmbHost` exists, so `available` is false and a request is refused with `smb_unavailable` instead of filing an approval that could not run |
| Screen | `dashboard/src/pages/FileSharing.tsx`, route `/file-sharing` | Shows the honest "not available yet" state now; once a host reports available it files requests and stops shares. A Pro screen (owner, adult) |

Rules kept: off by default; one share per person and kind; a person's share maps to `home:<person>` only; the table is written before the host is asked and a share is dropped only after the host confirms; the host is told names, owners, kinds and size caps, never a password or a host path.

## 2. PR 2: the box side (design)

**Where Samba runs: a host package, started by the root host service, not an app.** `onemindd host serve` ([HOST-ACTIONS.md](HOST-ACTIONS.md)) already is the root helper behind a root-and-gateway-only Unix socket with a journal; it gets one more operation.

1. **Image (`os/`).** Add `samba` to `os/rootfs/packages/debian-common.txt` (Debian 13), mask `smbd`, `nmbd` and `winbind` by default so a fresh box listens on nothing. Config lives in `/data/onemind/samba/` (the root is read-only): `smbd --configfile`, state and `private/` there, a unit drop-in with the same sandbox flags as `onemind-host.service`. avahi needs `/etc/avahi/services/onemind-smb.service`, a symlink into `/data/onemind/samba/` (dangling when there is no share). Firewall: one nftables include that opens `445/tcp` on the LAN and mesh interfaces only, present only while shares exist, so default-deny egress and ingress are untouched. Tests: `test/unit` golden checks on the package list and units, plus a QEMU battery step that mounts a share with `smbclient` and proves a second person gets `NT_STATUS_ACCESS_DENIED`.
2. **Go (`internal/host`, new `internal/smb`).** Operation `smb-apply` takes the desired list, renders `smb.conf` and the avahi file, writes both atomically (temp, fsync, rename), runs `testparm` first and refuses a config it rejects, then `smbcontrol reload-config` (starts or stops `smbd`; nothing left means stopped). Settings that are not negotiable: `server min protocol = SMB2_10` (no SMB1), `map to guest = Never`, `restrict anonymous = 2`, `valid users = <that person only>`, `follow symlinks = no`, `wide links = no`, `unix extensions = no`, one `force user = onemind` so files written over SMB belong to the same Unix user as the Files service. Time Machine shares add `vfs objects = fruit streams_xattr`, `fruit:time machine = yes`, `fruit:time machine max size = <cap>` and the `_adisk._tcp` record. Renderer tests are golden files; the operation uses the socket tests already in `internal/host`.
3. **Per-person SMB passwords.** SMB cannot use passkeys: each person gets an SMB password. New route `POST /v1/shares/smb/password` (that person only, step-up like other credential changes) generates it, shows it once, and sends it to the host over the socket (`smb-password` operation, `pdbedit`/`smbpasswd` into the tdbsam in `/data/onemind/samba/private`). It is never stored in the gateway database, the journal, the audit log or a log line.
4. **Gateway.** `HostSmbClient` replaces `NoSmbHost` (reuse `_UnixConnection` from `core/onemind_core/storage.py`); `status()` reads `GET /v1/status` for the `smb` operation's availability. Boot reconcile: the gateway re-sends the desired list so a box that lost its config converges.
5. **Dashboard.** Connect hints (`smb://<box>.local/<share>`) and a "Set my SMB password" action, shown only when `available` is true.
6. **Proof for the "Done when".** A Mac and a Windows PC opening a member's share cannot run in CI: a lab kit under `lab-kits/` for Zeus (Mac Finder, Windows Explorer, Time Machine first backup), with the QEMU `smbclient` checks as the CI half.

**Time Machine needs its own directory (PR 2).** Today a share's `root` is `home:<person>` for both kinds (`ShareRow.root` in `smbshares.py`), so a Time Machine backup would land inside the person's Files home and count against their Files quota. PR 2 gives Time Machine shares a separate directory outside `home/` (for example `/data/onemind/files/.system/timemachine/<person>`, beside `home/` and `shared/`), changes `root` to say so, and keeps it out of Files browsing, search and trash.

**Open problem to settle in PR 2, not hidden:** writes over SMB bypass the Files service's quota check. Options: count `/data/onemind/files` usage from disk (the service already does at upload time) and report it through Samba's `dfree command`, or enforce with btrfs qgroups once the storage patch lands. Until then a Time Machine share is bounded by its own `fruit:time machine max size`, but a home share is bounded only by free space.

## 3. Not in this feature

Per-device SMB users and WebDAV (UMB-FILES-5's later half), NFS, the household `shared` folder as an SMB share (add it as a third kind once per-role read-only mapping is designed), guest access (refused by design).

## 4. What PR 2 built, and where it differs from the plan above

| Plan | Built |
|---|---|
| Samba started by the host service | `onemind-host.service` is sandboxed with `~@privileged` and no network capability, which Samba cannot live in. So the host service only **writes** the config and the accounts and calls `systemctl`; Samba runs as its own unit, `onemind-smb.service`, which starts only while `/data/onemind/samba/smb.conf` exists. `smbd`, `nmbd`, `winbind` and `samba-ad-dc` are masked |
| nftables include for 445/tcp | The unit's `IPAddressDeny=any` plus `IPAddressAllow=` (LAN, link-local, mesh CGNAT, loopback) restrict it in the kernel in both directions, so default-deny egress holds; `smb.conf` repeats the list in `hosts allow`. `test/unit/test_smb_image.py` checks the two lists are identical |
| `smb-apply` operation, journaled | Desired-state calls, not one-shot actions: `PUT /v1/smb/shares` (the whole list; `testparm` first, then atomic writes, then `reload-or-restart`; an empty list stops Samba and deletes the config, the accounts and their passwords), `PUT /v1/smb/users/{user}/password`, `GET /v1/smb` (`internal/host/smb.go`, `internal/smb`). The gateway re-sends the whole list on every change, so a box that lost its config converges |
| Per-person accounts | One locked Unix account per Samba user from `libnss-extrausers`, kept in `/data/onemind/samba/extrausers` (`/var/lib/extrausers` is a `tmpfiles.d` link there), uids stable once given; Samba's own password database is `tdbsam` in `/data/onemind/samba/private`. Files are written as the gateway's Unix user (`force user`), so Files owns and trashes them |
| Passwords | `POST /v1/shares/smb/password`: generated, shown once (`Cache-Control: no-store`), sent to `smbpasswd` on stdin only; never stored or audited on the gateway, never in a host log or error |
| Time Machine directory | `.system/timemachine/<dir>` beside `home/` and `shared/`, made by the gateway's own user; the share's `root` reads `timemachine:<person>` |
| QEMU battery step | **Not added.** The battery's criteria are preregistered (`test/qemu/PREREGISTRATION.sha256`); adding a test is a decision for the gate. The checks that would run there are in `lab-kits/LT-SMB-01/smb-check.sh` (smbclient from Linux) and its README (Mac, Windows, Time Machine, egress), plus Go tests for the renderer and host calls, and `test/unit/test_smb_image.py` for the image wiring |

**Not verified yet (needs the image built and booted, or real machines):** that Samba, `vfs_fruit` and `libnss-extrausers` install from the Debian 13 snapshot and that `smbd` starts under the unit's capability list; that `smbpasswd` and `pdbedit` work inside `onemind-host.service`'s sandbox (`~@privileged`); that avahi accepts the dangling-until-first-share link; that macOS discovers the Time Machine share; Windows and macOS opening a share. The lab kit lists each.

**Still open:** step-up (a passkey check) before setting an SMB password, as for other credential changes; the SMB-versus-Files quota gap in section 2; per-device SMB users and WebDAV.
