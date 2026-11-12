# DC-09 refuter: base for the Jetson flavor (cost and business lens)

| Field | Value |
|---|---|
| Target | DC-09 (Q7, Q46, Q59). Conclusion in `evidence/qbank/W7.md` (DC-09 row, Q46, Q59) and `08-robotics-drones-physical-ai.md` FF-3: "Keep **NVIDIA L4T Ubuntu 24.04 (JetPack 7.2+)** for the Jetson flavor (ADR-001 D2 confirmed). Debian on Jetson is not a supported option. Yocto meta-tegra is NVIDIA-official since JetPack 7.2 and is the runner-up. Partial: the license text (Q59) wasn't opened; G1 CONDITIONAL." `01-FOUNDATION-DECISION.md` reuses it as the DC-09 tie-break for S2. |
| Lens | Cost and business (legal right to ship, cost of the fallback) |
| Protocol | RESEARCH-MISSION.md §2 rule 7. Only the conclusion and its cited claims (C-W7-007, 008, 015, 016, 051, 056; C-W2-050 as cited by 01 for G1) were read. |
| Date | 2026-11-10 (re-check by 2027-05-10) |
| Verdict | **weakened**. "Debian on Jetson is unsupported" and "meta-tegra is official" **hold**. "Keep L4T Ubuntu" rests on a G1 gap the conclusion understates: the Jetson rootfs is a **modified Ubuntu**, so the Canonical IP-policy blocker that `01` uses to keep Ubuntu off the core applies here too, unresolved. |

## 1. Re-checking the cited sources

| Sub-claim | Ledger | Holds? |
|---|---|---|
| JetPack 7 = kernel 6.8 + Ubuntu 24.04, Orin and Thor | C-W7-007 | Yes |
| JetPack 7.2 lists official Yocto (OE4T) and "Canonical Ubuntu 24.04 for Jetson" as supported; Debian is not listed | C-W7-008 | Yes |
| meta-tegra LTS branches: wrynose = R39.2.1, scarthgap = R36.5.2 | C-W7-015 | Yes |
| meta-tegra is concentrated: top contributor 2,373 commits vs next 189 | C-W7-016 | Yes. This is a bus-factor risk on the named fallback, and the conclusion does not carry it into the runner-up's cost. |
| BSP binaries under the Tegra Software License Agreement; text not opened | C-W7-056 | Yes. G1 is unverified for the NVIDIA part. |

## 2. Strongest counter-argument

**The Jetson flavor has the same redistribution problem that kept Ubuntu off the core, and it is the costlier one to discover late.**

- `01-FOUNDATION-DECISION.md` rejected Ubuntu 26.04 for the core mainly on G1: "redistribution of modified versions of Ubuntu must be approved, certified or provided by Canonical", otherwise remove the trademarks **and recompile the binaries** (C-W2-050).
- A OneMind Jetson image is a modified Ubuntu: L4T Ubuntu plus OneMind's agent, k3s, A/B config and branding. When asked whether a product may ship an L4T rootfs built from Ubuntu-base, the NVIDIA forum reply says the L4T redistribution answer "does not extend to Ubuntu root file system", that "L4T packages a root file system derived from Ubuntu", and that the vendor must "adhere to" Canonical's IP terms and contact Canonical [C-REF-DC-cost-007]. An earlier NVIDIA reply on whether its own Jetson image complies also defers to Canonical [C-REF-DC-cost-008]. NVIDIA does not grant downstream rights to the Ubuntu part.
- So "keep L4T Ubuntu" has one of three costs, and the conclusion priced none of them:
  1. **a Canonical agreement**, which is the same agreement that would re-open the Ubuntu core (S1 "what re-opens" item 1). If OneMind has to get it for Jetson anyway, Debian's core advantage on G1 shrinks;
  2. **trademark scrub plus recompile** of the Ubuntu userland, which is effectively building your own distro, i.e. more work than meta-tegra;
  3. **meta-tegra**, the "runner-up", which drops the Ubuntu question and has official NVIDIA recipes (C-W7-008), and which would also turn Mender, SWUpdate or RAUC into one framework across the family (DC-07).
- **Security cadence favours whoever tracks BSP point releases fastest.** Jetson CVE fixes ship only in point releases (36.5, 38.4 for CVSS 8.3/7.6 in March 2026) [C-REF-DC-cost-006]. On stock L4T, OneMind waits for NVIDIA's apt/OTA packages; on meta-tegra, it waits for the OE4T bump, which C-W7-016 shows rests largely on one maintainer. Neither is free, and the conclusion compares them on capability only.

**Why it is not refuted.** Stock L4T keeps full JetPack (CUDA, TensorRT, Isaac ROS containers) without a build system, which matters a lot for a sole developer (M-6). Canonical and NVIDIA have a public Jetson partnership, so permission may be obtainable, and many robot vendors ship L4T images today. No source found shows Canonical enforcing against a Jetson product. The risk is legal and commercial uncertainty, not a demonstrated failure.

## 3. New sources (searched for redistribution disputes, CVE patch timing, maintainer concentration)

| ID | Source | What it shows |
|---|---|---|
| C-REF-DC-cost-007 | https://forums.developer.nvidia.com/t/l4t-redistribution-license-issue-for-manually-generated-root-file-system/306285 | The L4T redistribution answer excludes the Ubuntu rootfs; vendors must follow Canonical's IP terms. |
| C-REF-DC-cost-008 | https://forums.developer.nvidia.com/t/does-nvidias-official-jetson-nano-image-comply-with-ubuntu-canonicals-iprights-policy/226020 | NVIDIA defers compliance to Canonical. |
| C-REF-DC-cost-006 | https://nvidia.custhelp.com/app/answers/detail/a_id/5797/ | Jetson security fixes ship only as BSP point releases. |

Caveat: 007 and 008 are forum replies (SECONDARY); the staff badge on 007 is not visible. They show NVIDIA's posture, not a legal ruling.

## 4. What would flip the decision

- **Flips to meta-tegra:** Canonical declines written permission for a modified, OneMind-branded L4T Ubuntu image, or asks for a per-device fee above H-1 margins. Then the Jetson flavor moves to Yocto meta-tegra, and DC-07 is re-scored for a single framework.
- **Flips the core decision instead (toward Ubuntu):** Canonical grants permission that covers **both** the Jetson image and an Ubuntu x86/Pi image at an acceptable price. That satisfies S1 re-open item 1 for free.
- **Upholds as written:** a written Canonical or NVIDIA statement (or counsel's opinion) that a OneMind image built on unmodified L4T Ubuntu packages, with OneMind additions only in separate packages, is not a "modified version" under the policy; plus Q59 (Tegra SLA text) opened and PASS for redistribution.

**Required correction:** put G1 for the Jetson flavor under the same Q-W2-1 counsel and Canonical outreach as the core (`26-OPEN-QUESTIONS-FOR-ZEUS.md`), and record meta-tegra's bus factor (C-W7-016) against the fallback.
