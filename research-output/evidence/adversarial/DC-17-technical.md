# DC-17 — Refuter report: one OS from Pi to enterprise (F-14, G5), technical lens

- **Conclusion under test (03 §10; 01 §3.1.1 gate table):** With Debian 13 as the core (Rugix A/B) and Jetson on L4T Ubuntu 24.04, G5 is **CONDITIONAL, not FAIL**: Jetson is a second OS family, but every tier runs the same k3s apps and management plane. The small end is measured: k3s idle ≈ 1.1 GiB used on a 4 GiB node, leaving about 2.7 GiB (4 GB) or 6.7 GiB (8 GB). One box grows into a cluster by a k3s join (`--cluster-init`). Ubuntu 26.04 as the core is scored **PASS** ("one family").
- **Flip condition:** G5 FAILs for the proposal and PASSes for an alternative.
- **Lens:** technical. I read only the conclusion and its cited claims (C-W2-026, 027, 040, 041, 053, 057; C-W4-006; C-W7-007 via the gate row).
- **Date:** 2026-11-10

## Verdict: **weakened** (CONDITIONAL is fair for Debian, but the PASS for Ubuntu is overstated, and the small end is not measured on the shipping stack)

The formal flip does not happen: I found nothing that turns G5 into FAIL for Debian. But the evidence behind the condition is thinner than the text implies, in three places:

1. **The small-end number is not from the proposed OS or the target board.** C-W2-053 is a single 5-minute idle run on a **QEMU aarch64 VM running Fedora IoT bootc** with k3s v1.37.2. It is not Debian 13, not a Pi 5, and not on NVMe. k3s's own docs say SD/eMMC cannot carry etcd, and they flag a "known iptables bug" on Debian-based Raspberry Pi OS (N3). So "fits on 4 GB" is still unmeasured for the shipping stack.
2. **"Same k3s apps and management plane" on Jetson needs different plumbing.** The GPU Operator does not support Jetson (C-W2-027). The working Kubernetes path is CDI in CSV mode plus a hand-applied node label, because GPU discovery does not see Jetson (N1). Separately, k3s's network-policy controller has panicked on a Tegra kernel missing nf_tables modules (N2). The Jetson tier is a second family at the kernel, runtime and GPU plumbing level, not only at the userland level.
3. **Ubuntu's PASS has the same Jetson split.** JetPack 7 is Ubuntu 24.04 on a Tegra kernel, while the proposed Ubuntu core is 26.04. "One family" is true only at the brand level. The real gap between candidates A and D on G5 is smaller than COND vs PASS suggests. That **helps** the Debian proposal: under the flip condition, no candidate cleanly PASSes with Jetson included.

## Checks of the cited sources

| Sub-claim | Claim | Result |
|---|---|---|
| k3s idle ≈ 1.1 GiB on 4 GiB | C-W2-053 | Accurate as stated, but the setup is QEMU + Fedora bootc, one run, idle only. The k3s cgroup MemoryCurrent was 1.69 GiB including page cache. Not transferable to Debian on a Pi 5 without a re-run. |
| GPU Operator k3s column lists Ubuntu only | C-W2-026 | Holds. Debian x86 GPU servers run k3s outside NVIDIA's validated matrix. |
| GPU Operator does not support Jetson | C-W2-027 | Holds. This applies to Ubuntu too, so it does not separate A from D. |
| balena: one OS across Pi 5, Orin, Thor, amd64 | C-W2-040 | Holds (device-type API). balena gets there with **one Yocto kernel/BSP pipeline per board**, not one distro. |
| RHDE on Orin | C-W2-041 | Holds, without Pi 5. |
| Pi 5 certified for Ubuntu 26.04 | C-W2-057 | Medium confidence (column mapping inferred), as the ledger itself says. |
| Single node → HA by `--cluster-init` | C-W4-006 | Documented. The SQLite→etcd move has had regressions in the past, and etcd on SD/eMMC is unsupported (N3), so "join" assumes NVMe on every server node. |

## Strongest counter-argument

F-14 promises **one OS**. What the proposal delivers is one app platform (k3s + Helm/Argo) on top of three kernel lines (Debian generic, Raspberry Pi vendor, NVIDIA Tegra), two userlands (Debian 13, Ubuntu 24.04), and two GPU integration models (dGPU via the driver repo, iGPU via CDI/CSV). Each Jetson integration issue below has to be solved by OneMind, not by a vendor matrix. A solo developer (M-6) carries all three trains. If "one OS" means one thing to patch, test and certify, G5 is closer to FAIL than to COND. balena shows the honest version: one OS **build system** across boards, rather than one distro.

## New sources (searched for failures and regressions)

- **N1. NVIDIA Developer Forums, "JetPack 6.3 containerd and kubernetes"** — https://forums.developer.nvidia.com/t/jetpack-6-3-containerd-and-kubernetes/296483 (opened). Thread from 2024-06-14 to 2024-08-08. On AGX Orin with containerd, GPU containers fail with `NvRmMemInitNvmap failed with Permission denied` and an nvml error. NVIDIA said `nvidia-container-cli` is no longer supported on iGPU Jetsons. The working path was `nvidia-ctk cdi generate --mode=csv`, runtime `mode=cdi`, device plugin 0.16.1, and a **manual** `nvidia.com/gpu.present=true` label. [C-REF-DC-technical-005]
- **N2. NVIDIA/NemoClaw issue #404** — https://github.com/NVIDIA/NemoClaw/issues/404 (opened). Opened 2026-03-19 and closed 2026-04-13 with no code fix ("on the roadmap"). On an Orin Nano Super (JetPack 6.x, 5.15.148-tegra), k3s's network policy controller panics after `iptables v1.8.10 (nf_tables): RULE_INSERT failed`. The reporter attributes it to missing nft modules in the Tegra kernel. GPU detection fails because `nvidia-smi` reports memory as `[N/A]`. NVIDIA's own k3s-based product did not support its own Jetson. [C-REF-DC-technical-006]
- **N3. k3s requirements** — https://docs.k3s.io/installation/requirements (opened). "etcd is write intensive; SD cards and eMMC cannot handle the IO load." Server minimum is 2 cores / 2 GB. Raspberry Pi OS "may suffer from a known iptables bug" and needs cgroup memory flags. [C-REF-DC-technical-007]

## What would flip the decision

- **To FAIL for Debian (the formal flip needs an alternative to PASS as well):** Debian 13 + k3s on a **real Pi 5 4 GB on NVMe**, with OneMind's minimum stack (gateway, IdP, NATS leaf, one small model), leaves under about 500 MiB free or OOM-kills within 24 h, while the same stack fits on another base. Or k3s on L4T 24.04 cannot run the same Helm charts as the Debian tiers without per-chart forks (network policy, GPU resource names).
- **To PASS for Debian:** the same Helm/Argo app set deploys unchanged on Pi 5 (Debian), x86 (Debian, NVIDIA repo) and Orin (L4T), joined into one cluster, with GPU scheduling working on both x86 and Orin through a single documented device-plugin configuration.
- **Re-score Ubuntu:** move candidate D's G5 to COND unless JetPack ships on 26.04, because the Jetson split is the same.
