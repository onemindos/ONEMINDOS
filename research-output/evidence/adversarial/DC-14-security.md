# DC-14 · Real-time kernel needs of robotics — security refuter

**Lens:** security · **Refuter:** REF3 (independent; did not read other adversarial files) · **Date:** 2026-11-11
**Target conclusion** (`08-robotics-drones-physical-ai.md` §5, `qbank/W7.md`): a PREEMPT_RT kernel exists on every target flavor (mainline 6.12+, Debian `linux-image-rt-*`, Raspberry Pi `-rpi-v8-rt`, NVIDIA L4T RT at Developer-Preview quality), and no alternative base improves Jetson. The flip condition is not met.

## Strongest counter-argument

Having an RT kernel doesn't settle whether a real-time loop can share a node with k3s **securely**:

1. **RT pods break the cluster's pod-security baseline.** ros2_control's controller_manager requests SCHED_FIFO priority 50 (C-W7-036). An unprivileged container gets that only with CAP_SYS_NICE (or a raised RLIMIT_RTPRIO, which Kubernetes has no pod-level field for). The Pod Security Standards forbid CAP_SYS_NICE in **both** Baseline and Restricted: Restricted allows adding back only NET_BIND_SERVICE [C-REF3-DC-security-003]. Every RT robot workload therefore needs a namespace exempted from PSS, a Kyverno exception, or a privileged pod. Any Market app that claims to be a "robot controller" gets that exemption too. A process with SCHED_FIFO on an isolated core can also starve the node (CPU isolation is not containment). So the design needs a security answer as well as a latency one.
2. **The Jetson RT kernel is a separate preview package set, and security fixes ship as L4T version bumps.** NVIDIA's 2026 Jetson fixes (CVE-2026-24148, CVSS 8.3 network; CVE-2026-24154 initrd injection) arrived only in L4T 35.6.4, 36.5 and 38.4. The public report doesn't mention the RT kernel packages [C-REF3-DC-security-005]. With RT at "Developer-Preview quality" (C-W7-009), nothing is known about whether `nvidia-l4t-rt-kernel` gets fixes at the same time as the standard kernel.

## Where the counter-argument fails

- **The Pi RT kernel does not lag on security.** On 2026-11-11 the Raspberry Pi trixie archive published `-rpi-v8-rt` at the same versions as `-rpi-2712` and `-rpi-v8`, up to 6.18.60 [C-REF3-DC-security-004]. The owner's C-W7-024 lists the RT builds only up to 6.18.50, so that row is out of date. It should be updated, but the change helps the conclusion. There is still no `rpi-2712` RT package.
- Both problems are **base-agnostic**. PSS applies to any Kubernetes, and on Jetson NVIDIA's kernel is used on every base (C-W7-009). Neither one makes an alternative base better, which is what the flip condition tests.

## Verdict: **upheld**

The flip condition is not met, and the security lens finds nothing that a different base would fix. Two required changes: (a) the robot profile needs a written RT security model: a dedicated namespace with a narrow Kyverno exception granting only SYS_NICE to signed, allow-listed images, never to Market apps by default, plus CPU-pinning limits; (b) before shipping RT on Jetson, check whether L4T RT packages get each security bulletin's fixes, and if they don't, the Jetson RT profile is lab-only.

## What would flip it

- **To weakened:** NVIDIA's RT packages are shown to miss a bulletin's fixes (security lag on Jetson RT), or Debian `linux-image-rt` stops being updated in step with the stable kernel.
- **To refuted:** an alternative base provides an RT kernel with security support on a flavor where OneMind's base has none (for example a supported Pi 5 `2712` RT kernel on Ubuntu with security updates, while Raspberry Pi's lags).

## Sources opened (new)
- C-REF3-DC-security-003 · https://kubernetes.io/docs/concepts/security/pod-security-standards/
- C-REF3-DC-security-004 · http://archive.raspberrypi.com/debian/dists/trixie/main/binary-arm64/Packages.gz (fetched; sha256 recorded in the ledger)
- C-REF3-DC-security-005 · https://securityonline.info/nvidia-jetson-linux-security-patch-cve-2026-24148/
