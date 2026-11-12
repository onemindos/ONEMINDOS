# DC-15 — Refuter report: ROS 2 tier support on the host OS, technical lens

- **Conclusion under test (08 FF-6, FF-7; qbank W7 DC-15):** ROS 2 treats Debian as Tier 3 and Debian packages no ROS 2, but Ubuntu 24.04 (the JetPack 7 base) is also Tier 3 for Lyrical. So ROS 2 runs in containers on every flavor, and Debian is not singled out. The one Ubuntu-only coupling is Isaac ROS on x86 (Ubuntu 24.04 hosts only), so DC-15 is **CONDITIONAL** on LAB-W7-3. Container fast paths need hostNetwork, hostIPC and SYS_NICE, which Baseline PSS forbids, so D6 needs a scoped "robot runtime" exception.
- **Flip condition:** a capability needed on the robot only works on an Ubuntu host.
- **Lens:** technical. I read only the conclusion and its cited claims (C-W7-026 to 034, 037, 038).
- **Date:** 2026-11-10

## Verdict: **upheld** (with two caveats the lab must cover)

The tier facts are right (C-W7-026, 027, 030), and so is the observation that the robot's ROS stack is containerised on every flavor. The cited container mechanics (C-W7-032 to 034) are accurate. I found no capability that works only on an Ubuntu host. What I did find is that "containers make the host irrelevant" is only partly true for NVIDIA GPU containers, and that the failure modes are **silent**. Neither caveat flips D2, but both change what LAB-W7-2/3 must measure.

## Checks of the cited sources

| Sub-claim | Claim | Result |
|---|---|---|
| Debian Tier 3 (Jazzy Bookworm only; Lyrical trixie, EOL 2028-08-09) | C-W7-026, C-W7-027 | Holds. Note that trixie's Lyrical Tier 3 support ends 2028-08, three years before Lyrical's EOL in 2031 (C-W7-029). This is irrelevant to the host *if* ROS is container-only, so the host must never be asked to build ROS. |
| Ubuntu 24.04 Tier 3 for Lyrical | C-W7-027 | Holds. This is the strongest point for the conclusion: the Jetson base is not privileged either. |
| Isaac ROS x86 hosts: Ubuntu 24.04 only, driver 595+, CUDA 13.2+ | C-W7-031 | Holds. Debian's own driver is too old (550, per DC-13), so the Debian x86 flavor needs NVIDIA's `debian13` repo before Isaac ROS can run at all. |
| Fast DDS SHM needs host network + host IPC; Baseline PSS forbids them | C-W7-033, C-W7-034 | Holds. |
| rmw_zenoh needs a router | C-W7-032 | Holds. |
| Jetson device plugin needs toolkit ≥1.11 | C-W7-038 | Holds, but see N2 in the DC-17 report: on Jetson the working k8s path is CDI in CSV mode plus a manual node label. |

## Strongest counter-argument

On NVIDIA hardware, a container is **not** independent of the host. In CSV/CDI mode the Jetson runtime mounts the host's L4T driver libraries into the container. Isaac ROS images are pinned to specific JetPack/driver versions, and an OTA of the host BSP has broken the dev container (N2). On x86, Isaac ROS fixes a driver floor (595+) that the host must supply. So "ROS in containers everywhere" gives OS-independence for plain ROS 2, but GPU-accelerated ROS couples the **container release train to the host driver/BSP train**. An A/B image that updates the driver without updating the robot containers in step can break the robot. Second, the Fast DDS SHM failure is silent: discovery succeeds and no data flows (N1). A robot-runtime exception granting hostNetwork + hostIPC also makes those pods host-equivalent. That is a large hole in D6, not a "scoped" one, unless the allowlist is enforced by signature (as the conclusion says).

## New sources (searched for failures and regressions)

- **N1. eProsima Fast-DDS issue #2624** — https://github.com/eProsima/Fast-DDS/issues/2624 (opened). Two containers with `--network=host` exchange no data. Fast DDS derives the same host ID in both, assumes SHM, and cannot reach the other container's `/dev/shm`. The maintainer recommends `--ipc=host`. The issue was closed as a duplicate of #1698/#1750/#1755, so this is a long-standing class of bug. [C-REF-DC-technical-003]
- **N2. NVIDIA Isaac ROS forum, "Error in dev container creation"** — https://forums.developer.nvidia.com/t/error-in-dev-container-creation/332196 (opened). After an OTA from L4T 36.3 to 36.4, the dev container failed: `libnvidia-eglcore.so.540.3.0: no such file or directory`. The moderator said Isaac ROS 3.1 is not compatible with L4T 36.4.3 and to use 3.2. [C-REF-DC-technical-004]
- Context (opened for DC-17): ProventusNova, "ROS 2 Across Containers: the Fast DDS Gotchas" (2026-09-27), https://proventusnova.com/blog/ros2-fast-dds-containers-genio. It describes "the nodes discover each other, the topics show up, and yet data does not move", and DDS locators going stale when a Wi-Fi interface changes address. The second failure is relevant to robots that roam between APs.

## What would flip the decision

- **Flip for the x86 GPU tier:** LAB-W7-3 fails on Debian 13 + NVIDIA `debian13` repo + toolkit (Isaac ROS container does not start, or NITROS/CUDA graphs fail) while the same image works on an Ubuntu 24.04 host with the same driver. That is the stated flip, and it stands.
- **Flip for any tier (new):** an Isaac ROS release documents a minimum **host** component that Debian cannot ship (for example a kernel module or VPI/PVA host service only packaged for Ubuntu), or NVIDIA's container toolkit drops Debian from its install docs.
- **Required lab additions (not flips):** LAB-W7-2 must check for silent fallback (assert SHM is in use, not just that messages arrive), and must run one A/B update that moves the host NVIDIA driver while the robot container stays fixed, to prove the coupling is managed.
