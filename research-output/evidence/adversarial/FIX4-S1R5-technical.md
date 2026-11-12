# S1R5 · Rev-4 S1 decision of record (Ubuntu 26.04 + RAUC) · technical and security refuter

**Lens:** technical, including the security cell C3 · **Date:** 2026-11-11 · **Refuter round:** 5 (critic pass-4 gap P4-1; RESEARCH-MISSION.md §2 rule 7)
**Target:** `01-FOUNDATION-DECISION.md` §3.1.6 (c)–(h): "Under the frozen protocol, D (Ubuntu 26.04 + RAUC A/B) 65.0 ties C (RHEL-family bootc) 64.0 and wins the top-two tie-break 6–4; the decision map pre-registers the outcomes of W2-HW-3 and Z-01."
**Read:** §3.1.6 (c)–(h) only, the frozen `scorecard-weights.md` (§2–§6, §8), and the rows those sections cite (C-DEC4-001…009, C-LAB-secureboot-rauc-012…015, C-LAB-secureboot-1152-005/006, C-LAB-ubuntu-2604-leg-003/010/011, C-W2-005/050/057, C-DEC-006, C-SCORE-025).
**Independence limit (disclosed):** this session cannot start sub-agents, so the three S1R5 refuters (this file, [longevity](FIX4-S1R5-longevity.md), [cost](FIX4-S1R5-cost.md)) were written one after another by the same agent (FIX4), which had already read 01's reasoning to find the gap. Each file was argued from its own lens and its own new sources, but none is blind in the sense rule 7 intends. The mission allows sequential refuters when the platform cannot run them in parallel; the lack of blindness is a real weakness, recorded in 01 §5.1.2 and §12.
**New sources:** `claims/FIX4.csv` C-FIX4-008, 010, 011, 012, 014 (sources in `sources/FIX4.md`).

> **Explain it like I'm the founder.** Ubuntu beat bootc by one point. That point comes from one cell: Ubuntu's "security and update safety" score was raised from 3 to 4 because our Secure Boot lab passed. But that lab ran **Debian**, not Ubuntu. The rules let a cell be scored from documents when the *hardware* is missing. Here no hardware is missing: the Ubuntu test runs in the same virtual machine as the Debian one. And we already know Debian and Ubuntu are not interchangeable underneath RAUC. Ubuntu's newer kernel broke Debian's RAUC once. Ubuntu 26.04 also changes the start-up program that unlocks the disk, the system manager version, and the basic command-line tools. If that cell stays at 3 until an Ubuntu test passes, **bootc wins** instead. So the decision is honest, but it hangs on a test we can run in a day or two, without buying anything. It should be written into the decision map now.

---

## 1. Verdict: **weakened**

The protocol steps in §3.1.6 are applied correctly. The totals reproduce (D 65 · C 64 · A 63 [C-DEC4-001]), only the top two are compared, and COND stays ranked. But the winner rests on **one cell, D·C3 = 4**, whose only test evidence comes from another base. If that cell is held at 3, which §3.1.6 (g) already lists as V3, the frozen-protocol result is **C (bootc)**, in 11 of 14 runs [C-DEC4-007]. The decision is not refuted, because the anchor text can be read to allow 4. But it must not be presented without a pre-registered Ubuntu Secure Boot leg.

## 2. Strongest counter-argument

### 2.1 `doc-only` is used outside the rule that allows it
Anchor 4 is a documentation anchor: "a documented Secure Boot / measured boot / TPM path that does not need a partition or bootloader change later" [C-FIX4-014]. A lab is not required. But §3.1.6 marks D·C3 `doc-only`, and frozen §5 rule 5 allows `doc-only` only "where hardware is unavailable (`blocked: founder-hardware`)" [C-FIX4-014]. No hardware is missing for an x86 Secure Boot leg. Both earlier Secure Boot labs ran in QEMU with OVMF and swtpm [C-LAB-secureboot-1152-005]. The honest label is "documented in RAUC's base-neutral docs; tested on Debian only; the Ubuntu leg has not run" [C-DEC4-004]. When a test is cheap and has not run, the frozen §4 rule ("between two anchors, give the lower") points to 3, not 4.

### 2.2 "The same route on any base" has already failed once on exactly this pair
S1-12 says the RAUC `efi` route "meets [anchor 4] the same way on any base". This run's own lab disproves the general form of that claim for Debian → Ubuntu. Debian's RAUC 1.13 cannot install **any** bundle on Ubuntu 26.04's 7.0 kernel, because of a dm-verity status change in Linux 6.19 [C-LAB-ubuntu-2604-leg-003, C-LAB-ubuntu-2604-leg-010]. OneMind ships its own RAUC 1.15.x, so that particular break is fixed. The point is the class of risk: the layers below RAUC differ, and they have broken RAUC before.

### 2.3 The Secure Boot chain touches exactly the layers Ubuntu 26.04 changes
The passed Secure Boot battery depends on these parts: UKIs built with `ukify` and signed with `sbsign`, RAUC's `efi` backend writing `BootNext` and `BootOrder`, a systemd initrd that unlocks LUKS2 with TPM2 bound to PCR 7 (plus the signed PCR 11 bonus), and a time-boxed health gate [C-LAB-secureboot-1152-005, C-LAB-secureboot-1152-006]. In both runs, every one of those parts came from **Debian 13** (systemd/ukify 257.13 [C-DEC4-004]). On Ubuntu 26.04:
- **systemd is 259**, not 257 [C-FIX4-010]. The initrd unlock, `systemd-cryptenroll` policies and `ukify` all live in systemd.
- **The default initramfs generator is dracut.** The kernel package names dracut as its first choice [C-FIX4-011], and a third-party guide says 26.04 is the first Ubuntu whose on-disk initramfs is built by dracut, with Ubuntu's TPM-backed FDE built on it [C-FIX4-012, SECONDARY]. Our Ubuntu lab leg sidestepped this by naming initramfs-tools explicitly [C-FIX4-010]. So no Ubuntu image in this run has used Ubuntu's own default early-boot path.
- **Our Ubuntu leg never used RAUC's `efi` backend at all.** It booted through GRUB (`grub-mkstandalone` / `grub-editenv`) [C-FIX4-010]. The k3s battery it passed [C-LAB-ubuntu-2604-leg-011] says nothing about UKIs, `BootNext` or TPM unlock on Ubuntu.
- **Default coreutils is uutils** (rust-coreutils 0.10.0) [C-FIX4-010]. Upstream has an open bug: `timeout -s KILL` and `timeout -k` do not kill the whole process group [C-FIX4-008]. A deadline-driven health gate that runs helpers under `timeout` can then hang past its deadline. 01 already says the image pins GNU coreutils on any Ubuntu leg. That fixes the gate, but it is one more Ubuntu-only change that no lab has exercised.

None of these is a known failure. Each is an untested difference on the path that anchor 4 is about. Rule 6 requires the same evidence for every candidate. A·C3 = 4 has two passing labs on its own base, and D·C3 = 4 has none on its base. That is not the same evidence.

### 2.4 The rest of the D–C margin is thin too
- The D–C tie-break is 6–4. Counting only DC rows plus the G1 row, it is **4–4**, and the frozen text has no draw rule (§3.1.6 f).
- The "Lab: D" row for D vs C rests on the k3s battery. Ubuntu's leg did not include the Secure Boot battery that bootc's stack was also never put through, so that row compares two incomplete test sets.
- The new "signed GPU modules" row is ≈ for D–C, and each side of it rests on an inference (Ubuntu's restricted modules being signed [C-STEEL-ubu-016]; Red Hat signing only on paid RHEL [C-REF4-S1R4-security-007]). It does not move D–C. It does show that the security rows lean on inferences.

## 3. Where the counter-argument is weaker (fair limits)
- **Anchor 4 really is a documentation anchor.** RAUC's `efi` backend and UKIs are upstream features, and nothing in them is Debian-specific. A strict reader can keep 4 on the text alone.
- **S1-12 applied the same reading to G (Yocto) and F (Buildroot)**, neither of which ran the Secure Boot lab. Dropping D alone to 3 would itself break rule 6. The symmetric fix (hold every RAUC stack without its own Secure Boot leg at 3) moves D, G and F together. It still gives V3's result for the top three, because G and F are far behind.
- **The differences in §2.3 are risks, not failures.** systemd 259 and dracut both support TPM2 unlock and UKIs upstream. The most likely outcome of an Ubuntu Secure Boot leg is a pass.

## 4. What would flip it
- **To refuted:** an Ubuntu 26.04 Secure Boot leg (the X-2R/1152 battery with Ubuntu's kernel, systemd 259, Ubuntu's default initramfs generator, OneMind's RAUC 1.15.x `efi` backend and signed UKIs) **fails**, or passes only after a partition or bootloader change. D·C3 then = 3 → V3 → **C (bootc)**, by the frozen rules (C 64 · A 63 · D 62; C 11 of 14 runs) [C-DEC4-007].
- **To upheld:** that leg passes unchanged, in two runs, with the same pre-registered pass criteria as `lab/secureboot-1152`. D·C3 = 4 then has evidence equal to A's, and the `doc-only` label can be dropped.
- **Required now (no test needed):** add the Ubuntu Secure Boot leg to the 01 §3.1.6 (h) decision map, and log that row in `scorecard-weights.md` §8 **before** the leg runs. It is VM-only, so it belongs before gate G1 next to W2-HW-3. Until it runs, report the result as "D, contingent on D·C3 = 4; V3 gives C".

## 5. New sources (opened 2026-11-11)
- uutils/coreutils #15768, `timeout -k` / `-s KILL` process-group bug (open). https://github.com/uutils/coreutils/issues/15768 [C-FIX4-008]
- This repo's Ubuntu lab versions and package observations @ `7836316` (systemd 259, GRUB boot, initramfs-tools named, uutils coreutils; dracut first in the kernel's Recommends). [C-FIX4-010, C-FIX4-011]
- computingforgeeks, "Configure Dracut on Ubuntu 26.04" (2026-05-08), SECONDARY. https://computingforgeeks.com/ubuntu-2604-dracut-guide/ [C-FIX4-012]
- Frozen anchor and rule text @ `7836316`. [C-FIX4-014]
