<!-- SPDX-License-Identifier: Apache-2.0 -->
# Updates: OS, apps and rescue (CORE-UPDATE)

**Date:** 2026-11-12 · **Status:** proposal · **Plan epics:** E0 (land wave 2), E4 (update engine on metal, G1), E10 (Pi 5 image, G2), E13 (rescue) · **Deeper docs:** `os/update/README.md` and `os/update/CHANNEL.md` (branch `feat/os-security-pipeline`), `internal/update/README.md` (branch `feat/onemindd-updater`), contract §10; brief 30 B4, B5 · **Serves:** R-1, R-3, BD-09; core-alignment OSU-P1, OSU-P2, OSU-B1…B3, APP-P1, APP-B1; hardening H-07, H-26, H-28.

> **Explain it like I am the founder**
> The OS is never patched in place. Every night CI checks Debian for security fixes, builds a new signed image, tests it, and offers it on the security channel. Your box installs it into the other slot in its maintenance window and reboots.
> The new slot is kept **only if the box comes up healthy** with fresh signals; otherwise it falls back by itself and tells you why.
> Apps follow the same idea: updates are scanned first, a snapshot is taken, and an app update is kept only if the app is healthy afterwards. If k3s itself is broken, a small rescue page outside Kubernetes still lets you roll back.

## 1. Goals and non-goals

| Goals | Non-goals (now) |
|---|---|
| Land the OS security pipeline and the updater (E0) | Delta updates |
| Metal proof at G1: rollback 10/10, 20/20 power pulls bootable (E4) | A fleet server product (Mender, hawkBit) |
| OS updates approval-aware through the gateway (`os.update`, REC-DEC-13) with BD-09 policy | "Never bricks" claims before metal runs (plan §6) |
| Updates screen with booted slot, notes, window, postpone, history | Ubuntu shipping leg (D-007) |
| App updates: Renovate + rescan + approval; health-gated with snapshot and revert | Automatic minor/major app updates |
| Rescue console in `onemindd`, outside k3s | |
| Fleet-staged updates: canary node first | |

## 2. What exists today

| Piece | Where | State |
|---|---|---|
| RAUC bundle build, fresh-signal health gate (G1–G8 design) | `os/rauc/`, `os/gate/` | `main` (emulation only) |
| Nightly security pipeline: tracker check, snapshot pick, SBOM, Trivy + VEX, ClamAV, QEMU battery, signed RAUC, TUF | `os/update/*`, `.github/workflows/security-nightly.yml` | `feat/os-security-pipeline` (3 commits) |
| `onemindd update` service loop, go-tuf v2 client, channels `security`/`stable`, window, postpone, reboot-inhibit, pre-update restic, state read from gate files | `internal/update/`, `cmd/onemindd/main.go` | `main` (PR #15, merged after this spec was written) |
| CLI `onemind update status\|check\|apply` | `cmd/onemind/update.go` | `main` (PR #15) |
| Heartbeat optional `update` object | `internal/heartbeat/` | `feat/onemindd-updater` |
| Developer installs: `unattended-upgrades` limited to security origins + `needrestart` | `deploy/install.sh` | `feat/deploy-v0` |
| App rescan workflow, Renovate config | `.github/workflows/apps-rescan.yml`, `renovate.json` | `feat/app-pipeline` (uncommitted) |

**Known gaps (from the updater README):** no gateway approval wiring, no offline grace or USB installs, metadata expiries differ from brief 30 B4.3 (1 d / 7 d / 30 d vs 7 d / 30 d / 180 d; flagged for the decision owner), not yet run against a real RAUC install.

## 3. Design

### 3.1 OS update flow
```
CI nightly ─► rebuild if a Debian security fix exists ─► scans + QEMU battery ─► sign RAUC + TUF ─► security channel
box: onemindd update ─► TUF verify ─► select (board, compatible, not bad) ─► policy (BD-09)
     ├─ security + auto ─► window ─► restic snapshot ─► rauc install ─► reboot ─► gate: commit | roll back
     └─ stable / notify ─► action os.update awaiting_approval ─► owner approves ─► same path
```

### 3.2 Gateway wiring (CORE-UPDATE-2)
`onemindd` exposes a local Unix socket; the gateway proxies `/v1/os/*` and turns installs into actions.

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/os/status` | any principal | `{node_id, version, booted_slot, channel, policy, window, state, available: {version, notes_url, security, cves_fixed}, history: [...]}` per node |
| `POST /v1/os/apply` (action `os.update.apply`, API.md §5.6) | owner or agent request | owner approval (security auto-installs stay policy-driven, BD-09, and are recorded as `approved_by: policy:os-security`) |
| `POST /v1/actions {"type": "os.rollback", "params": {"node_id"}}` | owner request | owner approval with step-up (`destructive`) |
| `PUT /v1/os/settings` | owner | channel, window, policy; always an `os.update.settings` action the owner approves (API.md §5.6) |

```console
$ onemind update status
Node          Version               Slot  Channel   State      Last result
hub 3f9c2a1b  0.1.20261116025704    B     security  committed  kept after 3 healthy rounds (41 s)
Available     0.1.20261118021133    security · fixes 2 CVEs (2 others not affecting this box, VEX)
Window        02:00-05:00 · policy auto · next check in 37 min
$ onemind update apply --no-reboot
action a_120  os.update.apply  awaiting_approval   → approve on your phone
```
```python
print(client.os.status()[0].booted_slot)                                          # Python
```
```ts
await om.actions.request({ type: "os.update.apply", params: { node_id, version, reboot: "window" } });    // TypeScript
```
```go
st, _ := om.OS.Status(ctx)                                                         // Go
```
**MCP:** a read tool for update status; `request_action` may request `os.update.apply`; never `os.rollback` without the owner, never a policy change.

### 3.3 Rollback you can trust (OSU-B3)
After a rollback the alert names the failed gate check (`G4 core pod onemind-core not Ready since boot`) and the verdict (`image-bad` is final; `environment-bad` is re-offered at most 3 times, REC-DEC-45).

### 3.4 App updates (CORE-UPDATE-5, CORE-UPDATE-6)
- Renovate opens digest/tag bump PRs; `app-gate` re-runs; `verified` apps with `automerge: patch` merge when green (contract §10.2). Daily rescan blocks and alerts on a new critical or malware hit.
- On the box: the catalog update arrives; each installed app shows "update available". `app.update` is an action; a standing approval may cover patch updates of verified apps (founder decision F-6).
- **Health-gated app update:** snapshot the app's volumes (BACKUPS), apply the new checked plan, run the manifest's probes with fresh signals for up to 5 minutes, and on failure re-apply the old plan and restore the snapshot. The result names the failing probe.

### 3.5 Rescue console (CORE-UPDATE-8, REC-W11-04)
Served by `onemindd` on the host, HTTPS with the box CA, LAN only, owner passkey cached locally (SECURITY). Shows health, gate log, slots, journal tail, and offers rollback and restore. Works with k3s stopped.

### 3.6 Fleet-staged updates (CORE-UPDATE-9, OSU-B1)
With more than one node: update the canary (default: the smallest worker) first; its `committed` verdict releases the others one at a time; `image-bad` stops the fleet and alerts.

## 4. Security model
- Trust anchor: the TUF `root.json` in the image; TUF stops fake, rolled-back and frozen metadata; RAUC re-checks the bundle signature.
- Signing keys in separate GitHub environments with reviewers; RAUC and TUF targets never in one job (H-07, CORE-SEC-8).
- `/data` override of `update.conf` may set policy keys only (H-26); path and binary keys only from the read-only image.
- Update protection failures alert the owner (H-28): check failing > 48 h, timestamp expired.
- Agents can request updates but cannot change channel, window or policy; rollback is owner-approved.

## 5. Versioning and compatibility
- Release contract: `os/update/CHANNEL.md` (versions compare as dot-separated integers; `-dev` ranks below). Changes to CHANNEL.md are a hotspot owned by the pipeline stream.
- `SYSEXT_LEVEL` and `ONEMIND_VERSION` in `/usr/lib/os-release`; the gate's G7 refuses a kernel/root version mismatch (SB-4).
- k3s minor guard: a datastore written by a newer k3s minor is not started under an older binary (brief 30 B5).
- Heartbeat `update` object becomes part of contract §2 (additive).

## 6. Test plan and acceptance

| Test | Pass when |
|---|---|
| Unit (exists) | `internal/update/engine_test.go`: expired timestamp, wrong root, wrong board, tampered bundle, window, postpone, pending-trial refusal, verdicts |
| QEMU battery | T0–T5 green on x86_64-efi, vm-do; T0–T1 on arm64-efi (pipeline) |
| Metal G1 (E4) | LT-X86-01/02; rollback 10/10 with a chaos release; 20/20 power pulls during trial still bootable |
| Pi soak | LT-PI5-03 30-day soak started by 2026-12-11 |
| Approval | Stable-channel update on a box with `policy notify` creates `os.update` awaiting approval; nothing installs before approval |
| App gate | A patch update whose probe fails is reverted, snapshot restored, alert names the probe |
| Rescue | With `systemctl stop k3s`, rescue page lists slots and rolls back |

## 7. Build steps

| Epic | Step | Effort | Depends on |
|---|---|---|---|
| CORE-UPDATE-1 | Land `feat/os-security-pipeline` and `feat/onemindd-updater` (commit the uncommitted edits, CI green) | S | – |
| CORE-UPDATE-2 | Local socket + `/v1/os/*` + `os.update`/`os.rollback` actions | M | 1, SEC-2 |
| CORE-UPDATE-3 | Updates screen + "What's new" | S | 2, DASH-1 |
| CORE-UPDATE-4 | Metal runs for G1 (Beelink), start Pi soak | L | 1 |
| CORE-UPDATE-5 | App updates through approval (catalog diff, `app.update`) | M | SANDBOX-2 |
| CORE-UPDATE-6 | Health-gated app updates with snapshot/revert | M | 5, BACKUP-2 |
| CORE-UPDATE-7 | Offline grace + USB/LAN mirror installs | M | 1 |
| CORE-UPDATE-8 | Rescue console in `onemindd` | M | SEC-1 |
| CORE-UPDATE-9 | Fleet-staged updates | M | 2, FABRIC-1 |

## 8. Who owns which files

| Branch | Files |
|---|---|
| `feat/os-security-pipeline` (exists) | `os/update/*`, `.github/workflows/security-nightly.yml` |
| `feat/onemindd-updater` (exists) | `internal/update/*`, `cmd/onemind/update.go`, `deploy/systemd/update.conf.example` |
| `feat/os-api` (proposed) | new `core/onemind_core/os_updates.py`, local socket in `internal/update/api.go` |
| `feat/app-updates` (proposed) | `core/onemind_core/app_updates.py`, `sdk/tools/app-gate` probes |
| `feat/rescue` (proposed) | new `internal/rescue/` |
| Hotspots (serialized) | `cmd/onemindd/main.go`, `os/versions.lock.yaml`, `os/update/CHANNEL.md`, contract §2/§3/§10 |
