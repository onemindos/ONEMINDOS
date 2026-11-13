---
title: Contract API
description: The gateway's REST API, the node heartbeat, the MCP endpoint and the error codes.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

The binding definition is [`sdk/contracts/poc-v0.md`](https://github.com/onemindos/ONEMINDOS/blob/main/sdk/contracts/poc-v0.md). This page summarises it; when they differ, the contract wins. The gateway also publishes its live OpenAPI document at `/openapi.json`.

## Ports and names

| Thing | Value |
|---|---|
| Hub gateway (REST and dashboard) | `:8080` |
| Node agent `onemindd` local API | `:7480` |
| NATS on the hub | `:4222` |
| Heartbeat subject | `onemind.node.<node_id>.status`, every 10 s |
| Audit subject | `onemind.audit` |

## Authentication

Send `Authorization: Bearer <token>`. Each token maps to a principal `{id, kind: person|agent, role: owner|adult|guest|agent}`. A missing or unknown token returns `401`. Only `GET /healthz` is open.

## REST endpoints <span class="om-tag om-tag--ok">works today</span>

| Method and path | Who | Returns |
|---|---|---|
| `GET /healthz` | anyone | `{"ok": true}` |
| `GET /v1/instance` | any principal | `{name, version, hub_node_id}` |
| `GET /v1/nodes` | any principal | heartbeats, each with `status` (`online`, `stale`, `offline`) and `last_seen` |
| `GET /v1/nodes/{node_id}` | any principal | one node, or 404 |
| `GET /v1/apps` | any principal | the catalog, with `installed` and `status` per app |
| `POST /v1/actions` | owner or agent | 201 with the action in `awaiting_approval`; the same idempotency key returns the same action (200) |
| `GET /v1/actions`, `GET /v1/actions/{id}` | any principal | action(s) |
| `POST /v1/actions/{id}/approve` | **owner only** | runs the action; an agent gets `403 permission_denied` |
| `POST /v1/actions/{id}/deny` | owner only | action → `cancelled` |

Action body:

```json
{ "type": "app.install", "params": { "app_id": "ntfy" },
  "idempotency_key": "…", "expires_at": "RFC3339" }
```

Action types in v0: `app.install`, `app.remove`.

**States:** `requested → awaiting_approval → accepted → dispatched → succeeded | failed | outcome_unknown | expired | cancelled`.

## Errors

Every error has the shape `{"error": "<code>", "message": "…"}`:

| Code | When |
|---|---|
| `unauthenticated` | no token or unknown token (401) |
| `permission_denied` | the principal's role may not do this, e.g. an agent approving (403) |
| `not_found` | no such node, app or action |
| `expired` | approving after `expires_at` (409) |
| `stale_precondition` | installing an app without a passing scan newer than 7 days (409) |
| `conflict` | the action is not in a state that allows this |
| `outcome_unknown` | the executor could not confirm the result |

## Node heartbeat <span class="om-tag om-tag--ok">works today</span>

Published by `onemindd` and served at `GET :7480/api/v1/node`. Schema `onemind.node.status/v1`:

```json
{
  "schema": "onemind.node.status/v1",
  "node_id": "3f9c2a1b7d4e", "hostname": "beelink", "role": "hub",
  "board": "x86_64-efi", "arch": "amd64",
  "os": {"id": "debian", "version_id": "13", "pretty": "Debian GNU/Linux 13 (trixie)"},
  "kernel": "6.12.0-amd64", "cpu_model": "…", "cpus": 4,
  "mem_total_mb": 7800, "mem_available_mb": 5100,
  "disk_total_gb": 238.0, "disk_free_gb": 190.2,
  "tpm2": false, "secure_boot": "disabled",
  "k3s": {"present": true, "role": "server", "ready": true},
  "rauc": {"present": false, "booted_slot": null, "slots": []},
  "gpu": {"nvidia": false, "model": null},
  "uptime_s": 1234, "agent_version": "0.1.0",
  "observed_at": "2026-11-11T22:00:00Z"
}
```

`board` is one of `x86_64-efi`, `arm64-efi`, `rpi5`, `jetson-orin`, `vm`, `vm-do`, `unknown`.

## Catalog fields and scan record <span class="om-tag om-tag--ok">works today</span>

Each `GET /v1/apps` entry gains `links` (docs, GitHub, website, support), `tier` and `scan: {scanned_at, result} | null`. The CI gate writes `apps/<id>/scan.json`:

```json
{"scanned_at": "RFC3339", "result": "pass|fail",
 "images": [{"ref": "repo:tag@sha256:…", "archs": ["amd64", "arm64"],
             "trivy": {"version": "0.76.2", "critical_fixable": 0, "critical": 0, "high": 0},
             "clamav": {"signatures": "daily-NNNNN", "infected": 0},
             "secrets": 0, "cosign": "verified|unsigned|failed"}],
 "licence": {"spdx": "MIT", "class": "L1|L2|blocked"},
 "smoke": "pass|fail|skipped"}
```

## MCP endpoint for agents <span class="om-tag om-tag--ok">works today</span>

`POST /mcp`, Streamable HTTP (MCP 2025-06-18), bearer token, agent principals only (anything else gets `403 permission_denied`).

| Tool | Equivalent |
|---|---|
| `list_nodes` | `GET /v1/nodes` |
| `list_apps` | `GET /v1/apps` |
| `request_action` | `{type, app_id, reason?}` → `POST /v1/actions` with a generated idempotency key and a 24 h expiry |

There is no approve or deny tool.
