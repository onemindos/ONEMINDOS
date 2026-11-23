# QEMU battery, edge profile: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-22 before the harness it judges (`edge.py`) or the edge changes it tests (the leaf health check, the k3s skip on a leaf) existed. Its sha256 at that moment is in `PREREGISTRATION.sha256`. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to `results.json` and CI logs).

**Serves:** issue #751 (edge profile, part of #170): an edge is the **same image** as every other box (founder decision, plan PLAN-V2 §"One image on every machine") with the role `leaf` picked at install. It runs `onemindd`, the NATS leaf (own JetStream domain, capped outbox, #472/#532) and RAUC with the same health gate, and **no** k3s server, gateway, hub NATS, Headscale or dashboard. **Does not replace** `CRITERIA.md` (the T-battery stays the hub's update gate) or the founder's Pi 5 lab kit (real hardware, real join, real uplink loss).

## 1. Starting state and rules

- The battery's fixtures for the board, made with `EDGE=1` (`make fixtures BOARD=x86_64-efi EDGE=1`), which adds one bundle: **`bad-leaf`** (version 8), the `good` tree with `/usr/bin/onemindd` replaced by a program that exits 1 at once. Nothing else in the tree changes.
- One VM, 3072 MiB RAM, 4 vCPU, the fixture disk copied into the work folder (the T-battery fixtures stay untouched). A NoCloud seed (label `CIDATA`) holds `onemind: {role: leaf, join_code: <a well-formed leaf join code for a hub that does not exist>, hub_addr: 192.0.2.10}` (TEST-NET-1, RFC 5737). The join therefore never completes; nothing here depends on it.
- "Hub services" means these units: `k3s`, `onemind-gateway`, `onemind-gateway-kube`, `onemind-nats`, `onemind-headscale`, `onemind-mesh-setup`, `onemind-starting`.
- "Hub secrets" means these paths: `/data/onemind/gateway/tokens.yaml`, `/data/onemind/identity/ca.key`, `/data/onemind/gateway/tls/ca.key`, `/data/onemind/nats/keys`, `/data/onemind/etc/headscale.key`, `/data/k3s/server/token`, `/data/k3s/server/tls`.
- A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. Every verdict records the board, KVM or TCG, and the host CPU count.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| EG1 | First boot as an edge | Within the timeouts the console shows `ONEMIND-FIRSTBOOT: configured role=leaf source=nocloud` and **no** `ONEMIND OWNER TOKEN` line; the gate logs `RESULT committed-boot slot=A version=1` | Either line missing, or an owner token printed |
| EG2 | Restart: no hub service runs | After one `systemctl reboot` with no input: the console shows `ONEMIND-FIRSTBOOT: already configured role=leaf`; `systemctl is-active` is not `active` for every hub service; `systemctl show -p Result --value k3s` prints `exec-condition` (k3s skipped itself, it did not crash); nothing listens on TCP 6443, 10250, 8080, 8443, 8444 or 7422; `/data/k3s` does not exist | A hub service active, k3s with any other result, one of those ports listening, or `/data/k3s` present |
| EG3 | Edge services and no hub secret | `onemindd` is `active` and `curl http://127.0.0.1:7480/healthz` returns a body containing this boot's `boot_id`; none of the hub secrets exists | `onemindd` not active, a stale or missing `boot_id`, or any hub secret present |
| EG4 | The gate uses the leaf check | On the EG2 boot the gate logs `LEAF-FRESH ok` (committed boot, check for the log only); running `/usr/lib/onemind/onemind-leaf-check` by hand exits 0 and prints a line starting with `ok (` | No `LEAF-FRESH ok`, a `K3S-FRESH` line on this boot, or the hand-run check failing |
| EG5 | Good update on an edge | `good` (v2) installs to B; on the trial boot the gate logs at least 3 `CHECK pass n/3` lines that name `onemindd`, then `RESULT mark-good slot=B version=2` | No commit, fewer than 3 passes, a pass line from the k3s check, or the wrong slot |
| EG6 | Bad update on an edge rolls back | `bad-leaf` (v8) installs to A; with no input the gate logs `RESULT mark-bad slot=A version=8` with `verdict=image-bad` at the deadline, the box reboots to `RESULT committed-boot slot=B version=2`, and grubenv shows `A_OK=0` | A commit of A, a hang, any input needed, another verdict, or the bundle missing from the fixtures |
| EG7 | Memory against the 300 MiB target (recorded) | Recorded, not judged: on the EG2 boot, after the gate's result and 60 s of settling, the box's used memory (`MemTotal - MemAvailable`) and the sum of `MemoryCurrent` of `onemindd`, `onemind-nats-leaf`, `tailscaled`, `onemind-fabric-join`, `onemind-local-api` and `onemind-firstboot`; the verdict is `RECORDED` with `within` or `over` against 300 MiB for the box's used memory | Never FAIL; `BLOCKED` if the numbers cannot be read |

## 3. What these tests do not cover (reported, never claimed)

- A **joined** edge: the NATS leaf with its own JetStream domain, the capped outbox and 30 minutes without uplink need a hub on the other end (two VMs, or the founder's Pi 5 kit). The leaf config and the outbox cap are covered by the Go tests in `internal/leaf`.
- The join time with the owner's approval (under 5 minutes on a Pi 5) and the real QR flow: the founder's lab kit.
- An OCI runner under systemd: not in this image yet (issue #751 lists it; it lands in a later PR on the same issue).
- Real hardware memory (Pi 5 kernel, 16 KiB pages): EG7 is a VM number, UNVERIFIED on a Pi.
