# Proxmox VE: Tier B condensed teardown

**Date:** 2026-11-11 · **Tier:** B (condensed) · **Workstream:** W1 · **Claims:** `evidence/claims/TD-proxmox-ve.csv` (C-TD-proxmox-ve-001…042) · **Sources:** `evidence/sources/TD-proxmox-ve.md`, saved copies and hashes in `evidence/sources/TD-proxmox-ve/`
**Analysed:** Proxmox VE 9.2 (released 2026-05-21; arm64 edition 2026-08-05), source at the development heads listed in §1 [C-TD-proxmox-ve-001, -002]

> ### Explain it like I'm the founder
> Proxmox VE is the free "run lots of virtual machines and containers on your own servers" product that small businesses, home labbers and, increasingly, companies leaving VMware use. It is **Debian with a management layer on top**, the same base OneMind picked. That is good news: a 20-year-old company has proven that Debian holds up as an appliance base for a long time.
> But Proxmox is built for **an administrator at a server**, not for a family or a robot. Updates are ordinary `apt` package upgrades. There is **no second copy of the OS to fall back to**. If an upgrade breaks the bootloader, someone needs a USB stick and a rescue shell. Real users hit exactly that in the 8 → 9 upgrade. The only "undo" Proxmox gives is "boot the previous kernel".
> **Copy:** the upgrade checker script, the "keep a fallback kernel" rule, the 1 GiB boot partition, signed app catalogues, OCI images as one more app source, and the business model where every feature is free and you pay only for the stable channel and support.
> **Do better:** A/B images with automatic rollback, full-disk encryption from day one, Raspberry Pi and Jetson support, and an AI layer. Proxmox has none of these.

---

## 0. Glossary

| Term | Meaning here |
|---|---|
| **Hypervisor** | Software that runs virtual machines (VMs). Proxmox uses KVM/QEMU. |
| **LXC** | Linux Containers: "system containers" that feel like a small VM but share the host kernel. Proxmox's main container type. |
| **OCI image** | The standard container image format (what Docker pulls). Proxmox 9.1+ can turn one into an LXC container. |
| **pmxcfs** | Proxmox Cluster File System: a small SQLite database replicated to every node by Corosync and shown as files in `/etc/pve`. |
| **Corosync / quorum** | The cluster messaging layer. "Quorum" means a majority of nodes agree, so HA needs 3+ nodes. |
| **Fencing / watchdog** | A node that loses quorum reboots itself (via a watchdog timer), so its VMs can safely start elsewhere. |
| **vzdump / PBS** | vzdump is the built-in backup tool. Proxmox Backup Server (PBS) is a separate product with deduplicated, encrypted backups. |
| **proxmox-boot-tool** | Proxmox's script that keeps one or more EFI System Partitions (ESPs) in sync and lets you **pin** a kernel. |
| **ESP** | EFI System Partition, the small FAT partition the firmware boots from. |
| **shim** | A small Microsoft-signed bootloader that lets Linux boot with Secure Boot on. |
| **A/B update** | Two OS copies: write the new one to the idle slot, reboot into it, and roll back automatically if it fails. **Proxmox does not do this.** |
| **Enterprise / no-subscription repo** | Two apt channels. The enterprise channel is "most stable" and needs a paid key. The free channel is "for testing and non-production use". |

---

## 1. What was analysed

| Item | Value |
|---|---|
| Product | Proxmox Virtual Environment (PVE) 9.2, Debian 13.5 base, kernel 7.0 default, QEMU 11.0, LXC 7.0, ZFS 2.4 [C-TD-proxmox-ve-001] |
| Release line | 9.0 on 2025-08-05 (Debian 13) · 9.1 on 2025-11-19 · 9.2 on 2026-05-21 · 9.2 arm64 on 2026-08-05 [C-TD-proxmox-ve-001, -033] |
| Code (official read-only mirrors) | `pve-installer@ce4ea55a` (9.2.9), `pve-manager@e1e1c4af` (9.2.27), `pve-container@15eb5c70` (6.1.20), `pve-access-control@bbc4ed63`, `pve-docs@7742f85b`, `proxmox-kernel-helper@3b801dcd` (9.2.1, git.proxmox.com) [C-TD-proxmox-ve-002] |
| Licence | AGPL-3.0 (core); proxmox-boot-tool GPL-2.0-only; docs GFDL-1.3 [C-TD-proxmox-ve-004, -005] |
| Company | Proxmox Server Solutions GmbH, Vienna, founded 2005; self-reports 1.5 M hosts (SECONDARY) [C-TD-proxmox-ve-038] |
| Method | Read source at pinned SHAs and official docs and wiki. Nothing was installed or run (Tier B). |

**Licence rule (mission §2.4):** AGPL code is studied for **patterns only**. Nothing below recommends copying Proxmox code into Apache-2.0 OneMind.

---

## 2. Architecture

```
            Web UI (ExtJS; Yew mobile UI)  ·  REST API (/api2/json)  ·  pvesh CLI
                                   │
   pveproxy / pvedaemon / pvestatd / pvescheduler   (Perl, moving to Rust)
        │                │                    │                     │
   qemu-server       pve-container       pve-storage          pve-ha-manager
   (KVM VMs)         (LXC + OCI→LXC)    (LVM-thin, ZFS,       (CRM/LRM, watchdog
                                          Ceph, NFS, iSCSI)     fencing)
        └──────────── pmxcfs (/etc/pve: SQLite, replicated by Corosync) ────┘
                                   │
               Debian 13 userland (mutable, apt-managed)
               proxmox-kernel (Ubuntu-derived, Proxmox-signed) + ZFS
```

- **Base OS:** stock Debian 13 with Proxmox's own kernel and packages layered on top. The FAQ states "Proxmox VE is based on Debian GNU/Linux" [C-TD-proxmox-ve-003].
- **Config plane:** every node holds the whole cluster config in **pmxcfs**, an SQLite database replicated by Corosync and capped at 128 MiB [C-TD-proxmox-ve-028]. This is the same idea as k3s's SQLite/kine datastore, but with the cluster replication built in.
- **HA:** 3+ nodes for quorum (QDevice for 2 nodes). Fencing uses a hardware watchdog or `softdog` [C-TD-proxmox-ve-029]. 9.2 added dynamic load balancing [C-TD-proxmox-ve-001].
- **Multi-cluster:** a separate product, Proxmox Datacenter Manager, reached 1.0 on 2025-12-04 and 1.1 on 2026-05-28 [C-TD-proxmox-ve-040].
- **No Kubernetes.** Workloads are VMs and LXC containers. Users run Kubernetes *inside* VMs.

---

## 3. Image build and install paths

**How the image is built (from code).** The installer does not assemble the OS. It copies a **prebuilt `pve-base.squashfs`** off the ISO with `unsquashfs` [C-TD-proxmox-ve-006]. Then it `dpkg --unpack`s every `.deb` in `proxmox/packages/` on the ISO and skips packages that do not fit the machine: `grub-pc` vs `grub-efi`, Secure Boot packages, and Intel vs AMD microcode. Last, it runs `dpkg --configure -a` [C-TD-proxmox-ve-007]. The squashfs and ISO build tooling is **not in Proxmox's public git index** [C-TD-proxmox-ve-008]. So the outer pipeline (snapshot pinning, reproducibility) cannot be audited from source.

**Disk layout (from code)** [C-TD-proxmox-ve-009, -010, -011]:

| # | Partition | Size | Notes |
|---|---|---|---|
| 1 | BIOS boot (EF02) | 1 MB | x86 only, skipped on arm64 |
| 2 | ESP (EF00) | **1024 MB** on disks > 100 GB, else 512 MB | "to allow users having multiple kernels/UKI's" |
| 3 | OS | rest | ext4/xfs → LVM VG `pve`: `swap`, `root` (≤ 96 GiB by default), `data` thin pool for guests · or ZFS `rpool/ROOT/<volume>` · or Btrfs |

There is **one root**, with no second slot and no read-only system. The minimum disk is 2 GB, with a warning below 8 GB [C-TD-proxmox-ve-009].

**Install paths** [C-TD-proxmox-ve-039]: graphical or TUI ISO, **automated install from an answer file** (`proxmox-auto-installer`, with PXE menu generation), and install on top of Debian 13. Proxmox warns that the Debian route "presumes" a correctly prepared system. There are no preinstalled appliances or SD-card images.

---

## 4. Update and rollback

```
Admin                     pve-manager / apt                  proxmox-boot-tool           Firmware
  │ apt update (or UI)          │                                  │                         │
  │────────────────────────────>│ refresh lists (signed repos)     │                         │
  │ pveupgrade / apt full-upgrade                                  │                         │
  │────────────────────────────>│ apt-get dist-upgrade (in place)  │                         │
  │                             │ new kernel? → postinst hook ────>│ copy kernels to ESP(s), │
  │                             │                                  │ refresh loader entries  │
  │<── "please consider rebooting" (no health gate, no commit) ────│                         │
  │ reboot ──────────────────────────────────────────────────────────────────────────────────>│
  │   boots OK → done                                                                         │
  │   kernel bad → admin picks an older kernel in the menu, then `proxmox-boot-tool kernel pin`│
  │   bootloader/userland bad → rescue ISO, chroot, grub-install / dpkg --configure -a        │
```

- **Updates are plain apt.** `pveupgrade` is "a small wrapper around apt-get dist-upgrade". It refuses if the package cache is over 3 days old and afterwards only *suggests* a reboot [C-TD-proxmox-ve-013]. Point releases use `apt update && apt full-upgrade` [C-TD-proxmox-ve-014].
- **Rollback covers the kernel only.** `proxmox-boot-tool kernel pin <ver> [--next-boot]` [C-TD-proxmox-ve-015]. apt auto-removal always keeps the running kernel, the two newest, the newest of each older series and the pinned one [C-TD-proxmox-ve-016]. Userland, GRUB and Proxmox packages cannot be rolled back except through ZFS snapshots the admin takes by hand. That route is not productised.
- **Major upgrades** (8 → 9) happen in place via apt, by editing the Debian suite from bookworm to trixie, or by reinstalling and restoring guests from backup. "A valid and tested backup is always required" [C-TD-proxmox-ve-018]. A **2,408-line checker, `pve8to9`**, runs about 30 checks before, during and after. Its bootloader check warns that an unmounted ESP or a missing `grub-efi-amd64` "may leave the system unbootable" [C-TD-proxmox-ve-017].
- **Lifecycle:** a major release lives as long as its Debian release has security support (about 3 years). PVE 8 reached end of life in 2026-08, one month after Debian 12 [C-TD-proxmox-ve-003]. In practice this means **one in-place base jump about every 2 years**: eight since 2008, from Debian 5 to Debian 13.

### 4.1 Real-world failures (all in the bootloader, during the 8 → 9 jump)

| # | Report | What happened | Lesson for OneMind |
|---|---|---|---|
| 1 | forum 178482 (2025-12) [C-TD-proxmox-ve-019] | Dropped to `grub>` after the upgrade. The firmware still booted an old GRUB from the ESP or NVRAM. Recovery took a hand-typed kernel boot and `grub-install`. One user saw it come back after a full power loss | The bootloader is the single point of failure in an in-place upgrade. Keep the first-stage loader tiny and rarely updated, and update it as a separately tested step |
| 2 | forum 176455 (2025-11) [C-TD-proxmox-ve-020] | After removing `systemd-boot` as the checker advised, the host was stuck in a GRUB reboot loop, and the rescue ISO could not find the kernel | Advice delivered as "run this command" is fragile. OneMind's update engine, not the user, must own the bootloader |
| 3 | forum 168662 (9.0 beta) [C-TD-proxmox-ve-021] | A fresh 8 → 9 upgrade in a VM did not boot. Proxmox staff attribute it to a missing `proxmox-boot-tool reinit` when the GRUB/shim update arrived | Multi-ESP sync is hard even for an experienced vendor. RAUC's single-writer A/B model avoids this whole class of failure |

---

## 5. App format and catalogue

| Layer | Format | Trust | Source |
|---|---|---|---|
| Official templates | LXC rootfs tarballs listed in `aplinfo.dat` | Index signed with a detached `.asc`, verified with `sqv` against a shipped keyring. Each download needs a matching sha512 or md5 hash from the signed index | [C-TD-proxmox-ve-022, -023] |
| OCI images (9.1+) | Any OCI archive or registry image becomes an LXC container. It is extracted inside the container's **user namespace**, and Entrypoint/Cmd, User, WorkingDir, Env and StopSignal are mapped into LXC config. Volumes become empty directories only. Application containers are a **tech preview** | No signature check found in this path | [C-TD-proxmox-ve-024, -025] |
| Planned | "Declarative multi-guest application support based on the **Compose Specification**" | Roadmap only | [C-TD-proxmox-ve-026] |
| Community | `community-scripts/ProxmoxVE` (MIT, ~30 k stars, 652 `ct/` scripts): `bash -c "$(curl …)"` one-liners that create an LXC and install an app | **Unsigned curl-to-bash, run as root on the host**, third party | [C-TD-proxmox-ve-027] |

Proxmox has **no first-party app store**. Its largest real app ecosystem is a third-party shell-script collection, which shows the demand for one-click apps (A-1). Proxmox is now moving toward OCI plus Compose. That is the same direction OneMind's W4 portability guard took (Market imports Compose; apps never depend on runtime-specific features [C-DEC-007]).

---

## 6. Identity, AI, backups, security, hardware

| Area | What Proxmox does | Evidence |
|---|---|---|
| **Identity** | Realms: Linux PAM, built-in PVE, LDAP, Active Directory, OpenID Connect. 2FA: TOTP, WebAuthn, YubiKey OTP, recovery keys. Role + ACL-path permissions; API tokens with separate privileges | [C-TD-proxmox-ve-031] |
| **AI features** | **None in the product.** No assistant, MCP server or LLM feature appears in the 9.x notes or roadmap. AI shows up only as a *workload*: NVIDIA vGPU, and PVE as the HA substrate under **NVIDIA Mission Control** (vendor press, 2026-07-28) | [C-TD-proxmox-ve-035, -034] |
| **Backups** | vzdump: stop / suspend / snapshot modes and fleecing. PBS adds deduplicated, incremental, **client-side AES-256-GCM** backups with an RSA-wrapped key. PBS 4.0 shipped 2025-08-06; 4.2 on 2026-04-29 | [C-TD-proxmox-ve-030, -040] |
| **Security** | Secure Boot out of the box since **8.1 (2023-11-23)**: Microsoft-signed shim, Proxmox-signed GRUB and kernels, GRUB only. **No signed shim on arm64 yet**. **No root full-disk encryption in the installer** (a roadmap item). Signed apt repos. Datacenter/node/guest firewall with an nftables backend | [C-TD-proxmox-ve-032, -012, -026, -037, -041] |
| **Hardware** | x86-64. **Official arm64 since 2026-08 only on NVIDIA Grace and Vera**; other UEFI+ACPI ARMv9 machines are best-effort; **Raspberry Pi and other device-tree-only boards are not supported**. Eval minimum 1 GB RAM, recommended 2 GB plus guests; enterprise SSDs with power-loss protection recommended | [C-TD-proxmox-ve-033, -042] |

---

## 7. Licence and business model

- **AGPL-3.0, every feature free.** Proxmox sells **per-CPU-socket subscriptions** that grant the enterprise apt repository and support tickets: Community €120, Basic €370, Standard €550, Premium €1,100 per socket per year. Arm64 needs separate keys, and arm64 support is "upon request" [C-TD-proxmox-ve-036].
- The free `pve-no-subscription` repository is labelled "testing and non-production use" [C-TD-proxmox-ve-037]. **The product's revenue is the stable channel itself**, together with a nag dialog and a 20-year support reputation.
- Subscriptions have existed since 2013. Proxmox also sells training and runs a partner network (vendor-reported) [C-TD-proxmox-ve-038].

---

## 8. Strengths and weaknesses

| Strengths | Weaknesses (for OneMind's purposes) |
|---|---|
| 20 years and eight Debian base jumps shipped, with a documented checker each time [C-TD-proxmox-ve-003, -017] | No A/B and no automatic rollback; a bad bootloader update needs a rescue ISO [C-TD-proxmox-ve-019…-021] |
| Debian lifecycle alignment is simple to explain [C-TD-proxmox-ve-003] | The image pipeline is not public, so reproducibility cannot be checked [C-TD-proxmox-ve-008] |
| Secure Boot working on x86 since 2023 [C-TD-proxmox-ve-032] | No root FDE; no Secure Boot on arm64 [C-TD-proxmox-ve-026, -012] |
| Real HA, clustering and replicated config with no external database [C-TD-proxmox-ve-028, -029] | Admin-centric: no family accounts, no consumer UX, no app store [§5] |
| Signed template index plus hash-checked downloads [C-TD-proxmox-ve-022, -023] | Biggest app ecosystem is unsigned curl-to-bash scripts [C-TD-proxmox-ve-027] |
| Strong backup story (PBS) [C-TD-proxmox-ve-030] | No Pi or Jetson; arm64 is limited to data-centre NVIDIA [C-TD-proxmox-ve-033] |
| Clear open-core-free business: pay for the stable channel and support [C-TD-proxmox-ve-036] | No AI layer [C-TD-proxmox-ve-035] |

---

## 9. What competitors do (with constraint fit)

| Question | Proxmox VE | HAOS | umbrelOS | Constraint fit with OneMind |
|---|---|---|---|---|
| Base OS | Debian 13 + own kernel | Buildroot | Debian 13 | **High** for base choice (same Debian lineage, same 2-year jump cadence) |
| Update model | in-place apt, kernel pin only [C-TD-proxmox-ve-013, -015] | RAUC A/B (commits even if unhealthy [C-W3-025]) | Rugix A/B (commits at daemon start [C-W3-036]) | **Low**: Proxmox targets attended servers with an admin. OneMind targets unattended boxes and robots |
| Major base jump | in place + 2,400-line checker [C-TD-proxmox-ve-017] | new image | new image | **Medium**: copy the checker idea; deliver the jump as an A/B image |
| App format | LXC templates, OCI→LXC, Compose planned [C-TD-proxmox-ve-024, -026] | Supervisor add-ons | Compose apps | **Medium**: confirms the Compose/OCI import direction |
| Kubernetes | none (VMs/LXC) | none | none | **Low**: the Tier A k3s choice is not tested by Proxmox |
| Hardware | x86 + Grace/Vera, no Pi [C-TD-proxmox-ve-033] | Pi, x86, Green/Yellow | Pi 5, x86, Umbrel Home | **Low** at the edge, **medium** for the Omni/Cluster GPU tier |
| Team / scale | ~20-year company, global partner network (SECONDARY) [C-TD-proxmox-ve-038] | foundation + Nabu Casa | startup | **Low**: OneMind is one developer (M-6) |
| Robotics | none | none | none | none |

---

## 10. Constraint-fit summary

Proxmox is a **server virtualisation platform for administrators**. Its constraints differ from OneMind's: data-centre x86 and NVIDIA Grace hardware, no Kubernetes, a human at the console for updates, no robots, a large team. Its patterns are therefore **candidates, not defaults** (mission §2.2). The exceptions match OneMind's constraints closely: the **Debian lifecycle**, the **base-jump checker**, the **kernel-retention rule** and the **free-features / paid-stable-channel business model**.

---

## 11. What OneMind copies, and what it does better

| ID | Recommendation | Type | Serves |
|---|---|---|---|
| REC-PVE-01 | Ship a **`onemind-preflight`** checker for every base jump and Kubernetes minor upgrade. It runs before staging a RAUC bundle, refuses on known-bad states (ESP not writable, unsupported apps, low disk) and prints fixes. Same idea as `pve8to9` [C-TD-proxmox-ve-017] | Copy (pattern) | R-1, R-3, M-6 |
| REC-PVE-02 | **Retain at least one previous kernel and bootloader** in the inactive slot and the ESP, never auto-removed, like Proxmox's keep rule [C-TD-proxmox-ve-016]. RAUC slots give this for free; keep it as a release-contract test | Copy | R-1, R-3 |
| REC-PVE-03 | Keep the **1 GiB ESP** decided in 01 §4.3. Proxmox uses 1024 MB on large disks "for multiple kernels/UKIs" [C-TD-proxmox-ve-009], which is independent confirmation | Confirms Tier A | R-3, F-7 |
| REC-PVE-04 | **Signed Market index plus a per-artifact digest**, the Proxmox `aplinfo.dat` + `.asc` + sha512 pattern [C-TD-proxmox-ve-022, -023], applied to Helm/OCI digests. Never offer curl-to-bash as the install path [C-TD-proxmox-ve-027] | Copy + better | A-1, A-5, A-6, F-5, U-4 |
| REC-PVE-05 | **Import OCI images and Compose files** into the Market, with untrusted image config parsed in a sandbox (Proxmox extracts in a user namespace and rejects control characters [C-TD-proxmox-ve-024]) | Copy (pattern) | A-1, A-2, A-3 |
| REC-PVE-06 | **Do better on updates:** A/B with a fresh-signal health gate and automatic rollback (01 §1), so none of the three §4.1 failures needs a rescue USB | Better | R-1, F-3, F-14 |
| REC-PVE-07 | **Do better on encryption:** LUKS2 data from first boot (01 §4.3). Proxmox still lists root FDE as future work [C-TD-proxmox-ve-026] | Better | M-2, U-4 |
| REC-PVE-08 | **Lifecycle statement per SKU** in Proxmox's plain form: "supported at least as long as Debian N has security support, plus the overlap to N+1" [C-TD-proxmox-ve-003]. Feeds the CRA support-period decision (00 §4 item 6) | Copy | R-2, R-3 |
| REC-PVE-09 | **Business model reference:** all features free; revenue from a stable/LTS channel, support and boxes [C-TD-proxmox-ve-036]. This fits D-001 Apache-2.0 open core without gating features. Input to W16 | Candidate | H-1, H-4, M-8 |
| REC-PVE-10 | **Coexist, don't compete, at the hypervisor layer:** publish the P4 VM appliance (qcow2) with a tested Proxmox import, so homelab users can try OneMind inside PVE (01 §4.4) | Better (reach) | P-7, F-8 |
| REC-PVE-11 | **AI layer is open ground:** Proxmox has no AI/MCP surface [C-TD-proxmox-ve-035]. OneMind's MCP + human-approval gateway is a real differentiator against the most-used self-hosted infrastructure product | Better | AI-1, AI-2, AI-4, AI-5 |
| REC-PVE-12 | **Multi-node view without a cluster network**, as Proxmox Datacenter Manager does [C-TD-proxmox-ve-040], for UX-6 multi-box management over NATS/Tailscale | Candidate | UX-6, UX-7 |

---

## 12. Does Proxmox challenge any Tier A decision in 01?

| Tier A decision | Challenge from Proxmox | Verdict |
|---|---|---|
| **Debian 13 core** | Supports it. A 20-year vendor ships Debian 13 as an appliance base on Debian's ~3-year cadence [C-TD-proxmox-ve-001, -003] | **Upheld** (adds evidence) |
| **RAUC A/B** | The strongest counter-example: a successful product with **no A/B**, using in-place apt, a kernel pin and an upgrade checker for 20 years [C-TD-proxmox-ve-013, -015, -017]. **But** it targets attended servers, and its own forum shows bootloader breakage that needed a rescue ISO [C-TD-proxmox-ve-019…-021] | **Upheld.** Does not flip: Proxmox's constraint (admin present) does not match unattended boxes and robots (R-1, F-3). It does mean a **"package mode" developer install (P6)** is a legitimate, proven pattern for servers, which 01 already allows as a developer preview |
| **k3s on ≥ 4 GB + SSD; NATS leaves below** | Proxmox runs clusters with no Kubernetes, and HA from SQLite + Corosync in 1–2 GB [C-TD-proxmox-ve-028, -033]. That suggests a lighter config plane is possible | **Not flipped.** OneMind's app and GPU ecosystem needs Kubernetes (N-9, F-2). Note the pmxcfs pattern as prior art if a "Lite without k3s" profile is ever reopened |
| **restic + online SQLite backup** | PBS is a stronger, image-level, deduplicating backup system [C-TD-proxmox-ve-030], but AGPL and VM-centric | **Upheld**. PBS is a candidate *target* for users who already run it, not a replacement |
| **Secure Boot later; 1 GiB ESP; LUKS2 data** | Proxmox needed until 8.1 (late 2023) for Secure Boot and still has **no signed arm64 shim** [C-TD-proxmox-ve-032, -012]. Getting a Microsoft-signed shim is a long-lead item, especially for arm64 | **Weakens the timeline, not the decision.** Add a dated task to start shim review early, and plan arm64 Secure Boot as vendor-dependent (Pi and Jetson have their own chains) |
| **Jetson on L4T Ubuntu 24.04; Pi 5 via Raspberry Pi's kernel** | Proxmox's arm64 port, built with NVIDIA, chose **UEFI+ACPI servers only** and explicitly excludes device-tree boards such as the Pi [C-TD-proxmox-ve-033] | **Upheld.** It shows the alternative (one generic arm64 image) does not reach Pi and Jetson even for a large vendor working with NVIDIA. Per-board flavors remain necessary |
| **Ubuntu/RKE2 GPU-server flavor (Omni/Cluster)** | NVIDIA now validates and partners with a **Debian-based** platform for Grace/Vera and Mission Control [C-TD-proxmox-ve-034] | **New evidence for Debian on the GPU-server tier** (SECONDARY, vendor press). Worth a row in the W2/W4 refuter set: Debian may be viable on NVIDIA data-centre arm64 without Canonical's terms |

---

## 13. Open items

- The ISO/squashfs build pipeline is not public [C-TD-proxmox-ve-008]. Image reproducibility is unknown.
- OCI→LXC signature verification: none was found in `restore_oci_archive`. The registry-pull path in `pve-storage` was not read (Tier B depth).
- The Debian-on-Grace evidence is vendor press only. Confirm through NVIDIA's own documentation before using it in a scorecard.
- Install and VM-import of the OneMind P4 appliance on PVE 9 is untested. Add it to `22-HARDWARE-LAB-TEST-PLAN.md` (any x86 box with PVE 9: import qcow2, boot, run an A/B update inside the VM, pass if rollback works).
