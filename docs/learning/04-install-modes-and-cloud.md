# Lesson 04: Install Modes (Image vs Installer) and Running OneMind in the Cloud

**For:** Zeus (learning track) · **Date:** 2026-11-11
**Sources:** the ultracode research on branch `research/ultracode-foundation` (PR #1, rev. 4.1): `research-output/01-FOUNDATION-DECISION.md` (Install and Kubernetes rows), `research-output/02-competitors/olares.md`, `research-output/05-kubernetes-cluster-conversion-nvidia.md` §9, `research-output/12-dashboard-clients-xr.md`. Claim IDs (C-…) resolve in `research-output/evidence/claims/*.csv` on that branch.
**Status:** founder notes and recommendations. Not logged decisions.
**Builds on:** [03-base-os-debian-vs-ubuntu.md](03-base-os-debian-vs-ubuntu.md)

---

## 1. Can OneMind work the Olares way?
Olares is **not an OS image**. It is an installer that puts k3s and its apps on top of the user's Ubuntu or Debian. Its ISO writes Ubuntu, and its script supports Ubuntu 22.04–25.04 or Debian 12/13 [C-TD-olares-007, C-TD-olares-041]. Olares doesn't control the disk layout, has no A/B copies and no automatic rollback [C-TD-olares-014, C-TD-olares-015], and checks updates with an MD5 checksum from the same server, not a signature [C-TD-olares-004, C-TD-olares-005].

**Yes, technically, and it should be a second install mode, but not the main product.**

**What you gain:**
- **No Canonical issue.** Installing on a customer's *unmodified* Ubuntu is allowed (Olares and Cloudron do this).
- **Faster to start.** There is no image pipeline, and it runs on any existing PC or server.
- **It fits machines you don't own:** clouds and company servers.

**What you lose:**

| Olares-style installer | Why it matters for OneMind |
|---|---|
| No automatic rollback | A bad update leaves a robot, greenhouse controller or C2 station broken until someone fixes it on site (R-1, R-3) |
| MD5 checksum, not a signature | Anyone who can tamper with the download server can push a fake update; unacceptable with AI driving physical actions |
| Doesn't own the OS | Each distro release can break you. Olares's Debian 13 install broke on a sources-file format change (issue #4171, open 2026-09) [C-TD-olares-050] |
| EU CRA | Reliable security updates are hard to deliver without controlling the OS underneath |
| "Simple as a Pi" | The customer has to install and maintain Linux first |

**The research already plans both modes** (`01`, Install row):
1. **Main product:** the OneMind image (A/B, rollback, signed) via flash image, USB installer, VM images, preinstalled boxes and NVIDIA flash.
2. **Developer preview:** OneMind on a container, VM or existing Linux. Host-modifying install scripts become **unsupported after the image's general release**.

**Recommendation: keep both, with clear roles.**
- **OneMind image:** every box you sell or ship to the field.
- **OneMind on your existing Ubuntu or Debian:** servers and clouds you don't control. Updates are signed but have no OS rollback, and are labelled as such. This also sidesteps the Canonical question for GPU servers, because the customer's Ubuntu is unmodified.
- Both run the same management layer, apps and Market.

## 2. Is the route cloud-server friendly?
**Yes.** There are three ways, and all use the same management layer, apps and Market.

| Way | How | Use it for |
|---|---|---|
| **1. OneMind image as a cloud VM** | The same Debian image exported as a VM disk and uploaded as a custom image (DigitalOcean, AWS, Hetzner, …). A/B, rollback and signing work as on a box. | Cloud nodes you control end to end: your hub, customer "cloud boxes" |
| **2. OneMind on the cloud's stock Ubuntu or Debian** | Olares-style install on a normal VM. Updates are signed, with no OS rollback. Unmodified Ubuntu means no Canonical issue. | Quick starts, companies with their own cloud rules, GPU cloud servers |
| **3. OneMind on managed Kubernetes** (DOKS, EKS, GKE) | No OneMind OS. The management layer and apps run as normal Kubernetes apps, because k3s and managed Kubernetes follow the same certified standard. | **The current cloud cluster**, and enterprises already on Kubernetes |

**Why the research supports it:**
- VM images are a planned install path (`01`, Install row).
- **Every lab test ran in VMs** (RAUC, rollback, k3s gate, Secure Boot, restore). A cloud server is a VM, which makes it the best-tested target.
- The DOKS cluster is in the plan:
  - Phase 0 (weeks 1–4): replace the retired ingress-nginx with Gateway API + Traefik, and enable off-site backups [C-W4-016].
  - Later: an optional move to k3s/RKE2. That is 13 dependencies, not 3; the hardest is storage, about 95 PVs and 1.2 TiB [C-W4-063].
- NATS leaf nodes dial **out** to the hub, so home and edge boxes need no open ports.

```
Cloud (DOKS today, OneMind cloud VMs later)   ← hub: management layer, Market, backups, AI gateway
        │  NATS leaf + Tailscale (boxes dial out, no open ports)
        ├── Home: Pi 5 / mini PC (OneMind image)
        ├── Greenhouse / print farm hub (OneMind image)
        ├── Field kit / TAK (OneMind image, offline-first, syncs when back)
        └── Robots: Jetson (NVIDIA L4T Ubuntu, k3s agent)
All in one Nodes app, one dashboard, one AI.
```

**Cloud caveats:**
- **Secure Boot and TPM differ per cloud** (each has its own virtual implementation). The research tested emulation only, so test per provider.
- **GPU cloud servers** follow the GPU-tier rule: Ubuntu + RKE2, or way 2 on the cloud's own Ubuntu, where NVIDIA's support is.

## Vocabulary
- **OS image:** the whole operating system shipped as one sealed, versioned file. Updates swap the whole thing.
- **Installer mode:** software added on top of someone else's OS. You don't control what's underneath.
- **A/B update:** two OS copies. Update the inactive one, boot it, and keep it only if it's healthy; otherwise roll back.
- **Signature vs checksum:** a checksum (MD5) only detects accidental corruption. A cryptographic signature proves *who* made the update.
- **Managed Kubernetes:** the cloud provider runs the Kubernetes control plane for you (DOKS, EKS, GKE).
- **NATS leaf node:** a small messaging server that dials out to a hub, so edge sites need no inbound ports.

## Check yourself
1. Why can OneMind install on a customer's Ubuntu without Canonical's permission, but not ship its own Ubuntu image?
2. What is the one thing an installer can never give you that an A/B image can?
3. Which of the three cloud ways does your current cluster use today?
4. Why is a cloud VM the best-tested target so far?
