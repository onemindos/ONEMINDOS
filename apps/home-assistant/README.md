<!-- SPDX-License-Identifier: Apache-2.0 -->
# Home Assistant

Home Assistant is open source home automation that puts local control and privacy first. It connects lights, sensors, switches and thousands of other devices and services, and runs automations locally. In OneMind it is the engine of the Home & IoT module and the core of the `greenhouse` profile (brief 30 B10).

This package runs **Home Assistant Core** in a container, which upstream calls the "Container" install type. It is not Home Assistant OS and has no Supervisor, so upstream "apps" (formerly add-ons) are not available. OneMind's own Market supplies the companion apps (Mosquitto, Zigbee2MQTT, Node-RED) instead.

| | |
|---|---|
| Version | 2026.11.1 (released 2026-11-09) |
| Licence | Apache-2.0 ([LICENSE.md at the release commit](https://github.com/home-assistant/core/blob/d8a0dc698c8946b44e455d904000db563cfbf1ba/LICENSE.md)). Research licence class **L1** (permissive): it may be preinstalled on a OneMind box ([`research-output/13-apps-market-plugins.md`](../../research-output/13-apps-market-plugins.md), [`license-matrix.csv`](../../research-output/evidence/license-matrix.csv)). |
| Trademark | "Home Assistant" and its logo are trademarks that Apache-2.0 does not license. The app is listed under the upstream name only, and `icon.svg` is a neutral generated icon with the initials, not the upstream logo. |
| Source | https://github.com/home-assistant/core |
| Website | https://www.home-assistant.io |
| Docs | https://www.home-assistant.io/docs/ |
| Support | https://github.com/home-assistant/core/issues |
| Image | `ghcr.io/home-assistant/home-assistant:2026.11.1@sha256:6785d1eca68747a524c156faae1b139ed415c07357386ae6fe17291986e59e82` (multi-arch index with `linux/amd64` and `linux/arm64`, checked with `crane manifest`) |
| Web UI | port 8123 (Service `home-assistant`) |

## Resources

Upstream's minimum for a Home Assistant system is **2 GB of RAM and 2 vCPUs** ([Linux install docs](https://www.home-assistant.io/installation/linux), virtual machine section). The package asks for:

| | Request | Limit |
|---|---|---|
| CPU | 250m | 2 |
| Memory | 1 GiB | 2 GiB |
| Storage | 5 GiB PVC `home-assistant-config` at `/config` | |

`requires.minMemoryMb` is 2048. Memory grows with the number of integrations and with the recorder history. Raise the limit if the pod is killed for running out of memory.

## How it is packaged, and why

- **State:** everything lives in `/config`: `configuration.yaml`, `.storage/` (users, auth, integrations) and the SQLite recorder database `home-assistant_v2.db`. It is one PVC with no `storageClassName`, so k3s uses its default class (`local-path`).
- **One writer:** the Deployment uses the `Recreate` strategy, so the old pod stops before a new one opens the same database.
- **Clean shutdown:** `terminationGracePeriodSeconds: 60`, matching upstream's advice (`stop_grace_period: 60s`) so the database closes cleanly.
- **Health checks:** startup, readiness and liveness probes call `GET /manifest.json`. Home Assistant has no dedicated health endpoint. This path needs no login (`requires_auth = False` in the frontend component), and upstream's own landing page reads it to detect that Core is up. The startup probe allows up to 10 minutes for the first start on slow boards.
- **Time zone:** `TZ` is `Etc/UTC`. Upstream mounts `/etc/localtime` from the host instead; OneMind avoids host paths. The owner sets the real time zone during onboarding, or changes `TZ` in the Deployment.

### Security trade-offs

Upstream's compose file runs the container with `privileged: true`, `network_mode: host` and a read-only mount of the host's `/run/dbus`. This v0 package uses none of them:

| Upstream setting | What it gives | v0 package | What you lose |
|---|---|---|---|
| `network_mode: host` | mDNS/SSDP/UPnP discovery on the home LAN, HomeKit Bridge, DLNA, Wake-on-LAN | normal pod network, port 8123 through the Service | Devices that are found by multicast discovery are not found automatically. Add them by IP address in **Settings > Devices & services**. HomeKit Bridge and similar integrations need the host network. |
| `privileged: true` | access to USB radios, Bluetooth adapters and other devices | not privileged, `allowPrivilegeEscalation: false`, all capabilities dropped, `RuntimeDefault` seccomp | No USB Zigbee or Z-Wave stick and no Bluetooth inside this pod. Run Zigbee2MQTT (wave 2) with the stick and connect it to Home Assistant over MQTT. |
| `/run/dbus` mount | the Bluetooth integration | not mounted | No Bluetooth integration. |

The image starts s6-overlay (`/init`) as root, and upstream documents no non-root mode, so the pod does not set `runAsNonRoot`. Root inside it has no Linux capabilities and cannot gain new ones. A host-network or device variant would be a separate, explicitly approved package.

## First run

From upstream's Container install guide (https://www.home-assistant.io/installation/linux) and onboarding guide (https://www.home-assistant.io/getting-started/onboarding/):

1. Install the app from the Market and approve the action. Wait until the pod is ready. The first start can take a few minutes while Home Assistant creates `/config`.
2. Open the web UI on port 8123 (the dashboard links to it; from a shell: `kubectl -n app-home-assistant port-forward svc/home-assistant 8123:8123`, then http://localhost:8123).
3. Onboarding: create the owner account, or restore from a Home Assistant backup. Then set the home's name, location, time zone and units, and choose whether to share analytics.
4. Add integrations under **Settings > Devices & services**. Without host networking, add devices by IP address rather than waiting for discovery.
5. After you change `configuration.yaml`, restart from **Settings > System** (power icon > **Restart Home Assistant**), as upstream describes.

## Not verified yet

- This package has not yet been started on k3s: there was no container runtime where it was written. That all capabilities can be dropped comes from reading the s6-overlay `preinit` script (as root it only changes ownership of `/run` when `/run` belongs to another user, and in this image it belongs to root). It must be confirmed by the contract §9.4 smoke test.
- The §9.4 gate's image scans (Trivy, ClamAV) and cosign verification have not run on this image.
