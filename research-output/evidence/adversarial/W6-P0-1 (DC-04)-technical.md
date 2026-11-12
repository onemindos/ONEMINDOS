# W6 — Refuter report: P0-1 (DC-04, CRA support period vs base release), technical lens

- **Claim under test (P0-1, 07-security-compliance.md):** The CRA requires a support period of at least five years that reflects expected use [C-W6-002]. It does not require one base release to last that long: under Art. 13(10) the manufacturer may support only the latest version if the upgrade is free and needs no new hardware [C-W6-004]. Debian 13's free LTS ends 2030-06-30 [C-W6-022], so a box sold in late 2027 must be rebased in place (Debian 14, then 15) to stay compliant to 2032+, or buy ELTS (to 2035-06-30, price unpublished, amd64 guaranteed) [C-W6-023]. Decision: **D2 confirmed, conditionally** on the in-place rebase path (DC-05) and per-board kernel support (DC-08).
- **Refuter lens:** technical. I read only the conclusion row and its cited sources (RESEARCH-MISSION.md §2 rule 7). I did not read the author's reasoning sections or the other W6 adversarial files before forming this view.
- **Date:** 2026-11-10
- **Sources cited by the claim:** C-W6-002, 004, 005, 022, 023.

## Verdict: **weakened**

The legal reading holds, and the Commission's final guidance makes it stronger than the claim says. The technical premise that every OneMind board can follow "Debian 14, then 15" through the A/B updater does not hold today. For the Jetson tier the base is not Debian at all, and NVIDIA's record shows that older modules are capped at an old Ubuntu. Where a board cannot take the next base, the guidance says Art. 13(10) is unavailable. The manufacturer then owes fixes on the old version for the whole declared period. D2 stands for amd64 and, with work, for the Pi. The "confirmed" label is too strong for Jetson-class boxes.

## Checks of the cited sources

- **C-W6-002 / 004 / 005 (CRA Art. 13(8), 13(10), 13(19)):** the ledger wording matches the Regulation. Art. 13(8) lists "the support periods of integrated components that provide core functions and are sourced from third parties" as a factor. That factor cuts against the claim on Jetson (see below).
- **C-W6-022 (Debian LTS, trixie to 2030-06-30, architectures "to be determined"):** correct as cited. Note that "to be determined" means **arm64 LTS for trixie is not yet promised**. The claim treats the LTS date as if it applies on every board.
- **C-W6-023 (Freexian ELTS to 2035-06-30, "at least amd64"):** correct. It confirms that the paid fallback is guaranteed only on amd64.

## New sources (opened 2026-11-10; found by searching for lifecycle cuts, abandonment and unsupported upgrades)

- **N1. European Commission, CRA application guidance, Annex to C(2026) 5252 (27 July 2026), PRIMARY.** https://ec.europa.eu/newsroom/dae/redirection/document/131456 (PDF downloaded and text extracted).
  - Para. 130: "additional costs" **does not** include "upgrades of underlying software dependencies that are necessary to address end-of-life components". It **does** include "mandatory purchases of new hardware, infrastructure replacement or fundamental changes to the operating environment".
  - Example 52: a smartphone maker may fix only the latest OS major version if users "can install free of charge without requiring new hardware". This supports the claim: a hardware product doing OS major upgrades is the Commission's own example.
  - Para. 131: each substantially modified version needs its own Art. 13(8) support period, and Art. 13(10) lets the manufacturer stop fixing older versions **only once users are able to upgrade**.
  - Para. 128: a substantial modification does not by itself reset the support period.
- **N2. NVIDIA, "JetPack 4 Reaches End of Life" (forum announcement, 2023-09-25), PRIMARY.** https://forums.developer.nvidia.com/t/jetpack-4-reaches-end-of-life/267563. The final JetPack 4 release came in Q1 2024. Xavier users were told to move to JetPack 5. The post offers no upgrade path for the Jetson Nano.
- **N3. Connect Tech, "Your Jetson Xavier Platform Is Approaching End of Life" (2026-05-27), vendor.** https://connecttech.com/jetson-xavier-eol-migration-guide/. AGX Xavier and Xavier NX "top out at JetPack 5.1.5 / L4T 35.6.2, running on Ubuntu 20.04", with "no JetPack 6 support". Nano, TX2 NX and TX2i are "capped at JetPack 4.6.x (L4T 32.x) on Ubuntu 18.04". JetPack 6 and later are "Orin-only territory".
- **N4. NVIDIA Jetson Product Lifecycle page, PRIMARY.** https://developer.nvidia.com/embedded/lifecycle. Orin modules are listed as available through January 2032 (AGX Orin Industrial through July 2033). The page states **no software support duration**: hardware availability is not a BSP commitment.
- **N5. Raspberry Pi Engineer (forum moderator), "Upgrading a bookworm image to trixie" (2025-10-02), vendor.** https://forums.raspberrypi.com/viewtopic.php?t=392376. Quote: "we do not recommend updating an existing bookworm image, and offer no support for problems encountered when attempting this". Raspberry Pi recommends a clean image. The same search turned up community reports of armhf (Pi 2) boards left on an orphaned bookworm kernel with no trixie kernel package. That report is **not verified** and is not used for the verdict.

## Strongest counter-argument

Art. 13(10) works only when the next version runs on the hardware the customer already owns. The Commission reads "additional costs" to cover "mandatory purchases of new hardware" and "fundamental changes to the operating environment" (N1, para. 130). For a OneMind box, whether a next version exists is decided by the board vendor's BSP, not by Debian:

1. **Jetson:** NVIDIA ships L4T on **Ubuntu**, not Debian. "Rebase to Debian 14, then 15" is not a path NVIDIA supports for any Jetson. NVIDIA's history is that each module generation is frozen on the Ubuntu of its last JetPack: Nano and TX2 on 18.04, Xavier on 20.04 (N2, N3). The availability dates on the lifecycle page say nothing about software (N4). If an Orin box sold in 2027 hits an NVIDIA freeze before 2032, its users cannot get the latest OneMind version without new hardware. Art. 13(10) is then unavailable, and OneMind must patch the frozen version itself for the remaining declared period, on an EOL Ubuntu plus a vendor kernel. Art. 13(8) already counts the support periods of third-party core components, so a declared period longer than NVIDIA's commitment is hard to defend.
2. **Raspberry Pi:** the vendor itself does not support an in-place major upgrade (N5). OneMind's A/B image replaces the whole rootfs and boot assets, so it avoids the apt-upgrade failure mode. It also takes on the vendor's untested migration (firmware/EEPROM, config.txt, kernel package changes) as OneMind's own engineering for every board revision in the field. This is a real, unbudgeted work item, not just a "gate".
3. **Debian LTS on arm64** for trixie is "to be determined" (C-W6-022). ELTS guarantees only amd64 (C-W6-023). The paid fallback in the claim therefore does not exist for the Pi and Jetson tiers unless Freexian agrees to cover them on request.

What survives: on amd64 the claim is correct and well supported. An image-based A/B rebase to Debian 14 is a free software upgrade, and N1 para. 130 and Example 52 say it qualifies.

## Required corrections to the decision text

- Change "D2 confirmed, conditionally" to **"D2 confirmed for amd64; conditional per board"**. Name the Jetson tier as **not on the Debian rebase path** (it follows NVIDIA's Ubuntu-based L4T cadence).
- Cite the Commission guidance (N1 paras. 129–131, Example 52) in place of the bare Article text. It confirms the interpretation and defines "additional costs".
- The declared support period on the box (Art. 13(19)) should be the **minimum** of the OneMind commitment and the board vendor's BSP commitment, unless OneMind budgets to self-maintain the frozen BSP to the end of the period.

## What evidence would flip the decision

- **To refuted (D2 fails for a board tier):** (a) NVIDIA declaring an Orin JetPack line final, or Orin not getting the next Ubuntu-LTS-based JetPack, before 2032; (b) a DC-05 lab result showing the A/B updater cannot move a Pi 5 or Orin box across a major base with new kernel/firmware without reflash or user intervention; (c) Commission/ADCO guidance or an FAQ treating a base-OS major rebase on a hardware product as a "fundamental change to the operating environment".
- **To upheld (as written):** (a) a written NVIDIA software-support commitment for Orin (or Thor) to at least 2032; (b) a DC-05 lab pass of an A/B major-base rebase (trixie to forky) on amd64, Pi 5 and Orin, including power-cut and rollback; (c) a Freexian written quote covering arm64 ELTS for trixie.

## Ledger rows

C-REF-W6-technical-001 to -005 in `evidence/claims/REF-W6-technical.csv` (TAG REF-W6-technical).
