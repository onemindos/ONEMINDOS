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

## v0 shortcuts / gaps
- The binary path is `/usr/local/bin` (developer install, contract §6). The OneMind image will ship it in `/usr/bin` and the image's own unit.
- Not yet run under this unit on real k3s/RAUC/NVIDIA hosts; if a sandbox option blocks one of those tools there, relax that one option and record why here.
