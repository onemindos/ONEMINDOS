# DC-15 · ROS 2 tier support on the host OS — refuter (security lens)

**Refuter:** REF3, security lens, 2026-11-11. Inputs read: the DC-15 question, the W7 answer (`08-robotics-drones-physical-ai.md` §6, FF-6/FF-7, `qbank/W7.md`) and cited claims C-W7-026, -027, -030, -031, -033, -034.

## Conclusion under test
Debian is Tier 3 for ROS 2, but so is Ubuntu 24.04 for Lyrical, so ROS 2 runs in **pinned multi-arch containers on every flavor**; DC-15 is CONDITIONAL only on Isaac ROS on a Debian x86 host (LAB-W7-3). Containerized fast paths need `hostNetwork`, `hostIPC` and `SYS_NICE`, handled by a scoped, signed "robot runtime" exception.

## Strongest counter-argument
The tier analysis is right; the security cost of the chosen mitigation is unpriced.

1. **The robot-runtime exception exposes the middleware's attack surface on the host network namespace.** With `hostNetwork: true`, Fast DDS binds its RTPS listeners on the robot's real interfaces, not a pod network a NetworkPolicy can fence. Fast DDS has a live stream of *unauthenticated, network-reachable* memory-safety bugs: CVE-2025-62799 is a heap overflow in the DATA_FRAG receive path that "an un authenticated sender" triggers with "a single malformed RTPS DATA_FRAG packet", with potential RCE [C-REF3-DC-security-004]; July–September 2026 brought more remote DoS/overflow advisories plus a Critical "insecure connections" advisory in the security plugin [C-REF3-DC-security-005]. A process compromised that way runs in a pod that already shares the host's network and IPC namespaces and may hold `SYS_NICE` — one step from the host. Allowlisting by *signature* (who built the image) does not mitigate a remote exploit of a correctly signed image.
2. **"Pinned" ROS images mean OneMind owns middleware patching.** Fast DDS 2.14 (Jazzy's line) left standard support in September 2026; 3.6 has standard support to March 2028 [C-REF3-DC-security-006]. A fleet that pins ROS per site (which the answer recommends) carries unpatched DDS stacks unless OneMind rebuilds and re-signs every robot image per advisory. On a Tier 1 Ubuntu host this is the same problem — so it is not a Debian penalty — but it is a recurring cost the CONDITIONAL verdict omits.
3. **GPU-accelerated ROS containers add the NVIDIA hook surface.** Isaac ROS containers run through the NVIDIA Container Toolkit, whose createContainer hook gave host root from a three-line image (NVIDIAScape, CVSS 9.0) [C-REF3-DC-security-007]. On a host-equivalent robot pod this is less a new risk than a confirmation that robot pods must be treated as host code.

None of this needs an Ubuntu host: every point applies identically on Ubuntu, so the host-OS decision (D2) is not moved.

## Verdict: **upheld** (with a security condition added)
The D2 conclusion stands: no capability found works only on an Ubuntu host, and the security costs are host-OS-neutral. Required additions: (a) robot pods are classed as host-equivalent in the threat model, not "scoped"; (b) DDS on robots runs with SROS2/DDS Security and a host firewall restricting RTPS ports to the robot's own interfaces, or prefers rmw_zenoh with a router (normal pod networking) where SHM is not needed; (c) a Fast DDS advisory feed and an image-rebuild SLA are part of the robot runtime.

## What would flip it
- **To weakened:** LAB-W7-2 shows Fast DDS SHM cannot work without `hostNetwork` *and* rmw_zenoh cannot meet the robot's latency budget, so every robot must expose RTPS on host interfaces; or a Fast DDS RCE is exploited in the wild against ROS 2 robots before the signed-image rebuild path exists.
- **To refuted:** an Ubuntu host offers a mitigation Debian cannot (for example, a vendor-patched ROS/DDS stack under Ubuntu Pro ESM for ROS that is unavailable as a container on Debian).

## New sources (opened)
- OSV, CVE-2025-62799 (Fast DDS DATA_FRAG heap overflow) — https://osv.dev/vulnerability/CVE-2025-62799 [C-REF3-DC-security-004]
- eProsima/Fast-DDS security advisories — https://github.com/eProsima/Fast-DDS/security [C-REF3-DC-security-005]
- Fast DDS RELEASE_SUPPORT.md — https://github.com/eProsima/Fast-DDS/blob/master/RELEASE_SUPPORT.md [C-REF3-DC-security-006]
- Wiz, NVIDIAScape CVE-2025-23266 — https://wiz.io/blog/nvidia-ai-vulnerability-cve-2025-23266-nvidiascape [C-REF3-DC-security-007]
