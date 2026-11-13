---
title: Try it on a Mac
description: Run a practice OneMind hub on a Mac with Docker, with nothing reachable from the network.
status: works-today
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

You can try the dashboard, the Market and the approval flow on a Mac without a spare machine. The practice hub runs in Docker: the message bus (NATS), the gateway, the dashboard and one simulated machine.

:::note[A practice hub]
- **Nothing is really installed.** The gateway uses a pretend installer (the `noop` executor): Approve marks a request `succeeded` without running anything. It also skips the security-scan check, so even blocked apps can be "installed". A real hub does neither.
- **Nothing is reachable from the network.** Every port is bound to `127.0.0.1`, your Mac only.
- It is for learning and development, not for keeping data.
:::

## What you need

- Docker with Compose v2 (for example Docker Desktop), running.
- `git`, and ports 8080, 4222 and 7480 free on your Mac.

## Start it

```sh
git clone https://github.com/onemindos/ONEMINDOS.git
cd ONEMINDOS/deploy/compose
./gen-tokens.sh                 # once: random owner and agent tokens into ./local/ (not committed)
docker compose up -d --build
cat local/owner.token           # your owner token
open http://127.0.0.1:8080      # sign in with it
```

The first start builds the gateway, the node agent and the dashboard, so it takes longer than later starts.

## What you will see

- On **Nodes**, one simulated machine, `node-sim`. The hub itself does not appear: the practice hub runs no node agent for it.
- In the **Market**, every app in the catalog, with its real trust card.
- In **Approvals**, your requests. Approve them to see the whole flow, then continue with [First steps](../first-steps/).

`local/agent.token` is an **agent** token (id `dev-agent`). Sign in with it in a second browser window to see what an AI agent may and may not do, or use it with the [MCP example](../../guides/agents/#try-it-by-hand) against `http://127.0.0.1:8080/mcp`.

## Check it

`verify.sh` checks every part, including that an agent can request but never approve:

```sh
../verify/verify.sh http://127.0.0.1:8080 --token-file local/owner.token \
  --agent-token-file local/agent.token
```

One SKIP is expected: "hub_node_id has no heartbeat", for the reason above.

## Stop it

```sh
docker compose down       # stop; your requests and audit log are kept
docker compose down -v    # stop and delete everything
```

## Without Docker: the dashboard on made-up data

The dashboard alone can run on built-in sample data, with no hub at all. This needs Node.js:

```sh
cd dashboard && npm ci && npm run dev:mock
```

Open `http://localhost:5173` and sign in with `owner-demo`, `agent-demo` or `adult-demo` to see each role.
