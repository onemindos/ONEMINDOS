# DC-02 · Blocking limitation for IoT/IIoT? — longevity refuter (round 4)

> **Refuter round 4 · lens: longevity and vendor risk · 2026-11-11.** Independent refuter (RESEARCH-MISSION.md §2 rule 7). Formed from the DC-02 Result in `decision-critical.md`, `01-FOUNDATION-DECISION.md`, the owning workstream file and the cited claim rows only; no earlier adversarial file was read first. New claims are in `evidence/claims/REF4-DC-longevity.csv`.

## Conclusion under test (rev. 3)
No G4 sub-check fails; G4 is **CONDITIONAL** with five mitigations, including protocol stacks as upstream-pinned app images with a CVE SLA, an own 62443-4-1 process or partner, and **go-fdo with funded interop** for zero-touch onboarding; NATS (whose MQTT listener is 3.1.1-only) stays the bus.

## Strongest counter-argument
The two load-bearing third-party components for IIoT onboarding and messaging are each governed by one company or are pre-1.0, and an industrial buyer evaluates a 10-15-year supplier chain.

1. **The bus has already had a near-relicensing event.** In April 2025 Synadia, NATS's sole corporate steward, proposed taking NATS out of the CNCF and forking the server under BSL; it backed down on 2025-05-01, transferring the trademarks to CNCF and keeping Apache-2.0 [C-REF4-DC-longevity-004]. The settlement keeps the code open, but the maintainers' employer has shown it will try to close the core when its business needs change, and Synadia reserved commercial products (e.g. security gateways) — exactly the features an IEC 62443 buyer asks for. The "MQTT 5 broker decision" is still open, so a second broker may be needed anyway.
2. **Zero-touch onboarding rests on a library with no release and no interop certificate.** go-fdo states it "has not yet completed interop testing with the FIDO Alliance", implements FDO 1.1, and has no tags or releases [C-REF4-DC-longevity-005]. "Funded interop" is a mitigation OneMind would pay for, on a codebase it does not control, against a spec that is already moving to 2.0.

## Why it does not flip
The flip needs a G4 sub-check that FAILs for Debian + RAUC and PASSes for an alternative. Both risks are **base-independent**: NATS and go-fdo would be the same on EL10 bootc or CIP Core. The governance risk raises the cost of G4 but does not move D2.

## Verdict: **weakened**
- Required change: add NATS governance to the risk register with a named exit (the Apache-2.0 NATS fork point is CNCF-held; keep the leaf/bus contract broker-neutral, and decide the MQTT 5 broker independently of Synadia's commercial line).
- Required change: treat FDO as "experimental until go-fdo tags a release and passes FIDO interop"; ship IDevID/802.1AR + manual claim as the day-one fallback.

## What would flip this verdict
- **To upheld:** a tagged go-fdo release with a FIDO interop result, and a published CNCF/NATS maintainer roster showing non-Synadia maintainers with merge rights.
- **Towards a real G4 failure:** any change in NATS server licensing, or go-fdo archived, while an alternative base ships a supported onboarding stack (e.g. RHEL's packaged FDO with a support contract).

## Sources opened (new)
- https://www.synadia.com/blog/nats-server-next-steps [C-REF4-DC-longevity-004]
- https://github.com/fido-device-onboard/go-fdo/blob/65061850e1c91a2cfe83c2dea748989a7e70c110/README.md [C-REF4-DC-longevity-005]
