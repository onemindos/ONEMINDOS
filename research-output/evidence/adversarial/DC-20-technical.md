# DC-20: refuter report on a distro base vs a build-from-source appliance, technical lens

- **Conclusion under test (decision-critical.md DC-20 Result; 01 §6.2, D1 row):** the same minimal x86 core built with mkosi (Debian 13.7) and Buildroot 2025.02.19 LTS. Buildroot is 4–6× smaller, has a complete SBOM and incremental builds of 29–102 s, but only 7–18% fewer CVE IDs against a pre-registered 50% threshold, because the kernel is 73–80% of IDs either way. Debian has triaged all 161 userspace IDs, while 32–53 of Buildroot's have unapplied upstream fixes. Flip not met; D1 stands because of the userspace patch backlog.
- **Flip condition:** the from-source build is maintainable by one developer and scores higher on C1 and C3 (W3 steelman: materially fewer CVEs, < 1 h incremental builds, a CUDA path).
- **Lens:** technical. I read only the conclusion and its cited claims (C-LAB-minimal-image-dc20-008…013, -021). I formed this view before reading any other refuter file. This is the first dedicated DC-20 refuter.
- **Date:** 2026-11-11

## Verdict: **weakened**

The measurements are honest, and the decision may still be right. The **CVE clause**, the reason the conclusion now gives, rests on a metric that cannot tell the two builds apart where they differ most:

1. **The kernel count is identical by construction.** grype matches the kernel by version, so Debian's generic kernel (4,230 modules) and Buildroot's tailored kernel (59 modules) score almost the same 428–440 IDs [C-LAB-minimal-image-dc20-010, -012]. Configuration is the main way a from-source build reduces kernel exposure, and this metric ignores it. The embedded toolchains already filter on it. Yocto's `improve_kernel_cve_report.py` checks the source files actually compiled (`SPDX_INCLUDE_COMPILED_SOURCES`) and is documented to cut kernel CVE false positives by 70–80% [C-REF4-DC-technical-003]. A Buildroot patch series (v1/v2, Feb 2026) adds the same filter to `support/scripts/cve-check` through the kernel's `compile_commands.json` and the kernel CNA's cvelistV5 data. It is still in review and gives no measured numbers [C-REF4-DC-technical-004].
2. **What-if arithmetic (my estimate, not a measurement).** Take the lab's Buildroot figure of 428–440 kernel IDs and remove 70–80% as code-not-present: about 90–130 remain, for about 150–240 in total with userspace. Debian's generic kernel compiles most drivers, so the same filter would remove fewer, perhaps 20–40%, leaving about 420–500 in total. The reduction would then be about 50–70%, near or over the pre-registered 50% threshold. The comparison has to be measured, not assumed, but the 7–18% figure can't be quoted as the size of the build-method effect.
3. **"Debian triaged all 161" isn't "Debian is safe".** The lab counts 74 *not-fixed* and 87 *wont-fix* IDs as having "0 fixable" [C-LAB-minimal-image-dc20-013]. In the tracker's own terms, unfixed issues stay open "for further work", and `<ignored>` means "no updates will be provided", so both mean the package is still affected and Debian has chosen not to ship a fix [C-REF4-DC-technical-005]. For the CRA, OneMind still has to assess those 161 IDs itself, through VEX or its own justification. Buildroot's 32–53 have a fix available, which can be the *easier* backlog: a version bump inside an LTS that backports security fixes, rather than a vendor decision OneMind can't override.

This doesn't flip D1 on its own. The CUDA clause is untested, and NVIDIA userland is still absent on Buildroot. The one-developer maintainability of a userspace backlog is real, and the aarch64 leg hasn't run. It does weaken the stated reason. The pre-registered CVE clause may pass under a code-presence metric, so "Flip not met … because of the userspace patch backlog" should become "Flip not decided on CVEs; D1 stands on CUDA and maintainability."

## Strongest counter-argument

DC-20's CVE verdict compares two kernels by version string, which gives the same count by construction, and then credits Debian for won't-fix triage that leaves the IDs open. Under the compiled-source filtering that Yocto ships and Buildroot is adding, the tailored kernel could plausibly clear the 50% threshold. The answer would then be "Buildroot wins C3 and loses C2/C5 (NVIDIA, solo upkeep)", a trade-off for Zeus to decide rather than a measured non-flip.

## New sources (searched for failures, regressions and lifecycle limits)

- **N1.** Yocto Project 5.3 manual, "Checking for Vulnerabilities". Opened. `improve_kernel_cve_report.py` with `SPDX_INCLUDE_COMPILED_SOURCES` "reduces CVE false positives by 70%-80%". https://docs.yoctoproject.org/5.3/dev-manual/vulnerabilities.html [C-REF4-DC-technical-003]
- **N2.** Buildroot mailing list, "[PATCH v2 0/2] Linux kernel CVE filtering improvements" (F. Lehoussel, 2026-02-18/19, last reply 2026-02-24, not yet merged). Opened. https://ratatoskr.run/buildroot/2026/02/11784767/t [C-REF4-DC-technical-004]
- **N3.** Debian Security Tracker documentation. Opened. Defines `<no-dsa>`, `<postponed>` and `<ignored>` ("no updates will be provided"); `<unfixed>` means "for further work". https://security-team.debian.org/security_tracker.html [C-REF4-DC-technical-005]
- (Context) TECH VEDA, "Your SBOM Is Ready. Your Kernel CVE Triage Is Not." (R. Bharadwaj, 2026-07-16): the kernel is now the largest CNA, and compiled-source data can't be added to products already in the field. This is secondary and not ledgered as load-bearing.

## What would flip it

- **→ upheld:** re-run `results/sbom-cve.md` with a compiled-source kernel filter on **both** legs (Buildroot's `compile_commands.json` and Debian's own config and debug sources) and a VEX pass on Debian's no-dsa and ignored IDs. If Buildroot's reduction stays below 50%, the original conclusion stands on all clauses.
- **→ refuted (CVE clause met):** the filtered comparison shows ≥ 50% fewer IDs for Buildroot. DC-20 then turns on the CUDA clause and the one-developer anchors, and needs the aarch64 + CUDA leg (DC20-R6) before D1 can be called confirmed.
