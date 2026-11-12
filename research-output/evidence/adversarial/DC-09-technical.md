# DC-09 — Refuter report: which base for the Jetson flavor, technical lens

- **Conclusion under test (qbank W7 DC-09, 08):** keep NVIDIA L4T Ubuntu 24.04 (JetPack 7.2+) for the Jetson flavor (ADR-001 D2 confirmed). Debian on Jetson is not a supported option. Yocto meta-tegra, NVIDIA-official since JetPack 7.2 with LTS branches (wrynose = JP 7.2.1, scarthgap = JP 6.2.3), is the runner-up. Partial: the license text (Q59) was not opened at the time, and no meta-tegra build was run.
- **Flip condition (decision-critical.md):** a non-Ubuntu Jetson rootfs keeps full JetPack capability and passes G1, which unifies the family; or stock L4T fails G1 for redistribution.
- **Lens:** technical. I read only the conclusion and its cited claims (C-W7-007, 008, 015, 016, 056). I did not read the author's reasoning or other refuter files first.
- **Date:** 2026-11-11

## Verdict: **upheld** (base choice), with two qualifications on "JetPack 7.2+ on Orin" and on what "Ubuntu" buys

No new evidence shows a non-Ubuntu rootfs with full JetPack capability, so the formal flip condition is not met. L4T Ubuntu stays the right base. But the conclusion carries two hidden assumptions that the evidence does not support:

1. **"JetPack 7.2+" for Orin is the newest, least-proven line, not a settled one.** JP 7.2 added Orin to JetPack 7 in June 2026. Users report install, flash and power-mode regressions on Orin Nano through October 2026, several closed without a root cause (C-REF3-DC-technical-014, 015).
2. **"Ubuntu" on Orin 24.04 does not carry Canonical's support.** Canonical certifies Orin only on Ubuntu 22.04 / Core 22. Only Thor is certified on 24.04 (C-REF3-DC-technical-016). The L4T 24.04 rootfs on Orin is NVIDIA's own build, and its security fixes arrive only as whole-BSP releases without package-level mapping (C-REF3-DC-technical-017). So the motive "inherits Ubuntu's userspace and terms" is weaker in both directions. The flavor gets fewer of Canonical's guarantees, and it is tied more tightly to NVIDIA's release train.

## Checks of the cited sources

| Sub-claim | Claim | Result |
|---|---|---|
| JP 7 is Ubuntu 24.04 / kernel 6.8, Orin + Thor | C-W7-007, 008 | Holds as NVIDIA's statement. Orin support in JP 7 is only from 7.2 (2026-06-02), so field time is about 5 months. |
| Yocto official via OE4T | C-W7-008, 015 | Holds. But scarthgap "will stay on R36.x/JetPack 6.x", so the Yocto LTS that matches Orin's mature line is JP 6, not JP 7. |
| meta-tegra bus factor | C-W7-016 | Holds and stays a serious runner-up risk (one maintainer with about 12x the commits of the next). |
| License | C-W7-056 | Superseded by C-LIC-001 per the ledger. Not re-examined under this lens. |

## Strongest counter-argument

The real choice is not "L4T Ubuntu vs Yocto vs Debian". It is **which NVIDIA release train, and who patches it**. Every option, including meta-tegra, consumes the same NVIDIA BSP binaries and the same L4T security cadence. NVIDIA publishes fixes per L4T release (for example the March 2026 bulletin's fixes land in 35.6.4 / 36.5 / 38.4) and declines to say which package carries a fix (C-REF3-DC-technical-017). So an A/B image of any base must take whole-BSP upgrades, including bootloader and QSPI firmware, which is exactly where the JP 7.2 regressions sit (bootloader package postinst failures and board-ID/EEPROM flash failures; C-REF3-DC-technical-014, 015). The base question is secondary to two things: **"can we ship a BSP bump through A/B safely?"** and **"do we standardise Orin on JP 6.2.x (22.04, Canonical-certified, meta-tegra scarthgap LTS) until JP 7.x on Orin has matured?"** The conclusion's "JetPack 7.2+" quietly chooses the less-proven answer to the second question. JP 6 has its own problem: Ubuntu 22.04 standard support ends in April 2027, which the conclusion has to weigh against this.

## New sources (searched for failures and regressions)

- **N1. NVIDIA forum, JetPack 7.2 / r39.2 Orin Nano feedback thread, page 3** — https://forums.developer.nvidia.com/t/jetpack-7-2-jetson-linux-r39-2-on-jetson-orin-nano-developer-kit-getting-started-and-feedback-thread/372151?page=3 (opened). June 2026 reports:
  - The installer fails at `nvidia-l4t-bootloader` with "does not match any known boards", and the package stays half-configured. The workaround was a no-op postinst plus an apt hold.
  - USB installs lose Super power modes.
  - The camera NITO override was removed.
  
  The thread has few NVIDIA replies. [C-REF3-DC-technical-014]
- **N2. NVIDIA forum, "Orin Nano Super P3767-0005 — missing board ID/EEPROM data causes JetPack 7.2.1 flash failure"** — https://forums.developer.nvidia.com/t/jetson-orin-nano-super-p3767-0005-missing-board-id-eeprom-data-causes-jetpack-7-2-1-flash-failure/385156 (opened). In October 2026 a new board could not be flashed with JP 7.2.1. The NVIDIA moderator closed the thread for inactivity, with no root cause. [C-REF3-DC-technical-015]
- **N3. Canonical, "Install Ubuntu on NVIDIA Jetson"** — https://ubuntu.com/download/nvidia-jetson (opened). Orin is certified on 22.04 only, and Thor on 24.04. Long-term support comes via Ubuntu Pro. [C-REF3-DC-technical-016]
- **N4. NVIDIA forum, CVE-2026-24148 package question** — https://forums.developer.nvidia.com/t/cve-2026-24148-which-specific-debian-package-contains-the-fix-and-is-a-partial-update-feasible-on-jetpack-36-4-3/367096 (opened). NVIDIA: "we're not able to provide further details than the information listed." So the only fix route is a full BSP upgrade. [C-REF3-DC-technical-017]
- Context only (search result titles, not opened): other October 2026 NVIDIA forum threads report a JP 7.2 Orin NX bricked by a failed flash, Orin Nano ext4/NVMe corruption on JP 7.2, and "Jetpack 7.2 installation exit 100 for apt-get install nvidia-l4t-bootloader".

## What would flip the decision

- **Towards a different base (formal flip):** a meta-tegra or Canonical "Ubuntu for Jetson" (`linux-nvidia-tegra-jetson`) image that runs the full JetPack 7.2 stack (CUDA, TensorRT, DeepStream, Isaac ROS containers) on Orin and Thor, with a BSP bump delivered through an A/B update in the lab without a reflash. Canonical's certified image is a fourth option that the conclusion did not weigh. If Canonical certifies Orin on 24.04 with Ubuntu Pro security maintenance, it dominates stock L4T on support terms.
- **Towards "JP 6.2.x on Orin first":** LAB-W7 cannot complete a JP 7.2.x BSP upgrade (bootloader + rootfs) through the chosen A/B tool on a production Orin module, or NVIDIA's JP 7.2.x release notes keep listing Orin install/flash known issues by the next point release.
- **Upheld cleanly if:** a JP 7.2.1 → 7.2.x BSP update succeeds via A/B on Orin Nano and AGX Orin in the lab, including the QSPI/bootloader capsule, with automatic rollback on a forced failure.
