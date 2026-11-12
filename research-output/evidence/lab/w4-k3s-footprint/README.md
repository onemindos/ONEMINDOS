# Spike W4-1: k3s vs Podman idle footprint on a 4 GiB arm64 node

**Owner:** W4 · **Written before running:** 2026-11-10 · **Serves:** N-9, N-2, F-14, M-6 · **Bank:** Q125, Q19, Q44, Q154 · **DC-10**

## Goal
Measure, on a disposable 4 vCPU / 4 GiB aarch64 Debian 13 VM (a stand-in for a 4 GB Pi 5; QEMU/HVF, not real Pi silicon):
1. RAM left for apps (`MemAvailable`) with (a) the bare OS, (b) Podman running a 2-container reference app, (c) k3s v1.37.2+k3s1 default single-server (SQLite) idle, (d) k3s with the same reference app, (e) k3s "slim" (traefik, servicelb, metrics-server disabled) with the app.
2. Steady-state disk writes (bytes/day, extrapolated from a 10-minute window of `/proc/diskstats` sectors written).
3. Time from `systemctl start k3s` to node Ready and to all kube-system pods Ready.
4. CPU use at idle (from `/proc/stat` over 5 minutes).

## Hypothesis (DC-10)
k3s single-server with SQLite leaves at least 2 GiB of a 4 GiB node available to apps, and writes well under 5 GB/day at idle; Podman leaves several hundred MiB more and writes less.

## Pass / fail (fixed before running)
- **k3s PASS for the 4 GB tier** if `MemAvailable` with k3s + reference app (state d) is **≥ 2.0 GiB**, **and** steady-state writes in state (d) are **≤ 5 GB/day**.
- **FAIL (DC-10 flip condition met)** if either threshold is missed.
- 5 GB/day is a judgement threshold: about 9 TB over 5 years, which is inside the endurance of a typical 64 GB eMMC/industrial SD in pSLC mode and far inside any NVMe SSD. It is not a vendor figure.

## Limits
VM, virtio disk, Apple Silicon host: absolute CPU and timing numbers do not transfer to a Pi 5. RAM numbers transfer approximately (same arm64 binaries). Writes include the guest's own journald. One run each, no repetition. A real Pi 5 + NVMe/SD test is in `22-HARDWARE-LAB-TEST-PLAN.md`.

## Pinned inputs
- Lima 2.3.0, template `debian-13` (Debian 13 genericcloud arm64 20261103-2651, sha512 pinned by Lima), `mounts: []`, no credentials.
- k3s `v1.37.2+k3s1` `k3s-arm64` from the GitHub release, verified against the release's `sha256sum-arm64.txt`.
- Podman from Debian 13 main (version recorded in the log).
- Reference app: `docker.io/library/nginx:1.29-alpine` and `docker.io/library/redis:8-alpine` (digests recorded in the log).
