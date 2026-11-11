# W3 P0-W3-2 refuter: longevity and vendor risk

| Field | Value |
|---|---|
| Claim | P0-W3-2 (`04` §1 V1, §14.2 P0-2): "RAUC leads S2." RAUC is the lead A/B update client on x86 and Pi 5, and the Jetson leg uses NVIDIA's rootfs A/B plus image-based OTA. Cited for longevity: RAUC is LGPL-2.1 with 512 commits from 16 human authors in 12 months [C-W3-017]; Rugix has a single maintainer and patches only its latest minor version [C-W3-001, C-W3-004]; the Jetson backend [C-W3-049, C-W3-050]; the RAUC Tegra layer was removed [C-W3-021]; the Mender Tegra layer exists [C-W3-053]. |
| Lens | Longevity and vendor risk: the G3 and maintainer cells, and the life of the Jetson backend |
| Protocol | RESEARCH-MISSION.md §2 rule 7. The refuter saw only the conclusion and the cited sources. |
| Date | 2026-11-11. Re-check repo statistics and BSP facts by 2027-05-11. |
| Verdict | **weakened**. A written response is required. |

## 1. Re-checking the cited sources

| Claim | Finding | Holds? |
|---|---|---|
| C-W3-017: 512 commits from 16 human authors | The counts reproduce. The breadth does not. 455 of the 512 commits (89%) are from pengutronix.de addresses, and two people wrote 440 (86%). The only outside author with more than 3 commits wrote 14 [C-REF-W3-longevity-001]. | **Count yes, framing no.** "16 authors" reads as a community; the data shows one company and two people. |
| C-W3-001 / C-W3-004: Rugix's concentration and latest-only support | Reproduced (see the P0-W3-1 file). | Yes |
| The implied contrast that RAUC has a better support policy | RAUC's SECURITY.md defines how to report a vulnerability and states **no supported-versions window**. CVE-2026-34155 lists only 1.15.2 as patched, even though a `stable-1.11` branch exists [C-REF-W3-longevity-008]. In practice both engines patch only the latest release line. | **No.** On published support policy the two engines are a tie, not a RAUC advantage. |
| C-W3-021 / C-W3-049 / C-W3-050: Jetson goes through NVIDIA's own A/B and OTA | The NVIDIA pages are as summarised. That leg's life depends entirely on NVIDIA's BSP cadence (see §3). | Yes, but the lifecycle risk is NVIDIA's and RAUC does not reduce it |

## 2. Strongest counter-argument

The S2 lead is presented as partly a longevity win: a multi-author RAUC against a single-maintainer Rugix. On primary data that gap is narrower than the scoring implies.

1. **RAUC is one company with two key people.** Pengutronix funds maintenance from its consultancy. In November 2025 it began selling sponsorships because reviewing pull requests is unpaid work ("who wants to pay for pull request review?") [C-REF-W3-longevity-006]. That reads as a funding-pressure signal, not as the profile of a broad community.
2. **Neither engine publishes support beyond its latest release.** If the G3 penalty for Rugix rests on "latest minor only" [C-W3-004], RAUC should carry the same penalty [C-REF-W3-longevity-008].
3. **Both engines had high-severity signature-path bugs in 2026.** RAUC's CVE-2026-34155: a plain bundle over 2 GiB had a signature covering only its first bytes. Rugix's GHSA-f8wx: execute payloads without block encoding. Neither engine has the cleaner record. RAUC's bug was found by Sony, which shows deep outside scrutiny. Rugix's was found by Umbrel.
4. **"One release contract over per-board backends" adds vendors.** OneMind takes on RAUC (Pengutronix), NVIDIA's OTA tooling and a OneMind wrapper. The Jetson leg has its own failure reports, including an OTA that reported success while leaving a slot without a filesystem [C-REF-W3-longevity-009]. Longevity is set by the weakest backend.

**What still favours RAUC.** It has 10 years of releases and named large adopters: HAOS, Valve's Steam Deck, IKEA Dirigera and Linux4ICE trains [C-REF-W3-longevity-007]. The adopter list is a vendor statement, but HAOS's use of RAUC is public in code. Pengutronix has publicly pledged no enterprise edition and no relicensing. Even on the strict count, two key people beat one. **The direction of the lead holds; its size on the longevity cells is overstated.**

## 3. New failure, abandonment and CVE evidence (opened by this refuter)

| Source | What it shows |
|---|---|
| [Pengutronix sponsorship post, 2025-11-21](https://pengutronix.de/en/blog/2025-11-21-labgrid-rauc-sponsoring.html) [C-REF-W3-longevity-006] | Maintenance is funded from consultancy, review is unpaid, and sponsorship is now being solicited. Pengutronix pledges no Plus or Enterprise edition and no relicensing. |
| [RAUC SECURITY.md @2d17b27](https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/SECURITY.md) and [GHSA-6hj7-q844-m2hx](https://github.com/rauc/rauc/security/advisories/GHSA-6hj7-q844-m2hx) [C-REF-W3-longevity-008] | No supported-versions window, and no backport listed for the 2026 high-severity CVE. |
| [NVIDIA forum: JetPack 5.1.2→6.2 OTA depends on slot state](https://forums.developer.nvidia.com/t/jetpack-5-1-2-6-2-ota-fails-or-succeeds-depending-on-a-b-slot-state/367303) [C-REF-W3-longevity-009] | The Jetson backend fails across major BSP jumps unless both chains are updated first, and the root cause was never explained. SECONDARY. |
| [HAOS #4540](https://github.com/home-assistant/operating-system/issues/4540) [C-REF-W3-longevity-010] | A RAUC install failed because inactive slots were mounted. The cause was integration, not a RAUC defect. It shows that HAOS-scale field use surfaces integration traps rather than engine bugs, which is mildly in RAUC's favour. |

## 4. Verdict: weakened

On the longevity lens the lead survives, but its basis must be restated. The cell scores should rest on "a 10-year, company-backed project with large adopters and two key maintainers", not on "16 authors". The support-window penalty should apply to both engines. The Jetson leg's lifecycle belongs to NVIDIA and should be scored as an NVIDIA dependency, not credited to RAUC.

## 5. Evidence that would flip the decision

- Pengutronix loses or reassigns either of its two key maintainers, or no RAUC release ships for more than 12 months.
- HAOS or SteamOS publicly migrates off RAUC.
- Rugix gains an independent co-maintainer and a previous-minor backport policy. On G3 it would then match RAUC.
- NVIDIA drops image-based OTA for a supported Jetson module, or OneMind's lab cannot make NVIDIA's OTA pass both-chain updates across a major BSP. That would push the Jetson leg towards Mender and Yocto and reopen S2.
