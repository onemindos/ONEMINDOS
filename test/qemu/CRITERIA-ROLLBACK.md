# QEMU battery, go back to the previous OS version: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-25 before the `os-rollback` host action (`internal/host/rollback.go`) or `rollback.py` was booted in any image. Its sha256 at that moment is in `PREREGISTRATION.sha256`. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the run's `results.json` and CI logs).

**Serves:** P-16 (decisions D-027, D-028, D-029: every write is an owner action; going back is destructive, so the owner approves it with a passkey), D-007 (RAUC A/B with a health-gated commit). **Does not replace** `CRITERIA.md`; the update, the gate and the rollback of a bad update stay tested there.

## 1. Starting state and rules

- The fixture is the slot-A disk of `make fixtures` (version V1), booted through first boot as in `CRITERIA-BOOTLOCK.md` §1. The test then installs the fixture's `good.raucb` (version V2) the way T3 does, so the box runs V2 in slot B and V1 waits, committed, in slot A.
- The gateway's passkey approval is covered by `core/tests/test_os_rollback_passkey.py`. Here the box's **host service** is asked directly over `/run/onemind/host.sock`, as the gateway does after an approval: the request carries the action id, the kind `os-rollback` and the version the owner approved, nothing else.
- Everything is read from the guest's console and the host service's own JSON answers. No test changes a file on the box except through RAUC's own commands named below.
- A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. Every verdict records the board, KVM or TCG, and the host CPU count. A harness bug may be re-run once and is named as such.
- Timeouts (wall clock): first-boot configuration line 900 s; gate result as in `CRITERIA.md`.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| RB0 | Starting state | After the good update the gate logged `RESULT mark-good slot=B version=V2`, `rauc status` shows slot A `good` holding V1, and no `/data/onemind/pending` marker exists | Anything else (the later tests are then BLOCKED, not failed) |
| RB1 | The host offers a rollback only when the other slot is known good | `GET /v1/status` lists `os-rollback` as available; after `rauc status mark-bad other` it lists it unavailable with a reason containing `not marked good`; a `POST /v1/operations` for V1 then answers a refusal (HTTP 409) and the box does not reboot (same boot id and booted slot B 30 s later); after `rauc status mark-good other` it is available again | Offered with a bad slot, accepted with a bad slot, a reboot, or not offered again after the repair |
| RB2 | An approved rollback boots the previous slot and the gate commits it | `POST /v1/operations {action_id, kind: os-rollback, version: V1}` answers 202; the box reboots; the next gate line is `RESULT committed-boot slot=A version=V1` (committed mode, no trial); `rauc status` shows A booted and `good`; no pending marker; `grep V2 /data/onemind/bad-releases` shows the version it left with `verdict=owner-rollback`; `GET /v1/operations/<id>` says `succeeded`; no `rauc install` ran (no new `onemind-pre-update` restic snapshot is needed and none is required) | A different slot or version booted, a trial boot, the gate rolling it back, the marker present, the version not recorded, or the operation not `succeeded` |
| RB3 | A rollback can not be asked for twice to swap the slots | Right after RB2, `GET /v1/status` lists `os-rollback` unavailable with a reason containing `rolled back earlier`, and a `POST` for V2 is refused (HTTP 409) and the box does not reboot | Offered, accepted, or a reboot |
| RB4 | A version the owner did not approve is not run | Run after RB1 and before RB2, on the same boot: a `POST` for `9.9.9` (not the other slot's version) is taken (202) and then ends `failed` with reason `version_changed` in the host's journal within 60 s, the box does not reboot (same boot id, booted slot B), and the boot order is unchanged | The box reboots, boots a different slot, or the operation ends `succeeded` |

## 3. Boards and verdicts for this task

- **x86_64-efi** (OVMF) runs RB0-RB4 in the order RB0, RB1, RB4, RB2, RB3. Other boards are reported, never required.
- On a host without KVM the run uses TCG and says so; a timeout missed only because TCG is slower is **BLOCKED (TCG timing)**, and the test must then pass on a KVM host before it counts.
- Required for this task's "done": RB0-RB4 PASS on x86_64-efi.
