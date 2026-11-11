# W18 — Refuter report: P0-1 (kernel family), technical lens

- **Claim under test (P0-1):** Linux is the only kernel family that passes OneMind's gates. The Kubernetes control plane runs only on Linux (workers Linux or Windows); CUDA 13.5 covers only Linux distributions (incl. Debian 13 and Jetson); NVIDIA's FreeBSD driver is x64-only with no arm64; ROS 2 REP 2000 (Kilted) lists Tier 1 Ubuntu/Windows, macOS Tier 3 amd64-only, and no BSD.
- **Refuter lens:** technical. Given the claim and its sources only (protocol: RESEARCH-MISSION.md §2 rule 7).
- **Date:** 2026-11-10
- **Requirement IDs touched:** F-15, F-7, F-2, RS-4, plus the tier profiles in DECISIONS.md (Pi 5, x86, Jetson).

## Verdict: **weakened**

The **conclusion stands**: no non-Linux kernel family passes all of OneMind's gates (a K8s/k3s control plane, plus CUDA, plus Jetson, plus Pi 5, plus ROS 2 Tier 1 on arm64). **But two of the four supporting facts are wrong or stale, and the gate set leaves out a kernel-maintenance gate that Linux itself only partly passes on the Jetson tier.** The decision text has to be corrected before it goes into the final report (F-10).

## Checks of the cited sources (opened 2026-11-10)

| Sub-claim | Source opened | Result |
|---|---|---|
| The K8s control plane is Linux-only; workers are Linux or Windows | kubernetes.io/docs/concepts/windows/intro/ — "While you can only run the control plane on Linux, you can deploy worker nodes running either Windows or Linux"; Windows nodes need "Windows Server 2022 or Windows Server 2025" | **Confirmed.** Note: Windows workers are Server SKUs only. |
| "CUDA 13.5 covers only Linux distributions" | The cited source is the **Linux** install guide, which cannot show "only Linux". The Windows guide, https://docs.nvidia.com/cuda/cuda-installation-guide-microsoft-windows/index.html (header "Windows 13.5 documentation"), lists Windows 11 25H2/24H2/23H2/22H2-SV2, Windows 10 22H2, Windows Server 2022 and 2025 | **Wrong as worded.** CUDA 13.5 supports Windows. The correct statement is "CUDA 13.5 supports Linux and Windows. Of those two, only Linux can host the K8s control plane and run on Jetson." |
| NVIDIA's FreeBSD driver is x64-only | nvidia.com/en-us/drivers/unix/ lists "FreeBSD x64" and "FreeBSD x86". There is no FreeBSD aarch64, while "Linux aarch64" is listed | **Confirmed.** |
| REP 2000 (Kilted): Tier 1 Ubuntu/Windows, macOS Tier 3 amd64, no BSD | REP 2000 @11ca24a, Kilted section: Ubuntu 24.04 amd64/arm64 Tier 1, Windows 10 amd64 Tier 1, RHEL 9 Tier 2, macOS amd64 Tier 3, Debian 12 and OpenEmbedded Tier 3, no BSD | **Confirmed but stale.** Kilted's window runs "May 2025 – November 2026", so it ends this month. REP 2000 no longer governs releases after Kilted (see N1). |
| TrueNAS CORE (FreeBSD) in decline | truenas.com blog (2024-03-20): CORE is "entering a sustaining engineering phase", new work goes to SCALE (Linux), and "Linux supports a wider range of hardware" | **Confirmed (supports the claim).** The source says CORE is "not deprecated". Do not describe it as abandoned. |

## New sources (found by searching for failure, abandonment, regressions, CVEs and lifecycle cuts)

- **N1 — ROS 2 Lyrical Luth supported platforms (lifecycle cut of the cited source):** https://raw.githubusercontent.com/ros2/ros2_documentation/rolling/source/Releases/lyrical/supported-platforms.rst (opened). The current LTS (support "until May 2031", per `Releases/Release-Lyrical-Luth.rst` in the same repo) lists Ubuntu 26.04 amd64/arm64 Tier 1, **Windows 11 (VS2022) amd64 only** Tier 1, RHEL 10 Tier 2, and macOS amd64, Debian Trixie, Ubuntu 24.04 and OpenEmbedded Tier 3. No BSD and no arm64 for Windows or macOS. Debian 13 is Tier 3, which means building from source. The rendered docs.ros.org page is `UNVERIFIED (blocked)` by an Anubis bot wall, so this row cites the GitHub source on the `rolling` branch instead. Pin it to a commit SHA before archiving (rule 1).
- **N2 — kernel.org longterm releases:** https://www.kernel.org/category/releases.html (opened). The longterm kernels are 6.18 and 6.12 (EOL Dec 2028), 6.6 and 6.1 (Dec 2027), and 5.15 and 5.10 (**Dec 2026**). **6.8 is not a longterm kernel.**
- **N3 — Jetson Thor developer guide (r39.2.1):** https://docs.nvidia.com/jetson/archives/r39.2.1/DeveloperGuide/SO/JetsonThorSeries.html (opened). Kernel "Version 6.8.12". With N2, this means the Jetson BSP kernel gets no upstream stable/LTS fixes. The JetPack 6 / L4T 36.x line runs 5.15, which reaches upstream EOL in Dec 2026. That 5.15 line is reported only by SECONDARY sources (search results: RidgeRun JetPack 7.2 component table, techveda.live). It was not opened and is `UNVERIFIED`.
- **N4 — Linux kernel CVE volume (SECONDARY):** Greg Kroah-Hartman's Dec 2025 post (kroah.com, "Linux CVEs, more than you ever wanted to know") reports the kernel CNA moving from #3 (2024) to #1 (2025) among CVE issuers. Its policy is to assign a CVE to every qualifying stable fix. linuxcvetracker.com reports about 5,681 kernel CVEs in 2025. The kroah.com page **could not be opened** (connection refused) and is `UNVERIFIED`. The figures come from search snippets only and must be re-opened before use.
- **N5 — FreeBSD on Raspberry Pi 5 (SECONDARY, supports the claim):** freebsd-arm mailing list, Apr 2025 (https://lists.freebsd.org/archives/freebsd-arm/2025-April/004711.html) and FreeBSD forum thread 91406. Pi support is volunteer-only, and the RP1 southbridge (wired Ethernet, fan) is unsupported. Taken from search results and not opened, so `UNVERIFIED` until opened.

## Strongest counter-argument

1. **The evidence chain is partly false, and a false premise in a P0 decision is a defect in its own right.** "CUDA 13.5 covers only Linux" is contradicted by NVIDIA's own CUDA 13.5 Windows guide. Windows actually fails on other grounds: no control plane (kubernetes.io), Server-only worker SKUs, no Jetson or Pi 5 image, no ROS 2 arm64. k3s's requirements page (https://docs.k3s.io/installation/requirements, opened) says only "expected to work on most modern Linux systems", with archs x86_64/armhf/arm64. The conclusion survives, but on different evidence than the claim cites.
2. **The ROS 2 evidence is about to expire.** Kilted support ends in November 2026, and REP 2000 does not cover Lyrical (2026–2031). The current LTS is the right citation. It makes the Linux case stronger (only Ubuntu 26.04 has arm64 Tier 1), but it also makes **Debian 13 Tier 3**. That matters for the base-distro decision (RS-4) more than for the kernel family.
3. **"Passes the gates" hides a gate that Linux only partly passes: security maintenance of the kernel you actually ship.** On Jetson (the Robotics tier and F-2), OneMind does not get "Linux". It gets NVIDIA's BSP kernel 6.8.12, which kernel.org does not maintain as LTS. The alternative line (5.15) reaches upstream EOL in Dec 2026. Since 2024 the kernel CNA has issued CVEs at a very high rate (N4, UNVERIFIED), so a non-LTS vendor kernel builds up a backlog of unpatched CVEs that a solo founder cannot triage. The Pi 5 adds a second downstream kernel (raspberrypi/linux). "Linux" is therefore really two or three vendor-kernel forks, each with its own lifecycle. That is a real cost, though not a reason to choose another family, since the BSDs and Darwin have no Jetson support at all.
4. **"Only kernel family" is too broad for a robotics/drones/IIoT product.** Flight controllers and MCU-class IIoT nodes run RTOSes (NuttX for PX4, Zephyr, FreeRTOS), and micro-ROS targets them. The defensible claim is "Linux is the only kernel family for the **host OS** on every OneMind tier". The product as a whole will also ship or integrate non-Linux kernels on co-processors. F-15 asks for an explanation per domain (IoT included), and the claim as worded does not give one. (This point is analytical and has no new source. It should be verified by the robotics-lens refuter.)

Points 1, 2 and 4 are wording and evidence fixes. Point 3 is a real gap: it should become a stated gate, "a kernel with a maintained security lifecycle on every tier", plus a named mitigation (follow NVIDIA's L4T security updates, or the Bring-Your-Own-Kernel path to an LTS kernel, with its "combinations are not tested" caveat; forum source, SECONDARY).

## Required corrections to the decision text

- Replace the CUDA sentence with: "CUDA 13.5 supports Linux (incl. Jetson via JetPack) and Windows. Only Linux also hosts the K8s/k3s control plane and runs on Jetson and Pi 5."
- Cite ROS 2 **Lyrical** supported platforms (pinned SHA) next to, or instead of, REP 2000 Kilted.
- Add the kernel-lifecycle gate and record its Jetson result: "passes with a vendor-BSP caveat (6.8 is not LTS)".
- Scope the claim to the host OS, and name the RTOS families used on MCUs and flight controllers as out of scope (or as a separate decision).

## What evidence would flip the decision

Any one of these would move the verdict from "Linux only" to "Linux plus an alternative":

1. NVIDIA shipping a **FreeBSD aarch64** driver with CUDA, or a **Jetson BSP for a non-Linux kernel** (e.g. QNX for Jetson Thor with CUDA, made generally available outside DRIVE OS), **together with** a Kubernetes-conformant control plane on that kernel.
2. Kubernetes (or k3s) officially supporting a **non-Linux control plane** (Windows Server or FreeBSD) in a GA release.
3. A ROS 2 LTS listing a BSD, or macOS arm64, at **Tier 1 or Tier 2**.
4. A non-Linux kernel with upstream-supported **Raspberry Pi 5 (RP1) networking** and a CUDA path on its GPU tiers.

None of these has been seen as of 2026-11-10. The family decision is upheld; its evidence is weakened.

Evidence that would turn this into **refuted for the Jetson tier specifically** (not the family): NVIDIA announcing that Jetson Linux will stay on non-LTS kernels without a security backport commitment, or EOL of JetPack 6 / 5.15 with no LTS-based successor for Orin. In that case the Robotics tier would need its own kernel-maintenance plan before it can count as "passing".

## Archiving to-do (rule 1)

Save text plus a hash in `research-output/evidence/sources/` for: kubernetes.io Windows intro, CUDA 13.5 Windows guide, ROS 2 Lyrical supported-platforms.rst (at a pinned SHA), kernel.org releases, and the Jetson Thor r39.2.1 guide. Re-open the kroah.com post and the freebsd-arm list message before citing them as anything other than UNVERIFIED.
