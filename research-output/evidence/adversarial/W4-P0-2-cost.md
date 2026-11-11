# W4 adversarial check: P0-2 (k3s default, RKE2 for GPU/AI and regulated tiers), cost and solo-developer lens

- **Claim under test:** P0-2. k3s should be the default Kubernetes distribution, with RKE2 for the GPU/AI-conformant and regulated tiers. RKE2 needs 4 GB minimum (8 GB recommended), and Talos supports Jetson Orin only in an unmerged PR, so k3s is the only candidate that passes every gate for the 4 GB Pi tier.
- **Refuter lens:** cost, and how much one founder can operate alone over 10 years.
- **Date:** 2026-11-10.
- **Protocol:** RESEARCH-MISSION.md §2 rule 7. The refuter saw only the claim and its four cited sources.
- **Verdict:** **weakened.** k3s on the 4 GB Pi tier is defensible. Two parts of the claim do not hold:
  - "k3s is the only candidate" is false.
  - The two-distribution split (k3s plus RKE2) is the costliest option for a solo founder, and the evidence offered does not justify it.
- **Response:** under rule 7 the author must respond in writing.

## 1. What the cited sources actually say (re-read 2026-11-10)

| Cited source | What it says | Effect on the claim |
|---|---|---|
| [C1] docs.rke2.io/install/requirements | "RAM: 4GB Minimum (we recommend at least 8GB)", "CPU: 2 Minimum". arm64 is supported. Raspberry Pi is not mentioned. | Accurate. On a 4 GB Pi, RKE2 meets the floor but leaves almost no room for apps. |
| [C2] siderolabs/sbc-jetson PR #23 | Open, one commit, opened 2026-02-02. On 2026-02-18 it was put "On Hold". On 2026-04-22 maintainer frezbo wrote "let's work on getting this merged". Its U-Boot blobs come from L4T r36.4.4. Jetson GPU support is a separate gap: out-of-tree nvgpu, tracked in siderolabs/pkgs#1518. | Accurate as of today, but the PR is moving again, so this could change. |
| [C3] cncf/k8s-ai-conformance@c64e5bc | `rke2` appears for every version from v1.33 to v1.37. `talos` appears for v1.33, v1.34 and v1.37. **`k0s` appears for v1.35 and v1.36.** **`k3s` appears in no version.** | Supports RKE2 for the AI tier. It also shows that **k0s and Talos pass the same gate**, which undercuts "only candidate". |
| [C4] cncf/k8s-conformance@4772d34 | For v1.34 and v1.35: `k0s`, `k3s`, `microk8s` and `talos` are all certified. | Every light distribution is conformant, so this gate does not single out k3s. |

The tables come from `gh api repos/cncf/k8s-ai-conformance/contents/<ver>?ref=c64e5bc8…` and `…/k8s-conformance/contents/<ver>?ref=4772d34f…`, run on 2026-11-10.

## 2. Strongest counter-argument

### A. "Only candidate" is false: k0s passes the Pi gate and the AI-conformance gate that k3s fails

- **k0s system requirements [N1]:**
  - controller+worker: 1 GB RAM, 1 vCPU
  - worker: 0.5 GB
  - architectures: x86_64, aarch64 and armv7l
  - k3s, for comparison, needs a 2 GB / 2-core server minimum [N2]
- **Pi 5 guide for k0s [N3]:** written for v1.37.2+k0s.1 on Raspberry Pi OS. It needs the same memory-cgroup kernel argument as k3s.
- **AI conformance:** k0s's v1.36 entry [C3, `v1.36/k0s/PRODUCT.yaml`] is `platformVersion: v1.36.4+k0s.1`. It names the NVIDIA GPU Operator v26.7.0 and time-slicing GPU sharing as implemented.
- **What this means:** one distribution can cover all three:
  - the 4 GB Pi tier
  - x86 and Jetson boxes (k0s, like k3s, is a single binary on a host distribution)
  - a CNCF-certified AI-conformance tier

  k3s cannot claim the AI-conformance part today [C3].

### B. For a solo founder, two distributions cost more than one

k3s and RKE2 come from the same vendor and share config conventions. They are still two of everything:
- two release trains to track
- two CIS and hardening profiles
- two sets of bundled components and CVE feeds
- two upgrade paths to test on every board
- two sets of support questions

The one-pipeline, many-profiles principle in DECISIONS.md argues against splitting the Kubernetes layer by tier unless a gate forces it.

The cited evidence forces the split only if the GPU/AI tier must be **CNCF AI-conformant**. On that gate, RKE2 is one of three passing options (RKE2, k0s, Talos), not the only one.

The "regulated" tier (FIPS, STIG) is a real RKE2 advantage. But no source cited for P0-2 supports it, and it is a sales tier, not a day-one need. Putting the split off until a regulated customer pays for it costs nothing now.

### C. The upgrade treadmill is the real long-run cost, and the claim leaves it out

SUSE's RKE2/k3s lifecycle table [N4] gives each minor version roughly 14 months from GA to end of life:
- 1.34: GA 2025-09-10, EOL 2026-10-27
- 1.35: GA 2025-12-30, EOL 2027-07-17
- 1.37: GA 2026-09-15, EOL 2028-02-15

The table shows no LTS line. Over a 10-year horizon, OneMind must ship at least one Kubernetes minor upgrade a year to every box in the field, including offline Pi nodes. This cost hits any choice of k3s, RKE2 or k0s. Running both k3s and RKE2 doubles it.

The claim should state this as a gate: the distribution's in-place, offline-capable minor upgrade must be automatable from the OneMind updater.

### D. Batteries-included means inheriting someone else's CVEs

- **CVE-2025-62878** in Rancher local-path-provisioner [N5]:
  - CVSS 10.0 per GitHub, 8.4–9.1 per Orca
  - fixed in v0.0.34, disclosed 2026-02-04
  - local-path-provisioner is k3s's default storage
  - a default install was not directly exploitable: an attacker needs RBAC to add a `pathPattern`
- **CVE-2026-54250 / GHSA-jxr7-mqhw-9p98** [N6]:
  - path traversal when restoring a compressed etcd snapshot, CVSS 5.8
  - fixed in v1.35.3+k3s1, v1.34.6+k3s1 and v1.33.10+k3s1, published 2026-06-03
  - this is the exact path a OneMind restore UI would drive

Neither CVE disqualifies k3s. Both show that the components bundled with k3s (Traefik, local-path, klipper-lb, kine) each add triage work to a solo founder's queue. Disabling the ones OneMind replaces should be part of the decision.

### E. The 4 GB Pi tier has a hidden BOM cost

k3s's own docs [N2] say "etcd is write intensive; SD cards and eMMC cannot handle the IO load", and recommend an external SSD on Pi.

So the 4 GB Pi tier has two options:
- single-node SQLite/kine only, with no HA
- HA with an NVMe or SSD line added to every Pi BOM

The claim's "passes every gate" hides this choice. It applies equally to k0s with etcd.

### Counterweight: why the claim survives as a default

k0s has its own vendor risk. Mirantis was acquired by IREN, an AI data-centre operator, which IREN announced on 2026-08-04 [N7, SEC 8-K Ex. 99.1]. The release promises that "the open-source k0rdent AI platform will continue to be developed", and **it does not mention k0s**. k0s is also only a CNCF Sandbox project [N8].

k3s has the larger Pi and home-lab install base. Its documentation covers the Pi cgroup and iptables pitfalls [N2]. It is also what Olares, the closest competitor, runs. So k3s as the default is reasonable. "Only candidate" and the evidence for a mandatory RKE2 second tier are not.

## 3. New sources (searched for failure, CVEs, lifecycle cuts and vendor risk; all opened on 2026-11-10)

| ID | Source | Label |
|---|---|---|
| N1 | https://docs.k0sproject.io/stable/system-requirements/ | PRIMARY |
| N2 | https://docs.k3s.io/installation/requirements | PRIMARY |
| N3 | https://docs.k0sproject.io/stable/raspberry-pi5/ (v1.37.2+k0s.1) | PRIMARY |
| N4 | https://ranchergovernment.com/product-lifecycle-dates (RKE2/k3s table) | PRIMARY (SUSE subsidiary page; recheck against suse.com lifecycle by 2027-05) |
| N5 | https://orca.security/resources/blog/cve-2025-62878-rancher-local-path-provisioner/ | SECONDARY (vendor analysis of a GitHub advisory) |
| N6 | https://github.com/k3s-io/k3s/security/advisories/GHSA-jxr7-mqhw-9p98 | PRIMARY |
| N7 | https://www.sec.gov/Archives/edgar/data/0001878848/000114036126031053/ny20079234x2_ex99-1.htm (IREN 8-K Ex. 99.1, 2026-08-04) | PRIMARY |
| N8 | https://github.com/cncf/sandbox/issues/125 (k0s sandbox application), seen in search, not opened | UNVERIFIED |
| N9 | k0s AI-conformance entry: cncf/k8s-ai-conformance@c64e5bc8085da207715df96e458f2c6585c9f53e:v1.36/k0s/PRODUCT.yaml | PRIMARY |

Not used: idle-RAM reports for k3s on Pi (k3s-io/k3s #3558, #4593). They date from 2021–2022, are about older releases, and say nothing about 2026.

## 4. Verdict and what would flip it

**Weakened.**
- Keep k3s as the default for the Pi tier.
- Drop "only candidate".
- Make the RKE2 second tier conditional, not part of the base decision.
- Add k0s to the W4 bake-off as the single-distribution challenger.

**Evidence that would flip the decision:**
1. **Toward refuted, in favour of one distribution (k0s everywhere):** a bake-off on a Pi 5 4 GB and a Jetson Orin Nano Super (JetPack 6) showing all of the following:
   - k0s idle RSS at or below k3s's
   - GPU Operator or the device plugin working on L4T
   - unattended minor upgrades working offline

   This would also need k0s to keep releasing within about 30 days of each upstream minor and keep its AI-conformance listing for v1.37 or later through 2027.
2. **Toward upheld:** any of the following:
   - IREN or Mirantis deprioritises k0s: maintainer departures, release cadence slipping more than 60 days behind upstream, or CNCF Sandbox archival
   - k3s itself is added to cncf/k8s-ai-conformance, which removes the need for RKE2 entirely
   - a paying regulated or FIPS customer is in the pipeline, which turns the RKE2 tier from speculative into necessary
3. **Toward re-opening Talos:** siderolabs/sbc-jetson #23 merges and siderolabs/pkgs#1518 (nvgpu) ships, giving Jetson GPU support on Talos.
4. **Toward a different Pi tier:** measured OneMind baseline (distribution plus NATS, dashboard and Market controller) above about 2.5 GB RSS on a 4 GB Pi 5. That would make the 4 GB tier an agent-only node, whatever the distribution.

**Re-check by:** 2027-05-10 (6 months, Kubernetes facts).
