# Adversarial review: P0-W3-2 (RAUC replaces Rugix as A/B update lead), security lens

- Refuter: independent, security lens. Date: 2026-11-10.
- Claim under test: for the A/B OS update client, RAUC should replace Rugix as the lead, for the security and maintenance reasons listed in the claim, with a scorecard of RAUC 61.0, Mender OSS 57.0 and Rugix 52.0.
- **Verdict: WEAKENED.** Choosing RAUC over Rugix holds up under the security lens. Several of the security facts used to support it are overstated or misattributed, and RAUC has no maintained upstream integration for Jetson, one of OneMind's targets. The scorecard should be re-scored with the corrections below before the decision is frozen.

## 1. Strongest counter-argument

1. **RAUC's own signature check was bypassable in its default bundle format until March 2026.** GHSA-6hj7-q844-m2hx (CVE-2026-34155) is rated High (CVSS 4.0 7.2, CWE-347). For `plain` bundles with a payload over 2 GiB, an integer overflow made the signature cover only the first few bytes. An attacker holding one legitimately signed bundle could change the rest. Versions before 1.15.2 are affected. `plain` is still the default when creating a bundle (`reference.rst` L811, and the note at L1146-1150 that warns about defaulting to plain). The flaw was found by Sony, not by the maintainers. The claim cites v1.15.2, the fixed release, but does not mention that RAUC has the same kind of integrity bypass it holds against Rugix.
   - Required mitigation the claim omits: the OneMind system.conf must set `bundle-formats=-plain` (verity only), and every RAUC version in use must be at least 1.15.2.
   - Root-filesystem images for Jetson and the GPU-cluster tier will easily exceed 2 GiB, so this is not an edge case for OneMind.
2. **RAUC's CRL support is not used in practice by its main reference user.** The claim lists "supports CRLs" as an advantage. HAOS PR #4757, the same PR the claim cites for the CA rotation, removed CRLs from the keyrings. Issue #4743 records why:
   - HAOS never set `check-crl=true`, so the CRLs were never checked (`check-crl` is at `reference.rst` L322).
   - An on-device CRL does not stop a revoked signer from updating devices that hold an older CRL.
   - An expired CRL invalidates the trust chain and blocks updates.
   - The maintainers concluded that rotating the intermediate CA is the practical response to a compromise.

   The competitor evidence (rule 2) therefore says revocation through CRLs is not an effective control. Rugix's lack of documented revocation is a much smaller gap than the claim implies.
3. **"Certificate validation at bundle signing time" weakens security; it is not a control.** `use-bundle-signing-time=true` (reference.rst, just above L292) checks certificates against the signing time embedded in the bundle, not the device clock. A bundle signed while its certificate was valid then stays installable after that certificate expires. Combined with the point above, revoking a signer becomes even less effective. It is useful on devices without a reliable clock. It should not be scored as an advantage. This risk is my inference from the option's definition; I found no source that discusses it.
4. **RAUC's anti-downgrade protection is a static floor, not a monotonic counter.** `min-bundle-version` (reference.rst L72-90) rejects only bundles older than a value set in system.conf. The docs themselves warn that this conflicts with rollback, and the D-Bus option `ignore-version-limit` (L1761-1763) disables it. `prevent-late-fallback` stops fallback to the old slot, but that is not the same thing. RAUC has no TPM or fuse-backed rollback index. The claim is right that Rugix documents no anti-downgrade. On the other side the realistic credit is "partial", not "present".
5. **There is no maintained upstream RAUC integration for Jetson, a OneMind target.** `rauc/meta-rauc-community` removed `meta-rauc-tegra`, which supported only the TX2 on JetPack 4, in commit b89bdf3469c5c1b83ee3395547151beb1884102b (2024-08-21). The only Orin material I found is a third-party RidgeRun wiki page. It uses a custom `jetson-extlinux` backend that rewrites `extlinux.conf` non-atomically, and it notes that with the default `noop` backend, `mark-good` does not affect bootloader state. That is a fail-safe gap: the A/B rollback guarantee does not hold out of the box on Jetson.

   OE4T's `tegra-demo-distro` ships integration layers for SWUpdate and Mender, not RAUC. RAUC "runs HAOS on x86 and Pi 5" covers two of OneMind's three hardware classes. The Pi 5 support comes from a HAOS-specific tryboot script, not upstream RAUC.
6. **HAOS's own RAUC deployment has had bootloader and environment-file failures in 2026.** These show the integration work is where the risk lies, whichever client is chosen:
   - HAOS #4807 (opened 2026-06-22): a GRUB environment mismatch meant slot B was never marked bad after failed boots.
   - HAOS #5036 (opened 2026-09-23): RAUC boot-order changes were silently ignored on legacy-BIOS x86. Maintainers closed it "not planned" and declined BIOS support.

   This is integration risk, not a RAUC code defect. It does show that bootloader integration on x86 and Pi 5 is where the work and the risk are.
7. **The maintainer-count figure is slightly inflated and hides a single-vendor bus factor.** I re-ran the cited API (`/repos/rauc/rauc/commits?since=2025-11-10`, 512 commits, fully paginated):
   - 15 distinct humans by GitHub login, plus one `claude` commit and dependabot.
   - Counting by author name gives inflated numbers because "Jan Lübbe" and "Jan Luebbe" (and "Enrico Jörns", "Jorns" and "Joerns") are counted separately.
   - jluebbe (287) and ejoerns (155) wrote 442 of the 484 commits by humans with a GitHub login (about 91%), and both work at Pengutronix.

   The bus factor is about two people at one vendor. This is still far better than Rugix: koehlma wrote 303 of the 304 commits in the same window, one maintainer.

## 2. What survives (fairness)

- Rugix has a worse security record in the same period. It published two High advisories in October 2026:
  - GHSA-f8wx-p63f-pp8h (2026-10-29): unverified bytes could reach execute-payload handlers when a bundle was built without block encoding, leading to code execution. Versions 0.8.0 to before 1.3.2, and 1.4.0-dev.1, are affected.
  - GHSA-637r-qx4c-jm45 (2026-10-21): the bundled WebPKI roots still trusted compromised eMudhra intermediate CAs. Versions before 1.3.1 are affected.
- Rugix supports only single-signer CMS signatures (signed-updates.md, at the cited SHA). That stands.
- HAOS did carry out a cross-signed root rotation (PR #4757, merged 2026-06-09, which keeps old-chain bundles valid until 2028-05-14). That stands. It is a CA-management practice that RAUC's `intermediate` option makes possible, and it shows key rotation works in the field.
- Net result under the security lens: RAUC is still at least as good a choice as Rugix. The specific advantages claimed, CRLs and validation at signing time, should be removed or re-scored, and the Jetson gap needs its own row.

## 3. Evidence that would flip the decision

- **Toward Mender OSS (the margin is 4 points):** a maintained, current Mender integration for JetPack 6 on Orin (an OE4T or `mender-community` layer pinned to an r36.x branch, with CI), while RAUC has none. Re-scoring the security rows as corrected above (CRL: no credit; signing-time validation: neutral or negative; anti-downgrade: partial) and adding a Jetson fail-safe row could close the 4-point gap. If the 14-point perturbation set does not include a Jetson-support weight, the robustness claim does not test that axis.
- **Toward Rugix:** a Rugix release that adds multi-signer CMS, a documented anti-downgrade floor and a working Jetson boot flow, together with a second active maintainer. The single-maintainer risk is what most clearly keeps Rugix out.
- **Against RAUC:** a second integrity-bypass advisory affecting the `verity` format, or Pengutronix ending or reducing its stewardship.
- **Holds the decision:** a OneMind proof of concept on Orin with RAUC 1.15.2 or later, verity only, a custom backend that switches slots atomically through `nvbootctrl` or the UEFI variables, and a passing forced-failure rollback test.

## 4. New sources opened in this review (not in the claim's source list)

| # | Source | What it shows | Integrity |
|---|---|---|---|
| N1 | https://github.com/rauc/rauc/security/advisories/GHSA-6hj7-q844-m2hx (also via api.github.com/repos/rauc/rauc/security-advisories/GHSA-6hj7-q844-m2hx) | CVE-2026-34155, High, signature bypass for plain bundles over 2 GiB; fixed in 1.15.2; published 2026-03-27 | sha256 of API JSON e63afea8537eda4f1d5b819571a99dd38ce6143f54e695e9a43101dac84eaf95 |
| N2 | https://github.com/home-assistant/operating-system/issues/4743 | HAOS: CRLs were never checked and are ineffective on-device; rotation preferred | PRIMARY (issue thread) |
| N3 | https://github.com/rauc/meta-rauc-community/commit/b89bdf3469c5c1b83ee3395547151beb1884102b | meta-rauc-tegra removed 2024-08-21; no upstream Jetson integration remains | PRIMARY, pinned SHA |
| N4 | https://api.github.com/repos/rugix/rugix/security-advisories (GHSA-f8wx-p63f-pp8h, GHSA-637r-qx4c-jm45) | Two High Rugix advisories in Oct 2026 | sha256 db9e51293ab45338c0f8bc272c6892430368a6ae683756c7ceb971bacf8d6d1b |
| N5 | https://github.com/home-assistant/operating-system/issues/4807 | Failed boots did not mark slot B bad because of a GRUB env mismatch (2026) | PRIMARY |
| N6 | https://github.com/home-assistant/operating-system/issues/5036 | RAUC boot-order changes ignored on legacy-BIOS x86; BIOS support declined | PRIMARY |
| N7 | https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/docs/reference.rst#L72-L90 , #L322 , #L811 , #L1146-L1150 , #L1761-L1763 | min-bundle-version caveats; check-crl; plain is the default format; ignore-version-limit | PRIMARY, pinned SHA |
| N8 | https://developer.ridgerun.com/wiki/index.php/RidgeRun_Platform_Security_Manual/Getting_Started/Over-the-Air/NVIDIA_Jetson_-_RAUC/Update_Flow_and_Custom_Bootloader | Orin RAUC needs a custom, non-atomic extlinux backend; noop backend mark-good has no effect on boot | SECONDARY (vendor wiki) |
| N9 | https://api.github.com/repos/rugix/rugix/commits?since=2025-11-10T00:00:00Z | 303 of 304 commits by one maintainer | PRIMARY (API) |

The commit count for the claim's own source was recomputed from https://api.github.com/repos/rauc/rauc/commits?since=2025-11-10T00:00:00Z: 512 commits, 15 distinct human logins.

`UNVERIFIED`: whether Mender OSS currently ships a maintained JetPack 6 integration. I did not open a primary source for it. The OE4T `tegrademo-mender` support I found is for JetPack 4 (SECONDARY, 2023 talk).
