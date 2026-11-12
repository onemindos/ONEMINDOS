---
title: CLI
description: The onemind command-line tool.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

`onemind` answers everyday questions from a terminal. It uses the same detection code as `onemindd` and the same API as the dashboard. Source: [`cmd/onemind`](https://github.com/onemindos/ONEMINDOS/tree/main/cmd/onemind).

## Nodes <span class="om-tag om-tag--ok">works today</span>

```sh
onemind node info                                     # collect here, print the heartbeat JSON
onemind node info --agent http://127.0.0.1:7480       # ask a running onemindd instead

export ONEMIND_TOKEN=…                                # safer than --token: flags land in shell history
onemind nodes --hub http://hub.local:8080             # table
onemind nodes --hub http://hub.local:8080 --json      # raw list from the gateway
onemind version
```

```
NODE_ID       HOSTNAME  ROLE  BOARD       ARCH   OS         K3S    STATUS  LAST_SEEN
3f9c2a1b7d4e  beelink   hub   x86_64-efi  amd64  debian 13  ready  online  2026-11-11T22:00:00Z
```

Gateway errors are printed with the contract's error code, for example `HTTP 401 unauthenticated: …`.

## Updates <span class="om-tag om-tag--warn">in review</span>

```sh
onemind update status
onemind update check
onemind update apply
```

See [Updates and rollback](../../concepts/updates-and-rollback/).

## Build

`make -C cmd/onemindd build` builds `onemind` and `onemindd` for linux/amd64 and linux/arm64 into `dist/`.
