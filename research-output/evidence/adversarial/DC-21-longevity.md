# DC-21 · The kernel route — longevity refuter (round 4)

> **Refuter round 4 · lens: longevity and vendor risk · 2026-11-11.** Independent refuter (RESEARCH-MISSION.md §2 rule 7). Formed from the DC-21 Result in `decision-critical.md`, `01-FOUNDATION-DECISION.md`, the owning workstream file and the cited claim rows only; no earlier adversarial file was read first. New claims are in `evidence/claims/REF4-DC-longevity.csv`.

## Conclusion under test (rev. 3)
**K1** (the board maintainer's kernel: Debian stock, Raspberry Pi's, NVIDIA L4T) at launch with a CI kernel contract; **K2-hybrid** (OneMind-built LTS) for the first Secure Boot release with out-of-tree modules [C-DEC-008…010]. K1 wins S5 14/14 [C-W18-001, C-W18-003, C-W18-012].

## Strongest counter-argument
K1's score assumes "the board maintainer" carries the kernel for the support period. The 2023–2026 record says upstream support is shorter, the fix volume is far higher, and two of the three maintainers move on their own schedule.

1. **Upstream LTS is shrinking.** In 2023 the kernel community announced LTS support dropping from six years to two [C-REF4-DC-longevity-019]; current projections give 6.12 and 6.18 end Dec 2028 [C-STEEL-KRU-009], while Debian 13 runs to 2030 (LTS) and its ELTS tail backports *newer* kernels — confirmed only for amd64 [C-REF4-DC-longevity-003]. After 2028 the x86/arm64 kernel is Debian's own backport, and arm64 after 2030 has no published owner.
2. **The fix volume makes "stock kernel, take updates" a weekly job.** The kernel CNA issues roughly 50–60 CVEs a week, with 432 IDs in two days in July 2026; Kroah-Hartman's advice is to update or "pay a company to provide the needed support" [C-REF4-DC-longevity-020, C-REF4-DC-longevity-022]. Under K2-hybrid a one-person company becomes that company.
3. **The Pi tier's kernel is not Debian's.** Raspberry Pi moved its kernel from the 6.12 series to 6.18.34 in June 2026, inside the Debian 13 release [C-REF4-DC-longevity-021]. K1 on the Pi tier means a major kernel jump whenever Raspberry Pi decides, which breaks the "Debian-stable kernel" premise and DC-16 driver packs alike.

## Why it does not flip
The flip condition is "stock kernels can't cover the declared period but a CIP or OneMind LTS can **at solo-developer cost**". The counter cuts against every route: K2 has the same weekly CVE load and no Pi 5 mainline proof; K3 CIP 6.12 runs to 2035 [C-W18-003] but scored 2 on adoption and needs membership. K1 still costs least *at launch*.

## Verdict: **weakened**
- Required change: the kernel contract must treat a **major kernel jump inside a Debian release** (Pi 6.12 → 6.18) as a normal event: driver packs rebuilt and gated per kernel ABI.
- Required change: state that the 2028–2030 x86/arm64 kernel is Debian's backport and post-2030 arm64 has no owner; bring the CIP SLTS 6.12 (to 2035) quote forward as the costed answer for the arm64 tail, not only for industrial SKUs.

## What would flip this verdict
- **To upheld:** a published Debian kernel-team or Freexian commitment covering arm64 through 2035, and T-W18-4 showing a < 1 h weekly kernel bump including Pi.
- **To refuted (move to K3 for arm64):** CIP membership priced within the solo budget plus a Pi 5 or target arm64 board accepted as CIP reference hardware.

## Sources opened (new)
- https://linuxiac.com/linux-lts-kernels-moves-to-two-year-support-period/ [C-REF4-DC-longevity-019]
- https://www.noze.it/en/insights/432-linux-kernel-cves-two-days/ [C-REF4-DC-longevity-020]
- https://linuxiac.com/raspberry-pi-os-june-update-lands-with-linux-kernel-6-18-lts/ [C-REF4-DC-longevity-021]
- https://www.cncf.io/news/2024/08/22/the-linux-security-team-issues-60-cves-a-week-but-dont-stress-do-this-instead/ [C-REF4-DC-longevity-022]
- https://www.freexian.com/lts/extended/docs/debian-13-support/ [C-REF4-DC-longevity-003]
