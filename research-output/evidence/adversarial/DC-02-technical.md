# DC-02: refuter report on "no blocking limitation for IoT/IIoT" (technical lens)

- **Conclusion under test (decision-critical.md DC-02 rev. 3; 01 §4.7, §5.8; 09 P0-1, P0-4, §1(d), G4-M2/M3):** no G4 sub-check fails. G4 is CONDITIONAL with five mitigations: supervise-not-control; an RT IIoT SKU on x86 `linux-image-rt`; protocol stacks as upstream-pinned app images with a CVE SLA; OneMind's own 62443-4-1 process or a partner; go-fdo with funded interop. A maintenance-horizon condition is added on top. Status: partial.
- **Flip condition:** any G4 sub-check FAILs for Debian + Rugix and PASSes for an alternative.
- **Lens:** technical. I read only the conclusion, 01 §4.7 and §5.8, and 09's P0-1/P0-4 rows and G4 table. I formed this view before reading any other refuter file.
- **Date:** 2026-11-11

## Verdict: **weakened**. The relative claim holds; the absolute claim ("no part of the stack blocks IIoT") is not shown.

1. **The question is absolute, but the answer only meets a relative test.** DC-02 asks: "Does any part of the stack block IIoT?" The flip condition counts a failure only when an alternative passes the same sub-check. Many gaps are common to every candidate, and those can never trigger it. Zero-touch onboarding is the clearest case: Debian, EL10 bootc and CIP all depend on the **same** go-fdo code (09 §1(d)). The FDO sub-check is therefore "CONDITIONAL everywhere", which can never flip D2, even if FDO never works. That is a sound reason not to change the base. It does not answer "does anything block IIoT".
2. **The zero-touch mitigation rests on a library with no interop and no releases.** go-fdo's README still says it "has not yet completed interop testing with the FIDO Alliance". It implements FDO 1.1, and its Releases section is empty [C-REF4-DC-technical-004]. The FDO 2.0 core is one 18-commit PR, opened 2026-10-12 by a single author. On 2026-10-27 it was still failing lint and TinyGo tests, and intermediate commits "do not build on their own" [C-REF4-DC-technical-005]. "Adopt go-fdo and fund interop" therefore means OneMind funds, or performs, the interop that upstream hasn't done, on a protocol version that is in mid-rewrite. That is a build item of unknown size, not a mitigation. 09 priced it at "~1 week" (G4-M2).
3. **The MQTT 5 gap is now permanent, so the IIoT site always runs two brokers.** On 2026-07-07 a NATS maintainer wrote: "I don't think we are likely to accept PRs for MQTT 5 support" [C-REF4-DC-technical-003]. 09 P0-4's flip condition ("NATS adds MQTT 5") is therefore effectively closed. The Mosquitto/NanoMQ bridge (G4-M3) becomes permanent architecture. It adds a second broker to the 62443 zone model, a second CVE SLA (already required by mitigation 3) and a bridge whose subject mapping must follow the locked grammar. G4 does not fail on this, but the "~1 week" estimate covers only the first build, not the lifetime cost.

## Strongest counter-argument

G4 is "CONDITIONAL with five mitigations". Every one of them is OneMind-owned work: a Pi 5 RT build, an x86 RT SKU, a pinned-container CVE SLA for every protocol stack, a 62443-4-1 process, FDO interop, a second MQTT broker and a 10k fleet test. None is evidenced end to end. A solo founder cannot do all of that alongside the consumer product. In practice that is a blocker for IIoT **at launch**, even though no single sub-check fails. Under the flip condition's relative logic, an alternative that shares the same gaps (go-fdo, NATS) can never expose the problem, so the "not met" result is partly built into the test. The steelman's EL10 path shows the difference: go-fdo is **packaged by the distribution** there (CentOS Stream 10 / AlmaLinux 10), so on EL10 the FDO sub-check is "package exists, interop unproven". On Debian it is "no package, interop unproven".

## New sources (searched for abandonment, refusals and immature upstreams)

- **N1.** nats-io/nats-server discussion #8362, maintainer reply of 2026-07-07 refusing MQTT 5 PRs. Opened. [C-REF4-DC-technical-003]
- **N2.** fido-device-onboard/go-fdo README (interop not completed, FDO 1.1, no releases). Opened. [C-REF4-DC-technical-004]
- **N3.** fido-device-onboard/go-fdo PR #285, "FDO 2.0 core" (open; failing lint and TinyGo tests on 2026-10-27). Opened. [C-REF4-DC-technical-005]
- Checked, and it **supports** the conclusion: Eclipse hawkBit 1.0 reached Eclipse "Mature" status in 2026, and 1.1.0 shipped on 2026-07-03, so a RAUC fleet plane has a live upstream. Search result only; not ledgered.

## What would flip it

- **Toward refuted:** LAB-W8-4 cannot complete DI → TO2 with go-fdo on Debian (with or without a TPM) while the distro-packaged EL10 build can; or a 1k+ simulated fleet cannot be driven by a RAUC fleet plane while Flight Control on bootc can.
- **Toward upheld:** go-fdo tags a release that has completed FIDO Alliance interop testing, LAB-W8-4 passes on Debian x86 + TPM and on a Pi 5 with a secure element, and the Mosquitto bridge passes the Sparkplug TCK (LAB-W8-3).
- **Wording fix wanted now:** "no G4 sub-check fails relative to the alternatives; four of five are unproven in absolute terms and need OneMind-built work, not just configuration".
