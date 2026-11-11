# DC-23 refuter: Talos or Kairos instead of Debian + Rugix + k3s (cost and business lens)

**Target:** DC-23 (Q127, Q13). **Current answer:** reject both. Talos fails G2 because Jetson support is Nano-only and Orin support is the unmerged sbc-jetson PR #23 [C-W2-038, C-W4-064]. Kairos fails G2 because it has no Pi 5 model [C-W2-039]. Talos's API-only model also conflicts with host-level radios and CAN, and bootc plus greenboot matches its single signed artifact [C-W2-052].
**Refuter:** independent, cost and business lens. Formed before reading other refuters or the author's reasoning. **Verdict: upheld (rejection stands). The cost lens adds reasons and narrows one steelman.**

## 1. Re-checking the cited sources

- C-W2-038 and C-W4-064 are pinned and still accurate. PR #23 is still open on 2026-11-11, and it has sat in the "On Hold" column since 2026-02-18 with no formal review [C-REF3-DC-cost-006].
- C-W2-039 is accurate. Kairos models include Orin NX, AGX Orin, Thor and DGX Spark, and no Pi 5.
- C-W2-052 shows that bootc plus greenboot gates on k3s in QEMU. It does not show the fleet plane that Talos gets from Omni, so "matched" holds for the image but not for fleet management.

## 2. Strongest counter-argument (steelman for adopting one of them)

A solo developer (M-6) on Debian + Rugix + k3s has to build and maintain the image pipeline, the A/B integration with k3s (DC-12), the health gate and a fleet plane. Talos plus Omni ships all four as a product. Omni is free for up to 10 nodes [C-REF3-DC-cost-004], which covers the whole pre-revenue phase. Kairos is Apache-2.0 with no fleet fee and already supports the expensive hardware: Orin, Thor and DGX Spark [C-W2-039]. On cost, the best version of the argument is a split: **Kairos for the Jetson/Omni tiers, where the margin is, and Debian only for Pi and x86.** That would replace the hand-built Jetson flavor with a maintained framework.

## 3. Why the counter-argument fails on cost and business grounds

1. **Commercial terms do not suit a consumer appliance.** Talos Enterprise Linux costs $1,000 per node per year with a 10-node minimum. Omni Startup costs $25 per node per month, about $300 a year. Omni Edge has no public price and goes through sales [C-REF3-DC-cost-004]. A recurring per-box fee on a box sold for a few hundred dollars breaks H-1, and above 10 nodes the free tier ends. Omni is BSL (C-W2-049), so self-hosting it in production also needs a licence.
2. **Ownership changed in 2026.** Yardi, a property-management software company, acquired Sidero Labs on 2026-09-14. The announcement commits to Talos staying MPL-2.0 and keeps the same team. It says nothing about Omni licensing or pricing [C-REF3-DC-cost-003]. The fleet plane, which is the main cost saving in the steelman, now depends on a new owner whose priorities are not edge appliances.
3. **The board gaps are stalled, not merely pending.** Talos Orin support has been "On Hold" for nine months, and the latest activity is a community fork [C-REF3-DC-cost-006]. Kairos's Pi 5 issue has been open since 2023. A maintainer has doubted they have the capacity for it, and the only schedule signal is a bot setting the roadmap status to "Q2 2027" [C-REF3-DC-cost-005]. Neither project has paid staff working on the founder's two core boards.
4. **Talos on Pi 5 has a record of regressions.** Talos 1.12.3 kernel-panicked at boot on D0-stepping Pi 5 and CM5 boards because the overlay was tested only on C stepping [C-REF3-DC-cost-007]. Pi 5 NVMe and Ethernet depend on the Raspberry Pi kernel [C-REF3-DC-cost-008], the same vendor-kernel dependency the Debian path carries, and here with fewer maintainers. Every regression like this is unpaid founder time.
5. **The split-Kairos steelman does not remove a pipeline.** Kairos on Jetson would still be a second image family beside Debian on Pi and x86. It would add Kairos's cloud-init and immutable-layer model to learn. The saving would only be real if Kairos also covered Pi 5, and the DC-23 flip condition requires that (G2 on both boards).

## 4. New sources (searched for acquisition, stalled support, regressions and pricing)

| ID | What it shows |
|---|---|
| C-REF3-DC-cost-003 | Sidero Labs acquired by Yardi (2026-09-14); Talos licence kept; no Omni pricing or licence commitment |
| C-REF3-DC-cost-004 | Talos Enterprise $1,000 per node per year (10-node minimum); Omni Startup $25 per node per month; Omni Edge price unpublished |
| C-REF3-DC-cost-005 | Kairos Pi 5 issue open since 2023; maintainer capacity doubt; bot roadmap status "Q2 2027" |
| C-REF3-DC-cost-006 | Talos Orin PR "On Hold" since Feb 2026, no review |
| C-REF3-DC-cost-007 | Talos 1.12.3 Pi 5 D0 boot panic (Feb 2026) |
| C-REF3-DC-cost-008 | Talos Pi 5 NVMe and Ethernet depend on the Raspberry Pi kernel |

Seen but not ledgered: Sidero/Yardi press coverage reports a Talos hypervisor and "containers without Kubernetes" edge support, with GA planned for December 2026. The primary press release returned 403. If it ships, it would weaken the "API-only fights host services" argument in Q127, but not the G2 failure.

## 5. What would flip it

- **Talos:** sbc-jetson PR #23, or an equivalent, merged with Orin CUDA working; the official overlay booting Pi 5 (all steppings) from NVMe; and an Omni Edge price or self-host licence that costs no more than about 2% of box price per year. All three are needed.
- **Kairos:** a released kairos-init `rpi5` model that boots from NVMe. Kairos would then cover Pi 5, Orin and Thor under Apache-2.0 with no fleet fee, and it would have to be re-scored against the proposal on C5 (solo fit). Of the two, this is the most likely route to a flip. Re-check after Q2 2027.
- **Against both:** an Omni licence or pricing change under Yardi that restricts the free tier or self-hosting would close the Talos route for good.
