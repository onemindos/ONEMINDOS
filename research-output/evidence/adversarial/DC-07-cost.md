# DC-07 refuter: one update framework across x86, Pi 5 and Jetson (cost and business lens)

| Field | Value |
|---|---|
| Target | DC-07 (Q6, Q47). Conclusion in `evidence/qbank/W3.md` (Q6, Q47) and `04-image-install-updates-rollback.md` V2: "No off-the-shelf engine covers all three with stock NVIDIA Jetson Linux. Use **one OneMind release contract** (one manifest, one signing chain, one health gate, one UI) over **per-board backends**: RAUC on x86 and Pi 5, NVIDIA's rootfs A/B plus image-based OTA on Jetson." Confidence medium; the Jetson wrapper is unbuilt (T-W3-06, founder hardware). |
| Lens | Cost and business (sole developer, support load, RMA cost) |
| Protocol | RESEARCH-MISSION.md §2 rule 7. Only the conclusion and its cited claims (C-W3-013, 021, 049, 050, 051, 052, 053, 054, 055; C-W7-017, 018) were read. |
| Date | 2026-11-10 (re-check by 2027-05-10) |
| Verdict | **weakened**. The negative finding (no single open engine on stock L4T) **holds**. The recommendation's cost is understated: it *is* the outcome DC-07 warned about (two update engines for one person to run), and NVIDIA's backend has documented field-unrecoverable failure modes and a factory-flash precondition that the conclusion does not price. |

## 1. Re-checking the cited sources

| Sub-claim | Ledger | Holds? |
|---|---|---|
| Rugix has no Jetson/Tegra integration | C-W3-013 (grep absence at pinned SHAs) | Yes, as a negative search |
| meta-rauc-tegra was removed in 2024 | C-W3-021 (commit b89bdf34) | Yes |
| Mender and SWUpdate reach Jetson only through Yocto meta-tegra | C-W3-053, C-W7-017, C-W7-018 | Yes |
| NVIDIA rootfs A/B has a validation hook, 3 tries and a recovery kernel | C-W3-049 | Yes |
| Image-based OTA resumes after power loss; `OTA_MAX_RETRY_COUNT` defaults to 0, then drops to a recovery shell | C-W3-051 | Yes. This is itself a cost signal: the default end state of a failed OTA is a **shell on a robot**, not an automatic rollback. |
| apt upgrade 35.x → 36.x is unsupported | C-W3-050 | Yes |

## 2. Strongest counter-argument

**"One release contract over per-board backends" moves the cost but does not remove it.** DC-07's stated risk was that "a sole developer maintains two or three update stacks" and "the moat platform gets the weakest updates". The recommendation accepts both:

- **Two engines, one wrapper.** RAUC on x86/Pi, NVIDIA `nvbootctrl` + image-based OTA on Jetson, and a OneMind layer that has to translate one manifest, one signature and one health gate into both. The wrapper is a third component the founder owns alone, and it is unbuilt.
- **NVIDIA's path has field-unrecoverable failure modes.** A documented case: an A/B-flashed Xavier received an OTA payload built without `ROOTFS_AB=1`, the bootloader update failed with "Heap corrupted", staff called the version path unsupported, and the only recovery was a USB reflash from an x86 host [C-REF-DC-cost-004]. That case is an old BSP (R32), but nothing in the cited docs shows a payload/layout check was added since. For a robot sold to a customer, "reflash from x86 over USB" is an RMA or a site visit.
- **A/B is a factory decision, not an update.** NVIDIA staff confirmed in August 2026 (Thor, R39.2.1 guide) that rootfs A/B **cannot be enabled by OTA**; it needs a full reflash [C-REF-DC-cost-005]. Stock JetPack and OE4T flash non-redundant layouts by default (C-W7-017). Any dev kit or early unit flashed without A/B is permanently outside the update system without a physical reflash.
- **The Jetson backend is exercised more often than the x86 one.** Jetson security fixes land in BSP point releases (35.6.4, 36.5, 38.4 for the March 2026 CVEs, CVSS up to 8.3) [C-REF-DC-cost-006]. Each one is a bootloader + rootfs image OTA through the least-proven backend.

**Why it is not refuted.** The alternatives cost more on the same lens. A single framework on Jetson (Mender, SWUpdate or RAUC) needs a Yocto meta-tegra build, which is a second *build system* rather than a second *updater*, and Mender's deltas are paid (C-W3-055). On current evidence the recommendation is still the cheapest of bad options. The flip condition ("a per-flavor framework costs more than switching the core framework") is not met, because no core switch removes the Jetson special case on stock L4T.

## 3. New sources (searched for OTA bricking, A/B failures and Jetson CVE cadence)

| ID | Source | What it shows |
|---|---|---|
| C-REF-DC-cost-004 | https://forums.developer.nvidia.com/t/ota-bricks-jetson-agx-xavier-industrial-when-writing-smd-partitions-without-any-checks/272692 | OTA with a mismatched payload bricked an A/B device; only USB reflash recovers it; no validation added in thread. |
| C-REF-DC-cost-005 | https://forums.developer.nvidia.com/t/can-a-single-partition-bootloader-support-a-b-partitioning-via-an-ota-update/380176 | Rootfs A/B cannot be enabled by OTA (NVIDIA staff, 2026-08). |
| C-REF-DC-cost-006 | https://nvidia.custhelp.com/app/answers/detail/a_id/5797/ | Jetson CVE fixes ship only as BSP point releases on each branch. |

## 4. What would flip the decision

- **Toward one framework (Mender or RAUC on Yocto meta-tegra for Jetson):** DC-09 moving the Jetson flavor to meta-tegra (see `DC-09-cost.md`, where the Canonical IP question makes that more likely than the conclusion assumes). Then re-score Mender or RAUC as the single engine.
- **Against the NVIDIA backend:** T-W3-06 on an Orin Nano showing that (a) the OneMind gate in `l4t-rootfs-validation-config` cannot block commit, or (b) a power cut or a mismatched payload leaves the unit needing USB reflash. Either one makes RAUC-with-a-custom-`nvbootctrl`-backend the fallback, and makes the cost of the Jetson tier a support-contract line.
- **Strengthens the conclusion:** T-W3-06 passing, plus the OneMind build refusing to sign any Jetson payload whose layout flags do not match the device's recorded layout (a cheap check that closes C-REF-DC-cost-004).

**Required additions:** (1) a factory rule that every Jetson unit is flashed with `ROOTFS_AB=1` and the redundant layout before shipping; (2) set `OTA_MAX_RETRY_COUNT` above 0 and price the "recovery shell" end state as an RMA in the H-1 model; (3) wrapper ownership listed as a sole-developer maintenance item.
