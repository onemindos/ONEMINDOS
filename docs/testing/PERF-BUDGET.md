<!-- SPDX-License-Identifier: Apache-2.0 -->
# Hub performance budget (CORE-NET-14)

> **Status: VM-measured, UNVERIFIED on a real Pi (F-25 hardware pending).** Every number below came from a GitHub arm64 virtual machine (4 vCPU, 16 GB), not from a Raspberry Pi 5. A Pi has slower storage and a slower memory bus, so latency and start-up there will be worse. Memory is the number most likely to carry over. Do not quote these as Pi results.

> **Explain it like I am the founder**
> A *budget* is a ceiling we agree on before we ship: "the hub's own services may use at most this much memory, and answer in at most this many milliseconds." If a change pushes past it, CI goes red and we have to either fix the change or consciously raise the budget. That stops the hub from slowly getting fatter until it no longer fits a 4 GB Pi.
> *p95 latency* means "95 out of 100 requests were at least this fast"; it shows the slow tail that users feel, which an average hides.
> *Anon memory* (the number we budget) is memory a process owns privately and cannot give back without swapping. We leave out the page cache, which Linux hands back whenever something needs it.

## What is measured, and how

`deploy/install.sh --role hub` installs the real hub on the runner. Then `test/perf/perf.py` (standard library only) reads each service's cgroup, so the numbers are per component rather than a single "the box". The workflow is [`.github/workflows/perf-smoke.yml`](../../.github/workflows/perf-smoke.yml); it takes about 6 minutes, runs on changes under `deploy/`, `core/`, `cmd/`, `internal/`, `dashboard/`, `apps/` and `test/perf/`, and on every push to `main`.

1. **Idle:** settle 120 s, sample memory and CPU for 60 s, then 300 reads of the routes the dashboard polls (`/healthz`, `/v1/instance`, `/v1/nodes`, `/v1/apps`, `/v1/actions`).
2. **Load:** three simulated nodes heartbeating over NATS, 60 approval cycles (create then deny, so nothing is actuated), with reads going at the same time.
3. **Cold start:** restart `onemindd` and the gateway and time until `/healthz` answers.

Not in the quick CI run (they need image pulls or a reboot): app installs, boot-to-ready and disk. `perf.py` has the commands (`load --apps`, `boot-probe`, `disk`) for the lab run on the Pi.

## Measured (run 3 of PR #68, 2026-11-12) and the budget

| Metric | Measured | Budget (fails above) |
|---|---:|---:|
| Hub total, idle (anon MiB) | 758 | 1000 |
| k3s (server, containerd, shims) | 621 | 820 |
| k3s add-ons (coredns, traefik, metrics-server, local-path) | 56 | 80 |
| Gateway (Python) | 75 | 100 |
| `onemindd` | 4.7 | 10 |
| NATS | 3.6 | 8 |
| API read p95, idle (ms) | 19.9 | 40 |
| API read p95, under load (ms) | 20.3 | 45 |
| API read errors | 0 | 0 |
| Gateway cold start to `/healthz` (s) | about 2 (journal) | 10 |

The budget is roughly 1.3x to 2x the measurement. A shared CI VM is noisy and a budget that flaps teaches people to ignore red, so it is set to catch real regressions (a new service, a leak, a slow query), not 5 % wobble. Latency gets the wider margin because it is the noisiest. Revisit the figures after the first 10 runs and tighten them.

## What it means for the Pi 5 (arithmetic, not measurement)

| Pi 5 | RAM | Hub at budget | Left for apps and the OS |
|---|---:|---:|---:|
| 4 GB | about 3.9 GB usable | 1.0 GB | about 2.9 GB, minus kernel, page cache and the OS itself |
| 16 GB | about 15.8 GB usable | 1.0 GB | about 14.8 GB |

k3s is 80 % of the hub, which is why the plan keeps one Kubernetes server on the hub only. CPU was not budgeted: on a shared VM it is mostly noise, and `perf.py` still records it (`idle_cpu_pct.*`) for the Pi run. The VM was not constrained to 4 GB (`--memory` would not change the anon figures, only kill the process if they grew past the limit); the Pi lab run applies the real 4 GB and 16 GB boards.

## Running it yourself

```sh
sudo python3 -I test/perf/perf.py token --out /root/perf/token     # throwaway owner principal, throwaway hub only
sudo python3 -I test/perf/perf.py idle --token-file /root/perf/token --out idle.json
sudo python3 -I test/perf/perf.py sims start --count 3
sudo python3 -I test/perf/perf.py load --token-file /root/perf/token --out load.json
python3 -I test/perf/perf.py check --budget test/perf/budget.json idle.json load.json
```

Only use it on a test hub: it adds an owner principal and starts extra `onemindd` units. Unit tests for the arithmetic: `python3 -m pytest test/unit/test_perf_budget.py`.

## Open

- **Real Pi numbers** (F-25 hardware): run the lab commands above on a Pi 5 4 GB and 16 GB, replace the VM column, drop the UNVERIFIED label.
- **Boot-to-ready, app install time and disk** are measured by the lab run only.
- The CI hub is Ubuntu 24.04 with `--force-os`; the shipping base is Debian 13 (D-007). Re-measure on the Debian image once the image line produces one.
