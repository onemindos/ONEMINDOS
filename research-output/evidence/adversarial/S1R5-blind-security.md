# S1 refuter R5 (blind, security lens): Ubuntu 26.04 LTS + RAUC A/B

**Protocol:** RESEARCH-MISSION.md §2 rule 7. Blind refuter: I was given the claim only, and did not open `01-FOUNDATION-DECISION.md`, `decision-critical.md`, the scorecard files, or anything in `evidence/adversarial/` or `evidence/critic/`. (I listed the `adversarial/` directory to choose a file name and opened none of its files.) Product constraints come from `RESEARCH-MISSION.md` and `docs/REQUIREMENTS.md` (F-1, F-7, F-14, R-1, U-4).
**Date:** 2026-11-11 · **Lens:** security · **Ledger:** `evidence/claims/REF5-S1-security.csv`

## Claim under test

> S1 decision of record (rev. 4): the OneMind OS core is Ubuntu 26.04 LTS plus RAUC A/B updates (plus an NVIDIA L4T/JetPack flavor for Jetson). It was chosen over RHEL-family bootc and Debian 13 under a frozen weighted scorecard. It depends on Canonical's permission or a debranded rebuild (Z-01), and on G5 (one OS from a Pi 5 to a GPU cluster).

## Verdict: **WEAKENED**

On security, the decision holds only on one side of Z-01, the side where Canonical gives permission. The claim treats "Canonical permission" and "debranded rebuild" as two equal ways to meet Z-01. They are not equal on security.

- **Permission branch:** Canonical-signed binaries, the Canonical Secure Boot chain, Canonical's patch pipeline and ESM to 2036. This is a strong position.
- **Rebuild branch:** OneMind runs its own distribution. That means its own signing root, its own shim review, its own build of every Ubuntu Security Notice (USN), and no ESM binaries. That is a heavier security-operations load than the Debian 13 runner-up carries.

So Z-01 is not just a licensing condition. It decides whether the security case for Ubuntu exists at all.

## The strongest counter-argument (security)

### 1. Under the IP policy, the debranded-rebuild branch breaks the inherited chain of trust

Canonical's IP Rights Policy says: *"Any redistribution of modified versions of Ubuntu must be approved, certified or provided by Canonical if you are going to associate it with the Trademarks. Otherwise you must remove and replace the Trademarks and will need to recompile the source code to create your own binaries."* [S1]

A OneMind image with RAUC, its own slot layout, its own init and its own health-commit logic is a modified version of Ubuntu. Without Canonical's approval, OneMind has to rebuild the binaries itself.

Rebuilt binaries are not signed by Canonical. On x86, UEFI Secure Boot then needs one of two things:

- **(a) OneMind's own Microsoft-signed shim.** This goes through `rhboot/shim-review`. Since 27 June 2026 Microsoft signs shims only with the UEFI CA 2023. The submission needs an EV certificate, SBAT generation 5 in GRUB, NX compatibility answers, a description of kernel lockdown enforcement, and the hashes of any old shims for the DBX revocation list [S2].
- **(b) Per-device enrollment of a Machine Owner Key (MOK).** This breaks the founder's "as simple as a Pi" rule (F-14).

Either way, the 26.04 security story ("Canonical's signed shim, kernel and livepatch") stops applying. OneMind becomes a signing authority for x86 boot, with an HSM, key-rotation and revocation duties from day one. This lands in exactly the "Secure Boot and TPM later" area that ADR-001 deferred.

### 2. "LTS to 2036" is a Pro-gated security horizon, and it shrinks for an image vendor

- **Free maintenance ends in 2031, and covers only Main.** 26.04 LTS standard security maintenance ends in May 2031. Expanded Security Maintenance (ESM) runs to May 2036, and the Legacy add-on to May 2041 [S3][S4]. Free standard maintenance covers only **Main**, about 2,300 packages. **Universe**, over 36,000 packages, gets security fixes only through Ubuntu Pro [S5][S6].
- **Pro is per machine.** Free Pro covers *"up to five physical Ubuntu systems"* under the Personal terms [S7]. The commercial terms define redistributable "Ubuntu Content" as Canonical-published packages and images *"redistributable in their original form subject to the IP policy"* [S8].
- **The rebuild branch falls back to OneMind's own fixes.** A rebuilt image cannot carry Canonical's ESM binaries. After May 2031, and for any Universe package in the image from day one, the fixes are OneMind's to backport.
- **Under F-1 the gap is concrete.** F-1 calls for a 5–10-year horizon, and the image is shipped as a sovereign OS. A device sold in 2029 has about 2 years of free Main coverage left. After that it either carries a per-device Canonical subscription (a vendor dependency in a "sovereignty" product) or OneMind's own backports.
- **Pro is the condition, not 2036.** A security claim of "supported to 2036" holds only if every shipped device is Pro-attached, or OneMind has a Pro-for-Devices agreement whose redistribution terms I could not see in public text (UNVERIFIED).

### 3. A/B images move patch latency onto OneMind, and Ubuntu's base is in flux

- **OneMind owns the update path.** With RAUC, devices do not run `apt`/unattended-upgrades. Every USN becomes an image rebuild, a test, a sign and a staged rollout by OneMind. Canonical's patch is only an input.
- **The kernel cadence works against a lean team.** HWE interim kernels get only about 6 months of support and no ESM. For example, 6.17 on 24.04.4 was supported from Jan 2026 to Jul 2026 [S4]. Tracking HWE for new Pi or GPU hardware therefore means re-basing the kernel twice a year. Staying on the GA kernel (7.0 for 26.04, per the kernel table) means newer hardware lags.
- **The 26.04 userland has recent security-relevant regressions.**
  - LP #2127970 (Critical): the Rust coreutils `date -r` returned a wrong date, and this silently stopped unattended-upgrades from running on 25.10. The record also lists the `resolute` (26.04) series [S9].
  - `sudo-rs`, Ubuntu's Rust sudo, has six published advisories. One of them, GHSA-f42v-x7gq-phc8 (published 2026-08-31), is a TOCTOU local privilege escalation in `sudoedit` [S10].
  - Lesson: a fresh LTS userland carries regression risk that an image vendor must catch in its own CI, because no apt fallback runs on the device. Whether 26.04 ships sudo-rs as the default is UNVERIFIED here.

### What I checked that **supports** the claim (fairness)

- The Raspberry Pi 5 is listed as **"Yes, certified"** for Ubuntu 26.04 LTS [S11]. G5 on the Pi side is credible.
- The real-time kernel is *"available for everyone from the 26.04 release onwards"* through `apt install ubuntu-realtime`, with no Pro needed [S12]. This removes a Pro dependency for robotics.
- The lifecycle is the longest of the three candidates: maintenance to 2031, ESM to 2036, and Legacy to 2041 [S3]. Canonical publishes FIPS 140-3, DISA-STIG and CIS as "Planned" for 26.04 [S3]. That helps the public-safety tier, but only on the permission/Pro branch.

## What would flip the verdict

| Evidence | Effect |
|---|---|
| Written permission from Canonical to ship Canonical-signed binaries (shim, kernel, packages) unmodified inside a OneMind-branded RAUC image, plus a device-scale Pro/ESM price that OneMind can resell or bundle | **→ upheld** (the security case stands as claimed) |
| Canonical declines, the rebuild branch is forced, and OneMind has no shim-review submission plan, HSM or USN-rebuild SLA | **→ refuted on security** (Debian 13 or bootc would carry less signing and backport burden; this needs a like-for-like check of the Debian trademark policy and the Debian/Fedora Secure Boot paths, which I did not open: UNVERIFIED) |
| The S1 record includes, in measured form, a USN-to-signed-image latency target (for example ≤72 h for high/critical), a GA-kernel-only policy, and the cost of Pro on every shipped device | weakened → closer to upheld on the rebuild branch |
| Primary evidence that Canonical's ESM sources are publicly available for rebuild | Softens point 2 (UNVERIFIED either way) |

## Required response (rule 7: weakened needs a written response from the author)

The author should state which branch of Z-01 the security scores assumed. If the scores assumed Canonical's signed chain and ESM, they must be re-scored for the rebuild branch, or the decision must be made conditional on the permission branch alone.

## Sources (all opened 2026-11-11; ubuntu.com and launchpad.net do not resolve from this sandbox, so Wayback captures were read; raw sha256 of each downloaded capture)

| # | Source | Type | Archive / integrity |
|---|---|---|---|
| S1 | Canonical IP Rights Policy, https://ubuntu.com/legal/intellectual-property-policy | PRIMARY (legal text) | https://web.archive.org/web/20261023180559/https://ubuntu.com/legal/intellectual-property-policy · `d72961648ebf476465f044ca1804950b28d32270b07a40ea3395a89f80caa315` |
| S2 | `rhboot/shim-review@e9b3a73d0e74fb1258a3ef68ea6e79e483134d24:README.md#L18-L20,L60-L65,L142-L253` | PRIMARY (code repo, pinned) | Opened via `gh api` at that SHA |
| S3 | Ubuntu release cycle, https://ubuntu.com/about/release-cycle | PRIMARY (vendor lifecycle) | https://web.archive.org/web/20261107191606/https://ubuntu.com/about/release-cycle · `1576d58fe49a2cf239402ee14df8acae6bf90d47aac336ab9bd99384f99454df` |
| S4 | Ubuntu kernel lifecycle, https://ubuntu.com/kernel/lifecycle | PRIMARY | https://web.archive.org/web/20261105172832/https://ubuntu.com/kernel/lifecycle · `e3111fafcd54c9aa2376b6612882d333d4465df84d37e4b8b9e8d889b6659791` |
| S5 | ESM page, https://ubuntu.com/security/esm | PRIMARY | https://web.archive.org/web/20261103130446/https://ubuntu.com/security/esm · `0ab79050b33c3212ea7c4108ddec95ddb8774be9986a2de7fafc14365c00cd5a` |
| S6 | Ubuntu Pro page, https://ubuntu.com/pro | PRIMARY | https://web.archive.org/web/20261107214224/https://ubuntu.com/pro · `f090f03c252fb46257ca12fb9323ee5a8ec5f52dcdff4815f78e407c1f84a29b` |
| S7 | Ubuntu Pro Personal terms, https://ubuntu.com/legal/ubuntu-pro/personal | PRIMARY (legal text; capture 2025-08-04, re-check) | https://web.archive.org/web/20250804230855/https://ubuntu.com/legal/ubuntu-pro/personal · `ecab6bdb3430e3e082c81c8e82bb215e9f772af7dff312bafff861c367d9e098` |
| S8 | Ubuntu Pro service terms, https://ubuntu.com/legal/ubuntu-pro-service-terms | PRIMARY (legal text) | https://web.archive.org/web/20260508102745/https://ubuntu.com/legal/ubuntu-pro-service-terms · `ca823cfb79492b9c60838c2ac5745fe9ef4f6815a828e66ffb896fab0db739af` |
| S9 | Launchpad bug 2127970 (rust-coreutils) | PRIMARY (bug tracker) | https://web.archive.org/web/20260502143821/https://bugs.launchpad.net/ubuntu/+source/rust-coreutils/+bug/2127970 · `1aaf32a7964d88058dd6b9b033cf765f3d2e3beceb2d894493eed4ceec6ab04a` |
| S10 | `gh api repos/trifectatechfoundation/sudo-rs/security-advisories` (GHSA-f42v-x7gq-phc8, GHSA-q428-6v73-fc4q, GHSA-c978-wq47-pvvw, …) | PRIMARY-METADATA (vendor-repo advisories) | API response, not saved |
| S11 | Ubuntu on Raspberry Pi, https://ubuntu.com/raspberry-pi | PRIMARY | https://web.archive.org/web/20261020213536/https://ubuntu.com/raspberry-pi · `9a15f6991b6e07beb03f8676a977cb2ca9396bea3b0438dc84c140f0a49d84e5` |
| S12 | Real-time Ubuntu, https://ubuntu.com/real-time | PRIMARY | https://web.archive.org/web/20261101110028/https://ubuntu.com/real-time · `13fb819c43a2649aa72bbf7ce2c137603025d99324f7b82c5206ff513461a33b` |

The 26.04 release notes (discourse.ubuntu.com) were not captured in Wayback (4.6 KB stub) and were not read.
