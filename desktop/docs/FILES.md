<!-- SPDX-License-Identifier: Apache-2.0 -->
# Files in Finder and File Explorer: the WebDAV mount plan

**Status (2026-11-12): designed, not built.** The desktop app mounts nothing yet. Its **Files** button still opens the box's SMB address (`smb://<box>/` on macOS, `\\<box>\` on Windows), as in the CLIENT-8 skeleton.

**Why not built:** the gateway serves no WebDAV yet. The Files service stream (UMB-FILES-1, -2 and -6: spaces, uploads, trash, quotas, folder grants) has no WebDAV endpoint. WebDAV and SMB serving is UMB-FILES-5, which is still `todo` and waits on founder decision F-45 (Samba as a system app, with WebDAV alongside). A mount client with no server to test against would be guesswork. This page fixes what the desktop needs, so the FILES-5 contract PR can include it and the desktop code can follow in its own PR (`desktop/src-tauri/src/mount/**`, epic UMB-CLIENT-9 / DESKTOP-FILES-1).

> **Explain it like I am the founder**
> "Mounting" means the box's folders appear in Finder or File Explorer like a USB disk. The operating system does the file traffic itself, using a network file protocol. SMB is the Windows file-sharing protocol (Samba is the Linux server for it). WebDAV is file access over HTTPS. The desktop app's job is small: get a per-computer password from the box, hand the address and password to the OS, and remove the mount when the computer is revoked.

## 1. What the desktop needs from the box (input for the FILES-5 contract PR)

| Need | Why | Proposed shape (the contract owner decides the names) |
|---|---|---|
| A feature flag and the WebDAV root URL | The app must know the box serves WebDAV before it offers "Connect", and older boxes answer 404 | `GET /v1/instance` `features` contains a WebDAV entry, plus the root URL for the signed-in person (`home:<person>` and shared spaces) |
| A **per-device** credential | OS WebDAV clients speak Basic or Digest auth, not bearer tokens. A per-device password can be revoked alone, and a stolen laptop file never holds the owner token | The clients study's `POST /v1/shares/credential` (create or rotate; the secret returned once as `one_time`), usable for SMB and WebDAV alike |
| WebDAV class 2 (`LOCK`/`UNLOCK`) | macOS mounts a WebDAV share **read-only** when the server does not support locking | `golang.org/x/net/webdav` (BSD-3-Clause, the files study's pick) has a lock system; turn it on |
| HTTPS with a certificate the OS trusts | The OS client validates TLS against the OS trust store, not against this app's settings | The per-box CA (contract §12.7) installed in the OS store by `onemind tls trust` (NETWORKING §9). The CA is name-constrained to the box's names, which limits what trusting it allows |
| Revocation that bites at once | A revoked or lost device must lose access at the next request | The credential check runs per request on the box; revoking the device deletes its credential |

## 2. How each OS mounts it

| OS | Mechanism | Notes |
|---|---|---|
| macOS 14+ | NetFS `NetFSMountURLAsync` with the `https://` WebDAV URL (Finder's "Connect to Server" uses the same path) | Password passed in the call, never on a command line. The mount appears under `/Volumes`. UNVERIFIED: the exact NetFS options for a non-interactive WebDAV mount; check on a Mac before building |
| Windows 11 | The WebClient service (WebDAV redirector): `WNetAddConnection2W` with `\\<host>@SSL@<port>\<path>` and no fixed drive letter (Windows picks one) | WebClient sends Basic auth only over HTTPS by default and caps a file at about 50 MB (`FileSizeLimitInBytes`) unless the registry is changed. UNVERIFIED: Microsoft lists WebClient as deprecated in recent Windows releases; if it is off or gone on a clean Windows 11, WebDAV cannot be the Windows path and SMB is. This is input for F-45 |
| Linux | GVfs: `gio mount davs://<host>:<port>/<path>` (password on stdin), or davfs2 | Not built for v1 (no Linux build in CI yet) |

The app never stores the WebDAV password in a file. It lives in the OS keychain next to the box token (`store.rs`), under its own entry, so removing the box removes both.

## 3. Flow in the app

1. The **Files** button checks `features`. With no WebDAV on the box, it keeps today's behaviour (open the SMB address) and says so in its tooltip.
2. First connect: request the per-device credential, keep it in the keychain, then mount through the OS call above. The UI says "Connected as <device name>", not "connected as owner".
3. Each later start: re-mount only after the box has answered `GET /v1/instance` with the same instance id, so a look-alike box on the network never receives the password (the clients study's "re-adopt mounts only after identity proof" rule).
4. **Remove** on a box unmounts it and deletes its credential locally. On the box, the owner revokes the device to cut access everywhere.

## 4. Tests to write with the code

- Mount, write a file and read it back on macOS and Windows against a FILES-5 test box (CI cannot mount; this is a lab test for the test register, TEST-REG-1).
- A revoked device fails its next file operation.
- A child's device cannot list the owner's space.
- A box with a different instance id at the same address gets no credential.
- An OS that does not trust the box CA fails to mount, with an error that names `onemind tls trust`.
