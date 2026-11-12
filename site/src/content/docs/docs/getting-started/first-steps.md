---
title: First steps
description: Sign in, find your way around the Home screen, see your machines, install your first app through an approval, and check the audit log.
status: works-today
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

This walk-through uses the dashboard, the web screens of your OneMind. Every button is also a plain API call (see [Contract API](../../reference/contract-api/)), so scripts and AI agents follow exactly the same path, under the same rules.

## 1. Sign in

Browse to your hub: `http://<hub-address>:8080` (on the Mac practice hub, `http://127.0.0.1:8080`). You see **Welcome to OneMind**.

Paste your **access token** (the owner token the install printed) and press **Sign in**.

- "That token was not accepted by the hub." means the token is wrong. Paste it again.
- "Could not reach the hub" means your browser cannot reach the hub at all. See [Troubleshooting](../../guides/troubleshooting/#signing-in).

The dashboard keeps your token only for this browser tab: closing the tab signs you out, and **Sign out** at the top right does the same. A static token is a stand-in for now; accounts with passkeys are <span class="om-tag om-tag--unknown">coming soon</span>.

## 2. The Home screen

The bar at the top has **Home**, **Nodes**, **Market** and **Approvals**. A number next to Approvals counts the requests waiting for you.

Home shows, from top to bottom:

- **A greeting and your OneMind's name**, with its version and the id of the hub machine.
- **Machines**: how many are **online**, **stale** and **offline**, and how long ago the hub was last asked ("Checked 3s ago"). Below that, **See all machines**, and a link to the requests waiting for approval, if there are any.
- **Your apps**: a tile for each installed app, or "No apps yet. Browse the Market." on a new hub.

Home refreshes by itself (machines every 10 seconds); you never need to reload the page.

:::note
The app tiles link to the app's port on the hub, but on `main` today apps are reachable only inside the hub. Opening an app takes one extra step for now: see [Open an installed app](../../guides/apps/#open-an-installed-app). A new Home screen, with widgets, wallpapers and an app launcher, is designed and <span class="om-tag om-tag--unknown">coming soon</span>.
:::

## 3. See your machines

Open **Nodes** (the page is called **Machines**). Each card shows the machine's name, its board (for example *Raspberry Pi 5* or *DigitalOcean droplet*), whether it is the hub, its OS and kernel, k3s state, boot slot ("no A/B (developer install)" on a developer install), processor, free memory and disk, an NVIDIA GPU if it has one, and its Secure Boot and TPM state.

A machine that stops reporting turns **stale** after 30 seconds and **offline** after 120 seconds. Its card gets a dashed border and says its values are **the last report, not live**, with when it was last seen. OneMind never shows old numbers as if they were current.

From a terminal:

```sh
onemind node info                                   # what this machine reports
export ONEMIND_TOKEN=<owner-token>
onemind nodes --hub http://<hub-address>:8080       # every machine the hub knows
```

## 4. Install your first app

1. Open **Market** and pick an app whose **Install** button is active, for example **ntfy**, a notification server. A greyed-out button has its reason written under it ([why an app can be blocked](../../guides/apps/#why-an-app-can-be-blocked)).
2. Press **Install**. Nothing is installed yet: OneMind writes a **request** with the exact app, valid for 1 hour, and takes you to **Approvals**.
3. Read the card: who asked (you, a person), the action type `app.install`, when it expires, and the **exact parameters**.
4. Press **Approve**. The request moves through `accepted` and `dispatched` to `succeeded`, and the app is installed in its own area, `app-ntfy`.

Only an **owner** can approve. An AI agent that tries gets refused, and the attempt itself is recorded. The [Apps guide](../../guides/apps/) covers the rest: reading trust cards, failed installs, removing apps.

## 5. Check the audit log

Every request and decision is added to an audit log in which each line carries a fingerprint of the line before it. Editing, deleting or reordering any past line breaks the chain, so tampering shows. On the hub, `verify.sh` checks the whole chain:

```sh
read -rs ONEMIND_TOKEN && export ONEMIND_TOKEN   # paste the owner token
sudo --preserve-env=ONEMIND_TOKEN deploy/verify/verify.sh http://127.0.0.1:8080 \
  --no-execute --audit-file /var/lib/onemind/audit.jsonl
```

In a development checkout, `ONEMIND_AUDIT_PATH=<file> make -C core audit-verify` does the same.

## What's next

- Put an AI agent to work, under the same rules: [AI agents](../../guides/agents/).
- See every guide: [User guides](../../guides/).
