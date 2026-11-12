# DC-07 · One update framework across x86, Pi 5 and Jetson — refuter (security lens)

**Refuter:** REF3, security lens, 2026-11-11. Inputs read: the DC-07 question (`decision-critical.md`), the W3 answer (`04-image-install-updates-rollback.md` §5.3, `qbank/W3.md` Q6/Q47) and its cited claims C-W3-013, -021, -049…-054. No other refuter file was read first.

## Conclusion under test
No single open-source engine covers x86 + Pi 5 + stock-L4T Jetson. Recommended: **one OneMind release contract** (one signed manifest, one key hierarchy, one health gate, one UI/CLI) over **per-board backends**: RAUC on x86 and Pi 5; NVIDIA rootfs A/B plus image-based OTA on Jetson, with OneMind writing "a wrapper". Cost claim: "the Jetson one is NVIDIA's code; we write a wrapper."

## Strongest counter-argument
The answer treats the Jetson backend as NVIDIA-maintained plumbing and the OneMind part as a thin wrapper. On the security side it is the reverse: **the code that decides whether an update is authentic on Jetson is OneMind's, not NVIDIA's.**

1. **NVIDIA's image-based OTA has no built-in payload authenticity check.** The guide ships the payload as a plain `ota_payload_package.tar.gz`, *recommends* that the integrator add "a signature or encryption", and tells the device to "validate the downloaded OTA payload package … according to your own security requirements" and to "create a complete and secure OTA solution" [C-REF3-DC-security-001]. So "one key hierarchy" on Jetson means a OneMind-written verifier (download, signature check, extraction, hand-off to NVIDIA's tools as root) — exactly the class of code where RAUC needed a CVE for a TOCTOU (CVE-2020-25860) and again in 2026 for a signature that covered only the first bytes of a large bundle [C-REF3-DC-security-003]. A from-scratch verifier written by a sole developer is the weakest link of the fleet, and it sits on the robot tier that the DC itself calls the moat.
2. **Two verifiers, two attack surfaces, two CVE streams.** With RAUC on x86/Pi and a home-grown verifier on Jetson, OneMind must track RAUC advisories (and pin the verity format: CVE-2026-34155 hits `plain` bundles > 2 GiB, which a Jetson-sized image would exceed [C-REF3-DC-security-003]) *and* keep its own verifier correct. "One contract" unifies the manifest format, not the trust-critical code path.
3. **Jetson security fixes arrive only as BSP point releases** (Oct 2025: 35.6.3, 36.4.7, 38.2.2 [C-REF3-DC-security-002]). Whatever backend is chosen must ship BSP point releases routinely and unattended, including UEFI firmware. The security posture of the robot tier therefore rests entirely on the unbuilt wrapper and test T-W3-06; it is not "NVIDIA's code" in any sense that transfers responsibility.
4. **The alternative the answer lists only as a fallback is the safer primary.** RAUC with a custom `nvbootctrl`/capsule backend (or a RAUC bundle whose install handler calls NVIDIA's OTA tools) gives **one audited signature-verification path on all three boards**, with dm-verity bundles, and leaves NVIDIA's A/B, validation hook and recovery kernel in place underneath. That is "one framework" for the part that matters to security, which is the flip condition DC-07 asks about.

## Verdict: **weakened**
The factual core holds (no engine has a maintained stock-L4T integration [C-W3-013, C-W3-021, C-W3-053]). The recommendation's cost and risk framing does not: the Jetson backend is not a thin wrapper but a security-critical verifier OneMind must write, and a RAUC-as-verifier design over NVIDIA's slot mechanics would deliver one trust path. Required change: make "RAUC (verity bundles) as the single verifier on all boards, NVIDIA A/B as the Jetson slot backend" the primary design to test in T-W3-06, and forbid `plain` bundles.

## What would flip it
- **To upheld:** NVIDIA documents a signed-payload verification step inside its OTA tools (for example, verification tied to the UEFI db/PKC keys) for r38/r39, or a maintained open-source verifier for NVIDIA payloads exists that OneMind can reuse.
- **To refuted:** T-W3-06 shows RAUC's custom-backend handler cannot drive NVIDIA's image-based OTA across BSP majors (so two verifiers are unavoidable) **and** a review of the OneMind verifier passes; or DC-09 moves Jetson to meta-tegra so one engine (Mender or SWUpdate) covers all three.

## New sources (opened)
- NVIDIA Jetson Linux r36.5.2, Software Packages and the Update Mechanism — https://docs.nvidia.com/jetson/archives/r36.5.2/DeveloperGuide/SD/SoftwarePackagesAndTheUpdateMechanism.html [C-REF3-DC-security-001]
- NVIDIA Security Bulletin, Jetson and IGX, October 2025 — https://nvidia.custhelp.com/app/answers/detail/a_id/5716 [C-REF3-DC-security-002]
- RAUC changelog, 1.15.2 security fix CVE-2026-34155 — https://rauc.readthedocs.io/en/latest/changes.html [C-REF3-DC-security-003]
