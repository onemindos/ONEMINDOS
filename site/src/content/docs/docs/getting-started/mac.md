---
title: Try it on a Mac
description: Run a OneMind hub on a Mac with Docker, with nothing reachable from the network.
status: in-review
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

You can try the gateway, the dashboard and the approval flow on a Mac without a spare machine. The compose setup runs NATS, the gateway with the `noop` executor (it marks actions as done without installing anything), the dashboard and one simulated node.

:::note
Development only. Every port is bound to `127.0.0.1`. The compose files are in the same open pull request as the install script.
:::

```sh
git clone https://github.com/onemindos/ONEMINDOS.git
cd ONEMINDOS/deploy/compose
./gen-tokens.sh                 # once: random owner and agent tokens into ./local/ (gitignored)
docker compose up -d --build
open http://127.0.0.1:8080      # sign in with the token in local/owner.token
```

Check it, including that an agent can request but never approve:

```sh
../verify/verify.sh http://127.0.0.1:8080 --token "$(cat local/owner.token)" \
  --agent-token "$(cat local/agent.token)"
```

Stop and delete everything:

```sh
docker compose down -v
```

## Without Docker: mock mode

The dashboard alone runs on fixtures that match the contract:

```sh
cd dashboard && npm ci && VITE_MOCK=1 npm run dev
```
