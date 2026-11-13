---
title: Remote access
description: OneMind has no built-in remote access yet. How to reach your hub safely from outside today, and the private mesh that is coming.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

**Remote access** means using your OneMind when you are not on the same network as it, for example approving a request from your phone while you are away. OneMind does not do this by itself yet. This page explains why you should not simply open it to the internet, what to do instead, and what is coming.

## Today: keep the hub on a trusted network <span class="om-tag om-tag--ok">works today</span>

A developer install is built for a home or lab network you trust:

- The dashboard and API on port **8080** use plain HTTP. Your access token travels **unencrypted**, so anyone who can watch the traffic can copy it.
- The message bus (NATS) on port **4222** has no password. Anyone who can reach it can send fake machine reports.
- The node agent on port **7480** answers anyone, read-only. Its report holds no secrets or personal data by design.

:::danger[Do not forward these ports on your router]
Never forward ports 8080, 4222, 6443 or 7480 from the internet to your hub, and on a cloud server block them with a firewall. See the [DigitalOcean notes](../../getting-started/install/#digitalocean-droplet) in the install guide.
:::

### Safe ways to reach the hub from elsewhere

**An SSH tunnel** carries the dashboard inside an encrypted SSH connection. If you can already log in to the hub with SSH:

```sh
ssh -L 8080:127.0.0.1:8080 <you>@<hub-address>
```

Leave it open and browse to `http://127.0.0.1:8080` on your laptop.

**A private VPN you already run** (for example WireGuard) puts your phone or laptop on the hub's network, encrypted. Then use the hub's address on that network as usual. The [phone app](../phone-app/) recommends this when you connect over plain HTTP.

### More than one machine

Machines join the hub over any network on which they can reach it on ports **6443** (k3s, encrypted and authenticated with the join token) and **4222** (NATS, not encrypted). Keep both on a trusted network. While a machine cannot reach the hub, it does not send or store its reports; it sends a fresh one as soon as the link is back, so the dashboard never shows old reports as live.

## Coming soon: your own private mesh <span class="om-tag om-tag--unknown">coming soon</span>

Most of the pieces are on `main` already, tested on their own, but not switched on in the running hub or the command-line tool yet:

- **A private network between your machines, phones and laptops (a mesh).** Each device gets an encrypted WireGuard connection to the others, even across home routers. It is coordinated by a server that runs on your own hub (Headscale), not by an outside company. In a lab test on 12 November 2026, machines behind two separate home-style routers connected with no ports opened on either router.
- **Joining needs your approval.** A machine or phone gets a one-time key only after you approve the request, like any other change.
- **Sites that survive outages.** Each site gets its own NATS relay (a *leaf node*) that stores messages while the link is down and delivers them when it is back. In the same lab test, 1,200 of 1,200 messages sent during a 30-minute outage arrived afterwards, in order.
- **Apps with your sign-in in front.** Installed apps get their own addresses such as `uptime-kuma.onemind.local`, reached through the hub, which checks who you are first.
- **HTTPS everywhere.** Each box gets its own certificate authority, so the dashboard and apps no longer use plain HTTP.

There is also a command, `onemind mesh status`, written but not yet part of the `onemind` tool. The design is in [Fabric](../../concepts/fabric/).
