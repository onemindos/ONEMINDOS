<!-- SPDX-License-Identifier: Apache-2.0 -->
# G1 record: RAUC update engine on metal (CORE-UPDATE-4, #215)

`g1-run.py report` fills the automatic parts from `result.json`. **You** fill every `FOUNDER:` line and decide the verdict.
The kit never decides that G1 passed. Gate G1 (research-output/20-PLAN-180-DAYS.md; docs/leap/core/UPDATES.md §6) needs:
rollback 10/10 with a chaos release, 20/20 power pulls during the trial still bootable, and the Pi soak started by 2026-12-11.

- Date / tester: FOUNDER: <date> / founder
- Device: {{device}}  (no serial numbers) · BIOS or EEPROM version: FOUNDER:
- Software: {{software}} · kit commit: FOUNDER: <sha>
- Run started / last update: {{started}} / {{updated}}

## A. Automatic checks (from `result.json`; evidence files are in `evidence/`)
| Step | Bundle | Verdict | Detail |
|---|---|---|---|
{{rows}}

```json
{{summary}}
```

## B. Things only you can see
- [ ] FOUNDER: no keyboard input was needed after any reboot (Secure Boot OFF, UEFI mode)
- [ ] FOUNDER: `curl -s localhost:10248/healthz` printed `ok` on the committed slot at the end
- Good-commit time (`mark-good ... after Ns` in step good-commit): FOUNDER: ___ s. Set the production gate deadline to about 3x this (`ONEMIND_GATE_TIMEOUT`, os/gate/onemind-health-gate.default): FOUNDER: ___ s
- Bad-k3s decision time (from the gate log): FOUNDER: ___ s
- Rollback rounds passed: FOUNDER: ___ / 10
- Power pulls (lab-kits/common/PP-10.md, during `rauc install good` and the trial boot): bootable after FOUNDER: ___ / 20

## C. Pi 5 4 GB soak (LT-PI5-03)
- `soak-start` ran on: FOUNDER: <date>; ends: FOUNDER: <date>; daily timer enabled: FOUNDER: yes / no (sampled by hand)
- Free memory floor so far (`soak.jsonl`, `mem_available_mib`): FOUNDER: ___ MiB (pass: >= 2048); GB/day written: FOUNDER: ___ (pass: <= 5)

## D. Verdict
- G1: FOUNDER: PASS / FAIL / BLOCKED (reason)
- Consequence applied (22 LT-X86-01 "Fail": a broken k3s committed, or a boot needing a keyboard, re-opens S2): FOUNDER:
- Notes / surprises: FOUNDER:
