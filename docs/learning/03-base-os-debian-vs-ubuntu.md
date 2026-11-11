# Lesson 03: Base OS: Debian vs Ubuntu vs bootc, and the Real-World Call

**For:** Zeus (learning track) · **Date:** 2026-11-11
**Sources:** the ultracode research on branch `research/ultracode-foundation` (PR #1, rev. 4.1): `research-output/01-FOUNDATION-DECISION.md` §3.1.6, `research-output/26-OPEN-QUESTIONS-FOR-ZEUS.md` (Z-01, Z-38), `research-output/02-competitors/MATRIX.md` and `olares.md`. Claim IDs (C-…) resolve in `research-output/evidence/claims/*.csv` on that branch.
**Status:** founder notes and a recommendation. **Not a logged decision**: Z-38 is still open.

---

## 1. The research result
Under the scoring rules locked before scoring: **Ubuntu 26.04 = 65, RHEL-family bootc = 64, Debian 13 = 63**. That is a statistical tie, and the research rates its confidence **Low**. Ubuntu wins 11 of 14 weight-sensitivity runs, decided by a 6–4 row count [C-DEC4-001, C-DEC4-006].

Ubuntu's win is **CONDITIONAL** on two things:
- **G1, licence (Z-01).** Canonical allows redistribution of *modified* Ubuntu only if it is "approved, certified or provided by Canonical". Without approval you must remove the trademarks **and** recompile the binaries [C-W2-050, C-LIC-011]. A refuter found the permission "can be revoked at any time" [C-REF5-S1L-001].
- **G5, one OS from Pi to cluster.** Jetson runs NVIDIA L4T Ubuntu 24.04 while the core would be 26.04. Debian and bootc carry this same condition.

**"Blocked" means shipping, not using.** You can develop on Ubuntu freely. What needs Canonical's yes is shipping OneMind's own modified, read-only Ubuntu image.

## 2. Head-to-head: Debian vs Ubuntu (`01` §3.1.6 f)
Debian beats Ubuntu **6–5** on the decision-critical rows.

| Debian wins | Affects |
|---|---|
| Legal to ship today (G1) | Every box |
| Cost at 10k units (about $40 vs $120 per device, `lifecycle-cost-2036.md`) | Every box |
| Pi 5 pipeline (DC-19) | First beta box |
| CRA FOSS route (DC-04) | Every EU box |
| Governance (community, not one company) | Every box, and the "sovereignty" brand |
| Proven competitor (umbrelOS: Debian on Pi 5 + x86) | Core product |

| Ubuntu wins | Affects |
|---|---|
| NVIDIA GPU (DC-13) | GPU servers: an Ubuntu + RKE2 flavor is allowed anyway |
| ROS 2 (DC-15) | Robots: ROS 2 runs in containers on every base |
| NVIDIA trajectory | Jetson and GPU servers: Ubuntu flavors already |
| IIoT vendor process | Industrial: the bootc profile in year 2 |
| Signed GPU modules under Secure Boot | GPU boxes |

**Takeaway:** Ubuntu's wins all sit on tiers that already get their own Ubuntu or bootc flavor. Debian's wins sit on the boxes OneMind ships first: the day-180 beta (x86 mini PC + Pi 5) and the hypothesised first kit (Greenhouse + TAK: Lite hub + Pi leaves).

## 3. Recommendation (Z-38 option b, founder decision)
```
Pi 5, mini PCs, x86 hubs (Edge / Lite / Pro)  →  Debian 13 OneMind image + RAUC
Jetson robots                                  →  NVIDIA L4T Ubuntu 24.04 (any base needs this); Yocto meta-tegra test in 180 days
GPU servers / robot simulation                 →  Ubuntu LTS + RKE2, after Canonical answers (Z-01)
Industrial / enterprise (year 2)               →  AlmaLinux / RHEL bootc profile; Fedora IoT as CI canary
Same on every box: apps, Market, dashboard, AI gateway, k3s, NATS, restic, plugins E1–E10
```
Keep the Ubuntu 26.04 CI leg running. Ask Canonical anyway (Z-01), because the Jetson flavor needs the answer whatever the core is. If Canonical offers a written, long-term, affordable agreement, switching is cheap: the disk layout, RAUC and signing are identical.

## 4. Real-world risks with Debian, and how they're covered
1. **Recent Pi 5 boot problems on Debian 13** [C-REF4-S1R4-technical-004, -005]. One of them hits Ubuntu's Pi 5 image too. *Covered by* the hardware tests on a real Pi 5 (`22-HARDWARE-LAB-TEST-PLAN.md`).
2. **Debian's long-term security fixes rest on one paid team (Freexian) after 2028** [C-REF-DC-cost-003]. *Covered by* planned rebases to Debian 14/15, budgeted in the plan. ELTS for shipped boxes needs an OEM-style agreement (Z-06).
3. **NVIDIA's Debian drivers aren't pre-signed for Secure Boot** (DKMS only) [C-REF4-S1R4-security-005], so OneMind must sign them itself for RTX boxes. *Covered by* OneMind's own signing keys (Z-04), which are needed anyway.

## 5. What competitors run (`02-competitors/MATRIX.md`)
**Products that ship their own OS image (OneMind's model):**

| Base | Products |
|---|---|
| **Debian** | umbrelOS (13), StartOS (13), Proxmox VE (13), TrueNAS (12 → 13), FreedomBox, YunoHost (12) |
| Buildroot | Home Assistant OS, ZimaOS |
| Yocto | balenaOS |
| Closed | Unraid (Slackware-derived), Synology DSM |
| NVIDIA L4T Ubuntu | ClawBox (Jetson) |

**Products that install on top of the user's OS:**
- **Olares:** its ISO writes Ubuntu; the script and Compose installs work on Ubuntu 22.04–25.04 or Debian 12/13 [C-TD-olares-007, C-TD-olares-041]. Olares One's preinstalled OS is not stated in the research (likely Ubuntu, UNVERIFIED).
- Cloudron runs on Ubuntu only.
- CasaOS, Runtipi, Coolify, Dokploy, Cosmos, N.O.M.A.D., Formant and Viam run on the host's Debian or Ubuntu.

No competitor in the matrix ships its own image built on stock Ubuntu.

## Vocabulary
- **Base OS / distro:** the Linux distribution the image is built from.
- **Buildroot:** a tool that builds a minimal Linux from source (no distro). It gives a tiny image but leaves every patch to you. The research measured it as 4–6× smaller with only 7–18% fewer CVEs [C-LAB-minimal-image-dc20-011].
- **bootc:** Red Hat-family image-mode OS, where a container image becomes the bootable OS.
- **CONDITIONAL (gate):** passes only if something not yet true becomes true. It still gets ranked.
- **Debrand-and-recompile:** removing Ubuntu's trademarks and rebuilding every binary, which is the route if Canonical says no.

## Check yourself
1. Why is "Ubuntu wins 65 vs 63" not a strong reason to pick Ubuntu?
2. What exactly does Canonical's permission cover, and what does it not?
3. Why does the Canonical question matter even if the core is Debian?
4. Which competitor is the closest match to OneMind's core box, and what does it run?
