# Runner-up steelman: embedded etcd on every k3s server, from day one

- **Role:** runner-up steelman (RESEARCH-MISSION.md §2 rule 7). This agent was told to argue **for** running k3s with embedded etcd (`--cluster-init`) on every box, instead of the chosen "SQLite on a single box, online `.backup` inside restic, convert to etcd at the third server". It is advocacy held to the evidence rules: each fact is primary-sourced and opened on 2026-11-11 (code and docs at pinned SHAs), or labelled INFERENCE or UNVERIFIED. The honest weaknesses are in §6.
- **Date:** 2026-11-11 · **Re-check by:** 2027-05-11
- **Verdict:** `steelman`
- **Decision under test:** ADR-001 **D5** as changed by [`01` §4.6](../../01-FOUNDATION-DECISION.md) and [`06` §2.4](../../06-backups-recovery.md) (W5-R2, W5-R3, REC-DEC-11, REC-DEC-28). Until now this runner-up had only the in-file summary in `06` §2.4; `01` §8 lists it as an adversarial shortfall.
- **Ledger:** [`evidence/claims/STEEL-etcd-every-box.csv`](../claims/STEEL-etcd-every-box.csv) (C-STEEL-etcd-every-box-001…025)
- **Serves requirements:** F-11, F-14, M-4, M-6, M-7, N-9, R-1, R-2, R-3, UX-6

> ### Explain it like I'm the founder
> Kubernetes has to keep its "memory" (every app, setting and secret) in a database. k3s offers two: **SQLite**, a single file, and **etcd**, the database that every other Kubernetes uses. The study picked SQLite for single boxes because etcd wrote about 8 times more to disk in one 10-minute test, and switches a box to etcd only when a third server joins.
> The best case for etcd everywhere: **one database means one backup method, one restore method and no risky switch-over later.** That switch-over has already wiped a cluster once in a real k3s release. SQLite in k3s runs through **kine**, a translation layer whose own README is titled "Kine is not etcd", and about one person maintains it. etcd is maintained by a Kubernetes group with people from several companies, and it is fault-tested for thousands of hours. The scary "8× more writes" came from a 10-minute window that started **seconds after the switch-over, while a pod was restarting**. k3s's own published profiling measured etcd writing **half** the bandwidth SQLite did. Even if the 8× figure holds, the smallest common NVMe drive would last more than ten years. And the study already says every box that holds the database must have an SSD.
> The catch (§6): our only head-to-head measurement still says etcd writes far more; etcd opens two network ports even on one box; its restore needs one extra step that failed the first time in our lab; and it dislikes slow disks, which matters for bring-your-own hardware. **Argued at full strength, etcd wins for hub, Pro and Omni boxes if one clean write measurement on real hardware comes in under budget. It does not win for 4 GB Lite boxes.**

---

## 1. The claim

> **On every OneMind box that runs a k3s server (which `01` §4.5 already limits to ≥ 4 GB RAM and SSD/NVMe, with robots and field kits as agent-only), embedded etcd is the better datastore than kine/SQLite. It removes a second backup format, a second restore procedure and a one-way, historically fragile migration. It puts the most important state in the system on the datastore that upstream Kubernetes is built, governed and tested around. The case against it rests on one confounded 10-minute write measurement and on an SD/eMMC concern that the platform-node gate already excludes.**

## 2. Strongest arguments

### 2.1 One datastore, one recovery path, no one-way switch (F-14, M-6, R-2)

| Fact | Evidence |
|---|---|
| The SQLite → etcd conversion is a **one-way state change**. You restart with `--cluster-init`, and once etcd files exist on disk, k3s ignores the datastore flags from then on. | [C-STEEL-etcd-every-box-002] k3s docs `ha-embedded.md` L66–L68 |
| That conversion **crashed into an empty cluster** in k3s v1.32.5 (a kine regression), and k3s had **no end-to-end test** of it until a maintainer asked for one after that bug. | [C-REF-W5-longevity-002], [C-REF-W5-longevity-003] |
| kine **will never** produce etcd-compatible snapshots. Under the chosen design every OneMind box therefore needs two datastore backup formats for its whole life. | [C-REF-W5-longevity-001] |
| Embedded etcd has a vendor backup subsystem: scheduled snapshots on by default, per-node retention, compression, S3 replication with its own retention, and `ETCDSnapshotFile` objects that list every snapshot on every member through the normal Kubernetes API. | [C-STEEL-etcd-every-box-003], [C-STEEL-etcd-every-box-004] |
| For SQLite the vendor documents only "take a copy" of the folder. The WAL-safe online method is OneMind's own procedure. | [C-REF-W5-longevity-009] |

**Why this matters to OneMind:** F-14 says the user "never switches products". Under the chosen design, the riskiest operation a box will ever undergo (a datastore format change) happens at the moment the household or business is growing, which is the moment it has the most to lose. `01` §4.6 knows this, so it adds a verified backup before conversion, object-count checks after it, and a conversion test in CI for every k3s version. With etcd from day one, adding a second and third server is a plain **join**, the operation every k3s HA cluster performs every day.

**The CI matrix for a solo developer (M-6):** the chosen design commits OneMind to three restore-class drills for every shipped k3s minor (`01` §4.6, REC-DEC-28): a SQLite fresh-box restore, an etcd restore for clusters, and the SQLite → etcd conversion. With etcd everywhere it is **one** drill, `etcd-snapshot` plus token restored onto a fresh box, and it already passed in our lab [C-LAB-k3s-footprint-restore-013]. To 2036 that is about 8–10 k3s minors [C-W4-012] × 2 fewer drills, and no OneMind-owned SQLite procedure to keep correct against kine changes. *INFERENCE (count derived from `01` §4.6).*

### 2.2 The flash-wear objection is weaker than it looks

The whole case against etcd in `06` §2.4 is item (c): "etcd's write volume is the wrong default for SD/eMMC Lite boxes" [C-W5-018]. Four problems with it:

1. **The design never puts the datastore on SD/eMMC.** `01` §4.5 already says a platform node needs SSD/NVMe (or industrial eMMC with a measured budget), and SD-only devices are NATS leaves. Capturable field nodes run the agent only, so they hold no datastore at all. k3s's warning about SD/eMMC [C-W4-002] therefore applies to no OneMind *server* node.
2. **The 8.7× figure is confounded.** The etcd idle-write window began at the exact second the in-place conversion finished (14.5 s), while the test pod had just restarted (RESTARTS 1, `ContainerCreating` a moment earlier). It counted the whole VM disk, journald included, over 600 s, in one run [C-STEEL-etcd-every-box-019]. `06` itself lists "the etcd measurement started right after the migration" among its limits. A post-migration settling window is not a steady state.
3. **The vendor's profiling points the other way.** k3s's published resource profiling (p95 of steady-state operation, datastore and control plane only) gives **embedded etcd 250 KiB/s, SQLite 500 KiB/s**. etcd needs more IOPS (50 vs 10) and lower latency (< 5 ms vs < 10 ms), but half the bandwidth. The same tests ran embedded etcd on a **Raspberry Pi 4 with an SD card** [C-STEEL-etcd-every-box-020]. These numbers are old (k3s v1.26.5, etcd 3.5) and are requirements, not daily totals, but they are the only vendor figures, and they do not show an 8× penalty.
4. **Even taking the 8.7× figure at face value, NVMe survives to 2036.** 340,568 sectors in 600 s is about **25 GB/day**, or about **92 TB over 10 years** of idle writes for the whole VM. Samsung warrants its smallest 980 NVMe (250 GB) for **150 TBW**, the 500 GB for 300 TBW and the 1 TB for 600 TBW [C-STEEL-etcd-every-box-016, C-STEEL-etcd-every-box-021]. On a 500 GB drive that is about 31 % of the rated endurance in ten years, from an upper-bound measurement. *INFERENCE (arithmetic).*
5. **etcd is getting lighter.** etcd 3.6 cut the default `--snapshot-count` from 100,000 to 10,000 and reduced average memory by at least 50 % [C-STEEL-etcd-every-box-008]. Our own lab found embedded etcd on one node costs **+23 MiB** of RAM over SQLite, which is noise [C-LAB-k3s-footprint-restore-009].

### 2.3 Longevity to 2036: bet on the reference, not the shim (R-3, F-1)

| | Embedded etcd | kine/SQLite |
|---|---|---|
| What it is | The datastore Kubernetes is built for. `kube-apiserver --storage-backend` accepts only `etcd3` [C-STEEL-etcd-every-box-007]. | "Kine is not etcd": a shim that implements "the subset of the etcd V3 API required by the Kubernetes API server", "not intended to be usable as a generic etcd server" [C-STEEL-etcd-every-box-005]. |
| How watch works | Native etcd watch. | A poll loop over a SQL table (1 s ticker plus a local notify), which re-creates etcd revision semantics with gap detection and "fill" records [C-STEEL-etcd-every-box-006]. |
| Governance | A Kubernetes SIG: three chairs and three tech leads from several organisations [C-STEEL-etcd-every-box-010]; development merged with Kubernetes in 2023 [C-STEEL-etcd-every-box-012]. | One maintainer wrote 42 of the last 50 human commits [C-REF-W5-longevity-006]. |
| Maintenance | Three minor lines (3.5, 3.6, 3.7) patched on the same day, 2026-10-22 [C-STEEL-etcd-every-box-011]. | Ships inside k3s. The vendor positions SQLite for "a simple, short-lived cluster in your CI/CD environment" and embedded etcd for the edge [C-STEEL-etcd-every-box-001]. |
| Correctness testing | Systematic robustness tests; 830 hours on Antithesis simulating 4.5 years, on **1-node** and 3-node clusters, with process kills and clock jitter [C-STEEL-etcd-every-box-009]. | Known corruption reports with "nothing that can be done within K3s" [C-REF-W5-longevity-004]; no comparable published fault-injection programme found (UNVERIFIED: absence not proven). |
| Version mobility | etcd 3.6 is the first release with full **downgrade** support [C-STEEL-etcd-every-box-008]. | Backups are bound to the k3s version that wrote them (`01` §4.6). |

*INFERENCE:* the cross-k3s-minor rollback (T-W3-03) is still unproven in `01` §7. etcd's supported downgrade path is a better base for that work than a kine schema with no downgrade contract. It does not solve Kubernetes storage-version rollback, which is the same problem for both datastores.

### 2.4 F-14: one OS from greenhouse to GPU cluster

- The vendor's sizing guide covers 0–350 agents on a 2-CPU/4 GB server and 1,800+ on 16 CPU/32 GB, with a 3-server HA cluster scaling about 50 % further [C-STEEL-etcd-every-box-022]. Those HA numbers are etcd numbers: SQLite "cannot be used on clusters with multiple servers" [C-STEEL-etcd-every-box-001].
- With etcd everywhere, a Pi-class hub, a Pro box and an Omni rack all run the **same** datastore, backup, restore, metrics and failure modes. Support (R-2) sees one behaviour. The tier differences become disk class and server count, not a different database.
- **Competitor proof:** Olares, the closest consumer "home cloud on Kubernetes", runs k3s against **etcd even on single boxes** (an external etcd unit set through `K3S_DATASTORE_ENDPOINT`) and snapshots it every 30 minutes, keeping 5 [C-STEEL-etcd-every-box-017]. Talos counts etcd among the services every control-plane node must run before it is Ready [C-TD-talos-016] (ledger row of the Talos teardown, not re-opened here). The founder's own cloud cluster is on etcd.

### 2.5 F-11: industrial IoT

- Most IIoT devices are NATS leaves under `01` §4.5 and never touch the Kubernetes datastore. That is correct, and it shrinks this argument. What remains is the **site hub**: a farm, water-plant or warehouse hub that runs gateways, protocol adapters (OPC UA, Modbus, Sparkplug) and operators as Kubernetes objects. Operator-style apps that "make extensive use of the Kubernetes datastore" raise server requirements, and the vendor asks for agent and workload IO to be isolated from the datastore [C-STEEL-etcd-every-box-023].
- IEC 62443-style availability targets for a site hub are met by **redundant servers**, and in k3s that means etcd. A site that will need three servers should not have to cross the SQLite → etcd conversion in production. *INFERENCE.*

### 2.6 Robotics (M-7)

- Robots are agent-only (`01` §4.5), so the datastore that matters is the **hub's**. Every agent's kubelet heartbeat is an **update** to a Lease object [C-STEEL-etcd-every-box-024]. A warehouse hub with dozens of robot agents therefore turns its datastore into a steady stream of small writes. On kine/SQLite those writes go through one SQLite writer and come back to watchers through the poll loop above [C-STEEL-etcd-every-box-005, C-STEEL-etcd-every-box-006]. On etcd they use a native watch.
- A robot fleet is exactly the customer that will want a second and third hub server for availability. With etcd that is a join; with SQLite it is the one-way conversion while robots are working. *INFERENCE; no benchmark of kine/SQLite at fleet churn was found or run.*

### 2.7 Security

- **Neutral where it matters most:** both datastores hold every Secret. Both need `secrets-encryption` and need their backups wrapped in restic: an etcd snapshot is unencrypted [C-W5-013], and a SQLite copy plus token decrypts everything (`01` §5.4). etcd does not make this worse.
- **Better restore isolation:** during `--cluster-reset`, k3s binds etcd's client and peer listeners to **loopback only**, so no other node can connect while a restore runs [C-STEEL-etcd-every-box-015].
- **Snapshot inventory is visible:** `ETCDSnapshotFile` objects show which snapshots exist on which member [C-STEEL-etcd-every-box-004]. The dashboard can show backup freshness from the API instead of a custom agent. *INFERENCE (UX-4).*
- See §6 for the cost: etcd's network listeners.

### 2.8 Solo-developer operability (M-6)

- **One mental model:** the founder already runs etcd-backed Kubernetes in the cloud, so the box and the cloud fail the same way.
- **Less OneMind-owned code:** no online SQLite backup procedure, no integrity-check gate, no conversion path, no kine schema watch. The vendor `etcd-snapshot` path (schedule, retention, S3, CRD inventory) replaces most of it. restic still wraps the file.
- **Fewer drills:** see §2.1.

## 3. Criterion by criterion

| Criterion | Chosen (SQLite single box) | Steelman (etcd every server) | Who wins, honestly |
|---|---|---|---|
| Backup and restore surface | Two formats, three drills per k3s minor | One format, one drill | **etcd** |
| Growth to HA (UX-6, M-4) | One-way conversion with a regression history | Join | **etcd** |
| Datastore longevity and governance | kine, about one maintainer | Kubernetes SIG, several companies | **etcd** |
| Write volume | Lab: about 8.7× less (confounded) | Vendor: half the bandwidth, more IOPS | **Unresolved** |
| RAM | Baseline | +23 MiB (lab); +0–198 MiB (vendor, Pi 4) | ≈ tie; SQLite on 4 GB |
| Slow or HDD storage (P-7 BYO) | Tolerant (INFERENCE) | Needs fast fsync; Olares fails on HDD | **SQLite** |
| Network attack surface on one box | No datastore listener | 2379/2380 on the node address | **SQLite** |
| Restore simplicity | Token file alone was enough | Token must be passed explicitly; first attempt failed | **SQLite** |
| Two-server households | Second server must be an agent | Two-member etcd is *less* tolerant than one | **SQLite** unless the product blocks it |

## 4. The strongest defensible form

The steelman does **not** need to win on 4 GB Lite boxes to change the design. Its strongest form is:

> **Embedded etcd on every hub, Pro and Omni server (≥ 8 GB, NVMe ≥ 500 GB). SQLite only on the 4 GB slim profiles (TAK node, greenhouse) that `01` §4.5 already sells as fixed-purpose profiles. Never more than one SQLite box in a cluster's history.**

This keeps SQLite where its write and RAM edge matter. It also removes the conversion from every box class likely to grow into HA, and halves the datastore drill matrix for the boxes that carry the business.

## 5. Proposed changes if the flip test passes

1. Replace W5-R2/W5-R3 with the §4 split. Hub, Pro and Omni images start with `cluster-init: true`.
2. Keep restic as the outer wrapper and the token in the recovery kit (unchanged). The etcd restore tool must pass `--token-file` explicitly [C-LAB-k3s-footprint-restore-013].
3. Firewall 2379/2380 to the loopback and the cluster's own servers on every image, and leave etcd metrics on loopback.
4. The product refuses a two-server control plane (one or three, never two).
5. Run the install-time fsync benchmark Olares should have run: on a disk too slow for etcd, refuse the install or fall back to the SQLite profile.

## 6. Genuine weaknesses (stated as hard as the evidence allows)

1. **Our only head-to-head number still says 8.7×.** The vendor profile is three years old (k3s v1.26.5), gives p95 rates rather than daily totals, and was not built to compare write wear. Until a clean measurement exists, "etcd writes less" is not shown. The extrapolated ~25 GB/day would also **fail `01`'s own 5 GB/day hardened-profile gate** (§4.5), and would use about 61 % of a 250 GB drive's rated endurance in ten years.
2. **etcd listens on the network even on one box.** k3s's code binds etcd's client port (2379) and peer port (2380) to the node address as well as loopback whenever it is not resetting, both over TLS [C-STEEL-etcd-every-box-015]. The requirements page says those ports are "required only for HA with embedded etcd" [C-STEEL-etcd-every-box-025]. SQLite has no listener. This needs a firewall rule on every image and a security-refuter pass.
3. **Restore is less forgiving.** In our lab the etcd restore onto a fresh host failed the first time. k3s generated a new CA and token over the restored token file, and only passing the token explicitly worked. For SQLite the token file alone was enough [C-LAB-k3s-footprint-restore-012, C-LAB-k3s-footprint-restore-013].
4. **etcd punishes slow disks.** Fast disks are "the most critical factor"; slow writes can trigger elections and hurt stability [C-STEEL-etcd-every-box-013]. Olares maintainers told a user whose install kept failing on an HDD that "etcd requires an SSD" [C-STEEL-etcd-every-box-018]. Bring-your-own hardware (P-7) will meet such disks, and the vendor's own sizing gives SQLite lower IOPS and latency needs [C-STEEL-etcd-every-box-020].
5. **etcd upgrades have their own hazards.** Moving from 3.5 to 3.6 needed 3.5.20+ first or the upgrade failed, and two more upgrade issues were found later [C-STEEL-etcd-every-box-014]. k3s bundles and sequences etcd, which absorbs much of this, but it is not zero.
6. **More disk, more upkeep.** The etcd data directory was 131 MiB vs 17 MiB at idle [C-LAB-k3s-footprint-restore-009]. Whether k3s defragments embedded etcd automatically was not checked (UNVERIFIED).
7. **Two-server footgun.** A two-member etcd cluster needs both members for quorum [C-STEEL-etcd-every-box-002 (same page, L12)], so a household that adds a second server is *less* available than with one. SQLite makes that mistake impossible.
8. **RAM on the 4 GB floor.** Vendor Pi 4 figures show +198 MiB for etcd in the single-agent case [C-STEEL-etcd-every-box-020]. Our lab showed +23 MiB. On a 4 GB slim profile any extra counts, which is why §4 leaves those boxes on SQLite.
9. **No robotics or IIoT benchmark.** §2.5 and §2.6 are inference: nobody has shown kine/SQLite failing at robot-fleet or site-hub churn. The kine poll loop notifies local writes immediately, so single-server watch latency is usually not a full second.
10. **A third option exists that this file does not argue.** kine has a NATS JetStream driver that supports multiple servers [C-STEEL-etcd-every-box-005], and NATS is OneMind's authority bus. It would give HA without etcd. It has no lab evidence here and inherits kine's maintainer concentration.

## 7. What evidence would make it win

| Test | Pass condition (etcd wins) | Fail condition (SQLite stays) |
|---|---|---|
| **T-W5-03, corrected protocol** (Pi 5 8 GB + NVMe, then x86 mini PC): hardened k3s profile, 72 h, measured on the **datastore device or a dedicated partition**, starting ≥ 1 h after `cluster-init` or a fresh etcd install (not a conversion), with the same reference workload on both | etcd ≤ 2× SQLite **and** etcd ≤ 5 GB/day absolute | etcd > 2× SQLite or > 5 GB/day |
| A second `--cluster-init` conversion regression in any k3s release OneMind would ship, or a OneMind CI conversion failure | Any occurrence, so conversion becomes a product risk, not a lab risk | None across three consecutive minors |
| kine maintainer health | Main maintainer inactive 6+ months, or SUSE deprecates SQLite | Unchanged |
| Hub churn benchmark: 50 simulated agents + a CRD-heavy operator on a Pi 5 hub | kine/SQLite p99 API latency > 2× etcd | Within 2× |
| Founder decision | Hub, Pro and Omni boxes ship with ≥ 500 GB NVMe as standard | Lite hardware is the volume product |

**Bottom line (honest):** etcd everywhere does **not** beat SQLite on 4 GB Lite boxes. For server-class boxes (§4) it is **better on three of the five things a 10-year solo-built product needs** (one recovery path, no one-way migration, a long-lived and well-governed datastore). It is worse on network surface and restore forgiveness, and unresolved on wear. One corrected 72-hour measurement decides it.
