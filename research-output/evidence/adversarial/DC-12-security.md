# DC-12 refuter: security lens (REF4)

**Target:** DC-12, how the A/B layer and k3s interact (health-gated commit). **Lens:** security. **Date:** 2026-11-11. **Protocol:** RESEARCH-MISSION.md §2 rule 7; read only the DC-12 question and result in `decision-critical.md`, `01` §4.2 items 5, 6 and 8, and the cited lab claims (C-LAB-rauc-1152-011, C-LAB-ubuntu-2604-leg-011, C-LAB-mender-014). No earlier adversarial file was read first.

## Claim under test

"A safe design exists: k3s inside the read-only slot, datastore on `data`, fresh-signal gate (apps excluded, 3 tries, watchdog), k3s-minor guard, no auto-retry." The lab proves the gate tells a broken system from a working one under three engines and two bases.

## Strongest counter-argument

The labs test **safety against accidents**. They do not test **safety against an adversary**, and the same design features that make rollback safe turn into security problems.

1. **The gate is a denial-of-update primitive.** A failed gate rolls back and, by rule 8 ("no auto-retry"), marks the release bad on that device for good; `01` §4.2 item 3 says an abandoned trial is re-offered "never for a release the gate marked bad". Anything that can keep a core pod un-Ready, or the data partition from being read-write, for the 300 s trial window therefore pins the device to the old release **permanently**. Ways to do that: an app that starves core pods (apps are excluded from the gate *verdict* but not from the node's resources), a full `data` partition, or a network-reachable crash in a core pod. If the release being blocked is a security fix, this is TUF's freeze attack moved from the metadata to the health check. The DC-12 lab never ran an *induced* gate failure by a hostile app; all bad cases were bad images.
2. **The older slot is a signed, bootable downgrade target.** After a good commit the previous slot stays valid for fallback. RAUC can retire it (`prevent-late-fallback` marks the other slot bad after `mark-good`) and can refuse older bundles (`min-bundle-version`), but both are **off by default**, and RAUC's own reference warns that a version floor conflicts with rollback [C-REF4-DC-security-001]. Neither appears in DC-12's answer. Anyone with root on the box (or physical access to the boot menu on the GRUB route) can switch to the older slot, which carries an older kernel and an older k3s with known CVEs, all still validly signed. Real-world precedent: Windows Downdate turned the OS's own update path into a way to "unpatch" a fully patched machine [C-REF4-DC-security-003], and bitpixie still extracts BitLocker keys by booting an old, still-trusted boot loader, because revoking old signed boot files is limited by firmware revocation space [C-REF4-DC-security-002]. ADR-001's per-slot signed UKIs have the same property until SBAT or a TPM policy refuses the old slot.
3. **The cross-minor guard collides with anti-rollback.** `07` SEC-05 requires an anti-rollback counter; DC-12's safety depends on falling back to an *older* k3s and, for a cross-minor case, restoring an older datastore snapshot. Those are the two cases RAUC's docs flag as conflicting [C-REF4-DC-security-001]. The snapshot restore path also re-exposes the data partition to older k3s code that will read current secrets. T-W3-03 (cross-minor rollback) has not run, so the one case where rollback and anti-rollback disagree is unproven.

## Verdict: **weakened**

The functional claim (a gate that separates working from broken updates) is well supported. The word "safe" is not, from a security view: the design has no stated defence against an attacker forcing a rollback, keeping a device on a vulnerable release, or booting the retained older slot. These are fixable, not flips, so D3/D4 stand.

## What would flip it

- **To upheld:** a lab (VM is enough) showing (a) `prevent-late-fallback=true` plus a `min-bundle-version` floor raised by each security release, with the cross-minor rollback (T-W3-03) still working inside the trial window; (b) a hostile in-cluster app that starves core pods during the trial does **not** permanently block the release: the device re-offers it with a bounded counter and raises an alert, distinguishing "image bad" (kubelet or k3s never healthy) from "environment bad"; (c) on the `efi` route, the older slot's UKI refused after commit (SBAT generation bump or a TPM PCR policy that no longer unseals `data`).
- **To refuted:** a design where cross-minor recovery needs the older slot to stay bootable after commit, so that retiring it (above) makes k3s upgrades unrecoverable; then DC-12's own flip condition (k3s outside the A/B image, or a different update model) is back in play.

## Sources (new, opened)

- RAUC reference, `min-bundle-version` and `prevent-late-fallback`: https://rauc.readthedocs.io/en/latest/reference.html [C-REF4-DC-security-001]
- heise on bitpixie downgrade (38C3): https://heise.de/-10221824 [C-REF4-DC-security-002]
- The Hacker News on Windows Downdate, CVE-2024-21302: https://thehackernews.com/2024/08/windows-downgrade-attack-risks-exposing.html [C-REF4-DC-security-003]
