---
title: Troubleshooting
description: The messages you can meet while installing and using OneMind, what they mean, and what to do.
status: works-today
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

Messages are quoted exactly as OneMind prints them. Commands marked "on the hub" run on the hub machine of a developer install.

## First, look at the services

On the hub, four services make up OneMind; on every other machine, two:

```sh
systemctl status k3s onemind-nats onemindd onemind-gateway   # on the hub
systemctl status k3s-agent onemindd                          # on another machine
curl -s http://127.0.0.1:8080/healthz                        # on the hub: {"ok": true} when the gateway runs
curl -s http://127.0.0.1:7480/healthz                        # on any machine: the node agent
```

Each service's log is one command away: `journalctl -u <service> -e` (for example `journalctl -u onemind-gateway -e`).

To check everything at once, run `deploy/verify/verify.sh` ([Install](../../getting-started/install/#5-check-everything)). It prints PASS, FAIL or SKIP for each part.

## The install script

| Message | What to do |
|---|---|
| `ERROR: run as root (sudo)` | Run it with `sudo`, or as root. |
| `... is not a target of this script (Debian 13, Raspberry Pi OS trixie, Jetson L4T Ubuntu). --force-os to try anyway` | The script was written for those systems only. Use one of them. `--force-os` lets you try anything else, at your own risk. |
| `architecture '...' is not supported (amd64 or arm64 only)` | You are on a 32-bit system. On a Raspberry Pi, install the **64-bit** Raspberry Pi OS. |
| `the memory cgroup is off; /boot/firmware/cmdline.txt was updated. Reboot, then run this script again.` | Normal on a Raspberry Pi the first time. The script has switched on a setting k3s needs. Run `sudo reboot`, then the same install command again. |
| `the memory cgroup is not available; k3s cannot run` | The kernel does not offer a feature k3s needs. Use a standard Debian 13 kernel. |
| `k3s did not become Ready in 180 s (journalctl -u k3s)` | Read that log. Common causes: too little memory, or a disk that is full. |
| `the gateway did not answer /healthz in 60 s (journalctl -u onemind-gateway)` | Read that log. A port conflict on 8080 is one cause: another program already uses it. |
| `sha256 mismatch for ...` | A download did not match the checksum OneMind pins for it. The script refuses to use it. Try again later; if it repeats, report it, because it can mean the download was tampered with. |
| `--hub must look like http://HOST:8080` | Give the hub's address with `http://` and the port, for example `http://hub.local:8080`. |
| `--token has unexpected characters` | Copy the join token again, exactly as the hub printed it. |

## Signing in

| What you see | What it means and what to do |
|---|---|
| "That token was not accepted by the hub." | The token is wrong, or it is not in the hub's tokens file. Paste it again without spaces. |
| "Could not reach the hub" | Your browser cannot reach the gateway. Check the address and port (`:8080`), that you are on the same network, and that `onemind-gateway` is running. If the hub was installed with `--gateway-bind 127.0.0.1`, it only answers on the hub itself; use an SSH tunnel ([Remote access](../remote-access/)). |
| Signed out after closing the tab | Expected. The dashboard keeps your token only for that browser tab. |

### I lost the owner token

The hub never stores the token itself, only a fingerprint of it, so it cannot show it again. Make a new owner token on the hub:

```sh
TOKEN=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
printf '  "sha256:%s": {id: owner-2, kind: person, role: owner}\n' \
  "$(printf %s "$TOKEN" | sha256sum | cut -d' ' -f1)" | sudo tee -a /etc/onemind/tokens.yaml >/dev/null
echo "$TOKEN"    # write it down now
unset TOKEN
```

It works at once; no restart is needed. Then open `/etc/onemind/tokens.yaml` with `sudo` in an editor and delete the line of the lost token. The other way out, `--uninstall` and a fresh install, deletes your apps and their data.

## Machines

| What you see | What to do |
|---|---|
| A machine never appears on **Nodes** | On that machine: `systemctl status onemindd`, and check that `/etc/onemind/onemindd.env` names the hub as `nats://<hub-address>:4222`. The machine must be able to reach the hub on port 4222. |
| A machine shows **stale** (no report for 30 s) or **offline** (120 s) | It stopped reporting: it is off, its network is down, or `onemindd` stopped. The card's numbers are its last report, not live. |
| A machine is in k3s but its k3s part is not ready | On that machine: `journalctl -u k3s-agent -e`. It must reach the hub on port 6443. |
| The hub's address changed | Run the join command again on each machine (the hub prints it every time its install script runs). |
| What does this machine report? | `onemind node info` on it prints exactly what it sends to the hub. |

## Apps and approvals

| What you see | What it means and what to do |
|---|---|
| **Install** is greyed out with a reason under it | The app's security scan is missing, failed or too old. See [why an app can be blocked](../apps/#why-an-app-can-be-blocked). Nobody can override it on a real hub. |
| "Could not approve: app '...' failed its last scan ..." (or "... was last scanned N days ago ...") | The scan changed after the request was made. The hub checks again at approval. Deny the request, or let it expire. |
| "... expired before it was approved." or "This request has expired and can no longer be approved." | Requests from the dashboard last 1 hour, from an AI agent 24 hours. Make a new one. |
| "Only the owner can approve or deny requests." | You signed in with a token that is not an owner's. |
| "Your account cannot request installs. Ask the owner." | You signed in as an adult or guest. Only an owner or an agent can make requests. |
| A request ends **failed** | The card shows what the hub reported. On the hub, `sudo k3s kubectl -n app-<id> get pods` shows the app's containers; `journalctl -u onemind-gateway -e` shows the gateway's side. You can request the install again. |
| A request ends **outcome unknown** | The hub could not confirm the result, for example after a timeout. It never retries by itself. Check the app as above, then request an install or a removal. |
| The app's tile on **Home** does not open the app | Expected on `main` today. Use the port-forward steps in [Open an installed app](../apps/#open-an-installed-app). |

## The Mac practice hub

| What you see | What to do |
|---|---|
| Docker says port 8080, 4222 or 7480 is already in use | Something on your Mac already uses that port. Stop it, then `docker compose up -d` again. |
| `local/tokens.yaml exists (use --force to make new tokens)` | You already have tokens: they are in `deploy/compose/local/`. Run `./gen-tokens.sh --force` for new ones. |
| Approve "installs" an app that is blocked | Expected. The practice hub uses a pretend installer and skips the scan check; a real hub does not. |
| The hub is missing from **Nodes** | Expected. The practice hub runs no node agent for the hub itself; you see one simulated machine, `node-sim`. |
| Something else | `docker compose ps` and `docker compose logs gateway`. |

## The phone app

| What you see | What to do |
|---|---|
| It cannot connect | The phone must reach the hub: same Wi-Fi, or a VPN. Use the full address with `http://` and `:8080`. Requests give up after 10 seconds. |
| No notifications | Today they arrive only while the app is open. |

## Getting help

Open an issue on [GitHub](https://github.com/onemindos/ONEMINDOS/issues) with what you ran, what you expected and what happened. Before you paste logs or output, **remove tokens and addresses**: the repository is public. For a security problem, follow [Community](../../../community/#security) instead of opening a public issue.
