# W4-1 result (2026-11-11 UTC)

| State | MemAvailable (MiB of 3923) | Writes, 10 min | Writes extrapolated | CPU (all 4 cores) |
|---|---|---|---|---|
| A bare Debian 13 | 3545 | ~0 MiB | 0.07 GB/day | 0.1% |
| B Podman + nginx + redis | 3513 | ~0 MiB | 0.07 GB/day | 0.1% |
| C k3s v1.37.2 default, idle | 2615 | 12 MiB | 1.89 GB/day | 2.0% |
| D k3s default + nginx + redis | 2557 | 18 MiB | 2.75 GB/day | 2.3% |
| E k3s slim + app (4 min after restart; traefik uninstall job still running) | 2702 | 40 MiB | 6.06 GB/day (transient, not steady state) | 1.8% |

k3s node Ready 5 s after `systemctl start`; all kube-system pods Ready at 22 s. k3s-server RSS ~757 MiB at idle. SQLite db dir 30 MB after ~40 min.

Verdict against pre-registered criteria (state D): MemAvailable 2557 MiB (2.50 GiB) >= 2.0 GiB -> PASS; writes 2.75 GB/day <= 5 GB/day -> PASS.
Surprise: state E exceeded 5 GB/day, measured while the traefik helm-delete job was still running after the restart; needs a steady-state re-run before slim is quoted as a write saving.
