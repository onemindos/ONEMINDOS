# Refutation · W18 P0-1 · lens: robotics fit

**Target:** 28-KERNEL-IMAGE-OWNERSHIP-AND-DEV-TOOLCHAIN.md, P0-1: "Linux is the only kernel family that passes OneMind's gates." Cited: C-W18-029 (Kubernetes control plane Linux-only), C-W18-027 (CUDA Linux/Windows only), C-W18-028 (NVIDIA FreeBSD driver x64-only, no CUDA), C-W18-034 (ROS 2 Tier 1 is Ubuntu and Windows).
**Refuter:** independent, robotics lens · 2026-11-11 · read only the conclusion and its cited claim rows before forming this view.
**Verdict: WEAKENED.** The decision (Linux on the hub and on robot companion compute) stands. The stated grounds are too broad, and one grounding claim is incomplete.

## Strongest counter-argument

Robotics and autonomous vehicles already run a non-Linux kernel with CUDA and ROS 2 in production: **QNX**.

- NVIDIA DriveOS offers "Linux or QNX" as the application OS, ships CUDA, cuDNN and TensorRT in its SDK, and claims ISO 26262 compliance [C-REF-W18-robotics-001].
- DRIVE OS 6.0.9 installs CUDA for aarch64 QNX and builds samples for the Orin GPU (SMS=87) [C-REF-W18-robotics-002]. "CUDA is Linux/Windows only" [C-W18-027] is therefore wrong as a general statement. The CUDA *installation guide for Linux* does not cover other OSes, but that does not mean no other OS has CUDA.
- ROS 2 ships on QNX: a ROS 2 APK was added to QNX Everywhere on 2026-06-19 [C-REF-W18-robotics-003]. REP 2000 tiers [C-W18-034] list only platforms the ROS project builds, not vendor ports.

The conclusion also does not split the robot into its layers. On a typical OneMind robot (a PX4 drone, a ground robot), the flight or motor controller runs an RTOS (NuttX, Zephyr or FreeRTOS, reached from ROS 2 through micro-ROS), not Linux. "Linux is the only kernel family" holds for the hub and the companion computer, not for the whole robot. If the ADR reads P0-1 literally, a future safety island or MCU kernel decision could be treated as already settled, which it is not.

## Why it does not refute the decision

- QNX fails the Kubernetes gate [C-W18-029]: no control plane, and no listed worker support.
- CUDA on QNX exists only inside NVIDIA's DRIVE program, at CUDA 11.4 in the DRIVE OS 6.0.9 docs [C-REF-W18-robotics-002], while the Linux line is at 13.5 [C-W18-027]. I found no public Jetson (JetPack) QNX path. That gap is a lifecycle risk for anyone who chose QNX, and it supports Linux. I did not check whether DRIVE OS 7 on Thor ships a newer CUDA for QNX. That check is open.
- QNX Everywhere's ROS 2 package is new and vendor-supplied. I found no independent production robotics reference for it.

## New sources (failure, lifecycle, lock-in)

1. NVIDIA DriveOS product page: QNX as an alternative application OS. CUDA and safety features are tied to the gated DRIVE program. https://developer.nvidia.com/drive/os
2. DRIVE OS 6.0.9 QNX sample build docs: CUDA for aarch64 QNX, held at CUDA 11.4 (a version gap against Linux). https://developer.nvidia.com/docs/drive/drive-os/6.0.9/public/drive-os-qnx-installation/common/topics/installation/build-samples/build-run-sample-apps-qnx.html
3. QNX Everywhere release notes: ROS 2 APK (QNXE-1601), June 2026. https://www.qnx.com/developers/docs/qnxeverywhere/rel_notes.html

## Required changes

- Restate P0-1 as: "Linux is the only kernel family that passes the hub and companion-compute gates (Kubernetes **and** CUDA on Jetson **and** ROS 2 Tier 1 together)."
- Correct the CUDA wording to "CUDA is publicly available on Linux and Windows. QNX CUDA exists only inside NVIDIA DRIVE (11.4 in DRIVE OS 6)."
- Add a sentence saying that the MCU or flight-controller kernel (NuttX, Zephyr) and any certified safety-island kernel are outside P0-1.
- Lower the confidence of the *wording* from High to Medium. Keep the confidence of the *decision* at High.

## What would flip the decision

- NVIDIA publishes a QNX (or other non-Linux) BSP with current CUDA for **Jetson** (Orin or Thor) outside the DRIVE program, **and** OneMind requires a safety-certified (ISO 26262 or IEC 61508) kernel on robot compute, **and** robot compute is not required to be a Kubernetes node (for example, robots join only as NATS leaf nodes). If all three hold, QNX becomes a real candidate for the robot compute tier. The hub would stay on Linux.
- Kubernetes adds a supported non-Linux, non-Windows node OS (no sign of this).
