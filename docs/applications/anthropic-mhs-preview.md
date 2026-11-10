# Anthropic Model Hardware Standard (MHS): Research Preview Interest (D-006)

**Apply at:** https://www.modelhardwarestandard.com/ (waitlist). The announcement doesn't say which fields are asked for.
**Zeus submits this himself.**

## What MHS is (from Anthropic's announcement)
A shared specification for AI agents to safely operate physical devices. It uses a standardized driver with read and write commands, a discoverable device format, and a reference file generated from natural-language notes on device characteristics and **safety limits**. Agents reach it through MCP, a CLI, or code. The preview targets research labs and advanced manufacturers. Early adopters include Raspberry Pi and Hugging Face (LeRobot). Anthropic plans to open-source it, with no date given.

## Our pitch (draft, for any free-text field)
OneMind OS is a local-first operating system that turns home, farm and field hardware into one AI-operable mesh. Raspberry Pi edge nodes, mini PCs, GPU servers, NVIDIA Jetson robots, drones and IoT sensors all join by QR code and publish their capabilities. Every app and device is already exposed to AI agents through a single permissioned capability gateway (MCP, REST, CLI), with per-user and per-agent grants, human approval for destructive or physical actions, and full audit.

We want to adopt MHS as the **device-control projection** of that gateway, so that any MHS device can join a OneMind node and be safely operated by local or external agents. Planned first targets: **greenhouse and homestead controllers** (pumps, valves, sensors on Raspberry Pi), **TAK/situational-awareness field nodes**, and **Jetson-based robots and drones** (ROS 2 / MAVLink via gateways). We already enforce safety primitives that align with MHS: device-local safe states, command TTLs, no blind replay after reconnect, and signed commands.

**What we'd contribute:** real-world feedback from consumer, homestead and field deployments (a segment beyond labs and factories), Raspberry Pi-based reference integrations, and safety-evaluation data from offline and intermittently connected environments.

## Contact
Zeus Delacruz, Founder, OneMind OS · [[company name]] · [[website]] · [[business email]]

> ⚠️ **Public repo:** don't fill this file in place. Copy it to a local `*.filled.md` (gitignored) before adding contact details.
