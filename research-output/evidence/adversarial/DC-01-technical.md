# DC-01: refuter report on Fedora IoT / bootc vs Debian 13 + Rugix (technical lens)

- **Conclusion under test (decision-critical.md DC-01 rev. 3; 01 §3.1.5, §6.1):** bootc is not the base. It becomes a supported **Industrial profile** (CentOS Stream 10 / AlmaLinux 10 / RHEL image mode, year 2), with **Fedora IoT bootc as a CI canary**. RHEL-family bootc leads S1 on paper (64 vs 62 vs 60) [C-SCORE-025]. Debian wins the three-way tie-break: it draws with bootc 5–5 and takes the draw on the Pi 5 tier. Our lab found greenboot silently downgrading a healthy box after a power cut in finalize [C-LAB-fedora-bootc-011].
- **Flip condition:** bootc/Fedora IoT passes G2 and G3 and beats Debian + Rugix by 3 or more points, robustly. A weaker result adds it as a profile or track.
- **Lens:** technical. I read only the DC-01 conclusion, 01 §3.1.5 and §6.1, and the cited claims (C-SCORE-025, C-LAB-fedora-bootc-011, C-LAB-fedora-bootc-015). I formed this view before reading any other refuter file.
- **Date:** 2026-11-11

## Verdict: **weakened**. "Not the base" holds, but "Fedora IoT as CI canary" rests on a thin upstream, and the 5–5 draw is decided by an argument outside the protocol.

1. **The canary is a small, fragile upstream.** In July 2025 Fedora Quality formally proposed taking away IoT's Edition status. The proposal cited "just two maintainers", "just under 4k" weekly check-ins (the lowest Edition), overlap with CoreOS, and a hardware test matrix QA "rarely actually manage to fill". The proposal was withdrawn, but the facts behind it were not disputed [C-REF4-DC-technical-001]. A canary is only useful if its signal is about bootc/greenboot rather than about Fedora IoT's own release engineering. Fedora IoT's own release engineering broke in November 2026. A Pi that upgraded from F44 to F45 could not upgrade again ("missing public key"), because the ostree remote still pointed `gpgkeypath` at `/etc/pki/rpm-gpg/`. The fix was a manual edit on the device. A maintainer said the file "should have been replaced during the upgrade" and no root cause was confirmed [C-REF4-DC-technical-002]. That is exactly a major-release rebase defect on a Pi, the thing the canary is meant to warn about, and it came from distro packaging, not from bootc. As written, a red canary cannot tell OneMind which of the two it is seeing.
2. **The Industrial profile doubles the base count for a solo founder.** §3.1.5 settles the A-vs-C draw by handing C's wins (IIoT, GPU, rebase) to "the bootc Industrial profile". That counts the profile as an asset in the tie-break while its cost is unpriced. A second base means a second image pipeline, a second update engine (greenboot/bootc instead of RAUC), a second signing chain and a second CVE feed. 01 §6.11 admits the greenhouse SKUs would still need Debian, so OneMind would run two bases.
3. **The 5–5 draw is broken by a tier argument the frozen protocol doesn't contain.** 01 says so openly ("an interpretation of the frozen protocol"). On the technical facts the tie-break is sound: C's Pi 5 route is "experimental" with manual firmware steps [C-SCORE-025], and C silently downgraded a healthy box [C-LAB-fedora-bootc-011]. So the base decision stands. But "Debian is the only finalist no other finalist beats" should read "Debian draws with bootc, and the draw is resolved by an interpretation".

## Strongest counter-argument

In both directions, DC-01's answer is a hedge that buys optionality at a cost the solo founder cannot carry. Take the bootc lineage seriously: it rebased in our lab by design [C-LAB-fedora-bootc-015], it has a 62443-certified sibling, and it led the cited card. Deferring it to "year 2" then means the hard-to-undo choice (disk layout, update engine, signing) is made on Debian + RAUC first, and the Industrial profile arrives later as a second product. Take it lightly instead, as an upstream whose consumer canary has two maintainers and whose IoT Pi upgrade path broke this month. Then the profile and the canary are both commitments OneMind should not make before W2-HW-3. The middle position (profile plus canary) costs the most and settles the least.

## New sources (searched for abandonment, maintainer loss and regressions)

- **N1.** Fedora Discussion, "Proposal: Re-consider Edition status for IoT" (Kamil Páral, 2025-07-29; replies from Adam Williamson, Paul Whalen and Neal Gompa; marked withdrawn). Opened. [C-REF4-DC-technical-001]
- **N2.** fedora-iot/iot-distro issue #143, "Unable to upgrade due to public key not found" (opened 2026-11-06, closed 2026-11-09). Opened. [C-REF4-DC-technical-002]
- Not used: a Fedora Planet digest said bootc and Atomic were moving to a unification effort ("Atomic Fusion"), but the original digest was behind a bot wall and could not be opened. It is not cited.

## What would flip it

- **Toward refuted (bootc should be the base, or the profile should come sooner):** W2-HW-3 passes on a Pi 5 with the AlmaLinux image, greenboot #219 is fixed upstream, and the AlmaLinux RPi images drop the "experimental" label. 01's own re-open conditions then apply.
- **Toward dropping the canary/profile (a stronger weakening):** Fedora IoT loses Edition status or its Pi deliverable, or a second F45/F46 IoT upgrade regression on Pi needs manual intervention. In that case, use a CentOS Stream 10 / AlmaLinux bootc job as the canary instead of Fedora IoT.
- **Toward upheld:** a pinned CI canary that has run for one Fedora cycle, with its failures triaged to bootc/greenboot rather than to Fedora IoT packaging.
