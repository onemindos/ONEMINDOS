# DC-03 refuter: lifecycle cost to 2036 (robotics lens)

| Field | Value |
|---|---|
| Target | DC-03. Current answer (01 §3.1.5; 03 §6.2): Debian 13 costs **$0 if rebased to 14/15 in the field**; ELTS is not usable for a fleet as-is; Ubuntu needs unpublished Pro for Devices after 2031; Alma is $0 to 2035. Ranking **A ≈ C > D**. |
| Cited claims | C-W2-001, -002, -003, -004, -005, -006, -013 |
| Lens | Robotics fit: arm64 robots, Pi 5 (Lite) and Jetson nodes, fielded for years |
| Protocol | RESEARCH-MISSION.md §2 rule 7. I read only the conclusion and its cited claims before forming this view. |
| Date | 2026-11-10. Re-check by 2027-05-10. |
| Verdict | **weakened** |

## 1. Cited sources re-checked

The cited lifecycle rows (C-W2-001, -005, -013) and the Freexian terms (C-W2-002…004) are consistent with what they claim. My objection is not with these rows. It is that the cost model prices only the Debian archive, while a robot image also depends on packages Debian does not ship.

## 2. Strongest counter-argument

The "$0 if rebased" answer assumes that each rebase is free and that Debian's own LTS window governs the cost. On the boards a robot actually uses, neither holds:

1. **The Pi 5 kernel follows Raspberry Pi's cadence, not Debian's.** On the Lite/robot tier the kernel and firmware come from archive.raspberrypi.com (C-W2-044). A Raspberry Pi engineer states that the previous OS release (bookworm) gets "some updates … limited to security fixes … until we release Forky", with no dated period [C-REF-DC-robotics-009]. By that rule, trixie's Pi kernel line gets security fixes only until Raspberry Pi ships the release after forky, about 2029–2030. That is before Debian 13 LTS ends (2030-06-30), and ELTS excludes external packages anyway (C-W2-004). So on Pi the rebase is **forced on Raspberry Pi's two-release window**, not optional at 2030. Each forced rebase costs engineering and field-validation time, and the model prices that at $0.
2. **arm64 LTS coverage for trixie is not yet committed.** The Debian LTS wiki lists trixie's LTS architectures as "to be determined" (bookworm's list includes arm64) [C-REF-DC-robotics-010]. The free 2028–2030 window for arm64 robots is likely but not guaranteed.
3. **The Jetson flavor is outside the model, and its security fixes come as full BSP upgrades.** NVIDIA's March 2026 bulletin ships fixes for three CVEs only as new Jetson Linux releases (35.6.4, 36.5, 38.x) [C-REF-DC-robotics-001]. NVIDIA staff declined to name the fixed package, which leaves a full BSP upgrade as the only documented remedy [C-REF-DC-robotics-002]. The cost to 2036 of a mixed robot fleet is therefore dominated by Jetson BSP-upgrade cadence and Pi rebases, and neither appears in the A/C/D comparison.

**Effect:** the ranking A ≈ C > D probably survives, because Ubuntu and Alma share the Pi and Jetson problems (Ubuntu's Pi kernel is Canonical's, and its Jetson half is NVIDIA's). But "$0" overstates Debian's advantage. The true answer is "$0 in licences, with a rebase every about 2 years on Pi and a BSP upgrade per NVIDIA security release on Jetson". That cost is the same order as one Pro-for-Devices quote for a small fleet.

## 3. New sources (searched for lifecycle cuts and failures)

- Raspberry Pi Forums, "Security updates for Bookworm now that it's oldstable", reply by a Raspberry Pi engineer, 2025-08-26: https://forums.raspberrypi.com/viewtopic.php?t=391247 [C-REF-DC-robotics-009]
- Debian wiki, LTS: https://wiki.debian.org/LTS (trixie LTS architectures "to be determined") [C-REF-DC-robotics-010]
- NVIDIA Security Bulletin, Jetson and IGX, March 2026: https://nvidia.custhelp.com/app/answers/detail/a_id/5797 [C-REF-DC-robotics-001]
- NVIDIA forum, CVE-2026-24148 partial-update question, 2026-04-20: https://forums.developer.nvidia.com/t/cve-2026-24148-which-specific-debian-package-contains-the-fix-and-is-a-partial-update-feasible-on-jetpack-36-4-3/367096 [C-REF-DC-robotics-002]

## 4. What would flip the decision

- **Toward D (Ubuntu):** Canonical publishes or quotes a Pro for Devices price that, over 10 years at 1k units, costs less than OneMind's estimated engineering cost of 3 or more in-field Pi rebases plus their validation. Ubuntu's Pi kernel would also need a support window longer than Raspberry Pi's n+1 window.
- **Against A:** Debian publishes the trixie LTS architecture list without arm64, or Raspberry Pi states a support window for trixie that is shorter than one release cycle.
- **Strengthens A:** Raspberry Pi commits in writing to a dated kernel-support period for its trixie packages, reaching at least 2030-06.
- **Needed in the model either way:** a line item for the engineer-days per rebase and per Jetson BSP upgrade, measured from the umbrelOS 12→13 path and from one lab BSP upgrade.
