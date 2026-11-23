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
onemind update apply [--no-reboot]        # owner installs now (not while the health gate is deciding)
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

Use a scoped agent token issued by the box. Set `HUB_URL` to the gateway URL and run the following from the repository root with `onemind` and your MCP client on PATH. Paste the token at the hidden login prompt.

```sh
onemind mcp login --hub "$HUB_URL" --name workstation-agent
scripts/register-onemind-mcp.sh claude workstation-agent
scripts/register-onemind-mcp.sh codex workstation-agent
```

Run the registration for each client you use. The script checks the saved credential with `onemind mcp doctor` and registers the stdio bridge in Claude Code's user configuration or Codex's user configuration (`~/.codex/config.toml` by default). The client records the command and context name. The token stays in the OneMind CLI's credential file (mode 0600). Launch the client without an exported `ONEMIND_TOKEN` or `ONEMIND_HUB` so the bridge uses the saved credential and its gateway. To generate a Claude Desktop entry, run `onemind mcp config claude-desktop --context workstation-agent`.

The bridge forwards JSON-RPC lines from stdin to the box's `/mcp`. An agent can read and request changes. A person approves requests through OneMind.

Under [D-018](../../docs/DECISIONS.md#d-018--the-d-016-desktop-is-the-only-front-door-backstage-is-retired), the cloud-only views from Backstage are deliberately dropped from core, including the Ops globe, OpenCost, the DigitalOcean page, GitHub cards, Tech Radar, Tech Insights, the Visualizer and DevTools. The replacement MCP server exposes the box's own gateway tools.

Example table:
```
NODE_ID       HOSTNAME  ROLE  BOARD       ARCH   OS         K3S    STATUS  LAST_SEEN
3f9c2a1b7d4e  beelink   hub   x86_64-efi  amd64  debian 13  ready  online  2026-11-11T22:00:00Z
```
Gateway errors are printed with the contract's error code, e.g. `HTTP 401 unauthenticated: …`.

## Build and test
`make -C cmd/onemindd build` builds this tool too (`dist/onemind-linux-{amd64,arm64}`). Tests: `go test ./cmd/onemind/...` (a fake gateway: tables, `--json`, contexts and file modes, the approval flow, exit codes, the bridge); end to end against a live gateway in `core/tests/test_sdk_conformance.py`.

## v0 shortcuts
- Static bearer token (contract v0 shortcut; Kanidm/OIDC later, BD-03).
- Plain HTTP is allowed to the hub; TLS with the per-box CA comes with the gateway's HTTPS.
