---
title: Apps
description: Find an app in the Market, read its trust card, request and approve an install, and understand why an app can be blocked.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

An **app** is a program OneMind runs for you, such as a notification server or a password manager. Each app runs in its own walled-off area on the hub (a Kubernetes **namespace** called `app-<id>`). This guide uses the dashboard; the [phone app](../phone-app/) and the [API](../../reference/contract-api/) follow the same steps.

## Who can do what

| You signed in as | Browse the Market | Ask for an install or removal | Approve or deny |
|---|---|---|---|
| **Owner** (the token the install printed) | yes | yes | yes |
| **Agent** (an AI or a script) | yes | yes | **never** |
| **Adult** or **guest** | yes | no | no |

On a developer install there is one person, the owner. Household accounts with their own sign-in are <span class="om-tag om-tag--unknown">coming soon</span>.

## The Market <span class="om-tag om-tag--ok">works today</span>

Open **Market** in the top bar. Each card shows:

- the app's **name**, **category** and **version**, and an **Installed** badge if you already have it;
- **Runs on**: the processor types it supports (`amd64` for most PCs, `arm64` for a Raspberry Pi or a Mac);
- **Needs**: a GPU, or the minimum memory it asks for;
- the three **trust facts**: licence, tier and last scan (below);
- links to the app's docs, source code, website and support, when the app publishes them.

Click an app's name to open its own page (`/market/<app-id>`). It adds the requirements in full: memory, whether a GPU is needed, and the web port the app listens on.

## Reading the trust card

Every fact on the card comes from a file in the OneMind repository, written by an automatic check, never typed by hand.

| Fact | What it tells you |
|---|---|
| **Licence** | The app's open-source licence, read from the upstream project. Licences are sorted into classes: **L1** and **L2** are allowed in the Market; anything unknown or non-commercial is **blocked**. |
| **Tier** | **Verified**: every check passed. **Community**: the checks pass, but the upstream project is archived or has not released anything in 18 months. **Blocked**: the licence, a malware hit or a critical check failed. **Not rated**: no tier recorded. |
| **Last scan** | The date of the last security scan and whether it **passed** or **failed**, or **Not scanned**. Dates are shown in UTC. |

Behind "last scan" is a full report. The scan checks that every container image is pinned to an exact, unchangeable version, looks for known vulnerabilities (with Trivy), for malware (with ClamAV) and for passwords left inside the image, checks the image signature when the upstream signs, and finally installs the app on a throwaway cluster to see that it answers. The report is in the repository as `apps/<id>/scan.json`, and the [apps catalog on this site](../../../apps/) shows it for every app. Every app is scanned again each day.

## Install an app <span class="om-tag om-tag--ok">works today</span>

1. In **Market**, press **Install** on the app you want (for example ntfy, if its button is active).
2. Nothing is installed yet. OneMind writes a **request** (an *action*) with the exact app, and takes you to **Approvals**, where the new request is highlighted.
3. Read the request card:
   - **Requested by**: a person or an agent, and when;
   - **Action type**: `app.install` or `app.remove`;
   - **Expires**: a request made from the dashboard can be approved for **1 hour**;
   - **Exact parameters**: what will run. What you approve is exactly what runs.
4. Press **Approve**. The request moves through `accepted` and `dispatched` to `succeeded`, and the app shows as **Installed** in the Market and on Home. Press **Deny** instead and the request is `cancelled`.

Every step, including a refused attempt, is written to the [audit log](../../getting-started/first-steps/#5-check-the-audit-log).

**If it does not work:**

- **`failed`** means the hub tried and the install returned an error. The card shows "What the hub reported". The Market then shows "Last change failed", and you can request the install again.
- **`outcome unknown`** means the hub could not confirm what happened (for example, a timeout). OneMind never retries by itself, because it cannot know what was already applied. Request again, or remove the app.
- **"This request has expired and can no longer be approved."** Make a new request from the Market.

On the [Mac practice hub](../../getting-started/mac/), Approve marks the request `succeeded` without installing anything: it runs a pretend installer so you can learn the flow.

## Why an app can be blocked

If an app's **Install** button is greyed out, the reason is written right under it. These are the four reasons, word for word:

| What you see | What it means |
|---|---|
| "Not scanned yet. Only apps with a passing security scan from the last 7 days can be installed." | There is no scan report for this app. Nothing unscanned runs. |
| "Failed its last security scan (*date*)." | The last scan found a problem: a critical vulnerability that already has a fix, malware, a password inside the image, a licence that is not allowed, an image that is not pinned for every processor type, a signature that does not verify, a container that runs as the all-powerful root user when it does not need to, or a test install that did not start. |
| "Last scanned *date*, more than 7 days ago. Waiting for a new scan." | The report is too old to trust. The next daily scan refreshes it. |
| "The scan record has an invalid date, so it cannot be trusted." | The report is damaged. It counts as missing. |

For example, the scans of 12 November 2026 blocked Home Assistant, Node-RED, Uptime Kuma and Hermes Agent because each image had critical vulnerabilities that already had fixes upstream, and blocked Mosquitto because its licence was classed as not allowed. The [apps catalog](../../../apps/) always shows the current state.

**Can I install it anyway?** No, not on a real hub. The hub checks the scan again at the moment you press Approve, and refuses with `409 stale_precondition` if the report is missing, failed or older than 7 days, even when the dashboard showed the button. No setting turns this off on a hub that really installs apps. A blocked app becomes installable again when a newer scan passes, usually after the upstream project ships a fix.

**Removing is never blocked.** You can always remove an app, whatever its scan says.

## Open an installed app

The tiles under **Your apps** on Home link to the app's web port on the hub. On `main` today, apps are reachable only inside the hub's cluster, so that link does not open the app yet. A built-in way to open apps, with your OneMind sign-in in front of them, is <span class="om-tag om-tag--unknown">coming soon</span>.

Until then, forward the app's port from the hub (this example uses ntfy; the app's page in the Market shows its web port):

```sh
# On the hub: list the app's service and its port
sudo k3s kubectl -n app-ntfy get service
# Forward it to port 8081 on the hub (Ctrl+C stops it)
sudo k3s kubectl -n app-ntfy port-forward service/ntfy 8081:8080
```

Then browse to `http://127.0.0.1:8081` on the hub. From your laptop, open an SSH tunnel to the hub first, in a second terminal:

```sh
ssh -L 8081:127.0.0.1:8081 <you>@<hub-address>
```

and browse to `http://127.0.0.1:8081` on the laptop.

## Remove an app

Press **Remove *app*** in the Market or on the app's page, then approve the request. OneMind deletes the app and its whole `app-<id>` namespace.

:::danger[Removing an app deletes its data]
On `main` today, an app's data lives inside its namespace, and removing the app deletes it. OneMind has no backups yet ([Backups](../backups/)). Before you remove an app you care about, save what you need with the app's own export or backup feature.
:::

## Updating an installed app <span class="om-tag om-tag--unknown">coming soon</span>

There is no "update app" action yet. When the catalog gets a newer version of an app, an app you already installed keeps running the version it was installed with. Removing it and installing it again would delete its data, so do not use that as an update. See [Updates and rollback](../updates/).

## Coming soon

- **Grants**: apps that need a device, the host network or a GPU will say so, and you will see each permission before you approve.
- **App sandboxing**: restricted containers and default-deny network rules for every app. This is written and waiting in an open pull request.
- **"Open in OneMind"** buttons on this website that hand an app to your own hub, which asks you to confirm.
- **Alerts** when an app you have installed becomes blocked.

## Suggest an app

Add a line to [`apps/_intake/queue.yaml`](https://github.com/onemindos/ONEMINDOS/blob/main/apps/_intake/queue.yaml) and open a pull request. The tools fill in the rest from the upstream project and run the same checks. See [Apps and trust cards](../../concepts/apps-and-trust-cards/).
