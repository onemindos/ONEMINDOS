<!-- SPDX-License-Identifier: Apache-2.0 -->
# 2-VM network proof: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-12 before the harness `test/net/two_vm.py` existed and before any run of it. The sha256 of this file at that moment is in `PREREGISTRATION.sha256` and in the commit that adds it (a separate commit, before the harness; same rule as `test/qemu/CRITERIA.md`). Nothing in this file may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here: they go to `test/net/results/` (local) and the CI artifact `net-2vm-results`.

**Serves:** CORE-NET-11 (mesh-first installer), CORE-NET-12 (gateway and `onemindd` wiring), hardening H-05 (no plain HTTP on the LAN), H-06 (NATS leaf with TLS and per-node credentials), H-34 (proxy strips identity cookies); NETWORKING.md tests NT-1, NT-3, NT-4, NT-6, NT-8 (parts). **Source of the steps and criteria:** the Lima lab `research-output/evidence/lab/net-p2/` (PASS at commit `ac55dd751ba5`, criteria NP-1 to NP-8). This file reuses them in substance and moves them onto a CI-runnable x86-64 QEMU pair.

> **In plain words.** Two fresh Debian 13 virtual machines on one private virtual cable. One becomes the hub with `deploy/install.sh`. The owner makes a one-time join code on the hub. The other machine joins with it, the owner approves, and the test then checks that the private mesh works, the event bus link is encrypted and uses the node's own login, the hub does not serve plain HTTP to the LAN, and an app opened over HTTPS through the hub's proxy never sees the hub's login cookies.

## 1. Setup and rules

- Two VMs from the pinned Debian 13 `genericcloud` amd64 image (`test/net/image.pin`, sha512 checked). Hub: 4 vCPU, 4 GiB. Node: 2 vCPU, 2 GiB (CI default; `--hub-mem` and `--node-mem` lower them for a laptop). KVM when `/dev/kvm` is usable, else TCG; the run records which, and the host CPU count, with every verdict (wall-clock deadlines depend on it).
- Network: each VM has NIC 1 on QEMU user-mode networking (internet for package and k3s downloads, SSH forward on loopback) and NIC 2 on a private QEMU socket link that exists only between the two VMs. The private link uses the documentation range `198.51.100.0/24` (hub `.1`, node `.2`). The mesh range the installer's Headscale hands out is the shared CGNAT range; the harness identifies it by property (not global, not RFC 1918) and never writes it as a literal.
- Source under test: the tree of the checkout (or `ONEMIND_NET_SRC_REF`, a commit-ish, to test another tree with this harness). `onemindd` is built on the host and passed to `install.sh --onemindd-bin`; the dashboard is the core test fixture (`core/tests/fixtures/dist`; this suite is about networking). Everything else is downloaded inside the VMs by `install.sh` with its sha256 pins. `install.sh` and `core/` are called as they are; the harness never edits them.
- Keys, tokens and certificates are created inside the run (owner token by the installer, join code by the hub) and die with the VMs. Dumps mask 64-hex strings and join codes.
- **Result states.** PASS: the check ran and held. FAIL: the check ran and did not hold. BLOCKED: the check cannot run because something it depends on is not in the source tree or not up, with the reason and, where possible, what was observed instead. BLOCKED is never PASS and is never hidden: the suite verdict is PASS only when every criterion is PASS; FAIL if any is FAIL; otherwise BLOCKED. A harness (driver) bug is named as such in the results and may be re-run once.
- **Prerequisite probes** (recorded, never judged by themselves). A criterion is BLOCKED, not FAIL, only when one of these probes shows the feature it checks is not in the tree:
  - **P-INSTALL** `deploy/install.sh --help` lists `--join` (the mesh-first installer with owner-approved join, CORE-NET-11).
  - **P-ROUTER** `core/onemind_core/app.py` mounts the net router (`routers/net.py`), and a signed-in `GET /v1/fabric` on the hub answers 200 rather than 404 (CORE-NET-12).
  - **P-CLI** the `onemind` CLI on the hub offers `fabric ticket` and `fabric approve`.
- **Fail fast.** The harness stops at once, marks the running criterion FAIL (or BLOCKED for a harness bug), and dumps both VMs' journals and consoles when it sees a kernel panic, oops, out-of-memory kill, a dead QEMU process, or a command exceeding its stage deadline (hub install 1500 s, node join 900 s, other stages 300 s or less).

## 2. Criteria

| ID | Criterion | PASS if | FAIL if | BLOCKED if |
|---|---|---|---|---|
| N2-0 | Harness: two VMs on the private link | Both VMs boot and answer SSH; `cloud-init status` is `done`; hub and node ping each other on `198.51.100.0/24` | Any of these missing within 300 s per VM | n/a (an environment that cannot boot QEMU fails the run as a harness error) |
| N2-1 | Hub install | `install.sh --role hub` (with `--box-name box1 --lan-addr 198.51.100.1` when P-INSTALL holds) exits 0; the owner token is printed; the gateway answers `/healthz` on loopback inside the hub | Non-zero exit, no owner token, or no healthz within 120 s of the installer's end | n/a |
| N2-2 | Join: node appears in hub fabric status | The owner's `onemind fabric ticket` on the hub issues a code; `install.sh --role node --join <code>` on the node prints a match code and waits; the hub's `GET /v1/fabric` lists that request with the **same** match code; `onemind fabric approve` approves it; the node installer exits 0; `GET /v1/fabric` then lists the node id (from the node's `/etc/onemind/fabric.json`) among `nodes` with a state other than `joining` | Any step fails: codes differ, installer exits non-zero, node never listed | P-INSTALL, P-ROUTER or P-CLI does not hold |
| N2-3 | Mesh: IPs assigned, reachable | Hub and node each have a mesh IPv4 (`tailscale ip -4`) in the shared CGNAT range, the two differ, the node pings the hub's mesh IP and the hub pings the node's mesh IP (3 packets each, 0 loss) | No address, wrong range, same address, or loss | N2-2 did not PASS (no joined node to test) |
| N2-4 | NATS leaf: TLS and per-node credentials (H-06) | The hub's `/leafz` (monitor port, loopback) lists exactly one leaf whose account is `NODE_<node id>` and whose remote address is the node's mesh IP; the leaf listener `:7422` is bound to the hub's mesh IP only (not a wildcard address); the listener's first INFO line says `tls_required` true; a TLS client with no node certificate cannot complete a leaf handshake | Any of these not true | N2-2 did not PASS |
| N2-5 | Hub does not serve plain HTTP to the LAN (H-05) | On the hub, no TCP listener bound to a wildcard address (`0.0.0.0` or `[::]`) answers a plain HTTP `GET /healthz` with 200 when probed from the **node** at the hub's LAN address `198.51.100.1` (ports 22, 6443 and 10250 are skipped: not plain HTTP); additionally the gateway port `8080` is not bound to a wildcard address. Port 80, if open, may answer only a redirect (3xx) | Any plain-HTTP 200 on the LAN address, or `:8080` bound to a wildcard | P-INSTALL does not hold (the old developer installer binds the gateway to all addresses by design; the observed listeners are still recorded as evidence) |
| N2-6 | HTTPS through the per-app proxy (H-29, H-34) | An approved `app.install` of `vaultwarden` completes; from the node, `https://vaultwarden.box1.local/` (resolved to the hub's LAN address, box CA from `GET /v1/tls/ca.crt?format=pem`) answers 401 without sign-in and 200 with the owner token as a bearer; the same request without the box CA fails the TLS handshake | Any answer other than these, or a handshake that succeeds without the CA | P-INSTALL or P-ROUTER does not hold, or N2-2 did not PASS |
| N2-7 | Identity cookies stripped (H-34) | With the app's backend replaced by an echo pod (a busybox CGI that prints its `Cookie` header, placed behind the app's own Service), a request through the proxy carrying `__Host-onemind_session=x; __Host-onemind_csrf=y; onemind_session=z; keep=1` plus the owner bearer reaches the echo with `keep=1` and with **none** of the three `onemind` cookie names | The echo sees any cookie whose name starts with `onemind_` or `__Host-onemind_` | N2-6 did not PASS, or the echo pod could not be placed (reason recorded; never counted as a pass) |

**Verdict rule.** The suite PASSES when N2-0 to N2-7 are all PASS in one run on fresh VMs. A run with no FAIL and at least one BLOCKED is reported BLOCKED and exits 0 unless `--strict` (CI sets `ONEMIND_NET_STRICT=1` once the blocking changes have merged); with any FAIL it exits 1. Informational lines (kernel, QEMU, image sha, durations) are recorded and not judged.

## 3. Adaptations from the Lima lab (and why)

1. **x86-64 QEMU/KVM instead of Lima on Apple silicon:** the lab's criteria do not depend on the hypervisor; CI runners are x86-64 with KVM.
2. **Network:** Lima's `user-v2` switch is replaced by a QEMU socket link plus a user-mode NIC for internet. The hub's LAN address is passed as `--lan-addr` as in the lab.
3. **Narrowed to the owner's list:** the lab's k3s pod-to-pod test (NP-5), mesh port rules (NP-7), leaf liveness (NP-8) and mDNS (NP-9) are not repeated here; they stay in the lab and in later suites. NP-4's forged-subject test is replaced by the TLS-without-certificate refusal plus the per-node account name (the account is what confines a node).
4. **H-34 echo:** the lab only checked 401/200. This suite adds the echo pod so the cookie strip is observed at the upstream, not inferred.

## 4. How to run

```
python3 -I test/net/two_vm.py --results test/net/results/run1.json     # needs qemu-system-x86, qemu-utils, cloud-image-utils, ssh, and Go or Docker
ONEMIND_NET_SRC_REF=<commit> python3 -I test/net/two_vm.py --hub-mem 3072 --node-mem 1536
```

CI: `.github/workflows/net-2vm.yml` (pull requests touching net code, and manual dispatch with an optional `source_ref`).
