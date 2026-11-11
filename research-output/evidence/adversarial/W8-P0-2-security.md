# Adversarial review: W8 P0-2 (security lens)

- **Claim under test (09-iot-mesh-offgrid-tak.md §0):** IEC 62443-4-2 does not require the Red Hat lineage. A Debian 13-based OS (Moxa MIL4) holds a 62443-4-2 SL2 certification declaration (2026-07-02). The Debian-based CIP project announced 62443-4-1 and 4-2 compliance (2026-09-28). Certification attaches to a product (device + OS + configuration), never to "an OS". Cited: C-W8-033, 034, 035; C-W8-063. Confidence stated: High (certificate PDFs not opened).
- **Refuter lens:** security (certification scope, assessor independence, transferability).
- **Date:** 2026-11-10. Re-check by 2027-11-10.
- **Verdict: `upheld`** for the conclusion as worded: 62443-4-2 does not require Red Hat. **The supporting evidence is overstated and needs rewording.** The confidence should name what was and wasn't verified.

## 1. Re-check of cited sources

| Claim | Re-check (2026-11-10) | Status |
|---|---|---|
| C-W8-033 Moxa MIL4 | The Moxa page lists the MIL4 and MIL3 documents with "Certification" in the title, but their **type is "Declaration"**. The page names **no issuing body or certification body**. The scope is five Moxa UC series with MIL4. The page doesn't mention 62443-4-1. | Partly confirmed. "Holds a certification" is unproven; it could be a vendor self-declaration of conformance |
| C-W8-034 CIP | The LF release says CIP "has achieved compliance with IEC 62443-4-1 and IEC 62443-4-2". It names **no assessor, no SL, and no software scope**. Adopters keep product-specific responsibility. | Confirmed as an announcement; "compliance" ≠ certificate |
| C-W8-035 IEC 62443-4-2:2019 | Not re-opened (catalogue metadata) | n/a |

## 2. Strongest counter-argument

"Neither cited source shows an independent certificate for a Debian-based OS. Moxa's document is typed as a *declaration* with no named CB, and CIP's is a *press-release 'compliance'* with no assessor or SL. The only artefact in the file with a stated SL-C and a stated product scope is Red Hat's (C-W8-063). So the evidence fits an alternative reading: Red Hat has a third-party-certified OS component, and Debian derivatives have self-declarations. For a buyer whose procurement requires a CB certificate, that difference is what decides."

**Why it does not refute the conclusion:** the conclusion is a negative: the *standard* does not require a Red Hat lineage. It needs only one non-Red-Hat Linux product with an independent 62443-4-2 assessment, and such products exist:
- CIP's own Secure Development Process records that vulnerability and penetration testing of the CIP Security images "was carried out by a third party agency" (SVV-3/SVV-4). A secondary report says CIP finished its 4-1 assessment in August 2024 and its 4-2 assessment in February 2026; I could not confirm those dates on CIP's own pages.
- Phoenix Contact's PLCnext Control (a Linux-based controller) is certified by **TÜV SÜD** to 62443-4-1 ML3 combined with 4-2. The certificate is bound to firmware "2024.0 LTS" and requires a Security Profile to be activated to reach SL2. This is independent evidence for the file's last sentence: certification attaches to a product + version + configuration. The standard places no requirement on OS lineage.

So the counter-argument hits the *evidence quality*, not the conclusion.

## 3. Security-lens findings (new evidence)
1. **CIP's assessed scope is Debian 12 + CIP kernel 6.1.x, not Debian 13.** SM-3: the TSC "agreed upon Debian 12 (Bookworm) as the version for the base layer of CIP-Core component and 6.1.x version for the CIP Kernel for IEC-62443-4-1 and 4-2 certification." The file's wording "the Debian-based CIP project" is accurate. Any implication that the result carries over to OneMind's Debian 13 + stock 6.12 kernel + Rugix is not supported (see W8-P0-1-security.md §3.2).
2. **4-2 test evidence covers only CIP's added security packages.** CIP's test documentation says only the packages "included in CIP to meet IEC 62443-4-2" are captured, not the 100+ package base system.
3. **Certificates are version-pinned.** PLCnext's certificate covers specific firmware versions and has needed recertification. A rolling A/B update stream (Rugix, R-1) changes the certified configuration with every release. OneMind's 4-1 process would have to cover this, and no base OS removes that cost.

## 4. New sources (searched for scope limits, missing assessors and recertification; opened 2026-11-10)
1. CIP Secure Development Process, SM-3 and SVV-3/4: https://cip-documentation.readthedocs.io/en/latest/process/secure_development_process.html. PRIMARY.
2. CIP upstream test results, 4-2 package scope: https://cip-documents.readthedocs.io/en/latest/testing/core/upstream_test_results.html. PRIMARY.
3. PLCnext IEC 62443-4-2 compliance list (firmware-version-bound): https://security.plcnext.help/se/IEC_62443-4-2_compliance_list.htm, and the TÜV SÜD award coverage: https://www.controldesign.com/connections/cybersecurity/news/11289531/phoenix-contact-receives-iec-62443-certificate-for-plcnext-control-by-tuv-sud. PRIMARY / SECONDARY. (Not Debian-based; used only for the "no lineage requirement / product-bound" point.)
4. Moxa MIL page, re-read for document type: https://www.moxa.com/en/products/industrial-computing/system-software/moxa-industrial-linux. PRIMARY.

## 5. What would flip the decision
- **To WEAKENED/REFUTED:** the Moxa MIL4 PDF turns out to be a vendor self-declaration with no CB, *and* CIP's 4-2 assessment has no CB report, *and* a 62443 CB or IECEE scheme document requires a pre-certified OS component that only RHEL holds. (No evidence of this last point was found; the standard assesses components, not OS lineage.)
- **To UPHELD at High confidence:** open the Moxa MIL4 declaration PDF and CIP's assessment report and record the CB name, SL-C and certificate number for each.
- **Required wording changes:** "holds a 62443-4-2 SL2 certification **declaration (type: Declaration, issuer not named on the product page)**". "CIP announced compliance **for Debian 12 + CIP kernel 6.1.x**". Drop "High" to "Medium-High" until the PDFs are opened.
