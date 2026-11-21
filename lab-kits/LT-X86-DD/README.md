<!-- SPDX-License-Identifier: Apache-2.0 -->
# LT-X86-DD · Daily-driver gate for the Dell all-in-one (M-LIVE, #234)

**Status:** kit-ready. The logic is proven only against stubs (`test/unit/test_dd_gate.py`). **It has not run on the R530 VM or the Dell yet.** Acceptance is: run it end to end on an R530 VM first, then on the Dell, and file the evidence.
**Builds on:** [`../LT-X86-01/`](../LT-X86-01/README.md) (image, installer, criteria), [`../G1/`](../G1/README.md) (update, rollback and power-pull tools), `test/restore-drill/` (restore timing), `test/perf/` (load).

> **Explain it like I'm the founder.** "Can I live on this box?" is not one question. It is seven: does it install and come up on its own, can I sign in with a passkey, does a bad update undo itself, does it survive someone pulling the plug, are there doors open that should be shut, can I rebuild everything from a backup in under an hour, and does it stay quick under load. Today each answer lives in a different tool. This script is the checklist that asks all seven and writes down the answers, with timings, in one file. It runs on your Mac (or the lab box), not on the box under test, so the box stays as a real user would have it.

## Stages
| Stage | How it is judged | Evidence it uses |
|---|---|---|
| `install` | runs it | the dashboard answers `/healthz` over TLS with the box CA (time to ready is recorded); over SSH: Debian 13 (D-007), root mounted read-only, RAUC booted slot `good` |
| `passkey` | runs it | the owner has at least one passkey (`GET /v1/auth/passkeys`). Registering one is a human step in a browser that trusts the box CA, so the stage is PENDING until you have done it |
| `rollback` | reads it | the G1 kit's `result.json` (`g1-run.py` on the test image): good update commits, every bad bundle rolls back, 10 of 10 chaos rollbacks |
| `powerpull` | reads it | the `g1-power.py` results file: 20 of 20 pulls come back with no keyboard |
| `portscan` | runs it | TCP connect scan of ports 1 to 1024 plus the service ports of the image (k3s, NATS, Postgres and others). Only 22, 80 and 443 may be open (`--allow-ports` to change) |
| `restore` | reads it | the JSON from `test/restore-drill/drill.py`: byte-for-byte verified inside 3600 s |
| `load` | runs it | copies `test/perf/perf.py` to the box, runs `load`, then `check` against `test/perf/budget.json` |

**Why some stages only read.** A power pull needs a relay, a BMC or your hand, and a rollback test reboots the box several times. Those tools already exist and survive reboots, so the gate reads what they wrote instead of duplicating them. A stage with no evidence is **PENDING**, never PASS. A stage that ran and missed is **FAIL**.

## Run it
```sh
python3 -I lab-kits/LT-X86-DD/dd-gate.py plan
python3 -I lab-kits/LT-X86-DD/dd-gate.py run \
  --host root@<box> --base-url https://<box> --ca box-ca.pem --token-file owner.token \
  --g1-result g1-result.json --power-results g1-power.jsonl --restore-results restore.json \
  --label "Dell all-in-one" --out evidence/dd-gate/
```
`--stage install,portscan` runs part of it. SSH uses your agent or `DD_SSH_KEY` (a path). Exit code: 0 all PASS, 1 a stage failed, 3 something is still PENDING, 2 bad usage.

**First on the R530 VM, then on the Dell.** On the VM the power-pull stage uses `g1-power.py --power redfish` or a Proxmox hook; on the Dell it is the cord or a smart plug. The restore drill needs KVM, so run it on the lab box and pass its result file.

## Record
The run writes `dd-gate.json` and `DD-GATE.md` (addresses, MACs, e-mails, home paths and tailnet names are masked). Read them once by eye, then file them as `research-output/evidence/lab/founder-hardware/DD-GATE.md`. The script never decides that the Dell is ready: that is your call.

## Not covered here (honest list)
- Passkey on the phone app (open founder decision in `mobile/README.md`).
- Real OS updates from the dashboard (no update path for an installed box yet, blocker B1) and Wi-Fi, microcode and firmware (B4): the gate has no stage for them until they exist.
- Thirty-day soak, remote access away from home.
