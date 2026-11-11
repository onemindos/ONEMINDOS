# DC-13 refuter: NVIDIA GPU drivers on Debian (robotics lens)

| Field | Value |
|---|---|
| Target | DC-13. Current answer (05 P0-6 and §7.2; 01 §3.1.5): **weakened, not flipped.** The Debian path works for device-plugin GPU access and time-slicing on the Pro box ("nothing needed fails"), but loses the Operator lifecycle, signed precompiled drivers and AI conformance. The Omni/Cluster GPU tier may run Ubuntu LTS + RKE2. |
| Cited claims | C-W2-026, C-W4-021, -022, -025, -028, -037, -038 |
| Lens | Robotics fit: a Pro box used for simulation, training and fleet-side perception |
| Protocol | RESEARCH-MISSION.md §2 rule 7. I read only the conclusion and its cited claims before forming this view. |
| Date | 2026-11-10. Re-check by 2027-05-10. |
| Verdict | **weakened** (the GPU-tier carve-out is upheld; "nothing needed fails on the Pro box" is not, for robotics workloads) |

## 1. Cited sources re-checked

The cited claims support the matrix facts: no Debian in the GPU Operator, AICR or the signed-driver lists, k3s absent from AI conformance, and DKMS-only Debian driver docs. I also confirmed that the Container Toolkit's tested-platform list still names **Debian 11 only** next to Ubuntu 22.04/24.04/26.04 [C-REF-DC-robotics-011].

## 2. Strongest counter-argument

The Pro verdict rests on a reference workload of "time-sliced Ollama/ComfyUI". For a robotics customer the Pro box is the **simulation and training node**, and that workload is Ubuntu-only.

1. **Isaac Sim's supported hosts are Ubuntu 22.04 (deprecated) and 24.04 on x86_64, plus Windows 11**, with a single validated Linux driver (595.58.03) [C-REF-DC-robotics-013]. Debian is not listed, and "the container is only supported on Linux" does not name Debian as a validated host. Robot sim-to-real loops (Isaac Sim/Lab, plus Isaac ROS on x86, which DC-15/FF-6 already found Ubuntu-only) are a needed capability for the robotics tier. On Debian they are unvalidated, which is close to the flip condition ("a needed feature fails on Debian 13 but works on a validated base") even if it is not yet a measured failure.
2. **The DKMS path regresses on routine Debian kernel updates.** NVIDIA's open-module DKMS build fails on Debian 13 point-kernel updates (6.12.94 → 6.12.96, and again on 6.12.101) with driver 595.71.05, leaving the kernel packages unconfigured. The issue has been open since 2026-07-22 with no NVIDIA response, and a user wrote "I had to block updates to the kernel" [C-REF-DC-robotics-012]. In OneMind's image build this breaks at build time rather than on the device, but it shows that Debian is not in NVIDIA's CI. Every Debian kernel security update then becomes an NVIDIA integration task, and on a validated base that work is NVIDIA's.

**Effect:** the robotics Pro/sim node belongs with the Omni/Cluster carve-out (Ubuntu 24.04 + NVIDIA's validated stack), not with the Debian Pro box. That widens the second x86 flavor from a "cluster tier" option to a likely default for every robotics customer's GPU box.

## 3. New sources (searched for regressions and support gaps)

- NVIDIA/open-gpu-kernel-modules issue #1258 (open, opened 2026-07-22): https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1258 [C-REF-DC-robotics-012]
- Isaac Sim requirements (6.x docs): https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html [C-REF-DC-robotics-013]
- NVIDIA Container Toolkit supported platforms: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/supported-platforms.html [C-REF-DC-robotics-011]

## 4. What would flip the decision

- **Back to Debian for the robotics Pro box:** a lab run of Isaac Sim 6.x headless in its container on a Debian 13 host with the NVIDIA debian13 repo driver at the validated version, passing NVIDIA's compatibility checker (`isaac-sim-comp-check`), plus a DKMS rebuild that survives two consecutive Debian point-kernel updates in the image pipeline.
- **To Ubuntu for all GPU boxes:** Isaac Sim fails in that lab on Debian, or a second DKMS regression on Debian 13 stays open for more than one Debian point release.
