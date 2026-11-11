# Refuter report: FF-1 (DC-08), robotics-fit lens

- **Refuter lens:** robotics fit (robots and drones in the field for a decade on Jetson)
- **Date:** 2026-11-10 · **Re-check by:** 2027-05-10 (BSP facts: 6 months)
- **Verdict:** **weakened** (the direction holds; two factual parts are wrong, and the metric is the wrong one for robots)

## Claim under test

> NVIDIA commits Jetson hardware availability (Orin modules through January 2032, AGX Orin Industrial through July 2033, T5000 through August 2035, T4000 through January 2036) but publishes no software-support period per Jetson Linux release. Observed branch lifetimes: r32 from 32.1 (Mar 2019) to 32.7.6 (Nov 2024), about 5.7 years; r34/r35 from 34.1 (Apr 2022) to 35.7.0 (Oct 2026), still active at 4.5+ years.

## What the cited sources confirm (re-opened 2026-11-10)

| Item | Source | Status |
|---|---|---|
| Orin commercial modules through Jan 2032, AGX Orin Industrial through Jul 2033, T5000 through Aug 2035, T4000 through Jan 2036 | lifecycle page | Confirmed |
| The lifecycle page states no software support period; only "EOL notice ... a minimum of 8 months prior to the last shipment" | lifecycle page | Confirmed |
| r32: 32.1 (Mar 2019) to 32.7.6 (Nov 2024) | Jetson Linux archive | Confirmed |
| r34.1 (Apr 2022) to 35.7.0 (Oct 2026) | Jetson Linux archive | Dates confirmed |
| The archive states no end-of-support policy per release | Jetson Linux archive | Confirmed |

## Strongest counter-argument

1. **"Still active" is false. r35 ended on 30 Oct 2026.** NVIDIA's announcement says "JetPack 5.1.8 marks the final release for JetPack 5 series". JetPack 5.1.8 ships Jetson Linux R35.7, and the post lists it as the "EoL release" for AGX Xavier and Xavier NX. NVIDIA gave notice on 15 Jan 2026 ("scheduled to reach End of Life (EoL) in Q3 2026"). So r34/r35 is a closed branch of about 4.5 years (Apr 2022 to Oct 2026), not an open-ended one. The two observed branch lifetimes are 5.7 and 4.5 years, so the trend is getting *shorter*.

2. **"Publishes no software-support period" is too strong.** NVIDIA does publish a general branch policy, though not a date for each release. The JetPack 6.1 blog (21 Nov 2024) says a JetPack branch "typically remains in the active state for about two years" (features, CVE fixes, PCN additions), then moves to "the sustaining state", where "it continues to receive CVE fixes and PCN updates". NVIDIA also gives EOL notice ahead of time: about 9.5 months for JetPack 5 (Jan 2026 notice, Oct 2026 final release). The JetPack 4 end was announced with its final release (22 Nov 2024), and the 2021 roadmap had announced its move to sustaining mode. The accurate wording is: *no end-of-support date per release and no contractual minimum, but a published active (about 2 years) plus sustaining (open-ended) policy and an EOL notice per branch.*

3. **Robotics fit: branch lifetime is the wrong metric, and it flatters NVIDIA.** A robot ships on a release in the *middle* of a branch, so what matters is the support left after the ship date:
   - **Jetson Nano:** the lifecycle page says the hardware is available through **Jan 2027**, but its only software (JetPack 4 / r32, Ubuntu 18.04, kernel 4.9) has been EOL since **Nov 2024**. NVIDIA's EOL post says "no longer receive any critical updates". Canonical says Ubuntu Pro/ESM covers the 18.04 userspace, but the JetPack 4 kernel "remains outside of the scope". So a Nano robot bought new in 2026 ships with no vendor security support at all.
   - **Xavier NX / AGX Xavier:** the hardware is available through **Jul 2027** (lifecycle page), but the software ended at JetPack 5.1.8 in **Oct 2026**. No JetPack 6 or 7 supports Xavier.
   - **Orin:** this is the same pattern on a larger scale. Orin has already gone through JetPack 5 (EOL), JetPack 6 (sustaining since late 2024, per the FAQ and the 6.1 blog) and now JetPack 7.2.x. A robot fleet frozen on any Orin branch must re-base its whole OS (Ubuntu 20.04 to 22.04 to 24.04, a new kernel, new CUDA/TensorRT ABIs) about every 2 to 4 years to stay patched. For a 10-year robot product, that means *2 to 3 full BSP migrations*, each needing re-validation of cameras, motor drivers, real-time patches and ROS 2. None of them can be done as a simple A/B delta.

4. **The hardware dates are not stable either.** NVIDIA's own pages disagree. The JetPack 6.1 blog (Nov 2024) extended Xavier NX 16GB "to Q1 2028", and the Jetson FAQ says AGX Xavier/Xavier NX are available "until January 2028" and AGX Xavier Industrial "until July 2031". The current lifecycle page lists Xavier NX 16GB and AGX Xavier Industrial as available through **July 2027**. Either the dates were cut or the pages are out of date. Either way, the "committed" hardware dates in the claim can move, and they should be re-checked each cycle instead of being treated as anchors.

5. **There are partial bridges, so a frozen BSP is not automatically fatal.** NVIDIA points users to paid partners: TimeSys and Codethink for the JetPack 4 kernel, and RidgeRun for JetPack 5. RidgeRun reports CIP kernel 5.10 (CIP support through 2031) running on AGX Xavier with GPU, MIPI camera and codecs validated. DC-08's flip condition says "with no affordable bridge", so the existence of these bridges is relevant to that clause. Their cost is unknown, and they are vendor-dependent.

## New sources (opened 2026-11-10; found by searching for EOL, abandonment and lifecycle cuts)

1. NVIDIA Developer Forums, "Announcing End of Life for NVIDIA JetPack 5 with the release of JetPack 5.1.8" (30 Oct 2026): https://forums.developer.nvidia.com/t/announcing-end-of-life-for-nvidia-jetpack-5-with-the-release-of-jetpack-5-1-8/387446
2. NVIDIA Developer Forums, "JetPack 5 upcoming End-of-Life notice" (15 Jan 2026; RidgeRun CIP reply 20 May 2026): https://forums.developer.nvidia.com/t/jetpack-5-upcoming-end-of-life-notice/357718
3. NVIDIA Developer Forums, "Announcing End of Life for NVIDIA JetPack 4 with the release of JetPack 4.6.6" (22 Nov 2024): https://forums.developer.nvidia.com/t/announcing-end-of-life-for-nvidia-jetpack-4-with-the-release-of-jetpack-4-6-6/314300
4. NVIDIA Technical Blog, "NVIDIA JetPack 6.1 Boosts Performance and Security ..." (21 Nov 2024; active/sustaining policy and module extensions): https://developer.nvidia.com/blog/nvidia-jetpack-6-1-boosts-performance-and-security-through-camera-stack-optimizations-and-introduction-of-firmware-tpm/
5. NVIDIA Jetson FAQ (JetPack 6 and 5 "sustaining"; module lifetime 5 years, up to 10; Xavier dates that disagree with the lifecycle page): https://developer.nvidia.com/embedded/faq
6. Canonical, "JetPack 4 EOL" (the ESM userspace cover excludes the JetPack 4 kernel): https://ubuntu.com/blog/jetpack-4-eol. Seen in search results only, not opened, so it is not counted as one of the two required sources.

## Corrected claim (proposed)

> NVIDIA commits Jetson hardware availability (Orin through Jan 2032, AGX Orin Industrial through Jul 2033, T5000 through Aug 2035, T4000 through Jan 2036; dates have changed before) but gives no end-of-support date per Jetson Linux release. Its published policy is about 2 years "active" followed by an open-ended "sustaining" phase (CVE fixes), ended by a branch EOL notice. Observed branch lifetimes: r32 Mar 2019 to Nov 2024 (about 5.7 years, final 32.7.6); r34/r35 Apr 2022 to Oct 2026 (about 4.5 years, final 35.7.0 = JetPack 5.1.8, EOL). Hardware has outlived its software: the Nano is sold through Jan 2027 with software EOL since Nov 2024, and Xavier is sold through Jul 2027 with software EOL since Oct 2026.

## What would flip the decision

- **Toward refuted** (OneMind can rely on NVIDIA's BSP): NVIDIA publishes an end-of-sustaining date for each JetPack/Jetson Linux branch that runs to at least the module availability date, for example "r36 CVE fixes through Jan 2032 for Orin". Or a branch receives CVE releases after its EOL announcement.
- **Toward upheld/stronger** (DC-08 flips ADR-001 D2): JetPack 6 / r36 gets an EOL notice before about 2029 while Orin is still sold through 2032. Or JetPack 7 drops a module family before that module's availability date, repeating the Nano and Xavier pattern.
- **On the "affordable bridge" clause:** published pricing or terms from RidgeRun, TimeSys or Codethink for multi-year Jetson kernel maintenance (CIP 5.10/6.x on Orin), or upstream Linux coverage of Orin/Thor good enough to run a mainline or CIP kernel with GPU and cameras. Either would remove the flip even when NVIDIA's own window is short.
- **Hardware anchor:** an NVIDIA statement that confirms which Xavier date is authoritative (Jul 2027 or Jan 2028), and whether Orin's Jan 2032 has ever been cut.

## Note for the author

The claim is useful but understates the risk. Replace "still active" with "EOL Oct 2026 (35.7.0 / JetPack 5.1.8)". Cite the active/sustaining policy instead of saying nothing is published. Measure the remaining window from a typical robot ship date, not the full branch lifetime.
