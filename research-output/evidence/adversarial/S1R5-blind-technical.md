# S1R5: blind technical refuter for S1 (rev. 4)

- **Lens:** technical
- **Date:** 2026-11-11
- **Protocol:** RESEARCH-MISSION.md section 2, rule 7. This review is blind: I did not open 01-FOUNDATION-DECISION.md, decision-critical.md, the scorecards, or the adversarial/critic folders.
- **Ledger:** `evidence/claims/REF5-S1-technical.csv`

## Target

> S1 decision of record (rev. 4): the OneMind OS core is Ubuntu 26.04 LTS plus RAUC A/B updates, with an NVIDIA L4T/JetPack flavor for Jetson. It was chosen over RHEL-family bootc and Debian 13 under a frozen weighted scorecard. The decision depends on Canonical permission or a debranded rebuild (Z-01), and on G5 (one OS from a Pi 5 to a GPU cluster).

## Verdict: **weakened**

The base choice survives. The rev. 4 claim states two things more strongly than the primary sources support:

- **One OS (G5):** what the sources describe is a family of operating systems.
- **Ubuntu plus RAUC:** on the Pi 5 there is no upstream, fail-safe RAUC path, and Ubuntu's own Pi A/B mechanism would compete with RAUC.

Neither point clearly favours bootc or Debian 13, so the verdict is not *refuted*.

## Strongest counter-argument

### 1. "One OS" is really three kernels and two Ubuntu releases

- **Jetson:** NVIDIA's current lines all use an Ubuntu 24.04 root filesystem and kernel 6.8. JetPack 7.1 is "L4T Ubuntu 24.04", k6.8, with "Canonical Ubuntu 24.04 for Jetson" as the other supported distro [R5T-003]. Jetson Linux 39.2 / JetPack 7.2, the release that brings Orin into JetPack 7, is also kernel 6.8 on 24.04 [R5T-004].
- **No 26.04 for Jetson:** I found no NVIDIA or Canonical artefact that ships 26.04 for Jetson.
- **What the fleet would run:**
  - x86 and GPU nodes: 26.04 with the 7.0 kernel.
  - Pi 5: 26.04 with the separate `linux-raspi` kernel.
  - Jetson: 24.04 userspace with the 6.8 vendor kernel.
- **Support windows differ:** standard support ends 2029-05-31 for 24.04 and 2031-05-29 for 26.04 [R5T-001]. So the Jetson flavor reaches end of standard support two years before the core does.
- **Consequences:** G5 holds only at the level of the app/runtime contract, not the OS image. Every CVE, every package pin and the RAUC bundle format must be tracked twice.

### 2. RAUC on the Pi 5 has no upstream, fail-safe backend

- **No official backend:** RAUC v1.15.2 (2026-03-27) is the latest release [R5T-005]. Its backends are barebox, grub, uboot, efi and custom. There is no Raspberry Pi firmware backend.
- **The upstream PR is stalled:** PR #1599 "bootchooser: add Raspberry Pi firmware initial support" is still open and unmerged after 22 months (opened 2025-01-16, last activity 2026-08-14) [R5T-006]. In the thread:
  - The submitter calls it "best effort and not fail safe (failure rate would be low but not null)".
  - Another participant notes that TRYBOOT state "survive[s] a reboot ... but not a halt/poweroff".
  - The RAUC maintainer says mapping the Pi handling onto RAUC "still feels a little complex".
- **The community backend cannot fall back:** its README states it "cannot implement a boot-attempts counter" and that "the firmware cannot fallback to the other slot if the primary slot gets unbootable" [R5T-007].
- **Bootlin's Pi 5 build depends on undocumented and downstream parts** [R5T-008, not new; already in W17]:
  - It uses "a currently undocumented feature of the RPi 5 firmware" (the `[boot_partition=N]` conditional).
  - It needs the vcio/vcmailbox driver, which is "not present upstream", so it requires a Raspberry Pi kernel.
- **Overall:** the Pi 5, the entry point of G5, is the platform where the decision's update mechanism is weakest. Rollback there is one-shot, and a power cut during the trial boot loses state.

### 3. Ubuntu already has its own Pi A/B scheme that would compete with RAUC

- **What Ubuntu ships:** since 25.10, Ubuntu's Pi boot path includes a piboot/tryboot fallback managed by Ubuntu's own boot-asset tooling.
- **Pi 5 caveat in Ubuntu's own doc:** on the Pi 5 "the bootloader simply freezes", and recovery needs a power cycle [R5T-009].
- **The conflict:** a RAUC design has to disable or replace Ubuntu's mechanism. Otherwise two owners will rewrite `autoboot.txt`/`config.txt` on every kernel update. It also means stock Ubuntu Pi kernel packages cannot be applied in place inside a slot; the image has to be rebuilt.
- **Verification status:** UNVERIFIED (blocked). documentation.ubuntu.com does not resolve from this host. The quoted text comes from the search index, and I could not open the page.

### 4. The Pi 5 is a fragile target on 26.04

- **Launchpad bug 2146383:** Pi 5 boards need an EEPROM newer than 2024-09-23 (one comment says 2025-02-11) to boot kernel 7.0. As of March 2026 the exact minimum was undetermined [R5T-010].
- **Late kernel change:** 26.04 moved to the final 7.0 kernel late in the cycle.
- **Status:** UNVERIFIED (blocked); Launchpad and the lists.snapcraft.io archive do not resolve from here.
- **Why it matters:** a fleet OS must ship and update EEPROM firmware itself. RAUC does not cover that, and no A/B slot protects it.

### 5. The Pi vendor's own A/B tooling targets the Debian side

- Raspberry Pi's `rpi-image-gen` ships an `image-rota` layer: an "Immutable GPT A/B layout for rotational OTA updates ... and a shared persistent data partition" [R5T-011].
- It is built with mmdebstrap and Debian packages, and produces Raspberry Pi Connect update bundles. It says nothing about Ubuntu.
- So the board vendor's supported immutable-A/B path sits on the Debian/Raspberry Pi OS side, which is the S1 runner-up's ecosystem.
- This strengthens Debian 13 on the Pi tier specifically. It does not help bootc, which has no Pi 5 story here.

### 6. The debranded-rebuild branch (Z-01) has a technical cost

- **The policy:** Canonical's IP policy (2015 text, still current per the search index; canonical.com is blocked from here) requires approval for modified images that carry its marks. Otherwise the marks must be removed. Commentators read the policy as also requiring archive rebuilds. Matthew Garrett (LWN, 2015-11-20): "Canonical refuse to tell you what changes you need to make to the packages" [R5T-002]. That is a secondary source, so I give it medium confidence.
- **The cost:** if Z-01 goes the rebuild way, OneMind runs its own archive rebuild and mirror. That loses the main technical reason to pick Ubuntu: drop-in binary compatibility and Canonical security updates.
- **After 2031:** the 2031-05-29 → 2036-04-23 ESM window [R5T-001] is a Canonical subscription. A debranded rebuild does not get it by default.
- **Comparison:** Debian 13 LTS runs to 2030-06-30 and ELTS to 2035-06-30 [R5T-001], with no trademark-rebuild problem.

### 7. Real-time Ubuntu on the Pi 5 for 26.04 is unconfirmed

- **Generic kernel:** search-indexed Canonical text says real-time is free from 26.04 (`ubuntu-realtime`) for amd64/arm64.
- **Pi variant:** the Pi variant (`--variant=raspi`) is documented only for 22.04 and 24.04, through Pro [R5T-012, UNVERIFIED (blocked)].
- **Effect:** a robotics/IIoT real-time claim at the Pi tier is open.

## Why this is *weakened*, not *refuted*

- **Point 1 hits every candidate.** NVIDIA ships Ubuntu userspace for Jetson. With Debian 13 or bootc, the Jetson flavor would be an even more foreign OS. Ubuntu is still the closest base to Jetson.
- **Point 2 is a RAUC-on-Pi problem, not an Ubuntu problem.** Debian + RAUC hits it identically. bootc has no supported Pi 5 path.
- **Points 3, 5 and 6 are real costs.** They change the risk and effort, but none of them on its own shows a better-scoring alternative.

## Required changes to the claim

1. Restate G5 as "one OneMind runtime contract and update format across a family of OS builds (26.04 core; 24.04-based Jetson flavor until NVIDIA ships 26.04)".
2. Put the Jetson/core EOL skew in the risk register: standard support ends 2029-05-31 for the Jetson flavor and 2031-05-29 for the core.
3. Mark Pi 5 rollback as **not fail-safe** until RAUC PR #1599 (or an equivalent) is merged and lab-tested through power-cut-during-tryboot. Either decide that Ubuntu's piboot mechanism is disabled, or adopt it as the backend.
4. Make EEPROM firmware management an explicit OneMind update channel.
5. Price the Z-01 rebuild branch: archive rebuild, mirror and post-2031 security feed.

## What would flip the verdict

**Back to upheld:**

- NVIDIA or Canonical ships a 26.04-based Jetson BSP.
- RAUC merges a Raspberry Pi firmware backend, and a OneMind lab run shows Pi 5 recovery after power loss during a trial boot.
- Canonical gives written Z-01 permission that covers redistribution of Ubuntu binaries in the image, including ESM.

**To refuted:**

- Z-01 is refused and the rebuild is costed above the Debian 13 + Freexian ELTS path.
- A lab shows Ubuntu's piboot/flash-kernel cannot be cleanly removed in favour of RAUC on the Pi 5, while a Debian/`rpi-image-gen` A/B image passes the same power-cut test.
- NVIDIA states Jetson will stay on 24.04 through 2029. The core would then have no on-target Ubuntu advantage over Debian at the Jetson tier for most of the product's first five years.

## Source access notes

These hosts did not resolve from the research host on 2026-11-11: ubuntu.com, canonical.com, documentation.ubuntu.com, bugs.launchpad.net, lists.snapcraft.io and discourse.ubuntu.com. I made no attempt to route around this. Claims that rely on those hosts are marked UNVERIFIED (blocked) in the ledger and must be re-checked before they are cited as primary.
