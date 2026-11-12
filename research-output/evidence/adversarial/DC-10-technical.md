# DC-10: refuter report on k3s on every tier (technical lens, round 4)

- **Conclusion under test (decision-critical DC-10 Result, rev. 3; 01 §4.5):** k3s runs on every platform node (≥ 4 GB RAM **and** SSD/NVMe, "or industrial eMMC with a measured endurance budget"), with a NATS leaf below that. The lab measured +936 MiB idle on a 4 GiB arm64 VM [C-LAB-k3s-footprint-restore-007]. The founder test T-W4 (30 days, hardened k3s, Pi 5 4 GB NVMe) raises the floor to 8 GB if free memory falls below 2.0 GiB or writes exceed 5 GB/day.
- **Flip condition:** k3s on a 4 GB Pi 5 leaves less than about 2 GB for apps, or writes enough per day to threaten SD/eMMC life over 5 years, while a Compose/Quadlet node can still join the same app platform.
- **Lens:** technical. I read only the conclusion, 01 §4.5 and claim C-LAB-k3s-footprint-restore-007. I formed this view before reading any other refuter file.
- **Date:** 2026-11-11

## Verdict: **weakened** (the memory side holds as measured; the write side rests on a steady state that k3s's SQLite datastore does not guarantee)

The memory figure is a real lab number, and the 4 GB slim-profile caveat is honest. The weak side is flash. T-W4 measures a **healthy** 30-day average against 5 GB/day, but k3s's single-node datastore has a documented failure mode that the soak won't trigger by chance:

1. **Baseline writes are already close to the threshold.** A k3s reporter measured about 720 MiB/day on an empty x86 node and **about 3.3 GiB/day on an aarch64 node with 11 pods**, on default config [C-REF4-DC-technical-004]. OneMind's hardened profile adds an audit policy, which writes as well. The OneMind stack (NATS, Market, dashboard, AI, apps) is more than 11 pods. A real Pi 5 could reach the 5 GB/day gate without any fault.
2. **Compaction failure is unbounded growth "by design".** When kine compaction fails on SQLite, "the database will grow without bound. That is how it works" (k3s maintainer). Reported state.db sizes reach 12 GB [C-REF4-DC-technical-006]. A regression in kine v0.13.4–v0.13.9 stopped compaction **permanently** after any SQL error on the first attempt [C-REF4-DC-technical-007]. A stalled compactor turns into steady extra WAL and page writes plus API timeouts, on exactly the small, slow-storage boxes this tier targets.
3. **The tested envelope.** k3s maintainers say they neither target nor test NAND flash storage [C-REF4-DC-technical-005]. 01 §4.5's "industrial eMMC with a measured endurance budget" is therefore outside what upstream tests, and OneMind owns that risk.

## Strongest counter-argument

The 4 GB/eMMC platform node is justified by one healthy-state measurement. The k3s datastore's write rate and size depend on a compactor that has had a silent stop-forever regression in the last two years, and whose failure upstream treats as expected behaviour. A Compose/Quadlet node has no API-server datastore churning leases and events. On a 4 GB or eMMC box, that difference is the flash budget. The Market already imports Compose (01 §4.5 portability guard), so the "can still join the same app platform" clause of the flip condition is closer to met than the result admits.

## New sources (searched for regressions, wear and failure reports; each opened)

- **N1.** k3s-io/k3s issue #5042, "k3s wears flash storage such as NAND". [C-REF4-DC-technical-004]
- **N2.** k3s-io/k3s discussion #7694 (maintainer statements on NAND, SD and SQLite vs etcd). [C-REF4-DC-technical-005]
- **N3.** k3s-io/k3s issue #12898, "When compaction fails, it results in the bloating of the state.db". [C-REF4-DC-technical-006]
- **N4.** k3s-io/kine PR #414 (compaction stop-forever regression, v0.13.4–v0.13.9). [C-REF4-DC-technical-007]

Not used: a homelab issue reporting about 10 GB/day from k3s, because its text says it was written by an AI agent and I could not trace its measurement.

## What would flip this verdict

- **To upheld:** T-W4 on hardened k3s with the real OneMind stack stays under 5 GB/day **and** state.db size stays flat for 30 days, including a run where a compaction error is injected and recovered (kine ≥ v0.13.10).
- **To refuted (for 4 GB/eMMC nodes):** the soak exceeds 5 GB/day with the real stack, or a compaction stall cannot be detected and recovered automatically on-device. Then sub-8 GB/eMMC nodes become agent-only or Compose/Quadlet.

## Recommended change (for the owner, not applied)

Extend T-W4: measure with the hardened profile and the real stack, inject one compaction failure, and record state.db size and bytes/day. Add a node health check that alerts on stalled kine compaction (state.db growth or compact-revision lag) on every SQLite server.
