# DC-12 · k3s inside the A/B image with a health-gated commit — longevity refuter

**Refuter:** REF4, lens **longevity and vendor risk** (RESEARCH-MISSION.md §2 rule 7) · **Date:** 2026-11-11 · **Verdict: weakened**

## Conclusion under test

`evidence/decision-critical.md` DC-12 and `01` §4.2 item 6: a safe design exists with k3s inside the read-only slot, the datastore on `data`, a fresh-signal gate (apps excluded, 3 tries, watchdog), a k3s-minor guard and no auto-retry. The gate passed under RAUC 1.13/1.15.x and Mender [C-LAB-rauc-1152-011, C-LAB-ubuntu-2604-leg-011, C-LAB-mender-014]. Cross-minor rollback (T-W3-03) has not run. `04` §7.4 adds "snapshot taken on 1.N before install; never skip a minor".

## Strongest counter-argument

The labs prove the gate catches a broken **platform** on a single release step. Over a 10-year support life the risk is in the steps the gate doesn't look at:

1. **The gate commits a box whose apps a k3s minor has broken.** Kubernetes removes API versions at specific minors (the deprecation guide lists removals at 1.22, 1.25, 1.27, 1.29 and 1.32 [C-REF4-DC-longevity-002]), and kubelet defaults flip too. The gate excludes apps by design, so a k3s minor that removes an API a Marketplace chart still uses passes the gate (k3s Ready, core pods Ready) and **commits**. After commit, `04` §7.4 allows rollback only by restoring the pre-update snapshot. On a fleet with third-party charts (E1) that is the most likely k3s-minor failure, and it is outside the gate.
2. **The trial runs on a copy of the k3s datastore, not of the apps' data.** Another A/B-style k3s appliance hit exactly this in November 2026: a k3s minor bump means "the rollback lands on a broken box", and system apps upgraded during the trial "may migrate their databases. After a rollback, the old images run on migrated data" [C-REF4-DC-longevity-001]. Its remedies (snapshot the datastore before the trial, hold app migrations until commit, ship k3s minors alone) match OneMind's for k3s but add one OneMind doesn't state: **no app or core-service schema migration until the OS commits**.
3. **"Never skip a minor" becomes a permanent publishing and hosting duty.** Kubernetes keeps three minors with about one year of patch support and forbids `kube-apiserver` from skipping a minor even on one node [C-REF4-DC-longevity-003]; k3s's own docs repeat the rule and say a previous-minor rollback needs a snapshot taken on that minor, "If you cannot restore the database, you cannot roll back" [C-REF4-DC-longevity-004]. With k3s inside the image, every image release that changes the minor is a mandatory stepping stone. A box offline for 18 months must walk 4–5 intermediate images in order, each through its own trial, gate and snapshot, and most of those images carry a k3s minor that is already out of patch support. Over 10 years that is about 30 stepping stones OneMind must keep signed, hosted and bootable on every board revision (and re-signable after any key rotation, E9). The design states the rule but costs neither the stepping path nor its retention.
4. **Vendor pace sets the OS cadence.** Because k3s is in the slot, the image cannot sit on a quiet LTS stream: the OS must ship at least three minor-bump images a year for as long as the box is supported, regardless of Debian's cadence.

None of this shows the design is unsafe on one step; it shows the "safe design exists" answer covers the step the lab ran, not the 10-year sequence.

## Verdict: weakened

The gate result stands (three engines, two bases). The conclusion is weakened because (a) the most likely real k3s-minor failure (API removal or default flip breaking apps) commits by design; (b) app data is not covered by the trial copy; (c) the mandatory stepping path is an uncosted, decade-long hosting and signing liability.

**Proposed changes (for the owner, not applied):** add to T-W3-03 a case where the new minor removes an API a test chart uses, and decide whether that blocks commit (an "app canary" check) or is caught by a pre-publish API scan of every installed chart against the target minor; hold app/core migrations until commit; write a stepping-path policy (which images are retained, for how long, and how an offline box discovers its path) into `04` and the cost model.

## What would flip it

- **To upheld:** T-W3-03 passes including an API-removal chart (blocked pre-install by a scan, or rolled back), plus a written, costed stepping-path retention policy and a demonstrated N→N+3 catch-up of an offline box.
- **To refuted:** a forced cross-minor rollback leaves k3s unable to start on the restored datastore, or an offline box cannot catch up without operator intervention.

## Sources (new in this refuter)

- librepod/os issue #21 (opened 2026-11-02, open): <https://github.com/librepod/os/issues/21>
- Kubernetes deprecated API migration guide: <https://kubernetes.io/docs/reference/using-api/deprecation-guide/>
- Re-cited (already in other ledgers): Kubernetes version skew policy <https://kubernetes.io/releases/version-skew-policy/>; k3s rollback and manual-upgrade docs <https://docs.k3s.io/upgrades/roll-back>, <https://docs.k3s.io/upgrades/manual>
