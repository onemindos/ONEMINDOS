# Adversarial review: W4 P0-2 (security lens)

- **Conclusion under test (05-kubernetes-cluster-conversion-nvidia.md, P0-2):** k3s is the default distribution, and RKE2 is the GPU/AI-conformant and regulated tier. On the frozen weighted scorecard, k3s (63), RKE2 (62) and Talos-native Kubernetes (61) are a statistical tie. The gates settle it: RKE2 needs 4 GB minimum and 8 GB recommended, Talos has no merged Jetson Orin support, and k3s passes every gate. Stated confidence: medium (fragile under weights).
- **Cited claims:** C-W4-012, -038, -064, -072, -073.
- **Refuter lens:** security and compliance (FIPS, STIG, CIS, crypto-module lifecycle, the cost of patching two distributions).
- **Date:** 2026-11-11. Re-check by: 2027-05-10. CMVP status and the RKE2 FIPS docs move with releases.
- **Verdict: `weakened`.** The facts it cites hold. The gates still rule RKE2 and Talos out of nodes under 8 GB. But under a security lens, "k3s passes every gate" holds only because the gate set has **no compliance gate**. And "RKE2 is the regulated tier" is under-specified: the FIPS boundary depends on the RKE2 version, the CNI and the ingress chosen, and the older FIPS 140-2 basis went Historical on 2026-09-21.

## 1. Re-check of the cited sources (2026-11-11)

| Claim | Re-check | Status |
|---|---|---|
| C-W4-038: AI conformance lists rke2 for v1.34-v1.37, talos for v1.34 and v1.37, k0s for v1.35-v1.36, no k3s | `gh api repos/cncf/k8s-ai-conformance/contents/<v>?ref=c64e5bc...`: rke2 is in all four, talos in v1.34 and v1.37, k0s in v1.35 and v1.36, no k3s | **Confirmed** |
| C-W4-064: Talos Jetson Orin is open PR #23 | `gh api repos/siderolabs/sbc-jetson/pulls/23`: state `open`, created 2026-02-02T03:09:09Z, not merged | **Confirmed** |
| C-W4-072: RKE2 4 GB min / 8 GB recommended; validated OS SLES 16, RHEL 10, Ubuntu | docs.rke2.io/install/requirements, opened 2026-11-11: same | **Confirmed** |
| C-W4-012, -073 (lifecycle, conformance) | Not re-run; no contrary evidence found | Accepted |

## 2. Strongest counter-argument

"OneMind is a NATS-native C2/ISR system. For a defense-adjacent buyer, FIPS-validated crypto, a DISA STIG and CIS-by-default are the entry ticket, not an optional tier. Of the three tied candidates, only RKE2 has them. The SUSE RKE2 docs and SUSE's own comparison place RKE2 as the security- and compliance-focused distribution, and k3s has no FIPS build and no STIG. A tie on a weighted scorecard should break toward the option that makes the compliance story possible. The default should be RKE2 on every node that can hold it (8 GB or more), with k3s only as a constrained-device exception. Running two distributions as equal tiers also doubles the security work: two hardening baselines, two CVE feeds, two upgrade matrices, and two sets of bundled containerd/runc to track."

## 3. Findings

### 3.1 The gate set has no security or compliance gate
P0-2 settles the tie with resource and hardware gates only. If a "FIPS-validated crypto available" gate existed, k3s would **fail** it. The RKE2 FIPS pages describe a BoringCrypto/GoBoring build for RKE2, and none of the k3s docs I opened offer an equivalent. So "k3s passes every gate" is true only for the gates chosen. That should be stated, because the result is described as fragile under weights.

### 3.2 "RKE2 = regulated tier" needs a version, CNI and ingress qualifier
- The RKE2 FIPS 140-2 page (docs.rke2.io/security/fips_support) cites BoringCrypto **CMVP certificate 4407**. The NIST CMVP record for #4407 (opened 2026-11-11) is **FIPS 140-2, status Historical** ("Moved to historical list due to sunsetting"). NIST's CMVP transition moved all 140-2 certificates to Historical on 2026-09-21. Historical modules may stay in existing systems but are not for new procurements.
- The SUSE RKE2 "FIPS 140-3 Enablement" page cites **CMVP certificate 4968**. That certificate is **FIPS 140-3, Active, sunset 2029-07-22**, "SUSE Rancher Kubernetes Cryptographic Library", validated 2025-02-20. So a current basis exists. But the page does not say which RKE2 versions are built against it.
- Both pages say **"only Canal is rebuilt for FIPS compliance"**: Calico, Cilium and Multus are outside the boundary. Both pages also list Calico among the FIPS-built charts, which contradicts this. If OneMind picks Cilium (Hubble already runs on the DOKS hub), RKE2 nodes leave the FIPS boundary.
- The RKE2 docs state that **ingress-nginx reached EOL in March 2026**, with CVE fixes only on RKE2 v1.32-v1.36, and recommend Traefik. Any "regulated tier" design must name Traefik and an RKE2 version within that support window.
- The STIG: search results say a DISA STIG for RGS RKE2 exists (stigviewer listing; the page returned HTTP 403 to me) and that a STIG-aligned "RKE2 Government" build is in technical preview for RGS customers only (executivebiz, not opened). Both are **unverified** here.

### 3.3 The two-tier design is a real patch-load cost but not disqualifying
k3s and RKE2 share upstream Kubernetes and SUSE release cadence (C-W4-012). The runc escapes CVE-2025-31133/52565/52881 had to ship through both distributions' bundled runtimes. Doubled triage is real but modest. It does not refute the split.

### 3.4 What the security lens does not change
RKE2 at 4 GB min / 8 GB recommended (C-W4-072) and Talos with no merged Orin support (C-W4-064) remain hard blockers for small and Jetson nodes. Neither FIPS nor STIG changes physics. So k3s on 4-8 GB nodes stands. What is weakened is whether k3s should also be the *default* on nodes of 8 GB or more in a C2/ISR product.

## 4. New sources (searched for lifecycle cuts, sunsets and CVEs; all opened 2026-11-11 unless noted)

1. NIST CMVP certificate #4407, BoringCrypto, FIPS 140-2, **Historical**. https://csrc.nist.gov/projects/cryptographic-module-validation-program/certificate/4407. PRIMARY.
2. NIST CMVP certificate #4968, SUSE Rancher Kubernetes Cryptographic Library, FIPS 140-3, Active, sunset 2029-07-22. https://csrc.nist.gov/projects/cryptographic-module-validation-program/certificate/4968. PRIMARY.
3. RKE2 FIPS 140-2 page (cert 4407, Canal-only CNI). https://docs.rke2.io/security/fips_support. PRIMARY.
4. SUSE RKE2 FIPS 140-3 Enablement (cert 4968, Canal-only, ingress-nginx EOL March 2026). https://documentation.suse.com/cloudnative/rke2/latest/en/security/fips3_support.html. PRIMARY.
5. k3s CIS hardening guide: not CIS-passing by default. https://docs.k3s.io/security/hardening-guide. PRIMARY.
6. NIST CMVP project page (140-2 to Historical on 2026-09-21). https://csrc.nist.gov/projects/cmvp. PRIMARY. Seen through search results, not opened.

## 5. What would flip the decision

- **Toward `refuted` (RKE2 should be the default on nodes of 8 GB or more):** a written OneMind target market or contract requires FIPS 140-3 and/or a DISA STIG on every node class that can run RKE2, or Zeus decides compliance is a P0 product property. Then the tie breaks to RKE2 above 8 GB, and k3s becomes the constrained exception.
- **Toward `upheld`:** OneMind states that no FIPS or STIG requirement applies before the regulated tier is sold, *and* the regulated tier is pinned as "RKE2 vX.Y built against CMVP #4968, Canal CNI, Traefik ingress, CIS profile", with a dated SUSE document proving the version-to-certificate mapping.
- **Also relevant:** a k3s FIPS 140-3 build appearing (removes the compliance gap), or CMVP #4968 being revoked or moved to Historical (removes RKE2's edge).
