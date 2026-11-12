# DC-18 · Adding the chain of trust later without a layout change: longevity and vendor-risk refuter

**Refuter:** REF3, lens longevity and vendor risk · **Date:** 2026-11-11 · **Verdict: WEAKENED**
**Read before forming this view:** DC-18 in `decision-critical.md`, `07-security-compliance.md` P0-4 and §2, the DC-18 bullets in `01-FOUNDATION-DECISION.md` (tie-break and §4.3 notes), `qbank/W6.md` Q206–Q209, and the claims they cite (C-W6-044…051, 056…061, C-LAB-secureboot-rauc-012…017, C-STEEL-updates-mender-014). No other adversarial file was read first.

## The conclusion under test

The claim is that retrofitting a verified boot chain **does not need a reflash if** the x86 layout is chosen now: a large ESP, a signed UKI per slot, verity headroom and LUKS2 data from first boot. Pi 5 OTP and Jetson fuses are compatible with A/B but irreversible. On owned hardware, OneMind enrols its own PK/KEK/db at the factory. The flip condition (not met) is that the updater cannot boot signed UKIs per slot, or cannot keep a TPM-sealed key valid across A/B. The x86 route is lab-confirmed in emulation with RAUC's `efi` backend.

## Strongest counter-argument

"Layout chosen now" removes the **partition** reason for a reflash. Whether Secure Boot can be "added later" over a 10-year life also depends on two things the layout does not control: firmware key stores on cheap x86 hardware, and the maintainers of the software the plan rests on.

1. **Firmware key stores are the weak, long-lived link, and 2026 shows it.** LWN's 2026 report on the Microsoft 2011 CA expiry says forced Secure Boot DB updates "have left some machines unbootable", that "in some cases we have observed that systems were permanently damaged", and that some recoveries need physical access. It also reports vendors that stopped shipping LVFS updates, HP and Fujitsu hardware needing newer firmware before a DB update can be deployed, and a Dell where a firmware update did not refresh the keys [C-REF3-DC-longevity-008]. LWN's 2025 preview said a KEK update "has never happened before", so "there are chances that bios vendors messed up things", and that "the older your BIOS the more likely you are to hit this" [C-REF3-DC-longevity-009]. "Turn Secure Boot on later" for a fielded mini PC means writing authenticated variables (db/KEK, and PK if OneMind owns it) through the same firmware paths. The lab ran on OVMF, which is the best-behaved implementation there is.
2. **Factory key enrolment assumes the ODM's PK can be trusted or replaced.** PKfail (BRLY-2024-005) showed that firmware from 10 vendors (Acer, Dell, Fujitsu, Gigabyte, HP, Intel, Lenovo, Supermicro and others) shipped AMI's "DO NOT TRUST" test Platform Key in production for "over 12 years" (May 2012 to June 2024). The fix depends on vendor firmware updates [C-REF3-DC-longevity-010, SECONDARY]. A white-label mini PC's ODM is exactly the supplier least likely to ship those updates for 10 years. If Secure Boot is deferred to phase 2, boxes already in the field need the PK replaced in setup mode, with physical presence on the owner's site. The 01 note already admits that boxes in the field "need an owner-run enrolment". At fleet scale that is a site visit or a return. It is not a reflash, but it is not "later, by update" either.
3. **The TPM path in the update tool rests on one maintainer.** 07 makes "Rugix stays" the D3 outcome and relies on Rugix's `luks2-tpm2` driver. At c2f5f4f its schema calls the driver "production-grade" but binds literal PCRs only, warns that PCRs 0–9 "will brick the device on every update", and leaves `tpm2-public-key` / `TPM2_PolicyAuthorize` to "future revisions". That is the feature that makes TPM sealing survive A/B. The GitHub API shows **303 of 304 commits to rugix/rugix since 2025-11-11 by one account**, and 1,161 of about 1,170 commits overall [C-REF3-DC-longevity-011]. The planned signed-policy mode has no second contributor. If that maintainer stops, OneMind owns the TPM unlock path for every x86 box. (01 has since moved the x86 tie-break to RAUC, which is lab-proven with a signed PCR 11 policy. That route avoids this point **only if** D3 is formally RAUC, but 07's P0-4 row still says "Rugix stays".)
4. **Pi 5 and Jetson: irreversibility plus a vendor-controlled bootloader.** Raspberry Pi signs nothing for OneMind. The OTP key is permanent, and the bootloader channel is Raspberry Pi's. Turning on secure boot "later" on a fielded Pi means an irreversible OTP write done remotely. If it fails halfway, that is a return to factory. The DC answer treats this as a known constraint. It does not plan for the fact that phase-2 enablement on fielded Pis is, in practice, never.

## What does not break

- The partition argument is sound. A 1 GiB ESP, UKIs per slot and LUKS2 from first boot remove the need to repartition, and the RAUC + OVMF lab shows A/B, rollback and TPM unlock under enforced Secure Boot (C-LAB-secureboot-rauc-012…017).
- On hardware OneMind sells with its own PK enrolled **at the factory, before shipping**, points 1 and 2 shrink to "choose an ODM whose firmware handles authenticated variable updates". That can be tested before purchase.

## Verdict: WEAKENED

"No reflash" holds for the **layout**. "Can be added later" does not hold as a fleet operation. Secure Boot (and the db key) must be **enrolled at the factory on every x86 box from the first shipment**, even if enforcement and the TPM policy are switched on in phase 2. Pi 5 secure boot must be decided per SKU before shipping, because remote OTP enablement is not a realistic later step. The D3 record should either name RAUC for the x86 TPM path or record Rugix's single-maintainer risk on `luks2-tpm2` with an exit plan.

## What would flip it

- **To REFUTED:** on the actual target mini-PC model (not OVMF), a remote db/KEK update or PK replacement fails or bricks the box, **or** the ODM firmware ships a PKfail-class test key with no update. Either one means phase-2 enablement needs a site visit or an RMA.
- **Back to UPHELD:** a hardware test on the chosen ODM board shows that an OS-initiated authenticated db/KEK update and a setup-mode PK enrolment survive power loss, **and** D3 is formally RAUC for x86 (or Rugix merges PolicyAuthorize and gains a second active maintainer).

## New sources (opened 2026-11-11)

| Claim | Source | Type |
|---|---|---|
| C-REF3-DC-longevity-008 | https://lwn.net/Articles/1079808/ | SECONDARY (LWN reporting, 2026) |
| C-REF3-DC-longevity-009 | https://lwn.net/Articles/1029767/ | SECONDARY (LWN reporting, 2025-07-16) |
| C-REF3-DC-longevity-010 | https://www.bleepingcomputer.com/news/security/pkfail-secure-boot-bypass-lets-attackers-install-uefi-malware/ (cites Binarly BRLY-2024-005) | SECONDARY |
| C-REF3-DC-longevity-011 | GitHub API `repos/rugix/rugix/commits?since=2025-11-11` and `/contributors`; schema at rugix/rugix@c2f5f4f `crates/apps/rugix-ctrl/schemas/system.sidex` | PRIMARY |
