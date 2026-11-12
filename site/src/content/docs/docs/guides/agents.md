---
title: AI agents
description: What an AI agent can and cannot do on OneMind, how an app gets its own agent identity, and how to connect your own AI client over MCP.
status: works-today
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

An **agent** is a program that acts on its own, usually driven by an AI model: an assistant you chat with, an automation, a script. On OneMind an agent has its own identity, separate from yours, and **it can ask but never decide**. Every change it wants becomes a request that waits for you on the Approvals screen.

This rule is built into the hub (the **gateway**), not into the AI's instructions. A confused or tricked model cannot talk its way past it, because the hub simply has no way for an agent to approve anything. [Approvals and agents](../../concepts/approvals-and-agents/) explains the reasoning.

## What an agent can do

- **See your machines**: the same list as the Nodes screen (hardware, OS, status).
- **See the app catalog**: every app, whether it is installed, and its licence, tier and last scan.
- **Ask to install or remove an app**, optionally with a short reason (up to 500 characters). The request lands in **Approvals** marked as coming from an agent. A request made over MCP can be approved for **24 hours**.

## What an agent cannot do

- **Approve or deny anything**, including its own requests. If it tries, the hub answers `403 permission_denied` and writes the attempt to the audit log.
- **Change anything without a request.** In v0, the only changes anyone can request are installing and removing apps.
- **Install an app that failed its security scan.** The scan check applies to everyone; see [why an app can be blocked](../apps/#why-an-app-can-be-blocked).
- **Act as a person.** A token set up as an agent can never be given the owner role: the hub refuses a tokens file that pairs `kind: agent` with any role other than `agent`.

:::caution[Read the request, not the reason]
An agent can write anything in its reason, including something misleading. The reason is kept in the audit log; the dashboard card shows the **exact parameters**, and those are what will run. Approve based on the parameters.
:::

## Way 1: an app with its own agent identity

An app can ask for an agent identity in its manifest. When you approve its install, the hub:

1. creates the agent `agent:<app-id>` with a fresh random token;
2. puts the hub's address and that token into a Kubernetes Secret inside the app's namespace, so the app can find them;
3. deletes the identity, and the token stops working, when you remove the app (or when the install fails).

**Hermes Agent** is the first such app. Its trust card shows whether it can be installed right now: on 12 November 2026 its scan was failing, so it was blocked. Hermes also needs a key for an AI model provider. The hub install prints the commands for creating that key's Secret yourself, so the key never passes through the OneMind repository or the dashboard.

## Way 2: connect your own AI client over MCP

**MCP** (the Model Context Protocol) is the common way for AI assistants to use outside tools. The hub has an MCP endpoint for agents:

| Setting | Value |
|---|---|
| Address | `http://<hub-address>:8080/mcp` |
| Transport | Streamable HTTP, protocol version 2025-06-18 |
| Sign-in | `Authorization: Bearer <agent token>` |
| Tools | `list_nodes`, `list_apps`, `request_action` (`type` is `app.install` or `app.remove`, plus `app_id` and an optional `reason`) |

There is no approve or deny tool. A person's token is refused on `/mcp` with `403`; only agent tokens work there.

Your AI client must support MCP over Streamable HTTP and let you add an `Authorization` header. Check its documentation; OneMind does not ship a client of its own.

### Create an agent token (developer install)

On the hub, the tokens file `/etc/onemind/tokens.yaml` lists who may sign in. It stores only a fingerprint (a SHA-256 hash) of each token, never the token itself. To add an agent called `my-assistant`:

```sh
TOKEN=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
printf '  "sha256:%s": {id: my-assistant, kind: agent, role: agent}\n' \
  "$(printf %s "$TOKEN" | sha256sum | cut -d' ' -f1)" | sudo tee -a /etc/onemind/tokens.yaml >/dev/null
echo "$TOKEN"    # give this to your AI client now; it is not stored anywhere
unset TOKEN
```

The hub notices the changed file on the next request; no restart is needed. If the file has a mistake, the hub keeps the last good list and logs an error (`journalctl -u onemind-gateway`).

To take the token away again, delete that line from the file.

On the [Mac practice hub](../../getting-started/mac/), `deploy/compose/local/agent.token` already is an agent token (id `dev-agent`).

### Try it by hand

With the agent token in a variable (`read -rs AGENT_TOKEN` keeps it out of your shell history), ask for an install the way an AI client would:

```sh
curl -s http://<hub-address>:8080/mcp \
  -H "Authorization: Bearer $AGENT_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"request_action","arguments":{"type":"app.install","app_id":"ntfy","reason":"trying the agent path"}}}'
```

The answer contains the new request's id and the state `awaiting_approval`. Open **Approvals**: the card says it was requested by an agent, `my-assistant`. Approve or deny it as usual. Use `"method":"tools/list"` (with no `params`) to see the three tools.

`deploy/verify/verify.sh` runs these checks for you when you give it `--agent-token-file`, including that the agent's attempt to approve is refused.

## What gets recorded

Every request, approval, denial and refused attempt goes into the hash-chained audit log with who asked and who decided, for example requester `my-assistant` (an agent) and approver `owner` (a person). See [First steps](../../getting-started/first-steps/#5-check-the-audit-log) to check it.

## Coming soon

- **Approvals on your phone**, as a push notification that only says "something needs you".
- **More request types**: backups, updates, node changes. Agents will be allowed to *start* a backup and read its status; restores, key changes and deletions will always need a person.
- **Scopes**: limiting each agent to the tools and apps it needs.
- **Household roles**, so the same rules apply to agents acting for a teen or a guest.
