<!-- SPDX-License-Identifier: Apache-2.0 -->
# deploy/: run OneMind without the OneMind image

**Serves:** contract [`sdk/contracts/poc-v0.md`](../sdk/contracts/poc-v0.md) §6 (deploy), §10.1 last
bullet (security updates on developer installs) and the deploy side of §7/§11.2 (agent apps);
brief 30 **D-B2.4** (developer install P6) and **REC-DEC-30** (P6 is labelled unsupported).

| Path | What it is |
|---|---|
| [`install.sh`](install.sh) | P6 developer install on a stock OS: `--role hub` or `--role node` |
| [`pins.env`](pins.env) | Every download `install.sh` makes: version + sha256 |
| [`systemd/`](systemd/) | Units for `onemindd`, the hub NATS and the gateway |
| [`compose/`](compose/) | The hub on a Mac with Docker (noop executor, one simulated node) |
| [`verify/verify.sh`](verify/verify.sh) | Scripted PASS/FAIL of the contract against any hub |
| [`check-pins.py`](check-pins.py) | CI: `pins.env` and the compose images match `os/versions.lock.yaml` |

## Why a "developer install" at all (plain English)
The real OneMind box runs **our own read-only image** with two copies of the OS (A/B, RAUC). An
update goes to the copy that is not running, and if the box does not come back healthy it boots
the old copy again: that is **rollback**. A developer install puts the same pieces (k3s, NATS,
`onemindd`, gateway, dashboard) on a **normal Debian** that you already have. That is quick for
development, but Debian upgrades its packages in place, so a bad update cannot be undone. Hence the
banner `unsupported developer install, no OS rollback` (REC-DEC-30) that the script prints at the
start and the end.

## install.sh
```sh
git clone https://github.com/onemindos/ONEMINDOS && cd ONEMINDOS
sudo deploy/install.sh --role hub                    # prints the owner token ONCE, and a join command
sudo deploy/install.sh --role node --hub http://<hub>:8080 --token <join token>   # on each other machine
ONEMIND_TOKEN=<owner token> deploy/verify/verify.sh http://<hub>:8080
sudo deploy/install.sh --uninstall [--purge]
```
Targets (§6): Debian 13, Raspberry Pi OS trixie, Jetson Linux (L4T) Ubuntu, a DigitalOcean Debian 13
droplet; amd64 or arm64. Anything else stops unless `--force-os`. Re-running is safe (each step
checks what is there; it restarts a service only when its binary or config changed).
Options: `--gateway-bind ADDR`, `--onemindd-bin FILE` (skip Go, use `make -C cmd/onemindd build`
output), `--dashboard-dist DIR` (skip Node), `--hub URL` on the hub (the address it advertises).

### What it installs, and where
| Piece | How | Where |
|---|---|---|
| apt: `unattended-upgrades`, `needrestart` | Debian's documented switch (`dpkg-reconfigure unattended-upgrades`), then `52onemind-security-only` limits it to **security origins** (`#clear` + `Debian-Security` patterns; on L4T Ubuntu `${distro_codename}-security`). `needrestart` restarts affected services itself (`$nrconf{restart}='a'`) | `/etc/apt/apt.conf.d/`, `/etc/needrestart/conf.d/` |
| k3s `v1.37.2+k3s1` | binary from `os/versions.lock.yaml` (sha256-checked), then upstream `install.sh` **at the tag commit, sha256-pinned**, run with `INSTALL_K3S_SKIP_DOWNLOAD=true` (it only writes the unit, links and uninstall scripts). The hub is a **server** with a separate `agent-token`; nodes join as **agents** with that token, so a node can never join as a server and holds no admin kubeconfig (D-B6.2, checked in the test) | `/usr/local/bin/k3s`, `/etc/rancher/k3s/config.yaml` |
| NATS `v2.15.2` (hub; D-B6.5) | release tarball, sha256-pinned; unit `onemind-nats` as a dynamic user | `/usr/local/bin/nats-server`, `/etc/onemind/nats.conf` |
| `onemindd` + `onemind` CLI | **built from this checkout with Go 1.26.11** (pinned tarball): no release artifact exists yet. Static, `-trimpath`. Unit = `systemd/onemindd.service` | `/usr/local/bin/`, `/etc/onemind/onemindd.env` |
| gateway (hub) | `core/` installed by **uv 0.13.7** (pinned) from `core/uv.lock` (`--frozen`, hash-checked); uv downloads Python 3.12 and checks its hash. Runs as user `onemind`, `ONEMIND_EXECUTOR=kubernetes` | `/opt/onemind/{core,venv,python,apps,sdk}`, `/etc/onemind/gateway.env`, data in `/var/lib/onemind` |
| dashboard (hub) | `npm ci --ignore-scripts` + `vite build` with **Node v24.22.3** (pinned), run as user `onemind` (never root: npm packages are third-party code), served by the gateway via `ONEMIND_DASHBOARD_DIST` | `/opt/onemind/dashboard` |
| toolchains + downloads | only what the role needs | `/opt/onemind/toolchain`, `/var/cache/onemind` |

### Tokens
- **Owner token:** 256 random bits, printed once. `/etc/onemind/tokens.yaml` stores only
  `sha256:<hex>` (the gateway supports that form), so the file holds no usable secret. Lost it?
  `--uninstall` then install again, or add a new `sha256:` entry by hand.
- **Join token:** the k3s `agent-token` in the full `K10<CA hash>::node:<secret>` form, so the node
  also checks it talks to the right server. The hub prints the join command on every run.

### The gateway's access to Kubernetes (why not the admin kubeconfig)
The gateway runs `kubectl apply -k` for approved actions (§3), and with §11.2 it creates a Secret
in the app's namespace. It gets its own ServiceAccount `onemind-system/onemind-gateway`, bound to
the built-in **`admin`** ClusterRole (full control *inside* namespaces) plus create/delete on
namespaces. That is less than `cluster-admin` (no nodes, CRDs, cluster roles or webhooks), but it
applies to **every** namespace, `kube-system` included, and k3s enforces no Pod Security by
default: whoever controls the gateway can read every Secret and start a privileged pod, which is
root on the nodes. Treat a gateway compromise as a cluster compromise (see "v0 shortcuts"). Its
kubeconfig is `/etc/onemind/gateway.kubeconfig` (root:onemind, 0640). The k3s admin file stays
root-only. `kubectl` is k3s's own (same version as the cluster), called through a small wrapper
`/opt/onemind/bin/kubectl` so it always uses that kubeconfig.

### Agent apps (contract §7, §11.2), the deploy side
- `gateway.env` sets `ONEMIND_PUBLIC_URL` (the `--hub` URL, else `http://<primary IP>:8080`): the
  URL app pods use to reach the gateway, which the wave-2 gateway writes into each agent app's
  Secret as `ONEMIND_GATEWAY_URL`. The wave-1 gateway ignores the variable.
- The ServiceAccount above can create and delete Secrets in `app-<id>`, which §11.2 needs.
- The **owner** enters Hermes's model-provider keys (`hermes-agent-credentials`, declared in its
  `spec.secrets`) in the dashboard's install approval; the gateway stores them encrypted and writes
  the Secret ([SECRETS.md](../docs/leap/core/SECRETS.md)). Until the dashboard shows that form, the
  hub install prints the terminal equivalent, `onemind-secrets approve <action id> <secret>/<key>`,
  which reads the key without echo and seals it the same way. Keys never come from the repo, and
  no `kubectl create secret` command is printed any more.
- `ONEMIND_ALLOW_UNSCANNED` is **not** set on the hub (the contract refuses it with the kubernetes
  executor). With the wave-2 gateway, installs of apps without a fresh passing `scan.json` return
  `409 stale_precondition`; `verify.sh` counts that as the §10.3 check passing.

### Choices to flag for the contract owner
- **Gateway bound to `0.0.0.0:8080` by default.** Brief 30's P6 line says "dashboard bound to
  localhost", but contract §1 gives the hub gateway `:8080` and §11.2 needs app pods to reach it.
  `--gateway-bind 127.0.0.1` gives the brief's behaviour (and breaks agent apps and remote browsers).
  Founder call; the default follows the contract.
- **NATS has no auth or TLS** and listens on `0.0.0.0:4222`, because the contract's v0 shortcut is
  "nodes publish straight to the hub's NATS". Anyone on the LAN can publish fake heartbeats. Leaf
  nodes + account permissions (D-B6.5) replace this.
- Plain HTTP on the LAN (no TLS) for the gateway: the bearer token crosses the network in clear.

## compose/ (Mac with Docker)
```sh
cd deploy/compose
./gen-tokens.sh                    # random owner + agent tokens in ./local/ (gitignored, 0600)
docker compose up -d --build
../verify/verify.sh http://127.0.0.1:8080 --token-file local/owner.token --agent-token-file local/agent.token
open http://127.0.0.1:8080         # sign in with the owner token
docker compose down -v
```
Services: `nats` (2.15.2), `dashboard` (builds `dashboard/` into a volume, then exits), `gateway`
(`core/Dockerfile`, **noop executor**, so nothing is really installed), `node-sim` (`onemindd` with
`ONEMIND_NODE_ID=compose-node-1`). All images are pinned by digest; every port is bound to
`127.0.0.1`. `ONEMIND_ALLOW_UNSCANNED=1` is set and marked **dev only**: the seed apps have no
`scan.json` yet, and the contract allows the flag only with the noop executor.

## verify/verify.sh
Needs `bash`, `curl`, `python3` (stdlib only). It talks to the hub only over HTTP and NATS, so it
runs from a laptop or on the hub. Tokens come from `--token-file`/`--agent-token-file` or the
`ONEMIND_TOKEN`/`ONEMIND_AGENT_TOKEN` variables and reach curl through a 0600 header file, so they
never show in the process list (`--token T` still works but is visible in `ps` and shell history).
Values the hub returns (node and action ids) are passed to the checks as data, never spliced into
code, so a hostile hub cannot run commands on the machine running `verify.sh`. One line per contract item:
- §3: `/healthz` open, `/openapi.json`, 401 without/with a wrong token, dashboard at `/` and SPA
  fallback, `/v1/instance`, `/v1/nodes` (status ∈ online/stale/offline, `last_seen`, §2 fields and
  values, no MAC/serial/IP/user/machine-id), `/v1/nodes/{id}` and 404, `/v1/apps` with every §3 field.
- Actions: expiry → `409 expired`; deny → `cancelled`; create (by the agent when `--agent-token` is
  given) → `201 awaiting_approval`; same idempotency key → 200 + same id; exact params; agent
  approve/deny → `403 permission_denied`; owner approve → `succeeded` (or `409 stale_precondition`
  under §10.3); catalog shows it installed; `app.remove` → `succeeded` (skip with `--keep`, or use
  `--no-execute` to deny instead of installing).
- NATS: the server answers; a heartbeat on `onemind.node.<id>.status` with the right schema; the
  `onemind.audit` lines of this run re-hash correctly and link by `prev_hash`; the audit names the
  agent requester and the owner approver. `--audit-file` re-checks the whole chain on the hub.
- §11.3 MCP: a person token gets `403 permission_denied`; with an agent token, `initialize`,
  `tools/list` (has `list_nodes`, `list_apps`, `request_action`; no approve/deny tool) and
  `request_action` → an ordinary action requested by the agent, which the owner then denies.
- Wave 2 (§11.3 `/mcp`, §11.4 `links`/`tier`/`scan`): **SKIP** while the gateway lacks them,
  checked as soon as it has them; `--strict` turns SKIP into FAIL.
Exit code 0 only when nothing failed.

## Test record (2026-11-12, Apple-silicon Mac, Lima 2.3.0, all arm64)
**Hub on Debian 13** (Lima `template:debian-13`, 4 vCPU, 8 GiB, kernel 6.12.115+deb13.1-cloud-arm64),
repo copied in as a tarball, `sudo deploy/install.sh --role hub`:
- First run found two bugs, both fixed in this branch: `/etc/onemind` was 0750, so the gateway
  (user `onemind`) and NATS (dynamic user) could not read their config (every token 401, NATS
  down); and `verify.sh --nats none` killed its own process group in the exit trap.
- Final from-scratch install (after `--uninstall`): **rc 0 in 30 s**; all of `k3s`, `onemind-nats`,
  `onemindd`, `onemind-gateway` active. Re-run: rc 0, nothing rebuilt that had not changed
  (dashboard "up to date", owner token kept).
- `verify.sh http://127.0.0.1:8080 --token … --agent-token … --audit-file /var/lib/onemind/audit.jsonl`
  inside the VM: **37 passed, 0 failed, 2 skipped** (§11.3 MCP and §11.4 fields, wave 2). The
  approved `app.install` of ntfy really ran `kubectl apply -k` through the k3s kubectl as user
  `onemind`; with `--keep`, `deployment/ntfy` became Available and its pod Running; `app.remove`
  then deleted namespace `app-ntfy`.
- `apt-config`/`unattended-upgrade --dry-run`: allowed origins are exactly
  `origin=Debian,codename=trixie-security,label=Debian-Security` and
  `origin=Debian,codename=trixie,label=Debian-Security`.
- `systemd-analyze verify` on the three units: clean. `systemd-analyze security`: gateway 1.6,
  NATS 1.5, onemindd 2.2 (all "OK").
- **Node join:** a second Debian 13 VM (2 vCPU, 4 GiB) on Lima's `user-v2` network (Lima's `vzNAT`
  does not pass VM-to-VM traffic on this Mac: ARP never resolved), ran the printed
  `--role node` command: rc 0, `kubectl get nodes` shows both `Ready`, the node has **no**
  `/etc/rancher/k3s/k3s.yaml` and no `/var/lib/rancher/k3s/server`. `verify.sh` then: **37 passed,
  0 failed, 2 skipped**, `/v1/nodes` lists 2 nodes. This test found a third bug (a re-run did not
  re-join after the hub address changed), fixed here.
- `--uninstall --purge` on the node and `--uninstall` on the hub: no k3s/OneMind units left, ports
  6443/4222/8080/7480 closed, `/var/lib/onemind` kept without `--purge`.

**Compose** (Lima `template:docker`, Docker 29.9.3, rootless): `./gen-tokens.sh && docker compose up -d --build`
then `verify.sh … --token … --agent-token …`: **35 passed, 0 failed, 3 skipped** (the two wave-2
items, and "hub_node_id has no heartbeat", which is expected: compose runs no onemindd for the hub).
`docker compose ps` shows every published port on `127.0.0.1`. The CI job's exact commands
(`up --wait gateway node-sim`, `config -q`) were run the same way.

**Review pass (2026-11-12, same Mac, arm64), after the review fixes:**
- Debian 13 hub (Lima `template:debian-13`): `install.sh --role hub` rc 0, re-run rc 0 (dashboard
  "up to date", owner token kept); the dashboard now builds as user `onemind` with
  `npm ci --ignore-scripts`. `verify.sh --token-file … --audit-file …`: **34 passed, 0 failed,
  3 skipped** (no agent token on that run; kubernetes executor installed and removed ntfy). The
  printed `hermes-agent-credentials` command was run as printed with a dummy key: Secret created.
  `--hub 'http://x;id'` and a `--token` with quotes or spaces are refused.
- Compose (Lima `template:docker`): wave-1 gateway **35 passed, 0 failed, 3 skipped**; with the
  wave-2 gateway (branch `feat/gateway-agent-mcp`) **43 passed, 0 failed, 1 skipped**, including
  every §11.3 agent MCP check and §11.4.
- A fake hub that answers `hub_node_id`/`node_id` = `x' or __import__('os').system('touch …') or '`
  made the previous `verify.sh` run the command; the fixed one reports a FAIL and runs nothing.
- `shellcheck -x` (0.11.0) clean; `check-pins.py` clean; `docker compose config -q` clean.

**Not tested here (needs hardware or other images):** Raspberry Pi OS trixie (the memory-cgroup
`cmdline.txt` step is written from the k3s docs but never ran), Jetson L4T Ubuntu, a DigitalOcean
droplet, and amd64 (every run above is arm64; the amd64 path differs only in the pinned hashes).

## v0 shortcuts (list in the PR)
Static tokens (Kanidm later, BD-03); SQLite gateway database (PostgreSQL target, BD-04); NATS
without auth/TLS/leaf nodes; plain HTTP; no OS rollback (P6 by definition); the gateway's
ServiceAccount can administer every namespace, not only `app-*` (Kubernetes RBAC cannot scope a
binding to a name prefix; a policy engine or per-app RoleBindings created by the gateway fix it).
