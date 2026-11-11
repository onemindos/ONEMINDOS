# Glossary {#sec-glossary}

| Term | Meaning |
|---|---|
| **A/B update** | Two copies (slots) of the OS. Updates go into the copy that isn't running; if the new copy fails, the box boots the old one. |
| **Agent principal** | An AI agent with its own identity and permissions, acting as "a named user intersected with a grant", never as the owner. |
| **aiPolicy** | A per-integration flag saying whether its data may go to AI: allowed, consent-required, official-MCP-only, display-only or prohibited. |
| **ATAK / iTAK / CloudTAK** | Team Awareness Kit map apps for Android, iPhone and the browser; TAK Server links them. CoT (Cursor on Target) is their message format. |
| **batman-adv** | A Linux kernel mesh-networking protocol; with WireGuard and NATS leaf links it forms OneMind's native mesh. |
| **Base lock (G6)** | The gate (April 2027) after which one base (Ubuntu, Debian or bootc) is the shipping base; changing it later means reflashing boxes. |
| **bootc / image mode** | Shipping the whole OS as a container image; Red Hat's long-life lineage (Fedora → CentOS Stream → RHEL) uses it. |
| **BSP** | Board support package: the vendor's kernel, drivers and firmware for a board (for example NVIDIA's L4T). |
| **Decision map** | The base-OS result for each outcome of the three pending results (Canonical's reply, the bootc Pi 5 test, Ubuntu's Secure Boot test U-SB), written on 2026-11-11 before any is known. |
| **Decision of record** | What the research assumes until you rule otherwise: for the base, the result the frozen rules give (Ubuntu 26.04 + RAUC, conditional). |
| **Capability gateway** | OneMind's single enforcement point: it turns app capabilities into MCP tools, REST, CLI and Agent Skills, checks permissions, asks for approvals and logs everything. |
| **CRA** | EU Cyber Resilience Act (Regulation (EU) 2024/2847); main obligations from 2027-12-11. |
| **DC-nn** | A decision-critical question: one of 24 questions whose answer could flip ADR-001. |
| **DKMS** | A system that rebuilds a kernel driver (such as NVIDIA's) on the device after each kernel update; OneMind builds and signs drivers in CI instead. |
| **dm-verity / verity bundle** | A kernel feature that checks every block of a read-only filesystem against a hash; RAUC's verity bundles use it. |
| **Driver pack** | A signed system extension carrying kernel modules built for one exact OneMind kernel. |
| **E1–E10** | OneMind's ten plugin extension points (Chapter 9). |
| **FDO** | FIDO Device Onboard: zero-touch onboarding of a new device to its owner's management system. |
| **Flavor / profile** | A flavor is a variant image for a hardware family (Jetson, GPU server); a profile is a configuration of the same image for a use (greenhouse, TAK node, Industrial). |
| **Fresh signal** | Health evidence produced *after this boot*, as opposed to status saved from an earlier boot. |
| **greenboot** | Fedora/RHEL health checks that trigger an automatic rollback. |
| **Health-gated commit** | The new slot becomes the default only after checks pass. |
| **IEC 62443** | The industrial cybersecurity standard family: 4-1 for the development process, 4-2 for components, 3-3 for systems. |
| **JetPack / L4T** | NVIDIA's Jetson software stack; Jetson Linux (L4T) is its Ubuntu-based OS and kernel. |
| **k3s / RKE2 / k0s** | Small Kubernetes distributions; k3s and RKE2 come from SUSE, k0s from Mirantis. |
| **Kernel contract** | The list of kernel features OneMind needs, checked in CI on every kernel bump. |
| **LUKS2** | Linux disk encryption; OneMind encrypts the data partition from first boot. |
| **MCP** | Model Context Protocol: the standard way AI clients call tools; current version 2026-07-28. |
| **meta-tegra / OE4T** | The Yocto layer that builds Jetson images; official in NVIDIA's documentation since JetPack 7.2. |
| **MHS** | Anthropic's Model Hardware Standard, a research preview since 2026-08-27 for AI control of devices. |
| **NATS / JetStream / leaf node** | The message bus; JetStream adds storage; a leaf node is a small NATS server that forwards to a hub and buffers during outages. |
| **NFD / GFD** | Kubernetes Node Feature Discovery and NVIDIA GPU Feature Discovery, which label a machine's hardware. |
| **PCR 7 / 11 / 15** | TPM registers recording Secure Boot state (7), the booted kernel image (11) and the unlocked volume's identity (15). |
| **PREEMPT_RT** | Linux's real-time mode, in mainline since 6.12. |
| **RAUC / Mender / Rugix** | Open-source A/B update engines (Home Assistant OS uses RAUC; umbrelOS uses Rugix; umbrelOS once used Mender). |
| **Rebase** | Moving a fielded box to a new major OS release (Debian 13 → 14) without wiping it. |
| **Refuter / steelman** | An agent told to disprove a conclusion / an agent told to argue for the runner-up. A **blind** refuter sees only the claim, not the research's reasoning. |
| **restic** | An encrypting, de-duplicating backup program that allows several keys per repository. |
| **ROS 2** | Robot Operating System 2, the standard robotics framework; Jazzy and Lyrical are long-term releases. |
| **SBAT** | A generation number inside signed boot files that lets firmware refuse older signed files. |
| **Secure Boot / UKI** | Firmware checks each boot file's signature; a unified kernel image (UKI) packs kernel, initrd and command line into one signed file. |
| **sysext / confext** | systemd system and configuration extensions: signed images laid over a read-only `/usr` or `/etc`. |
| **SQLite / etcd** | The two k3s databases: SQLite for one server, etcd for several. |
| **Tie / tie-break** | When the **top two** candidates on the frozen scorecard are less than 3 points apart, they are tied; the tie goes to the decision-critical evidence between those two, counted row by row, never to changed weights or to a third candidate. |
| **Tryboot** | The Raspberry Pi firmware's one-shot "try this boot partition next" mechanism. |
| **U-SB / LT-VM-20** | Ubuntu's own Secure Boot test: the Debian Secure Boot lab re-run on Ubuntu 26.04 in a virtual machine. A fail moves the base to bootc. Attempted on 2026-11-11 and blocked; LT-VM-20 is the founder-run version. |
| **Z-nn** | A founder decision item in `26-OPEN-QUESTIONS-FOR-ZEUS.md`. |

# Appendix B · How this was researched, and its limits {#sec-method .unnumbered}

**Method** (`RESEARCH-MISSION.md` §2): every factual claim cites a primary source the research actually opened (official docs, release notes, legal text, or source code at a pinned commit), or is labelled SECONDARY or UNVERIFIED. Scorecard weights were frozen before scoring. Every P0 conclusion went to at least three independent refuters with different lenses (technical, longevity, security, cost, robotics), and each runner-up got a written steelman. Thirty products were torn down from code.

**The VM lab** (disposable Lima/QEMU VMs on a Mac; pass/fail criteria written before each run):

| Spike | Result |
|---|---|
| Debian 13 + Rugix (x86 and arm64) | Pass; found the stale-status trap [C-LAB-debian-rugix-023] |
| Debian 13 + RAUC + real k3s gate | Pass twice; naive gate committed a broken kubelet [C-LAB-rauc-k3s-gate-008] |
| RAUC under enforced Secure Boot | Pass twice; downgrade gap found [C-LAB-secureboot-rauc-018] |
| RAUC 1.15.2 under enforced Secure Boot (rev. 4) | Pass; the old-signed-kernel gap persists [C-LAB-secureboot-1152-005, C-LAB-secureboot-1152-009] |
| RAUC 1.15.2 + k3s on native arm64 (rev. 4) | Pass with the unchanged gate [C-LAB-aarch64-gate-004] |
| RAUC 1.15.2 + real k3s gate | Pass [C-LAB-rauc-1152-011] |
| Ubuntu 26.04 leg | Pass with RAUC 1.15.1; RAUC 1.13 fails on Linux 7.0 [C-LAB-ubuntu-2604-leg-010] |
| Ubuntu 26.04 under enforced Secure Boot (U-SB, rev. 4.1) | **Blocked, not run**: rule frozen before the build; Ubuntu's archive does not resolve from the research environment. Founder runs it as LT-VM-20 [C-FIX5-001, C-FIX5-002] |
| Mender 5.2.0 + same gate | Pass, with the one-try limit [C-LAB-mender-013] |
| Fedora bootc + greenboot | Mostly pass; power cut in finalize silently downgraded a healthy box [C-LAB-fedora-bootc-011] |
| Fedora IoT bootc + k3s gate | Automation pass; 32-minute rollback fails the time target [C-W2-054] |
| k3s footprint + restore | Pass; whole-box restore onto a fresh VM [C-LAB-k3s-footprint-restore-011] |
| NATS leaf buffering | 600/600 delivered [C-W8-050] |
| Minimal image, Debian vs Buildroot | 4–6× smaller, 7–18% fewer CVE IDs [C-LAB-minimal-image-dc20-011] |
| Mac kernel build | arm64 kernel in 5.5 minutes [C-W18-066] |
| systemd sysext/confext | Functional pass; signing and slot switches not yet tested [C-W19-006] |

**What the lab cannot show:** real power loss, real PC firmware, Pi 5, Jetson, GPU drivers or real-time latency on metal. These are the founder tests in `22-HARDWARE-LAB-TEST-PLAN.md` and the gates in Chapter 11.

**Honest limits of this report.** It summarises; the reasoning and the full evidence are in the numbered research files. Confidence is **low** on the base OS (a fragile result, conditional on Canonical) and **low-medium** on the update engine (a tie-break win), **high** on the health gate and backups. Vendor prices (Ubuntu Pro for Devices, Freexian ELTS for arm64, Red Hat) are unpublished, so cost figures depend on stated assumptions. KubeCon NA 2026 was checked mid-event (re-check by 2026-12-10). Humanoid and post-Thor NVIDIA forecasts are proposals, not sourced. Legal readings (CRA, licences, trademarks, AB 1043) are for counsel. The research could not contact vendors, use the live cluster or touch hardware. The completeness critic's later passes and any remaining ledger gaps are tracked in `evidence/critic/`.
