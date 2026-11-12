<!-- SPDX-License-Identifier: Apache-2.0 -->
# 05 · Multi-cluster and fleet control (FB-4): one big cluster, many clusters with a hub, or both?

**Date:** 2026-11-12 · **Workstream:** FB-4 (Tier A) · **Lab:** `fb4-fleet-rings` (spike 2): pre-registered verdict **FAIL** (T3), plus two exploratory variants (§3).
**Serves requirements:** M-4, N-5, N-6, P-4, P-9, UX-6, R-1, F-6, F-14
**Decision-critical:** DC-F2, refuters in `evidence/refuters/DC-F2-*.md`.

> **Explain it like I'm the founder.** The answer is **"many clusters with a hub"**, and inside each site "one cluster or one box". Each place you own keeps its own brain, so a cut cable at the cabin never stops the cabin. Your fleet hub (your own cloud server) holds the plans and sends releases out in rings: first one test machine, then a few sites, then everyone, stopping by itself if something breaks. We tested the most-used open-source tool for this (Rancher Fleet) on four small clusters. Sites joined without the hub ever calling them. With the strictest setting we had written down in advance, an update **never started**, and its source code explains why (so the pre-registered test FAILED). With one notch looser setting, it stopped a broken release at the first ring and went back in one step, but an offline site in ring 1 held up everyone behind it. So OneMind should copy the pattern, define the ring rule its own way, and keep Fleet as an option for big Kubernetes customers.

## 1. The answer

| Question | Answer | Evidence |
|---|---|---|
| One big cluster? | **No**, except always-online cloud workers joining a home cluster | k3s: "all servers should be in the same location"; latency "could also impact the health of the cluster"; agents may span networks [C-FB4-001]; KubeEdge's 100k nodes are simulated, in one data-centre control plane, with disconnection untested [C-FB4-008] |
| Many clusters with a hub? | **Yes**: one cluster (or box) per site; a fleet hub holds desired state, rings and summaries; **sites pull** | pull models: Fleet [C-FB4-003], OCM [C-FB4-009], argocd-agent [C-FB4-011], Flight Control [C-FB11-004]; lab T1 (no hub-to-site connection) |
| Both? | **Both layers exist**: inside a site, Kubernetes schedules across that site's nodes (FABRIC); across sites, the fleet layer moves releases, not pods | FABRIC §2 roles; this file §2 |
| Engine for the fleet layer | **OneMind's own rings over signed NATS jobs** (CORE-UPDATE-9 extended), Fleet optional for enterprise Kubernetes sites | lab §3; refuters DC-F2; [C-FB4-016] |

## 2. Shape at 1 → 10 → 1,000 → 100,000 nodes

| Nodes | Clusters | Fleet layer | What the owner sees |
|---|---|---|---|
| 1 | 1 box | none | the box |
| 10 | 1 site cluster (hub + workers + leaves) | none | Nodes list (FABRIC §6) |
| 1,000 | 10–100 site clusters/boxes | fleet hub, rings by site, summaries over NATS leaf | Sites list → site → nodes (`11-…`) |
| 100,000 | thousands of sites | region hubs (NATS leaf trees [C-FB3-002]); rings by region; only summaries and alerts flow up | Sites by region, counts, alerts |

Scale evidence is still thin: Fleet's README promises "a lot of clusters" with no number, OCM claims "thousands" without a benchmark [C-FB4-009], and Headscale needs per-site meshes [C-FB3-006, C-FBREF-006]. Mission 01's rule stands: **prove 10k by simulation** (W8-R11) before claiming it; that is gate FG5 in `13-…`.

## 3. Lab spike 2: `fb4-fleet-rings` (pre-registered)

Record: `../evidence/lab/fb4-fleet-rings/README.md`. One disposable Debian 13 arm64 VM (4 vCPU / 4 GiB), Docker from Debian, k3d v5.9.0, k3s image `rancher/k3s:v1.37.2-k3s1` (digest equals the `os/versions.lock.yaml` pin), Fleet v0.16.3 (charts and CLI hash-checked). Clusters: `hub` (Fleet manager), `box-1` (ring 0), `site-b` (ring 1), `site-a` (2 nodes, ring 2), all on a documentation-range Docker network.

### 3.1 Pre-registered run (strict rings: `maxUnavailable: 0`, `maxUnavailablePartitions: 0`)

| ID | Result | What happened |
|---|---|---|
| T0 | PASS | every pin matched pin and upstream checksum file; k3s image digest equal to the repo pin [C-LAB-fb4-fleet-rings-001] |
| T1 | **PASS** | three clusters registered by agent-initiated registration and were Ready **63 s** after the agent installs; the `DOCKER-USER` rule dropping every new hub→site connection counted **0** packets while the site→hub counter saw 9 new API connections (so the rule did see bridged traffic) [-002] |
| T2 | PASS | first release v1 reached all three clusters, Available, in **18 s** [-003] |
| T3 | **FAIL** | the bad release v2-bad **never reached ring 0** in 15 min; all three BundleDeployments stayed on v1 while the bundle reported `WaitApplied` on every partition [-004] |
| T4–T6 | stopped | the run was stopped after T3 (verdict already FAIL); T4 trivially passed (v1 re-applied); for v3, ring 0 got a *staged* deployment ID that was never promoted (`OutOfSync`) [-005] |

**Why (from source):** Fleet's partition rule says "Unavailable for a partition is stricter than unavailable for a target. For a partition a target must be available and **up-to-date**" [C-FB4-016]. A cluster still waiting for the new release counts as unavailable, so `maxUnavailable: 0` leaves room for no cluster to begin. The pre-registration encoded "zero tolerance" in a way Fleet reads as "zero progress". This is a configuration lesson with a source-code root, not a Fleet bug; users ask the same question upstream [C-FBREF-005].

**Spike verdict: FAIL** (as pre-registered: T3 failed).

### 3.2 Exploratory variants (not part of the verdict; criteria changed after seeing the result)

| Variant | Settings | Result |
|---|---|---|
| E5 | `maxUnavailable: 0`, `maxUnavailablePartitions: 1` | same stall: no cluster received the bad release in about 2.5 min before the variant was stopped; two partitions counted unavailable [-006] |
| E6 | `maxUnavailable: 1`, `maxUnavailablePartitions: 0` | the T2–T6 sequence behaved as OneMind wants on four of five points (§3.3) [-008, -009] |

### 3.3 E6 result

| Step (same as pre-registered T2–T6) | E6 result |
|---|---|
| v1 to all | Available everywhere |
| bad release v2 | reached ring 0 (box-1) in 17 s and was **held there for the whole 6-minute window**; rings 1 and 2 stayed on v1; Fleet showed ring 0 `NotReady` ("Progress deadline exceeded") and the other rings `WaitApplied` |
| rollback (re-apply v1) | box-1 back on v1 and Available in 17 s; other rings untouched |
| good release v3 | all three clusters on v3 within one 16 s poll (ring order not resolvable at this poll rate) |
| partition: site-b (ring 1) stopped, v4 applied | box-1 (ring 0) got v4; **site-a (ring 2) did not get v4 while site-b was offline** (5 min); 48 s after site-b restarted, all three were on v4 |

**Reading.** With room for one updating cluster per ring, Fleet does halt a bad release at ring 0 and rolls back by re-applying. But an **offline cluster in ring 1 holds back ring 2** until it returns: under Fleet's rule an offline cluster is simply "not available and not up to date" [C-FB4-016], and the open upstream bug about stuck status with offline clusters points the same way [C-FBREF-004]. For 1,000 sites, some of which are always offline, that would stall every release. OneMind's rule 3 below therefore differs from Fleet's on purpose.

### 3.4 Footprint (E2)

Fleet manager pods on the hub: about **170 MiB** working set in total (controller 30, agent-management 34, gitjob 22, helmops 16, cleanup 24, local agent 44); the Fleet agent on each site: **42–49 MiB** [-007]. Each k3s node container used about 0.6 GB (site) and 0.95 GB (hub) in this VM, so a 4 GiB hub can carry Fleet but not much else.

## 4. What competitors do (constraint-matched)

See `competitors/k8s-edge-multicluster.md`. In short: Fleet and OCM are pull-based and fit the "sites behind NAT" constraint; Argo CD's ApplicationSet is push and needs reachability [C-FB4-010]; KubeEdge/OpenYurt keep one central control plane, which contradicts "home is the authority"; Flight Control's success-threshold batches [C-FB11-005] are the cleanest ring rule.

## 5. Rules for OneMind's fleet layer (proposals)

1. A site enrols with a one-time token **and** an owner approval on the fleet hub (MULTI-CLUSTER-1); ring membership comes from that record, never from labels a site reports (Fleet advisories [C-FBREF-011]).
2. A release enters ring *k+1* only when ring *k*'s **updated** nodes are healthy for a soak time and its success ratio meets the threshold; nodes not yet updated never count as failures (the lesson of T3).
3. An offline site never blocks other sites' rings; it converges when it returns. (Fleet does the opposite: E6 showed an offline ring-1 site holding back ring 2.)
4. Releases are verified on each site against OneMind's signing keys; the fleet hub cannot act on a site by itself (`07-…` A8).

## 6. Open items

- **ZF-01** engine choice; **ZF-02** cross-site workers; **ZF-12** ring defaults.
- Gate FG3 re-runs this spike's pre-registered T1–T6 against OneMind's own engine.

## Glossary

| Term | Meaning |
|---|---|
| Partition | Fleet's word for a ring |
| `maxUnavailable` | how many clusters in a ring may be not-ready before Fleet stops |
| Staged vs deployed | Fleet first writes the new version as "staged" for a cluster, then promotes it to "deployed" |
| Pull model | sites ask the hub for work; the hub never connects to sites |
