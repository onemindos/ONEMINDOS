# DC-13 refuter: NVIDIA GPU drivers on Debian (cost and business lens)

| Field | Value |
|---|---|
| Target | DC-13 (Q16; Q55, Q92, Q101 folded in). Conclusion in `evidence/qbank/W4.md` (Q16), `05-kubernetes-cluster-conversion-nvidia.md` P0-6 and §7.2, and the DC-13 row of `01-FOUNDATION-DECISION.md`: "**Weakened, not flipped.** Debian works for driver + toolkit + device plugin (time-slicing); for the Pro box nothing needed fails; the cost is that OneMind builds and signs its own driver modules into each image. It loses GPU Operator lifecycle, signed precompiled drivers and AI conformance, so allow Ubuntu LTS + RKE2 for the Omni/Cluster GPU-server tier." |
| Lens | Cost and business (recurring maintenance, security-patch latency, cost of a second x86 flavor) |
| Protocol | RESEARCH-MISSION.md §2 rule 7. Only the conclusion and its cited claims (C-W4-021…028, 037, 038; C-W2-026) were read. |
| Date | 2026-11-10 (re-check by 2027-05-10) |
| Verdict | **upheld**, with a cost correction. The tier split is right, and the counter-evidence below makes it stronger rather than reversing it. But "nothing needed fails" on the Pro box understates a **recurring** cost: NVIDIA's DKMS build on Debian 13 breaks on routine point-kernel updates, which can hold back kernel security fixes. |

## 1. Re-checking the cited sources

| Sub-claim | Ledger | Holds? |
|---|---|---|
| GPU Operator OS list has no Debian; K3s column is Ubuntu-only | C-W4-021, C-W2-026 | Yes |
| GPU Operator doesn't support Jetson or (by listing) GeForce | C-W4-023, C-W4-024 | Yes (024 is medium: "not listed", not "excluded") |
| Signed precompiled drivers only for Ubuntu kernels (and SUSE partner) | C-W4-025 | Yes |
| Container Toolkit apt covers "Ubuntu, Debian"; CUDA 13.5 supports Debian 12/13 | C-W4-026, C-W4-027 | Yes |
| Driver guide covers Debian 12/13 with DKMS-built nvidia-open; no Secure Boot/MOK procedure | C-W4-028 | Yes. This is where the recurring cost lives. |
| AICR and CNCF AI Conformance list RKE2 and others, not a Debian k3s base | C-W4-037, C-W4-038 | Yes |

## 2. Strongest counter-argument

**The Pro tier's "it works" is a per-kernel promise that NVIDIA does not test on Debian, and a single break blocks a security release.**

- On Debian 13, NVIDIA driver 595.71.05's DKMS build fails during an ordinary apt point-kernel update (6.12.94 → 6.12.96+deb13) because helper scripts lose their execute bit. dpkg leaves the new kernel unconfigured. The issue has been open since 2026-07-22 with no NVIDIA reply, and a second user reports blocking kernel updates to stay working [C-REF-DC-cost-009]. Point kernels are how Debian ships security fixes, so on an A/B image pipeline this shows up as a **build that won't produce a release** until someone patches the driver packaging.
- Debian's own packaged driver is worse: `nvidia-kernel-dkms` 550.163.01-2 from trixie non-free fails against a newer kernel API, with no NVIDIA response [C-REF-DC-cost-010]. That forces NVIDIA's own `debian13` repo (prior-verified) and rules out "use the distro driver" as the low-cost path.
- Each break costs founder time **on the critical path of a CVE fix**, which matters under the CRA's "without delay" duty (DC-04). On Ubuntu, Canonical builds and signs precompiled modules for each kernel (C-W4-025), which moves that cost to the vendor.
- The conclusion also books "OneMind signs its own modules" as a one-off. Under Secure Boot (DC-18), it means OneMind's key signs every kernel × driver pair for the life of the product, with no NVIDIA procedure for Debian (C-W4-028).

**Why the verdict is still upheld.** The counter-argument raises the cost of Debian on the Pro tier, but it does not make Ubuntu cheaper *there*: the Pro box uses consumer/pro RTX cards, which the GPU Operator does not list (C-W4-024), so the Operator's lifecycle does not apply even on Ubuntu. The failures above are build-time failures that an image pipeline catches before devices see them; they cost time, not fleet outages. On the Omni/Cluster tier, the evidence supports the conclusion's split. The new sources mainly strengthen the case for a **precompiled, pinned driver per image** rather than DKMS on the device.

## 3. New sources (searched for DKMS regressions and driver-package abandonment on Debian)

| ID | Source | What it shows |
|---|---|---|
| C-REF-DC-cost-009 | https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1258 | Debian 13 point-kernel update breaks the NVIDIA DKMS build; open, no NVIDIA reply; users block kernel updates. |
| C-REF-DC-cost-010 | https://forums.developer.nvidia.com/t/nvidia-driver-550-163-01-debian-trixie-package-fails-to-build-against-proxmox-ve-kernel-7-0-6-2-pve-vma-lock-offset-undeclared-in-nv-mmap-c/381219 | Debian's packaged 550 driver fails on a newer kernel; "unmaintained" is a community claim (not verified). |

## 4. What would flip the decision

- **Flips the Pro tier to Ubuntu (or the GPU-server flavor on all RTX boxes):** the GPU lab spike (Debian 13 + NVIDIA repo + toolkit + device plugin on k3s) logs **more than one release-blocking driver build failure per year**, or a Debian security kernel that cannot ship within the CRA patch target because no NVIDIA driver builds against it.
- **Flips back toward one base everywhere (Debian):** NVIDIA adding Debian to the GPU Operator or precompiled-driver matrix, or Debian shipping signed nvidia-open modules for its own kernels.
- **Upholds and closes the cost gap:** the image pipeline builds nvidia-open modules once per image in CI (not DKMS on the device), signs them with the OneMind key, and gates releases on a GPU smoke test. That turns C-REF-DC-cost-009-type breaks into CI failures with a known workaround (`PRE_BUILD chmod`).

**Required correction:** replace "nothing needed fails" for the Pro box with "works, with a recurring per-kernel driver-build cost that can delay security releases", and add that cost to the H-1 maintenance budget.
