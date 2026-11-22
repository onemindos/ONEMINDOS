# QEMU battery, memory pressure: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-21 before the harness it judges (`memorypressure.py`) was ever run against an image. Its sha256 at that moment is in `PREREGISTRATION.sha256`. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to `results.json` and CI logs).

**Serves:** the P0 item "protect the control plane from memory and disk pressure" of the 2026-11-21 image audit (a big app on an 8 GB box must not make the kernel OOM killer pick k3s, NATS or the gateway), D-007, and the daily-use goal (#234). Design: `os/rootfs/layers/base/etc/systemd/zram-generator.conf`, the `*.service.d/10-onemind-memory.conf` drop-ins, `etc/rancher/k3s/config.yaml.d/10-onemind-reserve.yaml`. **Does not replace** `CRITERIA-FIRSTBOOT.md`: it uses the same first boot as a hub, on a bigger VM.

## 1. Starting state and rules

- One VM of **8192 MiB** RAM (`ONEMIND_QEMU_MEM=8192`), 4 vCPU, first boot as a hub with the NoCloud seed of `firstboot.py`, no other disk change. The harness waits for the health gate and `/healthz` = 200 before anything else.
- "Control plane" means these units: `k3s`, `onemind-nats`, `onemind-gateway`, `onemindd`.
- "The hog" is one transient systemd unit (`onemind-memhog`) running the gateway's own Python to allocate and touch **6 GiB** of memory (half of it compressible), hold it for 90 s, then exit. It stands in for a big app (an LLM, Immich).
- "Probe" means one `curl -m 3` of `http://127.0.0.1:8080/healthz` from inside the guest, every 2 s, from before the hog starts until 20 s after the hog unit ends.
- A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. Every verdict records the board, KVM or TCG, and the host CPU count.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| M0 | Protection is in place before the load | `MemTotal` is at least 7.5 GiB; `swapon` lists a `zram` device; `vm.swappiness` is 100; each control-plane unit's main process has `oom_score_adj` -900; the unit's cgroup `memory.min` is above 0; the kubelet reports node capacity minus allocatable memory of at least 1 GiB (the reserves); `/data` is mounted with `noatime`; the journal's `SystemMaxUse` is 500M | Any of these is missing |
| M1 | 6 GiB hog on the 8 GiB VM | During the whole window: at least 30 probes ran and **every probe returned 200**; for each control-plane unit the main PID and `NRestarts` are the same before and after; the kernel log shows no OOM kill of a control-plane process (`k3s`, `nats-server`, `python3` from the gateway venv that is the gateway, `onemindd`); `/healthz` is 200 at the end | One failed probe, a changed PID or restart count, an OOM kill of a control-plane process, or fewer than 30 probes |

The hog itself may finish or be killed by the OOM killer: both are recorded as information and neither decides M1 (the point is who survives, not whether the app does).

## 3. What these tests do not cover (reported, never claimed)

- A real app pod under a kubelet memory limit (the hog is a host process; pod eviction is the kubelet's job and is not driven here).
- Disk pressure: a full `/data` is not simulated. `journald` and `noatime` are checked as configuration only (M0), not as measured write reduction.
- Real hardware (16 GB all-in-one, SD or NVMe storage, thermal limits).
