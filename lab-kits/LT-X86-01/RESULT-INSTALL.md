<!-- SPDX-License-Identifier: Apache-2.0 -->
# LT-X86-01 install result (copy to research-output/evidence/lab/founder-hardware/LT-X86-01-install.md)

Fill every field. Use placeholders for addresses (`<beelink-ip>`), never the owner token, serial numbers or MAC addresses. Base layout: [../common/RESULT-TEMPLATE.md](../common/RESULT-TEMPLATE.md).

- Date / tester: <date> / founder
- Device: Beelink <model>, BIOS <version>, RAM <GB>, internal disk <type/size> (no serial numbers)
- Firmware settings used: Secure Boot <off>, boot mode <UEFI>, boot menu key that worked <F7/F12/Esc>
- Software: release tag `dev-<date>-<sha>`, installer file `onemind-installer-amd64-<version>.img.xz`, sha256 check <OK/failed>
- Stick written with: <balenaEtcher / dd>
- Criteria: the 8 checks in [INSTALL-BEELINK.md](INSTALL-BEELINK.md) section F, copied before running

| # | Check | Pass / fail / n/a | Note |
|---|---|---|---|
| 1 | Stick verified on the Mac | | |
| 2 | Stick booted, menu shows disks | | |
| 3 | Install wrote and `verified sha256=` | | |
| 4 | Restarted into OneMind alone | | |
| 5 | Owner token shown once | | |
| 6 | Dashboard reachable from the Mac | | |
| 7 | Owner sign-in works, box online as hub | | |
| 8 | Survives a power cycle, same token works | | |

- Result: PASS / FAIL / BLOCKED (<exact reason>)
- Numbers: write time <min>, verify <min>, install reboot to dashboard <min>, free memory after first boot <MiB from the dashboard or `free -h`>
- What differed from the doc (boot key, menu names, screen text, timings):
- Photos kept (names only, not committed if they show addresses):
- Decision consequence applied: <DC / REC / Z id, or "none">
