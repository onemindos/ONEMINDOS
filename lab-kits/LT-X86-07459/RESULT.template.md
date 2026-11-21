<!-- SPDX-License-Identifier: Apache-2.0 -->
# LT-X86-07459 result (Dell Inspiron 7459 all-in-one, daily hub)

Everything about this model is UNVERIFIED until filled in. Use placeholders for addresses (`<dell-ip>`); never the owner token, serial numbers or MAC addresses. Base layout: [../common/RESULT-TEMPLATE.md](../common/RESULT-TEMPLATE.md).

- Date / tester: <date> / founder
- Device: Dell Inspiron 7459 all-in-one, BIOS <version>, RAM <GB> (expected 16), CPU <model> (expected i7-6700HQ), discrete graphics <yes/no>, internal disk <SSD/HDD, size> (fitted SSD? <yes/no>)
- CPU model and x86-64 level (from precheck.txt): <model>, v<2|3>
- Firmware: boot mode <UEFI>, Secure Boot <off>, SATA mode <AHCI>, TPM <present/none>, keys that worked <F2/F12/other>
- Software: release tag `dev-<date>-<sha>`, installer `onemind-installer-amd64-<version>.img.xz`, sha256 <OK/failed>
- Worker: Debian 13 VM on the lab server, vCPU <n>, RAM <GB>, joined with <install.sh --join>
- Criteria: the 9 checks in [README.md](README.md) section 5, copied before running

| # | Check | Pass / fail / n/a | Note |
|---|---|---|---|
| 1 | Pre-install check | | |
| 2 | Stick verified, booted, install wrote and checked | | |
| 3 | Restart into OneMind alone | | |
| 4 | Owner token shown once | | |
| 5 | Local screen: running, address, QR, no token | | |
| 6 | Dashboard from the Mac, sign-in, role hub | | |
| 7 | Worker joined only after approval | | |
| 8 | Power cycle: same token, worker back | | |
| 9 | More than 8 GiB memory available | | |

- Result: PASS / FAIL / BLOCKED (<exact reason>)
- Numbers: install write time <min>, reboot to dashboard <min>, memory available <GiB>, join to Nodes <min>
- Local screen: address printed vs address that worked from the phone/Mac (for #242):
- What differed from the doc (keys, menu names, screen text, timings):
- Decision consequence applied: <DC / REC / Z id, or "none">
