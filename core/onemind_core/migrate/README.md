<!-- SPDX-License-Identifier: Apache-2.0 -->
# Migration kit (core/onemind_core/migrate)

Moves a namespace of an existing Kubernetes cluster onto this box as a private app, with owner approval at every step. Module map: see `__init__.py`. Mechanics: `docs/leap/core/MIGRATE.md`.

## Replacing a whole cluster
The kit moves one namespace at a time. For a whole cluster, follow the phase plan in
[`lab-kits/cluster-replacement/RUNBOOK.md`](../../../lab-kits/cluster-replacement/RUNBOOK.md) and its
machine-readable target table [`targets.yaml`](../../../lab-kits/cluster-replacement/targets.yaml):

1. **P0** freeze and prove backups, 2. **P1** agent runtime, 3. **P2** small daily apps,
4. **P3** worker and data, 5. **P4** message bus authority flip (always last), 6. **P5** decommission.

Each workload class has one target: a Market app, the OS itself, a private deploy through this kit,
or a drop with an archive first. `core/tests/test_cluster_replacement_plan.py` fails when that stops being true.
Read-only toward the old cluster: GET only, never Secrets.
