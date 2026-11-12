<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind apps

Market apps, one directory per app (`apps/<id>/`), each with an `onemind.app.yaml` manifest as defined in [`sdk/contracts/poc-v0.md`](../sdk/contracts/poc-v0.md) §4. Check them with `sdk/tools/validate-apps`.

| App | Version | Licence (class) | Web port | Notes |
|---|---|---|---|---|
| [ntfy](ntfy/) | 2.37.2 | Apache-2.0 OR GPL-2.0 (L1) | 8080 | Push notifications for alerts and approvals; private (deny-all) by default |
| [Home Assistant](home-assistant/) | 2026.11.1 | Apache-2.0 (L1) | 8123 | Home automation engine (Core container, not HAOS); no hostNetwork or USB/Bluetooth in v0 |
| [Uptime Kuma](uptime-kuma/) | 2.5.10 | MIT (L1) | 3001 | Uptime monitor and status pages; upstream rootless image (UID 1000), SQLite on a PVC |
