# Refuter report: W2 P0-2 (Fedora IoT as single base), technical lens

- **Refuter lens:** technical (boot chain, Pi 5, bootc/ostree, update lifecycle; requirements F-12, F-11, RS-4)
- **Date:** 2026-11-10 · **Re-check by:** 2027-05-10 (Fedora 46 release; bootupd ARM payload work)
- **Verdict:** **weakened.** The conclusion holds: Fedora IoT should not be OneMind's *single* base today. But three of the five supporting facts are stale or misframed. The decision is right, but its stated reasons are partly wrong. A future reviewer who sees those reasons fixed (for example, Pi 5 working on Fedora 45) could wrongly reverse the decision, or could wrongly rule Fedora IoT out as a supported profile (F-12).

## Claim under test

> Fedora IoT should not be OneMind's single base today. Fedora 45 reaches end of life 2027-12-08. The IoT lead declined an oldstable tree ("We don't have the resources for that"). The bootc image does not boot on Raspberry Pi (issue #82 and bootupd PR #935 both open). Raspberry Pi 5 is not in Fedora IoT's reference platforms, and bootc on a Pi requires a device already provisioned with Fedora IoT.

## What the cited sources confirm (re-opened 2026-11-10)

| Item | Source | Status |
|---|---|---|
| F45 EOL 2027-12-08 | Bodhi `GET /releases/F45` (JSON): `"released_on": "2026-11-03", "eol": "2027-12-08", "state": "current"`; also fedorapeople f-45 key-tasks schedule, row "Fedora Linux 45 End of Life Wed 2027-12-08" | **Confirmed.** The HTML page is behind Anubis, but the API returns the data. F45 was released 7 days ago, so the window is about 13 months. |
| "We don't have the resources for that" | fedora-iot/iot-distro#123, nullr0ute (Member), 2025-10-15; the issue is still open | **Confirmed.** The same comment adds that an oldstable tree "wouldn't fix the nvidia problem because all the releases move to new kernels at the same time". |
| bootc image does not boot on Pi | fedora-iot/iot-distro#82 (open) | **Misframed.** The issue concerns the *raw disk image built by bootc-image-builder*. It lacks the Pi firmware and U-Boot and uses GPT. It does not show that "bootc does not boot on Pi". In the thread, an RPi 4 booted a bootc base image with a local build of bootupd #935 plus one manual U-Boot rename or `config.txt` step. The maintainer rejected both manual fixes for the product. The thread never mentions the Pi 5. |
| bootupd #935 open | coreos/bootupd#935 | **Confirmed, but incomplete.** It is open, needs a rebase (bot, 2026-03-18) and has no approvals. Reviewers redirected its design: #938 ("step1: Extend generate-update-metadata() to read from /usr") was **merged 2025-07-25**. #1073 (non-EFI components at the ESP root, opened 2026-03-22) and tracking issue #959 (optional ARM firmware payloads) are still open. The work continues, but no Pi firmware path has been merged. |
| Pi 5 not a reference platform | `fedora-iot/iot-docs@3cfcfe78:user-docs/modules/ROOT/pages/reference-platforms.adoc#L3-L51` | **Confirmed but stale.** The list has Pi 3 and Pi 4/CM4 and no Pi 5. That file was last changed at `0a0783c7` on **2024-02-16**, before any Fedora Pi 5 work. The repo HEAD is 2026-09-30. Absence from this page is weak evidence of current hardware status. |
| bootc on Pi requires a device already provisioned with Fedora IoT | `fedora-iot/iot-docs@3cfcfe78:.../fedora-iot-bootc-raspberry-pi-example.adoc#L3` | **Confirmed verbatim:** "Using `bootc` with Fedora IoT currently requires that you have already provisioned a device with Fedora IoT." The documented path is: flash the ostree IoT image, then `bootc switch`. That is a working path, not a dead end. |

## Strongest counter-argument

1. **The end-of-life date is not a cliff for an image-based fleet.** Fedora IoT's `fedora/stable/<ARCH>/iot` branch "corresponds to the Fedora release that's the latest stable" (`iot-docs@3cfcfe78:user-docs/modules/ROOT/pages/rebasing.adoc#L124-L132`). Rollback across a rebase is documented ("Just like system updates, rebases can be reversed", same file, L176). Automatic staging uses `rpm-ostreed-automatic.timer` (`applying-updates-UG.adoc#L104-L141`, default policy `none`). Fedora CoreOS runs production fleets this way: nodes follow a stream that is "updated automatically" and moves to the next Fedora major (`coreos/fedora-coreos-docs@e3e27608:modules/ROOT/pages/update-streams.adoc#L23-L28`). "F45 EOL 2027-12-08" is a constraint only for a design that pins a major version. The real cost is a **forced major rebase every ~6 months, with a new kernel each time**. This is what the IoT lead meant by the "nvidia problem" (iot-distro#123). For OneMind (Jetson, NVIDIA GPU nodes, robotics drivers), that cadence is the actual technical objection, and the claim should say so instead of citing a date.

2. **The Pi 5 premise is out of date as of last week.** Peter Robinson (nullr0ute, the same IoT lead) wrote on 2026-10-27 that Fedora 45 "will work—with caveats—on all variants of the Raspberry Pi Model 5B". He listed what works: microSD/NVMe boot, wired and Wi-Fi networking, USB, accelerated graphics, fan and thermal control, SPI and I2C. The Fedora 44 `cma=` boot workaround is no longer needed (nullr0ute.com/2026/10/raspberry-pi-5-on-fedora/; LWN 1103212). His post links a separate community "Fedora bootc RPi5 report" (fedora.yaasharc.me), which is **UNVERIFIED**: Cloudflare blocked the fetch and the Wayback Machine was unreachable. So "Pi 5 is not in reference platforms" rests on a two-year-old doc page while the hardware support has moved. A decision based on that fact would flip on the next docs PR, even though nothing material would have changed.

3. **The bootc-on-Pi gap applies to image creation, not runtime.** A Pi 4 with Fedora IoT flashed can `bootc switch` to a custom image today (Pi example doc). The gaps are (a) building a first-boot disk image with bootc-image-builder and (b) bootupd updating Pi firmware. For a solo founder that is a real factory-provisioning gap (OneMind needs one flashable image per device class). It does not mean bootc is unusable on Pi fleets.

4. **"Single base" is a straw man for F-12.** REQUIREMENTS F-12 requires a full, fair evaluation "as the base or as a supported profile". Every fact in the claim argues only against *single* base. None argues against a Fedora IoT / bootc **profile** for x86 and Pi 4, where it is reference-tested and also lists Jetson Xavier/Orin as reference platforms (reference-platforms.adoc). Without that qualification, the claim reads as rejecting Fedora IoT outright.

## New failure, abandonment and lifecycle evidence (searched for, opened)

These new sources **support** the conclusion while correcting the stated reasons:

- **Bus factor ≈ 1 (maintainer concentration).** `gh api repos/fedora-iot/fedora-iot-bootc/commits?since=2025-11-10` (HEAD `b68cc3e2`) shows 84 human commits in 12 months: **77 by pcdubs**, 6 by nullr0ute, 1 by djach7, plus 77 by dependabot. Together with "We don't have the resources for that", this is evidence of a thinly staffed edition. For a 10-year horizon this is a stronger reason than the end-of-life date.
- **Deprecated update mode.** Fedora Change "Fedora IoT Unified Core" (accepted for F40; wiki last updated 2024-02-08): the old rpm-ostree mode "is not maintained anymore, less tested and thus prone to bugs", and "Fedora IoT is the last rpm-ostree based Fedora edition using this older, soon to be deprecated mode." The change itself says users will see no impact, but it shows IoT lagging behind its sibling editions.
- **bootc image regression in CI.** virt-s1/rhel-edge#11175 (open, 2026-01-14): the "Fedora-IoT-44 iot-bootc-image test case is failing due to bootc-image-builder error Installing bootloader". A bootupd/grub2 link was suspected (RHBZ 2429501, bootc-dev/bootc#1907). The failure could still be reproduced on compose 20260116.0. The bootloader layer of IoT bootc images is still fragile on x86 as well.
- **Pi 5 caveats that matter to OneMind.** The same nullr0ute post says: no sound, "a number of other things" missing, USB boot not supported, and **Compute Module 5 and Pi 500+ still works in progress**. CM5 is the form factor for industrial and robotics carriers (F-11). PCIe, the camera (CSI) and general GPIO are not mentioned. These gaps are a better argument against making Pi 5 depend on Fedora than the reference-platforms page.
- **Context, against the PRD:** Fedora IoT's own PRD lists "short maintenance lifecycles" as an IoT security risk (`iot-docs@3cfcfe78:user-docs/modules/ROOT/pages/prd.adoc#L30`). Its delivery model is nonetheless a 13-month Fedora release window with no oldstable tree.

## Corrected claim (proposed)

> Fedora IoT should not be OneMind's single base today. It remains a candidate supported profile (x86, Pi 4, Pi 5B from F45). Reasons: (1) every node must take a major rebase and new kernel about every 6 months, and there is no oldstable tree ("We don't have the resources for that", iot-distro#123), which conflicts with NVIDIA/Jetson and robotics driver pinning; (2) the image tooling has an effective bus factor of one (77 of 84 human commits in 12 months); (3) bootc cannot yet produce a first-boot Pi disk image or update Pi firmware (iot-distro#82; bootupd #935/#1073/#959 open; #938 merged); (4) Pi 5 support is new and partial in F45 (no sound, no USB boot, CM5 not yet supported) and is not yet listed as a reference platform.

## What would flip the decision

Toward **Fedora IoT as the base (or the primary Pi/x86 profile)**, all of these together:

1. bootupd ARM firmware payloads merged (#935 or its #1073/#959 successors), and Fedora IoT publishing a bootc **Pi disk image that boots without first provisioning the device with ostree IoT**.
2. Pi 5 **and CM5** added to `reference-platforms.adoc`, with PCIe/NVMe, CSI camera and GPIO confirmed.
3. A documented, CI-tested unattended major rebase (stable ref plus greenboot rollback) on Pi 5 and an x86 GPU node, with a stated NVIDIA driver story across kernel bumps.
4. Visible staffing growth: at least 3 regular human committers on fedora-iot-bootc over 12 months, or a Red Hat commitment.
5. Alternatively, a longer-lived sibling in the same lineage (CentOS Stream 10 bootc / RHEL image mode) gaining Pi 5 firmware support. That would satisfy F-12 without Fedora's 13-month window.

Toward **dropping Fedora IoT even as a profile:** the IoT edition being demoted from Edition status (see `iot-docs wg-docs/.../edition-promotion.adoc`), pcdubs or nullr0ute leaving with no replacement, or the old rpm-ostree mode being removed before IoT finishes migrating.

## Sources

- Bodhi API F45: https://bodhi.fedoraproject.org/releases/F45 (JSON); schedule https://fedorapeople.org/groups/schedule/f-45/f-45-key-tasks.html (PRIMARY)
- https://github.com/fedora-iot/iot-distro/issues/123 ; https://github.com/fedora-iot/iot-distro/issues/82 (PRIMARY)
- https://github.com/coreos/bootupd/pull/935 ; /pull/938 (merged 2025-07-25) ; /pull/1073 ; /issues/959 (PRIMARY)
- fedora-iot/iot-docs@3cfcfe788629bde64e5b189a479aee0800fb3698: reference-platforms.adoc#L3-L51 (last changed 0a0783c7, 2024-02-16), fedora-iot-bootc-raspberry-pi-example.adoc#L3, rebasing.adoc#L124-L176, applying-updates-UG.adoc#L104-L141, prd.adoc#L30 (PRIMARY)
- coreos/fedora-coreos-docs@e3e27608d9f754af67a304e89820ab43c66119c7:modules/ROOT/pages/update-streams.adoc#L23-L28 (PRIMARY)
- fedora-iot/fedora-iot-bootc@b68cc3e259d6983de13e3277ecf7ed9ca11d6c80 commit history via GitHub API (PRIMARY, computed)
- NEW: https://nullr0ute.com/2026/10/raspberry-pi-5-on-fedora/ (PRIMARY, IoT lead's blog) ; https://lwn.net/Articles/1103212/ (SECONDARY)
- NEW: https://fedoraproject.org/wiki/Changes/Fedora_IoT_Unified_Core (PRIMARY)
- NEW: https://github.com/virt-s1/rhel-edge/issues/11175 (PRIMARY)
- UNVERIFIED (fetch blocked): https://fedora.yaasharc.me/posts/bootc/fedora-bootc-rpi5-report/
- Not archived here: Wayback was unreachable from this session. The pinned SHAs above serve as the archive for the code and docs citations.
