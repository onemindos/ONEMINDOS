# W8 P0-2 refuter: longevity and vendor risk

| Field | Value |
|---|---|
| Claim | P0-2 (`09-iot-mesh-offgrid-tak.md` §0): IEC 62443-4-2 does not require the Red Hat lineage. A Debian 13-based OS (Moxa MIL4) holds a 62443-4-2 SL2 certification declaration (2026-07-02). The Debian-based CIP project announced 62443-4-1 and 4-2 compliance (2026-09-28). Certification attaches to a product, never to "an OS". The author rates this High (vendor-published; certificate PDFs not opened). |
| Lens | Longevity and vendor risk: whether the Debian precedent carries over to Debian 13 + Rugix, and for how long. |
| Protocol | RESEARCH-MISSION.md §2 rule 7. The refuter read only the P0 row and the cited claims C-W8-033, 034, 035 and 063. It re-opened the Moxa and Linux Foundation pages. It did not read the author's reasoning or the other adversarial files before forming this view. |
| Date | 2026-11-11. Re-check the 62443-4-2 amendment status by 2027-05-11. |
| Verdict | **weakened**. The headline sentence holds. The confidence rating and the implied transfer to Debian + Rugix do not. |
| New ledger rows | `evidence/claims/REF-W8-longevity.csv` (C-REF-W8-longevity-006…009) |

## 1. Re-checking the cited sources

| Cited claim | Re-opened 2026-11-11 | Holds? |
|---|---|---|
| C-W8-033 (Moxa MIL4) | The page lists "IEC 62443-4-2 Security Level 2 Certification for UC-1200A, UC-2200A, UC-3400A, UC-4400A, UC-8600A Series with MIL4", with document type **Declaration**, v1.0, dated 2026-07-02. **No issuer or certification body is named.** MIL4 support runs to Aug 2035 and is delivered through paid subscriptions. Moxa is a CIP member [C-REF-W8-longevity-008]. | **Partly.** It is a Debian 13 precedent, but it covers Moxa hardware, Moxa's configuration and Moxa's paid 10-year patch service. Whether a third party assessed it is unverified. |
| C-W8-034 (CIP press release) | The release says CIP "has achieved compliance with IEC 62443-4-1 and IEC 62443-4-2". **It names no assessor, no certificate and no specific artifact** (kernel, CIP Core release or reference image) [C-REF-W8-longevity-006]. | **Weaker than stated.** It is an announcement, not a certificate. |
| C-W8-035 (IEC webstore) | The 2019 edition has a stability date of 2027. | Yes. See §2 C for what follows. |
| C-W8-063 (RHEL precedent) | A secondary source, reused and not re-opened by the author. | Not tested here. |

## 2. Strongest counter-argument

The sentence "62443-4-2 does not require the Red Hat lineage" is true and was never in serious doubt, because certification attaches to products. But the conclusion's job in the decision chain is to support DC-02/G4 for **Debian 13 + Rugix + k3s**. On the vendor and longevity axis, neither precedent carries over to that stack.

**A. CIP's 4-2 evidence is tied to CIP's own update stack, not Rugix.** CIP's published 62443-4-2 assessment, FR-3, covers software update (EDR/NDR 3.10 and RE(1)). It meets that requirement with "SWupdate framework installed in the CIP image", with instructions in `isar-cip-core`. Users "can use SWUpdate method" with "no further actions required". Users of other update methods must address the requirement themselves [C-REF-W8-longevity-007]. So a Debian 13 + Rugix product does not inherit CIP's update evidence, and OneMind would have to write its own. CIP's claimed "up to 70% less compliance effort" [C-W8-034] assumes the CIP reference stack.

**B. The Moxa precedent shows a 10-year paid patch commitment, which OneMind does not yet have.** 62443-4-2 CR 3.10 (support for updates) and 4-1's security-update management are only credible with a supported base. Moxa offers that until Aug 2035 through subscriptions. Debian's own support for trixie ends 2030-06-30. After that, Freexian ELTS runs to 2035-06-30, but only amd64 is confirmed, and base packages are covered only "as long as we have customers paying" [C-REF-W8-longevity-003, see the W8-P0-1 file]. The 62443 path on Debian exists, but it is a paid, vendor-run path, as it is on RHEL.

**C. The standard itself is moving.** IEC 62443-4-2:2019 reaches its stability date in 2027 [C-W8-035]. A CENELEC draft amendment, EN IEC 62443-4-2:2019/prAA:2026 (CLC/TC 65X), is listed in standards catalogues with updated and new requirements and an evaluation methodology, aimed at CRA alignment [C-REF-W8-longevity-009]. The catalogue pages did not render for this refuter, so this row is SECONDARY and low confidence. If the amendment is adopted, a 2026 declaration made against the 2019 text may need to be re-assessed. The "Moxa holds it" precedent is therefore dated.

**Why this is not "refuted".** Nothing found here shows that 62443-4-2 needs Red Hat, or that an assessor rejects Debian. The RHEL precedent (C-W8-063) is just as product-bound and just as dependent on a paid vendor. The headline survives. What fails is the **High** rating ("certificate PDFs not opened", no assessor named for CIP) and any reading that Debian + Rugix inherits a ready-made 62443 path.

## 3. Required changes for the author

1. Lower the confidence to **Medium** until the Moxa declaration PDF has been opened and its issuer (third party or self-declared) is recorded, and until CIP's assessor or certificate is identified.
2. Add one line: the CIP 4-2 evidence assumes SWUpdate and isar-cip-core, so Rugix-based products must produce their own CR 3.10 and 3.4 evidence.
3. Record the 62443-4-2 amendment and CRA-alignment work as a re-check item with date 2027-05.

## 4. What would flip the decision

- **Towards refuted:** an assessor's or CIP's statement that the 4-2 compliance applies only to CIP Core images built with Isar, SWUpdate and the SLTS kernel. Or the Moxa declaration turns out to be a self-declaration with no third-party assessment. Either would leave "Debian 13 + 62443-4-2" with no independently assessed precedent outside a vendor's closed stack.
- **Towards upheld at High:** the Moxa PDF names a certification body (for example TÜV or Bureau Veritas) and covers Debian 13 user space. Or CIP publishes a certificate number and an assessor. Or any 62443-4-2 assessed product ships a non-SWUpdate A/B updater (Rugix, RAUC or Mender) on Debian.

## 5. Sources opened by this refuter (new)

- https://cip-documents.readthedocs.io/en/stable/iec-62443-assessment/iec-62443-4-2/iec-62443-4-2-fr-3.html
- https://www.linuxfoundation.org/press/civil-infrastructure-platform-achieves-significant-cybersecurity-milestone-with-iec-62443-compliance (re-read)
- https://www.moxa.com/en/products/industrial-computing/system-software/moxa-industrial-linux (re-read)
- https://www.freexian.com/lts/extended/docs/debian-13-support/
- https://ecommerce.sist.si/catalog/standards/clc/1a47afd0-dc92-42b0-8b9c-55b553b163af/en-iec-62443-4-2-2019-praa-2026 (did not render; content known from the search snippet only)

Not archived by this refuter. The author must archive these under rule 1.
