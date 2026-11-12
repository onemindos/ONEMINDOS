<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind apps

Market apps, one directory per app (`apps/<id>/`), each with an `onemind.app.yaml` manifest as defined in [`sdk/contracts/poc-v0.md`](../sdk/contracts/poc-v0.md) §4. Check them with `sdk/tools/validate-apps`.

| App | Version | Licence (class) | Web port | Notes | Last scan |
|---|---|---|---|---|---|
| [ntfy](ntfy/) | 2.37.2 | Apache-2.0 OR GPL-2.0 (L1) | 8080 | Push notifications for alerts and approvals; private (deny-all) by default | pass |
| [Home Assistant](home-assistant/) | 2026.11.1 | Apache-2.0 (L1) | 8123 | Home automation engine (Core container, not HAOS); no hostNetwork or USB/Bluetooth in v0 | fail |
| [Uptime Kuma](uptime-kuma/) | 2.5.10 | MIT (L1) | 3001 | Uptime monitor and status pages; upstream rootless image (UID 1000), SQLite on a PVC | fail |
| [Actual Budget](actual-budget/) | 26.11.0 | MIT (L1) | 5006 | Local-first personal finance | pass |
| [Hermes Agent](hermes-agent/) | 0.23.0 | MIT (L1) | 9119 | Self-hosted AI agent; an agent principal that can request actions, never approve | fail |
| [Eclipse Mosquitto](mosquitto/) | 2.1.2 | EPL-2.0 OR BSD-3-Clause (blocked) | none | MQTT broker; licence class not confirmed, tier blocked | fail |
| [Node-RED](node-red/) | 5.0.9 | Apache-2.0 (L1) | 1880 | Low-code event-driven flows | fail |
| [Vaultwarden](vaultwarden/) | 1.37.5 | AGPL-3.0 (L2) | 8080 | Bitwarden-compatible password server | pass |
| [Zigbee2MQTT](zigbee2mqtt/) | 2.14.3 | GPL-3.0 (L2) | 8080 | Bridges Zigbee devices to MQTT | pass |

A scan of `fail` means the gateway refuses to install the app until a newer scan passes (contract section 10.3). The result comes from each app's `scan.json`, read on 2026-11-12.
