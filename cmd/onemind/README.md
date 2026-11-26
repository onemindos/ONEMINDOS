<!-- SPDX-License-Identifier: Apache-2.0 -->
# onemind: the OneMind command-line tool

**Serves:** contract [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md) §2 (heartbeat) and §3 (`GET /v1/nodes`); brief 30 BD-02 (Go CLI). `onemind update …` serves B4.2.

## Why it exists
Two everyday questions, answered from a terminal:
- **"What does this machine look like to OneMind?"** → `onemind node info`. It runs the *same* detection code as `onemindd`, so what you see is exactly what the hub will get. Use it as the first thing on new hardware (Beelink, Pi 5, Jetson, droplet).
- **"Which machines are in my OneMind right now?"** → `onemind nodes`. It asks the hub's gateway, which knows every node that sent a heartbeat and marks each `online`, `stale` or `offline`.

## Commands
```sh
onemind node info                         # collect here, print the heartbeat JSON
onemind node info --agent http://127.0.0.1:7480   # ask a running onemindd instead
onemind node info --root internal/detect/testdata/rpi5 --arch arm64   # what a fake Pi 5 would report

export ONEMIND_TOKEN=…                    # safer than --token: flags land in shell history
onemind nodes --hub http://hub.local:8080           # table
onemind nodes --hub http://hub.local:8080 --json    # raw list from the gateway
onemind version

# OS updates on a OneMind image (brief 30 B4.2; needs root except status)
onemind update status [--json]            # current/available version, state, last result, history
onemind update check                      # fetch the TUF channel and print the decision; never installs
onemind update apply --local [--no-reboot] # BREAK-GLASS: install on this machine now, as root, no approval (not while the health gate is deciding)
# With a box selected (onemind login), `onemind update apply` files an approval instead; see "Settings over the gateway" below
```
See [`internal/update/`](../../internal/update/README.md) for the policy, window and states.

### Talking to a box (docs/leap/dev/CLI.md; built on the Go SDK in `sdk/go`)
```sh
printf %s "$TOKEN" | onemind login --hub http://hub.local:8080 --name home --principal owner --token-stdin
onemind context list | use NAME | show | rename OLD NEW | delete NAME
onemind status                            # box, nodes, waiting approvals, audit chain
onemind nodes [list] [--status online] | nodes info NODE_ID
onemind apps list [--installed] [--category C] | apps info APP_ID
onemind apps install ntfy                 # request, show what will happen, approve (owners), follow to the end
onemind apps install ntfy --no-approve    # only file the request (scripts, agents)
onemind apps remove ntfy                  # asks you to type the app id
onemind actions list --pending | info ID | watch | approve ID | deny ID
onemind audit verify [--file audit.jsonl] # recompute every hash; exit 8 when broken
onemind audit tail -n 50 [-f]
onemind completion bash|zsh|fish|powershell
```
`--json` works everywhere (gateway objects unchanged; errors as one JSON line on stderr), and the exit codes follow CLI.md §4.2 (3 unauthenticated, 4 permission denied, 5 not found, 6 conflict, 7 unreachable, 8 verify failed, 9 still pending, 10 refused, 11 failed). The config (`~/.config/onemind/config.yaml`) holds no secret; tokens are in `credentials.yaml` next to it, mode 0600 (OS keychain: follow-up).

### AI agents: `onemind mcp`
```sh
printf %s "$AGENT_TOKEN" | onemind mcp login --hub http://hub.local:8080 --name laptop --token-stdin
onemind mcp doctor                        # token, MCP revision, tool list
claude mcp add onemind -- onemind mcp --context laptop    # or: onemind mcp config claude-desktop
```
The bridge forwards JSON-RPC lines from stdin to the box's `/mcp`. An agent can read and request; only an owner approves.

Example table:
```
NODE_ID       HOSTNAME  ROLE  BOARD       ARCH   OS         K3S    STATUS  LAST_SEEN
3f9c2a1b7d4e  beelink   hub   x86_64-efi  amd64  debian 13  ready  online  2026-11-11T22:00:00Z
```
Gateway errors are printed with the contract's error code, e.g. `HTTP 401 unauthenticated: …`.

## Settings over the gateway (users, backup, care, update policy)
Each of these calls an existing gateway route with your token, takes `--json` (the gateway's JSON, unchanged) and never approves anything:
- `onemind users list|invite NAME [--role R]|disable ID --yes`: owner only. `invite` prints the one-time sign-up link once. A box with passkeys asks for a passkey sign-in on these writes, which the CLI cannot do, so it says to use the dashboard.
- `onemind backup status|snapshots|run [--app ID]|verify [--mode check]|restore SNAPSHOT --app ID [--path P]`: `run`, `verify` and `restore` file a request that waits for an owner (`onemind actions approve ID`).
- `onemind care checkup`: the box check-up; reads only.
- `onemind update policy show|set`: the app update rules; `set` keeps every value you do not pass.
- `onemind update apply`: files an `os.update.install` request for the hub (or `--node`), which an owner approves; the box's host service then installs with the health gate and rollback. `--local` is the break-glass path that runs the engine on this machine as root with no approval, and it says so each time. With no box selected, apply refuses unless you pass `--local`. If the box reports it has no host service to install with, apply files nothing and tells you to use `--local` at the box.

## More groups over the gateway
The same rules: each command calls an existing gateway route, takes `--json`, and never approves anything. A change either files a request that waits for an owner (it prints the request id and `onemind actions approve ID`) or is a direct call the gateway already limits to the right person.

### Automation, alerts, monitoring
- `onemind automation rules list|show ID|create --file F|enable ID|disable ID|dry-run ID|delete ID --yes`: a rule only files requests; it starts off, and the box turns it on only after a dry run. `show` and `dry-run` print plain text; add `--json` for the whole document.
- `onemind automation runs [--rule ID]|schedules|state|pause|resume`, `automation policies list|revoke ID --yes` (creating a standing approval stays in the dashboard, with its passkey step), `automation windows list|set win_NAME --file F` (window ids look like `win_<lower-case name>`).
- `onemind alerts list|show ID|ack ID|resolve ID|fix ID`: `fix` files the alert's suggested fix as a request a person approves. `onemind monitoring summary`: machines, apps and open alerts at a glance.

### Tokens, secrets, family, browsers
- `onemind tokens list|create NAME [--agent A] [--scopes s,t] [--days N]|rotate ID [--grace S]|revoke ID --yes`: a new token is printed once.
- `onemind secrets show APP|public-key|generate APP NAME/KEY|clear APP NAME/KEY`: never shows or sends a value; `generate` and `clear` file a request. Typing a value stays in the dashboard, where the browser seals it.
- `onemind family profile show|set USER --file F` and `family app show|set APP --file F`: owner only. `show` prints day names, and says plainly when every app or every hour is blocked. A box with passkeys asks for a passkey sign-in on the writes, which the CLI cannot do.
- `onemind browsers open|close|reset-profile APP`: only for a dashboard or phone sign-in. The box refuses the API token that `onemind login` saves, and the CLI says so.

## Build and test
`make -C cmd/onemindd build` builds this tool too (`dist/onemind-linux-{amd64,arm64}`). Tests: `go test ./cmd/onemind/...` (a fake gateway: tables, `--json`, contexts and file modes, the approval flow, exit codes, the bridge); end to end against a live gateway in `core/tests/test_sdk_conformance.py`.

## v0 shortcuts
- Static bearer token (contract v0 shortcut; Kanidm/OIDC later, BD-03).
- Plain HTTP is allowed to the hub; TLS with the per-box CA comes with the gateway's HTTPS.
