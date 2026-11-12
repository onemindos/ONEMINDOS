<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lab spike LAB-machines-spike: KubeVirt vs an own QEMU + noVNC service on k3s

**Status:** PRE-REGISTERED, not yet run. Goal, hypotheses, design and pass/fail criteria were written 2026-11-12, before any lab VM was created, any file downloaded into it or any test run. They are committed alone, before the run. The sha256 of this file at that moment is in `../PREREGISTRATION.md` and `PREREGISTRATION.sha256`. Results are added below the line "Results" after the run. Nothing above that line changes afterwards except this Status line and typo fixes; any other change is logged in the deviations section.

**Serves:** [`docs/umbrel2/machines.md`](../../../../docs/umbrel2/machines.md) §4.1 (runtime choice) and §4.12 LT-MACH-2 (overhead budget), founder decision **F-56** (machines.md F-MACH-1: "KubeVirt extension; reopen if LT-MACH-2 fails"), and backlog row UMB-MACH-1 in part. This is a spike on a Lima VM ahead of the real-hardware lab kit. It does not replace LT-MACH-1…3 on the Dell, the N150 box or a Pi 5.

> **Explain it like I'm the founder.** OneMind plans to let people run whole computers ("machines", like Umbrel's) inside a box. There are two ways to build that on top of the k3s that already runs on every box. **A, KubeVirt**: a ready-made open-source add-on that turns a virtual machine into an ordinary Kubernetes object. **B, our own small service**: one container per machine that runs QEMU (the same emulator KubeVirt uses underneath) and shows its screen in the browser with noVNC. The design picked A, but warned that A might use too much memory on a Raspberry-Pi-sized box. This spike builds both in one disposable VM sized like a 4 GB Pi 5 and checks five things for each: a Linux machine boots; its screen works in a browser tab; the machine can be "frozen" for a moment so a backup copy is consistent; a household member's limit (quota) really stops a second machine; and how much memory each approach costs.

## 1. Goal

Answer with a run, not documentation, whether the runtime chosen in machines.md §4.1 (A: KubeVirt + CDI on k3s) does the five jobs above at least as well as the fallback (B: an own QEMU + noVNC service on k3s), and whether A's idle memory cost fits the Pi 5 budget that F-56 names (LT-MACH-2: **≤ 800 MiB**).

## 2. Hypotheses

- **H1 (boot)** Both A and B boot the same Fedora Cloud arm64 image to a login prompt with a working guest agent on k3s, using KVM inside a nested-virtualization Lima VM.
- **H2 (browser console)** Both show the guest's screen in a real browser engine through unmodified noVNC, and keyboard input from the browser reaches the guest. A needs only a pass-through proxy in front of KubeVirt's VNC subresource; B needs QEMU's built-in WebSocket VNC listener.
- **H3 (freeze)** Both can freeze the guest's filesystems through the QEMU guest agent. While frozen, guest writes block, and a raw copy of the disk taken during the freeze contains data written just before it and has a clean filesystem.
- **H4 (quotas)** A Kubernetes `ResourceQuota` on a person's namespace lets the first machine run and refuses a second one that would exceed it, with the reason visible on the machine's own objects, for both A and B.
- **H5 (overhead)** KubeVirt + CDI idle within the LT-MACH-2 Pi 5 budget (≤ 800 MiB) in a single-node configuration. Per machine, A costs more memory than B (libvirt and KubeVirt's launcher processes next to QEMU).

## 3. The two options

| | **A. KubeVirt + CDI** (machines.md §4.1 choice) | **B. Own QEMU + noVNC service** (machines.md §4.1 fallback) |
|---|---|---|
| Runtime | KubeVirt **v1.9.1** (operator, API, controller, handler, launcher) + CDI **v1.66.1**, upstream release manifests and images | One `Deployment` (1 replica) per machine: a container built in the lab VM from `debian:trixie` (digest in `os/versions.lock.yaml`) with Debian's `qemu-system-arm`, `qemu-utils`, `qemu-efi-aarch64`, `python3-minimal` |
| Machine object | `VirtualMachine` + `DataVolume` (CDI imports the image over HTTP and converts it to a raw `disk.img` on a `local-path` PVC) | `Deployment` + `local-path` PVC; an init container converts the image to raw with `qemu-img convert` if the disk is missing |
| Guest hardware | 2 vCPU, 1 GiB, UEFI, virtio disk and NIC, `masquerade` pod network | Same: `qemu-system-aarch64 -machine virt -accel kvm -cpu host -smp 2 -m 1024`, Debian AAVMF, virtio-blk (`cache=none`), virtio-net user-mode network with an SSH port forward, virtio-gpu display |
| Console | KubeVirt `vnc` subresource (WebSocket on the Kubernetes API). In the lab, `kubectl proxy` stands in for the gateway's console broker | QEMU `-vnc …,websocket=on` listener reached through the pod's ClusterIP Service |
| Guest agent | KubeVirt's `freeze` / `unfreeze` subresources | QEMU guest agent socket in the pod (`guest-fsfreeze-*` commands) |
| `/dev/kvm` | KubeVirt's device plugin (`devices.kubevirt.io/kvm`) | First a non-privileged pod with `/dev/kvm` as a `hostPath` char device. If QEMU cannot open it, the pod is made `privileged` and this is recorded as a B finding (a product would need a device plugin) |

Both options use the **same guest bytes**: `Fedora-Cloud-Base-Generic-45-1.4.aarch64.qcow2`, the same NoCloud user-data (a `lab` user with an SSH key generated in the VM at run time) and the same 2 vCPU / 1 GiB size. Before any test, the image's package list is checked (read-only loop mount) for `qemu-guest-agent`. If it is missing, both options get the same `packages: [qemu-guest-agent]` line in the user-data (decided now, not after a failure).

## 4. Pass / fail criteria (frozen before the run)

### 4.1 Lab-wide

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| T0 | Pins | Every download inside the VM matches the sha256 pinned here, and the pin equals the upstream-published value: k3s **v1.37.2+k3s1** `k3s-arm64` `a779ccf1…aa84b` (`os/versions.lock.yaml`); KubeVirt v1.9.1 `kubevirt-operator.yaml` `9ac45a43…92da`, `kubevirt-cr.yaml` `43106136…a2af`, `virtctl-v1.9.1-linux-arm64` `12a26aa4…cbc5` (GitHub release asset digests); CDI v1.66.1 `cdi-operator.yaml` `c7d92bd1…e224`, `cdi-cr.yaml` `a497f90d…f8a7` (asset digests); noVNC **1.7.0** npm tarball `32689f18…e903` (equals the registry `integrity` sha512 `ucEJOx4T…zyA==`); Fedora image `1632acc8…286c` (Fedora's signed `Fedora-Cloud-45-1.4-aarch64-CHECKSUM`). Every container image that runs is recorded by digest | Any mismatch, an unpinned download, or a running image not recorded by digest |
| T1 | Environment (not a product test) | `/dev/kvm` exists in the lab VM and B's first boot runs with `-accel kvm` | — If not: recorded as **LIMIT**; every M test then runs under software emulation (A: KubeVirt `useEmulation: true`; B: `-accel tcg`), every deadline below is multiplied by 3, and results are labelled TCG |

### 4.2 Per option (each test is run once for A and once for B, and judged separately)

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| M1 | Linux guest boots | Within **10 min** of creating the machine object (the image import counts): the guest agent answers (A: VMI condition `AgentConnected=True`; B: `guest-ping` returns `{"return": {}}`), and `ssh lab@<guest> uname -m` prints `aarch64`. The serial console output is saved as evidence (A: the launcher's `guest-console-log` container, or `virtctl console`; B: QEMU's serial log file) | Either is missing at the deadline |
| M2 | Console in a browser tab | Headless Chromium (Debian package, inside the VM) opens the lab console page (our own short HTML using unmodified noVNC 1.7.0 `core/`). Within **60 s**, RFB fires `connect` and the canvas is at least 640×480 with **≥ 1,000** non-black pixels (about 25 characters of console text). Then `root` + Enter is typed through Chrome DevTools key events, and **≥ 100** canvas pixels change within **10 s**. Screenshots before and after typing are saved and looked at | No connect, a blank or smaller canvas, or no change after typing |
| M3 | Guest-agent freeze for a consistent backup | All of: **(a)** freeze succeeds and status reads frozen (A: `PUT …/freeze`, then VMI `status.fsFreezeStatus` = `frozen`; B: `guest-fsfreeze-freeze` returns ≥ 1, then `guest-fsfreeze-status` = `frozen`). **(b)** A write into the guest user's home, issued over an SSH session opened before the freeze and started 5 s after it, has not completed 20 s into the freeze, and completes **≤ 10 s** after thaw. **(c)** A marker file written without `sync` less than 2 s before the freeze is present in a raw copy of the disk taken while frozen (`cp --sparse=always`). The copy's root filesystem passes a read-only check (`btrfs check --readonly`; for ext4 `e2fsck -fn`; for XFS `xfs_repair -n`), and the marker is read from a read-only mount that replays no log (`ro,rescue=nologreplay`; ext4 `ro,noload`; XFS `ro,norecovery`). **(d)** Thaw succeeds and status returns to thawed | Any of (a)–(d) fails |
| M4 | Resource quotas | In namespace `machines-alice` with a `ResourceQuota` of `requests.memory` = `limits.memory` = **2Gi** and `requests.cpu` = `limits.cpu` = **6**, each machine declares 1 GiB / 2 vCPU as both request and limit (A: in the `VirtualMachine`, KubeVirt adds its own overhead to the pod; B: the pod requests and limits 1 GiB + a fixed **256 MiB** allowance for QEMU, chosen now). **(a)** The first machine starts and runs. **(b)** A second identical machine is refused: no second QEMU process ever starts, and a reason naming the exceeded quota is visible within **60 s** on the machine's own objects (A: `VirtualMachine`/`VirtualMachineInstance` status or events; B: the `Deployment` status or its `ReplicaSet` events). **(c)** The running machine's pod cgroup has a finite `memory.max` no larger than the quota | (a), (b) or (c) fails, including a first machine that cannot start because of the quota |
| M5 | Memory on a Pi-class node | Method in §6. **A only (budget):** with the single-node settings (virt-operator scaled to 1 replica, KubeVirt CR `infra.replicas: 1`, CDI CR defaults), the **mean summed PSS** of every process in the `kubevirt` and `cdi` namespaces' pods over a 10-minute idle window is **≤ 800 MiB**. **Both (recorded, no budget exists):** per-machine pod PSS for the same idle guest, total and split into the QEMU process and everything else; B's control plane is zero by construction | A above 800 MiB. For B, M5 is a measurement, not a pass/fail |

### 4.3 Decision rule (what the result will recommend)

| Outcome | Recommendation written in the Results |
|---|---|
| A passes M1–M5 | Keep F-56 (KubeVirt as an optional extension), with any gaps found listed |
| A passes M1–M4 but fails M5 | Reopen F-56 as its own condition says. Name B (if it passed M1–M4) as the candidate runtime for the Edge/Pi tier, with KubeVirt kept for Lite and Pro |
| A fails one of M1–M4 that B passes | Name the failing capability and recommend B for it, or reopening F-56 |
| A test is BLOCKED for an option | No recommendation on that criterion; say so |

Whatever the outcome, the Results say that this was a Lima VM on an Apple M5 Max with nested virtualization, not a Pi 5, and that LT-MACH-1…3 on real hardware are still required before F-56 and F-58 are closed.

**Verdict per option:** PASS if M1–M5 all pass (M5 for B is recorded). A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. A failure caused by a lab-script bug is logged, the bug is fixed and that option's whole M1–M5 sequence is repeated; the failed attempt's logs are kept.

### 4.4 Exploratory (not pass/fail; labelled E-x in the Results)

- **E1 freeze matters:** the M3 (c) marker test repeated with a disk copy taken **without** a freeze, for both options: is the marker there, and is the filesystem clean?
- **E2 CPU accounting:** what A and B charge against `requests.cpu` for a 2-vCPU machine, and what KubeVirt adds to the pod's memory request and limit on top of the guest's 1 GiB.
- **E3 install and removal (LT-MACH-1 shape):** time from applying the KubeVirt and CDI manifests until every component is ready; after removing them, any pod, CRD, webhook, API service or namespace left behind.
- **E4 idle CPU** of A's control plane over the M5 window.
- **E5 upstream defaults:** A's control-plane PSS with the unmodified upstream replica counts (3-minute window).
- **E6 CDI checksum:** whether CDI v1.66.1's `DataVolume` HTTP source has a checksum field (`kubectl explain`), and if it does, whether a wrong value stops the import and leaves no PVC (machines.md MACH-5 assumes this).
- **E7 B without a freeze timeout:** QEMU's agent has no automatic thaw; KubeVirt's freeze has `unfreezeTimeout`. Record what each does if the caller never thaws (A: wait for the timeout; B: noted, not left frozen).
- **E8 glue size:** lines of lab manifests and scripts each option needed, as a rough proxy for "code OneMind must own".

## 5. Order of the run

1. Create the Lima VM, verify `/dev/kvm` (T1), install k3s, fetch and verify every pin (T0).
2. Baseline: k3s alone idle, 10-minute window (PSS of k3s and its pods, node `MemAvailable`).
3. Option **B**: build its image, M1 → M2 → M3 (+ E1, E7) → per-machine part of M5 → M4. Remove B.
4. Option **A**: install KubeVirt + CDI (E3 timing), E5 window with upstream defaults, switch to single-node settings, M5 control-plane window (+ E4), then M1 → M2 → M3 (+ E1, E7) → per-machine part of M5 → M4, E6. Remove A (E3 leftovers).
5. Copy masked evidence out, delete the VM.

B runs first so that its measurements are taken on a node with no KubeVirt installed.

## 6. Design and method

- **Host isolation:** everything runs inside one disposable Lima VM `machlab` (`template:debian-13`, the Debian 13 arm64 cloud image pinned by Lima 2.3.0, `vz`, `nestedVirtualization: true`, **4 vCPU / 4 GiB** = Pi 5 4 GB sizing, 40 GiB disk). Its only host mount is the lab work folder `<lab-dir>/machines-spike`. Nothing is installed on the Mac. The VM is deleted when the spike ends. Only one lab VM exists at a time.
- **k3s:** single server node, `--disable traefik,servicelb,metrics-server` (not used here), swap off, default `local-path` storage and flannel.
- **Tools inside the VM** (Debian packages, apt-verified, versions recorded): `podman` (builds B's image, then `k3s ctr images import`), `chromium` (headless browser), `qemu-utils`, `btrfs-progs`, `xfsprogs`, `e2fsprogs`, `jq`, `socat`, `cloud-image-utils`. Python stdlib only; Chromium is driven over `--remote-debugging-pipe`, so no Python package is installed.
- **Image import:** the verified Fedora qcow2 is served once from the node over HTTP to CDI (A) and mounted read-only into B's init container (B).
- **Memory method (M5):** for each pod, every PID in its cgroup tree is summed: `Pss` from `/proc/<pid>/smaps_rollup`, plus the pod cgroup's `memory.current` and `memory.stat` `anon`. Samples every 30 s. Control plane: 2-minute settle after all pods are Ready, then a 10-minute window; mean and max reported. Per machine: 3-minute settle after the guest agent connects, then a 5-minute window, guest idle at the login prompt. Node `MemAvailable` is sampled at the same times. CPU: `utime+stime` of the same PIDs at the start and end of the window.
- **Console method (M2):** the console page and noVNC files are served from the VM on `127.0.0.1`. A: page → `kubectl proxy` (holds the credential, as the gateway broker would) → kube-apiserver → virt-api `…/virtualmachineinstances/<name>/vnc`, WebSocket subprotocol `plain.kubevirt.io`. B: page → QEMU's WebSocket VNC port on the pod's ClusterIP. The page computes the canvas statistics in JavaScript. Screenshots come from DevTools `Page.captureScreenshot`.
- **Freeze method (M3):** the SSH session for (b) is opened before the freeze. Host-side timestamps are recorded for freeze, the write's start and completion, the copy, and thaw. The thaw is sent once the copy has finished and at least 30 s after the freeze. The disk copy is made on the node from the PVC's directory under `/var/lib/rancher/k3s/storage/`. It is checked through a read-only loop device; the guest is never mounted read-write from outside.
- **Secrets:** the SSH key pair and any token are generated in the VM at run time and deleted with it. Logs are masked before they are committed (pod and node addresses, which are private ranges, become `<pod-ip>` / `<node-ip>`).

## 7. Fidelity limits (written before the run)

| This lab shows | It does not show |
|---|---|
| Both runtimes on the same k3s, arm64, with the same guest image and size | A Pi 5: the lab VM runs on an Apple M5 Max under Virtualization.framework with nested virtualization. Cores are much faster than a Cortex-A76, so times are not Pi times. The Debian kernel uses **4 KiB pages**; the Pi 5 kernel uses 16 KiB pages (machines.md §4.11 risk), which changes memory figures and is not tested here |
| Memory of each approach's processes on a 4 GiB node | A real Pi's whole-system budget with OneMind's own services; real-hardware timings. The host is shared with other agents' VMs and was heavily loaded when this was written, and an earlier spike found nested KVM on this host erratic (`../aarch64-gate/` §7.1), so timings are observations only |
| Linux guest boot, browser console, agent freeze, namespace quotas | Windows (TPM, secure boot), USB or GPU passthrough, LAN bridge, live migration, multi-node placement, sound or clipboard |
| A consistent point-in-time raw copy | restic backups, a snapshot API, or a restore that boots (LT-MACH-6) |
| The console through a stand-in proxy and headless Chromium | The gateway's ticketed broker, a phone, touch input, a real desktop browser |
| B as a lab-grade service | A product-grade B: its security posture (privileged or not, no auth on the WebSocket port inside the cluster) is recorded, not designed |

## 8. Glossary

| Term | Meaning |
|---|---|
| KubeVirt | An open-source (Apache-2.0) add-on that runs virtual machines as Kubernetes objects; it drives QEMU through libvirt inside a "launcher" pod per machine |
| CDI | Containerized Data Importer: KubeVirt's companion that downloads and converts disk images into storage volumes |
| QEMU / KVM | The emulator that runs the machine, and the Linux kernel feature that makes it run at near-native speed |
| Nested virtualization | A VM that can itself run VMs with hardware acceleration |
| noVNC | A browser library (MPL-2.0) that shows a remote screen over a WebSocket |
| Guest agent | A small program inside the machine that the host can ask to flush and freeze its disks |
| Freeze / thaw | Pausing all writes to the machine's filesystems for a moment, so a copy taken then is consistent, then resuming |
| ResourceQuota | A Kubernetes limit on how much CPU and memory everything in one namespace may claim |
| PSS | Memory a process uses, with shared pages divided among the processes that share them |

---

## Results

### Run status (added 2026-11-12, agent B; nothing above this heading changed)

The tests above were **not run**. The session that continued this spike had no `/dev/kvm`, no Docker daemon and no access to `quay.io`. M1-M5 are BLOCKED, not PASS or FAIL. What could be checked, the extra criteria and the recommendation are in [PREREGISTRATION-ADDENDUM.md](PREREGISTRATION-ADDENDUM.md) and [RECOMMENDATION.md](RECOMMENDATION.md). Deviation: the addendum was committed after some manifests and docs had been read (disclosed in its section 0).
