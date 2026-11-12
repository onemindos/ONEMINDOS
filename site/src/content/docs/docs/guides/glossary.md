---
title: Glossary
description: Every OneMind word in plain English, from action to TUF.
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

- **A/B slots**: Two copies of the operating system on one disk. An update goes to the copy that is not running, so the working copy is always there to go back to. Part of the OneMind image (coming soon).

- **Access token**: The long random string you sign in with today. The hub stores only a fingerprint (hash) of it. Accounts with passkeys are coming.

- **Action**: A written request to change something, such as `app.install` or `app.remove`, with exact parameters, an expiry time and an idempotency key. Nothing changes until an owner approves it.

- **Agent**: A program that acts on its own, usually driven by an AI model. It has its own identity and can ask for actions, but never approve them. See [AI agents](../agents/).

- **Agent principal**: The identity an app gets when it declares one in its manifest, named `agent:<app-id>`. Created when you approve the install, deleted when you remove the app.

- **App**: A program OneMind runs for you, from the Market. Each runs in its own namespace, `app-<id>`.

- **Approval**: An owner's yes to an action. Only a person with the owner role can approve or deny.

- **Audit log**: The record of every request and decision. Each line carries a fingerprint of the line before it (a *hash chain*), so editing, deleting or reordering any past line is detectable.

- **Board**: The kind of hardware a machine is: `x86_64-efi` (a PC), `arm64-efi`, `rpi5` (Raspberry Pi 5), `jetson-orin`, `vm` (virtual machine), `vm-do` (DigitalOcean droplet) or `unknown`.

- **Catalog**: The list of apps the hub knows, with their trust facts. The Market shows it.

- **ClamAV**: An open-source malware scanner. The app checks run it over every app image.

- **Community (tier)**: An app whose checks pass but whose upstream project is archived or has not released in 18 months.

- **Contract**: The written agreement between OneMind's parts on how they talk to each other: [`sdk/contracts/poc-v0.md`](https://github.com/onemindos/ONEMINDOS/blob/main/sdk/contracts/poc-v0.md). Summary: [Contract API](../../reference/contract-api/).

- **CVE**: A publicly listed security vulnerability. A *critical* CVE that already has a fix blocks an app.

- **Dashboard**: The web screens of your OneMind: Home, Nodes, Market and Approvals, at `http://<hub-address>:8080`.

- **Developer install**: OneMind installed on top of a normal Debian system with `deploy/install.sh`. Quick, but nothing can roll back a bad OS update. The only way to install today.

- **Executor**: The one part of the gateway that changes the outside world, and only after approval. `kubernetes` really installs apps; `noop` pretends, for practice and tests.

- **Expiry**: The time after which a request can no longer be approved: 1 hour for requests from the dashboard, 24 hours from an agent.

- **Gateway**: The core program on the hub. It serves the dashboard and the API, keeps the list of requests, enforces "only an owner approves", writes the audit log and runs the executor.

- **Health gate**: On the OneMind image, the check after an update that keeps the new system only if k3s and the core services work. Otherwise the box goes back to the old copy.

- **Heartbeat**: The short report every machine sends to the hub every 10 seconds: board, OS, memory, disk, k3s state. It never contains serial numbers, network addresses or user names.

- **Hub**: The first machine. It runs the k3s server, NATS, the gateway and the dashboard.

- **Idempotency key**: A random id attached to a request. If the same request is sent twice, for example after a network hiccup, the hub sees the same key and does not create a second request.

- **Join token**: The secret the hub prints for adding machines. It lets a machine join k3s as a worker, never as a second hub.

- **k3s**: A small, complete Kubernetes, the system that runs apps in containers across your machines.

- **Leaf node**: A NATS relay at each site that stores messages while the link to the hub is down (coming soon).

- **Licence class**: How the app checks sort licences: **L1** and **L2** are allowed in the Market; unknown or non-commercial licences are **blocked**.

- **Manifest**: An app's description file, `onemind.app.yaml`: name, version, licence, supported processors, memory, web port. See [App manifest](../../reference/app-manifest/).

- **Market**: The dashboard screen where you browse apps and ask for installs.

- **MCP (Model Context Protocol)**: The common way for AI assistants to use outside tools. The hub has an MCP endpoint at `/mcp` for agents.

- **Mesh**: A private, encrypted network between all your machines and devices (coming soon). See [Remote access](../remote-access/).

- **Namespace**: A walled-off area inside k3s. Each app gets its own, `app-<id>`. Removing the app deletes it, with its data.

- **NATS**: The message bus: programs publish short messages on named subjects, and anyone subscribed receives them. Heartbeats travel over it.

- **Node**: Any machine in your OneMind. The hub is a node too.

- **`onemind`**: The command-line tool: `onemind node info`, `onemind nodes`, `onemind version`, and `onemind update` for the image.

- **`onemindd`**: The small program on every machine that sends its heartbeat. It also answers on port 7480.

- **Online, stale, offline**: A machine's status: it reported in the last 30 seconds (online), not for 30 seconds (stale), or not for 120 seconds (offline). Stale and offline cards show the last report, marked as not live.

- **Outcome unknown**: The executor could not confirm whether a change happened. OneMind never retries by itself; a person decides.

- **Owner**: The person who may approve. On a developer install, whoever has the owner token printed at install.

- **Principal**: Whoever is calling the hub, with an id, a kind (person or agent) and a role (owner, adult, guest or agent).

- **RAUC**: The open-source tool that installs updates into the A/B slots on the OneMind image.

- **restic**: The open-source backup program OneMind will use. Its format is documented, so you can restore without OneMind.

- **Scan record**: The security report of an app, `apps/<id>/scan.json`: licence, vulnerabilities, malware, secrets, signature and a test install. An app installs only with a passing record newer than 7 days.

- **Tier**: An app's overall verdict, set by the checks: verified, community or blocked.

- **Trivy**: An open-source scanner for known vulnerabilities and leaked passwords in container images.

- **Trust card**: The licence, tier and last scan shown next to every app's Install button.

- **TUF (The Update Framework)**: A standard for signed update indexes. The OneMind image trusts an update only if its index is signed by keys it already knows.

- **Verified (tier)**: An app that passed every check.
