<!-- SPDX-License-Identifier: Apache-2.0 -->
# deploy/: run OneMind without the OneMind image

**Serves:** contract [`sdk/contracts/poc-v0.md`](../sdk/contracts/poc-v0.md) §6 (deploy), §10.1 last
bullet (security updates on developer installs) and the deploy side of §7/§11.2 (agent apps);
brief 30 **D-B2.4** (developer install P6) and **REC-DEC-30** (P6 is labelled unsupported).

| Path | What it is |
|---|---|
| [`install.sh`](install.sh) | P6 developer install on a stock OS: `--role hub` or `--role node` |
| [`bundle.sh`](bundle.sh) | Builds an offline bundle on your Mac for `install.sh --bundle` |
| [`pins.env`](pins.env) | Every download `install.sh` makes: version + sha256 |
| [`systemd/`](systemd/) | Units for `onemindd`, the hub NATS and the gateway |
| [`compose/`](compose/) | The hub on a Mac with Docker (noop executor, one node and two simulated machines) |
| [`verify/verify.sh`](verify/verify.sh) | Scripted PASS/FAIL of the contract against any hub ([tests](verify/tests/)) |
| [`verify/node-check.sh`](verify/node-check.sh), [`verify/natscheck.py`](verify/natscheck.py) | Run on a machine: is this hub or node healthy (services, k3s, NATS auth, own heartbeat) |
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
sudo deploy/install.sh --role hub [--box-name box1]          # prints the owner token ONCE
ONEMIND_TOKEN=<owner token> onemind fabric ticket            # on the hub: a one-time join code (or Add a device)
sudo deploy/install.sh --role node --join 'onemind-join:v1?…'   # on the new machine; the owner approves it
ONEMIND_TOKEN=<owner token> deploy/verify/verify.sh http://<hub>:8080
sudo deploy/install.sh --uninstall [--purge]
```
Targets (§6): Debian 13, Raspberry Pi OS trixie, Jetson Linux (L4T) Ubuntu, a DigitalOcean Debian 13
droplet; amd64 or arm64. Anything else stops unless `--force-os`. Re-running is safe (each step
checks what is there; it restarts a service only when its binary or config changed).
Options: `--gateway-bind ADDR`, `--onemindd-bin FILE` (skip Go, use `make -C cmd/onemindd build`
output), `--dashboard-dist DIR` (skip Node), `--hub URL` on the hub (the address it advertises).

### Dry run and targets (ported from PR #27)
`--dry-run` prints every step the install would take (each download with its URL and sha256, each
file with its content, each service it would enable) and changes nothing; it needs no root. With
`--target` it plans for another machine, so you can read the plan on a Mac before touching the box:
```sh
deploy/install.sh --role hub  --dry-run --target rpi5
deploy/install.sh --role node --dry-run --target jetson --join 'onemind-join:v1?…'
```
| `--target` | Machine | What changes in the plan |
|---|---|---|
| `debian13` | Beelink or any Debian 13 PC or VM (amd64) | nothing special |
| `rpi5` | Raspberry Pi 5, Raspberry Pi OS trixie (arm64) | memory cgroup step, below |
| `jetson` | Jetson Linux (L4T) Ubuntu (arm64) | note: GPU pods need the NVIDIA runtime in k3s's containerd (not done in v0) |
| `do` | DigitalOcean Debian 13 droplet (amd64) | firewall reminder, below |

`--arch amd64|arm64` overrides the target's usual architecture. A real run (no `--dry-run`) refuses
`--target` and detects the machine itself: `/proc/device-tree/model` says Raspberry Pi 5,
`/etc/nv_tegra_release` means Jetson, DMI vendor `DigitalOcean` means a droplet.
- **Pi 5 memory cgroup.** k3s needs the memory cgroup, and the Raspberry Pi kernel turns it off by
  default. If `/sys/fs/cgroup/cgroup.controllers` lacks `memory`, the script copies
  `/boot/firmware/cmdline.txt` to `cmdline.txt.onemind-backup` (once), appends
  `cgroup_memory=1 cgroup_enable=memory` (docs.k3s.io, Raspberry Pi), and stops with **exit code 3**:
  reboot, then run the same command again. This runs before anything else is installed.
- **DigitalOcean firewall reminder.** A droplet has a public address, and v0 serves the gateway on
  plain HTTP and NATS without auth. On `do` the script prints, at the start and the end, that ports
  8080, 4222, 6443, 10250 and 8472/udp must be closed to the internet with a DigitalOcean Cloud
  Firewall (allow them only from your VPC or Tailscale range). It changes no firewall itself.

### Offline bundle (`bundle.sh`, ported from PR #27)
Without a bundle, the box downloads k3s and NATS and **builds** onemindd (Go), the gateway (uv,
Python, PyPI wheels) and the dashboard (Node, npm) itself. That needs the internet, a few minutes
and some RAM, which a Pi does not love. `bundle.sh` does all of it once on your Mac instead:
```sh
deploy/bundle.sh --arch amd64                      # Beelink, droplet (arm64: Pi 5, Jetson)
scp -r out/onemind-bundle-amd64 <user>@<box>:      # or rsync, or a USB stick
sudo ./onemind-bundle-amd64/src/deploy/install.sh --role hub --bundle ./onemind-bundle-amd64   # on the box
```
| In the bundle | What it is |
|---|---|
| `onemindd-linux-<arch>`, `onemind-linux-<arch>` | node agent and CLI, static, built from `cmd/` (local Go, or the pinned Go container) |
| `gateway-runtime-linux-<arch>.tar.gz` | Python 3.12 + the gateway venv: install.sh's own `uv sync --frozen` step, run for `/opt/onemind` in the pinned Debian container |
| `dashboard/` | the built dashboard (`npm ci --ignore-scripts`, in the pinned Node container) |
| `downloads/` | k3s, its pinned `install.sh`, **k3s airgap images** (pause, CoreDNS, ...) and NATS: the same files and sha256 as `pins.env` |
| `src/` | `deploy/`, `apps/`, `sdk/schema/` from your checkout (tracked and new files; gitignored ones such as compose tokens never) |
| `BUNDLE.txt` | arch, full or `--node-only`, git commit, versions |
| `SHA256SUMS` | a checksum for every other file |

`install.sh --bundle DIR` (found by itself when run from `DIR/src/deploy/`) first runs
`sha256sum --strict -c SHA256SUMS` and refuses a bundle with any file that list does not name, the
wrong architecture, or `--node-only` contents on a hub. Pinned files from `downloads/` are checked
again against `pins.env`, as a download would be. With a bundle nothing is downloaded or built on the
box except Debian packages that are missing (apt) and the app images k3s pulls when you install an
app. `--node-only` makes a smaller bundle for nodes (no gateway, dashboard or NATS; no Docker needed
when Go is installed); `--no-airgap` leaves the images out (k3s then pulls them).
- **SHA256SUMS proves the copy is intact, not who built it.** Build your own bundle, and keep it in a
  folder only you and root can write until the install is done. Signed releases come with the update
  pipeline (TUF), not here.
- Building for the other architecture runs the gateway step under emulation: Docker Desktop does that
  out of the box; on Linux it needs QEMU binfmt.

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

### Networking (CORE-NET-11, docs/architecture/NETWORKING.md)

> **In plain words.** The hub runs its own private network (a *mesh*: WireGuard tunnels coordinated by
> Headscale) and joins it first. Everything between machines then runs inside the mesh: k3s and its
> pod traffic (WireGuard again, H-17) and each node's NATS link, which is TLS with the box's own
> certificate authority and logs in with that node's own key. A new machine joins only with a
> one-time code the owner made, and only after the owner approved the card showing the same short
> code as the machine's screen. People open the dashboard at `https://<box>.local` and each app at
> `https://<app>.<box>.local`, behind their OneMind sign-in.

| Piece | How | Where |
|---|---|---|
| Headscale `0.29.7` (hub) | release binary, sha256-pinned in `pins.env`; unit `onemind-headscale` (dynamic user); TLS on `:8444` with a box-CA certificate a root `ExecStartPre` copies into its runtime directory (until `onemind-edge` fronts it on :443); embedded DERP + STUN `:3478/udp`; `derp.urls: []`, update checks and log upload off; policy pushed by the gateway from OneMind roles | `/usr/local/bin/headscale`, `/etc/onemind/headscale/config.yaml`, `/var/lib/onemind-headscale/` |
| Tailscale client `1.104.6` (every machine) | static tarball from pkgs.tailscale.com, sha256-pinned (no third-party apt key); `--no-logs-no-support`; drop-in `SSL_CERT_FILE` = the box CA, so the coordinator is trusted only through it. A machine that already has Tailscale is refused (OneMind would log it out of its network), and `--uninstall` removes the client only if OneMind installed it (`/etc/onemind/mesh-client`) | `/usr/sbin/tailscaled`, `/usr/bin/tailscale`, `/etc/default/tailscaled` |
| Hub mesh enrollment | the hub mints its own key over Headscale's local socket (`tag:onemind-hub`, `tag:onemind-k3s`, 10 min, single use, through a 0600 file) and gives the gateway a Headscale API key (0600, user `onemind`) | `/etc/onemind/headscale.key` |
| k3s over the mesh | `node-ip`/`advertise-address` = the mesh IP, `flannel-backend: wireguard-native` on `tailscale0`, Traefik and ServiceLB off (the gateway owns :443/:80); a drop-in waits for the mesh address (`onemindd mesh wait-ip`). A cluster created before the mesh is refused (rebuild after a backup) | `/etc/rancher/k3s/config.yaml`, `k3s(-agent).service.d/onemind-mesh.conf` |
| Hub NATS | clients `127.0.0.1:4222` only; leaf listener on `<mesh IP>:7422`, TLS `verify: true` with the box CA; one account per node in an include file the gateway writes; a systemd path unit reloads NATS when it changes; pings tuned so a dead link shows within about a minute | `/etc/onemind/nats.conf`, `/var/lib/onemind/nats/accounts.conf`, `onemind-nats-accounts.path` |
| Node NATS leaf | `onemind-nats-leaf` (user `onemind-nats`), config written by `onemind fabric join` | `/etc/onemind/nats/` |
| HTTPS gateway | box CA created by `python -m onemind_core.ca` as user `onemind`; HTTPS `:443` and `:8443`, `:80` redirects, `:8080` plain HTTP on loopback only (H-05), for local tools and the health gate; `CAP_NET_BIND_SERVICE` only | `/var/lib/onemind/tls/` |
| LAN names | avahi; the gateway publishes `onemind.local`, `<app>.<box>.local` and `<app>.onemind.local` for installed apps with a web UI | `avahi-daemon`, `avahi-utils`, `libnss-mdns` |

The v0 `--token` join (a long-lived k3s agent token printed by the hub, NATS open on the LAN) is gone.

### Tokens
- **Owner token:** 256 random bits, printed once. `/etc/onemind/tokens.yaml` stores only
  `sha256:<hex>` (the gateway supports that form), so the file holds no usable secret. Lost it?
  Remove `tokens.yaml` and run the install again (it prints a new one), or add a new `sha256:` entry by hand.
- **Agent token** (`--with-agent-token`, ported from PR #27): the same for principal `dev-agent`
  (`kind: agent`), which may request actions but never approve or deny them (§3, §7). On a re-run it
  is added only if `tokens.yaml` has no agent yet. `verify.sh --agent-token-file` uses it for the
  agent-403 and §11.3 MCP checks.
- **No raw API token on disk.** Before printing new tokens the script searches `/etc/onemind`,
  `/var/lib/onemind`, `/var/cache/onemind`, `/etc/systemd/system` and `/etc/rancher` for them and
  stops if one is found. Copy each token into a password manager; the script keeps no copy.
- **Join token:** the k3s `agent-token` in the full `K10<CA hash>::node:<secret>` form, so the node
  also checks it talks to the right server. The hub prints the join command on every run.

### The gateway's access to Kubernetes (why not the admin kubeconfig)
The gateway has its own ServiceAccount `onemind-system/onemind-gateway` with **no cluster-wide
power over workloads** (hardening H-03, [`k8s/gateway-rbac.yaml`](k8s/gateway-rbac.yaml)):
- cluster-wide it may only manage namespaces, create RoleBindings and `bind` one role,
  `onemind-app-deployer` (the kinds an app may ship, [`sdk/policy/app-objects.yaml`](../sdk/policy/app-objects.yaml));
- at each install the gateway binds that role to itself **inside `app-<id>` only**, so it can read
  and write app objects there and nowhere else (not `kube-system`, not its Secrets);
- a `ValidatingAdmissionPolicy` (built into Kubernetes) refuses any gateway write outside `app-*`,
  any app namespace without `onemind.io/app` and a Pod Security level of `restricted`/`baseline`,
  and any RoleBinding to another ClusterRole. Kubernetes' own escalation check refuses granting a
  permission the gateway does not hold.
Its kubeconfig `/etc/onemind/gateway.kubeconfig` (root:onemind, 0640) holds a **24-hour bound
token**, renewed every 6 hours by `onemind-gateway-token.timer` (`/opt/onemind/bin/onemind-gateway-kubeconfig`).
Upgrading from an earlier install deletes the old `admin` binding and the never-expiring token
Secret. The k3s admin file stays root-only. `kubectl` is k3s's own, called through
`/opt/onemind/bin/kubectl` so it always uses that kubeconfig.

The k3s config also turns on **Secrets encryption** (H-12; the install refuses to continue unless
`k3s secrets-encrypt status` says Enabled, and rewrites existing Secrets once) and **Pod Security
defaults** for every namespace ([`k8s/psa.yaml`](k8s/psa.yaml): enforce `baseline`, warn and audit
`restricted`; only `kube-system` and `onemind-system` are exempt). App namespaces get `restricted`
from the gateway. Both are cluster-start settings: an upgrade restarts k3s once.

### Agent apps (contract §7, §11.2), the deploy side
- `gateway.env` sets `ONEMIND_PUBLIC_URL` (the `--hub` URL, else `https://<primary IP>:8443`): the
  URL app pods use to reach the gateway, which the wave-2 gateway writes into each agent app's
  Secret as `ONEMIND_GATEWAY_URL`. The wave-1 gateway ignores the variable.
- The per-app RoleBinding above lets the gateway create and delete Secrets in `app-<id>`, which §11.2 needs.
- The hub install prints the command with which the **owner** creates `hermes-agent-credentials`
  (model-provider keys never come from the repo).
- `ONEMIND_ALLOW_UNSCANNED` is **not** set on the hub (the contract refuses it with the kubernetes
  executor). With the wave-2 gateway, installs of apps without a fresh passing `scan.json` return
  `409 stale_precondition`; `verify.sh` counts that as the §10.3 check passing.

### Choices to flag for the contract owner
- *(Retired by H-05, CORE-NET-11.)* **Gateway bound to `0.0.0.0:8080`.** Plain HTTP now listens on loopback only
  (`--gateway-bind` defaults to `127.0.0.1`, and the gateway narrows anything wider while HTTPS is on); the LAN is
  served by HTTPS on `:443` and `:8443` with the box CA. Agent apps in pods reach it on `https://<primary IP>:8443`;
  delivering the box CA to those pods (`ONEMIND_GATEWAY_CA`) is not built yet (hardening H-05, follow-up).
- *(Retired by CORE-NET-11, see Networking above.)* **NATS has no auth or TLS** and listens on `0.0.0.0:4222`, because the contract's v0 shortcut is
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
`ONEMIND_NODE_ID=compose-node-1`), and two **simulated machines** (ported from PR #27), `sim-rpi5`
and `sim-jetson`: [`simnode`](compose/simnode/main.go) runs onemindd's own agent code
(`internal/agent`) but reads the hardware from `internal/detect`'s Raspberry Pi 5 and Jetson fixture
trees, so Nodes shows a `rpi5` and a `jetson-orin` (with its GPU) next to the `vm`, and their
heartbeats are exactly what onemindd sends on those boards (PR #27's simulator wrote them by hand).
They report hardware that is not there: development only. All images are pinned by digest; every port is bound to
`127.0.0.1`. `ONEMIND_ALLOW_UNSCANNED=1` is set and marked **dev only**: the seed apps have no
`scan.json` yet, and the contract allows the flag only with the noop executor.

## verify/node-check.sh and natscheck.py (ported from PR #27)
Run **on** a hub or node after the install: `sudo deploy/verify/node-check.sh`. One line per check,
a table at the end, exit 0 when nothing failed:
- `onemindd` active; its local API `:7480/api/v1/node` answers with the §2 schema and the configured role.
- k3s at the `pins.env` version. Hub: `k3s` active, `/readyz`, nodes Ready, `onemind-nats` and
  `onemind-gateway` active, gateway `/healthz`. Node: `k3s-agent` active, and **no** admin
  kubeconfig or server data on the node (D-B6.2).
- NATS, with the auth main has today. `natscheck.py` reads `ONEMIND_NATS_URL` from
  `/etc/onemind/onemindd.env` (`--env-file`), so a URL with a token or `user:pass` never reaches a
  command line, and it never prints credentials. A hub NATS that requires none is a **WARN**
  ("v0 shortcut until per-node users, H-06"), not a pass. Then the machine's own heartbeat must
  arrive on `onemind.node.<id>.status` within 25 s.
- Leaf link (H-06): on a node that has the `onemind-nats-leaf` unit, the loopback leaf's `/leafz`
  must show a connection to the hub (`natscheck.py leafz`, the same signal as `internal/leaf`);
  without that unit it is SKIP (v0 nodes publish straight to the hub).
- Clock synchronised (WARN if not: stale and offline come from timestamps).

`natscheck.py` (standard library only) also works by hand: `ping` and `watch` take `nats://`,
`nats://TOKEN@`, `nats://USER:PASS@` or `tls://` with `--ca <box CA>`; against a server that wants
nkey users it says so (it signs no nonces) and points at `leafz`.
```sh
python3 -I deploy/verify/natscheck.py watch nats://hub.local:4222 --count 3   # heartbeats of 3 machines
```

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

## Tests of the deploy kit (ported from PR #27; CI: `ci-deploy.yml`)
| Test | What it proves | Run |
|---|---|---|
| [`verify/tests/test_verify.py`](verify/tests/test_verify.py) | `verify.sh` passes a correct hub with **nothing skipped** (`--strict`) and FAILs the right line for each of 15 broken hubs (no auth, agent may approve, no expiry, deny not cancelled, no idempotency, changed params, failed install, no online node, leaked IP, bad board, person on `/mcp`, an approve tool, broken audit chain, a heartbeat for another node, no dashboard). A hub that answers with node ids made of Python code runs nothing (the #26 eval bug). Tokens never reach curl's command line. `natscheck.py` against no-auth, token and nkey servers, `leafz`, and (with Docker) a real nats-server 2.15.2 with a token and TLS from a CA made at test time | `python3 -I deploy/verify/tests/test_verify.py -v` (about 80 s) |
| [`verify/tests/mock_gateway.py`](verify/tests/mock_gateway.py) | Not a test itself: an imitation hub (HTTP API with `/mcp`, plus a tiny NATS with heartbeats and a hash-chained `onemind.audit`), `--bug` breaks one rule | used by the test above |
| [`verify/tests/e2e-systemd/run.sh`](verify/tests/e2e-systemd/run.sh) | The real thing on two "stock Debian 13 machines" (containers with systemd as PID 1): `bundle.sh`, hub and node installed **from the bundle only**, tokens printed once and absent from disk, idempotent re-run, 2 Ready nodes, node-check on both, `verify.sh` with the kubernetes executor, an app Available in k3s, a dry run that changes no file, `--uninstall --purge` | `deploy/verify/tests/e2e-systemd/run.sh` (privileged Docker; about 4 min on arm64; `KEEP=1`, `E2E_APP`, `E2E_BUNDLE`) |

The e2e containers need one thing a real machine does not: under cgroup v2 a long `docker exec`
sits in the container's root cgroup and blocks k3s from getting its controllers, so
[`entrypoint.sh`](verify/tests/e2e-systemd/entrypoint.sh) moves PID 1 into a leaf cgroup first
(as kind and k3d do), and `/lib/modules` is mounted for k3s's kernel modules.

Record (2026-11-12, throwaway Lima VM, Docker 29.9.3, arm64): `test_verify.py` 17 passed, 0 skipped
(real NATS included); `e2e-systemd/run.sh` **20/20, E2E PASSED** in 3 min 49 s, with `verify.sh`
45 passed, 0 failed, 0 skipped on the bundle-installed hub. amd64 runs in CI.

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
without auth/TLS/leaf nodes; plain HTTP; no OS rollback (P6 by definition); no host firewall
between pods and the node's ports yet (the per-app NetworkPolicy blocks private ranges; H-04's
nftables part is open).
