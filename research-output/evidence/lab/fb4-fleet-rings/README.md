# Lab spike LAB-fb4-fleet-rings: one hub, two k3s clusters and a single-node box; ring rollout, a halted bad release, rollback and a partition

**Status:** COMPLETE: **FAIL** (T3), as pre-registered. Run 1, 2026-11-12 10:39–10:56 UTC; criteria pushed as `b5eaa3b` before any VM existed. Two exploratory variants (E5, E6) follow the verdict and do not change it.

**Serves:** fabric mission 02 §5 lab spike 2 ("Multi-cluster control") and workstream FB-4; research 05 §3.2 ("never stretch one cluster across sites"); `docs/leap` CORE-UPDATE-9 (fleet-staged updates) and the proposed multi-cluster epic.

> **Explain it like I'm the founder.** When you have many OneMind sites (home, cabin, office, a friend's house), each with its own small Kubernetes, you want one place to say "put version 2 of this app everywhere", and you want it to go to one test site first, stop by itself if that site breaks, go back with one step, and cope with a site that is offline. Rancher Fleet is the open-source tool built for exactly this at large scale. Each site's agent calls the hub; the hub never calls the sites, so no site opens a port. This spike builds that on one small VM and checks each of those promises.

## 1. Goal

Measure whether a pull-based multi-cluster tool (Rancher Fleet v0.16.3, Apache-2.0) gives OneMind what FB-4 asks for: one hub managing several k3s clusters and a single-node box, rollouts in rings that halt on failure, rollback, and correct behaviour across a partition, with no connection from the hub to any site. The result informs whether OneMind adopts Fleet, copies its pattern into its own gateway, or both.

## 2. Hypotheses

- **H1** Downstream clusters register by agent-initiated registration and the hub never opens a connection to them.
- **H2** Manual partitions with `maxUnavailable: 0` deliver a release ring by ring and stop at the first ring that is not Ready.
- **H3** Re-applying the previous bundle restores every cluster to it (rollback is "apply the old version"; Fleet has no rollback verb).
- **H4** A site that is offline during a release converges to it after it returns.

## 3. Pass / fail criteria (frozen before the run)

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| T0 | Pins | k3d **v5.9.0** `k3d-linux-arm64` sha256 `03cde5cf23e6e8e67de5a039ecf26e5b85aca82fba3e5d13dadf904cd218a250` and present in its `checksums.txt`; Helm **v3.22.1** `linux-arm64` sha256 `4c29e286b279d170fa048ddfc3e4e83dcd069ca9c52102766ba672d7149e694d`; Fleet **v0.16.3** `fleet-crd-0.16.3.tgz` `fd3e5641…141b`, `fleet-0.16.3.tgz` `1a4b7304…9bbc`, `fleet-agent-0.16.3.tgz` and `fleet-linux-arm64` `a0c2e18c…11f4` each present in `fleet_0.16.3_checksums.txt`; k3s image `rancher/k3s:v1.37.2-k3s1` (`os/versions.lock.yaml` pin); the pulled Fleet image digests are recorded | Any mismatch or unpinned download |
| T1 | Registration without inbound connections | Hub cluster `hub` (1 node) runs the Fleet manager. Clusters `site-a` (1 server + 1 agent), `site-b` (1 server) and `box-1` (1 server) register with one `ClusterRegistrationToken`, labels `ring=0` (box-1), `ring=1` (site-b), `ring=2` (site-a). Before registration, a `DOCKER-USER` rule **drops every new connection from the hub's container to any site container** (and its counter is recorded). All three `clusters.fleet.cattle.io` become Ready within **15 min** of the agent installs | Any cluster not Ready, or the hub → site drop counter shows the manager tried and the run needed it removed |
| T2 | First release | Bundle `demo` v1 (a Deployment of the k3s pause image plus a ConfigMap `demo-version: v1`), partitions ring0 → ring1 → ring2 with `maxUnavailable: 0` and `maxUnavailablePartitions: 0`: every cluster shows ConfigMap `v1` and the Deployment Available within **15 min** | Any cluster not on v1 Available |
| T3 | A bad release halts in ring 0 | Bundle `demo` v2-bad (image tag that does not exist, ConfigMap `v2-bad`): box-1 receives v2-bad and becomes not Ready; for the next **10 min** after box-1 shows v2-bad, site-b and site-a still show ConfigMap `v1` (polled every 15 s) | site-b or site-a ever shows v2-bad |
| T4 | Rollback | Re-apply v1: box-1 shows `v1` and Available within **10 min**; site-b and site-a stay `v1` throughout | Otherwise |
| T5 | Good release in ring order | Apply v3: every cluster reaches `v3` Available within **20 min**, and the first time each shows `v3` respects ring order (box-1 ≤ site-b ≤ site-a; ties allowed) | A later ring gets v3 before an earlier ring is Available, or any cluster misses v3 |
| T6 | Partition | Stop `site-b` (`k3d cluster stop`); apply v4; wait **5 min**; start `site-b`: within **15 min** of the restart, site-b and site-a show `v4` Available, and box-1 shows `v4` | Any cluster not on v4 after 15 min |

**Spike verdict:** PASS if T0–T6 all pass in one full run. An environment limit (for example, memory) gives BLOCKED with the reason, never PASS. A lab-script bug is logged, fixed, and the whole run repeated; failed logs are kept in `history/`.

**Exploratory (not pass/fail):**
- **E1 ring 2 while ring 1 is offline (T6):** does site-a get v4 while site-b is down, or does the halted partition hold it back? Recorded with timestamps.
- **E2 footprint:** memory of the Fleet manager pods on the hub, and of the Fleet agent per downstream cluster (`kubectl top pod`, 3 samples over 5 min, after settle).
- **E3 drift:** delete the ConfigMap on site-a by hand: does Fleet put it back, and how fast?
- **E4 what the hub can see:** what status a site reports (Bundle states, resource counts) that a Nodes or fleet view could show.

## 4. Design

- **Host isolation:** the same disposable Lima VM as `fb2-fdo-enroll` (`template:debian-13`, arm64, `vz`, **4 vCPU / 4 GiB**, 20 GiB), run after it; only host mount is `<lab-dir>`; deleted at the end.
- **Clusters:** k3d (k3s in containers) on one Docker network, Docker from the Debian 13 archive inside the VM. Traefik, servicelb and local-storage disabled on every cluster to save memory; metrics-server kept on the hub for E2.
- **Fleet:** manager from the pinned Helm chart on `hub`; agents from the pinned `fleet-agent` chart on each site; bundles produced from a local directory with the pinned `fleet apply` CLI (no Git server), as the GitRepo controller does internally.
- **Readiness reading:** ConfigMap and Deployment status read on each site through its own kubeconfig, and the Bundle and Cluster status read on the hub; all polls timestamped in UTC.

## 5. Fidelity limits (written before the run)

| This lab shows | It does not show |
|---|---|
| Fleet's registration, partitions, halting, re-apply and partition recovery on four small k3s clusters | Scale (hundreds or thousands of clusters), real WAN links, Fleet's Git path |
| That the hub needs no connection to sites | NAT traversal itself (fb3-mesh-nat covers that) |
| Fleet memory on a 4 GiB arm64 VM | Pi 5 numbers; CPU on a contended host is not meaningful |

## 6. Glossary

| Term | Meaning |
|---|---|
| Ring / partition | A group of clusters that receives a release together; ring 0 first |
| Bundle | Fleet's unit of deployment: a set of Kubernetes resources plus targets and a rollout strategy |
| Agent-initiated registration | The site's agent calls the hub with a token; the hub never calls the site |
| k3d | k3s running inside Docker containers, one container per node |

---

## Results

**Verdict: FAIL.** T0, T1 and T2 passed; **T3 failed**: with the pre-registered strict ring settings (`maxUnavailable: 0`, `maxUnavailablePartitions: 0`) Fleet never delivered the new release to ring 0 in 15 minutes, so the "halt in ring 0" behaviour could not even be reached. The run was stopped after T3 (§8). The cause is Fleet's documented-in-code partition rule, not a lab-script bug (§7.2). Data: `run-1/`, ledger `../../claims/LAB-fb4-fleet-rings.csv`.

> **Explain the result like I'm the founder.** Joining worked exactly as promised: each site's agent called the hub, and a firewall rule that blocked the hub from ever calling a site saw zero attempts. The first app version reached every site in 18 seconds. Then the strict "zero tolerance" ring setting we wrote down in advance turned out to mean "zero progress": Fleet treats a site that has not updated *yet* as broken, so with zero allowed, nobody may start. With one notch looser setting (exploratory, not counted), Fleet did what we hoped on the bad release (stopped it at the first ring and went back in one step) but an offline site in the middle ring held up the last ring until it came back. Lesson for OneMind: copy the pull model and the halt, but write the ring rule so that "not updated yet" and "offline" never count as "failed".

### 7.1 Results (run 1)

| ID | Result | Evidence |
|---|---|---|
| T0 | **PASS** | k3d, Helm, Fleet charts and CLI matched pin and upstream checksum file; k3s image digest = repo pin; Fleet image digests recorded [C-LAB-fb4-fleet-rings-001]. `logs/fetch.log`, `run-1/up.log`, `run-1/snap/` |
| T1 | **PASS** | 3/3 clusters Ready 63 s after the agent installs; hub→site NEW-connection drops **0**; site→hub API connections counted 9 [-002]. `run-1/res/T1.json` |
| T2 | **PASS** | v1 Available on all three in 18 s [-003]. `run-1/res/T2.json` |
| T3 | **FAIL** | v2-bad never reached box-1 in 900 s; every BundleDeployment kept the v1 deployment ID; bundle `WaitApplied` on all partitions [-004]. `run-1/res/T3.json`, `run-1/poll.csv` |
| T4 | not counted | ran before the stop and passed trivially (v1 was still deployed everywhere) |
| T5, T6 | **not run** | run stopped after the verdict was fixed; v3 was staged on ring 0 and never promoted (`OutOfSync`) [-005]. `run-1/snap/` |

### 7.2 Why T3 failed (source)

Fleet v0.16.3 `internal/cmd/controller/target/status.go` L46–L72: "Unavailable for a partition is stricter than unavailable for a target. For a partition a target must be available and up-to-date." A cluster waiting for the new release is not up to date, so it counts as unavailable, and `maxUnavailable: 0` admits no cluster to start [C-FB4-016]. Upstream users ask the same question (fleet #2891, #3586) [C-FBREF-005].

### 7.3 Exploratory (not pass/fail)

- **E5** (`maxUnavailable: 0`, `maxUnavailablePartitions: 1`): same stall for about 2.5 min before it was stopped; two partitions counted unavailable [-006]. `run-1-e5/`
- **E6** (`maxUnavailable: 1`, `maxUnavailablePartitions: 0`), the T2–T6 sequence: bad release reached ring 0 in 17 s and was **held there for 6 min**; re-applying v1 restored ring 0 in 17 s; a good release reached all rings within one 16 s poll; with ring 1 (site-b) stopped, ring 0 updated but **ring 2 waited for the whole outage**, and all three were current 48 s after site-b returned [-008, -009]. `run-1-e6/` (its T1 "FAIL" only reflects the registration clock of run 1 and is meaningless here)
- **E2 footprint:** Fleet manager pods ≈ 170 MiB on the hub; Fleet agent 42–49 MiB per cluster [-007]. `run-1/snap/fleet-footprint.json`
- **E3 drift:** a ConfigMap deleted by hand on site-a was **not restored within 5 min**, and the hub still showed site-a with 2/2 bundles ready (drift correction is off by default) [-010]. `run-1-e6/res/E3.json`, `E4.json`
- **E4 hub view:** per cluster the hub shows ready bundle counts, a state (`OutOfSync`, `WaitApplied`, `NotReady` with the failing resource's message) and the agent's last-seen time; per partition, ready/not-ready counts. `run-1/snap/`, `run-1-e6/res/e4-*.json`

### 8. Deviations, failed attempts and fixes

| # | What | Effect |
|---|---|---|
| 1 | Setup attempt 1: k3d refused a Docker network without a gateway (`no gateway defined for network fb4net`) | script fix (`--gateway`); `history/attempt1/` |
| 2 | Setup attempt 2: the token was applied before the `fleet-default` namespace existed (standalone Fleet does not create it) | script fix (create the namespace, as the docs' example namespace `clusters` implies); `history/attempt2/` |
| 3 | Setup attempt 3: the `limactl shell` session dropped and killed the script's output pipe | re-run as a transient systemd unit inside the VM; logs in `history/attempt3/` |
| 4 | Run 1 was **stopped after T3** instead of running T4–T6, because the verdict was fixed and T5/T6 depend on the same stalled gate; the time was used for E5/E6 instead | documented deviation from "one full run"; it does not change the verdict |
| 5 | E5 and E6 change the rollout settings after seeing T3: exploratory only | not counted |
| 6 | Not committed: the agent values file (it holds the registration token) and the Fleet chart's default values (upstream, reproducible with `helm show values`) | hygiene |

### 9. Reproduce

Inside a disposable Debian 13 arm64 VM: `LAB=<lab-dir> scripts/fetch.sh`, `scripts/fleet-up.sh 1`, `scripts/fleet-tests.sh 1`; variants `scripts/fleet-tests-e5.sh 1-e5`, `scripts/fleet-tests-e6.sh 1-e6`; `scripts/fleet-snapshot.sh <run-dir>` records hub state and footprint. Root inside the VM only.
