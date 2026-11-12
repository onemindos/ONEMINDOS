# W2 P0-2 refuter: longevity and vendor risk

- **Claim under test (P0-2):** Fedora IoT should not be OneMind's single base today. Fedora 45 reaches end of life 2027-12-08. The IoT lead declined an oldstable tree ("We don't have the resources for that"). The bootc image does not boot on Raspberry Pi (issue #82 and bootupd PR #935 both open). Raspberry Pi 5 is not in Fedora IoT's reference platforms, and bootc on a Pi requires a device already provisioned with Fedora IoT.
- **Lens:** longevity and vendor risk (10-year horizon, solo founder, Pi 5 + x86 + Jetson, IoT/IIoT; F-12 requires a full and fair Fedora IoT evaluation).
- **Refuter inputs:** the claim and its six cited sources only. I did not see the author's reasoning.
- **Date checked:** 2026-11-10.
- **Verdict:** **upheld** for the conclusion, with three factual corrections the author must make (section 5). The hunt for failure evidence added risk (a bootc regression on Pi 5, stalled bootupd work, one maintainer doing Pi enablement). It did not reduce the risk.

## 1. Cited sources, re-checked

| # | Source | What it says (opened 2026-11-10) | Supports claim? |
|---|---|---|---|
| S1 | bodhi.fedoraproject.org/releases/F45 | **UNVERIFIED (blocked):** the page is behind an Anubis bot wall, as is docs.fedoraproject.org/en-US/releases/lifecycle/. SECONDARY sources disagree: endoflife.ai gives 2027-12-08, and computingforgeeks reports `SUPPORT_END=2027-11-24` in F45's `/etc/os-release`. | Partly. The date is unconfirmed, and two dates are in circulation. |
| S2 | github.com/fedora-iot/iot-distro/issues/123 | Open. On 2025-10-15, member nullr0ute declined a "release - 1" tree: "We don't have the resources for that." He also pointed to the CoreOS-style archive repo, which is not enabled by default because of downgrade-attack risk. | Yes, quoted accurately. Note the context: he also argued that release-1 would not fix the NVIDIA lag, because all releases move kernels at about the same time. |
| S3 | github.com/fedora-iot/iot-distro/issues/82 | Open, bug, no assignee. Opened 2025-03-12. Last comment 2025-07-09: a Pi **4** booted a bootc image "with almost no hacks" using the unmerged bootupd `extend-payload-to-esp`, still needing a `u-boot.bin` rename or a `config.txt` edit. The lead called both fixes poor options. | Yes for Pi 4. The issue says nothing about Pi 5. |
| S4 | github.com/coreos/bootupd/pull/935 | Open. Opened 2025-05-27. `needs-rebase` since 2026-03-18. No approvals (two are required). Superseded in part by #938 and complemented by #1073 (below). | Yes |
| S5 | iot-docs@3cfcfe7 reference-platforms.adoc L3-L51 | aarch64 lists Pi 3 and Pi 4 (4B/CM4) and Jetson Xavier/Orin. No Pi 5. | Yes, at that SHA. The docs lag the code (section 2). |
| S6 | iot-docs@3cfcfe7 fedora-iot-bootc-raspberry-pi-example.adoc L3 | "Using bootc with Fedora IoT currently requires that you have already provisioned a device with Fedora IoT." | Yes |

## 2. Strongest counter-argument (steel-manned against the claim)

1. **Release EOL is not stream EOL.** Fedora IoT is a stream that moves to a new release every six months, like Fedora CoreOS and Bluefin. A device that rebases on schedule never sits on an EOL release. A 13-month release window only matters if OneMind wants to *freeze* a fleet. With an image pipeline that rebuilds every release (D: "one image pipeline, many profiles"), the cadence is a CI cost, not a lifecycle cut. Fedora is also the upstream of RHEL, one of the best-funded lineages in Linux (Red Hat/IBM).
2. **A longer-lived lineage exists with the same tooling.** CentOS Stream 10 is "maintained until 2030", contingent on RHEL 10 Full Support (centos.org/centos10, opened). bootc images exist for it (`quay.io/centos-bootc/centos-bootc:stream10`, per the bootc-workflow-report test runs; SECONDARY). RHEL image mode / Red Hat Device Edge extends that further. So "no oldstable" is a Fedora-tier limit, not a limit of the lineage.
3. **Pi 5 support has moved on since the cited doc.** The Fedora IoT lead (Peter Robinson, nullr0ute) wrote in Oct 2026: "The Raspberry Pi 5 has worked out of the box on Fedora since the F-44 release!!" It is an MVP: Model 5B only, uSD or NVMe boot, networking, USB, accelerated graphics, basic thermal and fan control. Fedora 45 drops the F44 `cma=` boot workaround (nullr0ute.com/2026/10/raspberry-pi-5-on-fedora/, opened; LWN brief lwn.net/Articles/1103212/, 2026-10-27, opened). The fedora-iot-bootc F45 image moved to the stable repos on 2026-10-30 (fedora-iot/fedora-iot-bootc PR #265, merged, opened).
4. **People already run bootc on Pi 5.** bootc-dev/bootc issue #2605 (opened 2026-10-30) comes from a Raspberry Pi 5 (aarch64) running a composefs bootc install, with the kernel booted directly by the Pi firmware and BLS entries on an ESP-typed FAT partition. The same blog post links a third-party "RPi5 on bootc" report: **UNVERIFIED (blocked, HTTP 403)**. So the categorical statement "the bootc image does not boot on Raspberry Pi" is too strong for Pi 5 with direct firmware boot.
5. **bootupd is moving.** PR #938 (read EFI payloads from `/usr/lib/efi`) merged on 2025-07-25. PR #1073 ("Support managing non-EFI components at the ESP root", opened 2026-03-22) was tested on a Pi 4 running Fedora CoreOS 43 with `bcm2711-firmware`, and a reviewer said it is "what automotive needs for Raspberry Pi support". Red Hat's automotive work gives Pi firmware support a funded consumer beyond IoT.
6. **"Single base" is the weak alternative anyway.** Each alternative base carries its own vendor risk: Raspberry Pi OS is Pi-only, and Buildroot/Yocto put the maintenance burden on a solo founder. The fair comparison is "Fedora IoT/bootc as one profile" against those, not against a perfect base.

## 3. Why the counter-argument still fails (new failure-evidence sources)

Each source below was found by searching for failure, regressions, abandonment or under-resourcing, and opened.

| # | New source | Failure evidence | Effect on the claim |
|---|---|---|---|
| N1 | github.com/bootc-dev/bootc/issues/2605 (open, 2026-10-30) | **Regression on exactly OneMind's edge target.** From bootc v1.17.2, `bootc status/upgrade/rollback` fail with `SystemNotUEFI` on non-UEFI systems. The reporter runs a Pi 5 with direct firmware boot; 1.17.1 works and 1.17.3 fails. Fix PR #2602 is open, not merged. | **Strengthens.** Pi 5 bootc works only off the UEFI path, which upstream does not test. A point release broke update *and rollback*, the two properties OneMind needs most. |
| N2 | github.com/bootc-dev/bootc/issues/1968 (open, 2026-01-31) | After an `ostree-finalize-staged.service` timeout on a slow-storage ARM device, bootc cannot upgrade, roll back or apply another image. Recovery used an undocumented `bootc internals` command. No maintainer response on the page after more than 9 months. | **Strengthens.** Slow SD/eMMC ARM devices are the Pi tier. An unanswered brick-class report weighs on the 10-year, unattended-fleet case. |
| N3 | github.com/coreos/bootupd/pull/1073 (open, `needs-rebase`, changes requested 2026-04-23) and PR #938 (merged 2025-07-25) | #938 did **not** deliver Pi firmware handling; reviewers deferred it. #1073, the piece that manages Pi firmware at the ESP root, is stalled. So 20 months after issue #82, upstream still has no merged path for Pi firmware updates under bootc. | **Strengthens** "does not boot / not supported on Pi" for the U-Boot/ESP route. |
| N4 | nullr0ute.com/2026/10/raspberry-pi-5-on-fedora/ (opened) | Bus factor: the lead writes, "Basically I've just not had the time to write it up properly", and says he held the announcement for months to fix one bug. Pi 5 enablement reads as one person's work. CM5 and Pi 500 are "still works in progress". Sound is unsupported. The post does not mention the IoT edition. | **Strengthens** the vendor-risk reading of the issue #123 quote, and shows CM5 (the industrial and IIoT form factor) is not ready. |
| N5 | centos.org/centos10 (opened) plus CentOS Stream 10 Pi search | The long-life lineage (Stream 10, then RHEL) has **no official Pi image or bootc Pi image**. The only Pi option found is a COPR marked "Advanced users only" (copr.fedorainfracloud.org/coprs/lucamagrone/el10-pi, SECONDARY, listing only). | **Neutralises counter-point 2** for the Pi tier. The lineage escape hatch exists only for x86 and SystemReady arm64. |

## 4. Net assessment

- On a 10-year, solo-founder horizon, the decisive facts are these:
  - No supported lifecycle longer than about 13 months on the Fedora tier, declined explicitly for lack of resources (S2).
  - No supported long-life tier that covers Pi.
  - Pi 5 bootc runs only on a non-UEFI path, which just regressed (N1).
  - Pi firmware update support under bootupd is stalled (S4, N3).
  - Pi 5 enablement depends on one maintainer, and CM5 is not ready (N4).
- The counter-arguments (stream rebasing, the Red Hat lineage, progress on Pi 5) are real. They argue for keeping Fedora IoT/bootc as a **supported profile**, for x86 and SystemReady arm64 and possibly Jetson, which the reference list includes. They do not argue for making it the **single** base.
- **Verdict: upheld.** The conclusion survives. Three sub-facts need correcting (section 5).

## 5. Required corrections to the claim text

1. **EOL date:** cite it as SECONDARY or UNVERIFIED (Bodhi and Fedora docs are bot-walled), and note the conflicting 2027-11-24 `SUPPORT_END` report. Better, restate the risk as "about 13 months per release, no LTS or release-1 tree", which does not depend on the exact day.
2. **"bootc image does not boot on Raspberry Pi":** narrow it. Upstream offers no supported Pi bootc image. On Pi 4 the U-Boot/ESP route needs unmerged bootupd work (#935/#1073). On Pi 5, community installs boot via direct firmware, but that path is untested upstream and regressed in bootc 1.17.2 (#2605).
3. **"Pi 5 not in reference platforms":** keep it, pinned to iot-docs@3cfcfe7. Add that Fedora 44/45 support Pi 5 Model B as an MVP (no sound, CM5/500 WIP) per the IoT lead's 2026-10 post. The docs lag the code.

## 6. What evidence would flip the decision (toward Fedora IoT as single base)

Taken together, all of these would flip it. Items a and b are each necessary.

- **a. A supported long-life tier on Pi.** Either Fedora IoT offers a release-1, LTS or extended tree, reversing S2, or CentOS Stream 10 / RHEL image mode officially supports Raspberry Pi 5 (and CM5) with a published bootc image.
- **b. Upstream Pi bootc as a first-class target.** The bootupd ESP-root firmware support (#1073 or a successor) is merged and shipped in Fedora, fedora-iot-bootc publishes a Pi disk image that boots without an existing Fedora IoT install (reversing S6), and bootc CI covers non-UEFI or Pi boot so that regressions like #2605 are caught before release.
- **c.** Pi 5 **and CM5** are added to the IoT reference platforms.
- **d. Evidence of more than one funded maintainer for Fedora arm/Pi enablement**, for example Red Hat automotive taking ownership of Pi firmware in bootupd, as the #1073 reviewer comment hints.
- **e. A soak result in OneMind's own bake-off:** at least 6 months of unattended upgrade and rollback cycles on Pi 5 with no bricked units (DECISIONS: test x86, Pi and Jetson from the start).

**Signals that would make the claim stronger:** the fedora-iot org loses its lead, the IoT edition is demoted, or #2605 or #1968 stay unfixed through the next bootc minor release.

## 7. Claims ledger entries (rule 10)

| Fact | Version / date | Source status | Re-check by |
|---|---|---|---|
| F45 EOL 2027-12-08 vs 2027-11-24 | F45, released Oct/Nov 2026 | UNVERIFIED (blocked); SECONDARY conflict | 2027-05-10 |
| No release-1 tree for Fedora IoT | issue #123, 2025-10-15 | PRIMARY (opened) | 2027-05-10 |
| Pi 5 Model B MVP on Fedora 44/45; CM5 and 500 WIP | blog post 2026-10 | PRIMARY (maintainer's blog, opened) | 2027-05-10 |
| bootc 1.17.2+ non-UEFI regression on Pi 5 | issue #2605, 2026-10-30 | PRIMARY (opened) | 2027-05-10 |
| bootupd #935 and #1073 open | 2026-11-10 | PRIMARY (opened) | 2027-05-10 |
| CentOS Stream 10 maintained until about 2030 | centos.org/centos10 | PRIMARY (opened) | 2027-11-10 |

**Archiving:** load-bearing URLs (N1, N3, N4, S2) still need Wayback snapshots or hashed copies in `research-output/evidence/sources/`. This refuter was allowed to write only this file, so it did not archive them.

## Sources

- Cited (re-checked): https://github.com/fedora-iot/iot-distro/issues/123 ; https://github.com/fedora-iot/iot-distro/issues/82 ; https://github.com/coreos/bootupd/pull/935 ; https://github.com/fedora-iot/iot-docs/blob/3cfcfe788629bde64e5b189a479aee0800fb3698/user-docs/modules/ROOT/pages/reference-platforms.adoc#L3-L51 ; https://github.com/fedora-iot/iot-docs/blob/3cfcfe788629bde64e5b189a479aee0800fb3698/user-docs/modules/ROOT/pages/fedora-iot-bootc-raspberry-pi-example.adoc#L3 ; https://bodhi.fedoraproject.org/releases/F45 (blocked)
- New, opened: https://github.com/bootc-dev/bootc/issues/2605 ; https://github.com/bootc-dev/bootc/issues/1968 ; https://github.com/coreos/bootupd/pull/1073 ; https://github.com/coreos/bootupd/pull/938 ; https://nullr0ute.com/2026/10/raspberry-pi-5-on-fedora/ ; https://lwn.net/Articles/1103212/ ; https://github.com/fedora-iot/fedora-iot-bootc/pull/265 ; https://centos.org/centos10/
- SECONDARY or blocked: https://endoflife.ai/fedora/45 ; https://computingforgeeks.com/what-is-new-in-fedora-45/ (search snippet only) ; https://copr.fedorainfracloud.org/coprs/lucamagrone/el10-pi (search listing) ; https://fedora.yaasharc.me/posts/bootc/fedora-bootc-rpi5-report/ (403, UNVERIFIED)
