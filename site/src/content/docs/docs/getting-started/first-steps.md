---
title: First steps
description: Install your first app through an approval, and see it in the audit log.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

This walk-through uses the dashboard. Every step is also a plain API call (see [Contract API](../../reference/contract-api/)), so scripts and agents follow exactly the same path.

## 1. See your machines

Open **Nodes**. Each card shows the board (`x86_64-efi`, `rpi5`, `jetson-orin`, `vm`…), the OS, k3s status, the booted RAUC slot when there is one, and when the machine was last seen.

A machine that misses heartbeats turns **stale** after 30 seconds and **offline** after 120 seconds. The dashboard never shows old numbers as if they were live.

From a terminal:

```sh
onemind node info                                   # what this machine reports
onemind nodes --hub http://<hub>:8080               # every machine the hub knows
```

## 2. Install an app

Open **Market** and choose **ntfy**. Pressing **Install** does not install anything yet. It creates an **action**: a written request with exact parameters, an expiry time and an idempotency key. The dashboard takes you to **Approvals**.

## 3. Approve it

In **Approvals** you see who asked (a person or an agent), what exactly they asked for, and when the request expires. Approve it. The action moves through `accepted`, `dispatched` and `succeeded`, and the app is applied into its own namespace, `app-ntfy`.

Only an **owner** can approve. An AI agent that tries gets `403 permission_denied`, and the attempt itself is logged.

## 4. Read the audit log

Every decision is appended to a hash-chained log: each line carries the hash of the line before it, so editing, deleting or reordering any past line is detectable. On a hub set up with the install script, `verify.sh` checks the whole chain:

```sh
sudo deploy/verify/verify.sh http://127.0.0.1:8080 --token "$ONEMIND_TOKEN" \
  --audit-file /var/lib/onemind/audit.jsonl --no-execute
```

In a development checkout, `ONEMIND_AUDIT_PATH=<file> make -C core audit-verify` does the same.

## What's next

- Put an AI agent to work, under the same rules: [Approvals and agents](../../concepts/approvals-and-agents/).
- Learn what the trust card on each app means: [Apps and trust cards](../../concepts/apps-and-trust-cards/).
