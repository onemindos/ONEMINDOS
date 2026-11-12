---
title: Why OneMind
description: Your machines, one private cloud, and AI that has to ask first.
date: 2026-11-12
author: The OneMind team
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

Most of us already own more computing than we use: a mini PC in a drawer, a Raspberry Pi, an old laptop, a GPU box, a cheap cloud VM. What we don't have is a way to make them **one** thing that we control: one place for our apps, our backups, our home and our AI agents, that keeps running when one machine dies and that doesn't phone home to work.

There are good projects that solve part of this. Before we wrote any code we took more than twenty of them apart: home-server OSes, NAS systems, self-hosting platforms, edge Kubernetes distributions. We read their code at pinned commits, their update logic, their licences and their websites. [The matrix is public](https://github.com/onemindos/ONEMINDOS/blob/main/research-output/02-competitors/MATRIX.md). Three things stood out.

## 1. Nobody checks that an update worked before keeping it

Several of these systems keep two copies of the OS and switch between them on update. That's the right idea. But every one we read marks the new copy good as soon as one of its own programs starts, or when boot reaches a certain point. None waits until the box is actually doing its job.

OneMind keeps an update only after fresh signs that k3s and the core services are healthy, measured after this boot. If they aren't, the box rolls back by itself. The gate is on `main` today and runs in our QEMU boot tests.

## 2. AI agents are being given the keys

Agents are getting good, and every home-server project is adding them. Some let an agent install updates and reboot the box, with only a hint in the AI client as a brake. Prompt injection cannot be reliably prevented today. So the brake has to be in the OS.

In OneMind an agent can **ask**: it files an action with exact parameters and an expiry. Only a person with the owner role can **approve**. The agent's MCP tools include `request_action` and nothing that approves. Every request and every decision lands in a hash-chained audit log. That is the core of the system, and it works today.

## 3. Trust is hard to see

An app store is a list of things you're asked to run as root-adjacent code on the machine that holds your family photos. You should be able to see what you're trusting: the real licence, the exact image, whether it was scanned for known vulnerabilities and malware, and when. OneMind puts that on a **trust card** next to every Install button, and the gateway refuses to install an app without a fresh passing scan.

## What we're building first

The founder's own test is simple: replace the Kubernetes cluster he runs today with OneMind OS, and use it every day. That sets the order:

1. **The core**: stable, usable, well designed. Security, multiple nodes, backups, deployments, automation, notifications.
2. **A properly designed dashboard**, and phone apps for Android and iPhone that show everything happening: nodes, apps, approvals, activity, notifications.
3. **The start of a plugin ecosystem**, with UI extension points. Headless operation stays first-class.

## What works today

We'd rather show you a short honest list than a long hopeful one. [Here it is](../../docs/), and it's repeated on the front page. If it isn't on `main`, we say "in review" or "planned".

## Why open source

OneMind is Apache-2.0: the OS, the SDK, the app format, the CLI and the gateway. An OS for owning your own computing has to be something you can read, fork and leave. Your backups are plain restic repositories; your apps are plain Kubernetes manifests.

If that sounds like something you want, [install it on a spare machine](../../docs/getting-started/install/), break it, and [tell us](../../community/).
