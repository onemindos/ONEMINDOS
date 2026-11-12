# Lab spike LAB-fb4-fleet-rings: one hub, two k3s clusters and a single-node box; ring rollout, a halted bad release, rollback and a partition

**Status:** PRE-REGISTERED (criteria frozen before any VM, download or build).

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
