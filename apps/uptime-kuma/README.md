<!-- SPDX-License-Identifier: Apache-2.0 -->
# Uptime Kuma

**What it is:** a self-hosted uptime monitor. It checks websites, TCP ports, DNS, ping and many other targets on a schedule, shows their history, publishes status pages and sends alerts through 90+ notification services. In OneMind it feeds the alert centre (research `13-apps-market-plugins.md`, UX-4). Upstream calls it "a fancy self-hosted monitoring tool."

| | |
|---|---|
| Version | 2.5.10 (GitHub release, 2026-11-12, commit `fc96c63bf31e`) |
| Licence | MIT ([LICENSE at tag 2.5.10](https://github.com/louislam/uptime-kuma/blob/2.5.10/LICENSE)). OneMind licence class **L1** (permissive), so it may be preinstalled on sold boxes |
| Source | https://github.com/louislam/uptime-kuma |
| Website | https://uptime.kuma.pet |
| Docs | https://github.com/louislam/uptime-kuma/wiki |
| Support | https://github.com/louislam/uptime-kuma/issues |
| Image | `docker.io/louislam/uptime-kuma:2.5.10-rootless@sha256:0df77d22bb9284368f4a6541197dd413051b13de63615145c24a889f97c7e724` (multi-arch index: linux/amd64, linux/arm64, linux/arm/v7) |
| Icon | `icon.svg` is the project's own logo (`public/icon.svg` at tag 2.5.10), redistributed unchanged under the MIT licence. Copyright (c) 2021 Louis Lam |

## How it is packaged

- **Image:** the upstream **rootless** full image. The default `2.5.10` tag runs as root; the `-rootless` tag is the same release with `USER node` (upstream `docker/dockerfile`). The pod runs as UID/GID 1000, which upstream documents as the owner the data directory needs ([Docker Tags](https://github.com/louislam/uptime-kuma/wiki/Docker-Tags)). The full image (not `-slim`) keeps the embedded MariaDB option and the Chromium "Browser Engine" monitor.
- **Security:** `runAsNonRoot`, `allowPrivilegeEscalation: false`, all Linux capabilities dropped, `RuntimeDefault` seccomp, no service-account token.
- **State:** one PVC `uptime-kuma-data` (2 Gi, the k3s default `local-path` class) on `/app/data`. Upstream warns that the data folder needs POSIX file locks, so not NFS. One replica with the `Recreate` strategy, so two pods never write the database at once.
- **Network:** Service `uptime-kuma`, port 3001 (HTTP and WebSocket). `enableServiceLinks: false` stops Kubernetes injecting `UPTIME_KUMA_PORT=tcp://…`, which the app would otherwise read as its port (upstream issue #2083).
- **Health:** startup, readiness and liveness probes on `GET /api/entry-page`, which returns 200 both in the first-run database setup and in normal running.

## Resources

| | Request | Limit |
|---|---|---|
| CPU | 100m | 1 |
| Memory | 256 Mi | 512 Mi |
| Disk | 2 Gi PVC | |

Upstream publishes no sizing guidance. The 512 Mi limit is the OneMind research budget for this app (`research-output/13-apps-market-plugins.md`). Raise it if you use the Browser Engine (Chromium) monitor or embedded MariaDB, which use more memory.

## First run

From the upstream install guide, https://github.com/louislam/uptime-kuma/wiki/%F0%9F%94%A7-How-to-Install:

1. Open the app's web UI (port 3001) from the OneMind dashboard.
2. Version 2 first shows a **database setup** page. Choose **SQLite** for a single small box. Embedded MariaDB is also offered by the full image; an external MariaDB/MySQL needs its own server.
3. Create the admin account (username and password). There is no default login.
4. Add monitors with **Add New Monitor**, and add notification channels under **Settings → Notifications** (https://github.com/louislam/uptime-kuma/wiki/Notification-Methods). An ntfy channel delivers alerts to the OneMind ntfy app.
5. If you put it behind a reverse proxy, the proxy must pass the WebSocket `Upgrade` and `Connection` headers (https://github.com/louislam/uptime-kuma/wiki/Reverse-Proxy).

## Known limits in this package

- **nscd DNS cache is off.** The image tries `sudo service nscd start` at boot. With privilege escalation blocked this fails, and the app logs "Failed to start nscd" and carries on (`server/uptime-kuma-server.js`). DNS lookups still work, just without the local cache.
- **Ping monitors (UNVERIFIED):** with all capabilities dropped, ping needs the node to allow unprivileged ICMP sockets (`net.ipv4.ping_group_range`). This has not been tested on OneMind's k3s yet. HTTP, TCP port, DNS and keyword monitors do not need it.
- **Docker container monitor** does not apply: the app gets no container-runtime socket.
- **Upgrades from v1:** upstream does not recommend the rootless image for a v1 → v2 upgrade. This package starts on v2.
