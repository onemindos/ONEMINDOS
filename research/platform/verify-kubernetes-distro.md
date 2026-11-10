# Verification: Kubernetes distribution for OneMind OS

Date: 2026-11-10. Method: pages and APIs opened on 2026-11-10 (docs.k3s.io, docs.rke2.io, docs.k0sproject.io, docs.siderolabs.com, kubernetes.io, GitHub via `gh api`, cncf/k8s-conformance, cncf/landscape, NVIDIA, Longhorn, Rook, OpenEBS, MetalLB, Argo CD, DigitalOcean docs). Anything not opened or not stated by a source is marked **UNVERIFIED**. Source IDs [S#] map to the Sources list at the end.

## Recommendation (short)

1. **Default distribution for every tier: k3s.** It is CNCF-conformant, Apache-2.0, single binary, 2 GB server / 512 MB agent minimum, x86_64 + arm64 + armhf, embedded-etcd HA, built-in automated upgrades and S3 snapshots. Olares (closest comparable product) ships it as default [S25].
2. **Enterprise / public-safety / regulated tier: RKE2** (same SUSE family, same upgrade and snapshot tooling, CIS/FIPS/SELinux focus). Needs 4 GB RAM minimum (8 GB recommended), so it is not for the 2 GB boxes.
3. **Keep the product Kubernetes-neutral:** Helm + Argo CD + standard StorageClass/Ingress/LoadBalancer abstractions only, so the same app catalog runs on k3s, RKE2 and DOKS. Treat k3s-only features (`HelmChart` CRD, `/manifests` auto-deploy, kine/SQLite) as implementation details of the appliance, not of apps.
4. **Not recommended as the base:** kubeadm (you build everything), MicroK8s (snap/Canonical-tied, dropped from the v1.37 conformance listing [S9]), Talos (excellent but replaces the OS; MPL-2.0; Pi 5 not shown in its SBC list [S16]), k0s (good, CNCF sandbox, but smaller ecosystem for GPU/appliance recipes).

## 1. k3s

| Question | Finding | Source |
|---|---|---|
| CNCF certified? | Yes. Official docs FAQ: "K3s is a CNCF-certified Kubernetes distribution". k3s has a PRODUCT.yaml (vendor SUSE, type distribution) in cncf/k8s-conformance for v1.35, v1.36 and v1.37 (v1.37.0+k3s1). | [S2][S9] |
| Same API as upstream? | README: "fully conformant"; changes are packaging and bundled add-ons, not API changes. The conformance suite passing is the evidence. Exact API-surface diffs beyond that: UNVERIFIED. | [S1][S9] |
| What k3s replaces / adds | Single binary; sqlite3 default datastore via **kine** (etcd3, MySQL, Postgres also available); containerd + runc; Flannel CNI; CoreDNS; Metrics Server; Traefik ingress; Klipper/ServiceLB; kube-router netpol controller; Helm-controller; local-path-provisioner; websocket tunnel so worker kubelet ports need not be exposed. README: "These technologies can be disabled or swapped out". | [S1][S3] |
| Can each be disabled? | `--disable=traefik`, `--disable=servicelb`, `--disable=local-storage`, `--disable=coredns`, `--disable=metrics-server` (packaged AddOns); `--disable-network-policy`, `--disable-helm-controller`, `--disable-kube-proxy`, `--disable-cloud-controller`, `--disable-scheduler`; `--flannel-backend=none` for custom CNI (Cilium/Calico); embedded etcd replaces SQLite via `--cluster-init`; external DB via `--datastore-endpoint`. Disabled AddOns are actively uninstalled. | [S4][S5][S6] |
| Datastore | SQLite default, **cannot be used with multiple servers**. Embedded etcd for HA, or external PostgreSQL/MySQL/etcd. | [S7] |
| Minimum requirements | Server 2 cores / 2 GB; agent 1 core / 512 MB. Archs: x86_64, armhf, arm64. SSD recommended; on Pi/ARM use external SSD because etcd is write-heavy and SD/eMMC cannot handle it. | [S8] |
| Measured usage | Resource profiling (Intel 8375C): server with workload 6% of a core, 1596 MB (SQLite) / 1606 MB (embedded etcd); agent 3% core, 275 MB. Pi 4B: server with workload 30% core, 1588 / 1613 MB; agent 10% core, 268 MB. Baseline excludes the real workload. | [S10] |
| Pi specifics | Standard Raspberry Pi OS needs cgroups enabled (`cgroup_memory=1 cgroup_enable=memory`). Embedded-etcd HA warns of problems on SD cards. | [S8][S11] |
| Versions now | Latest GitHub releases (2026-11-03): v1.37.2+k3s1, v1.36.6+k3s1, v1.35.10+k3s1, v1.34.13+k3s1. Upstream Kubernetes supports 1.37, 1.36, 1.35 (1.34 EOL 2026-10-27); ~14 months patch support per minor. | [S12][S13] |
| Cadence | CNCF landscape entry: "Roughly every 3-4 months, shortly after each upstream Kubernetes minor release." Observed: parallel patch releases on 4 minors on the same day. SUSE's formal k3s support lifecycle: UNVERIFIED. | [S14][S12] |
| Governance / license | CNCF **sandbox** project, accepted 2020-08-19; originated at Rancher, vendor SUSE (conformance PRODUCT.yaml contact is a suse.com address). License Apache-2.0. | [S14][S9][S12] |

## 2. RKE2

| Topic | Finding | Source |
|---|---|---|
| What it is | SUSE Rancher's Kubernetes distribution "focused on enabling Federal government compliance-based use cases"; a.k.a. RKE Government. Inherits k3s's usability and deployment model plus close alignment with upstream (k3s diverges more for edge). Control plane runs as static pods managed by kubelet; containerd runtime. | [S9][S15] |
| Security focus | Defaults and options that pass CIS Kubernetes Benchmark v1.12/v1.11 "with minimal operator intervention"; "hardened by default" but some items (host sysctls, `profile: cis`) need manual steps; FIPS 140-2 via Go BoringCrypto builds; trivy CVE scans in build pipeline. FIPS 140-3: UNVERIFIED (docs opened say 140-2). | [S15][S17] |
| PSA | With `profile: cis` RKE2 enforces `restricted` Pod Security Standard (exempting kube-system etc.); without profile the default config is privileged/unrestricted. | [S18] |
| SELinux | Enforcing mode supported where default (SLES/RHEL family) with `rke2-selinux` policy and `selinux: true`. | [S19] |
| Datastore | Embedded etcd only for snapshots; `datastore-endpoint` flagged experimental in backup docs (so: etcd-centred, no SQLite). | [S20] |
| Resources | 4 GB RAM minimum (8 GB recommended), 2 CPU minimum (4 recommended). x86_64 and arm64. Sizing table: 2 CPU/4 GB: 0-225 agents; 4/8: 226-450; 8/16: 451-1300; 16+/32: 1300+. | [S21] |
| Defaults | Canal default CNI (Cilium, Calico, Flannel bundled). ingress-nginx EOL March 2026; Traefik default for new clusters from v1.36. | [S22][S23] |
| Governance / license | SUSE; Apache-2.0; GitHub 2.4k stars vs k3s 34k. In conformance list for v1.36 and v1.37 (not v1.35 listing). | [S9][S12] |
| When recommended | Docs position it for datacenter and heightened-security sectors; k3s for edge/IoT/ARM/air-gapped/low-resource (k3s docs intro). | [S15][S1] |
| Rollback doc | UNVERIFIED (guessed page URL 404). Assume same constraint as k3s: restore from etcd snapshot. |  |

## 3. Brief comparison of alternatives

| Distro | Conformance (cncf/k8s-conformance) | Footprint (docs) | HA | arm64 / edge | Governance / license | Notes |
|---|---|---|---|---|---|---|
| k3s | v1.35, v1.36, v1.37 | 2 GB server / 512 MB agent | embedded etcd (3+) or external DB | x86_64, arm64, armhf | CNCF sandbox, SUSE, Apache-2.0 | Best fit for tiers 1-4 |
| RKE2 | v1.36, v1.37 | 4 GB min / 8 GB rec. | embedded etcd, 3 servers recommended | x86_64, arm64 | SUSE, Apache-2.0 | Compliance tier |
| k0s | v1.35, v1.36, v1.37 | controller 1 GB/1 vCPU, worker 0.5 GB (stated minimum); measured controller ~0.5 GB, worker ~1.3 GB | multi-controller + load balancer, etcd co-located default; two-node control plane called HA in their docs | x86-64, ARM64, ARMv7, RISC-V | CNCF sandbox (landscape); GitHub license field NOASSERTION (LICENSE: Apache-2.0 outside docs/, docs CC-BY-SA-4.0) | Single binary; `k0s backup` built in; measured numbers from k0s v1.22 (old) |
| MicroK8s | v1.35, v1.36 listed; **absent in v1.37** | runs in "as little as 540MB"; recommend 4 GB and 20 GB disk | HA clustering exists (page not opened: UNVERIFIED details) | Pi supported per docs links; details UNVERIFIED | Canonical, Apache-2.0, snap-based | Not a CNCF project (not found in landscape as a project) |
| Talos Linux | v1.35, v1.36, v1.37 | min: control plane 2 GiB/2 cores/10 GiB disk; worker 1 GiB/1 core | 3 control planes recommended | amd64 + arm64; SBC list includes Pi 4B, CM4, Jetson Nano, RK3588 boards (Pi 5 not listed in page text: UNVERIFIED); NVIDIA drivers 595/580 | Sidero Labs, MPL-2.0; not a CNCF project in landscape | Replaces the OS: immutable, API-managed, no SSH; strong for clusters, awkward for an "appliance with a user-facing OS" |
| kubeadm | Upstream reference | 2 GB RAM, 2 CPU for control plane | stacked or external etcd, 3+ control-plane nodes | arm64 packages: UNVERIFIED | Kubernetes project, Apache-2.0 | You supply CNI, storage, LB, ingress, upgrades, backups |

## 4. HA and scaling

- **k3s embedded etcd HA:** odd number of servers required for quorum; start first server with `--cluster-init` and a shared `K3S_TOKEN`, join others with `--server https://<first>`; optional fixed registration address/`--tls-san`. Min 3 servers for real fault tolerance (the docs require an odd count; 3 is the minimum meaningful HA). [S24]
- **k3s external DB:** two or more servers + PostgreSQL/MySQL/etcd; optional fixed registration address; agents optional. [S7][S26]
- **k3s sizing:** server 2 CPU/4 GB: 0-350 agents; 4/8: 351-900; 8/16: 901-1800; 16+/32: 1800+. A 3-server HA setup scales ~50% more (3 servers of 4 vCPU/8 GB: ~1200 agents). Join agents in batches of 50 or fewer. [S8]
- **Upstream design limits (any distro):** 110 pods/node, 5,000 nodes, 150,000 pods, 300,000 containers. [S27]
- **RKE2 HA:** fixed registration address, odd number (three recommended) of server nodes running etcd, API and control plane, zero or more agents. [S28]
- **k0s:** HA = multiple controllers behind a load balancer; recommended controller RAM scales 1-2 GB (10 workers) to 8-16 GB (500 workers). [S29]
- **Appliance implication:** single-node tiers use k3s with SQLite (or embedded etcd if the same image must later grow to HA). SQLite to etcd migration path: see k3s datastore docs; exact in-place migration steps UNVERIFIED. Tier with 3 mini PCs: embedded etcd on NVMe/SSD only.

## 5. Upgrades and rollback

- **Automated upgrades:** Rancher `system-upgrade-controller` with `Plan` CRD (`upgrade.cattle.io/v1`), selectors, concurrency, cordon, channel `https://update.k3s.io/v1-release/channels/stable`; supports scheduling windows. [S30]
- **Version skew:** docs warn the Kubernetes version skew policy applies; plans must not skip minor versions and **SUC will not protect you** against unsupported jumps. Upstream skew: kubelet may be up to three minors older than kube-apiserver; kube-apiservers within one minor of each other. [S30][S31]
- **Downgrade prevention:** upgrade image refuses to downgrade k3s ("Kubernetes does not support downgrades of control-plane components"); failed nodes stay cordoned if `cordon: true`. [S30]
- **Rollback (k3s): possible, but only via binary downgrade plus datastore restore.** You need a snapshot taken on the older minor version; "If you cannot restore the database, you cannot roll back to a previous minor version." Works for SQLite (replace .db), embedded etcd (`k3s server --cluster-reset --cluster-reset-restore-path=<snapshot>`), external DB. [S32]
- **Snapshots:** embedded etcd scheduled snapshots on by default at 00:00 and 12:00, 5 retained per server on local disk; optional upload to S3-compatible storage; `k3s etcd-snapshot save|ls|delete|prune`. [S33]
- **RKE2 snapshots:** same tooling and defaults (`rke2 etcd-snapshot`), S3 optional, S3 secret supported for restore. [S20]
- **Product consequence:** OneMind must take a datastore snapshot before every Kubernetes-layer upgrade and refuse minor-skipping; "one-click rollback" must be implemented as snapshot-restore and is data-lossy for changes since the snapshot.

## 6. Security hardening

- **k3s:** secure-by-default "reasonable defaults"; CIS hardening guide and CIS self-assessments for several benchmark versions (e.g. v1.10 guide for k3s v1.28-1.31, plus 1.11, 1.12, 2.0 pages). Some CIS items require opt-in: host sysctls, `protect-kernel-defaults: true`, `secrets-encryption: true`, audit logging, PSA and NetworkPolicies. PodSecurity and NodeRestriction admission are enabled by default; PSA policy via `admission-control-config-file` (psa.yaml) from v1.25. [S34][S35]
- **Secrets encryption at rest:** `--secrets-encryption` generates AES-CBC key + encryption config; providers aescbc (default) and secretbox; key rotation supported; cannot be enabled on a running server without restart. [S36]
- **Network policies:** embedded kube-router controller (disable with `--disable-network-policy` when using Cilium/Calico). [S3][S6]
- **RKE2:** `profile: cis` flips on restricted PSS + default network policies; FIPS-built binaries; SELinux policy. See section 2. [S15][S17][S18]
- **Gap:** no source opened shows an independent third-party CIS certification of k3s; the docs describe self-assessment only.

## 7. GPU

- **NVIDIA GPU Operator** platform-support page lists K3s, RKE2 ("Rancher Kubernetes Engine 2"), Mirantis k0s and Canonical MicroK8s on Ubuntu 26.04/24.04/22.04 for Kubernetes 1.33-1.37 (bare metal / VM passthrough). [S37] The footnote meaning for the "4" markers on RKE2 and k0s columns was not resolved: UNVERIFIED.
- **Jetson:** the same page states: "NVIDIA Jetson, or other embedded products with integrated GPUs, are not supported" by the GPU Operator. [S37] The standalone device plugin notes nvidia-container-toolkit >= 1.11.0 is required for integrated GPUs on Tegra-based systems. [S38] So Jetson tier = k3s + host-installed JetPack/container toolkit + device plugin, not the GPU Operator.
- **k3s native:** k3s auto-detects the `nvidia`/`nvidia-cdi` runtimes in PATH at startup, writes them into containerd config, ships RuntimeClasses; pods may need `runtimeClassName: nvidia`. [S39]
- **RKE2:** official add-on doc for deploying the NVIDIA operator; from GPU Operator v26.3 it can manage drivers on any OS given a driver container image. [S40]
- **Talos:** support matrix shows NVIDIA drivers 595 (production) / 580 (LTS) via system extensions. [S16]

## 8. Who uses what

| Product | Distribution | Evidence |
|---|---|---|
| Olares (beclab/Olares, AGPL-3.0) | **k3s** is "the default Kubernetes distribution that Olares installs and runs on" (infrastructure/k3s/README.md; k3s code in cli/pkg/k3s). Olares also lists KubeSphere among incorporated projects. | [S25] |
| Kairos (CNCF sandbox, Apache-2.0) | Providers k3s and k0s (build flags `--provider k3s`, `--provider k0s`); kubeadm provider: UNVERIFIED (not seen in pages opened). | [S41] |
| SUSE Edge 3.7 | Lists K3s and RKE2 as components (with SLE Micro 6.2 as base OS). | [S42] |
| Rancher | Rancher-provisioned RKE2 (v2.6+) and managed K3s clusters. | [S15][S8] |
| DigitalOcean DOKS | Managed Kubernetes with managed control plane; has its own conformance entries for v1.35-v1.37. Its docs describe it as integrating "with standard Kubernetes toolchains". | [S9][S43] |

## 9. Migration / portability DOKS to k3s

- **Helm charts and plain manifests:** portable, because both DOKS and k3s are conformance-certified [S9]. Argo CD is not tied to a distro: its tested-Kubernetes-versions page (Argo CD 3.6 tested on 1.34-1.37) lists upstream versions only; no k3s-specific caveat found in the Argo CD docs opened (FAQ search for "k3s" returned nothing). [S44]
- **Differences to handle:**
  - `Service type: LoadBalancer` with `service.beta.kubernetes.io/do-loadbalancer-*` annotations is DO-specific. On k3s, **ServiceLB** (Klipper) uses node ports/IPs (and Traefik's LB service takes 80/443 on all nodes by default); for real VIPs use **MetalLB** and start k3s with `--disable servicelb` as MetalLB docs instruct. [S5][S45]
  - **StorageClass `do-block-storage`** (RWO only, DO CSI) does not exist on k3s. Replace with `local-path` (default in k3s), Longhorn, or OpenEBS. Charts should take `storageClass` as a value, never hard-code it. [S46][S4]
  - **Ingress:** k3s ships Traefik; RKE2 now also defaults to Traefik since v1.36 after ingress-nginx EOL (March 2026) [S23]. Any charts that assume ingress-nginx annotations need review.
  - `Node` labels/zones, cloud-controller-manager, autoscaler and managed-node-pool features are DOKS-only; DOKS cluster autoscaling has no k3s equivalent out of the box.
  - Certificates, DNS and the Tailscale operator are independent of the distribution (not distribution-specific; no source needed beyond the above).
- **Plan:** keep the existing DOKS cluster as the cloud "control" cluster; define OneMind appliance as a k3s cluster with the same Argo CD app-of-apps, using overlay values for storage/LB. NATS JetStream and Authentik are plain Helm workloads (portability not separately verified: UNVERIFIED).

## 10. Storage for appliances

| Option | Best for | Resource / topology needs | Replication | Backups | Source |
|---|---|---|---|---|---|
| local-path-provisioner (k3s default) | Single node, 2-16 GB boxes, Pi | No extra daemons; hostPath/local PVs under `/opt/local-path-provisioner` (k3s data dir variant) | None (node-local; data lost with node) | None built in; use Velero/restic/file-level backup (not verified in these docs) | RWO only per example; "no support for volume capacity limit" | [S47] |
| Longhorn (CNCF incubating, Apache-2.0) | 3+ node clusters on SSD/NVMe | V1 engine: 3 nodes, 4 vCPU and 4 GiB per node recommended; V2 engine adds a dedicated core and 2 GiB hugepages per node and kernel 6.7+; requires Kubernetes >= 1.34, open-iscsi/NFSv4 client prereqs; has k3s guide and Talos guide | Synchronous replicas across nodes | Backup targets: NFS, SMB/CIFS, Azure Blob, S3-compatible | [S48][S49] |
| OpenEBS (CNCF sandbox) | Local PV (hostpath/LVM/ZFS) or Replicated PV (NVMe-TCP, "hugepages and cores") | Replicated engine is heavyweight; exact installation requirement numbers not retrieved (page text empty): UNVERIFIED | Replicated PV mirrors across nodes; Local PV none | LVM/ZFS snapshots/backup/restore per docs | [S50] |
| Rook-Ceph (CNCF graduated, Apache-2.0) | Large clusters with raw disks | Needs raw devices/partitions/LVs without filesystems; supports K8s v1.32-1.37, amd64 and arm64; Ceph's own CPU/RAM sizing not retrieved: UNVERIFIED | Ceph replication/erasure coding, block/file/object | Ceph-native (RBD snapshots/mirroring: UNVERIFIED here) | [S51][S52] |

Appliance guidance: Tier 1-2 = local-path (+ external/off-box backups). Tier 3 multi-node = Longhorn (SSD, 3 nodes). Public-safety/enterprise scale = Rook-Ceph only with dedicated disks and ops staff; avoid on small boxes.

## k8s vs k3s explained simply

Kubernetes ("k8s") is the open-source system that decides which containers run on which computers, restarts them when they crash and gives them networking and storage. "Upstream" Kubernetes is the parts list; you must still pick and assemble a container runtime, networking, storage, load balancer and ingress, and keep it all upgraded. **k3s is the same Kubernetes, pre-assembled into one small program** with sensible parts already included (containerd, Flannel networking, Traefik web router, local disk storage, a simple load balancer), and with the datastore swapped to SQLite by default so one small machine can run it. Because it passes the same CNCF conformance tests, anything written for Kubernetes (Helm charts, Argo CD) runs on it. **RKE2** is the "locked-down" sibling for government/regulated environments: bigger, strict defaults, FIPS-built. A managed service such as DigitalOcean's DOKS is the same Kubernetes run for you in their cloud.

## Recommendation per tier

| Tier | Distribution | Datastore | Storage | Notes |
|---|---|---|---|---|
| Single x86 mini PC, 2-4 GB RAM | k3s, single server (server+agent in one) | SQLite | local-path | Docs minimum is 2 GB for a server; measured ~1.6 GB with a workload: 2 GB boxes are too tight for the OneMind app stack. Treat 4 GB as practical floor (our judgment; not a doc figure). Disable what OneMind does not use (e.g. servicelb, metrics-server if unused). |
| x86 8-16 GB | k3s single server | SQLite, or embedded etcd if growth to HA is planned | local-path | Main consumer tier. |
| NVIDIA RTX GPU box | k3s + NVIDIA runtime/CDI (or GPU Operator, which lists K3s) | SQLite/etcd | local-path | Discrete GPU: Operator supported on K3s [S37]. |
| Raspberry Pi 5 | k3s (arm64) | SQLite on external SSD; embedded etcd HA discouraged on SD | local-path on SSD | Enable cgroups in cmdline.txt. Pi 5 as a named platform: UNVERIFIED in k3s docs (docs name Raspberry Pi generally and measured on Pi 4B). |
| Jetson | k3s (arm64) + JetPack + nvidia runtime + device plugin | SQLite | local-path | GPU Operator explicitly unsupported for Jetson [S37]. |
| Multi-node cluster (3-N) | k3s, 3 servers embedded etcd + agents | embedded etcd on SSD/NVMe | Longhorn | MetalLB for VIPs, SUC for upgrades, S3 snapshots. |
| Enterprise / public safety | **RKE2** (`profile: cis`, SELinux, FIPS build) on SLES/RHEL/Ubuntu, optionally SUSE Edge validated design | embedded etcd, 3 servers | Longhorn or Rook-Ceph | Traefik default since 1.36; compliance claims need SUSE docs and your own audit. |

## Open items (UNVERIFIED, resolve before committing roadmap)

1. SUSE/k3s formal support lifecycle and EOL per k3s minor (only upstream's 14-month policy verified).
2. RKE2 rollback doc and FIPS 140-3 status.
3. Pi 5 explicit support statements (k3s, Talos).
4. Kairos kubeadm provider existence.
5. OpenEBS replicated and Ceph hardware minimums.
6. MicroK8s HA/arm64 pages and why it is missing from the v1.37 conformance listing (could simply be pending submission).
7. In-place SQLite to embedded etcd migration procedure on k3s.
8. Whether any OneMind chart depends on ingress-nginx (EOL March 2026).

## Sources

- [S1] https://docs.k3s.io/ (intro, bundled components)
- [S2] https://docs.k3s.io/faq ("CNCF-certified")
- [S3] https://github.com/k3s-io/k3s README (fully conformant, bundled list, "can be disabled or swapped out")
- [S4] https://docs.k3s.io/installation/packaged-components (`--disable`)
- [S5] https://docs.k3s.io/networking/networking-services (CoreDNS, Traefik, ServiceLB)
- [S6] https://docs.k3s.io/cli/server and https://docs.k3s.io/installation/network-options (flags, flannel backends)
- [S7] https://docs.k3s.io/datastore (SQLite, etcd, external DB)
- [S8] https://docs.k3s.io/installation/requirements
- [S9] https://github.com/cncf/k8s-conformance (v1.35, v1.36, v1.37 directories: k3s, rke2, k0s, talos, microk8s, digitalocean; PRODUCT.yaml for k3s and RKE2)
- [S10] https://docs.k3s.io/reference/resource-profiling
- [S11] https://docs.k3s.io/datastore/ha-embedded
- [S12] GitHub API: k3s-io/k3s, rancher/rke2 releases and license (Apache-2.0)
- [S13] https://kubernetes.io/releases/ and https://kubernetes.io/releases/patch-releases/
- [S14] https://github.com/cncf/landscape landscape.yml (k3s: project sandbox, accepted 2020-08-19; k0s sandbox; Longhorn incubating; OpenEBS sandbox; Rook graduated; Kairos sandbox)
- [S15] https://docs.rke2.io/ (intro)
- [S16] https://docs.siderolabs.com/talos/v1.14/ (what-is-talos, system-requirements, support-matrix, prodnotes)
- [S17] https://docs.rke2.io/security/fips_support and https://docs.rke2.io/security/hardening_guide
- [S18] https://docs.rke2.io/security/pod_security_standards
- [S19] https://docs.rke2.io/security/selinux
- [S20] https://docs.rke2.io/datastore/backup_restore
- [S21] https://docs.rke2.io/install/requirements
- [S22] https://docs.rke2.io/networking/basic_network_options
- [S23] https://docs.rke2.io/networking/networking_services (ingress-nginx EOL, Traefik default from v1.36)
- [S24] https://docs.k3s.io/datastore/ha-embedded
- [S25] https://github.com/beclab/Olares README and infrastructure/k3s/README.md
- [S26] https://docs.k3s.io/datastore/ha
- [S27] https://kubernetes.io/docs/setup/best-practices/cluster-large/
- [S28] https://docs.rke2.io/install/ha
- [S29] https://docs.k0sproject.io/stable/ (intro), /system-requirements/, /high-availability/, /backup/
- [S30] https://docs.k3s.io/upgrades/automated and https://docs.k3s.io/upgrades/manual
- [S31] https://kubernetes.io/releases/version-skew-policy/
- [S32] https://docs.k3s.io/upgrades/roll-back
- [S33] https://docs.k3s.io/cli/etcd-snapshot and https://docs.k3s.io/datastore/backup-restore
- [S34] https://docs.k3s.io/security/hardening-guide
- [S35] https://docs.k3s.io/security/self-assessment-1.10
- [S36] https://docs.k3s.io/security/secrets-encryption
- [S37] https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/platform-support.html
- [S38] https://github.com/NVIDIA/k8s-device-plugin (Tegra requirement)
- [S39] https://docs.k3s.io/advanced (NVIDIA container runtime)
- [S40] https://docs.rke2.io/add-ons/gpu_operators
- [S41] https://kairos.io/docs/reference/kairos-factory/ and https://github.com/kairos-io/kairos README
- [S42] https://documentation.suse.com/suse-edge/
- [S43] https://docs.digitalocean.com/products/kubernetes/ , /how-to/add-volumes/, /how-to/add-load-balancers/
- [S44] https://argo-cd.readthedocs.io/en/stable/operator-manual/tested-kubernetes-versions/
- [S45] https://metallb.io/configuration/k3s/
- [S46] https://docs.digitalocean.com/products/kubernetes/how-to/add-volumes/ (do-block-storage, RWO)
- [S47] https://github.com/rancher/local-path-provisioner README
- [S48] https://longhorn.io/docs/latest/best-practices/ and /deploy/install/
- [S49] https://longhorn.io/docs/latest/snapshots-and-backups/backup-and-restore/set-backup-target/
- [S50] https://openebs.io/docs/
- [S51] https://rook.io/docs/rook/latest-release/Getting-Started/Prerequisites/prerequisites/
- [S52] https://rook.io/docs/rook/latest-release/Getting-Started/intro/
- Additional: https://docs.kubeadm pages: https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/ and /high-availability/; https://microk8s.io/docs and /docs/getting-started
