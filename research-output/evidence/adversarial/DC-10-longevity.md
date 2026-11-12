# DC-10 · Is k3s justified on every tier? — longevity refuter (round 4)

> **Refuter round 4 · lens: longevity and vendor risk · 2026-11-11.** Independent refuter (RESEARCH-MISSION.md §2 rule 7). Formed from the DC-10 Result in `decision-critical.md`, `01-FOUNDATION-DECISION.md`, the owning workstream file and the cited claim rows only; no earlier adversarial file was read first. New claims are in `evidence/claims/REF4-DC-longevity.csv`.

## Conclusion under test (rev. 3)
**k3s on every platform node** (≥ 4 GB RAM and SSD/NVMe); NATS leaf below; capturable field nodes agent-only; Market compiles to Helm and imports Compose. Lab: +936 MiB idle on a 4 GiB arm64 VM [C-LAB-k3s-footprint-restore-007].

## Strongest counter-argument
The footprint question was tested; the **upgrade-treadmill and steward** questions were not. Over 2027–2036 every platform node must follow Kubernetes' release train:

1. **About a year of patches per minor.** Kubernetes maintains three minors and gives each "approximately 1 year" of patches (1.35 EOL 2027-02-28, 1.37 EOL 2027-10-28) [C-REF4-DC-longevity-014]. A box shipped in 2027 and supported to 2036 must take roughly **25-30 minor upgrades**, one at a time (no skipping minors), each with API removals that can break Market apps. Docker/Compose (the HAOS and Umbrel choice) has no comparable forced cadence.
2. **The steward may change hands.** EQT is exploring a sale of SUSE, k3s's corporate steward, at up to USD 6 bn (March 2026) [C-REF4-DC-longevity-015]. k3s is a CNCF project, but its core helper kine is about 70% one SUSE engineer by human commits [C-REF4-DC-longevity-016]. A buyer that cuts edge Kubernetes would leave the smallest tier on a CNCF sandbox-level project with thin maintenance.

## Why it does not flip
The flip condition is about RAM (< 2 GB left on 4 GB) and flash writes; neither source touches it. Upgrade churn is also borne by every Kubernetes product (Olares, Talos, Kairos), and k3s releases patches for all three supported minors on the same day (v1.35.10/1.36.6/1.37.2 on 2026-11-03), so the treadmill is predictable. The steward risk has an exit (k0s, RKE2, upstream kubeadm all accept the same manifests).

## Verdict: **weakened**
- Required change: add the minor-upgrade cadence to the cost model as a recurring task (≈ 3 OTA-carried k3s minors a year, each through the health gate), and make "app compatibility across a k3s minor" a Market CI gate.
- Required change: record SUSE ownership as a vendor risk with the named exits above.

## What would flip this verdict
- **To upheld:** T-W4 soak plus a measured, automated 3-minor upgrade run (e.g. 1.35 → 1.36 → 1.37 by RAUC bundle) with zero manual steps; or a k3s/SUSE extended-support offer for edge minors.
- **Towards a tiered D4:** the SUSE sale closing with k3s de-prioritised, or a minor upgrade that needs manual intervention on the single-box SQLite profile.

## Sources opened (new)
- https://kubernetes.io/releases/ [C-REF4-DC-longevity-014]
- https://www.techzine.eu/news/infrastructure/139465/suse-may-be-sold-again/ [C-REF4-DC-longevity-015]
- GitHub API, k3s-io/kine commits since 2025-11-11 at f82bd251 [C-REF4-DC-longevity-016]

Limit: SUSE's own k3s lifecycle table (suse.com/lifecycle) did not render for fetching; the upstream Kubernetes policy was used instead.
