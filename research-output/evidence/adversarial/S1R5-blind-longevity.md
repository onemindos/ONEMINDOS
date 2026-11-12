# S1R5: blind refuter, longevity and vendor risk lens

**Target (as given to this refuter, nothing else read):** "S1 decision of record (rev. 4): OneMind OS core = Ubuntu 26.04 LTS + RAUC A/B updates (+ NVIDIA L4T/JetPack flavor for Jetson), chosen over RHEL-family bootc and Debian 13 under a frozen weighted scorecard; conditional on Canonical permission/debranded rebuild (Z-01) and on G5 (one OS Pi 5 to GPU cluster)."

**Protocol:** RESEARCH-MISSION.md §2 rule 7. Blind: I did not open `01-FOUNDATION-DECISION.md`, `decision-critical.md`, any scorecard file, or anything else in `evidence/adversarial/` or `evidence/critic/`. Product constraints came from `RESEARCH-MISSION.md` and `docs/REQUIREMENTS.md` (F-7, F-11, F-14).
**Date:** 2026-11-11. **Ledger:** `evidence/claims/REF5-S1-longevity.csv` (C-REF5-S1L-001…014).

**Verdict: `weakened`.** This refuter does not overturn the decision. The decision's two conditions are not minor provisos: they carry most of its 10-year risk. Z-01 decides whether OneMind licenses Canonical's binaries under a permission Canonical can revoke, or maintains its own Ubuntu rebuild. On current NVIDIA evidence, G5 ("one OS") is false for at least the first half of the horizon.

> **Explain it like I'm the founder.** Picking Ubuntu means relying on Canonical for three things: the right to ship a modified Ubuntu, free security fixes, and the kernel on each board. Canonical's own legal text says (1) you may not hand out a modified Ubuntu built from their binaries without their approval, which may cost money and which they can revoke; otherwise you must strip the name *and rebuild everything yourself*. (2) Free security fixes for the core packages end in April 2031, and the community "universe" packages get none for free; anything after that is a paid Ubuntu Pro arrangement. (3) Your Jetson boxes cannot run 26.04 today, because NVIDIA's current JetPack is built on Ubuntu 24.04. So "one OS from Pi to GPU" is really two Ubuntu releases with different kernels and end dates. None of this is fatal, since Debian and Red Hat have their own versions of these problems. But the decision is only as safe as the Canonical contract Z-01 produces, and that contract does not exist yet.

---

## 1. Strongest counter-argument

**Ubuntu turns OneMind's 10-year foundation into a dependency on one vendor's commercial discretion, in exactly the places a 10-year product cannot absorb it. The fallbacks behind the conditions (debranded rebuild, two-base G5) are more expensive than "conditional" suggests.**

### 1.1 Z-01 is a fork in the road, not a formality

Canonical IP Rights Policy (source at `canonical/canonical.com@eebaf62d…:templates/legal/intellectual-property-policy/index.md`, "update_date: 15 July 2015"):

- L54: "Any redistribution of modified versions of Ubuntu must be approved, certified or provided by Canonical if you are going to associate it with the Trademarks. **Otherwise you must remove and replace the Trademarks and will need to recompile the source code to create your own binaries.** … If you need us to approve, certify or provide modified versions for redistribution you will require a licence agreement from Canonical, for which you may be required to pay."
- L18: Canonical IP "can only be used with Canonical's permission (**which can be revoked at any time**)".
- L83: "system images, together with Ubuntu packages and binary files, are in many cases copyright of Canonical".

A OneMind image is a modified Ubuntu: read-only rootfs, RAUC slots, OneMind's own packages and config. That leaves two branches, and both carry long-term cost:

| Z-01 branch | What OneMind gets | 10-year exposure |
|---|---|---|
| **A. Canonical licence** | Canonical binaries, the security stream, Pro for Devices | A revocable permission (L18) under a contract whose price is "may be required to pay" (L54), renegotiated at every LTS rebase (26.04 → 28.04 → 30.04…). Pricing power sits with the vendor, and the product's device BOM is exposed to it. |
| **B. Debranded rebuild** | Freedom from the trademark | OneMind must "recompile the source code to create your own binaries" (L54). In effect OneMind becomes a distribution: it rebuilds every package it ships plus every security update, for 10 years. A rebuild also falls outside what Canonical says its updates will match (L55: "Canonical's updates will be consistent with every version of Ubuntu approved, certified or provided by Canonical"). And after the free window closes (§1.2), the security sources you would rebuild from come from Canonical's paid ESM, which means a contract again. |

Contrast: Debian's trademark policy (v2.0, 2013-01-19) governs only names and logos ("You cannot use Debian trademarks … as the name of a product"). It contains no clause that conditions redistribution of modified *binaries*. On redistribution law, the runner-up has no counterpart to branch A versus B.

### 1.2 Free support ends at 4.4 years of a 10-year horizon

- `canonical/ubuntu.com@ec15716b…:releases.yaml#L24-L31`: 26.04 "Resolute Raccoon", released April 2026, `eol: "April 2031"`.
- `templates/about/release-cycle.html#L325`: LTS releases are "security maintained for 5 years with CVE patches for packages in the **Main** repository". L369-L372: ESM, available "through Ubuntu Pro", "adds 10 years of security coverage for the 'Universe' repository". **Universe has no free security coverage at any point.** L398: the Legacy add-on "can be purchased" for years 11 to 15.
- `templates/pro/devices.html#L352`: Pro for Devices is "a one-time fee per device"; no price is published.

So from 2031 to 2036 (the CRA support-period window and the founder's 10-year horizon), every OneMind device's security depends on a per-device Canonical fee whose price is not public, unless OneMind rebases the whole fleet to 28.04 or 30.04 through RAUC. Each rebase is a major-version jump (kernel, glibc, systemd, Python) done under A/B on devices in the field. Any OneMind component taken from Universe gets no free CVE fixes even inside the first five years. RAUC itself ships as a distribution package in non-embedded distros (RAUC docs, "Package-Based Distributions"), but this refuter could not open packages.ubuntu.com to confirm its Ubuntu component (UNVERIFIED (blocked)).

### 1.3 G5 is false today, and the Jetson lag is structural

- NVIDIA JetPack page (opened 2026-11-11): JetPack 7 is "Built on Linux Kernel 6.8 and Ubuntu 24.04 LTS", with "full support for the NVIDIA Jetson Orin™ and Thor™ platform". JetPack 7.2 / Jetson Linux 39.2 is still 24.04 with kernel 6.8.
- The 26.04 core is on a different kernel series: Ubuntu Launchpad bug 2146383 (2026-03-25, Critical) says Raspberry Pi 5 "boards need an EEPROM update to boot kernel 7.0" for 26.04. That is SECONDARY: lists.snapcraft.io and Launchpad were blocked, and the text came from a search snippet.
- In practice, "one OS" ships as two Ubuntu LTS bases (24.04 and 26.04), two kernels (6.8 and 7.0), two security windows (24.04 standard support ends roughly two years earlier) and two image pipelines. NVIDIA decides when it moves, not OneMind. On F-14 ("the user never switches products") this is a hidden product split.
- **New fact that cuts against the RAUC-on-Ubuntu shape specifically:** NVIDIA's forum announcement of 2026-07-01 called JetPack 7.2 its "first official Yocto release", with "NVIDIA-validated recipes" through OE4T meta-tegra (Wrynose LTS, Yocto 6.0) and pre-built images for Orin and Thor. RAUC's own integration docs say "we highly recommend using a Linux system build system like Yocto / OpenEmbedded or PTXdist". The silicon vendor and the update framework now both point to Yocto, and the decision uses neither of them as its build base. A Yocto + RAUC core could hold Pi 5 (meta-raspberrypi), x86 and Jetson on **one** build system and release cadence that OneMind controls. That is the one route that makes G5 true by construction. This refuter has not evaluated that route's cost (team size, F-1 ease of use). It is an alternative the decision must answer, not a proven winner.

### 1.4 RAUC on classic Ubuntu is off Canonical's paved road

Canonical's supported immutable and OTA device product is **Ubuntu Core**: "The kernel and base operating system are handled as snaps … automatic rollbacks on improperly updated kernels" (`templates/core/features/ota-updates.html#L198`). Pro for Devices, Landscape and the "IoT app store" are marketed around that model. Classic Ubuntu plus RAUC A/B is a OneMind-owned integration that Canonical does not test. For 10 years OneMind owns everything the vendor would otherwise own: boot-slot logic, Pi 5 slot switching (RAUC docs cover barebox, U-Boot, GRUB, EFI and "custom"; Pi tryboot is not mentioned), and how snapd-dependent Ubuntu packages behave on a read-only root. Separately, a paid Canonical relationship (§1.1, branch A) buys support for a stack Canonical does not ship.

### 1.5 Kernel churn and failure evidence

- `templates/kernel/variants.html#L169`: `generic-hwe` "updates … every 6 months until it matches the GA kernel in the subsequent LTS release". `raspi` is a separate platform variant (L221). An x86 box that needs new hardware support therefore takes a kernel series change every 6 months. Each change is a regression surface for out-of-tree NVIDIA modules. USN-8668-2 (LWN 1096013, 2026-09-21) warned of "an ABI change that requires third-party kernel modules to be rebuilt" on linux-raspi.
- Pi 5 kernels regress at the board level. raspberrypi/linux#7635 (2026-09-21, open) reports that the NVMe drive behind a PCIe switch "disappears on every kernel that carries the stable backport of upstream commit 72780f796468" (6.18.39 / 6.12.96). This is a Raspberry Pi OS kernel, not Ubuntu's, so it does **not** count against Ubuntu specifically. It shows that Pi 5 support depends on downstream kernel maintainers, and Canonical's `linux-raspi` is a second downstream of Raspberry Pi's own (Debian-based) stack.

## 2. Evidence that cuts the other way (honest ledger)

- **Real-time is no longer a Pro lock-in on 26.04.** `templates/real-time/index.html#L259`: "With the PREEMPT_RT patches being fully upstreamed, the real-time kernel is freely available for everyone from the 26.04 release onwards." This removes an earlier vendor-risk argument (F-7/F-11 real-time). Caveat: the Raspberry Pi-optimised RT variant is documented only for 24.04 via Pro (L313).
- **Canonical offers the longest single-vendor commitment of the three.** Up to 15 years (Pro for Devices, `devices.html#L296`, L352) with RT and ROS coverage, and Pro is "free for personal and small scale commercial use in up to 5 machines" (`realtime.html#L274`). Debian 13 and RHEL-family bootc also need paid or community extended support to reach 2036, so the 10-year gap is not unique to Ubuntu. Ubuntu's version is just the most clearly priced as a vendor contract.
- The Jetson lag would hit any non-L4T base equally (Debian 13, Fedora/bootc). Only the Yocto route in §1.3 escapes it.

These points are why the verdict is `weakened`, not `refuted`.

## 3. Verdict and required response

**`weakened`.** The selection can stand, but the decision record should:
1. Restate Z-01 as a **go/no-go gate with a costed fallback**, not a footnote. Spell out branch B (a full rebuild plus security-stream ownership after 2031) with the engineers and build infrastructure it needs.
2. Restate G5 as **"two LTS bases until NVIDIA ships a 26.04-based JetPack"**, with a dated trigger, and test the one-OS claim against that reality.
3. Answer the **Yocto + RAUC + NVIDIA-official meta-tegra** alternative explicitly. It did not exist as an NVIDIA-official option before July 2026.
4. Budget the 2031 cliff: either Pro for Devices at a quoted per-device fee, or a fleet rebase to 28.04 with a lab-proven A/B major-version jump.

## 4. What would flip it

**To `refuted`:**
- Canonical declines a modified-image redistribution licence, or offers one only with a revocation clause and no term, *and* the costed branch B exceeds the team budget.
- A Pro for Devices quote that makes the Edge/Lite BOM uneconomic.
- An NVIDIA roadmap statement that JetPack stays on 24.04 through 2028 or later, combined with NVIDIA making Yocto its primary BSP delivery.

**To `upheld`:**
- A written Canonical agreement covering redistribution of OneMind's modified image for at least 10 years, with no unilateral revocation, and Pro for Devices pricing compatible with the BOM.
- An NVIDIA-announced JetPack on Ubuntu 26.04 (Jetson Linux r40 or later) with a date.
- A lab demonstration of a RAUC A/B major-version rebase (24.04 → 26.04 or 26.04 → 28.04) on Pi 5 and x86 that rolls back cleanly.

## 5. New primary sources opened by this refuter

| # | Source | Type | Pinned / accessed | Used for |
|---|---|---|---|---|
| 1 | Canonical IP Rights Policy, `canonical/canonical.com@eebaf62d63ae3d51bd34f18fdf6e26e35a35dd96:templates/legal/intellectual-property-policy/index.md#L18,L34-L36,L52-L55,L83` (sha256 272c9635…) | PRIMARY (Canonical's site source; canonical.com itself unreachable from the sandbox) | 2026-11-11 | §1.1 |
| 2 | Ubuntu release data, `canonical/ubuntu.com@ec15716b1c4b95f1860672d4274dda730ee9b4fe:releases.yaml#L24-L31` | PRIMARY | 2026-11-11 | §1.2 |
| 3 | Release cycle page, same SHA, `templates/about/release-cycle.html#L325,L338-L341,L369-L372,L398` (sha256 e4037225…) | PRIMARY | 2026-11-11 | §1.2 |
| 4 | Pro for Devices, same SHA, `templates/pro/devices.html#L296,L352` (sha256 aa45dbd5…) | PRIMARY | 2026-11-11 | §1.2, §2 |
| 5 | Real-time Ubuntu, same SHA, `templates/real-time/index.html#L259,L274,L313` (sha256 45202698…) | PRIMARY | 2026-11-11 | §2 |
| 6 | Kernel variants, same SHA, `templates/kernel/variants.html#L169,L221` (sha256 871dc5dd…) | PRIMARY | 2026-11-11 | §1.5 |
| 7 | Ubuntu Core OTA, same SHA, `templates/core/features/ota-updates.html#L198` (sha256 d89f0bf6…) | PRIMARY | 2026-11-11 | §1.4 |
| 8 | NVIDIA JetPack page, https://developer.nvidia.com/embedded/jetpack | PRIMARY | 2026-11-11 | §1.3 |
| 9 | NVIDIA forum, "JetPack 7.2 Yocto Release for Jetson is now live" (2026-07-01), https://forums.developer.nvidia.com/t/jetpack-7-2-yocto-release-for-jetson-is-now-live/375042 | PRIMARY (vendor staff post) | 2026-11-11 | §1.3 |
| 10 | RAUC integration docs, https://rauc.readthedocs.io/en/latest/integration.html | PRIMARY | 2026-11-11 | §1.3, §1.4 |
| 11 | Debian trademark policy v2.0, https://www.debian.org/trademark | PRIMARY | 2026-11-11 | §1.1 contrast |
| 12 | raspberrypi/linux#7635 | PRIMARY (issue tracker; failure evidence) | 2026-11-11 | §1.5 |
| 13 | LWN 1096013 (USN-8668-2 linux-raspi, 2026-09-21) | SECONDARY (repost of Ubuntu notice) | 2026-11-11 | §1.5 |
| 14 | Launchpad bug 2146383 via search snippet | SECONDARY / UNVERIFIED (blocked) | 2026-11-11 | §1.3 |

**Access note:** from this sandbox, ubuntu.com, canonical.com, launchpad.net, lists.snapcraft.io, packages.ubuntu.com, raspberrypi.com and web.archive.org did not resolve or were refused. Canonical pages were read from Canonical's own public website repositories at pinned commit SHAs, which serve as the archive. The SHA-256 values are of the raw files fetched at those SHAs.

## Glossary

- **ESM / Ubuntu Pro:** Canonical's paid (free for 5 machines) security stream that extends an LTS beyond its 5 free years.
- **Main / Universe:** Ubuntu's Canonical-maintained package set versus its community package set. Only Main gets free security fixes.
- **HWE kernel:** a newer kernel series offered on an LTS, replaced every 6 months.
- **Debranded rebuild:** removing Ubuntu names and logos and recompiling all binaries yourself so that Canonical's trademark terms no longer apply.
- **OE4T / meta-tegra:** the community Yocto layer for NVIDIA Jetson, now carrying NVIDIA-validated recipes.
