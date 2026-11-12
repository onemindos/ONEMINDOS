# Refuter report: W4 P0-2 (k3s default, RKE2 for GPU/AI and regulated tiers), technical lens

- **Refuter lens:** technical (resource floor, board support, conformance, distro maintenance load for a solo founder; requirements P-9, N-9, F-2, D-001 one-pipeline-many-profiles)
- **Date:** 2026-11-10 · **Re-check by:** 2027-05-10 (Kubernetes facts, 6 months; also re-check k3s incubation at cncf/toc#1957 and sbc-jetson#23)
- **Verdict:** **weakened.** k3s as the *default* is still defensible. The claim's decisive sentence is false: "k3s is the only candidate that passes every gate for the 4 GB Pi tier." **k0s** passes the same gates the claim tests on smaller resources. It is CNCF-conformant and CNCF **AI**-conformant, and k3s is not AI-conformant. **Talos** now has a first-party Raspberry Pi 5 overlay. The RKE2 figure does not exclude a 4 GB board either. The decision needs a different stated reason and a written answer to the "one distro instead of two" option.

## Claim under test

> k3s should be the default Kubernetes distribution, with RKE2 for the GPU/AI-conformant and regulated tiers. RKE2 needs 4 GB minimum (8 GB recommended), and Talos has Jetson Orin support only in an unmerged PR, so k3s is the only candidate that passes every gate for the 4 GB Pi tier.

## What the cited sources confirm (re-opened 2026-11-10)

| Item | Source | Status |
|---|---|---|
| RKE2 4 GB minimum, 8 GB recommended | docs.rke2.io/install/requirements (sha256 prefix `4464b5afa42111df`) | **Confirmed but misread.** The page says "4 GB minimum, at least 8 GB recommended", 2 cores minimum. A 4 GB node *meets* the stated minimum. On a Pi 5 4 GB the usable RAM is below 4 GiB once firmware and CMA reservations are taken, so it misses in practice. But "RKE2 fails the 4 GB gate" is an inference, not what the doc says. The page does not mention the Raspberry Pi. |
| Talos Jetson Orin only in an unmerged PR | siderolabs/sbc-jetson#23 | **Confirmed.** Open, "On Hold", opened 2026-02-02. A maintainer said "let's work on getting this merged" (2026-04-22). The GPU is the blocker: NVIDIA's out-of-tree modules, and the GPU Operator does not support Jetson. **Not relevant to the 4 GB Pi tier**, which has no Jetson. The claim uses a Jetson fact to rule Talos out of a Pi gate. |
| AI conformance at `c64e5bc8` | cncf/k8s-ai-conformance tree | **Contradicts the claim's "only candidate" framing.** Entries exist for **rke2** (v1.33–v1.37), **talos** (v1.33, v1.34, v1.37) and **k0s** (v1.35, v1.36: `v1.36/k0s/PRODUCT.yaml`, platformVersion `v1.36.4+k0s.1`, vendor "The k0s Project", sha256 prefix `9df464fd4268f0a6`). **No k3s entry, and no k3s PR in that repo** (`gh pr list --search k3s`: empty). |
| Base conformance at `4772d34f` | cncf/k8s-conformance tree | **Confirmed for all.** k3s, k0s, talos, microk8s are listed for v1.33–v1.36. k3s, k0s, rke2, talos are listed for v1.37. Conformance does not tell these distros apart. |

## Strongest counter-argument

1. **k0s passes every gate the claim names for the 4 GB Pi tier, plus the AI gate that k3s fails.**
   - k0s minimums are **1 GB RAM / 1 vCPU for controller+worker** and 0.5 GB for a worker. It runs on x86_64, aarch64, armv7l and riscv64 (docs.k0sproject.io/stable/system-requirements, sha256 prefix `714953437776887a`). k3s's stated floor is **2 GB** for a server (docs.k3s.io/installation/requirements).
   - k0s has an official Raspberry Pi 5 guide (docs.k0sproject.io/stable/raspberry-pi5). It needs the same `cgroup_enable=memory` step as k3s.
   - k0s is CNCF-conformant (v1.33–v1.37) and **CNCF AI-conformant (v1.35, v1.36)**. Its v1.36 submission documents the GPU Operator driver lifecycle and time-slicing GPU sharing on k0s.
   - k0s was accepted into the CNCF Sandbox (cncf/sandbox#125, closed 2025-01-21; onboarding #333, closed 2025-07-30). That is the same maturity level as k3s.

   So the claim's own gates (fits 4 GB, conformant, arm64, Pi 5) have at least two passing candidates. A distro that is also AI-conformant could serve **both** the Pi tier and the GPU tier with one binary. That is a direct counter to the claim's two-distro design under D-001 ("one image pipeline, many profiles") for a solo founder.

2. **Talos is no longer excluded from the Pi 5 tier.**
   - siderolabs/sbc-raspberrypi (the first-party repo, `@9fa9252c`, README sha256 prefix `4eb8c458ad21f44d`) now says it "provides the overlay for building Raspberry Pi generic (models before Pi 5), **Raspberry Pi 5**, and RevolutionPi Talos images". Commit `f35948c0d7fc` "feat: add Raspberry Pi 5" landed 2026-01-24 and was released in v0.2.0 (2026-02-25). The latest release is v0.3.0 (2026-11-02).
   - Talos minimums are 2 GiB for a control plane and 1 GiB for a worker (Talos v1.13 system requirements).
   - Caveat that favours the claim: the v1.13 `rpi_generic` docs page still says it was "only been officialy tested on the Raspberry Pi 4". The Pi 5 is shipped in the overlay but not yet documented as tested.

   Talos's real gap is Jetson, which is a reason to keep it off the *Robotics* tier, not the Pi tier.

3. **The "RKE2 for AI-conformant" leg is not unique either, and it doubles the surface.** RKE2, Talos and k0s all hold AI conformance. Running k3s on small tiers and RKE2 on large ones means two install paths, two upgrade channels, two CIS/hardening profiles and two sets of CVE feeds for one founder. The mitigation (RKE2 and k3s share SUSE's code base and supervisor) is real but is not argued in the claim. The claim also does not show why a GPU tier needs an *AI-conformance badge* at all: the k0s submission shows the badge rests on the same GPU Operator and device-plugin stack any conformant distro can run.

4. **k3s on a 4 GB Pi leaves less headroom than the claim implies.** On a Pi 4B, k3s measured **1,588 MB (SQLite) / 1,613 MB (embedded etcd)** for a server with a workload (P95, docs.k3s.io/reference/resource-profiling). That workload includes Prometheus/Grafana, but the figures exclude logging, image management and system agents. The same docs warn that "etcd is write intensive; SD cards and eMMC cannot handle the IO load". So on the 4 GB tier, k3s is "single node, SQLite, SSD" and not HA-capable. That is still a pass, but with conditions the claim should state.

## New failure, abandonment and lifecycle evidence (searched for, opened)

1. **k3s is single-vendor with a bus factor of 1–2 (SECONDARY).** The third-party CNCF health report (castrojo.github.io/jorgepilot/reports/cncf/k3s-health-report, dated 2025-10-13, updated 2025-12-10, sha256 prefix `61161668a4e52338`) says "All 18 official maintainers (per MAINTAINERS file) are SUSE employees". It estimates "Bus Factor: 1-2", with one maintainer at about 50% of sampled commits, and rates single-vendor control "critical". Its method caveat: this is a 100-commit sample. For a 10-year horizon this is the most important k3s risk, and the claim does not mention it. Mitigation: k3s is Apache-2.0 and forkable. Counter-weight: k0s is also single-vendor (Mirantis).
2. **k3s is stalled at Sandbox. Its incubation bid is waiting on adopters.**
   - The first incubation proposal, cncf/toc PR #1307, was **closed unmerged** on 2025-01-28.
   - The re-application, cncf/toc#1957 (opened 2025-11-10), is still **open** with label `dd-status/waiting`.
   - TOC triage comment, 2026-07-03: "The project needs to submit 5-7 adopters for interviews… No responses from K3s adopters have been received yet." The comments repeat that request on 2026-07-13 and 2026-08-24.
   - Six years after k3s entered the Sandbox (2020), CNCF due diligence has not been completed. This weakens "k3s is the standard" as a governance argument, although it says nothing against k3s's code quality.
3. **Recent k3s CVEs are in features OneMind relies on.** GHSA-jxr7-mqhw-9p98 (Moderate, published 2026-06-03; CVE-2026-54250 per the GitLab advisory DB) is a path traversal in **etcd snapshot decompression**, fixed in 1.33.10, 1.34.6 and 1.35.3. CVE-2025-46599 exposed the kubelet read-only port 10255 in k3s 1.32 before 1.32.4. Both are fixed. They show that the k3s-specific add-ons (snapshot restore, opinionated kubelet defaults) carry their own CVE stream beyond upstream Kubernetes. A backup/restore design (W5) that uses k3s snapshots inherits that stream.
4. **Pi 5 16K-page kernel: checked and a non-issue.** The concern was that k3s's bundled userspace crashes on the Pi 5's default 16K-page kernel. k3s-io/k3s#7335 (2023) shows the buildroot userspace now builds with 64K page support, and a maintainer said k3s "works fine regardless of page size". This is recorded so that it is not re-raised against k3s. Third-party images (for example jemalloc-based ones) can still abort on 16K kernels, which is a Market-app concern, not a distro one.

## What would flip the decision

**Toward k0s (or a single distro for all tiers):**
- A founder-hardware bake-off (`22-HARDWARE-LAB-TEST-PLAN.md`) on a Pi 5 4 GB and a Jetson Orin Nano Super, with the same Market apps, NATS leaf and Argo agent. If k0s shows equal or lower steady-state RSS, the same upgrade and rollback behaviour, and working NVIDIA container toolkit / CDI on Jetson, then one k0s distro across Edge to Cluster beats k3s+RKE2 on maintenance load.
- Evidence that RKE2-only features (FIPS 140-3 build, DISA STIG) are not needed for the regulated tier before 2028, or are also available from another distro. That removes RKE2's unique role and with it the two-distro argument.

**Toward Talos on Pi and x86 tiers:**
- sbc-jetson#23 merges with a documented GPU path (CDI or the CSV approach) on Orin.
- The Talos docs list the Pi 5 as officially tested.

**Back to "upheld":**
- k3s passes CNCF due diligence (toc#1957 moves to incubating), or SUSE publishes a k3s AI-conformance entry.
- The author shows a gate that k0s fails and k3s passes. Candidates to test: the Olares/k3s ecosystem fit (constraint-matched competitor per rule 2), Rancher/Fleet multi-cluster tooling, NVIDIA's or Jetson's documented k3s support, size of the community and a usable answer on a 4 GB Pi.
- Measured RSS on a Pi 5 4 GB showing k3s at or below k0s.

## Required changes to the claim (for the author's written response)

1. Delete "k3s is the only candidate that passes every gate for the 4 GB Pi tier". Replace it with the actual tie-breaker (ecosystem, Olares precedent, SUSE k3s/RKE2 code sharing) and name **k0s as the runner-up**.
2. Say that RKE2 *meets* its stated 4 GB minimum and is ruled out by measured usable RAM, not by the minimum.
3. Do not use the Jetson PR to rule Talos out of the Pi tier. The Pi 5 overlay is first-party since v0.2.0 (2026-02-25).
4. Say that k3s has **no AI-conformance entry**, and justify why the GPU tier needs RKE2 rather than the k3s default plus GPU Operator, or rather than k0s.
5. Add the governance risk (single vendor, bus factor 1–2, incubation stalled) to the ledger, with re-check-by 2027-05-10.

## Sources opened for this report

- Cited: https://docs.rke2.io/install/requirements ; https://github.com/siderolabs/sbc-jetson/pull/23 ; https://github.com/cncf/k8s-ai-conformance/tree/c64e5bc8085da207715df96e458f2c6585c9f53e ; https://github.com/cncf/k8s-conformance/tree/4772d34f020b9408bfa9957b9c244dcb0e8d5d24
- New (PRIMARY unless marked):
  - https://raw.githubusercontent.com/cncf/k8s-ai-conformance/c64e5bc8085da207715df96e458f2c6585c9f53e/v1.36/k0s/PRODUCT.yaml
  - https://docs.k0sproject.io/stable/system-requirements/
  - https://docs.k0sproject.io/stable/raspberry-pi5/
  - https://github.com/cncf/sandbox/issues/125 ; https://github.com/cncf/sandbox/issues/333
  - https://github.com/siderolabs/sbc-raspberrypi/blob/9fa9252cca1a832a6154e3f431927302bb09d9bb/README.md (commit `f35948c0d7fc`, release v0.2.0)
  - https://docs.siderolabs.com/talos/v1.13/getting-started/system-requirements
  - https://docs.siderolabs.com/talos/v1.13/platform-specific-installations/single-board-computers/rpi_generic
  - https://docs.k3s.io/installation/requirements
  - https://docs.k3s.io/reference/resource-profiling
  - https://github.com/cncf/toc/pull/1307 (closed unmerged 2025-01-28)
  - https://github.com/cncf/toc/issues/1957 (open, `dd-status/waiting`)
  - https://github.com/k3s-io/k3s/security/advisories (GHSA-jxr7-mqhw-9p98)
  - https://advisories.gitlab.com/golang/github.com/k3s-io/k3s/CVE-2026-54250/ (SECONDARY database, CVE id mapping)
  - https://feedly.com/cve/CVE-2025-46599 (SECONDARY)
  - https://github.com/k3s-io/k3s/issues/7335
  - https://castrojo.github.io/jorgepilot/reports/cncf/k3s-health-report (SECONDARY, third-party analysis)
  - https://canonical.com/microk8s/docs/getting-started (MicroK8s recommends 4 GB, so it does not challenge the claim)
- Archive status: the sha256 prefixes above are from copies saved in the session scratchpad only. They have **not** been archived to `research-output/evidence/sources/` (this refuter may write only this file). The author should archive the k0s PRODUCT.yaml, the sbc-raspberrypi README, toc#1957 and the k3s health report.
