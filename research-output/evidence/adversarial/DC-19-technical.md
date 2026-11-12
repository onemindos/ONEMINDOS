# DC-19 — Refuter report: the Pi 5 / CM5 pipeline on Debian, technical lens

- **Conclusion under test (qbank W2 Q9, 03):** Umbrel's Pi 5 pipeline (from code) is a Debian trixie rootfs plus Raspberry Pi's own apt repo (archive.raspberrypi.com) for `linux-image-rpi-2712`, `raspi-firmware` and the boot files, with Rugix `rpi-tryboot` slots. Raspberry Pi commits Pi 5 production to at least January 2036. Risk: Freexian ELTS does not cover packages outside the Debian release, so after 2030 the Pi kernel depends on Raspberry Pi Ltd, not on Debian. G2 stays CONDITIONAL for Debian. Partial: the tryboot/EEPROM test is blocked on founder hardware.
- **Flip condition (decision-critical.md):** the Pi 5 path can't be maintained for the support period without carrying a fork.
- **Lens:** technical. I read only the conclusion and its cited claims (C-W2-004, 029, 044, 046). I did not read the author's reasoning or other refuter files first.
- **Date:** 2026-11-11

## Verdict: **weakened**

The pipeline facts hold, and CONDITIONAL is the right grade. But the conclusion puts the risk **after 2030** (the ELTS gap). The evidence shows the risk is present **now**, as kernel cadence and regression exposure:

1. **The Pi kernel does not follow Debian's kernel.** Debian trixie stays on 6.12. Raspberry Pi moved trixie users to 6.18 during 2026 ("Bookworm used 6.12 kernel. Trixie uses 6.18."; C-REF3-DC-technical-024). The Lite tier therefore runs a different major kernel from the amd64 tiers of the same "Debian 13" family, on Raspberry Pi's schedule. There is no published support window for an `rpi-6.x.y` branch.
2. **That cadence ships data-integrity regressions.** rpi 6.18 silently corrupted NVMe reads on SGL-capable drives (fixed in #7500 within a day; C-REF3-DC-technical-021). A device fleet that pins kernels (HAOS 18.1/18.2) shipped the bug to Pi 5/CM5 NVMe users for about two months (C-REF3-DC-technical-022). A later backport (in both 6.18.39 and 6.12.96) made NVMe devices behind a PCIe switch vanish (C-REF3-DC-technical-023).
3. **Holding an older Pi kernel is a fork.** The workaround for #7635 was to stay on 6.12.75. Since 6.12.96 carries the same backport, staying on "the old branch" doesn't escape it.

So "maintainable without a fork" holds only if OneMind tracks Raspberry Pi's kernel closely, **and** qualifies NVMe/HAT storage on each bump. That is ongoing work for a solo developer, starting now rather than in 2030.

## Checks of the cited sources

| Sub-claim | Claim | Result |
|---|---|---|
| ELTS excludes non-Debian packages | C-W2-004 | Holds. Note that the Pi kernel is already outside Debian's security process **today**, not only under ELTS. |
| Pi 5 production to at least 2036-01 | C-W2-029 | Holds, but it is a hardware-production promise, not a software-support promise. |
| Umbrel uses archive.raspberrypi.com kernel + firmware | C-W2-044 | Holds (code). |
| Rugix rpi-tryboot slots | C-W2-046 | Holds (code). The tryboot/EEPROM test is still unrun. |

## Strongest counter-argument

The Lite tier is not "Debian on a Pi". It is **"Raspberry Pi OS's kernel and firmware stream, grafted onto a Debian userspace"**, and the kernel is the component that matters most for security and storage integrity. Raspberry Pi Ltd changes kernel majors mid-release (6.12 → 6.18 in 2026) and states that the only supported upgrade route between OS releases is a reinstall (C-REF3-DC-technical-024). Its kernel team responds quickly (the fix came the next day), but its downstreams inherit regressions just as fast. HAOS, a mature product with a full-time team, still shipped silent NVMe corruption to Pi 5 users for about two months because it pinned a kernel (C-REF3-DC-technical-022). A OneMind box with k3s state, databases and restic repos on NVMe is the exact workload that bug hits. The honest grade for G2 is CONDITIONAL now, not just after 2030. The condition is "a kernel-qualification gate per Raspberry Pi kernel bump, with NVMe soak tests". Ubuntu's certified `linux-raspi` is the obvious comparison: Canonical carries a kernel per LTS with a published lifecycle. That shifts some of the score towards the base with first-class Pi support, which is what DC-19 said could happen.

## New sources (searched for regressions and breakage)

- **N1. raspberrypi/linux #7496 "NVMe storage delivers corrupt data since 6.18"** — https://github.com/raspberrypi/linux/issues/7496 (opened). Opened 2026-07-14: 6.12 and 6.17 are good, and 6.18 corrupts reads on SGL-capable drives. Fixed by PR #7500 and closed 2026-07-15. [C-REF3-DC-technical-021]
- **N2. home-assistant/operating-system #5005** — https://github.com/home-assistant/operating-system/issues/5005 (opened). HAOS 18.1/18.2 pinned an rpi kernel 909 commits behind the fix. Pi 5/CM5 NVMe users saw TimescaleDB "invalid page" errors. It was fixed only in 18.3 (2026-09-17). [C-REF3-DC-technical-022]
- **N3. raspberrypi/linux #7635** — https://github.com/raspberrypi/linux/issues/7635 (opened). An NVMe behind a PCIe switch disappears from 6.18.39 and 6.12.96. The issue is still open, and the maintainer points to upstream. [C-REF3-DC-technical-023]
- **N4. Raspberry Pi forum, "Moving Linux Kernel to 6.18"** — https://forums.raspberrypi.com/viewtopic.php?t=394580&start=150 (opened). Raspberry Pi engineer: "Trixie uses 6.18"; "The only recommended way to upgrade to trixie is a reinstall." [C-REF3-DC-technical-024]
- Context only (search results, not opened in full): raspberrypi/linux #7716 (NVMe "Device not ready" on 6.18.50, good on 6.12.75), and raspberrypi/trixie-feedback #50 (a Pi 5 `apt full-upgrade` left 6.12.62 kernel packages unconfigured when booting from USB SSD; opened, no maintainer reply). The search also surfaced an unverified claim that Raspberry Pi will ship no further 6.12 releases. I could not find it on the pages I opened, so it is not relied on here.

## What would flip the decision

- **Towards the formal flip (needs a fork):** Raspberry Pi stops publishing trixie-compatible kernels and firmware to archive.raspberrypi.com before the declared support end, or a needed fix lands only in a branch that requires a newer Raspberry Pi OS userspace. OneMind would then build `rpi-6.x.y` itself.
- **Towards Ubuntu for the Lite tier:** the founder-hardware test (tryboot + EEPROM + a kernel bump via Rugix) plus a 72 h NVMe soak across two consecutive rpi kernel bumps shows a regression that Ubuntu's `linux-raspi` for the same period did not carry. Or the per-bump qualification costs more than about 1 developer-day a month.
- **Upheld cleanly if:** a pinned-and-qualified pipeline works in practice. That means a CI gate pulling each new `linux-image-rpi-2712`, booting it via tryboot on Pi 5 and CM5 with NVMe, running a checksum soak, and promoting it only on a pass, with Rugix rollback catching any failure. The Pi kernel would then stay a managed dependency rather than a fork.
