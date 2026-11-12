---
title: What works today
description: An honest list of what OneMind OS does today, what is in review, and what is still a plan.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

OneMind OS is a local-first home and edge cloud OS. You run it on machines you own: a mini PC, a Raspberry Pi 5, a GPU box, a cloud VM. Apps, backups, updates and AI agents run on them, and **every change a person, app or AI agent asks for waits for a human yes**. OS security updates install on their own inside your maintenance window unless you turn that off.

This page is the single source of truth for status. The landing page repeats it. Both are updated in the same pull request that changes a status.

- **Works today** means the code is on `main`, has tests, and runs.
- **In review** means the code is written and waits in an open pull request.
- **Being built** means part of it exists on `main`, but you cannot use it yet.
- **Planned** means a researched design, with no code yet.

New here? Start with the [user guides](guides/).

## Core

| Part | Status | Where |
|---|---|---|
| Node agent `onemindd`: detects board, OS, kernel, k3s, RAUC slots, GPU, TPM and Secure Boot; publishes a heartbeat every 10 s | <span class="om-tag om-tag--ok">works today</span> | [`cmd/onemindd`](https://github.com/onemindos/ONEMINDOS/tree/main/cmd/onemindd), [`internal/`](https://github.com/onemindos/ONEMINDOS/tree/main/internal) |
| Gateway: actions, owner-only approval, expiry, idempotency, hash-chained audit log, `kubernetes` and `noop` executors | <span class="om-tag om-tag--ok">works today</span> | [`core/`](https://github.com/onemindos/ONEMINDOS/tree/main/core) |
| Scan gate (no install without a passing scan newer than 7 days), agent identities for apps, MCP endpoint for agents, catalog links and trust fields | <span class="om-tag om-tag--ok">works today</span> | [AI agents](guides/agents/), [Apps](guides/apps/) |
| Dashboard (v2, built on the shared design system): Home launcher, Market (with licence, tier and last scan), Installed, Approvals, Activity, Nodes, Settings, command palette. Settings sections whose API is not switched on yet say so | <span class="om-tag om-tag--ok">works today</span> | [`dashboard/`](https://github.com/onemindos/ONEMINDOS/tree/main/dashboard), [First steps](getting-started/first-steps/) |
| CLI: `login` and contexts, `status`, `nodes`, `apps`, `actions` (install, approve, deny, watch), `audit verify` and `tail`, `mcp` bridge for agents, `update`, `mesh status`, `storage`, `node info` | <span class="om-tag om-tag--ok">works today</span> | [CLI](reference/cli/) |
| Developer install `deploy/install.sh` (hub and node), Mac practice hub in Docker, `verify.sh`. Tested in Debian 13 arm64 virtual machines; not yet run on a real Pi 5, Jetson, droplet or amd64 PC | <span class="om-tag om-tag--ok">works today</span> | [Install](getting-started/install/), [Try it on a Mac](getting-started/mac/) |
| Apps catalog: every app in `apps/`. Each one can be installed only while its latest scan passes; see its trust card | <span class="om-tag om-tag--ok">works today</span> | [Apps catalog](../apps/), [`apps/`](https://github.com/onemindos/ONEMINDOS/tree/main/apps) |
| App intake: scaffolder, generated READMEs, CI gate (licence, pins, Trivy, ClamAV, smoke test), daily rescan | <span class="om-tag om-tag--ok">works today</span> | [Apps and trust cards](concepts/apps-and-trust-cards/) |
| OS update client: signed channel (TUF), policy, pre-update snapshot, RAUC install, `onemind update`. Nothing to install until the image and a signed channel are published | <span class="om-tag om-tag--unknown">being built</span> | [Updates and rollback](guides/updates/) |
| OneMind image on Debian 13: read-only root, RAUC A/B slots, health gate, boot tests in QEMU in CI | <span class="om-tag om-tag--unknown">being built</span> | [`os/`](https://github.com/onemindos/ONEMINDOS/tree/main/os) |
| Nightly security rebuilds of the image (CVE scan, ClamAV, signed security channel). The pipeline is on `main`; nothing is published yet | <span class="om-tag om-tag--unknown">being built</span> | [Security](concepts/security/) |

## Not yet

| Part | Status | Where |
|---|---|---|
| Backups with restic: hourly snapshots, retention ladder, weekly verified restores, single-file restore. The backup agent runs inside `onemindd` only when a settings file exists, and nothing installs one yet; the gateway has no backup routes, so OneMind takes no backups by default | <span class="om-tag om-tag--unknown">being built</span> | [Backups](guides/backups/) |
| Private mesh (self-hosted Headscale), NATS leaf nodes with store-and-forward, app proxy with sign-in, per-box certificate authority. On `main`, not switched on | <span class="om-tag om-tag--unknown">being built</span> | [Remote access](guides/remote-access/) |
| Disk inventory, disk health and mirror plans (`onemind storage`). The CLI has `disks`, `health`, `status` and `plan`: it lists, checks and plans, and changing disks is not part of it | <span class="om-tag om-tag--unknown">being built</span> | [`internal/storage`](https://github.com/onemindos/ONEMINDOS/tree/main/internal/storage) |
| New Home screen: widgets, wallpapers, app launcher, Store. The dashboard uses them now; some widgets show placeholders until their API exists | <span class="om-tag om-tag--unknown">being built</span> | [`ui/`](https://github.com/onemindos/ONEMINDOS/tree/main/ui) |
| Android and iPhone app: nodes, apps, approvals, activity, alerts while open. On `main`; build it yourself, no store release | <span class="om-tag om-tag--unknown">being built</span> | [Phone app](guides/phone-app/) |
| Household identity, sessions, passkeys and scoped API tokens. On `main` with tests; the box is still plain HTTP, so browser sign-in with a passkey works on `localhost` or behind TLS only | <span class="om-tag om-tag--unknown">being built</span> | [Security](concepts/security/) |
| App sandbox (restricted pods, default-deny network), scoped gateway permissions. On `main`; the host firewall part is still open | <span class="om-tag om-tag--unknown">being built</span> | [Security](concepts/security/) |
| Desktop app for Mac and Windows: tray, discovery, pairing, status, approval notifications. On `main`; build it yourself, no release yet | <span class="om-tag om-tag--unknown">being built</span> | [Desktop app](guides/desktop-app/) |
| Phone photo backup: the phone side (background, resumable, Wi-Fi and charging rules) is on `main`; the hub's Photos service that receives the photos does not exist yet, so nothing is sent | <span class="om-tag om-tag--unknown">being built</span> | [Phone app](guides/phone-app/) |
| Notifications: alerts for waiting approvals, blocked apps and failed backups, inbox, email, webhook and ntfy channels, quiet hours, app health monitoring. On `main`; Matrix and Telegram channels are still open | <span class="om-tag om-tag--unknown">being built</span> | [Approvals and agents](concepts/approvals-and-agents/) |
| Phone push that says only "something needs you" | <span class="om-tag om-tag--unknown">planned</span> | [Phone app](guides/phone-app/#notifications) |
| Plugin UI extension points for the dashboard | <span class="om-tag om-tag--unknown">planned</span> | headless operation stays first-class |
| Downloadable, signed OneMind images | <span class="om-tag om-tag--unknown">planned</span> | after the image passes its hardware gates |

## Where to go next

- [Install](getting-started/install/) on a spare Debian 13 machine, a Raspberry Pi 5 or a droplet, or [try it on a Mac](getting-started/mac/) with Docker.
- Follow the [user guides](guides/): first steps, apps, AI agents, updates, troubleshooting and a glossary.
- Read [Approvals and agents](concepts/approvals-and-agents/): it is the idea everything else is built on.
- The binding API definition is the [contract](https://github.com/onemindos/ONEMINDOS/blob/main/sdk/contracts/poc-v0.md); the [reference](reference/contract-api/) summarises it.
