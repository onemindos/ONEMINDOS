# DC-12: refuter report on the A/B layer and k3s (health-gated commit), technical lens

- **Conclusion under test (decision-critical.md DC-12 Result; 01 §4.2 item 6, D3 row):** a safe design exists: k3s inside the read-only slot, datastore on `data`, each trial boot runs against a copy, a fresh-signal gate (apps excluded, 3 tries, watchdog), a k3s-minor guard that refuses an older k3s on a newer datastore and offers the snapshot restore, and no auto-retry. The same gate passed on Debian (RAUC 1.13/1.15.2), Ubuntu 26.04 (RAUC 1.15.1) and Mender; a cross-minor rollback has not been run (T-W3-03).
- **Flip condition:** no safe design exists for rollback across a k3s minor version with k3s in the A/B image.
- **Lens:** technical. I read only the conclusion and its cited claims (C-LAB-rauc-1152-011, C-LAB-ubuntu-2604-leg-011, C-LAB-mender-014, C-W3-063, C-W3-065). I formed this view before reading any other refuter file. This is the first dedicated DC-12 refuter.
- **Date:** 2026-11-11

## Verdict: **weakened**

The labs prove the **gate**: a fresh-signal check catches a dead kubelet that a naive check commits, under three engines and two bases. They don't prove the part the flip condition is about. "A safe design exists" for a cross-minor rollback is still a design, not a result: T-W3-03 hasn't run. Two gaps in that design are concrete enough to fail the first time OneMind ships a k3s minor bump to a real cluster:

1. **The datastore copy is per node, but etcd isn't.** Rev. 3 moves hub, Pro and Omni servers to embedded etcd (DC-11). A per-node copy of the etcd member directory, restored on one node after a failed trial, is a filesystem-level etcd rollback. In k3s #3803, three embedded-etcd servers used this exact pattern: copy the data to the other partition on upgrade, switch partitions on rollback. They ended up disagreeing about which members were Ready, and some nodes would not rejoin until their etcd data was wiped. The k3s maintainer wrote: "I'm not sure that filesystem rollback of this type is really supported by etcd," and named cluster `etcd-snapshot` restore as the supported path [C-REF4-DC-technical-001]. On a multi-server cluster, rolling back one node's slot is a member-level restore the cluster has moved past, and rolling back all of them is a coordinated cluster restore. Neither is the single-box SQLite copy the labs exercised.
2. **The copy covers the k3s datastore, not app data.** The gate excludes apps from the health signal, but apps still run during the trial. If the new release bumps system apps or operators, they can migrate their own databases on PVCs during the trial. Rolling back restores `state.db` and the old images, which then run on migrated app data. An independent NixOS + k3s appliance project hit exactly this while designing the same mechanism (2026-11-02). Its fix holds the bootstrap/GitOps ref until commit, and it accepts losing trial-time datastore changes. Its done-criterion is an e2e test in which a failed k3s-minor trial restores the datastore and reaches Ready [C-REF4-DC-technical-002]. OneMind's design has neither a hold on app reconciliation during the trial nor that e2e test.

Neither gap makes a safe design impossible, so the verdict is not **refuted**. Both are fixable: a single-node-only claim for the current design, an etcd-snapshot path for clusters, and a trial-time freeze on app reconciliation. But "Answer: a safe design exists" overstates what was shown, and the status "partial" should say why.

## Strongest counter-argument

DC-12's "safe" rests on rolling back a per-node datastore copy. That is sound for single-box SQLite and unproven or unsupported for the embedded-etcd tiers that rev. 3 itself introduces. The trial also lets apps mutate state that the rollback doesn't restore. The flip condition asks for rollback across a k3s minor version, and that path is the one with no lab, no multi-node test and no app-data story. Until T-W3-03 passes on a three-server etcd cluster with an app migration in the trial, the image-held k3s on server nodes carries an untested brick risk. The DC-12 flip question then arises for those tiers: k3s outside the slot, or cluster-level snapshot orchestration.

## New sources (searched for failures and regressions)

- **N1.** k3s-io/k3s #3803, "k3s state inconsistent after filesystem rollback of all nodes in cluster" (opened 2021-08-09, v1.21.1+k3s1, 3 servers on embedded etcd, A/B partitions). Opened. NotReady disagreement after rollback, nodes that would not rejoin until etcd was wiped, maintainer doubt that etcd supports filesystem rollback. Closed stale with no fix. https://github.com/k3s-io/k3s/issues/3803 [C-REF4-DC-technical-001]
- **N2.** librepod/os #21, "updates: one-way releases (k3s minor, bootstrap bump) and a k3s datastore snapshot before the trial" (opened 2026-11-02, open). Opened. Same design as OneMind's, plus the app-migration failure mode and the hold-until-commit fix. https://github.com/librepod/os/issues/21 [C-REF4-DC-technical-002]
- (Context, not counted as new) SUSE/k3s roll-back docs repeat C-W3-063: rollback needs a snapshot taken on the target minor.

## What would flip it

- **→ upheld:** T-W3-03 run twice. (a) A single box: a k3s minor bump fails its trial, the guard restores the snapshot and the node reaches Ready. (b) A three-server embedded-etcd cluster: one node's minor-bump trial fails and it rolls back with no member divergence, or the design states that cluster rollback goes through `etcd-snapshot` restore and the lab shows it automated. In both runs an app with a schema migration is held until commit.
- **→ refuted (for server tiers):** a three-server etcd rollback that can't be made consistent without a manual wipe or cluster reset, or an app migration during the trial that leaves the rolled-back slot broken with no way to hold it. Server nodes would then need k3s outside the A/B image or a different update model (D3/D4 change).
