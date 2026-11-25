<!-- SPDX-License-Identifier: Apache-2.0 -->
# Replace the hosted cluster with the OneMind box: runbook

**Why this exists, in plain words.** The owner runs a hosted Kubernetes cluster (cloud, in standby to save money). It costs far more than the work it does: the real daily load is about 1.3 GiB of RAM, the rest is plumbing. OneMind OS is meant to do all of it on one small machine (a 16 GB all-in-one) plus a bigger worker. This runbook says what moves where, in what order, and how each move is proven. The machine-readable plan is [targets.yaml](targets.yaml); a test (`core/tests/test_cluster_replacement_plan.py`) fails if a workload has no target, a Market target is not a real app, data would be dropped without an archive, or the bus flip is not last.

Ties to: issue 234 (live goal), CORE-DEPLOY-6 (the migrate kit, [MIGRATE.md](../../docs/leap/core/MIGRATE.md)), D-007 (Debian 13 base). The full private inventory (names, hosts, domains, volumes) is kept outside this public repo.

**Rules.** Read-only toward the old cluster until P5 (GET only; the migrate role cannot read Secrets). Nothing is scaled up, deleted or edited by this plan before its phase. Every destructive step needs one explicit yes from the owner. Secrets are never copied by hand: they are re-entered at install approval or sealed on the box.

## What the read-only inventory found (2026-11-21)
- About 45 namespaces. Roughly 100 Deployments and 25 StatefulSets, most at 0 replicas (standby). Still running: the legacy agent and its MCP bridge, the tool gateway, the SSO provider, GitOps controller, policy engine, two CI runners, ingress controller, mesh operator and proxies, backup controller and three nightly jobs. "Standby" is therefore not "off": see P0.
- 13 CronJobs. Three are active (cluster-recovery backup, off-site copy, a 5-minute health keeper); the other ten are suspended app backups.
- About 60 PVCs. About 30 are real data (block storage, retain policy); the rest are backup-copy or cache volumes. Largest: the agent volume (100 Gi), the column store, bus streams and database replicas (10-20 Gi each).
- 4 Services of type LoadBalancer: the public ingress, the bus, and two mesh-only services.
- Ingress: 4 public hostnames on one load balancer (SSO, bus websocket, tile server, apex), about 25 private mesh-only hostnames.
- Certificates: 4 cert-manager Certificates, all internal (bus CA and server, database backup plugin). Public TLS is not terminated by cert-manager in this cluster (UNVERIFIED: check the edge before DNS moves).
- Alerts: about 35 PrometheusRules, 4 of them custom (backup health, cluster health, bus leaf nodes, tracking server). The alert path ends at a chat notifier (UNVERIFIED: Alertmanager config not read; read it in P0).
- Secrets: the read-only identity cannot list Secrets (good). Names and types must be read by the owner, privately, in P0.

## P0 Freeze and prove backups
1. Stop surprises: pause the three active nightly jobs only after one final run each succeeds. Keep the off-site copy until P5.
2. Pre-standby snapshots expire **2026-12-17**: copy them and the object-storage bucket to the worker and one off-site copy before then.
3. Restore drill: restic check on a snapshot repo; restore one database dump to a scratch Postgres; restore one app volume into a scratch namespace. Write the result down.
4. Read the Secret names and types and the Alertmanager receiver (owner, private). Decide which secrets are re-entered and which are retired.
5. Record who points at the public hostnames (phone, desktop, tracking clients) so P4 can flip them.
Test: `backup-jobs` row (restic repo is append-only; restore through the migrate copy path).

## P1 Agent runtime
Fix the agent image path first (the Market tier is `blocked` until the scan passes). Enter model keys at install approval. Restore its state from the volume by hand until "migrate into a Market app" exists. The MCP bridge and tool gateway need no move: the gateway `/mcp` is the replacement (`agent-mcp-and-tool-gateway`). Merge the agent budget and kill switch before any agent runs on the box. Run 7 days on the box, then scale the cloud copy to 0 and keep its volume 30 days.

## P2 Small daily apps
`password-manager` (signups off), `push-notifications`, `status-page`, `home-automation`, `bookmarks`, `metrics-and-dashboards`. Move each with `onemind migrate plan` then import, copy, cutover; old copies stay read-only 14 days. Each row's proof is its Market manifest and the app gate in CI.

## P3 Worker and data
Move `git-forge` (by git push), `workflow-automation` and `llm-observability` to the worker as private deploys after the licence questions are answered. Archive every `drop` row that holds data (SSO database, tracking and sensor stacks, IoT platforms, shared databases) into the restic repo, run restic check, then leave the old copies alone. Robotics and TAK work is parked: archive, do not run.

## P4 Message bus authority flip (always last)
Why last: every client and every app talks over the bus. Moving its authority before they are ready strands them. Steps: bring up the box bus with the same stream layout, mirror streams, repoint clients one by one (the list from P0 step 5), watch for 7 days, then make the box the authority and put the old bus in read-only. Test: `message-bus` row; the bus is part of the OS and has its own tests.

## P5 Decommission (not before 2026-12-17 and 30 stable days)
Move DNS, take a final snapshot and database backup, then remove in this order, one owner yes each: workloads, load balancer, volumes, cluster. Object storage stays read-only 90 days. Stop the CI runners here (replaced by the lab runner pool).

### Plumbing replacement
| Old part | Replaced by |
|---|---|
| GitOps controller | the OS image and RAUC A/B updates |
| Policy and scanning (admission policy, runtime and image scanners) | app gate in CI, sandbox, signed Market |
| Service mesh and VPN operator | fabric join ticket and mesh in the OS |
| Cost, cluster admin UIs, metrics operators | Control Hub, `onemind` CLI, Market metrics app |
| Managed Postgres operator, volume sync | per-app databases and restic |
| SSO provider | gateway passkeys and approvals |

### Target table (generated from targets.yaml, kept in step by a test)
| Workload | Phase | Target | Note |
|---|---|---|---|
| `agent-runtime` (legacy AI agent) | P1 | market-app `hermes-agent` | tier is blocked today (image scan); fix before the move |
| `agent-mcp-and-tool-gateway` (MCP bridge and tool gateway) | P1 | os-native | gateway /mcp replaces both |
| `password-manager` (password manager) | P2 | market-app `vaultwarden` |  |
| `push-notifications` (push notification server) | P2 | market-app `ntfy` |  |
| `status-page` (uptime and status page) | P2 | market-app `uptime-kuma` |  |
| `home-automation` (home automation hub) | P2 | market-app `home-assistant` |  |
| `bookmarks` (bookmark and read-later app) | P2 | market-app `karakeep` |  |
| `metrics-and-dashboards` (metrics store and dashboards) | P2 | market-app `grafana` | Prometheus is the second app; log store and operators are dropped |
| `git-forge` (self-hosted git forge) | P3 | market-app `gitea` | different upstream; move repos by git push |
| `workflow-automation` (workflow automation tool) | P3 | private-deploy | licence question open; decide before the move |
| `llm-observability` (LLM tracing and its column store) | P3 | private-deploy | RAM heavy: worker node only; licence question open |
| `message-bus` (message bus with durable streams) | P4 | os-native | bus authority flips last, after every client points at the box |
| `sso-identity` (single sign-on provider with its database and cache) | P3 | drop | one owner, passkeys in the gateway |
| `geo-and-situational-awareness` (mapping) | P3 | drop | parked with robotics and TAK work; archive, do not run |
| `iot-platforms` (two IoT platforms with their databases) | P3 | drop |  |
| `shared-databases` (managed Postgres cluster and operator) | P3 | drop | per-app databases travel inside their app volume |
| `ci-runners` (self-hosted CI runners) | P5 | drop | replaced by the lab runner pool |
| `cluster-plumbing` (GitOps) | P5 | drop | each is replaced by an OS part, see the runbook plumbing table |
| `old-front-door` (developer portal and redirect) | P5 | drop | the OneMind front door replaces it |
| `backup-jobs` (nightly backup CronJobs and snapshot repos) | P0 | os-native | restic in the image; keep old repos read-only 90 days |

## Not done here (left)
Read Secrets and alert receivers (owner only); Cloudflare DNS and edge TLS audit; a per-workload restore proof for every archive; a docs/learning copy of this runbook needs a founder-approved entry.
