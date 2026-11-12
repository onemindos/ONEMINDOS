---
title: Install
description: Install OneMind with one script on Debian 13, a Raspberry Pi 5 or a DigitalOcean droplet, as a hub or as a node.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

:::caution[Developer install, no OS rollback]
`deploy/install.sh` installs OneMind **on top of** a normal operating system. That system keeps updating its packages in place, so if an update goes wrong, nothing can roll it back. This is the only way to install OneMind today, and it is meant for learning, labs and early adopters. The OneMind image, with A/B updates and automatic rollback, is being built.
:::

You need **one hub** (the first machine; it runs the dashboard) and, if you like, more **nodes** that join it. No spare machine? [Try it on a Mac](../mac/) first.

## What has been tested

| Machine | Status |
|---|---|
| Debian 13 virtual machines, arm64 (hub and node) | <span class="om-tag om-tag--ok">tested</span>: install, re-run, node join, uninstall, and every `verify.sh` check |
| Debian 13 on an amd64 PC or mini PC | <span class="om-tag om-tag--warn">not yet run</span>: same script, only the pinned download hashes differ |
| Raspberry Pi 5 with Raspberry Pi OS (64-bit, trixie) | <span class="om-tag om-tag--warn">not yet run</span> on real hardware |
| DigitalOcean droplet with Debian 13 | <span class="om-tag om-tag--warn">not yet run</span> |
| NVIDIA Jetson dev kit with Jetson Linux (L4T) | <span class="om-tag om-tag--warn">not yet run</span> |

If you are first on one of the "not yet run" machines, please report what happened ([Troubleshooting](../../guides/troubleshooting/#getting-help)).

## What you need

- A **64-bit** machine (`amd64` or `arm64`) running **Debian 13** ("trixie"), **Raspberry Pi OS (64-bit)** based on trixie, **Jetson Linux** on a dev kit, or a **Debian 13 droplet**. The script stops on anything else.
- Administrator rights (`sudo`, or the root account) and an internet connection. The script downloads k3s, NATS and build tools at pinned versions and checks each download against a known fingerprint.
- For the hub, at least **4 GB of memory** and an SSD are the target. Each app states its own minimum (Home Assistant asks for 2 GB).
- `git`, to get the code. Many minimal systems do not have it: `sudo apt-get install -y git`.

## 1. Get the code

On the machine that will be the hub:

```sh
git clone https://github.com/onemindos/ONEMINDOS.git
cd ONEMINDOS
```

The script builds OneMind's own programs from this copy of the code, because no ready-made release is published yet.

## 2. Install the hub

```sh
sudo deploy/install.sh --role hub
```

The hub runs k3s (the system that runs apps), NATS (the message bus), the node agent `onemindd`, the gateway and the dashboard, each as a system service. Running the script again later is safe: every step checks what is already there.

At the end it prints:

- **The owner token.** You sign in with it. **Write it down now: it is shown once.** The hub keeps only a fingerprint of it, so it cannot show it again.
- **The join command** for adding machines, with the join token in it. This is printed every time the script runs.
- The address of the dashboard. By default the hub uses the address of its main network connection; add `--hub http://<name-or-address>:8080` to choose another.
- The commands for giving the Hermes AI agent its model key, if you plan to install that app later ([AI agents](../../guides/agents/)).

## 3. Open the dashboard

Browse to `http://<hub-address>:8080` and paste the owner token. You should see one machine, the hub, as **online**. Continue with [First steps](../first-steps/).

## 4. Add a machine (optional)

On each other machine, get the code (step 1), then run the join command the hub printed:

```sh
sudo deploy/install.sh --role node --hub http://<hub-address>:8080 --token <join-token>
```

The machine joins k3s as a worker (never as a second hub; it cannot see the hub's admin keys) and starts reporting. It appears on the Nodes screen within about 10 seconds. It must be able to reach the hub on ports 6443 and 4222.

## 5. Check everything

`verify.sh` checks each part of OneMind against your hub and prints PASS, FAIL or SKIP for each. It needs only `bash`, `curl` and `python3`, so it also runs from a laptop:

```sh
read -rs ONEMIND_TOKEN && export ONEMIND_TOKEN   # paste the owner token; it stays out of your shell history
deploy/verify/verify.sh http://<hub-address>:8080 --no-execute
```

Without `--no-execute`, it really installs ntfy and removes it again to test the whole path, which also deletes ntfy's data if you use it. It also checks the message bus on port 4222; where that port is blocked (as on a firewalled droplet), add `--nats none`. On the hub, it can check the audit log's chain too:

```sh
sudo --preserve-env=ONEMIND_TOKEN deploy/verify/verify.sh http://127.0.0.1:8080 \
  --no-execute --audit-file /var/lib/onemind/audit.jsonl
```

## Machine-specific notes

### Debian 13 PC or mini PC

Install Debian 13 as usual (the server install without a desktop is enough), then follow the steps above.

### Raspberry Pi 5

- Install **Raspberry Pi OS (64-bit)**, the trixie version; Lite (no desktop) is enough. The 32-bit version does not work.
- The first run will usually stop with `the memory cgroup is off; /boot/firmware/cmdline.txt was updated. Reboot, then run this script again.` k3s needs a kernel feature that Raspberry Pi OS leaves off; the script has switched it on. Run `sudo reboot`, then the same command again.
- An SSD is better than a memory card for a hub: apps write often, and memory cards wear out.

### DigitalOcean droplet

- Create a droplet with **Debian 13** and at least 4 GB of memory for a hub. You log in as `root`, so leave out `sudo` in the commands, or create a normal user first.
- **Put a firewall in front before you install.** A droplet is on the public internet, and a developer install is built for a trusted network: the dashboard (8080) uses plain HTTP, so your token would cross the internet unencrypted, and the message bus (4222) has no password. With a DigitalOcean Cloud Firewall, allow incoming **SSH (22)** only, plus 6443 and 4222 only from the addresses of machines you join to it.
- Reach the dashboard through an SSH tunnel, from your laptop:

  ```sh
  ssh -L 8080:127.0.0.1:8080 root@<droplet-address>
  ```

  then browse to `http://127.0.0.1:8080`.
- By default the hub advertises its public address. That is what the join command uses.

### NVIDIA Jetson

Use a dev kit with Jetson Linux (L4T) from NVIDIA. The script recognises it and follows the same steps.

## Options

| Flag | What it does |
|---|---|
| `--role hub\|node` | Hub: k3s server, NATS, onemindd, gateway and dashboard. Node: k3s worker and onemindd. |
| `--hub URL` | The hub's address, for example `http://hub.local:8080`. Required on nodes; on the hub, the address it tells others. Its host is also used for k3s (`:6443`) and NATS (`:4222`). |
| `--token T` | The join token the hub printed (nodes only). |
| `--gateway-bind ADDR` | Where the gateway listens (default `0.0.0.0`, all networks). `127.0.0.1` keeps it on the hub only, but then other machines, your phone and apps with their own AI agent cannot reach it. |
| `--onemindd-bin FILE`, `--dashboard-dist DIR` | Use ready-built programs instead of building with Go and Node. |
| `--force-os` | Try a system the script was not written for. |
| `--uninstall [--purge]` | Remove everything the script installed, **k3s and every app's data included**. The gateway's database and audit log in `/var/lib/onemind` are kept unless you add `--purge`. |

## Updating and removing

- **Update:** `git pull`, then run the same install command again. See [Updates and rollback](../../guides/updates/).
- **Remove:** `sudo deploy/install.sh --uninstall`. This deletes all apps and their data; OneMind has [no backups yet](../../guides/backups/).

## Security updates on a developer install

Because there is no A/B rollback here, the script turns on Debian's own `unattended-upgrades` for security updates only, the method Debian documents, and `needrestart` to restart the services that use an updated library. The OneMind image will do better: it applies security updates when the image is built and ships them as signed A/B updates. See [Updates and rollback](../../concepts/updates-and-rollback/).
