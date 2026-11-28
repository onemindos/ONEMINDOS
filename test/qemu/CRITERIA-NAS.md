# QEMU battery, NAS client: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-22 before the step it judges (`nasmount.py`, run by `run-tests.py`) was ever run against an image. Its sha256 at that moment is in `PREREGISTRATION.sha256`. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to `results.json` and CI logs).

**Serves:** issue #871 (`nas-client-packages`, wave C1): the image carries the SMB and NFS client tools so #718 (a NAS share as a Files location) can mount a share on the box itself, not only on a developer's laptop. D-007 (Debian 13 base), D-017 (Samba file sharing stays with #235). **Does not replace** `CRITERIA.md`: these tests run once, inside the T-battery, on the first boot after T1.

## 1. Starting state and rules

- The box is the battery's slot A, version 1, right after T1 passed (shell on the serial console, health gate done). Nothing outside the guest takes part: the NFS and SMB servers are the guest itself over loopback (127.0.0.1), and QEMU's user-mode network stays restricted.
- "The client packages" are `cifs-utils` (SMB) and `nfs-common` (NFS). "Server packages" are `nfs-kernel-server` and `ksmbd-tools`. Samba (`samba`) is already in the image for D-017 and is not counted here: its units stay masked as before.
- "The size budget" is the size of the board's system slot in `os/boards/<board>/layout.yaml` (`onemind-system-a`), because the read-only root must fit that partition.
- The throw-away exports live under `/run` (tmpfs) and are removed at the end of the step. The NFS export is made with the kernel's own NFS server (`nfsd` module) fed by the harness, because the image ships no NFS server tools. The SMB export is a throw-away `smbd` run from the shell with its own config on a non-standard port, never through `onemind-smb.service`.
- A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| TN0 | Client tools in the image, nothing serving | `dpkg-query` reports `cifs-utils` and `nfs-common` installed; `nfs-kernel-server` and `ksmbd-tools` are not installed; `modinfo` finds the `cifs`, `nfs` and `nfsv4` modules for the running kernel; `/usr/lib/onemind/packages.txt` lists both client packages with an installed size (KiB) greater than 0; no `rpcbind*`, `nfs*` or `rpc-*` unit is enabled and none is active; the root filesystem's used space is below the size budget | Any of these is missing |
| TN1 | NFS loopback mount | A file with a fresh random token, put in a throw-away directory exported over NFSv4 by the guest's kernel, is read back through `mount -t nfs4 127.0.0.1:/` with the same token; `findmnt` shows the mount as `nfs4`; it unmounts cleanly | The mount fails, the token differs, or the unmount fails |
| TN2 | SMB loopback mount | A file with a fresh random token, shared read-only by a throw-away `smbd` on 127.0.0.1, is read back through `mount -t cifs` (SMB 3.1.1, guest) with the same token; `findmnt` shows the mount as `cifs` or `smb3`; it unmounts cleanly | The mount fails, the token differs, or the unmount fails |

The step records, as information, the installed size of each client package and the root filesystem's used space against the budget, so a later size change is visible in the results.

## 3. What these tests do not cover (reported, never claimed)

- A real NAS on the LAN, credentials, Kerberos, or a share that stays mounted across reboots: that is #718 (mount engine) and #719 (real hardware).
- NFSv3 and its lock daemon (`rpc-statd`, started on demand through `rpcbind`): only NFSv4 is mounted here.
- Other boards than the one the battery runs on (the packages come from the common list, so every Debian board gets them, but only the battery board is booted).
