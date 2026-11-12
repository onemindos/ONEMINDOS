---
title: Install
description: Install OneMind on stock Debian 13 with one script, as a hub or as a node.
status: in-review
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

:::caution[Developer install, no OS rollback]
`deploy/install.sh` installs OneMind **on top of** a stock operating system. Packages are upgraded in place, so nothing can roll the OS back if an update goes wrong. It is for development, labs and early adopters. The OneMind image, with A/B updates and automatic rollback, is being built.

The script is written and waiting in an open pull request. These steps describe that pull request and will work once it is merged into `main`.
:::

## What you need

- A 64-bit machine running **Debian 13** ("trixie"), **Raspberry Pi OS trixie**, NVIDIA Jetson Linux (L4T) on a dev kit, or a Debian 13 cloud VM.
- `sudo` access and an internet connection.
- For the hub: at least 4 GB of RAM and an SSD is the target. Apps declare their own minimum memory (Home Assistant asks for 2 GB).

## 1. Install the hub

The hub is the first machine. It runs the k3s server, NATS, the gateway and the dashboard.

```sh
git clone https://github.com/onemindos/ONEMINDOS.git
cd ONEMINDOS
sudo deploy/install.sh --role hub
```

The script builds `onemindd`, the gateway and the dashboard from your checkout, installs k3s and NATS at pinned versions with checked hashes, and starts everything as systemd services. Running it again is safe: every step checks what is already there.

At the end it prints two things. **Write both down. They are shown once.**

- **The owner token.** You sign in to the dashboard with it. The hub stores only its SHA-256 hash, so it cannot show it again.
- **The join token** for adding nodes.

## 2. Open the dashboard

Browse to `http://<hub>:8080` and paste the owner token. You should see one node, the hub, as **online**.

## 3. Add a node (optional)

On a second machine:

```sh
git clone https://github.com/onemindos/ONEMINDOS.git
cd ONEMINDOS
sudo deploy/install.sh --role node --hub http://<hub>:8080 --token <join-token>
```

The node joins k3s as an agent (never as a server) and starts sending heartbeats. Within about 10 seconds it appears on the Nodes screen.

## 4. Check everything

`verify.sh` checks every item of the contract against your hub, over HTTP and NATS, and prints PASS, FAIL or SKIP for each:

```sh
export ONEMIND_TOKEN=<owner-token>
deploy/verify/verify.sh http://<hub>:8080 --token "$ONEMIND_TOKEN"
```

## Options

| Flag | What it does |
|---|---|
| `--role hub\|node` | Hub: k3s server, NATS, onemindd, gateway and dashboard. Node: k3s agent and onemindd. |
| `--hub URL` | The hub's gateway URL. Its host is also used for k3s (`:6443`) and NATS (`:4222`). |
| `--token T` | The join token the hub printed (nodes only). |
| `--gateway-bind ADDR` | Gateway listen address. `127.0.0.1` keeps it local, but then app pods and other machines cannot reach it. |
| `--onemindd-bin FILE`, `--dashboard-dist DIR` | Use prebuilt artifacts instead of building with Go and Node. |
| `--uninstall [--purge]` | Remove everything the script installed, k3s and its data included. `--purge` also deletes the gateway database and audit log. |

## Security updates on a developer install

Because there is no A/B rollback here, the script turns on Debian's own `unattended-upgrades` for security updates only, the policy Debian documents. The OneMind image does better: it applies security updates at build time and ships them as signed A/B updates. See [Updates and rollback](../../concepts/updates-and-rollback/).
