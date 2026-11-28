<!-- SPDX-License-Identifier: Apache-2.0 -->
# Replacing the cloud cluster

**Part:** founder, OS and image, core. **State:** plan done. Founder answers pending. Nothing moves this week.

**Verdict:** yes, replace the cluster with OneMind, in phases. The daily load is small (about 1.3 GiB, mostly the AI agent). The rest of the cluster is platform overhead OneMind does not carry. Running costs would fall a lot (figures stay private).

## Hard blockers

1. The mini PC is too weak to be the hub. Use a VM on the lab server until a 32 GB machine exists.
2. FABRIC.md allows exactly one hub, so the lab VM joins as a worker.
3. `onemind migrate` refuses Market app ids and copies only from a live cluster.
4. The agent app image is blocked by the app gate.

## Phases

- **0 (weeks 0 to 2):** nothing moves. Interim hub VM, backups on to a local append-only target, off-site copy of the object-storage backups, a restore drill, secrets inventory in a private repo.
- **1:** the AI agent first, behind approvals.
- Later phases move the daily apps.

## OS features this needs

Migrate into an existing Market app; restore an app from an external restic repo; the agent as a gateway principal (#167, PR #495); an unblocked agent image.

## Keep in the cloud

An off-site backup copy, a small relay only when something must be public, free DNS, an external dead-man check, and the hosted mesh during the transition.

## Founder questions

Hub hardware now or a lab VM; keep the hosted mesh for the first weeks; agent path; build "migrate into Market app" first; may one cluster node wake for migrate copies; off-site target.
