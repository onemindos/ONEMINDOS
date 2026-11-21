# LT-PI5-02 · bootc on a real Raspberry Pi 5 (W2-HW-3), plus the Pi soak start

**Status:** kit-ready (blocked: founder-hardware) · **Time:** about 2 hours on the Pi, plus 10 minutes of waiting · **Decision:** D-013 (Z-10 = a) · **Scored with:** D-012 (Z-40) · **Serves:** DC-01, REC-DEC-33, REC-DEC-44; the Pi soak serves CORE-UPDATE-4 (#215)
**Criteria:** [CRITERIA-22.md](CRITERIA-22.md), copied verbatim from `research-output/22-HARDWARE-LAB-TEST-PLAN.md`. They are not edited here.
**Dates:** run before gate G1 (2026-12-13). The Pi soak must have started by **2026-12-11**.

> **Explain it like I'm the founder.** OneMind ships on Debian 13 (D-007). The one thing that could reopen that choice is a bootc image (the "Red Hat way" of updating a whole OS like a container image) proving it can update and roll back safely on a real Pi 5. You write one of those images to a spare SSD or card, push a deliberately broken update, and watch: does the Pi return to the good image **by itself**, with no keyboard and no manual "commit" command? Then you cut the power in the middle of an update and see whether it still comes back right. A fail confirms Debian. A pass does **not** change anything on its own: it goes back to you, read with four scoring rules that were fixed before the result existed (D-012).

## Do these in order
1. **Gate check (2 minutes).** Open `research-output/evidence/scorecard-weights.md` section 8 and confirm the 2026-11-14 row "founder decision Z-40 (D-012)" exists. The plan says the four rules must be logged before the run; if the row is missing, stop and tell Zeus.
2. **Start the Pi soak first.** It is on the **4 GB** Pi and does not depend on this test, so a slip here must not delay it (deadline 2026-12-11). See "Pi soak" below.
3. **Run the bootc test** on the **16 GB** Pi (D-013), after LT-PI5-01 has used that Pi, with **its own SSD or card**, never the LT-PI5-01 target.
4. **Score and file the result.**

## What you need
- The 16 GB Pi 5, the official 27 W PSU, a spare NVMe SSD (or microSD) as the target, a way to pull power by hand (PP-10: [`../common/PP-10.md`](../common/PP-10.md)), HDMI monitor + keyboard, Ethernet.
- Wipe check before flashing: `sh lab-kits/common/check-target-disk.sh /dev/diskN` (type the size twice).
- A registry you can push to (a private one is fine) for the lab image `<registry>/onemind/lab:aarch64`.
- The Pi's EEPROM boot order must include 6 (NVMe) or 4 (USB), as in LT-PI5-01.

## Steps (22's four steps, with the commands)
**1. Boot a vendor bootc image.** Flash the **AlmaLinux bootc Raspberry Pi image** (the project documents it as experimental, tested on Pi 5 16 GB [C-SCORE-025]) or the Fedora IoT 45 raw image. Boot it, then on the Pi:
```sh
sudo bootc status
sh collect-evidence.sh step1 | sh ../common/redact.sh > step1.txt
```
**2. Switch to the OneMind lab image.** Build the lab Containerfile for aarch64 (greenboot + the k3s health check; the existing x86 build is in `research-output/evidence/lab/w2-fedora-bootc-greenboot/`, run it on an arm64 builder or the R530 worker with `--platform linux/arm64`) and push it. Then:
```sh
sudo bootc switch <registry>/onemind/lab:aarch64 && sudo reboot
# after the reboot:
sudo bootc status; sudo journalctl -u greenboot-healthcheck -b 0 --no-pager | tail
```
PASS: the health check says passed and k3s is active.
**3. A broken update must undo itself.** Push an image whose k3s check fails to the same tag, then:
```sh
sudo bootc upgrade && sudo reboot
```
Now touch **nothing for 10 minutes**: no keyboard, no commands. Afterwards run `collect-evidence.sh step3`. PASS: the Pi is back on the good image and you used no console and no manual commit.
**4. Power pull in the finalize (STEEL4 condition).** As in LT-X86-11 H4 (`research-output/22-...` section on LT-X86-11):
```sh
sudo bootc upgrade        # staged
sudo reboot               # pull the plug 1-2 s after the screen goes dark
```
Power on, run `sudo ostree admin status`, reboot once more, run `collect-evidence.sh step4`. Record: is the version the same after the second reboot, and did the commit happen **automatically**? Stock greenboot 0.16.4/0.16.5 is expected to fail this (a silent downgrade, #219 [C-LAB-fedora-bootc-011, C-LAB-fedora-bootc-013]). Record the greenboot version and whether #219 is fixed in it.

## Score it
```sh
python3 -I lab-kits/LT-PI5-02/score.py --template > result.json     # fill the five fields from your notes
python3 -I lab-kits/LT-PI5-02/score.py result.json
```
Exit 0 = scored, 1 = a field is still `null`, 2 = unreadable file. The script only applies the map that research wrote on 2026-11-11, before any result existed:

| Observation | Outcome | What it means |
|---|---|---|
| Step 3 fails, or a console or manual commit was needed | **FAIL** | bootc's Pi 5 cell drops; D-007 confirmed; bootc stays the year-2 Industrial profile |
| Pass, but #219 open or the commit was manual / a silent downgrade | **PASS (open)** | no cell moves; Debian stays; whether it reopens D-007 is Zeus's call |
| Pass, #219 fixed and the commit was automatic | **PASS (fixed)** | D-007's reopen condition is met; the rows are re-counted bootc vs Ubuntu (6-4, or a 4-4 draw goes to Zeus) |

**The four D-012 rules the reading uses:** (1) the tie-break counts rows across the full table and a draw returns to Zeus; (2) "experimental" support with a documented path scored 3 (`doc-only`) until this test measures it; (3) "proven in production" (C4) is scored on the base layer; (4) no third candidate may enter a tie. The kit never decides the base OS. Never run any OTP or key-programming command (SB-8).

## Pi soak (the 4 GB Pi, LT-PI5-03, start by 2026-12-11)
The 30-day memory and write-wear record is started by the G1 kit, on the 4 GB Pi with NVMe and the hardened k3s config:
```sh
python3 -I lab-kits/G1/g1-run.py soak-start --disk nvme0n1     # baseline, soak-start.json, daily timer
python3 -I lab-kits/G1/g1-run.py soak-sample                   # one extra sample by hand
```
Details and the pass rule (at least 2.0 GiB free over 30 days, at most 5 GB/day written) are in [`../G1/README.md`](../G1/README.md) "Soak start". This kit adds only the dates: start by **2026-12-11**, day 30 is start + 30 days (2027-01-10 if started on the deadline), and the start is one line in the result template. Do not run the bootc test on the soak Pi.

## Record and wipe
Fill [RESULT.template.md](RESULT.template.md) and file it as `research-output/evidence/lab/founder-hardware/LT-PI5-02.md` (everything through `redact.sh`). Wipe the target disk afterwards (`diskutil eraseDisk` or `sudo wipefs -a`).

## UNVERIFIED (confirm on the first real run)
- That the AlmaLinux bootc image's firmware path and the lab Containerfile's greenboot k3s check work on aarch64: the lab ran on x86 (`w2-fedora-bootc-greenboot`); only the AlmaLinux README (C-SCORE-025) says Pi 5 images exist.
- `collect-evidence.sh` has only been shellchecked, not run on a Pi; `rpm`, `rpi-eeprom-update` and `ostree` may be missing on some images (it prints a note and carries on).
- The Pi soak timer on a read-only root (see the G1 kit's own UNVERIFIED list).
