# LT-PI5-02 result (bootc on a real Raspberry Pi 5, D-013 / Z-10)
File as `research-output/evidence/lab/founder-hardware/LT-PI5-02.md`. Pipe every pasted log through `sh lab-kits/common/redact.sh`. No serial numbers, MACs, IPs, host names or home paths.

- Date / tester: <date> / founder
- Device: Raspberry Pi 5 16 GB, EEPROM bootloader <version from rpi-eeprom-update>, target disk <NVMe or card, size>
- Image: <AlmaLinux bootc RPi image version, or Fedora IoT 45 raw> · bootc <version> · greenboot <version> · k3s <version>
- Lab image ref: <registry>/onemind/lab:aarch64 (digest <sha256>)
- D-012 logged in `research-output/evidence/scorecard-weights.md` section 8 before this run: yes / no (STOP if no) · date of that entry: <date>
- Criteria: copied from [CRITERIA-22.md](CRITERIA-22.md) before running, unchanged: yes / no

## Steps (paste redacted evidence under each)
| Step | What you did | Expected | Observed | OK |
|---|---|---|---|---|
| 1 | flash, boot, `sudo bootc status` | booted image is the vendor image | | |
| 2 | `bootc switch <registry>/onemind/lab:aarch64`, reboot | health check passed | | |
| 3 | push broken image (k3s fails), `bootc upgrade`, reboot, touch nothing 10 min | back on the good image, no console, no manual commit | | |
| 4 | pull power during the staged update's finalize (as LT-X86-11 H4); power on; reboot again | same good version after the second reboot; note whether the commit was automatic | | |

## Scoring (fill result.json, then `python3 -I lab-kits/LT-PI5-02/score.py result.json`)
- h1_booted_and_healthy: 
- bad_image_auto_rollback: 
- console_or_manual_step_used: 
- power_pull_commit (automatic / manual / silent-downgrade): 
- greenboot_219_fixed (version used: <version>): 
- Scorer output (paste): 

## Pi soak (4 GB Pi, LT-PI5-03; started by 2026-12-11)
- Soak start date: <date> (deadline 2026-12-11) · `soak-start.json` present: yes / no · timer active: yes / no
- First sample: MemAvailable <MiB>, written <MiB>, NVMe wear <%>
- Day-30 date: <start + 30 days> · result to be filed separately as LT-PI5-03

## Result: PASS / FAIL / BLOCKED (<exact reason>)
- Notes / surprises:
- Decision consequence applied: none until Zeus decides (D-007 stays Debian 13). Recommended: <read from scorer>
- Left unwiped target disk? no (wipe it, 22 section 2.3 rule 3)
