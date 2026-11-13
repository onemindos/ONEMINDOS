# Lab spike LAB-fb-installer-mode: OneMind agent on stock Ubuntu and stock Debian, joining the same hub as an image node

**Status:** BLOCKED (lab environment and product dependency), design pre-registered so it can run unchanged later.

**Serves:** fabric mission 02 §5 lab spike 5 and workstream FB-1 (join matrix rows "cloud servers" and "company servers"); `docs/architecture/FABRIC.md` §13 FT-1; `docs/leap` CORE-FABRIC-1, CORE-NET-9, CORE-NET-11.

> **Explain it like I'm the founder.** Many machines will never run the OneMind image: a cloud server, a company's GPU server. On those, OneMind installs on top of the normal operating system ("installer mode"). This test would put the OneMind agent on an untouched Ubuntu server and an untouched Debian server and check they appear next to an image node in one Nodes list, honestly labelled "no OS rollback". It needs three machines running at once, and the owner-approved join it should exercise is not built yet.

## 1. Why it is blocked (checked 2026-11-12 on `main` at `1c278f5`)

| Needed | State |
|---|---|
| Three machines at once (hub, stock Ubuntu, stock Debian), each running k3s or a leaf | This run may start **one** VM of at most 4 vCPU / 4 GiB on a CPU-saturated host. Running `deploy/install.sh` (k3s agent, systemd units) faithfully needs real VMs, not containers |
| The owner-approved join it should exercise (ticket, request, approval, per-node credentials) | CORE-FABRIC-1 and CORE-FABRIC-2 are `todo` (`docs/leap/STATUS.md`); `deploy/install.sh --role node` still uses a long-lived token (`docs/leap/core/FABRIC.md` §2) |

It moves to build-path phase P1 as part of CORE-NET-9 (`research-output/fabric/13-BUILD-PATH.md`), which already plans a pre-registered Lima lab with several VMs.

## 2. Pass / fail criteria (frozen now, to run later)

| ID | Test | PASS if |
|---|---|---|
| T0 | Stock images | Ubuntu 24.04 LTS and Debian 13 cloud images, unmodified, by recorded image hash; the hub is a OneMind image node (or the Debian 13 image leg until the image exists) |
| T1 | Install | `install.sh --role node` (installer mode) completes on both stock VMs with no prompt other than the join code, and changes nothing outside the paths `deploy/README.md` lists |
| T2 | Owner-approved join | Each join appears as `node.join` awaiting approval with matching board, arch, OS and pairing code; after approval both are `online` within 30 s |
| T3 | One Nodes view | `GET /v1/nodes` and the dashboard list all three with role, OS and state; both installer-mode nodes carry the "no OS rollback" label and the image node does not |
| T4 | Same rules | NATS impersonation test FT-3 and job forgery test FT-4 pass on both installer-mode nodes |
| T5 | Removal | `node.remove` on one installer-mode node revokes its credentials; the VM cannot reconnect |

## 3. Fidelity limits

VMs only; no real cloud provider, no managed Kubernetes (the DOKS/EKS/GKE path is a separate design question, `research-output/fabric/02-JOIN-MATRIX.md`).
