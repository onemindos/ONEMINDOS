# DC-06: refuter report on Rugix's bus factor, maturity and exit plan (technical lens)

- **Conclusion under test (decision-critical.md DC-06 rev. 3; 01 §3.2, §6.7):** Rugix's bus factor is about one (303 of 304 commits in a year) [C-W3-001]. The flip to RAUC is taken. Rugix stays the documented alternative and is the only Debian A/B precedent besides Mender (umbrelOS). Status: answered.
- **Flip condition:** a single-maintainer bus factor **with no second adopter**, while RAUC is comparable on features. The likely flip is D3 → RAUC.
- **Lens:** technical. I read only the conclusion, 01 §3.2 and §6.7, and C-W3-001. I formed this view before reading any other refuter file.
- **Date:** 2026-11-11

## Verdict: **upheld**, with two wording corrections

1. **The bus-factor fact reproduces.** I re-ran the GitHub API query on 2026-11-11. rugix/rugix has 304 commits since 2025-11-11, and 303 are by the lead maintainer [C-REF4-DC-technical-012]. Silitics' published open-source commitment promises to keep the MIT/Apache-2.0 licences and "not degrade Rugix functionality". It says nothing about continuity, succession or escrow, and Rugix is funded by one owner-led company's consulting work and its Nexigon product [C-REF4-DC-technical-013]. A ten-year engine choice should not rest on that.
2. **Correction 1: as written, the flip condition is not literally met.** It requires "no second adopter". 01 §6.7 itself records an independent IIoT adopter (thin-edge.io/Cumulocity, meta-tedge), plus RevPi and Strato Pi examples. The move to RAUC is justified by the S2 scorecard (RAUC 61.0 vs Rugix 52.0, outside the tie band) together with the bus factor, not by DC-06's condition alone. The answer should say so, so that a later "Rugix gains adopters" does not look like a re-open trigger when it isn't one.
3. **Correction 2: RAUC's bus factor is about two, from one company, and its releases are slower.** Since 2025-11-11, rauc/rauc has had 511 commits. Two Pengutronix engineers wrote 441 of the 484 human commits (about 91%; 286 + 155), and Dependabot wrote 27 [C-REF4-DC-technical-009]. The latest release is v1.15.2 (2026-03-27). Nearly eight months later, 1.16 is still unreleased, with "preview level" features [C-REF4-DC-technical-010]. RAUC does deliver fixes that OneMind depends on: 1.15.1 (2026-01-05) fixed the Linux 6.19 dm-verity status change [C-REF4-DC-technical-011]. So "Mender ≥ RAUC > Rugix" is right, but RAUC's gap over Rugix comes from employer backing and a ten-year record, not from many maintainers.

## Strongest counter-argument

The flip swaps a known single-person risk for an untested integration risk. Rugix is the engine with a **shipped** Debian A/B appliance on Pi 5 and x86, and it passed OneMind's own lab on both architectures with a real k3s gate. RAUC has no Debian or Ubuntu product anywhere (C-DEC-013, cited in 01). Its Pi 5 tryboot path is desk-checked only, and Debian's own RAUC package cannot install on a ≥ 6.19 kernel, so OneMind must build and carry RAUC itself. Effectively, OneMind becomes the RAUC-on-Debian integrator of record, a bus factor of one on OneMind's side, in order to avoid a bus factor of one on Silitics' side. Rugix is also small enough (about 47k lines of permissively licensed Rust, per 01 §6.7) to fork. The counter does not overturn the flip, for two reasons. RAUC's maintainers are two employees of an established embedded-Linux firm with a ten-year record and large adopters. And Rugix's own field record has an unanswered, user-visible defect: umbrel #2153, where the update hangs because `rugix-ctrl` cannot find `sfdisk`, has been open since May and reproduced on umbrelOS 2.0.1 [C-REF4-DC-technical-008]. It sits in the integrator's PATH handling, not in Rugix itself, but it shows how thin the support around that precedent is.

## New sources (searched for maintainer concentration, release stalls and support gaps)

- **N1.** GitHub API, rauc/rauc commits since 2025-11-11 and the releases list (queried 2026-11-11). [C-REF4-DC-technical-009, C-REF4-DC-technical-010]
- **N2.** rauc/rauc `CHANGES` on master (1.16 unreleased; 1.15.1 dm-verity fix). Opened. [C-REF4-DC-technical-011]
- **N3.** rugix.org "Commitment to Open Source" (no continuity or escrow clause). Opened. [C-REF4-DC-technical-013]
- **N4.** getumbrel/umbrel #2153 (also used in DC-05). Opened. [C-REF4-DC-technical-008]
- Reproduction: GitHub API, rugix/rugix commits and releases (queried 2026-11-11). [C-REF4-DC-technical-012]

## What would flip it

- **Toward weakened (back toward Rugix as a co-equal choice):** RAUC goes 12 months without a release while a kernel or security fix sits unreleased on master, or one of RAUC's two main maintainers leaves Pengutronix. The same applies if RAUC fails the Pi 5 tryboot founder test (F-PI5) that Rugix passes. 01 §6.7 already names that last case.
- **Toward refuted (Rugix should be the engine):** Rugix gains a second maintainer with ≥ 10% of commits for two quarters, or Silitics publishes continuity terms (escrow, priced LTS or foundation hosting), **and** RAUC's lead over Rugix in the S2 tie-break drops below the 3-point band.
- **Stays upheld if:** RAUC ships 1.16 with two or more non-Pengutronix contributors credited, and OneMind's own RAUC package passes T-W3-04.
