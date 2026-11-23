---
pr: pending
branch: claude/199-mqtt5-bridge
---
MQTT 5 devices can reach the NATS bus (issue #199, FLD-02): NATS's MQTT listener accepts MQTT 3.1.1 only, so the Mosquitto app gains an optional bridge that forwards device topics to NATS as mqtt/up/... (and, only when the owner turns it on, NATS mqtt/down/... back to devices). It is Mosquitto's own bridge speaking 3.1.1, configured from app settings by a small start script, with the bridge password as a declared app secret that is never committed. A new CI job (ci.yml mqtt-bridge) starts the pinned NATS and Mosquitto images and checks that an MQTT 5 client is refused by NATS directly but round-trips a message through the bridge. The Mosquitto licence-matrix row now uses the SPDX expression from upstream LICENSE.txt (EPL-2.0 OR BSD-3-Clause); the tier changes only when CI rescans the app.
