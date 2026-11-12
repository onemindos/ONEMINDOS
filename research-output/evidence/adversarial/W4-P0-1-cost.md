# W4 P0-1 refuter: cost and solo-developer operability

| Field | Value |
|---|---|
| Claim | P0-1: k3s stays the app platform on every OneMind node with at least 4 GB RAM. Smaller devices (sensors, drones, MCU robots, Pi Zero) join as NATS leaf nodes, not Kubernetes nodes. Lab W4-1: k3s v1.37.2+k3s1 (SQLite) with a two-container app left 2,557 MiB available in a 4 GiB arm64 Debian 13 VM and wrote about 2.75 GB/day, about 0.95 GiB and 2.7 GB/day more than Podman. Olares (the only Kubernetes-based competitor) needs 8 GB. HAOS and umbrelOS use Docker. |
| Lens | Cost and solo-developer operability |
| Protocol | RESEARCH-MISSION.md §2 rule 7. The refuter saw only the claim and its cited sources. |
| Date | 2026-11-10 (re-check by 2027-05-10: Kubernetes and k3s facts) |
| Verdict | **weakened**. The split (k3s on capable nodes, NATS leaf on small devices) survives. The **4 GB threshold**, the **"every node"** wording and the missing **lifecycle cost** do not. A written response is required. |

## 1. Re-checking the cited sources

| Sub-claim | What the source says (opened 2026-11-10) | Holds? |
|---|---|---|
| k3s fits a node with 4 GB | k3s-io/docs@8958508 `requirements.md`: a server needs at least 2 cores and **2 GB RAM**, an agent at least 1 core and **512 MB**. "etcd is write intensive; SD cards and eMMC cannot handle the IO load." "If deploying K3s on a Raspberry Pi or other ARM devices, it is recommended that you use an external SSD." | Partly. The docs set no 4 GB line. They separate server from agent, which the claim does not. They also add a storage requirement (SSD) that the claim leaves out. |
| k3s overhead | k3s-io/docs@8958508 `resource-profiling.md` (k3s v1.26.5, 95th percentile): on a **Pi 4B**, a server with a workload uses **1,588 MiB** (SQLite) and **1,613 MiB** (etcd). A server in a single-agent cluster uses 1,215 MiB. An agent uses about 268 MiB. | The cited source shows **about 1.6 GB** for a k3s server on Pi silicon. That is about 40% of a 4 GB device, well above the lab's 0.95 GiB delta. |
| Lab W4-1 numbers | Claims ledger C-W4-076 to C-W4-080 (run-1.log sha256 c019bc07…): bare OS 3,545 MiB available, Podman plus app 3,513 MiB, k3s plus app 2,557 MiB, k3s plus app writing 2.75 GB/day, and `k3s.service` cgroup memory 1,995 MiB. The "slim" profile wrote 6.06 GB/day, but the traefik uninstall job was still running, so that rate is not steady state. | Yes, as reported. The ledger itself marks the result "VM, not Pi silicon". The run used one 10-minute window per profile and no OneMind services. |
| Olares requires 8 GB | beclab/Olares@e7fe1c9 `reusables.md` L74–L80: 4 cores, 8 GB RAM, 150 GB SSD. On Pi, it needs a Pi 4B or Pi 5 with 8 GB (C-W4-042). | Yes |
| umbrelOS and HAOS use Docker | umbrel@a72dac2 `app.ts` L518 (Docker Compose app lifecycle). home-assistant/supervisor@c1c6f0a `supervisor/docker/`. | Yes |

## 2. Strongest counter-argument (cost and solo-operability lens)

**A. The evidence argues against a 4 GB line, not for it.**

- In the lab, k3s used 956 MiB of a 3,923 MiB VM, about **24% of RAM**, before any OneMind service ran. Those services include the NATS server or leaf, the dashboard, the capability gateway, the Hermes agent and any camera or AI module.
- The claim's own source (`resource-profiling.md`) measured a k3s server **on a Pi 4B** at about **1.6 GB** with a workload. On a 4 GB board, that leaves roughly 2.4 GB for the OS and every app.
- The pass threshold (at least 2.0 GiB available) was set before the run, but nothing in the claim connects it to OneMind's real base stack.
- The only Kubernetes-based competitor, Olares, chose **8 GB**. The claim treats that as a contrast, but it is the one constraint-matched data point and it points the other way.
- OneMind's own hardware plan (`docs/HARDWARE.md`) specifies **8–16 GB** for the Edge box and 16 GB for the bake-off Pi 5. The 4 GB line therefore helps no product OneMind plans to sell. It only makes a promise to bring-your-own 4 GB boards (the HA Green class, for example), and the support load of that promise falls on one person.
- The cheaper, safer rule is: **8 GB for a k3s server; 4 GB is "best effort" and agent-only; below that, a NATS leaf.**

**B. "Every node" turns into a fleet of single-node control planes. A solo founder has to run that fleet.**

- The k3s docs separate server (2 GB) from agent (512 MB). If every ≥4 GB node runs its own k3s server, each home, robot or greenhouse is its own cluster.
- Each of those clusters has its own datastore, its own certificates, its own upgrades and its own failure modes. That calls for fleet tooling (Fleet, Argo CD or OneMind's own) from day one.
- Podman with Quadlet, or Docker Compose, the HAOS and Umbrel pattern, has no per-node control plane to keep healthy.
- The claim gives no reason why a 4 GB device should be a k3s server rather than a k3s **agent** of a nearby box, or a plain container host.

**C. Flash wear on the cheapest nodes.**

- 2.75 GB/day is about **1 TB/year** of host-level writes, about **10 TB over the 10-year horizon**. That is before SD or eMMC write amplification, and before any app beyond nginx and redis.
- The k3s docs say SD cards and eMMC "cannot handle the IO load" of etcd, and recommend an external SSD on ARM.
- Discussion #7694 (below): a user measured about **3.3 GiB/day** on an 11-pod aarch64 node. The k3s maintainer said Kubernetes is inherently write-heavy, that SQLite already writes less than etcd, and that he did not see how to cut writes further. He recommended a Pi 4-class board booting from SSD or NVMe. No code change followed.
- Issue #1850: k3s on a Pi 4 with a slow microSD card **crash-looped about 230 times**, because controller-manager leader election timed out on disk latency.
- A 4 GB device with only SD or eMMC therefore falls outside what upstream tests. That means more field failures, and support tickets for one person.
- The claim's rule should be gated on **storage (NVMe or SSD required)**, not only on RAM.

**D. The claim leaves out the lifecycle cost. This is the strongest cost point.**

- Kubernetes minors get about **1 year** of patch support, and three branches are maintained at a time (kubernetes.io/releases: 1.34 reached end of life on 2026-10-27).
- k3s upgrade rules: "Ensure that your plan does not skip intermediate minor versions when upgrading", and servers are upgraded before agents (docs.k3s.io/upgrades/manual).
- Over 10 years that means about **30 sequential minor upgrades on every node**, with no skipping. That includes robots and greenhouse boxes that may be offline for months. A node that is three minors behind needs a stepwise catch-up, done by automation or by the founder.
- Bundled components change between minors. For example, k3s v1.32 moved from Traefik v2 to Traefik v3, which needs a migration (docs.k3s.io/upgrades).
- A Podman or Docker host follows the base OS update cadence and has no forced yearly migration of an API surface.
- The claim sets "0.95 GiB and 2.7 GB/day" against Podman but leaves this ongoing operational cost off the scale.
- Kubernetes also adds security surface, though k3s's own advisory count is low: 3 GHSAs in total, including GHSA-jxr7-mqhw-9p98 / CVE-2026-54250, a path traversal in etcd snapshot restore published 2026-06-03, Moderate. This is a minor point and does not carry the argument.

**E. Competitor constraint-fit favours Docker for the small tiers.**

| Competitor | Runtime | Min RAM | Team | Constraint fit to OneMind's ≥4 GB edge node |
|---|---|---|---|---|
| HAOS | Docker (Supervisor) | runs on 4 GB HA Green | Large funded org (Nabu Casa) | **High** for edge and IoT hardware; **low** for GPU and cluster |
| umbrelOS | Docker Compose | 16 GB on its own boxes | Small company | Medium (consumer self-hosting) |
| Olares | k3s + external etcd + Calico | **8 GB** | Funded company | High for GPU and cluster tiers, **low** for 4 GB |

The two products that run on the cheapest hardware both chose Docker. The one that chose Kubernetes set 8 GB. Under rule 2 (a pattern is the default only when its constraints match), the "k3s at 4 GB" corner matches no competitor.

**What this does not overturn:**

- Kubernetes for the Lite, Pro, Robotics and Cluster tiers. GPU scheduling, multi-node and N-9 are legitimate reasons, and the lab shows k3s *works* at 4 GB.
- NATS leaf nodes for sub-GB devices. No counter-evidence was found against that half of the claim.

## 3. New sources (found by searching for failure, wear and lifecycle burden; all opened 2026-11-10)

Raw HTML was saved to the session scratchpad (not the repo) and hashed with SHA-256. The orchestrator should archive the load-bearing ones (1, 2, 3, 4) in `evidence/sources/`.

1. k3s-io/k3s Discussion #7694, "K3s read/writes and wear on flash storage such as NAND" (opened 2022-01-28; maintainer replies 2022-02-07 to 2022-02-10). https://github.com/k3s-io/k3s/discussions/7694. sha256 9c40d3b1696fb373b219d84d6943d8e5865e181ad96accd511f39f5e8001754b. Shows about 3.3 GiB/day on an 11-pod node, and the maintainer's statement that the write load cannot be reduced further. The maintainer recommends SSD or NVMe. Unresolved.
2. k3s-io/k3s Issue #1850, "K3S wrong backend for Rpi 4 on MicroSD Cards" (2020-06-01, closed by the reporter 2021-03-02). https://github.com/k3s-io/k3s/issues/1850. sha256 547cd9f97ab56d2957504475e6c18af905c732bf8acac82dc6062492b2700b16. Shows about 230 restarts from SD latency. Old (v1.18), but nothing in issue #7694 or the current docs says this was fixed.
3. Kubernetes, "Releases" (accessed 2026-11-10). https://kubernetes.io/releases/. sha256 cc63f4ffaae5434f98cf085f87c7225cd7f43e7d6860e94434fe13a8f3ec7eff. Shows "approximately 1 year of patch support", three maintained branches, and 1.34 end of life on 2026-10-27.
4. K3s docs, "Manual Upgrades". https://docs.k3s.io/upgrades/manual. sha256 a6a7614fa4fd5f6c0c9358ef56f064dd7a787ec2ff5048a0414a36396e360e59. Shows that intermediate minors must not be skipped, servers are upgraded before agents, and "the system-upgrade-controller itself will not protect against unsupported changes".
5. K3s docs, "Upgrades". https://docs.k3s.io/upgrades. sha256 8fe17999b5aeac886169a8f633dbbede4e9eee6b62e60d68d25b0a908bd143ba. Shows the Traefik v2 to v3 change at v1.32, which requires a migration.
6. k3s-io/k3s Security advisories. https://github.com/k3s-io/k3s/security/advisories. sha256 24c85798658c59aa2ba083518ad2a43c4ed75b3a20e10abbb825ed29e3f23ace. Shows 3 advisories, including GHSA-jxr7-mqhw-9p98 (2026-06-03). This **cuts against** a CVE-burden argument for k3s itself.
7. SECONDARY: D. Woitzik, "K3s on Raspberry Pi: Why I Said No (And You Probably Should Too)", dev.to (posted 15 Aug, year not shown; probably 2026). https://dev.to/dwoitzik/k3s-on-raspberry-pi-why-i-said-no-and-you-probably-should-too-2l38. sha256 1653b324ad03bfe7c2bae3dbc2a422890f225e81d599b8dca6bb0fff0046720e. The author ran an etcd control plane on Pi 5 (8 GB) with SD storage, saw latency spikes from about 10 ms to over 500 ms, and moved back to VMs after three weeks. This is an etcd HA anecdote, so it is weak evidence for SQLite.

Searched but not used: k3s idle-memory regressions in 2025–2026. No current regression was found. The older reports (#3558, about 535 MB idle; CPU creep on 1.21–1.25) are dated, so the lab's numbers stand on that point.

## 4. What would flip the decision

These would turn the verdict into **refuted**, meaning the threshold must move:

- A k3s server on a **real Pi 5 with 4 GB** (not a VM), running the **OneMind base stack** (NATS, dashboard, gateway, one AI or camera module), leaves **less than 1.5 GiB** available, or OOM-kills under a 24-hour soak. The line should then be 8 GB for a server.
- A k3s node on SD or eMMC shows **more than 5 GB/day** at steady state with the base stack, or an endurance projection under 5 years for the target eMMC or SD part. Storage then becomes a hard gate.
- A k3s node left offline for 2 or more minors fails an automated stepwise catch-up in the lab, or needs manual steps. "Every node" is then not sustainable for one maintainer.

These would turn the verdict into **upheld**:

- The claim is restated as: **server at ≥8 GB with NVMe or SSD; agent-only or Podman on 4–8 GB; NATS leaf below that.** Or a real-Pi 5 4 GB soak with the full base stack keeps at least 2 GiB available and writes under 3 GB/day on NVMe.
- The ADR records the upgrade cadence (about 3 minors a year, no skipping), the tested catch-up path for offline nodes, and the fleet tool that runs it.

This would refute the k3s-everywhere architecture itself (outside this lens, listed for completeness):

- N-9 concludes that GPU and multi-node scheduling are needed only on Pro and Cluster boxes. Podman with Quadlet plus NATS then covers the Edge and Lite tiers at about 1 GiB less RAM, about 2.7 GB/day fewer writes and no yearly Kubernetes migrations. That is the HAOS and Umbrel pattern, which matches the cheap-hardware constraints.

## 5. Required response from the author (weakened, so rule 7 applies)

1. Replace "≥4 GB RAM" with a two-part gate (RAM **and** NVMe/SSD), and separate k3s server from agent.
2. Reconcile the lab's 0.95 GiB delta with the cited profiling doc's ~1.6 GB server footprint on a Pi 4B. Schedule the real Pi 5 soak with the base stack.
3. Add the lifecycle cost (about 1-year minors, no skipping, Traefik-style component migrations, offline-node catch-up) to the P0-1 ADR, next to the RAM and write numbers.
4. Re-run the "slim" profile to steady state (C-W4-080 is flagged as not steady state).
