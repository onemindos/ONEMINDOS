<!-- SPDX-License-Identifier: Apache-2.0 -->
# Recovery mode: what a box does when its data disk fails

**Status:** v0, built and tested in the QEMU battery (TD1–TD3, [`test/qemu/CRITERIA-DATAFAIL.md`](../../test/qemu/CRITERIA-DATAFAIL.md)). **Serves:** CORE-UPDATE-8 and [`docs/leap/core/UPDATES.md`](../../docs/leap/core/UPDATES.md) §3.5 (a rescue view that works with k3s stopped), REC-DEC-45 (the `environment-bad` verdict), D-007. **Found by:** the umbrelOS 2.0.1 image study (`docs/learning/founder/02-umbrelos-image-teardown.md`, PR #122). umbrelOS is PolyForm-NC: only the idea is reused (boot on with temporary state, then switch to a recovery mode), no code or text.

## 1. The problem, in plain words

A OneMind box keeps everything that changes (apps, k3s, logs, settings, the health gate's notes) on one partition, `onemind-data`, mounted at `/data`. The OS itself is read-only.

Before this change, `/etc/fstab` listed `/data` as a normal, *required* mount. In systemd, every required mount belongs to `local-fs.target` ("all local filesystems are mounted"). If one fails, `local-fs.target` fails, and systemd's rule for that is to stop the whole boot and start `emergency.target`: a root shell on the console, **no network**. A box in a cupboard just looks dead. No page, no phone alert, nothing the owner can see.

## 2. What the box does now

| Step | What happens | Why |
|---|---|---|
| 1 | `/data` and the bind mounts that need it are marked `nofail` in fstab, so a failure no longer fails `local-fs.target`. `/data` waits at most 30 s for its partition (`x-systemd.device-timeout=30s`). | `nofail` turns "required" into "wanted". 30 s: on every v0 layout the data partition is on the same disk as the OS, so it appears together with the root; a longer wait only delays recovery. |
| 2 | `onemind-data-check.service` runs after those mounts and **before** `local-fs.target`. It checks: `/data` is mounted, read-write, a write + fsync + read-back works, and every bind mount from fstab is in place. | `nofail` also drops the ordering "before `local-fs.target`". The check puts it back, so nothing that needs `/var/log` or `/var/lib/...` starts before we know the answer. |
| 3 | If the check fails it writes the reason (`missing`, `unmountable`, `read-only`, `unwritable`, `layout`) to `/run/onemind-recovery/status`, mounts small **tmpfs** (RAM) directories over `/var/tmp`, `/var/lib/systemd`, `/var/log`, `/home` and `/root`, and exits non-zero. `OnFailure=` then **isolates** `onemind-recovery.target`. | "Isolate" means: stop the normal boot plan (k3s, gateway, gate, apps) and start only this target's units. The tmpfs dirs let ordinary services run with temporary state, the way umbrelOS does; `/data` itself stays unmounted, so nothing can write into the empty directory under it. |
| 4 | `onemind-recovery.target` starts: network (`systemd-networkd`, `systemd-resolved`), mDNS (`avahi-daemon`, so `onemind.local` still resolves), the console login, `onemind-recovery.service` and `onemind-recovery-web.service`. | Keep the box reachable. |
| 5 | `onemind-recovery.service` records the failure on the **ESP** (`/boot/efi/onemind/data-failed`), decides what to do with the update slots (§3), raises the alert (§4) and writes the status page. | The ESP is the small FAT partition that holds the bootloader. It is the only writable place that does not depend on the data disk. |
| 6 | `onemind-recovery-web.service` serves a read-only status page on port **8080** (the dashboard's port, so `http://onemind.local:8080` lands on it). Every path answers **HTTP 503**; `/status.json` is the same in JSON. | 503 "service unavailable" is the honest status: apps and data are offline. A plain static page needs no data, no database and no login. |

**What it never does:** format, repair (`fsck -y`), resize or wipe the disk; move data; start k3s, apps or the AI; take any action on the owner's behalf. The normal boot-time `fsck -a` (safe fixes only, "preen") is unchanged. AI never actuates (D-001 to D-007): there is nothing in recovery mode an agent can call.

When the disk is fixed, a normal restart boots normally. The box does not leave recovery mode by itself while running (simpler, and an owner who is swapping disks should decide when to restart).

## 3. Updates: a failed disk is not a failed update

The health gate ([`os/gate/onemind-health-gate`](../gate/onemind-health-gate)) decides whether a freshly installed OS version is kept. Its notes live on `/data`, so without `/data` it cannot run. Two risks follow, and both are handled:

1. **The box drifting back to an older OS.** GRUB counts every boot of a slot and gives up on it after 3 boots unless the slot is "marked good". Normally the gate does that on every boot. Without it, three restarts with a dead disk would switch the box to the *other* slot, an older version.
2. **A good update being blamed for the disk.** If the disk fails during an update's trial boots, the trial runs out and the old slot boots. Before this change the gate would later record the new version as `image-bad`, which is final: it is never offered again.

The fix needs to know, without `/data`, whether this boot is a trial. So RAUC's pre-install handler now writes its trial marker twice: on `/data` as before (it stays the one the gate trusts) and as a copy on the ESP (`/boot/efi/onemind/pending`). Recovery mode reads the copy:

| Marker copy says | `decision=` | Recovery mode does |
|---|---|---|
| nothing | `committed` | `rauc status mark-good booted`: resets the try counter of the already-committed slot, exactly what the gate does in its committed mode. No drift. |
| the booted slot | `trial` | Nothing to the slots. The trial is left undecided: the try counter keeps counting, so if the **new image** is what breaks the disk mount, GRUB still falls back to the old slot after 3 boots. When `/data` works again, the gate runs its normal trial checks. |
| the other slot | `fell-back` | `mark-good booted` (this slot was committed before the trial). It does **not** mark the other slot bad. |

When `/data` works again, the gate reads the ESP notes first. If a trial ran out while its boots were in recovery (a note names that slot and version), the gate's fell-back verdict is **`environment-bad`** instead of `image-bad`. `environment-bad` is re-offered at most 3 times (REC-DEC-45), so a good update gets another chance, and an image that really breaks the data mount is still stopped after 3 tries. The gate then moves the notes into `/data/onemind/data-failures.log` and deletes them from the ESP, so the gateway can show the owner what happened.

RAUC itself keeps its own small state in `data-directory=/data/rauc` and refuses to start without it ([rauc v1.15.2 `src/context.c` L339–L350](https://github.com/rauc/rauc/blob/v1.15.2/src/context.c#L339-L350)). Recovery mode therefore starts RAUC with a copy of `/etc/rauc/system.conf` whose `data-directory` is under `/run` (a runtime drop-in for `rauc.service`), only on that boot.

## 4. The alert

With the data disk gone there is no gateway, no NATS and no stored phone-push credentials, so v0 cannot push to a phone. It does what it can without them:

- the console line `ONEMIND-RECOVERY: entered ...` and a login-prompt banner (`/run/issue.d/`), for anyone with a screen;
- a journal entry at priority `crit` with a fixed `MESSAGE_ID` (`8a1f4c2e6b0d4f7a9c3e5b1d2f4a6c80`), for log tools;
- the status page on `onemind.local:8080`, which the phone and desktop apps already open;
- the ESP note, moved to `/data/onemind/data-failures.log` on the next good boot, for the gateway's history.

## 5. Founder calls (not decided here)

| # | Question | v0 default until Zeus decides |
|---|---|---|
| FC-R1 | **Phone push while in recovery.** Keep a copy of the push relay credentials outside `/data` (for example on the ESP, which is not encrypted) so a dead disk can still alert the phone? It is convenient, but it puts a secret on an unencrypted partition. | No push. Page, mDNS, console and journal only. |
| FC-R2 | **What the page may show to anyone on the LAN.** It needs no login (the owner's passkeys are on `/data`). Today it shows the reason, the OS version and slot, and the time. Is showing the OS version acceptable unauthenticated? | Shown (it helps support; the normal discovery record already exposes the box). No serial numbers, no names, no disk contents. |
| FC-R3 | **Owner actions in recovery** (start a restore onto a new disk, format a *new* blank disk, mark the disk "gone for good"). Each would be destructive or sensitive and needs owner approval with passkey step-up, which needs `/data`. | None. The page is read-only. Restores and formatting stay manual. |
| FC-R4 | **SSH in recovery** on cloud boards. Host keys live on `/data`, so sshd cannot start with the same identity. Generate throwaway host keys (clients see a changed key) or keep SSH off? | Off. Cloud boxes rely on the provider's console. |
| FC-R5 | **Leave recovery by itself** when the disk comes back while running, instead of waiting for a restart. | Wait for a restart. |
| FC-R6 | **A real rescue system in the `onemind-recovery` partition** (D-B2.3, empty in v0). This change does not use that partition: recovery mode is part of the normal OS image, so every update ships it. | Unchanged: the partition stays empty. |

## 6. Limits (known, reported)

- **First update from an older image.** The ESP copy of the marker is written by the *running* system's pre-install handler. An update installed from an image older than this change writes only the `/data` marker, so if the data disk fails during that one trial, recovery mode sees `decision=committed` and marks the new slot good. The gate still runs its trial checks once `/data` is back (its `/data` marker is intact), so a broken image is still rejected then; only the "fall back after 3 boots" protection is lost for that one trial.
- **Jetson** uses NVIDIA's own fstab and update path (`os/boards/jetson-orin/`); it is not covered yet.
- The status page is plain HTTP on IPv4. The planned rescue console (UPDATES §3.5) is HTTPS with the box CA, which lives on `/data`.
- Only the "partition missing" case is tested in QEMU; see `test/qemu/CRITERIA-DATAFAIL.md` §3.

## 7. Files

| File | Installed as | Role |
|---|---|---|
| `onemind-data-check` + `.service` | `/usr/lib/onemind/`, `/usr/lib/systemd/system/` | the check (§2 steps 2–3), enabled |
| `onemind-recovery.target` | `/usr/lib/systemd/system/` | the recovery boot target (not enabled; reached only by isolate) |
| `onemind-recovery` + `.service` | same | note, slot decision, alert, page (§2 step 5, §3, §4) |
| `onemind-recovery-respond`, `onemind-recovery-web.service` | same | the status page on :8080 |
| `os/rootfs/layers/base/etc/fstab`, `os/boards/rpi5/rootfs/etc/fstab` | `/etc/fstab` | `nofail` + device timeout |
| `os/rauc/handlers/rauc-pre-install` | `/usr/lib/onemind/` | writes the ESP copy of the marker |
| `os/gate/onemind-health-gate` | `/usr/lib/onemind/` | reads the ESP notes, `environment-bad` on fall-back |
