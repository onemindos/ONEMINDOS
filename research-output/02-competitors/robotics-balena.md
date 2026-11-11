# balena for robots: Tier C teardown (robotics angle)

**Workstream:** W1 (Tier C) · **Tag:** `TD-tier-c-robotics` · **Date:** 2026-11-11 · **Status:** draft, brief (Tier C: no refuter pass)
**Claims:** `evidence/claims/TD-tier-c-robotics.csv` (C-TD-tier-c-robotics-070…073) plus the Tier B balenaOS teardown's claims (`C-TD-balenaos-*`) and [C-REF-W19-longevity-011] · **Sources:** `evidence/sources/TD-tier-c-robotics.md`, `evidence/sources/TD-balenaos.md`
**Scope:** the platform itself (Yocto OS, A/B updates, Supervisor, Jetson support, pricing) is already torn down at code level in [`balenaos.md`](balenaos.md), pinned to meta-balena v9.0.6. This page does **not** redo that. It asks one question: **how well does balena serve robots, and what does that teach OneMind?**

> ### Explain it like I'm the founder
> balena is the only product in this tier that **is an operating system with real A/B updates**, and it runs on Pi 5, Jetson Orin and Thor, and x86 [C-W2-040][C-TD-balenaos-041]. It markets itself to robot and drone makers [C-TD-tier-c-robotics-070], and robotics teams do pick it: on the ROS forum one team "settled on Balena" because it does both jobs at once, A/B for the OS and Docker for the robot code [C-TD-tier-c-robotics-073].
>
> But it is a **general IoT platform with a robotics landing page**, not a robotics product. Its ROS 2 example is archived and built on a ROS version that died in 2023 [C-TD-tier-c-robotics-071]. Its update health check only proves the container engine and the cloud VPN came back, not that the robot works [C-TD-balenaos-019]. Long-term support releases last nine months and only on paid plans [C-TD-balenaos-039]. **For OneMind:** balena proves one company can ship one update system across Pi, Jetson and x86. OneMind must add what robots need on top: ROS 2 awareness, a robot-level health gate, local-first operation and multi-year support.

---

## 1. Profile (robotics view)

| Topic | What balena does | Evidence |
|---|---|---|
| **Architecture** | balenaOS (Yocto, read-only root) + balenaEngine + Supervisor on the device; balenaCloud for identity, OS updates, deltas and the dashboard. openBalena is the self-hosted server (AGPL, single-user, CLI-only). | [C-TD-balenaos-010][C-TD-balenaos-035][C-TD-balenaos-006][C-TD-balenaos-007] |
| **Base OS** | Own Yocto distro. Jetson images build from OE4T meta-tegra (L4T 39.2 / JetPack 7.2), not NVIDIA's Ubuntu rootfs. | [C-TD-balenaos-041][C-TD-balenaos-042] |
| **Update / rollback** | OS as a container image pulled into the spare slot; boot-count fallback; Jetson also stages a UEFI capsule and fails health if firmware and kernel L4T versions differ. Apps: per-service strategies and update locks. | [C-TD-balenaos-012][C-TD-balenaos-020][C-TD-balenaos-045][C-TD-balenaos-044][C-TD-balenaos-032] |
| **App format for robot code** | Docker Compose subset; hardware access through `io.balena.features.*` labels; "contracts" for required hardware/OS. ROS nodes run as containers. | [C-TD-balenaos-031][C-TD-balenaos-033][C-TD-balenaos-034] |
| **Robotics content** | A robotics landing page linking ROS "robot block" and multi-drone simulation posts; example repos for ROS 2 Foxy, now archived (last push 2023-06-17; Foxy EOL 2023-06-20). No ROS, MAVLink or PX4 code in meta-balena. | [C-TD-tier-c-robotics-070][C-TD-tier-c-robotics-071][C-MATRIX-002] |
| **AI features** | None for robots; only an archived experimental CLI-wrapper MCP server. | [C-TD-balenaos-057] |
| **Hardware** | 150+ device types, incl. Pi 5, Jetson Orin Nano/AGX, Jetson Thor, generic x86. Custom boards are a paid service. | [C-W2-040][C-TD-balenaos-053] |
| **Licence** | OS, Supervisor, engine: Apache-2.0. openBalena server: AGPL-3.0. | [C-TD-balenaos-003][C-TD-balenaos-004][C-TD-balenaos-006] |
| **Business model** | balenaCloud per-device plans (first 10 devices free); ESR (9-month support releases) on paid plans; custom device support for a fee. | [C-TD-balenaos-052][C-TD-balenaos-039][C-TD-balenaos-053] |

## 2. Robot-relevant failure reports

| Report | What it teaches OneMind | Evidence |
|---|---|---|
| A kernel bump on a CM4 broke a GPIO-expander overlay and renamed an RS-485 port | Robots depend on device-tree overlays and stable serial names; test them on every kernel update | [C-REF-W19-longevity-011] |
| Broken I2C on Pi 5; balena said it does not monitor GitHub issues and pointed to paid support | Sensor buses (I2C) are robot-critical; a public issue path matters | [C-TD-balenaos-049] |
| AGX Orin with one eMMC model never cold-boots on balenaOS 8.0.9 (missing NVIDIA fix in a boot blob) | Jetson BSP blobs are the riskiest part of any robot OS | [C-TD-balenaos-046] |
| Power cut on first boot after update caused an immediate rollback (fixed with retries) | Field robots lose power; the commit logic must tolerate it | [C-TD-balenaos-047] |
| (2019, SECONDARY) A ROS team on Jetson TX2 needed paid custom-device support and was satisfied | Robot makers will pay for board bring-up | [C-TD-tier-c-robotics-072] |

## 3. What competitors do (OS updates for robots)

| Approach | Who | Rollback | Robot-aware health check | Constraint fit to OneMind |
|---|---|---|---|---|
| Yocto A/B OS + Docker apps | **balena** [C-TD-balenaos-012] | Boot-count fallback [C-TD-balenaos-020] | No: engine + VPN only [C-TD-balenaos-019] | **Candidate**: closest proof of one engine across Pi, Jetson and x86 |
| Yocto + RAUC A/B + rootless Podman per ROS node | A team on ROS Discourse (SECONDARY) [C-TD-tier-c-robotics-073] | A/B | Not stated | **Default pattern** for the robot node: matches OneMind's RAUC choice |
| Mender dual-copy | ADI's shortlist (SECONDARY) [C-TD-tier-c-robotics-073] | A/B | Not stated | Candidate (OneMind's runner-up) |
| In-place apt + agent | Viam, Formant [C-TD-tier-c-robotics-046][C-TD-tier-c-robotics-005] | None | n/a | Low |
| **OneMind target** | Debian 13 / L4T + RAUC + k3s agent | Health-gated A/B | Yes (k3s and core pods; add robot probes) | — |

## 4. Constraint fit

balena matches OneMind on hardware (Pi 5, Jetson, x86), on Apache-2.0 for the device side, and on containers for robot code. It differs on team size (Yocto across 150+ boards [C-TD-balenaos-055]), cloud-first identity, no Kubernetes, nine-month support releases, and no robotics depth. **Fit: Candidate** for the update engine design and hardware contracts; **Low** for robotics features, which do not exist beyond marketing and archived examples.

## 5. What OneMind copies and what it does better

| ID | Recommendation | Evidence | Req IDs |
|---|---|---|---|
| REC-TDC-BAL-01 | Copy "OS A/B + containerised robot code" as the robot node pattern; run each ROS 2 node as its own unprivileged container, as practitioners do with RAUC + Podman. | [C-TD-tier-c-robotics-073][C-TD-balenaos-012] | M-7, N-1, R-1 |
| REC-TDC-BAL-02 | Copy hardware labels/contracts so a robot app declares the buses it needs (I2C, CAN, serial, GPU); do better by checking them against capability detection before install. | [C-TD-balenaos-033][C-TD-balenaos-034] | N-3, F-3, A-6 |
| REC-TDC-BAL-03 | Do better on the health gate for robots: before committing an update, also check the robot's buses and serial device names, overlays and the ROS 2 graph (expected nodes up), not just the engine. | [C-TD-balenaos-019][C-REF-W19-longevity-011] | R-1, R-2, M-7 |
| REC-TDC-BAL-04 | Keep robotics examples alive in CI against the current ROS 2 LTS (Jazzy, then Lyrical); an archived example on an EOL distro is a negative signal to robot makers. | [C-TD-tier-c-robotics-071] | M-7, F-4, W-3 |
| REC-TDC-BAL-05 | Do better on support periods: publish multi-year support per hardware SKU, not nine-month releases behind a paid plan. | [C-TD-balenaos-039] | R-2, R-3, M-8 |
| REC-TDC-BAL-06 | Offer paid board bring-up as a service line (balena proves robot makers pay for it), with a public issue tracker for everyone else. | [C-TD-balenaos-053][C-TD-balenaos-049][C-TD-tier-c-robotics-072] | H-4, R-2 |

## 6. Gaps

- balena's ROS blog posts were not opened, so their content is not cited.
- No named production robotics customer of balena was verified from a primary source.

## Glossary

| Term | Meaning |
|---|---|
| **Yocto** | A toolkit that builds a custom Linux from source for each board. |
| **Supervisor** | balena's on-device agent that runs and updates the app containers. |
| **Device tree overlay** | A small file telling the kernel what hardware is attached (sensors, ports) on boards like the Pi. |
| **I2C / RS-485 / CAN** | Wired buses robots use to talk to sensors, motor drivers and controllers. |
| **BSP / L4T** | Board Support Package: the vendor's kernel, drivers and boot firmware; L4T is NVIDIA's for Jetson. |
| **UEFI capsule** | A firmware update package the board applies at boot. |
| **ESR** | Extended Support Release: a version kept patched for a fixed time. |
| **ROS 2 graph** | The set of running ROS 2 nodes and the topics connecting them. |
| **EOL** | End of life: no more fixes. |
