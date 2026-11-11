# S1R5 · Rev-4 S1 decision of record (Ubuntu 26.04 + RAUC) · longevity / vendor refuter

**Lens:** longevity and vendor risk · **Date:** 2026-11-11 · **Refuter round:** 5 (critic pass-4 gap P4-1)
**Target:** `01-FOUNDATION-DECISION.md` §3.1.6 (c)–(h): Ubuntu 26.04 + RAUC (D) is the frozen-protocol S1 result, D 65 · C 64 · A 63, tie-break 6–4 over bootc, with the pre-registered decision map.
**Read:** §3.1.6 (c)–(h), frozen `scorecard-weights.md` §2–§6, and the cited rows C-W2-005/006/050/057, C-DEC-006, C-DEC4-007, C-LIC-011, C-REF-W2-robotics-004.
**Independence limit:** written sequentially by the same agent as the other two S1R5 files, after it had read 01 (see the [technical file](FIX4-S1R5-technical.md) header).
**New sources:** C-FIX4-001, 002, 005, 006, 007, 008, 009 (`sources/FIX4.md`).

> **Explain it like I'm the founder.** Picking Ubuntu means betting on Canonical for ten years, on every box. Three things make that bet shakier than the scorecard shows. First, on the Pi 5, a new Ubuntu release can refuse to install until the Pi's own firmware chip is updated, and Raspberry Pi's suggested fix needs a spare SD card. Second, Ubuntu 26.04 has replaced its basic command-line tools with a new Rust version that still behaves differently in places. OneMind will undo that, and every such change makes the image "modified Ubuntu", which needs Canonical's permission. Third, Canonical certifies devices only if they run a Canonical kernel. Our Secure Boot plan may need our own kernel. None of this beats Ubuntu outright, but it moves weight toward the question Canonical has not answered yet.

---

## 1. Verdict: **weakened**

The ten-year horizon is real with money: 26.04 gets security maintenance to May 2036 with Ubuntu Pro, and Legacy to 2041 [C-W2-005], and Pro for Devices can be bought "for a one-time fee per device, covering security maintenance for its entire lifecycle" [C-FIX4-003]. But three long-run dependencies are missing from both the C1 cell and the decision map.

## 2. Strongest counter-argument

**2.1 On the Pi 5, Ubuntu ties the OS release to a firmware floor, and fielded boxes must clear it.** Canonical's own Pi page says "Certain releases of Ubuntu require a minimum EEPROM date for compatibility for the Raspberry Pi 4 and 5" [C-FIX4-005]. For 26.04, the release upgrader blocks a Pi 5 whose EEPROM is older than 2025-02-11. The Raspberry Pi engineer's answer is to reflash the bootloader "using a spare sdcard and rpi imager" [C-FIX4-006, SECONDARY]. The open linux-raspi boot bug for older EEPROMs is the same constraint seen from the kernel side [C-DEC-006]. In a fleet, each Ubuntu LTS rebase (26.04 → 28.04 → 30.04 before 2036) can raise this floor. OneMind then has to push EEPROM updates in-band, inside the A/B bundle, before the OS can move. EEPROM updates have their own regressions: the 2025-11-05 Pi 5 EEPROM broke USB boot with two drives attached until a fix six weeks later [C-FIX4-007]. Debian on the Pi 5 also depends on Raspberry Pi's EEPROM. But Ubuntu turns the firmware date into a hard gate set by a second vendor's release.

**2.2 Ubuntu changes core userland inside an LTS. Undoing that makes the image "modified".** 26.04 ships uutils (rust-coreutils 0.10.0) as `coreutils` [C-FIX4-010]. Upstream has open divergences: `timeout -k` does not kill the process group [C-FIX4-008], and a differential fuzzer reports about 180 behaviour differences from GNU [C-FIX4-009, SECONDARY]. The 25.10 rust-coreutils bug that silently stopped unattended upgrades shows how such differences surface [C-REF-W2-robotics-004]. 01 plans to pin GNU coreutils on Ubuntu. Every such deviation is a modification under Canonical's policy, which allows redistribution only "where there has been no modification" [C-LIC-011]. So the safer OneMind makes Ubuntu, the more D depends on Z-01. Over ten years Canonical will make more swaps like this (sudo-rs, Rust coreutils), and each one is either accepted unaudited or reverted, which deepens the modification.

**2.3 Certification and the kernel route may pull apart.** Canonical's device terms say "Certified devices must run a Canonical kernel" and need four test units per board [C-FIX4-002]. 01 keeps K2-hybrid (a OneMind-built kernel) as the fallback for the Secure Boot release if the shim route fails (T-W19-03). If Canonical ties trademark use or Pro coverage to certified or Canonical kernels, D loses that fallback on x86 and generic arm64. Debian and AlmaLinux impose no such tie. Nothing in the opened sources says the trademark grant is tied to certification. This is a question to put to Canonical, not a fact.

**2.4 Two Canonical releases, two vendors, one condition.** The Jetson flavor stays on NVIDIA's Ubuntu 24.04 while the core moves to 26.04. That is known (S1-6, G5 COND) and is the same for A, C and D. But under D, a single Canonical answer (Z-01) gates both the core and Jetson. Under A or C, a Canonical refusal costs only the Jetson flavor. The decision map captures the refusal case. It does not capture "granted for the core but only with Pro for Devices on every box", which is the cost refuter's subject.

## 3. Where the counter-argument is weaker (fair limits)
- The EEPROM dependency exists for **every** base on the Pi 5, and 01's E10 already pins, gates and records EEPROM versions in the release pipeline. Ubuntu adds a vendor-set floor, not a new kind of work.
- Pinning GNU coreutils is a small, auditable change, the kind Canonical's derivative policy is meant to license.
- Canonical has supported Ubuntu on the Pi since 20.04, and the Pi 5 is "Yes, certified" for 26.04 [C-FIX4-005]. That is more vendor commitment than bootc's experimental Pi 5 images [C-SCORE-025].

## 4. What would flip it
- **To refuted:** Canonical's written terms make trademark use or Pro for Devices conditional on a Canonical-certified kernel, **and** T-W19-03 finds no shim route on the stock Ubuntu kernel. The Secure Boot release then has no viable kernel on D. Or the next Ubuntu LTS requires an EEPROM floor that some shipped Pi 5 units cannot reach in-band.
- **To upheld:** Canonical's answer to Z-01 states that trademark use covers a OneMind-modified image (package swaps such as GNU coreutils) with any kernel; and a fleet-safe in-band EEPROM update is shown in LT-PI5-01.
- **Required now:** add the kernel-tie question to the Canonical outreach (Z-01), and record in 01 that each Ubuntu-specific deviation counts toward G1.

## 5. New sources (opened 2026-11-11)
- ubuntu.com source, IoT/device pricing and certification terms @ `ec15716`. [C-FIX4-001, C-FIX4-002]
- ubuntu.com source, Raspberry Pi download page @ `ec15716` (Pi 5 certified; EEPROM floor). [C-FIX4-005]
- Raspberry Pi forum t=398535, the 26.04 upgrader's EEPROM block (SECONDARY). [C-FIX4-006]
- raspberrypi/rpi-eeprom #776, Pi 5 EEPROM regression and fix. [C-FIX4-007]
- uutils/coreutils #15768 and #15254. [C-FIX4-008, C-FIX4-009]
