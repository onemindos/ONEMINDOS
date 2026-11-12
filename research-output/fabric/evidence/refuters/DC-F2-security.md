<!-- SPDX-License-Identifier: Apache-2.0 -->
# DC-F2 refuter, security lens

**Claim given:** as DC-F2. **Cited:** C-FB4-003, C-FB4-004, C-FB4-006.

**Strongest counter-argument.** A fleet hub that every site trusts is a single target that can push to every site, and the registration step of pull-based tools is where the attacks land. Fleet published, within two months of 2026, a critical privilege escalation to cluster-admin through its agent-management controller, a high-severity cluster identity takeover in cluster registration, and cross-tenant BundleDeployment and Secret disclosure via spoofed cluster labels during agent-initiated registration [C-FBREF-011]. Labels are exactly what ring selection uses.

**New sources:** C-FBREF-011 (three Fleet GHSAs with patched versions).

**Verdict: weakened.**

**What would flip it:** a fleet hub design in which a compromised hub can still not make a site act without that site's owner (then the risk is bounded) — or, the other way, evidence that sites cannot verify releases independently of the hub (then "many clusters with a hub" is no safer than one cluster).

**Response (author).** Accepted, and it shapes the design: (1) the fleet hub holds *desired state and rings*, never site credentials that act (`07-…` A8); (2) releases are signed by OneMind's release keys (TUF, contract §12.13), so a site verifies a release independently of the hub; (3) ring membership is decided on the fleet hub from the site's enrolment record, never from labels the site reports about itself; (4) if Fleet is used for enterprise sites it must be ≥ v0.16.3 (all three advisories patched) and on the advisory feed.
