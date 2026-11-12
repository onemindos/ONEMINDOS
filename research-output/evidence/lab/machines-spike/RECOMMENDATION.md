<!-- SPDX-License-Identifier: Apache-2.0 -->
# Machines runtime: KubeVirt or an own QEMU + noVNC service? Recommendation for Zeus

**Serves:** founder decision **F-56** ([DECISIONS-NEEDED](../../../../docs/leap/DECISIONS-NEEDED.md)), [machines.md](../../../../docs/umbrel2/machines.md) 4.1 and 4.12, epic UMB-MACH-1/2. Criteria were fixed before this was written in [README.md](README.md) (M1-M5, sha256 in `PREREGISTRATION.sha256`) and [PREREGISTRATION-ADDENDUM.md](PREREGISTRATION-ADDENDUM.md) (B7-C1...C8). Date: 2026-11-12. Scope: a recommendation only, no production code.

## 0. In one paragraph (read this if nothing else)

OneMind wants to let people run whole computers ("machines") inside the box. Option **A** is KubeVirt, a ready-made add-on that makes a VM a Kubernetes object. Option **B** is our own small service that runs QEMU and shows its screen with noVNC. **This session could not run either one**: the container has no hardware virtualization (`/dev/kvm`), no Docker daemon, and cannot reach the registry that hosts KubeVirt's images. So every "does it boot / freeze / respect quotas / how much RAM" test is **UNVERIFIED**, not passed and not failed. What we could check without a hypervisor (licences, arm64 support as documented upstream, install footprint as declared in the manifests, how much glue code each option needs) does not contradict the current plan (A, as an optional extension, B as fallback), but it also does not prove it. **The one number the decision hangs on (idle RAM on a 4 GB / 16 GB Pi 5) is still unmeasured.**

## 1. What was and was not run

| Pre-registered test | Result here | Why |
|---|---|---|
| T0 pins | **PASS for 3 of 7 pins**: `kubevirt-operator.yaml` `9ac45a43...92da`, `kubevirt-cr.yaml` `43106136...a2af`, CDI `cdi-operator.yaml` `c7d92bd1...e224` re-downloaded and match the README pins. The other four (k3s, virtctl, noVNC tarball, Fedora image) were not re-checked | Enough network for 3 of the 7 |
| T1 environment | **LIMIT**: no `/dev/kvm`, no `vmx`/`svm` flag, x86_64 not arm64 | `uname -m`, `/proc/cpuinfo` |
| M1 boot, M2 console, M3 freeze, M4 quota | **BLOCKED** (not PASS, not FAIL) | Need KVM (or the 3x TCG rule), k3s, KubeVirt/CDI images from `quay.io` (refused by the proxy), a Debian mirror (refused) |
| M5 memory, KubeVirt control plane | **BLOCKED** | Same |
| M5 memory, a QEMU process | One **TCG** (software emulation) measurement, below. **Not** the cost of a KVM machine | No KVM |
| Licences B7-C4, docs-based C2/C5, install counts C3, glue lines C7 | Done (sections 3-6) | Runnable |

Evidence kept out of the repo (scratch only): the three downloaded manifests and the upstream user-guide pages named below.

### 1.1 The one TCG measurement (an upper bound that mostly shows what not to conclude)

QEMU 8.2.2 (Ubuntu 24.04 package), `-machine q35 -accel tcg`, 2 vCPU, a tiny busybox guest from the stock Ubuntu kernel, VNC with `websocket=on` (B's console listener; present in `-help`), summed **PSS** of the single QEMU process (`/proc/<pid>/smaps_rollup`) after 30 s settle, six samples 10 s apart, values stable to 0.1 MiB:

| Guest RAM | QEMU PSS (TCG) |
|---|---|
| 256 MiB | 249.6 MiB |
| 1024 MiB | 264.4 MiB |
| 2048 MiB | 284.7 MiB |
| 1024 MiB, `tb-size=16` (TCG code cache capped at 16 MiB) | 209.3 MiB |

Reading: the process is not 1 GiB for a 1 GiB guest (untouched guest RAM is not resident), and the figure moves by tens of MiB with TCG's translation cache, which **does not exist under KVM**. So this says nothing reliable about the KVM overhead on a Pi, and it was not used for any comparison. **Label: UNVERIFIED for KVM and for arm64.** Installed size of Debian-family QEMU for x86 on this host: `qemu-system-x86` 58.5 MiB + common 7.1 + data 9.1 + `qemu-utils` 11.1 = about 86 MiB on disk (dpkg Installed-Size). The arm64 package set for the Pi was not measured (UNVERIFIED).

## 2. The two options as designed

| | **A. KubeVirt + CDI** | **B. Own QEMU + noVNC service** |
|---|---|---|
| What it is | Apache-2.0 operator-managed add-on: virt-operator, virt-api, virt-controller, a per-node virt-handler, a per-VM virt-launcher pod holding QEMU/libvirt, plus CDI for disk import ([KubeVirt user guide, architecture](https://github.com/kubevirt/user-guide/blob/main/docs/architecture/architecture.md)) | One Deployment + PVC per machine running `qemu-system-*` directly; OneMind writes the object model, console proxy and agent calls |
| Console | `virtualmachineinstances/vnc` subresource on the Kubernetes API, separately authorisable by RBAC ([accessing VMs](https://github.com/kubevirt/user-guide/blob/main/docs/user_workloads/accessing_virtual_machines.md): the `console` and `vnc` subresources are granted with `get`) | QEMU's own `-vnc ...,websocket=on` listener (confirmed in `qemu-system-x86_64 -help` 8.2.2); no authentication inside the cluster unless we add it |
| Freeze for a consistent backup | KubeVirt snapshots freeze guest filesystems through the guest agent and unfreeze after; if freezing fails the snapshot is "best effort" and flagged `QuiesceFailed` ([snapshot API](https://github.com/kubevirt/user-guide/blob/main/docs/storage/snapshot_restore_api.md)) | We call the guest agent (`guest-fsfreeze-*`) ourselves and own timeout/thaw safety |
| Quotas | Normal Kubernetes `ResourceQuota` on the namespace; KubeVirt adds its own overhead to the pod request (size **UNVERIFIED**, pre-registered as E2) | Same quota, we choose the allowance (pre-registered 256 MiB) |

## 3. Results per criterion

### B7-C1 RAM overhead on 4/16 GB Pi 5 and an x86 mini-PC: **UNVERIFIED**

No usable measurement exists in this session. What upstream declares (not usage): the operator manifest requests **10m CPU / 450 Mi** for each virt-operator pod and asks for **2 replicas**; CDI's operator requests **100m CPU / 150 Mi**, 1 replica (`kubevirt-operator.yaml` v1.9.1, `cdi-operator.yaml` v1.66.1, Deployment specs). virt-api, virt-controller and virt-handler are created by the operator at install time, so their requests are not in these files (the KubeVirt CR in `kubevirt-cr.yaml` sets no replica or resource override). Requests are scheduling hints, not resident memory, and the earlier "0.6-1 GiB" in machines.md 4.1 remains an **UNVERIFIED estimate**. The prereg plan (single-node settings: operator 1 replica, `infra.replicas: 1`) is the right way to get the real number; it has not been run.

For the 4 GB case: k3s on a 4 GB Pi plus a 1 GiB guest plus the QEMU allowance leaves little headroom even before KubeVirt, so the 4 GB Pi 5 is likely headless-only or no-machines under either option. That is arithmetic, not a measurement.

### B7-C2 arm64: **PASS with documented holes (docs only, not run)**

The KubeVirt user guide says the operator install "supports to deploy KubeVirt on both x86_64 and Arm64" ([installation](https://github.com/kubevirt/user-guide/blob/main/docs/cluster_admin/installation.md)). The Arm64 pages list what does not work or is unverified: hugepages unsupported and only 4 KiB page-size hosts verified; hotplug network interfaces, hotplug volumes and the `HyperV` gate not supported; the Export API partly unsupported because "CDI is not supported yet" on Arm64; vGPU/mediated devices unverified ([operations on Arm64](https://github.com/kubevirt/user-guide/blob/main/docs/cluster_admin/operations_on_Arm64.md), [feature gate status](https://github.com/kubevirt/user-guide/blob/main/docs/cluster_admin/feature_gate_status_on_Arm64.md)). Live migration, snapshots, sidecar hook and VirtioFS are listed Supported. Two consequences:

1. The "only 4 KiB verified" line lands on the Pi 5 default kernel (16 KiB pages), which machines.md 4.11 and F-58 already flag as a risk. **Docs-grounded, still to be tested (LT-MACH-3).**
2. The Arm64 page says CDI is not supported there, while the pre-registered lab installs CDI v1.66.1 on arm64 and claims upstream release assets. One of these is stale; **UNVERIFIED which**. If CDI does not work on arm64, the Pi tier loses the checksum-verified image import that machines.md 4.6 relies on, and has to import disks another way. This is the most concrete arm64 risk found.

Option B on arm64: Debian ships `qemu-system-arm` and AAVMF (the pre-registered lab uses them); the Umbrel study shows QEMU/KVM arm64 guests with UEFI are routine ([machines.md 1.3](../../../../docs/umbrel2/machines.md)). Not run here: **UNVERIFIED**.

### B7-C3 Install footprint: **counted, partly**

| | KubeVirt v1.9.1 `kubevirt-operator.yaml` | CDI v1.66.1 `cdi-operator.yaml` |
|---|---|---|
| Size of the manifest | 496,820 bytes | 357,645 bytes |
| Objects in the file | 1 Namespace, 1 CRD document (the file embeds the CRD schema), 1 PriorityClass, 2 ClusterRoles, 1 Role, bindings, 1 ServiceAccount, 1 Deployment | 1 Namespace, 1 CRD document, 1 ClusterRole, 1 Role, bindings, 1 ServiceAccount, 1 Deployment |
| Images the operator may start | virt-operator, then virt-api/controller/handler/launcher (from operator env) | cdi-operator plus controller, importer, cloner, apiserver, uploadserver, uploadproxy (7 images in the operator's env) |
| Pods at rest | operator (2 replicas), plus virt-api, virt-controller and a virt-handler on each node, named on the architecture page; replica counts at runtime **UNVERIFIED** | operator, plus controller, apiserver and uploadproxy (names from the operator's image list; runtime pod list **UNVERIFIED**) |

Image sizes and the time to ready/removal (LT-MACH-1: <= 5 min, clean removal) are **BLOCKED** (registry unreachable). For B the add-on is one container image plus Debian's QEMU packages (about 86 MiB on disk for x86, above).

### B7-C4 Licence: **PASS for both, with a source-offer duty if mirrored**

KubeVirt: Apache License 2.0 (`LICENSE` at tag v1.9.1, header read). noVNC 1.7.0: `LICENSE.txt` states the core library (`core/**/*.js`, `app/*.js`) is MPL-2.0; MPL is file-level copyleft, so unmodified use as an npm dependency is fine and any change to a noVNC file must be published. QEMU is GPL-2.0 and libvirt is LGPL-2.1+ (the Ubuntu 24.04 copyright file for `qemu-system-x86` installed here refers to GPL-2 and LGPL-2; libvirt's licence was not re-read). Neither option links these into OneMind code: A runs them inside KubeVirt's launcher image, B runs the `qemu` binary in a container. If OneMind **mirrors** the launcher image (A) or builds a QEMU container (B), the GPL source-offer duty applies to both; this is the same for the two options. CDI's licence was not re-read at its tag in this session (machines.md 4.2 says Apache-2.0, **carried forward, UNVERIFIED here**).

### B7-C5 Isolation and security model: **A documented, B to be designed**

A: the install docs require the API server to allow privileged containers for "KubeVirt's privileged DaemonSet" (virt-handler) ([installation](https://github.com/kubevirt/user-guide/blob/main/docs/cluster_admin/installation.md)); the feature-gate table lists a `NonRoot` mode as Supported on Arm64 (with `Root` also listed); whether non-root is the default launcher mode in v1.9.1 was **not verified here** (machines.md 4.6 asserts it). The architecture page states the design goal that a non-privileged user must not gain access to a privileged pod through KubeVirt. AppArmor and SELinux have documented extra steps on some distros (a Debian AppArmor denial for `/usr/libexec/qemu-kvm` is the documented example), which matters on Debian 13. k3s uses containerd, which is on KubeVirt's supported-runtime list.

B: a pod needs `/dev/kvm`. The pre-registered lab tries a hostPath char device first and falls back to `privileged: true`, to be recorded as a finding. A product B would need its own device plugin to avoid privileged pods (not designed). The QEMU WebSocket port has no authentication of its own, so every consumer must go through our broker, and per-pod network policy has to keep it unreachable from other pods. This is the main place B costs security work.

### B7-C6 Approval-gated actions: **A fits better; AI must not hold the keys either way**

CLAUDE.md rule: AI never actuates without human approval. With A, a machine is a `VirtualMachine`/`DataVolume` object, so the gateway can render it, hash it (`plan_sha256`) and apply it after the owner approves, which is the model machines.md 4.6 describes. Start and stop are changes to `runStrategy` ([run strategies](https://github.com/kubevirt/user-guide/blob/main/docs/compute/run_strategies.md)). Console and VNC are separate RBAC subresources, so "see the screen" and "type into it" can be granted differently from "create a machine". With B the same mapping is possible (render a Deployment), but "type into it" is whatever our proxy allows, and the permission model is code we own and must test. Either way the agent control lease (machines.md 4.6, `machine.control`, passkey, never standing-approved) is OneMind's own rule, not the runtime's. **This criterion is design-level; nothing was run.**

### B7-C7 Maintenance burden: **glue counted, upstream health UNVERIFIED**

Committed lab scripts (not a product, `wc -l` of `scripts/a/*` vs `scripts/b/*`): **A 106 lines** (install, remove, single-node, apply, one `VirtualMachine` manifest), **B 149 lines** (Containerfile, build, run-qemu, a guest-agent client `qga.py`, apply, a 58-line Deployment manifest). Shared console files are not counted. These scripts have **not been run**; this is a rough proxy (pre-registered E8) and says nothing about the product-grade code behind either, which machines.md 4.1 estimates is smaller for A. The GitHub release API, and so release cadence and contributor activity, were refused by the proxy: **UNVERIFIED**. The cost of A that docs do show: the project follows "one of the latest three Kubernetes releases" ([installation](https://github.com/kubevirt/user-guide/blob/main/docs/cluster_admin/installation.md)), so every k3s bump is also a KubeVirt compatibility check; B depends only on QEMU and a guest agent.

## 4. Where this leaves the decision

| Question | Answer from this spike |
|---|---|
| Does anything found contradict F-56's current proposal (A as optional signed extension, B as fallback)? | No hard contradiction. Two new risks for the Pi tier: the Arm64 page says CDI is unsupported there (contradicts the lab's assumption; needs a quick upstream check), and only 4 KiB page-size hosts are verified. |
| Is there evidence B is cheaper in RAM? | Only by construction (B has no control plane). The size of that saving is **unmeasured**. |
| Is there evidence B is the easier path to maintain? | The glue counts are close and unrun. Not enough. |
| Is the RAM budget met on a Pi 5? | **UNVERIFIED.** |

## 5. What to do next (cheapest first, each is a runnable step)

1. **5-minute upstream check (no hardware):** open the CDI v1.66.1 release page and the KubeVirt Arm64 page issue tracker to see whether CDI publishes arm64 images and whether the "CDI is not supported yet" sentence is stale. Settles the biggest unknown above. Needs an environment that can reach `quay.io` and the GitHub API.
2. **Run the existing lab** (`scripts/` in this folder, pre-registered) on a machine with nested virtualization (the author's Mac) or an arm64 Linux box: gives M1-M5 and the real RAM number. Needs about half a day of someone's time and no new code.
3. **LT-MACH-2/3 on real hardware:** a Pi 5 (4 GB and 16 GB) and an N150 mini-PC with the same scripts: the only way to settle the Pi tier and the 16 KiB page question.

## Decision for Zeus

This is your decision (F-56, plus the Pi tier part of F-58); nothing here decides it.

1. **Keep F-56 as written** (KubeVirt as an optional signed extension, B as fallback, reopen if LT-MACH-2 fails). Cost: nothing now; the Pi tier stays conditional on a measurement we still do not have. Risk: if CDI does not support arm64 the Pi story changes.
2. **Make the Pi tier use B from the start** (own QEMU service on Pi 5, KubeVirt on Lite and Pro). Cost: we own two runtimes behind one `MachineRuntime` interface, and B's security and console work. Benefit: lowest RAM on the smallest box.
3. **Pause machines on Pi entirely** until the lab has run on real hardware; ship machines on Lite and Pro first.
4. **Authorise a time-boxed step**: someone runs the pre-registered lab (item 2 above) and the CDI check (item 1), then you decide with numbers.

What I would need from you: which of 1-4, and whether the Pi 5 4 GB should be offered Machines at all.
