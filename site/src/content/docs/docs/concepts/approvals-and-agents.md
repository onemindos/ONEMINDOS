---
title: Approvals and agents
description: Every change is an action that an owner approves. AI agents can ask, and never approve.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

OneMind has one rule that everything else follows: **AI never acts without a human yes.** The rule lives in the gateway's code, not in a prompt, so it holds even when a model is confused or tricked. Prompt injection cannot be reliably prevented today, which is why the brake has to sit in the OS and not in the AI client.

## Actions <span class="om-tag om-tag--ok">works today</span>

Nobody changes the box directly. A person, a script or an agent files an **action**:

```json
{ "type": "app.install", "params": { "app_id": "ntfy" },
  "idempotency_key": "6f1c…", "expires_at": "2026-11-13T12:00:00Z" }
```

- **Exact parameters.** What you approve is exactly what runs.
- **An expiry.** Approving after `expires_at` returns `409 expired`, so a stale request cannot be approved by accident.
- **An idempotency key.** Sending the same request twice, for example after a network blip, returns the same action instead of creating a second one.

The action then moves through fixed states:

```
requested → awaiting_approval → accepted → dispatched → succeeded | failed | outcome_unknown
                              ↘ expired | cancelled
```

Only a principal with the **owner** role can approve or deny. Only after approval does the **executor** run (`kubectl apply -k` into the namespace `app-<id>`). The executor is the only part of the gateway that touches the outside world.

## Principals

A **principal** is whoever is calling: `{id, kind: person|agent, role: owner|adult|guest|agent}`. In v0, principals come from a tokens file in which each token is stored only as its SHA-256 hash. Single sign-on with household roles is planned.

## The audit log <span class="om-tag om-tag--ok">works today</span>

Every decision, including a refused approval attempt, is appended to a JSONL file in which each line carries the hash of the line before it. Editing, deleting or reordering any past line breaks the chain. When NATS is up, each entry is also published on `onemind.audit`.

## Agents <span class="om-tag om-tag--warn">in review</span>

An app can ask for its own agent identity in its manifest:

```yaml
spec:
  agent: {principal: true, secret: hermes-agent-onemind}
```

When the owner approves its install, the gateway:

1. creates the principal `agent:<app-id>` with a fresh random token;
2. puts the gateway URL and that token into a Kubernetes Secret in the app's namespace;
3. revokes the principal and deletes the Secret when the app is removed.

The agent then talks to the gateway over **MCP** (Model Context Protocol, Streamable HTTP at `POST /mcp`). It gets three tools: `list_nodes`, `list_apps` and `request_action`. **There is no approve tool.** If the agent calls the REST approve endpoint anyway, it gets `403 permission_denied`.

### The demo we hold ourselves to

1. You ask the Hermes agent: "install ntfy".
2. An action appears in **Approvals**, marked as requested by an agent.
3. You approve. ntfy is installed.
4. The audit chain records requester `agent:hermes-agent` and approver `person:owner`.

## Planned

- **Approvals on your phone.** A push notification that only says "something needs you". The phone then fetches the details from your own box, so Apple and Google see *that* an alert arrived, never *what* it was.
- **Household roles** (Owner, Adult, Teen, Child, Guest) with parental policy that the gateway enforces for agents too.
- **More action types**: backups, restores, updates, node changes. Agents may *trigger* a backup and read its status. Restores, key changes and deletions always need a human.
