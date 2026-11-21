<!-- Copied verbatim from research-output/22-HARDWARE-LAB-TEST-PLAN.md (LT-PI5-02, section starting at line 338), 2026-11-21. Do not edit: if 22 changes, re-copy. -->

### LT-PI5-02 · bootc on a real Pi 5 · **G** · **run before gate G1 (week 4)**
**Aliases:** W2-HW-3, DC-01 founder test, REC-DEC-33, REC-DEC-44 · **Prerequisite:** a spare SSD or card; the lab Containerfile rebuilt for aarch64; **Z-39 and Z-40 logged** in `scorecard-weights.md` §8 before the run (`26-…`)
1. Write the **AlmaLinux bootc Raspberry Pi image** (documented as experimental [C-SCORE-025]) or the Fedora IoT 45 raw image; boot; `sudo bootc status`.
2. `sudo bootc switch <registry>/onemind/lab:aarch64` (the lab Containerfile with greenboot + k3s check); reboot; confirm healthy.
3. Push a broken image (k3s fails) and `sudo bootc upgrade && sudo reboot`; touch nothing for 10 minutes.
4. **(STEEL4 conditions)** Pull the power during the staged update's finalize, as in LT-X86-11 H4, and record whether the Pi commit happens automatically after a power pull.
- **Pass:** automatic return to the good image **with no console and no manual commit step**. Record whether greenboot #219 is fixed in the version used [C-STEEL4-bootc-024].
- **Consequence (the pre-registered map, `01` §3.1.6 h, written 2026-11-11):** **Fail** → bootc's Pi 5 cell drops (C·C2 3 → 2) and the S1 result becomes **Debian 13** (Ubuntu 65 · Debian 63 · bootc 60; Debian wins the tie-break 6–5) [C-DEC4-007]; bootc stays the Industrial profile only (REC-DEC-04). **Pass with #219 open or a manual commit step** → no cell or row moves; S1 stays Ubuntu 26.04. **Pass with #219 fixed and an automatic commit** → the DC-19 and lab rows are re-counted for Ubuntu vs bootc: bootc wins 6–4, or a 4–4 draw goes to Zeus under Z-40.

