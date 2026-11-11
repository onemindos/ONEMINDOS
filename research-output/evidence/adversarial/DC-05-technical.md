# DC-05: refuter report on rebasing a fielded device to a new major OS without a reflash (technical lens)

- **Conclusion under test (decision-critical.md DC-05 rev. 3; 01 §3.1.5 DC-05 row, §4.2, §4.3):** a major rebase without a reflash has a constraint-matched production precedent: umbrelOS moved from Debian 12 to 13 by OTA bundle [C-W3-039]. OneMind has not run one yet. bootc rebases by design and did so in our lab [C-LAB-fedora-bootc-015]. Flip not met. Status: partial.
- **Flip condition:** Rugix needs a reflash for a major rebase and a gate-passing alternative doesn't.
- **Lens:** technical. I read only the conclusion, 01 §3.1.5, §4.2 and §4.3, and the cited claims (C-W3-039, C-LAB-fedora-bootc-015, plus C-DEC-013, which 01 cites in the same table). I formed this view before reading any other refuter file.
- **Date:** 2026-11-11

## Verdict: **weakened**. The precedent is for an engine OneMind no longer uses, and the precedent's own field record includes stranded devices.

1. **The flip condition and the precedent are about Rugix; the decided engine is RAUC.** DC-06 moved D3 to RAUC. The umbrelOS Debian 12 → 13 OTA ran on Rugix (with a Mender variant for older boxes). 01's own negative search found **no shipped Debian or Ubuntu + RAUC product** [C-DEC-013]. So "constraint-matched production precedent" holds for the base (Debian 12 → 13) but not for the base plus the engine. The DC-05 question has to be asked again for RAUC: can a Debian-13 slot running OneMind's pinned RAUC install a Debian-14 bundle built with a newer RAUC (bundle format, verity parameters, signing, handler scripts), on the fixed 10 GiB / 512 MiB slots of §4.3? Nobody has shown that.
2. **The precedent's engine broke during the major rebase.** In April 2026 an umbrelOS 1.5.0 amd64 box on Debian 13 reported that the updater "does not offer any update beyond 1.5.0". The newer artifact uses Mender format version 3, the installed client is 3.4.0, a manual install fails with "invalid tar header", and "there is no Mender package available for Debian Trixie". There was no staff reply [C-REF4-DC-technical-006]. This is a single user report (medium-low confidence). It matches the failure class item 1 warns about: after a major rebase, the **old on-device client** cannot read the **new release's** artifacts, and the device is stranded with no reflash-free path.
3. **The precedent's later updates needed reflashes in the field.** In the 1.5 → 1.7.1 OTA thread (2026-04-29 to 05-03), NUC and Pi users reported "Update Failed", SSDs not mounted and apps not starting. One user recovered by **flashing 1.5 from USB**, another fixed a failed 1.4.2 → 1.5 with a clean install, and no staff replied [C-REF4-DC-technical-007]. Separately, umbrel #2153 (rugix-ctrl cannot find `sfdisk`, update hangs at 93%, slot switch never happens) is still open six months later and was reported again on 2.0.1 on 2026-11-03 [C-REF4-DC-technical-008]. The vendor shipped the rebase, but not every fielded device received it without a reflash. "Precedent" should be qualified as such.

## Strongest counter-argument

DC-05 exists because "choosing a distro for 10 years really means choosing a rebase strategy". The rev. 3 answer rests on someone else's rebase, done on someone else's engine, with field failures this file has now found. Meanwhile OneMind's chosen stack has never done a major rebase, in the lab or anywhere else. On the 01 §3.1.5 tie-break, C (bootc) wins DC-05 outright, and A is placed second only because of the umbrelOS precedent. With the precedent discounted to "base only, different engine, with stranded units", A's DC-05 row is no better than D's ("no production precedent"). The A-vs-D count would then move from 7–4 to 6–4 with DC-05 neutral. A still wins, but the "A > D" in that row is not earned.

## New sources (searched for failure and stranded devices)

- **N1.** Umbrel Community, "Umbreld crashes every ~36h … umbrelOS 1.5.0 — update system also broken" (2026-04-12). Opened. User report. [C-REF4-DC-technical-006]
- **N2.** Umbrel Community, "Fail to Update umbrelOS1.5 → 1.7.1" (2026-04-29 to 05-03). Opened. User reports. [C-REF4-DC-technical-007]
- **N3.** getumbrel/umbrel issue #2153 (opened 2026-05-24, still open, reproduced on 2.0.1 on 2026-11-03; fix PR #2163 open). Opened. [C-REF4-DC-technical-008]

## What would flip it

- **Toward refuted:** T-W3-04 shows that a Debian 13 slot with OneMind's pinned RAUC cannot install and commit a Debian 14 bundle on the §4.3 layout (slot too small, a bundle or verity format the old RAUC cannot read, or a bootloader or firmware change needing the ESP), while `bootc switch` does the same jump.
- **Toward upheld:** T-W3-04 passes on x86 (efi and GRUB routes) and on a Pi 5, with the **old** slot's RAUC installing the **new** release's bundle. In addition, OneMind adopts a rule: every release's bundle must be installable by the RAUC shipped N−2 releases earlier, enforced in CI.
- **Wording fix wanted now:** "umbrelOS shipped a Debian 12 → 13 OTA on Rugix/Mender (some devices stranded or reflashed); no RAUC major-rebase precedent exists; OneMind has not run one."
