# deploy/systemd: running onemindd as a service

**Serves:** contract §6 (`deploy/install.sh` installs `onemindd` as a systemd service), brief 30 B6 hardening spirit (least privilege for host services).

## Other units here
`onemind-nats.service` (hub NATS) and `onemind-gateway.service` (gateway + dashboard) are installed by
[`deploy/install.sh`](../install.sh); see [`deploy/README.md`](../README.md).

## Install by hand (`deploy/install.sh` does this for you)
```sh
sudo install -m0755 onemindd-linux-$(dpkg --print-architecture) /usr/local/bin/onemindd
sudo install -D -m0644 onemindd.service /etc/systemd/system/onemindd.service
sudo install -d -m0755 /etc/onemind
printf 'ONEMIND_NATS_URL=nats://HUB:4222\nONEMIND_NODE_ROLE=node\n' | sudo tee /etc/onemind/onemindd.env
sudo systemctl daemon-reload && sudo systemctl enable --now onemindd
curl -s localhost:7480/healthz
```
(`dpkg --print-architecture` prints `amd64` or `arm64`, which matches the binary names.)

## Why root, and why that is still locked down
systemd can run a service as a throw-away user (`DynamicUser=yes`), which is the safest default. We **cannot** use it here, because the agent must read things only root can read:
- the k3s admin kubeconfig `/etc/rancher/k3s/k3s.yaml` (mode 0600) for the `/readyz` check,
- the RAUC status over D-Bus,
- `/dev/nvidia*` (through `nvidia-smi`).

TPM and Secure Boot do **not** need root: both are read from `/sys` (world-readable).

So the unit runs as root but takes away almost everything root normally has:
- `CapabilityBoundingSet=` (empty): no Linux capabilities at all. Root without capabilities can read files it owns, but cannot override permissions, load modules, change the network, mount, etc.
- `NoNewPrivileges=yes`: nothing it starts can gain privileges (no setuid tricks).
- `ProtectSystem=strict`: the whole filesystem is read-only to it, except its own `StateDirectory` (`/var/lib/onemindd`).
- `ProtectKernel*`, `ProtectControlGroups`, `ProtectClock`, `ProtectHostname`: cannot change kernel settings, cgroups, time or hostname.
- `SystemCallFilter=@system-service ~@privileged`, `RestrictNamespaces`, `MemoryDenyWriteExecute`, `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`.
- `PrivateDevices` is **off** on purpose (nvidia-smi needs `/dev/nvidia*`).

## What was checked
In a Debian 13 (trixie) container running systemd as PID 1 (Docker Desktop on a Mac, arm64), with the static `onemindd-linux-arm64` binary:
- `systemd-analyze verify onemindd.service` → no errors.
- `systemctl start onemindd` → `active`; `/healthz` returned `ok: true` and a `boot_id`; `/api/v1/node` returned the heartbeat (board `vm`, detected through `systemd-detect-virt` under the sandbox).
- `systemd-analyze security onemindd` → overall exposure **2.2 OK**.

CI (`.github/workflows/ci-onemindd.yml`) re-runs `systemd-analyze verify` on every PR.

## onemind-update.service (OS updates, OneMind images only)
`onemindd update` checks the TUF channel, takes the restic snapshot, runs `rauc install` and reboots in the maintenance window ([`internal/update/`](../../internal/update/README.md)). It has its own unit so the heartbeat agent above can stay read-only. It gets only what that job needs:
- `ReadWritePaths=/data` (bundles in `/data/rauc`, state in `/data/onemind/update`); the rest of the filesystem stays read-only.
- `CapabilityBoundingSet=CAP_DAC_READ_SEARCH`: restic must read app files under `/data` owned by other users. No other capability.
- D-Bus over `AF_UNIX` to ask RAUC to install and systemd to reboot (both allow root).
- `ConditionPathExists=/etc/onemind/update.conf` and `After=onemind-health-gate.service`, so after a reboot it reports the gate's verdict once the gate has run.

Checked in a Debian 13 Lima VM (systemd 257, arm64): `systemd-analyze verify` clean for both units; `systemd-analyze security onemind-update` → **2.1 OK**; under the unit, a dry run against a loopback TUF repo downloaded to `/data/rauc`, called a fake `rauc` and wrote `status.json`. CI (`ci-onemindd.yml`) does not verify this unit yet.

Do **not** enable it on a developer install (stock Debian, no A/B): there, contract §10.1 uses `unattended-upgrades`.

## onemind-rescue.service (rescue console, CORE-UPDATE-8)
`onemindd rescue` serves a small web page on `https://<box>:7443/` that keeps working when k3s and the gateway are down: booted slot, slot states and versions, k3s unit state, a log download, and **roll back** (`rauc status mark-active other`, then `systemctl reboot`), which runs only on an owner POST with the page's CSRF token and the typed word `rollback`. See [`cmd/onemindd/README.md`](../../cmd/onemindd/README.md#rescue-console).
- Owner token: checked against the owner `sha256:` entry of `/etc/onemind/tokens.yaml` (the gateway's file, which holds only hashes). No owner entry, no access. 5 failed tries from one address lock it out for a minute.
- TLS: the box CA's `https.crt`/`https.key` from `/var/lib/onemind/tls` (re-read on each connection, so renewals apply). Without them it refuses to start unless `-listen` is a loopback address.
- No capabilities, read-only filesystem; D-Bus over `AF_UNIX` for RAUC and the reboot (both allow root).

## v0 shortcuts / gaps
- The binary path is `/usr/local/bin` (developer install, contract §6). The OneMind image will ship it in `/usr/bin` and the image's own unit.
- Not yet run under this unit on real k3s/RAUC/NVIDIA hosts; if a sandbox option blocks one of those tools there, relax that one option and record why here.

## Networking units (CORE-NET-11)

| Unit | Machine | What |
|---|---|---|
| `onemind-headscale.service` | hub | mesh coordinator, embedded DERP/STUN; dynamic user, TLS files copied into its runtime directory by a root `ExecStartPre` |
| `onemind-nats-leaf.service` | node | local NATS leaf linked to the hub over the mesh; user `onemind-nats` |
| `onemind-nats-accounts.path` + `onemind-nats-reload.service` | hub | reload NATS when the gateway rewrites the per-node accounts |

`install.sh` also writes drop-ins: `tailscaled.service.d/onemind.conf` (box CA only, no log upload),
`k3s(-agent).service.d/onemind-mesh.conf` and `onemind-nats.service.d/onemind-mesh.conf` (wait for the
mesh address; NATS gets its TLS files the same way).

## onemind-images.service (image cleanup and disk budget, NMD-08)
`onemindd images` removes only **superseded** container images: an app's older versions that no workload (at any replica count), no current or previous revision and no container (running or exited) uses. It never removes the images of an installed app, stopped or not, so a box with no internet can start every app again (Project NOMAD #858; test `TestOfflineBoxRestartsEveryInstalledAppAfterCleanup` in `internal/imagegc`). It removes nothing when it cannot read the cluster.
- Schedule: once at start, every 24 h, and at once when the image disk passes the box's budget (`ONEMIND_IMAGES_BUDGET_PCT`, default 80, below kubelet's own 85 % collector).
- Warning: the heartbeat's `images` object carries the disk use and `warn_pct` (`ONEMIND_IMAGES_WARN_PCT`, default budget - 10); the gateway opens the `disk.budget_near` alert for the owner there.
- Hub only (`ConditionPathExists=/etc/rancher/k3s/k3s.yaml`): it needs the k3s admin kubeconfig. Root without capabilities, read-only filesystem; containerd deletes the image files over its Unix socket.
