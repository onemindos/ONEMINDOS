# Sources · FIX4 (critic pass-4 gaps P4-1 and P4-2)

**Agent:** FIX4 · **Accessed:** 2026-11-11 · **Claims:** [`../claims/FIX4.csv`](../claims/FIX4.csv) (C-FIX4-001…015) · **Archive:** [`FIX4/`](FIX4/) with [`FIX4/SHA256SUMS`](FIX4/SHA256SUMS)

**Access note.** From this session, `ubuntu.com`, `launchpad.net`, `bugs.launchpad.net`, `git.launchpad.net`, `discourse.ubuntu.com`, `documentation.ubuntu.com` and `packages.ubuntu.com` did not resolve (DNS failure), and `web.archive.org` was refused by the fetch tool. Canonical's web pages were therefore read from the **source of the ubuntu.com website** on GitHub (`canonical/ubuntu.com`, pinned commit below), which is what ubuntu.com renders. Launchpad facts already in the ledger (for example C-DEC-006, linux-raspi bug #2170238) could **not be re-checked** and are cited as they stand. Nothing was bypassed.

| # | Source | Type | Opened how | Archive (sha256 in `FIX4/SHA256SUMS`) | Claims |
|---|---|---|---|---|---|
| 1 | `canonical/ubuntu.com@ec15716b1c4b95f1860672d4274dda730ee9b4fe:templates/pricing/devices.html` (IoT and device services pricing, incl. Ubuntu Pro for devices and certification terms) | PRIMARY | sparse clone in `<lab-dir>/src/` | `01-ubuntu.com-pricing-devices.txt` | C-FIX4-001, 002 |
| 2 | `canonical/ubuntu.com@ec15716…:templates/pro/devices.html` (Ubuntu Pro for Devices) | PRIMARY | same | `01-ubuntu.com-pro-devices.txt` | C-FIX4-003 |
| 3 | `canonical/ubuntu.com@ec15716…:templates/pricing/pro.html` (Ubuntu Pro list prices) | PRIMARY | same | `01-ubuntu.com-pricing-pro.txt` | C-FIX4-004 |
| 4 | `canonical/ubuntu.com@ec15716…:templates/download/raspberry-pi/index.html` (Pi download page, certification table, EEPROM note) | PRIMARY | same | `01-ubuntu.com-download-raspberry-pi-index.txt` | C-FIX4-005 |
| 5 | https://forums.raspberrypi.com/viewtopic.php?t=398535 "Update Ubuntu and EEPROM" (2026-05-22) | SECONDARY (forum; vendor-staff reply) | fetch tool | `04-forums-raspberrypi-t398535-extract.txt` (quoted extract) | C-FIX4-006 |
| 6 | https://github.com/raspberrypi/rpi-eeprom/issues/776 (Pi 5 EEPROM 2025-11-05 USB boot regression, fixed 2025-12-18) | PRIMARY (upstream tracker) | `gh api` | `02-rpi-eeprom-issue-776.txt` (commenter handles masked) | C-FIX4-007 |
| 7 | https://github.com/uutils/coreutils/issues/15768 (`timeout -k` does not kill the process group; open) | PRIMARY (upstream tracker) | `gh api` | `03-uutils-coreutils-issue-15768.txt` | C-FIX4-008 |
| 8 | https://github.com/uutils/coreutils/issues/15254 (~180 GNU vs uutils differences; open) | SECONDARY (user report, AI-written) | `gh api` | `03-uutils-coreutils-issue-15254.txt` (third-party home paths masked) | C-FIX4-009 |
| 9 | This repo, `evidence/lab/ubuntu-2604-leg/versions.md` L20–L23 and `ubuntu-observations-u2.txt` L17–L23 @ `7836316` | PRIMARY (own lab) | git | in repo | C-FIX4-010, 011 |
| 10 | https://computingforgeeks.com/ubuntu-2604-dracut-guide/ (updated 2026-05-08) | SECONDARY (third-party guide) | fetch tool | `06-computingforgeeks-ubuntu-2604-dracut-extract.txt` | C-FIX4-012 |
| 11 | https://lwn.net/Articles/586446/ (2014-02-14, Community Council statement on Canonical package licensing) | SECONDARY (news) | fetch tool | `05-lwn-586446-extract.txt` | C-FIX4-013 |
| 12 | This repo, `evidence/scorecard-weights.md` L106 and L159 @ `7836316` | PRIMARY | git | in repo | C-FIX4-014 |
| 13 | `torvalds/linux@028ef9c96e96197026887c0f092424679298aae8:COPYING` (tag v7.0, 2026-04-12) | PRIMARY | `gh api` | not archived (stable permalink) | C-FIX4-015 |

**Searched but not used** (failure-seeking searches with no openable primary result): "Ubuntu 26.04 systemd-boot UKI secure boot custom keys" (only third-party blogs; Ubuntu docs unreachable); "Ubuntu 26.04 dracut … TPM full disk encryption boot failure" (Discourse threads unreachable); "Linux Mint licence agreement with Canonical" (LWN 651089 and 586677 opened, but they hold only reader comments, so they are not cited).
