# Refutation · W18 P0-2 · lens: robotics fit

**Target:** 28-KERNEL-IMAGE-OWNERSHIP-AND-DEV-TOOLCHAIN.md, P0-2: "No non-Linux kernel (seL4, Zircon/Fuchsia, HongMeng, Redox) is viable for OneMind in 5–10 years." Cited: C-W18-036 (HongMeng had to be Linux API/ABI-compatible), C-W18-035 (seL4 verification excludes IOMMU and boot, and covers specific configurations), C-W18-040 (Redox 0.9.0, pre-1.0). Recheck in 2031.
**Refuter:** independent, robotics lens · 2026-11-11 · read only the conclusion and its cited claim rows before forming this view.
**Verdict: WEAKENED.** "Do not replace Linux as OneMind's general-purpose host kernel" is upheld, and the failure evidence below strengthens it. The absolute "no non-Linux kernel is viable" is false for robotics, and the candidate list leaves out the kernels robots actually use.

## Strongest counter-argument

The candidate list is a list of general-purpose OS projects. In robotics, non-Linux kernels win in *subordinate* roles, and P0-2's wording rules those roles out too.

- **QNX** is in production on autonomous-vehicle compute alongside NVIDIA GPUs (DriveOS QNX with CUDA on Orin [C-REF-W18-robotics-002]). It now ships ROS 2 [C-REF-W18-robotics-003]. P0-2 does not mention it.
- **seL4** is in production today: NIO mass-produces the ONVO L60 on the seL4-based SkyOS-M [C-REF-W18-robotics-005]. Its robotics role in DARPA HACMS (quadcopter, land robot, Boeing Unmanned Little Bird) was as a partitioning kernel that keeps an untrusted guest away from the control path. That is "seL4 under Linux", not "seL4 instead of Linux", so the HongMeng argument (it had to copy the Linux ABI) does not apply to it. The seL4 point in C-W18-035 (IOMMU and boot sit outside the proof) weakens the guarantee but does not make seL4 unusable.
- **NuttX and Zephyr** (PX4, micro-ROS) are the standard flight and motor controller kernels. Over 5–10 years, OneMind will almost certainly ship robots with a non-Linux kernel on board.

A blanket "not viable for 5–10 years" could close off a safety island or partitioned design (seL4 or QNX hosting a Linux guest) for the robot tier, where certification may later be required.

## Failure evidence that supports the decision

- **Fuchsia/Zircon:** in January 2023 Google cut at least 16% (later reported as more than 20%) of the ~400-person team. In July 2023 it marked the smart-speaker targets unsupported and removed their code [C-REF-W18-robotics-004]. The sponsor has lost interest, so Fuchsia should stay off the list.
- **seL4 tooling churn:** CAmkES is "eventually to be replaced by Microkit". Microkit is "in active development … not all features and configurations supported yet" and supports only MCS configurations. The Microkit VMM is AArch64-only, with RISC-V still in development [C-REF-W18-robotics-006]. Building a seL4 plus Linux-guest partition now means betting on a framework migration that is still under way. That supports "not at launch".
- **QNX lock-in and lag:** CUDA on QNX is DRIVE-only and at 11.4 in DRIVE OS 6 [C-REF-W18-robotics-002]. QNX Everywhere is free only for non-commercial use (search summary; not confirmed on the release-notes page). This is vendor dependence, not openness.

## New sources

1. 9to5Google, "Google abandons work to move Assistant smart speakers to Fuchsia", 2023-07-25. https://9to5google.com/2023/07/25/google-abandons-assistant-speakers-fuchsia/
2. seL4 tools page (CAmkES superseded, Microkit incomplete, VMM AArch64-only). https://sel4.systems/tools.html
3. seL4 use page (NIO ONVO L60 production; HACMS robotics was research). https://sel4.systems/use.html
4. DRIVE OS 6.0.9 QNX CUDA docs and QNX Everywhere ROS 2 release notes (see the W18-P0-1-robotics file).

## Required changes

- Restate P0-2 as: "No non-Linux kernel is viable as OneMind's **general-purpose host kernel** (hub and companion compute) in 5–10 years."
- Add a short note on scope: robot MCUs use NuttX or Zephyr, and a certified safety island or partition kernel (QNX, or seL4 with a Linux guest) remains an open option for the robot tier, to be decided only if a certification requirement appears.
- Add QNX to the list of kernels considered, and record why it was rejected for the host: proprietary, no Kubernetes, and CUDA only through DRIVE.

## What would flip the decision

- **Toward non-Linux in a subordinate role (not as the host):** a customer or regulation requires functional-safety certification of robot compute, **and** the seL4 Microkit VMM (or QNX Hypervisor) runs a Linux guest with GPU passthrough on Jetson Orin or Thor, with a public reference. That would make a "seL4 or QNX under Linux" robot tier viable inside the window.
- **Toward replacing the host:** a microkernel with NVIDIA GPU or CUDA support **and** Linux driver reuse released as open source. This matches the author's own flip condition, which I did not change.
- **Making P0-2 stronger:** Microkit reaches feature parity and CAmkES is formally retired with no AArch64 VMM regression. That would not change the decision, but it would close the tooling-churn caveat.
