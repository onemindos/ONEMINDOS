<!-- SPDX-License-Identifier: Apache-2.0 -->
# internal/update: the box side of OS updates

**Serves:** contract [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md) §10.1 ("On the box"), brief 30 **B4.2** (`onemindd` update service), **BD-09** (update policy), B5 (health-gate verdicts), D-B7.5 (pre-update snapshot). The channel format is the shared interface in [`os/update/CHANNEL.md`](../../os/update/CHANNEL.md), written by the release pipeline stream; this package is its client.

## What it does, in plain words
A OneMind box never upgrades packages in place: its root filesystem is read-only. Instead the release pipeline builds a whole new system image, signs it as a **RAUC bundle** and lists it in a **TUF repository** (one per channel: `security`, `stable`). This package is the program on the box that:

1. **Checks** the channel. TUF ("The Update Framework") is a signed index of files: four signed JSON files (`root`, `timestamp`, `snapshot`, `targets`) say which bundles exist and their sha256. The box trusts only the `root.json` shipped inside its image (`/usr/lib/onemind/tuf/<channel>/root.json`). TUF's checks stop an attacker or a broken mirror from serving a fake bundle, an old bundle again (**rollback**), or a stale index forever (**freeze**: the timestamp expires after 1 day). We use the maintained Go client `github.com/theupdateframework/go-tuf/v2` (v2.4.2) rather than our own verifier.
2. **Selects** the newest bundle for this box: same `board` and RAUC `compatible` string, newer than the running `ONEMIND_VERSION` (versions compare as dot-separated integers, CHANNEL.md §5, e.g. `0.1.20261112025704`; a developer image's `-dev` suffix ranks below the plain version), `min_from_version` ≤ the running version, not on the gate's `bad-releases` list (an `image-bad` verdict is final; `environment-bad` is re-offered at most 3 times, REC-DEC-45). On the security channel it must also be flagged `security: true`.
3. **Decides** with the owner's policy (BD-09, Z-02 answered 2026-11-28): by default every channel only notifies (ask first); with the owner's opt-in `auto` (`owner.conf`) the channel installs inside the maintenance window; `policy = off` opts out; a `postpone-until` file delays; nothing installs while a previous update awaits the health gate's verdict.
4. **Downloads** the bundle to `/data/rauc`, streaming to disk and checking length and sha256 against the signed TUF metadata before RAUC ever sees it.
5. **Snapshots** `/data` with restic first (if configured; see "No snapshot" below).
6. **Installs** with `rauc install` (RAUC re-checks the bundle's own signature and compatible string; its pre-install handler writes the gate's trial marker), then **reboots at a safe point**: inside the window and never while `/run/onemind/reboot-inhibit` exists (a robot mid-mission creates it).
7. **Reports the verdict after boot.** The health gate (`os/gate/onemind-health-gate`) commits the new slot or rolls back. This package never trusts `rauc install`'s exit status as "updated" (ZimaOS's field failure, [C-TD-casaos-zimaos-044]); it reads what booted plus the gate's files.

## States (the heartbeat's `update.state`)
```
idle ──check finds release, policy says install──► downloading ──► installing ──► pending_reboot
                                                       │               │               │ reboot
                                                       ▼               ▼               ▼
                                                     error           error           trial  (gate marker names the booted version)
                                                                                       │ gate decides
                                                                    committed ◄────────┴────────► rolled_back
```
How the state is read back after a reboot (the gate's files, the same ones the gate script uses):

| `<gate_dir>/pending` (trial marker) | booted `ONEMIND_VERSION` | state |
|---|---|---|
| present, version = booted | — | `trial` (the gate is still deciding) |
| present, version ≠ booted | — | `pending_reboot` (installed, not yet booted) |
| absent, we were in trial/pending_reboot | = target | `committed` |
| absent, we were in trial/pending_reboot | ≠ target | `rolled_back`, with the verdict from `bad-releases` |
| absent, we were downloading/installing | — | `error` ("interrupted") |

## Files
| Path | Owner | What |
|---|---|---|
| `/etc/onemind/update.conf` | image / owner | settings ([example](../../deploy/systemd/update.conf.example)) |
| `/usr/lib/onemind/tuf/<channel>/root.json` | image | the trust anchor; a rotated root is kept as `<state_dir>/tuf/<channel>/roots/N.root.json` and re-verified link by link from this file on every check |
| `/data/onemind/update/status.json` | this package | state + history; onemindd's heartbeat reads it |
| `/data/onemind/update/tuf/<channel>/` | go-tuf | last trusted metadata (gives rollback protection between checks) |
| `/data/onemind/update/postpone-until` | owner | one RFC 3339 time; no auto-install before it |
| `/data/onemind/update/owner.conf` | owner, via the host service | REL-02 (#154): `policy` and `window` (both required), over the image's `update.conf`; written only after the owner approved `os.update.settings` (`PUT /v1/os/settings`, `onemind update settings set`); read on every cycle and heartbeat; an invalid file is ignored, so the image default (notify: ask first) applies |
| `/data/onemind/update/lock` | this package | flock: the daemon and `onemind update apply` never run together |
| `/data/onemind/pending`, `/data/onemind/bad-releases` | RAUC handler, gate | read only here |
| `/data/rauc/` | this package | verified bundles (deleted after a successful install) |

## Config (`/etc/onemind/update.conf`)
`key = value` lines (`key=value` works too); unknown keys are ignored and logged as a warning (CHANNEL.md §4). Required: `channel` (`security`|`stable`), `url` (https, or http to loopback only). Optional: `targets_url` (default `<url>`: target files are fetched by file name from the flat layout of CHANNEL.md §3, following redirects as GitHub Release assets need; may be a template with `{path} {board} {version} {name} {sha256}` for other mirrors), `window` (`HH:MM-HH:MM` local time, may wrap midnight, or `any`; default `02:00-05:00`), `policy` (`auto`|`notify`|`off`; default notify on both channels; the owner opts in to auto), `require_snapshot` (default security=false, stable=true), `restic_binary` + `restic_repository` (+ `restic_password_file`), `reboot_inhibit_file`, `check_interval` (default 1h, plus up to 10% jitter), and path overrides used by tests.

**No snapshot.** If restic is not configured or the snapshot fails, the security channel installs anyway and records `snapshot: none` plus a warning in the status (a security fix outranks a backup that does not exist; rollback of the OS still works, only `/data` is unprotected). The stable channel refuses (`require_snapshot` defaults to true). Both are settings.

## Commands
- `onemindd update` — the service loop (unit [`deploy/systemd/onemind-update.service`](../../deploy/systemd/onemind-update.service)).
- `onemind update status [--json]` — what the box runs, what is available, state, last result, history.
- `onemind update check` — fetch and decide, print the decision; never installs.
- `onemind update apply --local [--no-reboot]` — break-glass: the owner installs now on this machine as root, with no approval (with a box selected, plain `apply` files an `os.update.install` approval through the gateway instead) (overrides window, notify, off and postpone; never overrides a pending gate verdict or a required snapshot).

## Try it (dry run, no VM needed)
```sh
go run ./internal/update/tuftest/devrepo -out /tmp/repo -bundle some.raucb -version 0.1.1   # throwaway keys, in memory only
(cd /tmp/repo && python3 -m http.server 8000 --bind 127.0.0.1) &
# update.conf: channel = security, url = http://127.0.0.1:8000, tuf_root_dir/state_dir/... pointing at temp dirs,
# rauc_binary = a script that writes "<slot> <version>" to <gate_dir>/pending, reboot_command = /bin/true
onemind update check --config update.conf
```
The unit tests do the same in-process (`engine_test.go`): verify OK, expired timestamp, replayed older metadata (rollback), wrong root, wrong board, tampered bundle, consistent-snapshot paths, window/policy/postpone, pending-trial refusal, commit and rollback verdicts, reboot inhibit, the lock, the "no snapshot" rules, and that a local restic repository under `/data` is excluded from its own snapshot.

## v0 shortcuts and open items
- **Gateway approval (REC-DEC-13) is only half wired.** The CLI files `os.update.install` through the gateway, and the A/B image ships the host service that runs the approved install (`onemind-host.socket`, `internal/host/update.go`). Only the dev box, the compose stack and the Mac VM have no `/run/onemind/host.sock`; there the CLI files nothing and `--local` is the working path. B4.2 says OS updates are approval-gated through the gateway; the box asks first by default (Z-02, founder 2026-11-28: policy notify on every channel; auto is the owner's opt-in) and treats `onemind update apply` at the console as the owner's approval. The `/v1/os/*` gateway API and the local Unix socket API come later.
- **Offline grace and mirror installs (B4.3, #155) first slice.** `onemind update check|apply --mirror <dir>` reads the channel from a directory (a USB stick or a mounted LAN share; same flat layout as CHANNEL.md section 3) instead of the network. Nothing about trust is relaxed: the same image-shipped root, the same TUF cache (so a stick cannot replay older metadata), the same length and sha256 checks against the signed targets, and RAUC still verifies the bundle's own signature. The one relaxation is freshness: the TUF reference time is moved back by `offline_grace` (default 90 days, max 1 year, `0` = strict), so a stick built weeks ago still verifies. Online checks never get the grace. Left: automatic detection and mounting of a stick, a gateway/dashboard entry point, a QEMU test with a real RAUC bundle and no network, and root rotation from the stick.
- **Metadata expiries:** this follows the shared interface (timestamp 1 d, snapshot 7 d, targets 30 d, root 1 y). Brief 30 B4.3 says 7 d / 30 d / 180 d; the pipeline sets them, the box only enforces what is signed. Flagged for the DEC owner.
- **Environment-bad re-offer** uses the gate's `bad-releases` count; the re-offer of an abandoned trial on Pi 5 / `efi` route and the alert are not done.
- **Data-migration hold** until commit and the E10 firmware-version record (B4.2) are not done.
- **SB-2 boot-entry re-check** is not part of this package.
- **Not yet run against a real RAUC install in QEMU**: the dry run used a fake `rauc` that writes the trial marker the way `os/rauc/handlers/rauc-pre-install` does. The image does not ship `onemindd`, this unit, `update.conf` or a channel root yet (that wiring is in `os/`, owned by the image/pipeline stream).
