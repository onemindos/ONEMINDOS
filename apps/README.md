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
| [Nextcloud](nextcloud/) | 33.0.10 | AGPL-3.0 (L2) | 80 | Files, calendar and contacts; tier blocked (fixable CRITICAL CVEs in the CI gate) | no scan record; blocked |
| [Immich](immich/) | 3.4.1 | AGPL-3.0 (L2) | 2283 | Photo and video library; tier blocked (fixable CRITICAL CVEs, list in its README) | no scan record; blocked |
| [Syncthing](syncthing/) | 2.1.7 | MPL-2.0 (L1) | 8384 | Continuous file sync; tier blocked (fixable CRITICAL CVEs) | no scan record; blocked |
| [Paperless-ngx](paperless-ngx/) | 3.4.2 | GPL-3.0 (L2) | 8000 | Document archive and search; tier blocked (fixable CRITICAL CVEs) | no scan record; blocked |
| [Gitea](gitea/) | 28.3.0 | MIT (L1) | 3000 | Self-hosted Git service; tier blocked (fixable CRITICAL CVEs) | no scan record; blocked |
| [Grafana](grafana/) | 13.3.1 | AGPL-3.0 (L2) | 3000 | Dashboards for metrics, logs and traces | no scan record yet |
| [Ollama](ollama/) | 0.40.16 | MIT (L1) | 11434 | Run local AI models | no scan record yet |
| [LibreChat](librechat/) | 0.8.8 | MIT (L1) | 3080 | Chat with local and hosted models; tier blocked (fixable CRITICAL CVEs) | no scan record; blocked |
| [SearXNG](searxng/) | 2026.11.11 | AGPL-3.0 (L2) | 8080 | Private metasearch engine | no scan record yet |
| [AdGuard Home](adguard-home/) | 0.107.80 | GPL-3.0 (L2) | 3000 | Network-wide ad and tracker blocking DNS | no scan record yet |

A scan of `fail` means the gateway refuses to install the app until a newer scan passes (contract section 10.3). An app with no `scan.json` is refused the same way ("nothing unscanned runs"), so the market batch 1 apps cannot be installed until CI writes a passing scan; the six marked blocked also carry `tier: blocked`. The result comes from each app's `scan.json`, read on 2026-11-12.
