<!-- SPDX-License-Identifier: Apache-2.0 -->
# Addendum to the machines-spike pre-registration (written before the recommendation)

**Serves:** UMB-MACH-1, founder decision F-56 (KubeVirt vs own QEMU + noVNC). Written 2026-11-12 by agent B, **committed alone before the recommendation is written**. It does **not** edit the frozen [README.md](README.md) (its sha256 in `PREREGISTRATION.sha256` stays valid). It adds the criteria the founder's brief asked for that M1-M5 do not cover (licence, security model, approval gating, maintenance), and says up front which of M1-M5 can run in this session.

> **Plain language.** The first pre-registration needs a real virtual-machine host (a Lima VM with hardware virtualization on an Apple Mac). This session runs in a cloud container with no `/dev/kvm`, no Docker daemon and no access to the container registry that serves KubeVirt's images. So most "does it run" tests cannot run here. We write down now what we will judge, what we can honestly check without a hypervisor, and what stays "UNVERIFIED" until someone runs the lab on real hardware.

## 0. Honest disclosure of what was seen before this addendum

Before this file was written the agent had already: merged `origin/main` into the branch; downloaded KubeVirt v1.9.1 `kubevirt-operator.yaml` and `kubevirt-cr.yaml` and CDI v1.66.1 `cdi-operator.yaml` and compared their sha256 with the pins in README T0 (all three match); read the manifests' Deployment resource requests; read the KubeVirt user-guide pages on installation, Arm64 limits, snapshots and VNC access; and run a QEMU process under software emulation (TCG) on this x86_64 container to see the order of magnitude of a QEMU process's memory. None of these results decided the thresholds below, but they are not blind.

## 1. Environment limits found (recorded, not guessed)

| Fact | Evidence (this session) |
|---|---|
| No `/dev/kvm`, no `vmx`/`svm` CPU flag | `ls /dev/kvm` fails; `grep -c -E 'vmx\|svm' /proc/cpuinfo` = 0 |
| x86_64 container, 4 vCPU, 16 GiB; not arm64, not a Pi | `uname -m`, `nproc`, `free` |
| No Docker daemon, `quay.io` refused by the proxy | `docker info`, `docker manifest inspect` |
| Debian mirror refused; Ubuntu 24.04 archive reachable | `apt-get` |
| GitHub release asset API (`api.github.com`) refused; release download URLs and `raw.githubusercontent.com` work | `curl` |

So M1 (boot), M2 (browser console), M3 (freeze), M4 (quota) and the KubeVirt half of M5 are **BLOCKED here**: they need KVM or the KubeVirt images, plus k3s. They are **not** called PASS or FAIL. They stay for the real-hardware lab (LT-MACH-1...3).

## 2. Criteria for this deliverable (B7-C1 ... B7-C8)

| ID | What is measured or checked | Method that can run here | Threshold | Status of method |
|---|---|---|---|---|
| B7-C1 | Idle RAM overhead of the control plane on a 4/16 GB Pi 5 and an x86 mini-PC | Real: README M5 (summed PSS). Here: only the **declared** requests in upstream manifests, and a QEMU process under TCG | Pi 5: KubeVirt + CDI **mean PSS <= 800 MiB**; x86: **<= 1 GiB** (LT-MACH-2, machines.md 4.12); B has no control plane | Real measurement BLOCKED; declared requests are a hint only |
| B7-C2 | arm64 support (Pi 5, Jetson-class) | Upstream docs | PASS if upstream documents arm64 for the VM features OneMind needs (headless Linux guest, console, snapshot with agent, cloud-init); any documented hole is listed | Docs read |
| B7-C3 | Install footprint | Count CRDs, Deployments, images in upstream manifests; installed size of B's packages | Report; PASS if the add-on is optional, and removable with no leftovers (LT-MACH-1: <= 5 min up, no pods/CRDs/webhooks after removal) | Counts here; timing/removal BLOCKED |
| B7-C4 | Licence compatibility with an Apache-2.0 repo | Read `LICENSE` of each component at the pinned tag | PASS if no copyleft code is linked into or copied into the OneMind tree; copyleft components (QEMU GPL-2.0, noVNC core MPL-2.0) run as separate programs or unmodified npm dependency | Runnable |
| B7-C5 | Isolation and security model | Upstream architecture and install docs; README 3 for B | PASS if privileged parts are a short named list and a guest runs unprivileged, with per-machine network policy possible; B must say how it gets `/dev/kvm` | Docs read |
| B7-C6 | Approval-gated actions: the AI never actuates without a human | Map machine verbs to OneMind's declarative action model (a rendered object with a `plan_sha256` the owner approves); check the runtime exposes console/VNC as a separately authorised verb | PASS if create/start/stop/delete/devices render to objects the gateway can hash and approve, and console/control use their own permission | Docs + design |
| B7-C7 | Maintenance burden | Lines of lab glue per option (committed scripts, `wc -l`); upstream release cadence and project health | Lower is better; report; upstream health from the repo if reachable, otherwise UNVERIFIED | Glue lines runnable; cadence UNVERIFIED if API blocked |
| B7-C8 | Tier fit (Edge Pi 5 / Lite N150 / Pro) | Combine C1-C7 | See decision rule | Derived |

## 3. Decision rule (fixed now)

1. If a **real** M5 measurement exists and A > 800 MiB on Pi 5: recommend B for the Edge tier and KubeVirt for Lite and Pro (the README rule).
2. If no real measurement exists (the case in this session): **no runtime may be declared the winner on memory.** The doc lists A as "keep F-56, conditional on LT-MACH-2" only if C2-C6 pass for A, and names B as the fallback. The decision stays with Zeus.
3. If A fails C2, C4 or C5, the recommendation says so and does not rely on LT-MACH-2.
4. UNVERIFIED items are never promoted to facts in the summary.
5. TCG (software emulation) numbers are only reported as TCG, never as the cost of a KVM machine.
