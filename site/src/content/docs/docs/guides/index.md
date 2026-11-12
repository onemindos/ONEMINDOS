---
title: User guides
description: Step-by-step guides for running OneMind today, with every part that is not ready yet marked "coming soon".
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

These guides describe what you can do with OneMind **today**, on the code in the `main` branch. Where a feature is not ready yet, the guide says so and marks it <span class="om-tag om-tag--unknown">coming soon</span>. Nothing here describes a screen or command that does not exist.

OneMind is still early. Today you install it yourself from the source code (a **developer install**), and you sign in with a long random token instead of a password. A ready-made OneMind image with automatic rollback, and proper accounts, are coming.

## Get started

| Guide | What you will do | Status |
|---|---|---|
| [Install](../getting-started/install/) | Set up a hub on Debian 13, a Raspberry Pi 5 or a DigitalOcean droplet, and add more machines | <span class="om-tag om-tag--ok">works today</span> |
| [Try it on a Mac](../getting-started/mac/) | Run a practice hub in Docker, with nothing reachable from the network | <span class="om-tag om-tag--ok">works today</span> |
| [First steps](../getting-started/first-steps/) | Sign in, read the Home screen, install your first app | <span class="om-tag om-tag--ok">works today</span> |

## Use OneMind

| Guide | What it covers | Status |
|---|---|---|
| [Apps](apps/) | The Market, trust cards, install requests and approvals, why an app can be blocked, opening and removing apps | <span class="om-tag om-tag--ok">works today</span> |
| [AI agents](agents/) | What an agent can and cannot do, connecting an AI client over MCP | <span class="om-tag om-tag--ok">works today</span> |
| [Updates and rollback](updates/) | Keeping a developer install up to date, and what the OneMind image will add | <span class="om-tag om-tag--warn">partly</span> |
| [Backups](backups/) | What is protected today (very little) and what is coming | <span class="om-tag om-tag--unknown">coming soon</span> |
| [Remote access](remote-access/) | Reaching your hub from outside your home, safely, today and later | <span class="om-tag om-tag--unknown">coming soon</span> |
| [Phone app](phone-app/) | The Android and iPhone app: what it does and how to try it | <span class="om-tag om-tag--warn">build it yourself</span> |
| [Desktop app](desktop-app/) | The Mac and Windows app | <span class="om-tag om-tag--unknown">coming soon</span> |

## When something goes wrong

- [Troubleshooting](troubleshooting/): the error messages you can meet, what they mean, and what to do.
- [Glossary](glossary/): every OneMind word in plain English.

## The one rule behind every guide

**Nothing changes on your OneMind until a person who owns it says yes.** Installing an app, removing one, and anything an AI agent asks for all become a written request that waits on the **Approvals** screen. The rule is enforced by the hub itself, not by a setting you could forget to turn on. [Approvals and agents](../concepts/approvals-and-agents/) explains why.
