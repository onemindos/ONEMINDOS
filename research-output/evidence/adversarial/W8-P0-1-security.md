# Adversarial review: W8 P0-1 (security lens)

- **Claim under test (09-iot-mesh-offgrid-tak.md §0):** Gate G4 is not failed by Debian 13 + Rugix + k3s. Its result is CONDITIONAL on four mitigations (Pi 5 PREEMPT_RT kernel variant, packaged FDO client, MQTT 5 broker app, 10k-device fleet test). DC-02's flip condition ("a G4 sub-check FAILs for Debian + Rugix and PASSes for an alternative") is not met. Cited: C-W8-001…006, 033, 037, 038, 044, 046, 049, 050.
- **Refuter lens:** security (IEC 62443 path, vulnerability response for the packages the gate relies on, update-engine trust chain).
- **Date:** 2026-11-10. Re-check by 2027-05-10.
- **Verdict: `weakened`.** The headline holds: nothing found here makes a G4 sub-check FAIL for Debian + Rugix while it PASSes for an alternative. But the evidence for two sub-checks is weaker on security grounds than the "High" confidence says, and the list of mitigations is incomplete. Debian's protocol packages cited as G4 coverage carry dozens of unfixed CVEs in trixie. The IEC 62443 sub-check rests on certifications of *other* Debian configurations. A fifth mitigation is needed.

## 1. Re-check of cited sources (only those bearing on security)

| Claim | Re-check | Status |
|---|---|---|
| C-W8-033 Moxa MIL4 62443-4-2 SL2 | Moxa page (fetched 2026-11-10): the documents are *titled* "Certification", but their document **type is "Declaration"**. The page names no issuing body. Hardware scope: UC-1200A/2200A/3400A/4400A/8600A only. | Confirmed as worded. "Holds a certification" overstates the source; see W8-P0-2-security.md |
| C-W8-034 CIP 62443-4-1/4-2 | The LF press release (2026-09-28) names no assessor, no security level, and no kernel, Debian release or image. Adopters keep "responsibility for the requirements specific to their own products and deployments". | Confirmed as worded; scope not stated by this source |
| C-W8-004/005 Debian packages open62541, mosquitto, nats-server | Packages exist as stated. Their security state is the problem (§3.1). | Confirmed; security-relevant gap |
| C-W8-046 Rugix fleet integrations | Not re-opened; the trust-chain issue is in §3.3 | n/a |

## 2. Strongest counter-argument

"G4 asks for a *path* to IEC 62443, not a certificate. On that path, Debian + Rugix is in the worst position of the candidates. The alternatives named in DC-02 have assessed artifacts: RHEL 9.6/MicroShift 4.21 holds SL-C 2 (C-W8-063), and CIP Core has a 62443-4-1 and 4-2 assessment. Debian 13 + Rugix has neither. It has only analogies, to a Moxa product on Moxa hardware and to a CIP build on a different Debian release and kernel. So the 62443 sub-check should be scored at least 'unproven' for Debian + Rugix and 'pass' for CIP Core (Isar) or RHEL image mode. That is close to the DC-02 flip condition."

**Why it falls short of a flip:** CONDITIONAL is not FAIL. A product-level certificate is earned by the product's owner on their own configuration (Moxa and Phoenix Contact certify *firmware versions with a security profile switched on*; see W8-P0-2-security.md). No candidate gives OneMind a transferable certificate. RHEL's SL-C 2 covers RHEL's own configuration, and OneMind would still need its own 4-1 process and its own 4-2 product assessment. The 62443 effort gap between the candidates is real, but nobody has shown that Debian 13 + Rugix *cannot* pass. So the gate result stands as CONDITIONAL. The 62443 sub-check confidence should drop from High to Medium.

## 3. Security-lens findings (new evidence)

### 3.1 The Debian protocol packages cited as G4 coverage are not security-maintained in trixie
- **nats-server 2.10.27-1 (trixie):** the Debian security tracker lists **25 CVEs as "vulnerable" in trixie** and fixed only in forky/sid. They include CVE-2026-29785 (unauthenticated panic through leafnode compression, CVSS 7.5, fixed upstream in 2.11.14/2.12.5) and CVE-2026-33246 (Nats-Request-Info header spoofing over leafnode connections). Leafnodes are the mechanism behind P0-5 and C-W8-050. The lab ran upstream v2.15.2, not the Debian package.
- **open62541 1.4.11.1-1 (trixie):** **23 CVEs unfixed in trixie, all "vulnerable (no DSA)"**. No Debian security advisory has been issued for them.
- **Consequence:** C-W8-004/005 prove that the *protocols are available* on Debian. They do not show a *secure* protocol stack. Any G4 "protocols" PASS must assume OneMind ships these brokers and stacks as upstream-pinned app containers with their own CVE response, not as Debian packages. This does not favour RHEL either, because RHEL ships neither nats-server nor open62541. So it is no flip, but it is an unlisted mitigation.

### 3.2 The CIP 62443 assessment is a different OS from the one proposed
CIP's own Secure Development Process (SM-3) says the TSC "agreed upon Debian 12 (Bookworm) as the version for the base layer of CIP-Core component" and "6.1.x version for the CIP Kernel for IEC-62443-4-1 and 4-2 certification". Vulnerability and penetration testing were done by a third party on "CIP Security images". CIP's test documentation also limits 4-2 test evidence to "packages included in CIP to meet IEC 62443-4-2", not the 100+ package base system. ADR-001 proposes Debian 13 with Debian's 6.12 kernel (including the RT flavour, C-W8-001) and Rugix. CIP's evidence does not cover that configuration. Reusing it means either adopting CIP Core / the CIP 6.1 SLTS kernel, which changes D2, or redoing the mapping yourself. Note also that CIP's 4-1 assessment covers *CIP's* development process, while OneMind still needs its own 4-1 ML.

### 3.3 The update engine's trust chain has already needed an emergency fix
Rugix Ctrl 0.8.0-rc.1 through 1.3.0 trusted compromised eMudhra intermediate CA keys through a trust store **compiled into the binary**. Updating `ca-certificates` did not fix it, so devices needed a new Rugix Ctrl binary (fixed in 1.3.1, 2026-10-21). For a 10k-device G4 fleet, the fleet-scale sub-check (e) must also cover "rotate a trust root across the whole fleet with no physical access". That is a security test, and the 10k fleet test as currently worded does not include it.

## 4. New sources (searched for CVEs, advisories, scope limits; all opened 2026-11-10)
1. Debian security tracker, nats-server: https://security-tracker.debian.org/tracker/source-package/nats-server (25 trixie CVEs "vulnerable"). PRIMARY.
2. GHSA-52jh-2xxh-pwh6 / CVE-2026-29785, NATS leafnode compression panic, High 7.5, patched 2.11.14/2.12.5: https://github.com/advisories/GHSA-52jh-2xxh-pwh6. PRIMARY.
3. Debian security tracker, open62541: https://security-tracker.debian.org/tracker/source-package/open62541 (23 trixie CVEs, no DSA). PRIMARY.
4. CIP Secure Development Process, SM-3 and SVV-3/4: https://cip-documentation.readthedocs.io/en/latest/process/secure_development_process.html. PRIMARY.
5. CIP upstream test results (4-2 scope limited to added packages): https://cip-documents.readthedocs.io/en/latest/testing/core/upstream_test_results.html. PRIMARY.
6. Rugix, eMudhra CA key compromise guidance (2026-10-21): https://rugix.org/blog/emudhra-ca-key-compromise/. PRIMARY (vendor).

## 5. What would flip the decision
- **To REFUTED (G4 FAILS, DC-02 met):** a 62443-4-2 assessor or CB states in writing that a Debian 13 stock-kernel + Rugix host can't be assessed at SL-C 2 (for example because of the patch-support window or the unreviewed update engine) while accepting CIP Core/Isar or RHEL image mode for the same device. Or a Pi 5 PREEMPT_RT build fails LAB-W7-1 while an alternative passes on the same board.
- **To UPHELD as written:** OneMind's protocol stack ships from upstream-pinned containers with a documented CVE SLA (closing §3.1); a 62443-4-2 gap analysis of the Debian 13 + Rugix image maps every SL-C 2 requirement to a feature; and the 10k fleet test includes a fleet-wide trust-root rotation (closing §3.3).
- **Required edit even if upheld:** add a fifth mitigation, "protocol brokers and stacks ship as upstream-pinned app images, not Debian packages". Lower the 62443 sub-check to Medium.
