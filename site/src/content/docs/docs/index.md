---
title: What works today
description: An honest list of what OneMind OS does today, what is in review, and what is still a plan.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

OneMind OS is a local-first home and edge cloud OS. You run it on machines you own: a mini PC, a Raspberry Pi 5, a GPU box, a cloud VM. Apps, backups, updates and AI agents run on them, and **every change waits for a human yes**.

This page is the single source of truth for status. The landing page repeats it. Both are updated in the same pull request that changes a status.

- **Works today** means the code is on `main`, has tests, and runs.
- **In review** means the code is written and waits in an open pull request.
- **Being built** means part of it exists on `main`, but you cannot use it yet.
- **Planned** means a researched design, with no code yet.

## Core

| Part | Status | Where |
|---|---|---|
| Node agent `onemindd`: detects board, OS, kernel, k3s, RAUC slots, GPU, TPM and Secure Boot; publishes a heartbeat every 10 s | <span class="om-tag om-tag--ok">works today</span> | [`cmd/onemindd`](https://github.com/onemindos/ONEMINDOS/tree/main/cmd/onemindd), [`internal/`](https://github.com/onemindos/ONEMINDOS/tree/main/internal) |
| Gateway: actions, owner-only approval, expiry, idempotency, hash-chained audit log, `kubernetes` and `noop` executors | <span class="om-tag om-tag--ok">works today</span> | [`core/`](https://github.com/onemindos/ONEMINDOS/tree/main/core) |
| Dashboard: Home, Nodes, Market, Approvals | <span class="om-tag om-tag--ok">works today</span> | [`dashboard/`](https://github.com/onemindos/ONEMINDOS/tree/main/dashboard) |
| CLI: `onemind node info`, `onemind nodes` | <span class="om-tag om-tag--ok">works today</span> | [`cmd/onemind`](https://github.com/onemindos/ONEMINDOS/tree/main/cmd/onemind) |
| Seed apps: Uptime Kuma, ntfy, Home Assistant | <span class="om-tag om-tag--ok">works today</span> | [`apps/`](https://github.com/onemindos/ONEMINDOS/tree/main/apps) |
| Developer install `deploy/install.sh` (hub and node), Mac compose hub, `verify.sh` | <span class="om-tag om-tag--warn">in review</span> | [Install](getting-started/install/) |
| Scan gate, agent identities for apps, MCP endpoint for agents, catalog links and trust fields | <span class="om-tag om-tag--warn">in review</span> | [Approvals and agents](concepts/approvals-and-agents/) |
| App intake: scaffolder, generated READMEs, CI gate (licence, pins, Trivy, ClamAV, smoke test) | <span class="om-tag om-tag--warn">in review</span> | [Apps and trust cards](concepts/apps-and-trust-cards/) |
| OS update client: signed channel (TUF), policy, pre-update snapshot, RAUC install, `onemind update` | <span class="om-tag om-tag--warn">in review</span> | [Updates and rollback](concepts/updates-and-rollback/) |
| OneMind image on Debian 13: read-only root, RAUC A/B slots, health gate, boot tests in QEMU in CI | <span class="om-tag om-tag--unknown">being built</span> | [`os/`](https://github.com/onemindos/ONEMINDOS/tree/main/os) |
| Nightly security rebuilds of the image (CVE scan, ClamAV, signed security channel) | <span class="om-tag om-tag--warn">in review</span> | [Security](concepts/security/) |

## Not yet

| Part | Status | Design |
|---|---|---|
| Backups with restic, 3-2-1 by default, verified restores | <span class="om-tag om-tag--unknown">planned</span> | [Backups](concepts/backups/) |
| Multi-site fabric: NATS leaf nodes, private mesh, store-and-forward | <span class="om-tag om-tag--unknown">planned</span> | [Fabric](concepts/fabric/) |
| Single sign-on and household roles (Owner, Adult, Teen, Child, Guest) | <span class="om-tag om-tag--unknown">planned</span> | v0 uses static bearer tokens |
| Android and iPhone apps: nodes, apps, approvals, activity, notifications | <span class="om-tag om-tag--unknown">planned</span> | approvals as push notifications, content fetched from your box |
| Plugin UI extension points for the dashboard | <span class="om-tag om-tag--unknown">planned</span> | headless operation stays first-class |
| Downloadable, signed OneMind images | <span class="om-tag om-tag--unknown">planned</span> | after the image passes its hardware gates |

## Where to go next

- [Install](getting-started/install/) on a spare Debian 13 machine, or [try it on a Mac](getting-started/mac/) with Docker.
- Read [Approvals and agents](concepts/approvals-and-agents/): it is the idea everything else is built on.
- The binding API definition is the [contract](https://github.com/onemindos/ONEMINDOS/blob/main/sdk/contracts/poc-v0.md); the [reference](reference/contract-api/) summarises it.
