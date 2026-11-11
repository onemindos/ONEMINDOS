# DC-20 refuter: security lens (REF4)

**Target:** DC-20, a distro base vs a build-from-source appliance. **Lens:** security. **Date:** 2026-11-11. **Protocol:** RESEARCH-MISSION.md §2 rule 7; read only the DC-20 question and result in `decision-critical.md` and the cited claims C-LAB-minimal-image-dc20-011…013 and -021. No earlier adversarial file was read first.

## Claim under test

"Flip not met; D1 stands, now because of the userspace patch backlog, not build time." Debian 13 triaged all 161 userspace CVE IDs; Buildroot 2025.02.19 has 32–53 with unapplied upstream fixes; Buildroot has only 7–18% fewer IDs, below a 50% threshold.

## Strongest counter-argument

The *new* reason for keeping D1 reads the lab result the wrong way round from a security view.

1. **"Triaged" is not "fixed".** C-LAB-minimal-image-dc20-013 says Debian's 161 userspace IDs are not-fixed (74) or wont-fix (87), so **0 have a fix available**. A Debian developer's own description of those tags: `no-dsa`/`postponed` "should be fixed in pu", while `ignored` means "there is a good reason why the CVE should never be fixed", and some `ignored (Minor issue)` tags are applied wrongly [C-REF4-DC-security-005]. So on Debian OneMind ships 161 known IDs it cannot patch without forking Debian packages, 87 of them by policy never. On Buildroot the 32–53 IDs have upstream fixes that OneMind, or Buildroot's LTS point releases, can apply. Buildroot's 2025.02 LTS is now a 3-year line with **paid stewards** doing weekly backports [C-REF4-DC-security-006], which shrinks the "OneMind owns the backlog" cost the conclusion relies on. A backlog with known fixes is a better security position than a backlog without fixes; for the CRA (no *known exploitable* vulnerabilities, Annex I), both need a VEX statement per ID, and Debian's bigger list needs more of them.
2. **The metric cannot carry a 50% threshold.** A peer-reviewed comparison of Grype and Trivy on 927 images found the tools agreed on the count in only 15.3% of images and disagreed on severity 60,799 times for identical IDs [C-REF4-DC-security-004]. CPE matching against a Buildroot SBOM and distro-tracker matching against Debian are different code paths in Grype, and the lab itself notes false positives (OpenSSH "fixed in 9.9p2" reported against 9.9p2). A 7–18% difference measured by one scanner is inside that noise; it neither supports nor rules out "materially fewer".
3. **Attack surface is not measured.** The Buildroot image is 4–6× smaller. Fewer binaries, setuid files and listening services reduce exploitability even when CVE IDs are similar, and the kernel share (73–80%) is identical either way, so it cancels out rather than favouring Debian.

What survives: the kernel dominates CVEs and is the same either way; aarch64 and CUDA legs are untested; Debian gives a security team and signed binary archive OneMind does not have to staff. Those are good reasons for D1, but they are not the reason the result now states.

## Verdict: **weakened**

D1 is not overturned, but its stated security rationale ("userspace patch backlog") is inverted: Debian's backlog is larger and unfixable in place, Buildroot's is smaller and fixable. The conclusion should rest on maintainability, the kernel being equal, and the untested aarch64/CUDA legs, and should drop the claim that the patch backlog favours Debian.

## What would flip it

- **To upheld:** a second scanner (Trivy or OSV-Scanner) plus manual reachability triage of the top Critical+High userspace IDs on both legs shows Debian's not-fixed/wont-fix IDs are unreachable or not exploitable in the minimal image while Buildroot's open ones are; or Buildroot's LTS point releases fail to close the 32–53 within 90 days.
- **To refuted (toward Buildroot on security):** after the next two Buildroot 2025.02.x point releases the open-fix count drops near zero while Debian's 161 stay open, and the aarch64 leg repeats the 4–6× size gap; then C3 favours Buildroot and only C5 (one-developer maintainability) holds D1.

## Sources (new, opened)

- Boles et al., SCAM 2024: https://www.cs.montana.edu/izurieta/pubs/SCAM2024.pdf [C-REF4-DC-security-004]
- Debian LTS list, tag meanings (2025-04-26): https://lists.debian.org/debian-lts/2025/04/msg00060.html [C-REF4-DC-security-005]
- Buildroot LTS page: https://buildroot.org/lts.html [C-REF4-DC-security-006]
