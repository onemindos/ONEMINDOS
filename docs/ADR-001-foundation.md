# ADR-001: OneMind OS Foundation (Base OS, Image, Updates, Kubernetes, Backups, Security)

**Status:** PROPOSED. Awaiting Zeus's approval. **Date:** 2026-11-10
**Rule applied:** copy what proven competitors (Home Assistant OS, umbrelOS, Olares) actually do; deviate only with evidence (see [RESEARCH-MISSION.md §2 rule 2](../RESEARCH-MISSION.md)).
**Evidence files** (every fact below is sourced there):
- E1 `research/platform/verify-ubuntu-vs-debian.md`
- E2 `research/platform/verify-kubernetes-distro.md`
- E3 `research/platform/verify-updates-rollback-backups-security.md`
- E4 `research/competitors/umbrel.md`
- E5 `research/competitors/olares.md`
- E6 HAOS docs: contributors.home-assistant.io/os/operating-system/ (+ /partitions/, /update-system/), read 2026-11-10

> **Correction to earlier advice:** ARCHITECTURE.md v0.1 recommended Ubuntu 24.04 + Kairos. Verification overturned both. Ubuntu's 10-year security updates need **paid Ubuntu Pro for commercial devices**, and **Kairos documents Raspberry Pi 5 as "currently not supported"** and commits an update as soon as cloud-init runs. This ADR supersedes those points.

---

## 1. What the proven competitors actually do

| | Home Assistant OS (E6, E3) | umbrelOS 2.0 (E3, E4) | Olares 1.12.7 (E3, E5) |
|---|---|---|---|
| Ships its own image? | **Yes**, one per board | **Yes**, x86 + Pi 4/5 | **No**, installs on Ubuntu/Debian |
| Base | Buildroot (built from source) | **Debian 13 trixie**, pinned snapshot | Your Ubuntu 22.04–25.04 / Debian 12–13 |
| Root filesystem | Read-only EROFS | Image-based | Normal mutable Linux |
| OS updates | **RAUC A/B**, signed bundles | **Rugix A/B**, signed (offline root key, refuses older versions, revocation list) | In-place via LarePass app |
| Rollback | Bootloader tries the new slot (3× on GRUB), falls back | Automatic on failure; ZFS pools survive rollback | **No A/B or OS rollback found** |
| Auto-update? | Never reboots itself | **Never auto-installs**; stable + beta channels | User-triggered |
| App runtime | Docker (Supervisor) | Docker Compose | **k3s** |
| Backups | Encrypted by default (SecureTar v3, audited), full/partial, local/NAS/cloud, 3-2-1 advice | Encrypted, hourly, retention up to 1 yr, to another Umbrel/NAS/USB; "FailSafe (ZFS RAID) is not a backup" | restic to local/S3; app restore only for some apps |
| Secure Boot/TPM | Not found | Not used | — |
| License | Apache-2.0 | PolyForm **Noncommercial** | AGPL-3.0 **and** a non-commercial LICENSE.md (conflict) |

**What we learn:**
1. The two most proven appliances (HAOS, Umbrel) both **ship their own read-only image with A/B updates and automatic rollback, keep user data on a separate partition, and never update on their own.**
2. The one that installs on top of a normal distro (Olares) **has no OS rollback.**
3. Only Olares uses Kubernetes, and it chose **k3s**.

---

## 2. Decisions

### D1. Ship our own image, like HAOS and Umbrel
- OneMind OS is flashed as an image (USB/SD/NVMe), **including on bring-your-own hardware**. The safety guarantees (read-only root, A/B, rollback) only hold if we own the whole disk.
- A script installer on an existing Linux is **developer mode only**, like Olares's model, which lacks rollback.

### D2. Base: **Debian 13 "trixie"** for the core image, plus an NVIDIA **L4T/Ubuntu 24.04 flavor for Jetson/DGX only**

| Evidence (E1) | Debian 13 | Ubuntu 24.04 |
|---|---|---|
| Free security support | Regular to **2028-08-09**, LTS to **2030-06-30** (ELTS paid to 2035) | Standard to **May 2029**; 10-yr ESM requires **Ubuntu Pro: free only for personal use (5 machines), $25/yr workstation / $500/yr server, "Pro for Devices" per-device fee unpublished** |
| Proven appliance use | **umbrelOS**, Proxmox VE 9, Olares-supported | Olares-supported, NVIDIA JetPack/DGX OS |
| NVIDIA on x86/RTX | CUDA 13.5 lists Debian 12/13; NVIDIA runs a `debian13` driver repo (Umbrel uses it). Debian's own driver (550) predates RTX 50, so we must use NVIDIA's repo. **GPU Operator does not list Debian** | GPU Operator officially lists Ubuntu 22.04/24.04/26.04 |
| Raspberry Pi 5 | Stock Debian 13 is not Pi-5 certified, but **Umbrel ships Pi 5 using Raspberry Pi's own kernel/firmware repo on Debian**; Raspberry Pi OS itself is Debian trixie | Certified |
| Jetson / DGX | Unverified | **JetPack 7 = Ubuntu 24.04, DGX OS 7 = Ubuntu (NVIDIA-only base)** |
| Snap | None | `ubuntu-server-minimal` hard-depends on snapd |
| Governance | Community; no vendor can change the terms | Canonical (corporate) |
| Image tooling | Rugix builds Debian; Kairos supports Debian | Kairos supports Ubuntu; no Rugix Ubuntu base documented |

**Why Debian wins:** it's the proven appliance base (Umbrel), costs nothing per device we sell, has no Snap coupling, and its governance can't be changed under us. **Why Jetson stays on Ubuntu:** NVIDIA ships Jetson and DGX only on its Ubuntu-based L4T, so we follow NVIDIA there.

**Cost we accept:** two flavors (Debian core + Jetson L4T). Apps don't care, because they're containers on k3s.

**GPU risk and mitigation:** the GPU Operator isn't validated on Debian. Use NVIDIA's host driver + Container Toolkit + the k8s device plugin (also the Jetson path). Spike this early (§4).

### D3. Updates: **A/B image, signed, user-controlled** (the Umbrel/HAOS pattern)
- **Tool: Rugix**, the Umbrel-proven choice: MIT/Apache-2.0, A/B, mandatory signatures, delta updates, builds Debian, Pi 5 proven by Umbrel. **Alternative: RAUC**, HAOS-proven (LGPL-2.1, x.509, HSM option). **Kairos is dropped as the lead** because its docs say Pi 5 is unsupported, it commits on cloud-init, and its Trusted Boot docs contradict themselves. Kairos stays a candidate for the Jetson/DGX flavor (it supports Orin NX/AGX/Thor and DGX Spark) and for Trusted Boot later.
- **Improvement over both competitors:** HAOS marks a slot "good" once the Supervisor starts, and Kairos once cloud-init runs. **OneMind marks good only after k3s + core platform pods are healthy.** Rugix requires us to supply this step anyway (E3).
- **Signing (copy Umbrel):** offline root key, online signing keys, a hash-pinned bundle, a revocation list, and refusal to install anything not newer.
- **UX (copy Umbrel + HAOS):** never auto-install or auto-reboot. Stable/beta channels, notification + one-click update, **automatic pre-update backup**.
- **Layers update separately:** OS image (A/B) · k3s version (system-upgrade-controller / Kairos-style operator, never skipping a minor) · apps (Market, per app) · firmware.

### D4. Kubernetes: **k3s on every tier; RKE2 for the hardened enterprise/public-safety tier**
- **k3s *is* Kubernetes:** CNCF-certified conformant (v1.35–1.37), the same API as your DOKS cluster, Apache-2.0, a CNCF Sandbox project (SUSE vendor) (E2).
- **Why not "full" upstream k8s on a box:** k3s packs everything into one binary. The docs minimum is a 2-core / 2 GB server and a 512 MB agent, and it measures ~1.6 GB with a workload (E2). RKE2 needs 4 GB minimum / 8 GB recommended, too heavy for Lite/Edge boxes.
- **Proven:** Olares runs k3s. NVIDIA's GPU Operator lists K3s and RKE2.
- **Scales:** 3 servers with embedded etcd supports ~1,200 agents (E2), from a single box to a cluster.
- **RKE2 for public safety/enterprise:** "hardened by default", CIS profile, FIPS 140-2 builds, SELinux policy (E2). Same Kubernetes API, so the same OneMind apps run on it.
- **Your DOKS cluster can convert:** Helm + Argo CD apps are portable. Three changes (E2):
  1. DigitalOcean load-balancer annotations → ServiceLB/MetalLB
  2. `do-block-storage` → local-path/Longhorn
  3. ingress-nginx (EOL March 2026) → Traefik

### D5. Storage and backups (copy HAOS encryption + Umbrel schedule; add k3s specifics)
- **Disk layout (HAOS pattern):** boot · OS slot A · OS slot B · small overlay (host settings) · **data partition** (everything users and apps own). OS updates never touch data.
- **Volumes:** single box uses local-path (no replication, so backups are mandatory). 3+ nodes use **Longhorn** (~4 vCPU / 4 GiB per node) (E2). Optionally ZFS mirror/RAIDZ like Umbrel FailSafe, explicitly **"not a backup."**
- **What gets backed up:**
  1. k3s datastore (etcd-snapshot, 2×/day, keep 5, optional S3; SQLite single-node coverage UNVERIFIED, so spike it)
  2. app volumes via **restic** (AES-256, authenticated). *Not* Velero file-system backup, which doesn't support hostPath and uses one shared key (E3).
  3. OneMind config, identity and secrets (separately encrypted recovery kit)
- **Policy:** encrypted by default (HAOS) · scheduled hourly/daily with retention (Umbrel) · destinations: another OneMind box, NAS, USB, S3 (3-2-1, HAOS docs) · automatic **pre-update snapshot** · regular **restore tests** shown in the dashboard ("last verified restore").

### D6. Security baseline
- **Day 1 (matches or beats HAOS/Umbrel):** read-only root · signed A/B updates · AppArmor profiles (HAOS uses AppArmor) · k3s CIS hardening (secrets encryption at rest, Pod Security Admission, network policies, audit logs) · no default SSH password · per-app isolation · capability gateway (ARCHITECTURE §4).
- **Phase 2 (goes beyond the competitors):** Secure Boot + TPM 2.0 + LUKS disk encryption on x86 (Kairos Trusted Boot is the documented reference) · Pi secure boot (OTP-held key) and Jetson fuse-based secure boot. **⚠ Fusing is irreversible**, so only for OneMind-built hardware, with careful key management.
- **Compliance:** EU Cyber Resilience Act vulnerability reporting has applied since **2026-09-11**, main obligations from **2027-12-11** (E3). Selling hardware in the EU means SBOMs, CVE handling and support periods. Plan for this now.

---

## 3. The stack, one picture

```
┌──────────────────────── OneMind Dashboard + apps + AI capability layer ───────────────┐
│ k3s (RKE2 for hardened tier) · Traefik · local-path/Longhorn · NATS · identity · backups│
├────────────────────────────────────────────────────────────────────────────────────────┤
│ OneMind OS image  = Debian 13 (pinned snapshot) · read-only root · Rugix A/B · signed  │
│   flavors: x86 (+NVIDIA debian13 driver for Pro) · Pi 5 (Raspberry Pi kernel/firmware) │
│ OneMind Jetson    = NVIDIA L4T / Ubuntu 24.04 (only NVIDIA-supported base)             │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Disk: boot │ OS-A │ OS-B │ overlay (settings) │ DATA (apps, files, k3s, backups staging)│
└────────────────────────────────────────────────────────────────────────────────────────┘
```

## 4. Spikes before final approval (prove on real hardware)
1. Debian 13 + Rugix A/B + k3s on the **Dell 5540** and **Beelink U55**: install, update, forced-failure rollback, data survives.
2. "Healthy before commit": the slot stays uncommitted until k3s + core pods are ready; a broken update rolls back.
3. Single-node k3s datastore backup/restore (SQLite) + restic app-volume restore onto a clean box.
4. **Pi 5** with the Raspberry Pi kernel on Debian + Rugix (Umbrel's path).
5. **RTX** (cloud GPU or later box): NVIDIA `debian13` driver + Container Toolkit + device plugin on k3s.
6. **Jetson** flavor: L4T + k3s + device plugin; pick an A/B method (Kairos vs NVIDIA's own vs RAUC).
7. Convert a copy of one DOKS app (Helm/Argo) to k3s with the three changes in D4.

## 5. Open items (UNVERIFIED in evidence)
SUSE's k3s support lifecycle · RKE2 rollback docs · single-node SQLite snapshot coverage · Longhorn backup encryption · GPU Operator on Debian · Jetson A/B method · Ubuntu Pro for Devices pricing (unpublished).
