# 03 · What This Repo Already Established (Findings Index)

**Purpose:** the starting baseline for the research agent. Everything below was already researched, sourced, or decided in `docs/` and `research/` on 2026-11-10. **Build on it; do not redo it.** Re-verify only (a) items in §3 (UNVERIFIED / SECONDARY / conflicting), (b) anything volatile (prices, versions, "latest" releases), and (c) anything the research mission needs at greater depth.

**How to read this file**
- §1 Verified facts: value + the evidence file that holds the source URL. "Status" uses the evidence file's own label (VERIFIED, read from primary page/repo; SECONDARY, press/blog/search snippet; VENDOR, vendor claim).
- §2 Decisions: founder decisions (final until changed) and ADR-001 (still **PROPOSED**).
- §3 Every open UNVERIFIED / SECONDARY / conflicting item, as a checklist.
- §4 Every spike, open question and next step named anywhere.
- §5 Contradictions between files, with which statement is current.

**File shorthand used below**

| Short | Path |
|---|---|
| REQ | `docs/REQUIREMENTS.md` |
| ARCH | `docs/ARCHITECTURE.md` (v0.1, partly superseded) |
| ADR | `docs/ADR-001-foundation.md` (PROPOSED) |
| DEC | `docs/DECISIONS.md` |
| HW | `docs/HARDWARE.md` |
| APPS | `docs/APPS.md` |
| DASH | `docs/DASHBOARD.md` |
| L01 / L02 | `docs/learning/01-linux-bases.md` / `02-omarchy.md` |
| MHS-APP / NV-APP | `docs/applications/anthropic-mhs-preview.md` / `nvidia-inception.md` |
| BASE | `research/platform/base-os-and-orchestration.md` |
| VUD | `research/platform/verify-ubuntu-vs-debian.md` |
| VK8S | `research/platform/verify-kubernetes-distro.md` |
| VUPD | `research/platform/verify-updates-rollback-backups-security.md` |
| ROBO | `research/platform/robotics-iot-xr-nvidia.md` |
| AINP | `research/platform/ai-native-protocols-and-ux.md` |
| WEB | `research/platform/website-patterns.md` |
| OLA | `research/competitors/olares.md` |
| UMB | `research/competitors/umbrel.md` |
| LAND | `research/competitors/landscape.md` |
| REPOS | `research/competitors/flagged-repos.md` |

All research dates are 2026-11-10 unless stated. Evidence quality caveat stated in BASE and VUPD: some pages were read through a summarizing fetch helper, so exact quotes and figures that matter should be re-opened on the cited page before being quoted externally.

---

## 1. Verified facts table

### 1.1 Base OS lifecycles and licensing

| Fact | Value | Status | Evidence |
|---|---|---|---|
| Debian 13 "trixie" release | 2025-08-09 (13.0); latest point 13.7 on 2026-09-12 | VERIFIED | VUD §1.1 |
| Debian 13 regular security support end | 2028-08-09 | VERIFIED | VUD §1.1, BASE A.9 |
| Debian 13 LTS end (volunteer/company LTS team) | 2030-06-30 | VERIFIED | VUD §1.1 |
| Debian 13 ELTS end (Freexian, paid, only packages customers use) | 2035-06-30 | VERIFIED | VUD §1.1 |
| Debian lifecycle statement | "3 years full + 2 years LTS" | VERIFIED | VUD §1.1 |
| Debian 13 kernel | 6.12 series (6.12.107-1); trixie-backports up to 7.2.x seen | VERIFIED | VUD §1.5 |
| Debian's own NVIDIA driver in trixie | 550.163.01 (branch 550, predates RTX 50/Blackwell) | VERIFIED | VUD §1.2 |
| Debian governance | Debian Constitution (elected DPL, Tech Committee), no single vendor | VERIFIED | VUD §1.8 |
| Debian 13 on Pi 5 (stock Debian kernel) | Not officially supported; unofficial raspi.debian.net says Pi 5 only on Debian 14/sid | VERIFIED (absence + unofficial statement) | VUD §1.3 |
| Raspberry Pi OS base | Debian trixie (announced 2025-10-02) | VERIFIED | VUD §1.3 |
| Ubuntu 24.04 LTS | Released Apr 2024; standard support to May 2029; ESM (Pro) to May 2034; Legacy add-on to May 2039 | VERIFIED | VUD §1.1 |
| Ubuntu 26.04 LTS | Released 2026-04-23; standard May 2031, ESM May 2036, Legacy May 2041 | VERIFIED (kernel 7.0 is SECONDARY) | VUD §1.1 |
| Ubuntu Pro free tier | Personal use only, up to 5 machines (50 for Ubuntu Community members) | VERIFIED | VUD §1.1 |
| Ubuntu Pro commercial list price | Workstation $25/machine/yr; Server $500/machine/yr (no support); 24/7 support tiers $300 / $1,775 / $3,400; Legacy = +50% | VERIFIED | VUD §1.1 |
| Ubuntu Pro for Devices | One-time per-device fee, up to 15 yr ESM; **price not published** | Model VERIFIED / price UNVERIFIED | VUD §1.1, ADR §5 |
| Ubuntu 24.04 kernels | GA 6.8; HWE 6.14, 6.17, 7.0 published in noble-updates | VERIFIED | VUD §1.5 |
| Snap coupling | `ubuntu-server-minimal` hard-Depends on snapd; `ubuntu-server` Recommends it; LXD needs snap; Thunderbird snap-only | VERIFIED | VUD §1.6 |
| Livepatch | Free up to 5 machines personal/evaluation | VERIFIED | VUD §1.5 |
| Ubuntu 24.04 compliance | DISA-STIG and CIS "Achieved" per release-cycle page | VERIFIED | VUD §2 |
| Ubuntu Core 24 / 26 | Core 24: 10 yr + 5 via Pro Legacy; Core 26 released 2026-05-14, standard to May 2036, Legacy to May 2041; Pi 5 support added in Core 24 | VERIFIED | BASE A.7 |
| RHEL 8/9/10 lifecycle | 10 years (5 full + 5 maintenance) + extended life phase | VERIFIED | BASE A.1 |
| Fedora CoreOS updates | Zincati + rpm-ostree; OCI transport (quay.io) accepted for F42; arches x86_64/AArch64/s390x; only Pi 4 guide | VERIFIED | BASE A.1 |
| FCOS ↔ bootc unification | Proposal issue #2214 opened 2026-08-26; WG formed Sep 2026; no decision as of Oct 7 | VERIFIED | BASE A.1 |
| bootc | CNCF Sandbox; OCI image = OS update | VERIFIED | BASE A.1 |
| Talos Linux | v1.14.5 (2026-10-26), Linux 6.18.58, etcd 3.7.3; v1.15.0-beta.0 2026-11-10; MPL-2.0; Omni is BSL 1.1; Enterprise $1,000/node/yr, 10-node minimum, FIPS 140-3 builds | VERIFIED | BASE A.2 |
| Talos SBC overlays | `rpi_generic` (Pi 4/CM4), `rpi5`, `jetson_nano` only; Orin installers are an unmerged PR without GPU support | VERIFIED (see §5 C-17) | BASE A.2 |
| Talos NVIDIA | Extensions `nonfree-kmod-nvidia` + `nvidia-container-toolkit` or OSS modules; drivers 595 (prod) / 580 (LTS); GPU Operator ≥ 26.3.1 with driver/toolkit disabled; GB10 needs `arm64.nobti` | VERIFIED | BASE A.2, VK8S §7 |
| Flatcar | CNCF Incubating (accepted 2024-08-02); Apache-2.0; LTS channel 18 months, new LTS yearly; Pi 4 "early stages"; NVIDIA sysext amd64 | VERIFIED | BASE A.4 |
| Bottlerocket | A/B, TUF, auto rollback; bare-metal K8s variants no longer supported; AWS-centric | VERIFIED | BASE A.5 |
| SUSE SL Micro 6.2 | Released 2025-11-04, EOL 2029-11-30 (SECONDARY); Jetson Orin production support on SL Micro 6.0–6.2 via SolidDriver (2026-03-16) | Mixed | BASE A.6 |
| balenaOS | Yocto, A/B rootfs, auto rollback; supports `raspberrypi5`, Jetson Orin devkits, generic-amd64; Apache-2.0 | VERIFIED | BASE A.8 |
| NixOS 26.05 | Released 2026-05-30, support ends 2026-12-31 (7 months); Pi 5 needs unstable | SECONDARY (search) | BASE A.9 |
| Yocto | Wrynose 6.0 LTS to Apr 2030; Scarthgap 5.0 LTS to Apr 2028 | VERIFIED | BASE A.9 |
| Proxmox VE 9 | Based on Debian 13 | VERIFIED | VUD §1.7 |

### 1.2 Image builders and update engines

| Fact | Value | Status | Evidence |
|---|---|---|---|
| Rugix | v1.4.0 (2026-11-02); **MIT or Apache-2.0**; atomic A/B, delta updates (open source), mandatory signatures by default (CMS), multiple cert roots; Bakery builds Debian/Alpine/Raspberry Pi OS | VERIFIED | VUPD §4, VUD §1.4 |
| Rugix boot flows | grub, uboot, systemd-boot, custom, rauc/mender compat, `rpi-tryboot` (Pi 4+), `rpi-uboot` | VERIFIED (page summarised) | VUPD §4 |
| Rugix commit model | **Does not mark boot good/bad automatically**; integrator must call `rugix-ctrl` (no default dead-man switch) | VERIFIED | VUPD §4 |
| RAUC | v1.15.2 (2026-03-27); LGPL-2.1; x.509 signing via OpenSSL, PKCS#11/HSM; symmetric/asymmetric; grub, barebox, u-boot, EFI; used by HAOS (verity bundles) | VERIFIED | VUPD §5 |
| Mender | Client 5.2.0 (2026-10-23) Apache-2.0; delta/RBAC/mTLS are commercial; Umbrel migrated Mender → Rugix | VERIFIED | VUPD §5 |
| SWUpdate | GPLv2 + OpenSSL exception | VERIFIED | BASE A.9 |
| Kairos | v4.4.0 (2026-10-26); **Apache-2.0** (GitHub API for kairos, kairos-agent, AuroraBoot); CNCF Sandbox; Spectro Cloud | VERIFIED | VUPD §3, ARCH §2 |
| kairos-init | Latest tag v0.17.3 (2026-08-18); distros incl. Debian, Ubuntu, RHEL family, Fedora, Arch, Alpine, openSUSE, Hadron; models generic, rpi3, rpi4, jetson agx-orin / orin-nx (L4T r36.x), jetson-thor (L4T r39.x), dgx-spark; **no rpi5** | VERIFIED | VUD §1.4 |
| Kairos Pi 5 | Docs: "Model 5 is currently not supported because of how we use U-boot" | VERIFIED | VUPD §3 |
| Kairos boot assessment (GRUB) | Good = active image mounted + cloud-init `boot.before`; does not wait for workloads; auto rollback is GRUB-only | VERIFIED | VUPD §3 |
| Kairos upgrades | `kairos-agent upgrade --source oci:...`; system-upgrade-controller **deprecated in Kairos**, replaced by Kairos operator `NodeOpUpgrade` (concurrency, stopOnFailure, canary); no scheduler found | VERIFIED | VUPD §3 |
| Kairos Trusted Boot | FDE + Secure Boot + Measured Boot, UKI signed with own keys, TPM 2.0 for encryption; kernel cmdline fixed | VERIFIED | VUPD §3 |
| Kairos prebuilt flavors | Hadron default; Ubuntu/openSUSE prebuilt repos no longer actively updated | VERIFIED | BASE A.3 |
| Kairos Jetson | AGX Orin, Orin NX (L4T r36.x, Ubuntu 22.04), AGX Thor (L4T r39.2, Ubuntu 24.04 or Hadron); Orin Nano not listed; DGX Spark page exists | VERIFIED | BASE A.3, VUPD §3 |

### 1.3 Competitor OS internals

| Fact | Value | Status | Evidence |
|---|---|---|---|
| HAOS latest | 18.5 (2026-11-06); Apache-2.0 | VERIFIED | VUPD §1 |
| HAOS build | Buildroot, one image per board; EROFS read-only root; GRUB (UEFI), U-Boot (SBCs), Pi 5 tryboot; AppArmor; Docker runs Supervisor | VERIFIED | VUPD §1 |
| HAOS partitions | boot 16–64 MB · kernel0/1 24 MB · system0/1 256 MB EROFS · bootstate 8 MB · overlay 96 MB ext4 · data (rest) | VERIFIED | VUPD §1 |
| HAOS RAUC flow | Writes inactive slot, needs **user reboot**, slot marked good once Supervisor starts; GRUB tries new slot 3× | VERIFIED | VUPD §1 |
| HAOS signing | RAUC keyring, separate dev CA and release CA; verity bundles; `compatible` per board | VERIFIED | VUPD §1 |
| HAOS channels | stable (production), beta (staging), dev | VERIFIED | VUPD §1 |
| HAOS backups | Encrypted by default; SecureTar v3 from 2026.4 (Argon2id, XChaCha20-Poly1305, Trail of Bits audit); recommended daily, keep 3; agents local/NAS/Google Drive/OneDrive/Synology/HA Cloud (5 GB, latest only); 3-2-1 endorsed | VERIFIED | VUPD §1 |
| HAOS SSH | Off by default; Dropbear on 22222 key-only via CONFIG USB | VERIFIED | VUPD §1 |
| HAOS MCP server | Since 2025.2; OAuth 2.0 + PKCE with CIMD; admin-only by default; read-only switch | VERIFIED | AINP §1.7, LAND §1.4 |
| HA Cloud → "Home Assistant Link" | Rename on Dec 2; $6.50/mo or $65/yr | VERIFIED | WEB §1, LAND §1.4 |
| HA Green | $199 / €179; RK3566, 4 GB, 32 GB eMMC; Yellow and Blue discontinued | VERIFIED | LAND §1.4, HW §3 |
| HA core / OS repos | core 2026.11.1 (2026-11-09), 92k stars; OS 7.6k stars | VERIFIED | LAND §1.4 |
| umbrelOS release | 2.0.0 on 2026-09-22; 2.0.1 on 2026-11-01; 2.1.0-beta.1 on 2026-11-03 | VERIFIED | UMB, VUPD §2 |
| umbrelOS base | **Debian 13 trixie** pinned to a snapshot.debian.org date; trixie-backports kernel/firmware on amd64/arm64; Pi image uses Raspberry Pi kernel/firmware/repo; NVIDIA driver from NVIDIA's debian13 repo (595.91.07 pinned) | VERIFIED (Dockerfile/README) | VUD §1.7, UMB §2 |
| umbrelOS image/updates | Rugix Bakery images (amd64 EFI/GRUB, arm64 EFI, Pi 4/5 tryboot); A/B; legacy Mender devices bridged; ZFS pools created `compatibility=openzfs-2.3` so rollback still imports pools | VERIFIED | VUPD §2, UMB §2 |
| umbrelOS release signing | Offline root key (hardware wallet) signs approved-signer list; signers use Secure Enclave P-256 keys; `requiredSignatures`; revocation by manifest hash; hash-pinned bundle; anti-downgrade (`semver.gt`); OpenTimestamps | VERIFIED (code) | VUPD §2 |
| umbrelOS update UX | Never auto-installs; stable + beta channels; auto rollback on failure | VERIFIED (support page summarised) | VUPD §2 |
| umbrelOS Secure Boot | Not used (DKMS modules unsigned) | VERIFIED | VUPD §2 |
| umbrelOS backups | Encrypted, hourly; retention 24h hourly / 1 wk daily / 1 mo weekly / 1 yr monthly; to Umbrel/NAS/USB; destination needs 2× space; Kopia 0.23.1 pinned | VERIFIED | VUPD §2, UMB §1 |
| Umbrel FailSafe | ZFS RAIDZ1 (SSD) / mirrors (HDD); "not a backup"; not on Pi | VERIFIED | VUPD §2, UMB §2 |
| umbreld stack | TypeScript on Node 26.12.1, Express + tRPC, better-sqlite3, dockerode; UI React+Vite+Tailwind+Radix | VERIFIED | UMB §2 |
| Umbrel app runtime | Docker Compose; `umbrel-app.yml` manifest (manifestVersion, storage.dataRoot, folderAccess, permissions [GPU, STORAGE_DOWNLOADS], dependencies/implements, widgets, backupIgnore); images multi-arch, pinned by digest; no Docker socket | VERIFIED | UMB §3 |
| Umbrel MCP | Built into umbreld with `@modelcontextprotocol/server` 2.0.0; bearer tokens hashed, max 20; owner-only; agents act as owner; permissions apps/appStore/files/manageSystem/machines/createMachines; tools registered only if granted; deletion = Trash only, never overwrites | VERIFIED (code + support page) | UMB §2, AINP §1.7 |
| Umbrel Machines | libvirt + KVM/QEMU + noVNC | VERIFIED | UMB |
| Umbrel license | **PolyForm Noncommercial 1.0.0**; License FAQ: cannot sell hardware/hosting/support with it | VERIFIED | UMB §4, VUPD §2 |
| umbrel-apps license | No LICENSE file (treat as unlicensed) | VERIFIED (absence) | UMB §4 |
| Umbrel hardware | Home: Intel N150, 16 GB DDR5, 1/2/4 TB NVMe, 1GbE, Wi-Fi 5. Pro: i3-N300 8-core, 16 GB LPDDR5, 4× NVMe up to 32 TB, 64 GB OS, 2.5GbE, Wi-Fi 6 | VERIFIED | UMB §5, LAND §1.1 |
| Umbrel store feed (Nov 2026) | Home $499 (512 GB) / $599 / $699 / $949 (4 TB). Pro $699 (no SSD) / $999 / $1,299 / $1,899 (8 TB). "Umbrel Protect" $39–99 | VERIFIED (products.json) | LAND §1.1, HW §3 |
| Umbrel company | $3M seed Oct 2021 | VERIFIED (blog) / total $3.4M SECONDARY | UMB §6 |
| Umbrel repo | 12.5k stars | VERIFIED | LAND |
| Olares latest | 1.12.7 (2026-09-24); 1.12.8-rc.1 (2026-11-10); daily 1.12.9-YYYYMMDD | VERIFIED | OLA §0 |
| Olares license | AGPL-3.0 since commit of 2025-08-30, **plus** legacy non-commercial `LICENSE.md` and "other"-licensed sub-repos | VERIFIED (conflict is real) | OLA §7.1, VUPD §6 |
| Olares install base | Ubuntu 22.04–25.04 or Debian 12/13 (script), ISO, Docker Compose; min 4 cores / 8 GB / 150 GB SSD | VERIFIED | OLA §5.4, VUD §1.7 |
| Olares Kubernetes | k3s default (Olares One showed v1.33.3+k3s1); containerd; Calico; KubeSphere fork; HAMi fork for GPU | VERIFIED | OLA §1, VK8S §8 |
| Olares updates | In-place via LarePass app; within-minor only; **no A/B or OS rollback found** | VERIFIED (absence in docs read) | VUPD §6 |
| Olares backups | restic-based; local/Olares Space/S3/COS; app restore only for Wise | VERIFIED | VUPD §6 |
| Olares multi-node | Documented for 2 Olares One units; JuiceFS + MinIO migration; manual multi-step upgrade with CR patch | VERIFIED | OLA §4 |
| Olares app format | OAC = Helm chart + `OlaresManifest.yaml`; linter `framework/oac`; market repo beclab/apps Apache-2.0, 404 folders (marketing "200+") | VERIFIED | OLA §3 |
| Olares agents | Router (AI gateway, 1.12.7), Lares agent with MCP client settings, CLI with 12 compiled-in Agent Skills; **no OS-level MCP server found** | VERIFIED | OLA §6, AINP §1.7 |
| Olares One spec | Core Ultra 9 275HX, RTX 5090 Mobile 24 GB, 96 GB DDR5-5600, 2 TB NVMe, TB5, 2.5GbE, Wi-Fi 7, 330 W, 3.5 L | VERIFIED (vendor spec page) | OLA §5.1 |
| Olares One price | $4,999 on official Shopify store (Nov 2026); Black Friday $300 off from Nov 17; Kickstarter $2,999; raised $2.34M | VERIFIED (store) / see §5 C-9 | OLA §5.2 |
| Olares company | Olares Tech Co., founded 2022, Singapore; ">$100M raised" (self-reported) | VENDOR | OLA §7.2 |
| Olares "Manufacture with Olares" | Contact-sales funnel; no public terms | VERIFIED | OLA §5.3 |
| CasaOS / ZimaOS | CasaOS Apache-2.0, last release v0.4.15 (2024-12-19); ZimaOS Buildroot, no LICENSE, 1.8.0 (2026-10-15) | VERIFIED | LAND §1.3 |
| Zima pricing | ZimaBoard 2 $339/$399; ZimaCube 2 $799/$1,299/$2,499; OCuLink dock $179.90 | VERIFIED (store feed) | LAND §1.3 |
| StartOS | MIT; Rust core; Server One Ryzen 5 6600H; Premium Support $200/yr | VERIFIED | LAND §1.6 |
| Project N.O.M.A.D. | Crosstalk-Solutions/project-nomad, Apache-2.0, 43.1k stars, v1.35.1 (2026-10-05); Ollama+Qdrant, Kiwix, Kolibri, ProtoMaps | VERIFIED | LAND §1.5 |
| ClawBox | Jetson Orin Nano Super, 8 GB, 512 GB, €749 | VENDOR | LAND §1.10 |
| Other licenses | YunoHost AGPL-3.0; Runtipi GPL-3.0; Cosmos Commons Clause; TrueNAS apps LGPL-3.0; Coolify Apache-2.0; Puter AGPL-3.0 | VERIFIED | LAND |
| Unraid pricing | Starter $49, Unleashed $109, Lifetime $249 | VERIFIED | LAND §1.8 |
| TrueNAS | Apps moved k8s → Docker in 24.10; Incus VMs in 25.04 | SECONDARY (search) | LAND §1.8 |

### 1.4 Kubernetes layer

| Fact | Value | Status | Evidence |
|---|---|---|---|
| k3s conformance | CNCF-certified; PRODUCT.yaml for v1.35, v1.36, v1.37 | VERIFIED | VK8S §1 |
| k3s versions | v1.37.2+k3s1, v1.36.6, v1.35.10, v1.34.13 (all 2026-11-03); upstream supports 1.35–1.37, 1.34 EOL 2026-10-27; ~14 months patch support | VERIFIED | VK8S §1 |
| k3s governance | CNCF Sandbox (2020-08-19), vendor SUSE, Apache-2.0, ~34k stars | VERIFIED | VK8S §1 |
| k3s minimums | Server 2 cores/2 GB; agent 1 core/512 MB; x86_64, armhf, arm64; SSD required for etcd on Pi | VERIFIED | VK8S §1 |
| k3s measured | Server+workload ~1.6 GB (x86 and Pi 4B); agent ~270 MB | VERIFIED (k3s v1.26.5 profile) | VK8S §1, BASE B.1 |
| k3s datastore | SQLite default (single server only); embedded etcd HA (odd, 3+); external Postgres/MySQL/etcd | VERIFIED | VK8S §1, §4 |
| k3s sizing | 3× 4 vCPU/8 GB servers ≈ 1,200 agents; join in batches ≤ 50 | VERIFIED | VK8S §4 |
| k3s snapshots | etcd snapshots 00:00 and 12:00, keep 5, optional S3 | VERIFIED | VK8S §5, VUPD §7 |
| k3s rollback | Only by binary downgrade + datastore restore from a snapshot taken on the older minor | VERIFIED | VK8S §5 |
| k3s upgrades | system-upgrade-controller `Plan` CRD; must not skip minors; refuses downgrades | VERIFIED | VK8S §5 |
| k3s hardening | CIS guide; opt-in `secrets-encryption` (aescbc default, secretbox), `protect-kernel-defaults`, PSA config, audit; NodeRestriction + PodSecurity on by default; published self-assessment lags (CIS 1.9 for k3s 1.27–1.29) | VERIFIED | VK8S §6, VUPD §8 |
| k3s + NVIDIA | Auto-detects `nvidia`/`nvidia-cdi` runtimes, ships RuntimeClasses | VERIFIED | VK8S §7 |
| RKE2 | SUSE, Apache-2.0, ~2.4k stars; 4 GB min / 8 GB rec; CIS profile (restricted PSS); FIPS 140-2 (BoringCrypto); SELinux; conformance v1.36 & v1.37; Traefik default from v1.36 | VERIFIED | VK8S §2 |
| ingress-nginx | EOL March 2026 | VERIFIED | VK8S §2, §9 |
| k0s | Conformance v1.35–1.37; CNCF Sandbox; Apache-2.0 code / CC-BY-SA docs | VERIFIED | VK8S §3 |
| MicroK8s | Conformance v1.35, v1.36; **absent from v1.37**; snap-based | VERIFIED | VK8S §3 |
| Upstream limits | 110 pods/node, 5,000 nodes, 150k pods | VERIFIED | VK8S §4 |
| DOKS → k3s portability | Helm/Argo portable; change DO LB annotations → ServiceLB/MetalLB; `do-block-storage` → local-path/Longhorn; ingress-nginx → Traefik; Argo CD 3.6 tested 1.34–1.37 | VERIFIED | VK8S §9, ADR D4 |
| Longhorn | v1.13.0 (2026-09-29), CNCF Incubating, Apache-2.0; 3 nodes, 4 vCPU/4 GiB per node; K8s ≥ 1.34; backups to NFS/SMB/Azure/S3 | VERIFIED | VK8S §10, VUPD §7 |
| Rook-Ceph | CNCF Graduated; needs raw devices; K8s 1.32–1.37 | VERIFIED | VK8S §10 |
| Velero | v1.18.4; FSB uses Kopia, no hostPath, **one static common encryption key** | VERIFIED (page summarised) | VUPD §7 |
| restic | v0.19.1; BSD-2; AES-256-CTR + Poly1305-AES, scrypt | VERIFIED | VUPD §7 |
| KubeEdge | CNCF Graduated (Oct 2024); v1.23.1 (2026-07-15) | VERIFIED | BASE B.1, ROBO §2.3 |
| OpenYurt | CNCF Incubating; v1.7.0 (2026-05-06) | VERIFIED | BASE B.1 |

### 1.5 NVIDIA, robotics, IoT, XR

| Fact | Value | Status | Evidence |
|---|---|---|---|
| GPU Operator OS support | Ubuntu 22.04/24.04/26.04, RHEL/Rocky, RHCOS, SLES; **"Debian" appears 0 times** | VERIFIED | VUD §1.2, BASE B.2 |
| GPU Operator + Jetson | "NVIDIA Jetson, or other embedded products with integrated GPUs, are not supported"; issue #1453 closed as not planned | VERIFIED | VUD §1.2, VK8S §7 |
| GPU Operator versions | 26.7.2 latest listed; K3s support from 26.3.0; DRA driver via `GPUCluster` in 26.7.0 (K8s ≥ 1.34.2, driver ≥ 580); K8s 1.33–1.37 | VERIFIED | BASE B.2 |
| Container Toolkit tested distros | Ubuntu 22.04/24.04/26.04; only Debian 11 (amd64) listed | VERIFIED | VUD §1.2 |
| CUDA 13.5 | Lists Debian 12 and 13 on x86_64 and arm64-sbsa | VERIFIED | VUD §1.2 |
| NVIDIA apt repos | `debian13/x86_64`, `debian13/sbsa`, `ubuntu2404/*`, `ubuntu2604/x86_64` exist (HTTP 200) | VERIFIED | VUD §1.2 |
| k8s-device-plugin | v0.17.1; time-slicing (no memory isolation), MPS experimental, CDI; Tegra needs toolkit ≥ 1.11.0; GFD merged in since v0.15.0 | VERIFIED | BASE B.2, ROBO §5 |
| DRA driver | ComputeDomains supported; GPU kubelet plugin not yet officially supported | VERIFIED | BASE B.2 |
| HAMi / KAI / Dynamo | HAMi CNCF Incubating; KAI Scheduler CNCF Sandbox Apache-2.0 (v0.18.7); Dynamo Apache-2.0 | VERIFIED | BASE B.2, ROBO §2.3 |
| JetPack 7.x | Ubuntu 24.04, kernel 6.8; supports Orin and Thor; 7.2 adds Yocto support and NemoClaw; CUDA 13.0 on Thor | VERIFIED | VUD §1.2, ROBO §1.3 |
| Jetson Linux 38.4 | Does not support Orin family (Thor only) | VERIFIED | ROBO §1.1 |
| DGX OS 7 | Customized Ubuntu (24.04) | VERIFIED | VUD §1.2 |
| Jetson modules | Thor up to 2070 FP4 TFLOPS, 128 GB, 40–130 W; AGX Orin 275 TOPS; Orin NX 157 TOPS; Orin Nano 67 TOPS, 7–25 W | VERIFIED | ROBO §1.1 |
| DGX Spark | GB10 (20-core Arm), 128 GB unified, 1 PFLOP FP4, ConnectX-7, 240 W; DGX OS | VERIFIED | ROBO §1.2 |
| DGX Station | GB300, 748 GB coherent, 1,600 W (20 A circuit); price not listed | VERIFIED | ROBO §1.2 |
| Isaac Sim requirements | x86 Ubuntu 22.04/24.04 or Win 11; min RTX 4080 16 GB, 32 GB RAM; A100/H100 unsupported (no RT cores); aarch64 = DGX Spark only; Jetson not a host | VERIFIED | ROBO §1.4 |
| Isaac Lab | v3.0.0 (2026-10-20), targets Isaac Sim 6.2 | VERIFIED | ROBO §1.4 |
| Isaac ROS | Thor/Orin on JetPack 7.2 (128 GB+ NVMe), x86 Ampere+ Ubuntu 24.04 CUDA 13.2+ driver 595+, DGX Spark; ROS 2 Lyrical; Docker recommended | VERIFIED | ROBO §1.4 |
| GR00T N1.7 | GA 2026-04-18; code Apache-2.0, weights NVIDIA Open Model License; inference 16 GB+ VRAM; ~28 Hz Thor | VERIFIED | ROBO §1.4 |
| Cosmos 3 | Super 64B, Nano 16B, Edge 4B (Jul 2026); license NOASSERTION | VERIFIED | ROBO §1.4 |
| Holoscan | v5.0.0 (2026-10-21), Apache-2.0 | VERIFIED | ROBO §1.4 |
| ROS 2 Lyrical | Released 2026-05-22, LTS to May 2031; Tier 1 Ubuntu 26.04 + Win 11; Ubuntu 24.04 Tier 3, early EOL 2029-06-01 | VERIFIED | ROBO §2.1 |
| ROS 2 Jazzy / Humble / Kilted | Jazzy to May 2029 (Tier 1 Ubuntu 24.04); Humble to May 2027; Kilted EOL Nov 2026 | VERIFIED | ROBO §2.1 |
| rmw_zenoh | Router required (multicast off); Humble can't talk to newer; no interop with zenoh-plugin-ros2dds | VERIFIED | ROBO §2.2 |
| PX4 / ArduPilot / MAVSDK | PX4 v1.17.0 (BSD-3); ArduPilot Plane-4.7.2 (GPL-3.0); MAVSDK v4.1.0 | VERIFIED | ROBO §2.4 |
| PX4 uXRCE-DDS | "unauthenticated ... DDS network must be kept isolated" | VERIFIED | ROBO §2.4 |
| MAVLink | MAVLink 2 signing, up to 255 systems, MIT for XML/C | VERIFIED | ROBO §2.4 |
| Open-RMF | Humble, Jazzy, Kilted, Rolling; amd64/aarch64 | VERIFIED | ROBO §2.3 |
| Matter / Thread / HA | HA is Matter controller only; connectedhomeip v1.6.1.0; ot-br-posix v2026.11.0; Matter needs IPv6 + mDNS | VERIFIED | ROBO §3 |
| Zigbee2MQTT / Z-Wave JS UI / ESPHome / ChirpStack | 2.14.3 GPL-3.0 / v11.26.2 MIT / 2026.10.2 / v4.20.0 MIT | VERIFIED | ROBO §3 |
| Meshtastic | Firmware v2.7.26 GPL-3.0; MQTT topics; ATAK plugin 1.1.42 GPL-3.0 (231-byte packets, 56 KB file cap) | VERIFIED | ROBO §3 |
| Reticulum | 1.6.0 (2026-11-07); license NOASSERTION | VERIFIED | ROBO §3 |
| Headscale | v0.29.7 (BSD-3); single tailnet scope | VERIFIED | ROBO §7 |
| NATS | Server v2.15.2 (2026-10-26); leaf dials out to hub; JetStream on a leaf needs its own domain | VERIFIED | ROBO §7 |
| Node Feature Discovery | v0.20.1 Apache-2.0 | VERIFIED | ROBO §5 |
| k3s join token | `K10<sha256(CA)>::<creds>`; bootstrap tokens default 24 h TTL | VERIFIED | ROBO §4 |
| Matter QR | `MT:` base-38; 27-bit passcode; 11-digit manual code | Mixed (Silicon Labs page + search) | ROBO §4 |
| WebXR | W3C CR Snapshot 2022-03-31; HTTPS only; experimental per MDN | VERIFIED | ROBO §6 |
| OpenXR | v1.1; runtimes incl. Android XR, Quest, Monado, SteamVR; Vision Pro not listed | VERIFIED | ROBO §6 |
| Galaxy XR | Launched 2025-10-21 at $1,799 | SECONDARY | ROBO §6 |

### 1.6 Hardware prices (volatile; re-check before any purchase)

| Item | Value | Status | Evidence |
|---|---|---|---|
| Raspberry Pi 5 16 GB | $305 board | VERIFIED (Pi product page) | ROBO §1.5, HW |
| Jetson Orin Nano Super Dev Kit | $399 (up from $249, July 2026) | SECONDARY (Hardware Busters; not on NVIDIA store) | ROBO §1.5 |
| Jetson AGX Orin Dev Kit | $3,499 (from $1,999) | SECONDARY | ROBO §1.5 |
| Jetson AGX Thor Dev Kit | $5,499 (from $3,499) | SECONDARY | ROBO §1.5 |
| AGX Orin 32GB module | $1,799 (from $899) | SECONDARY | ROBO §1.5 |
| DGX Spark Founders Edition | $4,699 (from $3,999, Feb 2026) | SECONDARY (Tom's Hardware) | ROBO §1.5 |
| Umbrel Home / Pro, Olares One, HA Green, Zima | see §1.3 | | |

### 1.7 AI-native protocols, identity, alerts, integrations

| Fact | Value | Status | Evidence |
|---|---|---|---|
| MCP current spec | **2026-07-28** (previous 2025-11-25): stateless, no `initialize`, no `Mcp-Session-Id`, `server/discover`, tasks → extension, MRTR replaces sampling/elicitation-as-requests, HTTP+SSE and DCR deprecated, CIMD preferred | VERIFIED | AINP §1.1 |
| MCP transports | stdio and Streamable HTTP | VERIFIED | AINP §1.2 |
| MCP auth | OAuth 2.1 resource server; RFC 9728 mandatory; RFC 8707 resource param; no token passthrough | VERIFIED | AINP §1.3 |
| MCP Registry | Preview; no private servers; not designed for self-hosting | VERIFIED | AINP §1.4 |
| MCP extensions | MCP Apps (`ui://`, Stable); Tasks (Beta); Skills over MCP (Beta); Server Cards (Beta) | VERIFIED | AINP §1.5 |
| MCP governance | Donated to Agentic AI Foundation (Linux Foundation) 2025-12-09; Apache-2.0 code/spec | VERIFIED | AINP §1.6 |
| MHS (Model Hardware Standard) | Anthropic research preview announced 2026-08-27; drivers + device reference files incl. safety limits; MCP/CLI/code access; Raspberry Pi and LeRobot among partners; open-source planned, no date; no public spec | VERIFIED | AINP §3, MHS-APP |
| A2A | v1.0 stable; LF; ACP (IBM) merged into A2A | VERIFIED (AAIF move SECONDARY) | AINP §2 |
| Agent Sandbox | kubernetes-sigs; CRDs Sandbox/Template/Claim/WarmPool; isolation via gVisor/Kata RuntimeClass | VERIFIED | AINP §2 |
| Backstage MCP Actions | Actions Registry → MCP tools at `/api/mcp-actions/v1`; hints read-only/idempotent/destructive; OAuth+CIMD | VERIFIED | AINP §1.7 |
| Dashboard licenses | Homepage GPL-3.0; Glance AGPL-3.0; Homarr Apache-2.0; Heimdall MIT; Dashy MIT + advertising clause; Organizr GPL-3.0 | VERIFIED | AINP §5 |
| Push on iOS | Self-hosted ntfy needs an upstream relay (APNs/Firebase poll_request carrying only message ID + topic hash); Android fully self-hostable | VERIFIED | AINP §6 |
| IdP licenses | Authentik MIT core + EE; Kanidm MPL-2.0; LLDAP GPL-3.0; Zitadel AGPL-3.0 | VERIFIED | AINP §7 |
| Jellyfin parental model | Rating ceiling, tag allow/block, access schedule, per-library, device approval | VERIFIED | AINP §7 |
| Strava API Policy (eff. 2026-06-01) | Bars using Strava data in any AI application, even with consent; Strava MCP is sole authorized agent interface, personal use | VERIFIED (section numbers SECONDARY) | AINP §8.2 |
| Nango / OpenBao | Nango Elastic License; OpenBao MPL-2.0 | VERIFIED | AINP §8.1 |
| EU Cyber Resilience Act | In force 2024-12-10; vulnerability reporting from 2026-09-11; main obligations from 2027-12-11 | VERIFIED (page summarised) | VUPD §8, ADR D6 |
| Pi secure boot | Customer RSA-2048 key hash in OTP; BCM2712 signs EEPROM bootloader; optional LUKS with OTP secret | VERIFIED | VUPD §8 |
| Jetson secure boot | PKC hash in write-once fuses, irreversible; UEFI Secure Boot can't be disabled without reflash | VERIFIED (page summarised) | VUPD §8 |
| Omarchy | MIT; 46.7k stars; v4.5.0 (2026-11-05); Arch + Hyprland + Quickshell; plugin validator; Omacom Foundation $23.65M pledged (self-reported) | VERIFIED (GitHub API) / VENDOR | L02, AINP §9 |
| Flagged repos | rea MIT (449.5k stars, rea-agents 6.8.0); craft-anything Apache-2.0 per API, README says MIT OR Apache-2.0 (26k stars, v0.6.0, early alpha); bla MIT (4.9k stars, v3.2.3) | VERIFIED (API); star counts unexplained | REPOS |

### 1.8 Website stacks of reference companies

| Company | Marketing / docs / store / community | Evidence |
|---|---|---|
| Umbrel | Next.js on Vercel / support pages / Shopify / Discourse; PostHog | WEB §1, UMB §7 |
| Olares | Vue SPA on Cloudflare / VitePress 1.6.4 / Shopify / Discourse; WordPress blog | WEB §1, OLA §8 |
| Home Assistant | Jekyll on Cloudflare + Plausible; Nabu Casa Astro; dev docs Astro | WEB §1 |
| Zima | Nuxt / Shopify (affiliate page) / Discourse | WEB §1 |
| Start9 | Angular + Express; own store; Discourse | WEB §1 |
| System76 | BigCommerce + HubSpot; Astro Starlight support docs | WEB §1 |
| Framework | Turbo/Rails-style (Rails inferred); Zendesk (moderate confidence) | WEB §1 |
| Circle.so | **Not used by any reference company found** | WEB §1 |

### 1.9 Founder-owned assets (described, not identified)
- Existing DigitalOcean Kubernetes (DOKS) cluster with Argo CD GitOps, NATS JetStream (established subject doctrine), Authentik IdP, Tailscale, TAK Server + CloudTAK (public at onemindos.dev), Hermes agents, onemind-core (Python/FastAPI), onemind-mcp, Backstage, Obsidian vault + Todoist (REQ §12). Details of endpoints/credentials deliberately not recorded here.
- Test hardware on hand (DEC D-004, HW §1): Mac (model unconfirmed), Android phone (model not recorded in HW), Beelink U55 (CPU disputed, see §5 C-39), Dell Latitude 5540 (i5-1345U, 16 GB, user-reported), DigitalOcean cloud access.
- Prior planning set on an external drive; the Blueprint is canonical (REQ §12).

---

## 2. Decisions made

### 2.1 Founder decisions (DEC, all dated 2026-11-10, final until changed)

| ID | Decision | Key points |
|---|---|---|
| **D-001** | License: **open core, Apache-2.0** | Apache-2.0 for core OS, SDK, `onemind.app.yaml` format, CLI, capability gateway. Revenue: hardware, support plans, pro/enterprise features, OEM program, education (Circle), later optional cloud. Brand, Market, signed updates, certified hardware stay under OneMind control. **Guardrail:** never copy code from PolyForm-NC (Umbrel), AGPL (Olares, Glance), GPL (Homepage) or unlicensed (umbrel-apps). **Still to decide:** which features are pro/closed (ADR before first paid feature). |
| **D-002** | Tiers: **build all together, one design** | One image pipeline, many profiles (Edge/Pi, Lite/mini PC, Pro/GPU, Robotics/Jetson, Omni/sim, Cluster). One app layer; NodeCapabilities decides placement. Release readiness per tier, design unified. Bake-off must test x86, ARM (Pi) and Jetson from the start. |
| **D-003** | Apps: **one unified app shell with modules, all scaffolded** | Each module is also a standalone Market app with its own manifest. Scaffold all now; build depth by daily use (see APPS). |
| **D-004** | Test hardware: **use what exists, buy in phases** | Mac, Android phone, Beelink U55, Dell 5540, DigitalOcean. Jetson and the rest per HW phased list. Box design from competitor specs. |
| **D-005** | iOS alerts: **APNs carrying minimal data only** | Payload is an opaque/encrypted "new alert" signal; app fetches content from the user's own box. Android/desktop/web fully self-hosted (ntfy/UnifiedPush/in-app). |
| **D-006** | Apply to **NVIDIA Inception** and **Anthropic MHS preview** | Drafts in `docs/applications/`; founder submits himself. |

### 2.2 ADR-001 Foundation: status **PROPOSED, awaiting founder approval**
Evidence files E1 VUD, E2 VK8S, E3 VUPD, E4 UMB, E5 OLA, E6 HAOS contributor docs. Explicitly supersedes ARCH v0.1's Ubuntu 24.04 + Kairos recommendation.

| ADR point | Content |
|---|---|
| Lessons (§1) | HAOS and Umbrel both ship their own read-only image with A/B + automatic rollback, keep user data separate, never self-update. Olares (installs on a normal distro) has no OS rollback. Only Olares uses Kubernetes (k3s). |
| **D1** Ship own image | Flashed image (USB/SD/NVMe) even on BYO hardware; a script installer on existing Linux is **developer mode only**. |
| **D2** Base | **Debian 13 trixie** for the core image (pinned snapshot); **NVIDIA L4T / Ubuntu 24.04 flavor for Jetson/DGX only**. Rationale: Umbrel precedent, no per-device fee, no snapd, community governance; NVIDIA ships Jetson/DGX only on Ubuntu-based L4T. Cost accepted: two flavors. GPU risk: GPU Operator doesn't list Debian → use NVIDIA host driver (debian13 repo) + Container Toolkit + k8s device plugin; spike early. |
| **D3** Updates | A/B image, signed, user-controlled. **Tool: Rugix** (alt: RAUC). Kairos dropped as lead (Pi 5 unsupported, commits on cloud-init, Trusted Boot docs contradict) but kept as candidate for Jetson/DGX flavor and Trusted Boot reference. **Mark good only after k3s + core platform pods healthy.** Signing copies Umbrel (offline root, online signers, hash-pinned bundle, revocation list, anti-downgrade). UX: never auto-install/auto-reboot; stable/beta; one-click; automatic pre-update backup. Layers update separately: OS image · k3s (never skip a minor) · apps · firmware. |
| **D4** Kubernetes | **k3s on every tier; RKE2 for hardened enterprise/public-safety tier.** DOKS apps convert with three changes (LB annotations → ServiceLB/MetalLB; `do-block-storage` → local-path/Longhorn; ingress-nginx → Traefik). |
| **D5** Storage/backups | Disk layout boot · OS-A · OS-B · overlay · DATA. local-path single box; Longhorn 3+ nodes; optional ZFS mirror/RAIDZ ("not a backup"). Back up: k3s datastore (etcd-snapshot 2×/day keep 5, S3 optional; SQLite coverage UNVERIFIED), app volumes via **restic** (not Velero FSB), OneMind config/identity/secrets as separately encrypted recovery kit. Encrypted by default, hourly/daily retention, destinations box/NAS/USB/S3, pre-update snapshot, restore tests surfaced as "last verified restore". |
| **D6** Security | Day 1: read-only root, signed A/B, AppArmor, k3s CIS hardening (secrets encryption, PSA, netpols, audit), no default SSH password, per-app isolation, capability gateway. Phase 2: Secure Boot + TPM 2.0 + LUKS on x86 (Kairos Trusted Boot as reference), Pi OTP secure boot, Jetson fuse secure boot (irreversible; OneMind-built hardware only). Plan CRA compliance (SBOMs, CVE handling, support periods). |
| §4 Spikes 1–7 | See §4.1 below. |
| §5 Open items | SUSE k3s support lifecycle · RKE2 rollback docs · SQLite snapshot coverage · Longhorn backup encryption · GPU Operator on Debian · Jetson A/B method · Ubuntu Pro for Devices pricing. |

### 2.3 Other recorded choices (proposals, not founder-ratified)
- ARCH: don't fork Umbrel (PolyForm NC) or Olares (AGPL + license ambiguity); copy patterns, reuse permissive parts. Layer model 1–7 + Node layer + Physical layer; capability layer driven by `onemind.app.yaml`; single capability gateway (OIDC; OAuth 2.1 + RFC 9728/8707 for MCP); agents act as a specific user with limited grants (intersection model).
- ARCH §8: Helm + `onemind.app.yaml`, images pinned by digest; Git-repo market + HA-style quality tiers; build own dashboard, study Homarr; Alertmanager + in-app center + ntfy/UnifiedPush; Authentik for clusters, evaluate Kanidm for boxes; OpenBao/Infisical; per-provider `aiPolicy`; KubeVirt/libvirt; Agent Sandbox + gVisor/Kata; website Astro + Starlight + Shopify + Circle.so + Discourse + Zoho Forms; bundle N.O.M.A.D.-style offline pack.
- ARCH §2 and L01/L02: Omarchy desktop edition later, as a **client**, not the box base; Fedora CoreOS/bootc "revisit 2027".
- APPS §C build order: (1) shell + system apps, (2) Projects & Tasks + Knowledge, (3) IoT & Home + Situational Awareness, (4) Wellness, Family, Finance, (5) Mesh, Robotics & Drones, OSINT, Infrastructure, Education.
- DASH: Simple (household) vs Pro (operator) modes; in cluster mode Argo CD stays GitOps engine, App Controller writes `OneMindApp` resources Argo can own.
- AINP: MCP is the only agent protocol needed in v1; A2A only for opaque peer agents; Hermes keeps NATS internally. Don't build on MHS until a spec exists.
- WEB: Astro + Starlight, Shopify, Discourse, Circle.so, Zoho Forms/Desk, Plausible, Cloudflare, agent-readable `.well-known` files.
- REPOS: use rea as pre-release red-team tool and distribution-pattern reference; craft-anything as study only; bla optional for closed components.

---

## 3. UNVERIFIED / SECONDARY / conflicting items (checklist)

Tick an item only after opening a primary source; record the URL and date in your output.

### 3.1 ADR / decisions dependencies (highest priority)
- [ ] GPU Operator on Debian with host-installed driver (`driver.enabled=false`) — not in any NVIDIA matrix (ADR D2, VUD §3)
- [ ] Jetson A/B update method: Kairos vs NVIDIA's own vs RAUC vs Rugix (Rugix Jetson support UNVERIFIED; no jetson/tegra in repo) (ADR §4.6, VUPD §4)
- [ ] k3s single-node SQLite datastore backup coverage by `etcd-snapshot` (ADR D5, VUPD §7)
- [ ] In-place SQLite → embedded etcd migration on k3s (VK8S §4)
- [ ] SUSE formal k3s support lifecycle / EOL per minor (ADR §5, VK8S open 1)
- [ ] RKE2 rollback doc (guessed URL 404) and FIPS 140-3 status (VK8S §2)
- [ ] Longhorn backup encryption (VUPD §7)
- [ ] Ubuntu Pro for Devices price (unpublished, "contact us") (VUD §1.1)
- [ ] Rugix on Ubuntu base (VUD §1.4); Rugix native signing config page returned 404 (VUPD §4)
- [ ] How umbreld commits a Rugix slot (VUPD §2)
- [ ] Debian userspace on Jetson L4T r36/r39; how Kairos builds its Jetson models (VUD §3)
- [ ] Debian 13 on Pi 5 with Debian's own kernel today (only unofficial 2026-01-28 statement) (VUD §3)
- [ ] Kairos Trusted Boot boot assessment: two docs disagree (VUPD §3)
- [ ] Kairos scheduling feature for user-timed upgrades (VUPD §3)
- [ ] Kairos kubeadm provider existence (VK8S open 4)
- [ ] Consumer GeForce/RTX 40/50 in GPU Operator matrix (lists RTX PRO / A-series only) (BASE B.2, HW)
- [ ] Footnote "4" markers on RKE2/k0s columns of GPU Operator page (VK8S §7)
- [ ] Thor GPU Operator viability via Kairos-linked guide (not opened) (BASE B.2)
- [ ] NFD / GFD labeling of Jetson integrated GPU on JetPack 7 (ROBO §5)
- [ ] NATS leaf + JetStream outage buffering / store-and-forward (ROBO §7, ARCH §5)

### 3.2 Base OS / orchestration (BASE)
- [ ] Fedora CoreOS Jetson and NVIDIA story; Fedora IoT ~13-month support; Fedora IoT Pi 5 (community only, search); Fedora IoT provisioning style
- [ ] bootc rollback; RHEL image-mode specifics (403); RHEL/CentOS Stream bootc license terms
- [ ] Talos rollback/A-B specifics; Talos Omni edge mode docs; CM5 not in Image Factory (secondary)
- [ ] Kairos production adopters
- [ ] Flatcar update-failure fallback wording; arm64 general support; Microsoft/Kinvolk lineage
- [ ] SUSE SL Micro transactional update details, rollback, Pi 5, pricing/license; SL Micro EOL date (secondary)
- [ ] Ubuntu Core Jetson guide contents, rollback mechanics
- [ ] balenaOS NVIDIA story; balena QR/provisioning-key flow (ROBO §4)
- [ ] NixOS 26.05 dates and Pi 5 status (search only); jetpack-nixos
- [ ] Debian stable arches/Pi 5/Jetson/non-free/preseed rows in BASE table (superseded partly by VUD)
- [ ] Omarchy arch support/Pi/NVIDIA; Arch+Hyprland "UNVERIFIED on those pages"; Btrfs+Snapper/Limine and hooks model (secondary, instagit); learn.omacom.io not fetched; learn.omarchy.org DNS failure
- [ ] SWUpdate A/B support
- [ ] StartOS base (Debian packaging dirs suggest Debian) and arches; also L01 lists StartOS base UNVERIFIED
- [ ] ZimaOS updater = RAUC (inferred only); ZimaOS license
- [ ] Docker/Compose footprint (not researched); Podman CDI; kubeadm footprint/arm64 packages; k0s join/edge; MicroK8s edge, HA, arm64, reason for v1.37 absence; KubeEdge/OpenYurt footprints and GPU fit; KubeEdge offline autonomy (docs 404)
- [ ] HAMi memory/core-limit mechanics
- [ ] JetPack 6.1 community k3s + device plugin pattern (user report)
- [ ] "Plain k3s agents keep running pods when control plane is unreachable" (general K8s behavior, unsourced)

### 3.3 Ubuntu vs Debian (VUD)
- [ ] wiki.debian.org/LTS (JS challenge)
- [ ] Ubuntu 26.04 kernel 7.0 (secondary, cnx-software)
- [ ] Official Canonical snapd removal doc; community criticism of Pro-gated universe fixes (opinion)
- [ ] Debian livepatch absence (inferred)

### 3.4 Kubernetes (VK8S)
- [ ] Exact k3s API-surface diffs beyond conformance
- [ ] Pi 5 named in k3s docs; Pi 5 in Talos SBC page text
- [ ] OpenEBS replicated and Ceph hardware minimums; Ceph RBD snapshots/mirroring
- [ ] local-path backups via Velero/restic (not in docs read)
- [ ] NATS JetStream and Authentik Helm portability DOKS → k3s
- [ ] Whether any OneMind chart depends on ingress-nginx
- [ ] Independent third-party CIS certification of k3s (only self-assessment)

### 3.5 Updates / backups / security (VUPD)
- [ ] HAOS Secure Boot / TPM / disk encryption (not found)
- [ ] HAOS auto-install of OS updates (none found, not exhaustive)
- [ ] Umbrel: manual rollback path, root FS read-only status, TPM use, app sandboxing model, beta-program page (search only), SMB restore-at-onboarding failure (single community report), FailSafe on Pi 5 thread (search only)
- [ ] Umbrel / Olares license scope for OneMind (counsel)
- [ ] Mender signing; mender-server license
- [ ] Kopia and borg features; borg license clause count
- [ ] Kairos OCI image signing; Kairos revocation doc contents
- [ ] Olares OS-level signing, rollback, root FS, Secure Boot; Olares cross-minor upgrade statement vs 1.12.x release notes
- [ ] Pi: no TPM (not stated); Jetson fTPM and disk-encryption pages
- [ ] SBOM format (SPDX vs CycloneDX) per CISA; CVE tooling (Trivy, Grype, OSV) not opened
- [ ] EU CRA legal read for OneMind boxes (and update/SBOM duties detail)
- [ ] Feasibility of automated restore tests (no compared product does it)

### 3.6 Robotics / IoT / XR / NVIDIA (ROBO)
- [ ] Jetson GPU/CPU core counts
- [ ] GPU Operator Jetson docs (404 in ROBO; resolved as unsupported by VUD/VK8S — see §5 C-20)
- [ ] Isaac Lab VRAM/RAM table; jetson-containers isaac-sim package
- [ ] Holoscan Jetson/IGX support; DeepStream version/platforms/license; NIM Jetson support and free-dev terms; Omniverse
- [ ] All Jetson/DGX price changes (secondary; NVIDIA store not confirmed; CNX 403); DGX Spark price-change forum thread (title only)
- [ ] NVIDIA-Certified Systems for Jetson OEMs; Jetson partner/OEM module resale terms
- [ ] Inception "preferred pricing" scope; no Jetson-specific discount listed
- [ ] rmw_zenoh tier in Lyrical (docs.ros.org Anubis block); default RMW post (title only); Zenoh ↔ PX4 uXRCE-DDS interplay
- [ ] Open-RMF Lyrical support; other fleet managers
- [ ] KAI Scheduler usage details
- [ ] ROS 2 on Kubernetes reference architecture (none found; patterns are PROPOSAL)
- [ ] Generic ROS 2 ↔ NATS bridge (none found)
- [ ] NATS MQTT bridge in server
- [ ] TAK/ATAK path for vehicles (not researched)
- [ ] HA ZHA / Z-Wave integrations; ESPHome Native API/Improv behavior; ChirpStack MQTT integration specifics
- [ ] Greenhouse/ag controller best practice (PROPOSAL only)
- [ ] Matter spec §5.1 (payload details from Silicon Labs + search); DPP role details
- [ ] NFD feature-source list / NodeFeatureRule CRD (docs 404); GFD full label list
- [ ] Olares and Umbrel GPU/hardware detection mechanics; inxi/lshw/hwinfo
- [ ] Vision Pro WebXR immersive-ar status 2026 (secondary); visionOS 27 Web Environments; Quest WebXR details
- [ ] Xreal Aura price/ship date (reports conflict $1,099 / $1,279 / <$1,500)
- [ ] VR-TAK currency (2020–2021 sources); any TAK XR/AR mode; 3D CoT rendering
- [ ] Headscale DERP/relay fallback; batman-adv BATMAN_V
- [ ] Whether OneMind can act as a Matter bridge
- [ ] Safety/failsafe contract (PROPOSAL, no source)

### 3.7 AI-native / UX (AINP)
- [ ] Authentik support for CIMD and RFC 8707 resource indicators
- [ ] Umbrel MCP "7 read-only tools default, 38 granted" (secondary; review page 404) — UMB lists tools from code
- [ ] Olares MCP server anywhere (none found at OS level)
- [ ] OpenAI Apps SDK UI ↔ MCP Apps relation
- [ ] MHS auth/authz/audit requirements (secondary summaries); "Device Context Protocol" arXiv paper and huzjie/hardmesh (search only)
- [ ] A2A move into AAIF (Axios, secondary)
- [ ] SSH-for-agents as a pattern
- [ ] Homarr service auto-discovery; Homarr code quality / plugin extensibility (build vs fork)
- [ ] Organizr maintenance state
- [ ] UnifiedPush iOS; Gotify iOS
- [ ] Umbrel kid-specific controls; Home Assistant roles beyond admin; Nextcloud user isolation
- [ ] Authelia license/OIDC; Keycloak (not opened)
- [ ] Composio-style brokers (not opened); Infisical license
- [ ] Strava section numbering (secondary blog); Garmin/Oura/Google Health AI terms (secondary only)
- [ ] Obsidian developer policies page (missing at fetch); VS Code scanning/signing/workspace trust; Omarchy "explicit enablement after install" (secondary)

### 3.8 Website (WEB)
- [ ] Circle.so SSO, custom domain, paywall/membership, API
- [ ] Zoho Forms/Desk capabilities and pricing vs HubSpot/Zendesk
- [ ] Any competitor affiliate network beyond Zima's page
- [ ] Framework CMS (Rails inferred); Olares marketing framework (Vue inferred); HA community Discourse (inferred)
- [ ] Agent-readable formats beyond what rea.tools headers show

### 3.9 Competitors (OLA, UMB, LAND, REPOS)
- [ ] Olares: Intel fork purpose; current data plane Envoy vs Linkerd; OPA use; "Terminus" rename history; Olares Zero; general Linux multi-node guide (not read); custom-domain Olares ID guide (not read); OAC `spec.accelerator` vs `spec.resources[]` transition; paid apps details; upstream dependency license compatibility (KubeSphere fork, Padloc, Seafile, MinIO, Infisical); custom market source privilege limits; `vercel.json` hosting inference; PromptQuorum review claims; "Save 95%" / "fastest" claims; craft repos product intent; Jetson support (none mentioned); Studio details
- [ ] Olares market apps not found by folder name: Scira, SurfSense, Void, Suna, OWL, AgenticSeek, OpenManus, Agent TARS, Activepieces, Knative, Browser Use, standalone Prometheus
- [ ] Umbrel: current Home/Pro prices on umbrel.com (page shows "From" only) vs store feed; Pro launch price/date (snippets); manufacturer; founders/CTO (search); Framer staging mechanism; "no hosted relay"; "no paid cloud tier"; "open-from-Mac" wording; earlier Home seller
- [ ] Landscape: Umbrel remote methods beyond Tailscale; Olares Market count (LAND) vs OLA; CasaOS multi-user; HA total app ecosystem count; N.O.M.A.D. creator identity and business model; Start9 catalog size and package format; YunoHost catalog/SSO/business model; DIY DGX Spark $3–5k (low-quality aggregator); TrueNAS release-note claims (search); Olares multi-node join in UI; absence claims for robotics/TAK/mesh/XR/MCP-registry are "not found", not proof
- [ ] Flagged repos: organic vs inflated star counts; craft-anything license (API vs README); legality of clean-room study of competitor UIs; BLA AV/false-positive risk; BLA effectiveness claims (self-reported); rea "Build RL environments" and `touhou` topic

### 3.10 Docs-level unconfirmed items
- [ ] Beelink U55 CPU (i3-5005U per most sources vs one N100 claim) — run `lscpu` (HW §1)
- [ ] Mac model (Apple silicon assumed) and Android phone model (HW §1)
- [ ] Dell 5540 spec is user-reported (HW §1)
- [ ] Accessory prices (Pi NVMe HAT, PSU, case), Zigbee/Thread dongle, Meshtastic radios, RTX box, RTX PRO 6000 / DGX Station prices — not priced (HW §2)
- [ ] L01 video claims summarized, not re-verified
- [ ] NVIDIA Inception contact form under maintenance on 2026-11-10 (NV-APP)
- [ ] MHS waitlist form fields unknown (MHS-APP)

---

## 4. Spikes, open questions and next steps listed anywhere

### 4.1 ADR-001 spikes (prove on real hardware before approval)
1. Debian 13 + Rugix A/B + k3s on the Dell 5540 and Beelink U55: install, update, forced-failure rollback, data survives.
2. "Healthy before commit": slot uncommitted until k3s + core pods ready; broken update rolls back.
3. Single-node k3s datastore (SQLite) backup/restore + restic app-volume restore onto a clean box.
4. Pi 5 with Raspberry Pi kernel on Debian + Rugix (Umbrel's path).
5. RTX (cloud GPU or later box): NVIDIA `debian13` driver + Container Toolkit + device plugin on k3s.
6. Jetson flavor: L4T + k3s + device plugin; choose A/B method (Kairos vs NVIDIA's own vs RAUC).
7. Convert a copy of one DOKS app (Helm/Argo) to k3s with the three D4 changes.

### 4.2 VUPD §10.6 spikes
1. RAUC or Rugix on Jetson Orin: L4T UEFI boot flow, rollback by corrupting new slot.
2. Pi 5 tryboot A/B with k3s: commit gate end to end.
3. k3s single-node datastore backup (SQLite vs embedded etcd) + `etcd-snapshot` restore test.
4. Velero vs restic/Kopia direct with restore drill; confirm Longhorn backup encryption.
5. Kairos Trusted Boot assessment behavior (docs conflict).
6. Umbrel and Olares license scope.

### 4.3 ARCH §9 "Next 30 days" (partly superseded by ADR; bake-off stack changed)
- Weeks 1–2 bake-off: ~~Kairos + Ubuntu 24.04 + k3s~~ vs ~~Ubuntu 24.04 + Rugix~~ vs Talos, on x86 mini PC, RTX, Pi 5, Jetson; measure install time, idle RAM (Pi 5), GPU Operator on consumer RTX, Jetson device-plugin + CDI, A/B rollback, user-timed updates, NATS leaf outage buffering; output ADR-001 (now written, PROPOSED). **Current form = ADR §4 spikes.**
- Weeks 3–4 capability layer v0 on existing cluster: `onemind.app.yaml` schema v0 + linter; registration controller (tile, health/alert, MCP tool generation); capability gateway via Authentik with agent grants + audit; Dashboard v0 (apps, health, alerts, Git-market install, phone PWA); demo: install app → dashboard tile → alert fires → Hermes uses it via MCP with scoped grant.

### 4.4 ARCH §10 founder questions (all marked decided 2026-11-10)
1. License → D-001. 2. First edition to ship → D-002 says build all together; *which tier ships first is still open in practice* (see §5 C-24). 3. First internal app → D-003 + APPS build order. 4. Bake-off hardware → D-004. 5. iOS APNs → D-005. 6. MHS + Inception → D-006.

### 4.5 ARCH §11 top risks (with mitigations)
K8s complexity for a sole dev · Kairos maturity (now moot under ADR) · Jetson outside GPU Operator · hardware price volatility (Jetson/DGX +18–101% in 2026) · cloud API terms (Strava, health APIs) · scope explosion.

### 4.6 BASE C.3 next steps
1. Kairos: license (now resolved Apache-2.0), Pi 5 status (resolved: unsupported), update-timing controls, k3s + NVIDIA on RTX and Orin. 2. GPU Operator on consumer RTX under K3s. 3. Measure idle k3s RAM/CPU on Pi 5. 4. Talos Omni edge and upgrade/rollback docs.

### 4.7 VUD §3 open gaps / §4 recommendation caveat
Open gaps as in §3.3/§3.1. Recommendation caveat: if NVIDIA-vendor support outranks licensing cost, flip to Ubuntu 24.04 → 26.04 and budget Pro for Devices.

### 4.8 VK8S open items 1–8
SUSE k3s lifecycle · RKE2 rollback + FIPS 140-3 · Pi 5 explicit support (k3s, Talos) · Kairos kubeadm provider · OpenEBS/Ceph minimums · MicroK8s HA/arm64 + v1.37 absence · SQLite → etcd migration · ingress-nginx dependencies in OneMind charts.

### 4.9 ROBO open verification items
Jetson GPU Operator/NFD on JetPack 7 · NATS leaf outage buffering · rmw_zenoh tier in Lyrical · Open-RMF on Lyrical · DeepStream/NIM on Jetson licensing · NVIDIA Jetson OEM/partner terms · visionOS immersive-ar · Olares and Umbrel detection mechanics. Plus PROPOSALs to validate: OneMind Join QR flow; NodeCapabilities schema; robot gateway (ROS ↔ NATS); mesh-gateway (Meshtastic MQTT ↔ NATS, CoT ↔ TAK Server); homestead topology (batman-adv + Headscale + NATS leaf + LoRa fallback); WebXR digital-twin serving; safety contract.

### 4.10 AINP §10.3 open questions
Authentik CIMD/RFC 8707 · build vs fork Homarr · iOS push stance (decided by D-005, implementation open) · fitness API legal review · MHS open-source/auth monitoring · Olares MCP and Umbrel real tool list (Umbrel list now in UMB §2).

### 4.11 WEB §3 open questions
Circle.so capabilities · Zoho Forms/Desk vs HubSpot/Zendesk · affiliate networks · Framework CMS · Olares marketing framework.

### 4.12 OLA §9.4 / UMB / LAND / REPOS next steps
- Olares: per-component license review by counsel before relying on any code; verify how far a custom Market source can go (OneMind as an OAC chart on Olares boxes).
- Umbrel: decide whether to adopt Umbrel-compatible manifests (licensing of umbrel-apps first).
- LAND §3: table stakes by launch = multi-user, MCP server with revocable per-agent tokens, GPU, VMs, one-click agent apps, remote access without port forwarding.
- REPOS: run rea against OneMind releases/firmware as red team before shipping hardware; review any `npx ... setup` before running.

### 4.13 REQ open questions
1. MHS → resolved (Anthropic Model Hardware Standard). 2. k8s everywhere vs hybrid → ADR D4 says k3s everywhere (PROPOSED). 3. License → D-001. 4. First hardware tier + first customer segment → partially (D-002); **first customer segment not decided anywhere**. 5. First internal app → D-003/APPS. **REQ change log not updated to reflect these.**

### 4.14 DEC / APPS / HW / applications pending actions
- D-001: write the open-core boundary ADR (which features are pro) before the first paid feature.
- APPS §D: per-module scaffold (`apps/<module>/onemind.app.yaml`, README, capability list with effect + approval, NATS subjects, export format) — none created yet; APPS says "no code yet".
- HW: buy Pi 5 16 GB + NVMe HAT + PSU + case and Jetson Orin Nano Super now (bake-off); later N150/N300 reference Lite box, Zigbee/Thread dongle + 2 Meshtastic radios, RTX 16–24 GB box or DGX Spark, AGX Orin/Thor; apply to Inception before buying NVIDIA hardware; certification tests, warranty/support terms and OEM model before any hardware sale.
- NV-APP: needs public landing page, incorporation details, funding status, pitch deck (offered, not built).
- MHS-APP: fill company name/website/business email placeholders; submit via waitlist.
- DASH: implement screens 1–9 and acceptance flows (install app, update OS, restore, add robot, kid account).
- AI-6 biometrics: "not designed yet" (ARCH §12).
- Omarchy: copy agent skills for plugins and crash → agent flow first (L02).

---

## 5. Contradictions between files (and which is current)

| # | Topic | File A says | File B says | Current / resolution |
|---|---|---|---|---|
| C-1 | **Base OS** | ARCH §1, §2, §3 L1, §7 profile table, §9; L01 §4; L02 split diagram; BASE C.2: **Ubuntu 24.04 LTS** | ADR D2, VUD §4: **Debian 13 trixie** core + Ubuntu 24.04/L4T only for Jetson/DGX | **ADR-001 is current** (ARCH carries a supersession banner; ADR "wins where they conflict"). But ADR is **PROPOSED**, and ARCH body, L01, L02 were never edited. L01 §6 Q4 "what pushes OneMind from Debian to Ubuntu" is now backwards. |
| C-2 | **Image/update tool** | ARCH §2, §9, §11; BASE C.2; L01 §4: **Kairos lead** (fallback Rugix/Talos) | ADR D3, VUPD §10.1: **Rugix lead, RAUC alternative**, Kairos dropped as lead (Pi 5 unsupported; commits at cloud-init) | **ADR current.** Kairos survives only as a Jetson/DGX candidate and Trusted Boot reference. |
| C-3 | Kairos license | BASE A.3: **UNVERIFIED** | ARCH §2 "Apache-2.0 verified"; VUPD §3 Apache-2.0 (GitHub API) | **Apache-2.0** (BASE is older). |
| C-4 | Kairos Pi 5 | BASE A.3: "not in current docs (Pi 3/4 only, search)"; ARCH: "Pi 5 not in its docs" | VUPD §3 explicit "Model 5 is currently not supported because of how we use U-boot"; VUD kairos-init no rpi5 model | **Unsupported** (VUPD). Consistent, VUPD is the stronger source. |
| C-5 | Kairos upgrade controller | ADR D3: k3s layer via "system-upgrade-controller / Kairos-style operator" | VUPD §3: SUC **deprecated in Kairos**, replaced by `NodeOpUpgrade` | Not a true conflict: SUC remains the k3s-documented mechanism (VK8S §5); deprecation applies inside Kairos only. Clarify in ADR. |
| C-6 | Kairos Orin base | BASE A.3: Orin NX/AGX Orin images on L4T r36 (Ubuntu 22.04) | VUD/ROBO: JetPack 7 = Ubuntu 24.04 supporting Orin and Thor; ROBO: Jetson Linux 38.4 excludes Orin | Unresolved: which L4T/JetPack line Orin uses under JetPack 7.x, and whether Kairos Orin images lag. **Verify.** |
| C-7 | **Umbrel Home price** | UMB §5: **launch $399** (N100, 16 GB, 2 TB, Feb 13 2024; community post); snippets $429 (2024), $699/$949 | LAND §1.1 + HW §3: store feed **$499 (512 GB) – $949 (4 TB)**; LAND also: "launched at $699 in 2023 per press" | **Current = store feed $499–$949 (Nov 2026)**. $399 was the 2024 launch price of the N100 model; current Home is N150. The "$699 in 2023" press figure (search snippet, likely the first-gen Home) conflicts with UMB's Feb 2024 launch date; treat as history, verify if needed. |
| C-8 | Umbrel Pro price | UMB §5: launch "$699" (snippets), current UNVERIFIED | LAND/HW: feed $699 (no SSD) – $1,899 (8 TB) | **Store feed current.** |
| C-9 | **Olares One price** | OLA §0/§5.2, LAND, HW, ARCH: **$4,999** Shopify store (published 2026-04-01) | ROBO tier table: conflicting **$2,999 / $3,999 / $4,999**; LAND: $2,899 early, $2,999 Kickstarter, $3,999 MSRP, VIP $2,799; ARCH "prices conflict" | **Current list price $4,999** on the official store (Nov 2026), with a $300 Black Friday discount from Nov 17. Lower figures are historical/Kickstarter/promo. |
| C-10 | Olares One SSD | Olares spec page: PCIe 4.0 | Olares FAQ: preinstalled SSD in PCIe 5.0 slot, PCIe 4.0 slot free | Vendor docs conflict (OLA §5.1). Unresolved. |
| C-11 | **Olares license** | LAND, ARCH §2, D-001 guardrail: **AGPL-3.0** | ADR §1, VUPD §6, OLA §7.1: AGPL **and** non-commercial `LICENSE.md` + "other"-licensed sub-repos | **Both are present in the repo** → treat as not freely reusable until counsel clarifies. D-001's "never copy AGPL code" makes the question moot for code reuse. |
| C-12 | Olares base OS | VUPD §9 table: "Debian-based K8s distro on K3s (OS image details not read)" | OLA, VUD, LAND: installs on Ubuntu 22.04–25.04 or Debian 12/13 (+ ISO) | **Installer-on-top model** (OLA/VUD). VUPD wording is loose. |
| C-13 | Olares Kubernetes distro | BASE A.10: "exact K8s distro not stated on page" | OLA §1.1, VK8S §8: **k3s default** (verified in repo) | **k3s.** |
| C-14 | Olares MCP | AINP §1.7: no MCP mention found; LAND: "MCP n/v" | OLA §6: Lares has Settings > MCP to connect app MCP servers; no OS-level MCP server | **No OS-level MCP server; Lares is an MCP client.** |
| C-15 | Olares GPU | Olares architecture doc: nvshare, one GPU per node | Olares GPU doc + repo: HAMi fork, time/memory slice/exclusive | **HAMi current**; architecture doc stale (OLA §1.1). |
| C-16 | **Umbrel update engine on amd64** | VUD §1.7: "Rugix on Pi, **Mender on amd64**"; VUD §1.4 "Rugix (Pi) plus Mender (amd64)" | UMB §2, VUPD §2, L01: Rugix Bakery builds amd64/arm64/Pi; Mender only for **legacy** devices (bridged to Rugix) | **Rugix on all current images; Mender legacy only.** VUD wording is outdated/misread; re-check `packages/os/README.md`. |
| C-17 | Umbrel base OS evidence | BASE A.10 + LAND §1.1: Debian claim **secondary/UNVERIFIED** (cnx-software) | VUD §1.7, UMB §2: **VERIFIED** from `umbrelos.Dockerfile` | **Verified Debian 13 trixie.** |
| C-18 | Umbrel app count | UMB: 397 dirs; README "over 300" | LAND: 406 top-level entries | Both are raw counts incl. non-app entries; use "300–400". |
| C-19 | Umbrel MCP tool list | LAND §4.5: "Umbrel docs fetched give no tool list"; AINP: secondary "7/38 tools" | UMB §2: full tool list read from `modules/mcp/` code | **UMB (code) current.** Secondary 7/38 figure unverified. |
| C-20 | GPU Operator on Jetson | ROBO §1.3: "UNVERIFIED (its docs URL 404'd)" | VUD §1.2, VK8S §7, BASE B.2: VERIFIED not supported (platform-support page quote; issue #1453 not planned) | **Not supported.** |
| C-21 | Talos Pi 5 | BASE A.2: `rpi5` overlay in official overlays list | VK8S §3: Pi 5 "not listed in page text: UNVERIFIED"; VK8S recommendation says "Pi 5 not shown in its SBC list" | Overlay repo lists `rpi5`; docs page text didn't. **Overlay exists; official support level unverified.** |
| C-22 | HAOS A/B | BASE A.10: "A/B not stated on page" | VUPD §1, L01, ADR: RAUC A/B verified from contributor docs | **A/B verified.** |
| C-23 | **Tier naming / mapping** | REQ P-5: editions "Lite, Pro, Super/Omni" | ARCH §7, HW §4, D-002: Edge (Pi) / Lite (N150 mini PC) / Pro (GPU) / Robotics (Jetson) / Omni / Cluster. ROBO tier table: **Lite = Pi 5**, **Edge = Jetson Orin Nano** | **ARCH/HW/D-002 naming current.** ROBO table predates and uses different labels. "Super" from REQ is folded into Omni. |
| C-24 | First edition to ship | ARCH §10 Q2 asks "Lite or Pro first?" | D-002: build all together; release per tier when acceptance tests pass | Design question decided; **which tier ships first commercially is still open**, as is first customer segment (REQ OQ4). |
| C-25 | Kubernetes on small nodes | ARCH §2: k3s "runs from a Pi (2 GB server / 512 MB agent)" | VK8S per-tier: ~1.6 GB measured; "4 GB practical floor" (judgment) for the OneMind stack | Both true; **plan 4 GB as practical floor** for full OneMind stack; 2 GB is the docs minimum only. |
| C-26 | REQ open question 2 (k8s vs hybrid Docker) | REQ OQ2: "to be decided" | ADR D4: k3s on every tier | Decided in ADR (PROPOSED); OLA lesson notes "do not require Kubernetes on small edge devices unless you must"; REQ not updated. |
| C-27 | Ubuntu Core 24 support end | BASE A.7: Core 24 (Jun 2024) 10 yr security maintenance (≈2034) + 5 Legacy | VUD §2: "Ubuntu Core 24 supported until 2036 per Canonical's Pi page" | **Conflict.** Re-check Canonical's support-duration page; probably 2034 standard / 2039 Legacy, while 2036 matches Core 26 standard (May 2036). |
| C-28 | Omarchy repo owner | BASE, AINP: `github.com/basecamp/omarchy` | L02: `omacom/omarchy` (MIT, 46.7k, v4.5.0) | Likely transferred to omacom; **L02 (GitHub API) is newer**. Verify redirect. |
| C-29 | Omarchy base | BASE A.9: Arch/Hyprland "UNVERIFIED on those pages" | L02: stated from repo and reviews | L02 current; minor. |
| C-30 | StartOS base | L01 table: UNVERIFIED | BASE A.10: `debian/` + `apt/` dirs suggest Debian (not confirmed) | Still unconfirmed. |
| C-31 | Ubuntu LTS support length | BASE C.2: "standard Ubuntu LTS length not fetched" | VUD/ADR: standard May 2029, ESM May 2034, Legacy May 2039; L01 "5 yrs (up to 15 with Pro)" | **VUD current.** Note L01 understates the commercial cost (Pro free tier is personal-use only). |
| C-32 | Backup engine | ADR D5: restic, *not* Velero FSB | ARCH §5: mirroring via "NATS mirroring plus Velero/restic snapshot replication" | **ADR current** (restic; Velero only with separately encrypted storage, per VUPD §10.4). |
| C-33 | GPU stack on x86 | ARCH §3 L2, §6, NV-APP: "GPU Operator (x86)" | ADR D2: GPU Operator not validated on Debian → host driver + toolkit + device plugin | **ADR current** for the Debian core; GPU Operator only if validated by spike 5 (or on Ubuntu/RKE2 enterprise nodes). NV-APP draft still says JetPack image + GPU Operator; fine for an application but not the plan of record. |
| C-34 | Jetson flavor in NV-APP | NV-APP: "JetPack 7.x (Ubuntu 24.04) based OneMind image" | ADR D2: same | Consistent. |
| C-35 | DGX Spark price | ROBO/HW: $4,699 FE (secondary) | LAND §1.10: DIY posts "$3,000–5,000" (low quality) | **$4,699** (post Feb 2026 hike) is the better-sourced figure; still secondary. |
| C-36 | Isaac ROS distro vs upstream | ROBO §1.4: Isaac ROS targets ROS 2 Lyrical on JetPack 7.2 (Ubuntu 24.04) | ROBO §2.1: Lyrical Tier 1 is Ubuntu 26.04; 24.04 is Tier 3 | Real tension, resolved by design: **run ROS in containers decoupled from host** (ARCH §6). |
| C-37 | Kairos Trusted Boot assessment | `boot_assessment.md`: not yet implemented | `boot_assessment_trusted_boot.md`: entries marked good at `multi-user.target`, 3 retries | Kairos's own docs conflict (VUPD §3). Unresolved. |
| C-38 | craft-anything license | GitHub API: Apache-2.0 | README badge: MIT OR Apache-2.0 (both LICENSE files present) | Likely dual; verify LICENSE files. |
| C-39 | Beelink U55 CPU | Most sources: i3-5005U (2 cores, 2015) | One source: N100 | **Unresolved; run `lscpu`.** HW calls it below Olares minimum in either case. |
| C-40 | Umbrel Home CPU | UMB launch (2024): N100 | Current pages/feed: N150 | Both true at different times; current is **N150**. |

---

**Bottom line for the research agent:** The foundation question has a sourced, *proposed* answer (ADR-001: own read-only image, Debian 13 core + NVIDIA L4T/Ubuntu Jetson flavor, Rugix A/B with health-gated commit, k3s everywhere + RKE2 hardened tier, restic backups, phased Secure Boot). Your job is to stress-test it, close the §3.1 items and the ADR spikes with evidence, fix the stale documents listed in §5 C-1/C-2, and extend the plan where these files are thin (5–10 year horizon, robotics/drone OS layer, hardware program, supply chain, regulation, and the existing cluster as proof of concept).
