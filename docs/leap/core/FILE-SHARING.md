<!-- SPDX-License-Identifier: Apache-2.0 -->
# File sharing: SMB shares per person and a Time Machine target

**Date:** 2026-11-20 · **Issue:** #235 (FILES-SHARE-01; backlog UMB-FILES-5, UMB-CLIENT-9 server side) · **Status:** PR 1 built (share model, approval, screen); PR 2 (Samba on the box) designed here, next · **Open decision it touches:** F-45 in [DECISIONS-NEEDED.md](../DECISIONS-NEEDED.md) (not locked; see section 4)

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

**Open problem to settle in PR 2, not hidden:** writes over SMB bypass the Files service's quota check. Options: count `/data/onemind/files` usage from disk (the service already does at upload time) and report it through Samba's `dfree command`, or enforce with btrfs qgroups once the storage patch lands. Until then a Time Machine share is bounded by its own `fruit:time machine max size`, but a home share is bounded only by free space.

## 3. Not in this feature

Per-device SMB users and WebDAV (UMB-FILES-5's later half), NFS, the household `shared` folder as an SMB share (add it as a third kind once per-role read-only mapping is designed), guest access (refused by design).

## 4. A file that conflicts with a decision? No, but one open decision

[DECISIONS-NEEDED.md](../DECISIONS-NEEDED.md) F-45 proposes Samba "as a separately updatable system app `apps/samba`". It is not locked (D-001 to D-014 do not mention SMB). PR 2 above chooses a host package because an app in k3s would need host networking for mDNS and Time Machine discovery, a host bind of the Files tree with the right owner, and a way to be told per-person passwords, all of which the root helper already does safely. Zeus decides; the model, routes and screen in PR 1 work either way, because they only talk to `SmbHost`.
