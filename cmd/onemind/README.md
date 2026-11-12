# onemind: the OneMind command-line tool (v0)

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

Example table:
```
NODE_ID       HOSTNAME  ROLE  BOARD       ARCH   OS         K3S    STATUS  LAST_SEEN
3f9c2a1b7d4e  beelink   hub   x86_64-efi  amd64  debian 13  ready  online  2026-11-11T22:00:00Z
```
Gateway errors are printed with the contract's error code, e.g. `HTTP 401 unauthenticated: …`.

## Build and test
`make -C cmd/onemindd build` builds this tool too (`dist/onemind-linux-{amd64,arm64}`). Tests: `go test ./cmd/onemind/` (a fake gateway checks the table, the JSON mode, the env token and the 401 path).

## v0 shortcuts
- Static bearer token (contract v0 shortcut; Kanidm/OIDC later, BD-03).
- Plain HTTP is allowed to the hub; TLS with the per-box CA comes with the gateway's HTTPS.
