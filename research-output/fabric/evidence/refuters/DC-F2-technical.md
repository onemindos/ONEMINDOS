<!-- SPDX-License-Identifier: Apache-2.0 -->
# DC-F2 refuter, technical lens

**Claim given:** many clusters with a hub; one cluster per site; sites pull from a fleet hub with rings; Fleet optional. **Cited:** C-FB4-001, C-FB4-003, C-FB4-005, C-FB4-008, lab fb4-fleet-rings.

**Strongest counter-argument.** (1) Pull-based ring rollouts are subtle even in the leading open tool. This run's own lab: with `maxUnavailable: 0` and `maxUnavailablePartitions: 0`, Fleet v0.16.3 staged the update for ring 0 but never deployed it in 15 minutes; all three clusters' BundleDeployments sat in `WaitApplied` (pre-registered T3 **FAIL**, `05-…` §3). Users ask the same questions upstream ("How do partitions work?", "how to make a failed partition block the next one", "does an offline cluster fail a partition") [C-FBREF-005], and an offline cluster can leave bundle status stuck with misleading messages (#594, open since 2021) [C-FBREF-004]. (2) The alternative is proven at large scale: KubeEdge reports 100,000 simulated edge nodes in **one** cluster [C-FB4-008], and k3s officially supports agents across networks [C-FB4-001]. So "many clusters" may be the harder path.

**New sources:** C-FBREF-004, C-FBREF-005 (Fleet issues), plus the lab result and its exploratory variant E6 (an offline ring-1 site held back ring 2 until it returned [C-LAB-fb4-fleet-rings-009]).

**Verdict: weakened** (the ring-engine part), **upheld** (one cluster per site).

**What would flip it:** (a) a OneMind ring engine that fails the same partition test → adopt Fleet with documented settings; (b) evidence that a single k3s cluster tolerates sites going offline for hours without evicting their workloads (it does not by default: pods on a `NotReady` node are evicted after the toleration period) → only then reconsider one stretched cluster.

**Response (author).** Accepted. `05-…` records the deadlock as a lab finding and the exploratory variant (E5) as separate evidence; OneMind's ring rule is defined on the *previous* ring's measured health (`09-…` §3), and the P2 gate repeats the pre-registered fb4 sequence against OneMind's own engine. KubeEdge's figure is a single-cluster scheduler benchmark with a 128-CPU master and simulated nodes, which does not address partitioned sites (its own report lists disconnection as untested [C-FB4-008]).
