<!-- SPDX-License-Identifier: Apache-2.0 -->
# G1 on metal: the update engine on the Beelink, and the Pi soak starts (CORE-UPDATE-4, #215)

**Status:** kit-ready (blocked: founder-hardware). **Nothing here has run on a real box.** The kit logic is proven only against a fake `rauc` and `systemctl` (`test/unit/test_g1_kit.py`), and the same sequence runs in QEMU as the battery (`make battery`). **The metal run is the founder's step, and the kit never says G1 passed.**
**Serves:** gate G1 (research-output/20-PLAN-180-DAYS.md), `docs/leap/core/UPDATES.md` §6 "Metal G1", REC-DEC-05/07/23/31/34, DC-12. **Builds on:** [`../LT-X86-01/`](../LT-X86-01/README.md) (image, bundles, criteria), [`../LT-PI5-01/`](../LT-PI5-01/README.md), [`../common/PP-10.md`](../common/PP-10.md).

> **Explain it like I'm the founder.** LT-X86-01 asks you to type seven `rauc install` lines and, after each reboot, read a log. This kit types them for you, in the same order, and after each reboot it reads the gate's own log and writes down PASS or FAIL in one file (`result.json`). It adds the "rollback 10 times in a row" loop that G1 asks for, and it starts the 30-day memory soak on the 4 GB Pi. It cannot pull the power cord and it cannot watch the screen for you; those two checks stay yours, with blanks in the record.

## What it checks (all from the image's own gate log, parsed like `test/qemu/run-tests.py`)
| Step | Bundle | Passes when |
|---|---|---|
| refuse-wrong-key, refuse-plain-good | `wrong-key`, `plain-good` | `rauc install` fails and no trial marker is written (T2, T11) |
| good-commit | `good` | the other slot boots and the gate logs `RESULT mark-good` (health-gated commit; time recorded) |
| reboot-committed | none | second reboot logs `committed-boot` on that slot, no trial (T3) |
| bad-k3s, bad-noagent | `bad-k3s`, `bad-noagent` | `RESULT mark-bad`, then the old slot boots and commits (T4, T5) |
| bad-boot, bad-hang | `bad-boot`, `bad-hang` | `RESULT fell-back` on the old slot after the boot attempts run out (T6, T7) |
| rollback-01 .. rollback-10 | `bad-k3s` again | the chaos release rolls back every time (`--rounds N`; G1 wants 10/10) |
A step fails at once if the gate ever says `mark-good` for a bad bundle, or after `--step-timeout` (2400 s) without a decision.

## Run it
1. **Build and flash** exactly as in [LT-X86-01 §A-B](../LT-X86-01/README.md) (`make fixtures BOARD=x86_64-efi UPTO=T10 HW=1`; for the Pi: `BOARD=rpi5`, [LT-PI5-01 route P](../LT-PI5-01/README.md)). The disk and the bundles stick must come from the **same** `make fixtures` run (one throwaway key pair signs both).
2. **On the box** (booted from the SSD, Secure Boot off, stick plugged in; the console logs in as root):
```sh
mkdir -p /run/onemind-test && mount -o ro /dev/disk/by-label/onemind-test /run/onemind-test
# put g1-run.py on the box (a third stick, or scp), then:
python3 -I g1-run.py run --dry-run     # prints the plan and the preflight; changes nothing
python3 -I g1-run.py autoresume on     # optional: the kit resumes itself after each boot
python3 -I g1-run.py run               # installs, reboots. After each reboot: run it again (or let autoresume do it)
```
Exit code 3 means "the gate is still deciding, run it again in a minute". `status` shows progress. State lives in `/data/onemind-lab/g1/` (`result.json`, `evidence/`), on the data disk, so it survives every reboot and every slot switch.
3. **Power pulls (20 of 20):** by hand, [LT-X86-02 / PP-10](../common/PP-10.md), after the automatic steps pass. Count them in the record.
4. **Record:** `python3 -I g1-run.py report` writes `/data/onemind-lab/g1/G1-RECORD.md` from [`G1-RECORD.template.md`](G1-RECORD.template.md). Fill every `FOUNDER:` line, copy it and `result.json` off the box (run the gate log through `lab-kits/common/redact.sh`), and file it as `research-output/evidence/lab/founder-hardware/G1.md` next to LT-X86-01's result.
5. **Wipe the SSD** afterwards (22 §2.3 rule 3).

## Power-pull harness (controller side, `g1-power.py`, #215)
Step 3 above (20 of 20 pulls) no longer has to be hand-timed. `g1-power.py` runs on **your Mac or the lab box**, not on the device under test, and repeats the [PP-10](../common/PP-10.md) cycle: start `rauc install` over SSH, cut power at a phase (write-start, write-mid, write-done, reboot, trial-boot, then random), hold it off, power on, wait. A cycle **passes** when the box comes back with no keyboard, RAUC says the booted slot is `good`, no trial is pending, the gate's last line is `committed-boot` or `mark-good` for that slot, and the optional HTTP probe answers. It stops at the first failure; re-running the same command resumes from the results file.

| `--power` | What cuts power | Environment (never stored, never printed) |
|---|---|---|
| `manual` | it asks you to pull and replug the cord | none |
| `redfish` | BMC `ComputerSystem.Reset` `ForceOff` then `On` (Dell iDRAC, e.g. an R610/R530 node) | `G1_BMC_HOST`, `G1_BMC_USER`, `G1_BMC_PASS`, optional `G1_BMC_SYSTEM_ID`, `G1_BMC_CACERT` |
| `ipmi` | `ipmitool chassis power off` then `on` (hard, not `soft`); password goes through `IPMI_PASSWORD` | same three `G1_BMC_*` |
| `hook` | HTTP calls to a smart plug or relay | `G1_PLUG_OFF_URL`, `G1_PLUG_ON_URL`, optional `G1_PLUG_METHOD` |

Probe settings: `G1_SSH_TARGET` (`user@host`), optional `G1_SSH_KEY` (a path) and `G1_HEALTH_URL`.
```sh
python3 -I g1-power.py plan --cycles 20                      # the phases; touches nothing
G1_SSH_TARGET=root@<box-ip> python3 -I g1-power.py run --power manual --cycles 20
G1_SSH_TARGET=root@<box-ip> G1_BMC_HOST=<bmc-ip> G1_BMC_USER=... G1_BMC_PASS=... \
  python3 -I g1-power.py run --power redfish --confirm-power --reinstall-check
python3 -I g1-power.py summary                               # the line for G1-RECORD.md section B
```
Backends other than `manual` cut real power, so they need `--confirm-power`: a human saying yes to this box. Use a BMC that only reaches the lab box. The box needs the same test image and bundles as the rest of this kit; the results file holds slots, verdicts and times only (no addresses), but run it through `lab-kits/common/redact.sh` before filing it. Aborted cycles (box unhealthy before the pull, install failed before the pull) are not counted.

**UNVERIFIED (first real run):** the exact `rauc status --output-format=json` layout on the shipped RAUC (the parser is tolerant and falls back to a failed check, never a pass); iDRAC accepts `ForceOff` on the target firmware; the 40 s `--trial-delay` really lands before the gate decides on that board (tune it from the gate log). Tested only against fakes (`test/unit/test_g1_power.py`).

## Soak start (4 GB Pi 5, LT-PI5-03; deadline 2026-12-11)
After the Pi's LT-PI5-01 run, on the 4 GB Pi with the hardened k3s config:
```sh
python3 -I g1-run.py soak-start --disk nvme0n1     # baseline sample, soak-start.json, a daily systemd timer
python3 -I g1-run.py soak-sample                   # one more sample by hand (the timer does this daily)
```
Each line of `soak.jsonl` has free memory, MiB written to the disk (`/proc/diskstats`), NVMe wear (needs `smartctl`) and the size of k3s's `state.db`. It warns when the board is not a 4 GB one. The pass rule is LT-PI5-03's: >= 2.0 GiB free over 30 days and <= 5 GB/day written. The kit only records; it does not judge the soak.

## UNVERIFIED (to confirm on the first real run)
- Writing the timer and resume units to `/etc/systemd/system` on the read-only root: if that fails the kit says so and you run the command by hand.
- The same sequence on the Pi (firmware `tryboot`): the gate and bundle names are the same, but the Pi fall-back path has not been booted (IMAGES.md §8, "Not tested").
- `bad-boot` and `bad-hang` boot-attempt counts (3) are read from the screen, not from the log; the kit checks the outcome, not the count.
