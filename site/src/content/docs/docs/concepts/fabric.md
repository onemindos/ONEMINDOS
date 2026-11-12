---
title: Fabric (many nodes)
description: How several machines become one OneMind, today and next.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

OneMind treats every machine you own as a **node** of one system. A mini PC, a Raspberry Pi 5, a GPU box and a cloud VM can all run apps, and the hub sees them all. Phones are **windows** into the system, not nodes.

## Today <span class="om-tag om-tag--ok">works today</span> / <span class="om-tag om-tag--warn">in review</span>

- **One hub.** It runs the k3s server, NATS, the gateway and the dashboard.
- **Nodes join k3s as agents**, never as servers. A separate agent-only join token means a node can never take over the control plane. (The install script is in review.)
- **Heartbeats.** Each node's `onemindd` publishes its status to the hub's NATS every 10 seconds on `onemind.node.<node_id>.status`. The gateway marks a node `online`, `stale` (30 s) or `offline` (120 s).
- **Privacy by default.** The node id is derived from `/etc/machine-id` by hashing; the heartbeat never contains serial numbers, MAC addresses, IP addresses or user names.

## Next <span class="om-tag om-tag--unknown">planned</span>

- **Sites that survive outages.** Each site gets a NATS **leaf node** with its own JetStream store. In our lab, a leaf kept accepting messages while the hub was down and delivered all 600 of 600 to the hub about 40 seconds after it came back, with no gaps or duplicates. Only subjects captured by a stream on the leaf are buffered, so the design gives every subject that must survive an outage its own stream.
- **A private mesh** between your sites and devices: WireGuard, coordinated by a self-hosted control server.
- **Growing without reinstalling.** A single box keeps k3s's simple SQLite datastore. Adding the third server migrates it to embedded etcd in place.
- **Phone apps** for Android and iPhone that show nodes, apps, approvals, activity and notifications.

## Headless first

Everything the dashboard shows comes from the same API that scripts, the CLI and agents use. A fabric of boxes with no screen attached is the normal case, not an edge case.
