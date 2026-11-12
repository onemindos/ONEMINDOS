# Refuter report: P0-W3-2, technical lens

- **Claim under test:** RAUC should replace Rugix as the lead A/B update client. Its stated grounds are 16 human committers, HAOS on x86 and Pi 5, CRLs, signing-time validation, signer allow-lists, open-source adaptive delta updates, and an HAOS root-CA rotation in 2026. The claim also says Rugix has no revocation, no anti-downgrade and single-signer CMS only. On the S2 scorecard RAUC scores 61.0, Mender OSS 57.0 and Rugix 52.0, with the same winner in 14 of 14 perturbations.
- **Refuter lens:** technical. Covers the update mechanism, board coverage, security features as actually used, and how robust the score is.
- **Date:** 2026-11-10 · **Re-check by:** 2027-05-10
- **Verdict: WEAKENED.** "RAUC over Rugix" survives: Rugix has one maintainer and no Jetson path. Three parts of the claim are wrong or out of date, though:
  - Two of RAUC's stated advantages over Rugix are not real. There is no anti-downgrade asymmetry, because RAUC has no such feature either. The open-source delta lead disappeared with Rugix 1.4.
  - The CRL advantage holds on paper only. The reference user disabled CRLs and calls offline CRLs "fundamentally broken".
  - The committer count includes an AI co-author.

  The 4.0-point lead over Mender depends on RAUC's C3 = 4. That cell rests on revocation as documented, not as used, and on a Secure Boot path the scorecard row does not cite. At C3 = 3 the lead is 1.0, inside the tie band, and on Jetson Mender is ahead.

## 1. Strongest counter-argument

### 1.1 The security asymmetry against Rugix is overstated
| Claimed RAUC advantage | What the primary sources show |
|---|---|
| "Rugix documents no … anti-downgrade" (so RAUC is better) | RAUC has no built-in anti-downgrade either. At the claim's own pinned SHA, `docs/*.rst` mentions downgrade only for format migration and sub-device downgrades ([integration.rst#L1897-L1899](https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/docs/integration.rst#L1897-L1899)). Both tools would do a version check in a hook: RAUC in an install-check handler, Rugix in its "before installing an update" hook ([rugix-docs hooks.md#L8](https://github.com/rugix/rugix-docs/blob/227f902790fe876b5a0d0df02e9c56e7cf1f6459/src/content/docs-ctrl/1.4/reference/hooks.md#L8)). **This is a tie, not a RAUC advantage.** |
| "supports CRLs" | The feature exists (`check-crl`), but its main user rejected it. In HAOS issue [#4743](https://github.com/home-assistant/operating-system/issues/4743) (June 2026), the maintainers found HAOS had never enabled `check-crl`; RAUC was logging "Detected CRL but CRL checking is disabled!". They called device-local CRLs "fundamentally broken": a device holding an older CRL still accepts a revoked certificate, and an expired CRL breaks the chain of trust. PR #4757 then **removed CRLs** and moved to 4-year leaf validity plus CA rotation. The HAOS pattern the claim cites is therefore *rotation without CRLs*. Rugix can do the same by shipping new trust roots in an update. **In practice the difference is small.** |
| "open-source adaptive (block-hash-index) delta updates" | Rugix Ctrl **v1.4.0 (2026-11-02)** turns on "Delta updates by default": block indices are kept, HTTP range requests are used, and Bakery bundles include the indices ([release notes](https://github.com/rugix/rugix/releases/tag/v1.4.0)). Both tools are open source, so this no longer separates RAUC from Rugix. It still separates RAUC from Mender OSS, where delta updates are commercial (C-W3-055). |
| "certificate validation at bundle signing time, signer allow-lists" | Both are real ([reference.rst#L288-L330](https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/docs/reference.rst#L288-L330)). Rugix's single-signer CMS limit (C-W3-008) is a genuine gap. **This is a real RAUC advantage.** |

### 1.2 RAUC's 2026 signing CVE and an insecure default
- **CVE-2026-34155 / GHSA-6hj7-q844-m2hx (High, 2026-03-27).** For `plain` bundles over 2 GiB, an integer overflow left the signature covering "only the first few bytes of the payload", so an attacker could modify the rest. The fix is the commit the claim pins (4fb7c798). Debian's tracker shows **bookworm 1.8-2 still vulnerable (`no-dsa`)** and trixie fixed in 1.13-3+deb13u1 ([tracker](https://security-tracker.debian.org/tracker/CVE-2026-34155)).
- The bundle `format` **still defaults to `plain`** ([reference.rst#L810-L811](https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/docs/reference.rst#L810-L811), [#L1146-L1152](https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/docs/reference.rst#L1146-L1152)). If OneMind leads with RAUC, it must set `format=verity` and `bundle-formats=-plain` in its configuration. Rugix had a comparable advisory in October 2026 (GHSA-f8wx-p63f-pp8h, execute payloads without block encoding; cited from the [v1.3.2 release notes](https://github.com/rugix/rugix/releases/tag/v1.3.2), advisory page not opened). **Both tools had a 2026 signing or verification flaw**, so neither wins on security track record.

### 1.3 The maintainer base is narrower than "16 human committers" suggests
I re-ran the cited API query for 2025-11-10 to 2026-11-10: 512 commits, 20 distinct author strings.
- After merging name variants ("Jan Luebbe"/"Jan Lübbe", "Enrico Jörns"/"Jorns"/"Joerns"), there are **15 humans**. The 16th author is `Claude <…@anthropic.com>`, an AI co-author, plus `dependabot[bot]`.
- **458 of the 485 non-bot commits (94%) come from `pengutronix.de`.** Two people wrote 287 and 155.

RAUC is effectively a single-company project with a bus factor of two people. That is better than Rugix (303 of 304 commits by one author, C-W3-001), but it is still one company. The latest release, v1.15.2, is from 2026-03-27, with no release in the 7.5 months since. Issue [#2049](https://github.com/rauc/rauc/issues/2049) (2026-10-09, v1.15.2) reports that an interrupted streaming install leaves the slot mounted and blocks further installs until RAUC restarts. A month later it has no maintainer reply. That matters for a fleet that streams updates over flaky links. None of this means RAUC is being abandoned, but the C1 = 3 score is generous at the edge.

### 1.4 On Jetson, Mender is ahead and RAUC has nothing maintained
- RAUC's Tegra community layer was **deleted** on 2024-08-21 ([meta-rauc-community b89bdf34](https://github.com/rauc/meta-rauc-community/commit/b89bdf3469c5c1b83ee3395547151beb1884102b)). The only public RAUC-on-Orin recipe is a vendor wiki page ([RidgeRun](https://developer.ridgerun.com/wiki/index.php/RidgeRun_Platform_Security_Manual/Getting_Started/Over-the-Air/NVIDIA_Jetson_-_RAUC/Update_Flow_and_Custom_Bootloader)). It uses a hand-written `bootloader=custom` extlinux script, does not mention nvbootctrl or UEFI capsules, and describes no boot-attempt rollback.
- Mender added a **native Tegra update module** in August 2026 ([meta-mender-community 72093c00](https://github.com/mendersoftware/meta-mender-community/commit/72093c006f007cef2405540464d62b2bc343519b)). It drives `nvbootctrl`, the BSP partition labels and the UEFI capsule directly, and covers Thor and Orin on L4T 39.2 (C-W3-053).
- RAUC on Pi 5 likewise depends on a **HAOS-specific custom backend script** (`rpi-tryboot.sh`), not on upstream RAUC. Rugix ships `rpi-tryboot` as a built-in boot flow (C-W3-011).

So on two of OneMind's three board families, the "RAUC path" is code that OneMind or HAOS maintains, not RAUC upstream. The scorecard prices part of this in (C2: RAUC 2, Mender 3) and adds a 2–3-week Jetson wrapper to the plan for every candidate. It does not account for Mender's wrapper already existing upstream.

### 1.5 The 14/14 robustness test hides how fragile the lead over Mender is
Perturbing weights does not test whether individual scores are right. The 4.0 margin over Mender comes from three cells: C3 (+3.0), C4 (+3.0) and C6 (+2.0), offset by C2 (−4.0).
- **C3 = 4** requires "key rotation **and revocation**" plus a "documented Secure Boot / measured boot / TPM path that does not need a partition or bootloader change later". Revocation through CRLs is documented, but the reference deployment calls it unusable (1.1). The RAUC row cites only C-W3-018 and C-W3-024 for C3, and neither covers a Secure Boot path. **Under the "lower anchor when in doubt" rule, C3 should be 3.** That leaves a margin of 1.0, a tie.
- **C4:** Mender at 2 cites only legacy umbrelOS (C-W3-040). If one more shipping product confirmed from code were added, Mender would reach 3 and RAUC's lead would shrink by another 3.0.
- Once tied, the decision-critical tie-break turns on Jetson (1.4), which favours Mender. The author's counter, that Mender's Jetson path needs a Yocto flavor DC-09 has not chosen, is valid. That makes the decision **contingent on DC-09**, not "robust".

## 2. What still holds
- **RAUC over Rugix is sound.** Rugix's single maintainer (C1 = 2), lack of Jetson support, single-signer CMS, no automatic good/bad marking (C-W3-005) and auto-commit footgun (C-W3-006) are real. Rugix's own comparison concedes it is "newer and less widely deployed" (C-W3-016).
- RAUC really does run HAOS on x86 and Pi 5, and ZimaOS. It has LGPL-2.1 terms suitable for a separate program, signer allow-lists, signing-time validation and verity/crypt formats. Debian trixie ships a patched build.
- The HAOS cross-signed CA rotation is real in source (PR #4757, merged 2026-06-09). Whether new-chain bundles have reached field devices is **UNVERIFIED**: the old chain is accepted until 2028-05-14, and I did not confirm which chain current releases are signed with.

## 3. Requested rewrite of the claim
"RAUC leads Rugix for the A/B client: a larger, though single-company, maintainer base (15 humans, 94% Pengutronix), multi-signer and allow-list support, signing-time validation, and production use in HAOS and ZimaOS. Neither tool has built-in anti-downgrade (both use a pre-install hook). Both now ship open-source delta updates (Rugix ≥1.4). RAUC's CRL support is unused by HAOS, which rotates its CA instead. RAUC's lead over Mender OSS is **within the tie band if C3 is scored 3**, and the choice between them depends on DC-09: with a Yocto Jetson flavor, Mender's maintained native Tegra module wins on Jetson. OneMind must configure `format=verity` and `-plain` (CVE-2026-34155)."

## 4. Evidence that would flip the decision
- **Toward Mender over RAUC:** either (a) DC-09 picks a Yocto/meta-tegra Jetson flavor, or (b) the S2 row is re-scored with RAUC C3 = 3 (no cited Secure Boot path, revocation unused) or Mender C4 = 3 (a second shipping product confirmed from code). Either change puts the two inside the tie band, and the tie-break then turns on Jetson.
- **Back toward Rugix:** Rugix gains a second active maintainer or company backing with a multi-minor security policy, plus multi-signer CMS and a Jetson boot flow. Or the `evidence/lab/debian-rugix` spike passes T4–T7 while `evidence/lab/rauc` fails any of them.
- **Firmly upholding RAUC:** the RAUC lab spike passes T2–T7 on Debian 13. A RAUC nvbootctrl/UEFI-capsule backend boots and rolls back on the founder's Orin Nano (T-W3-06). RAUC v1.16 ships with #2049 fixed. A documented RAUC + UEFI Secure Boot path is cited in the C3 cell.

## 5. Sources opened for this report (new)
1. RAUC advisory GHSA-6hj7-q844-m2hx / CVE-2026-34155 (via `api.github.com/repos/rauc/rauc/security-advisories`), https://github.com/rauc/rauc/security/advisories/GHSA-6hj7-q844-m2hx (PRIMARY)
2. Debian security tracker, https://security-tracker.debian.org/tracker/CVE-2026-34155 (PRIMARY)
3. HAOS issue #4743 (CRL rationale), https://github.com/home-assistant/operating-system/issues/4743 (PRIMARY)
4. RAUC issue #2049, https://github.com/rauc/rauc/issues/2049 (PRIMARY)
5. Rugix v1.4.0 release notes, https://github.com/rugix/rugix/releases/tag/v1.4.0 (PRIMARY)
6. meta-mender-community native Tegra module, https://github.com/mendersoftware/meta-mender-community/commit/72093c006f007cef2405540464d62b2bc343519b (PRIMARY)
7. meta-rauc-tegra removal, https://github.com/rauc/meta-rauc-community/commit/b89bdf3469c5c1b83ee3395547151beb1884102b (PRIMARY)
8. RidgeRun RAUC on Jetson, https://developer.ridgerun.com/wiki/index.php/RidgeRun_Platform_Security_Manual/Getting_Started/Over-the-Air/NVIDIA_Jetson_-_RAUC/Update_Flow_and_Custom_Bootloader (SECONDARY, vendor wiki)
9. RAUC docs at 4fb7c798: reference.rst#L810-L811, #L1146-L1152; integration.rst#L1897-L1899 (PRIMARY)
10. Rugix hooks.md at 227f9027, https://github.com/rugix/rugix-docs/blob/227f902790fe876b5a0d0df02e9c56e7cf1f6459/src/content/docs-ctrl/1.4/reference/hooks.md#L8 (PRIMARY)
11. Re-run of https://api.github.com/repos/rauc/rauc/commits?since=2025-11-10T00:00:00Z (pages 1–6, 512 commits, author and email-domain counts) (PRIMARY)
