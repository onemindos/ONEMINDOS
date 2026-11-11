# Sources: TD-tier-c-robotics (Tier C robotics fleet vendor teardowns)

**Accessed:** 2026-11-11 · **Claims:** `evidence/claims/TD-tier-c-robotics.csv` (C-TD-tier-c-robotics-001 … 073, 48 rows) · **Saved copies:** `evidence/sources/TD-tier-c-robotics/` with `SHA256SUMS`.
**Used in:** `02-competitors/robotics-formant.md`, `robotics-foxglove.md`, `robotics-viam.md`, `robotics-balena.md`, and the Tier C rows of `02-competitors/MATRIX.md`.

Wayback save requests are denied in this environment, so load-bearing pages are saved as text with a SHA-256 hash. Docs that publish Markdown (`.md` / `llms.txt`) were saved as that Markdown; the rest were converted from HTML. Before saving, e-mail addresses, a GPG key fingerprint and key ID, and anything that looked like a token, private IP or tailnet hostname were masked.

## Code (shallow clones in `<lab-dir>/src/`, pinned)

| Repo | Commit | Release / date | Type | Used for |
|---|---|---|---|---|
| github.com/viamrobotics/agent | `6d641fa60f76984720c3fa8a8e9300a1f5e78595` | 2026-11-10 (latest release v1.2.1, 2026-11-02) | PRIMARY (code, AGPL-3.0, read only) | update/rollback logic, OS-upgrade modes, storage health |
| github.com/viamrobotics/rdk | `046082ec9d5180319bf37559ad0df7659fcb91e0` | 2026-11-10 (reused clone; latest release v1.16.0) | PRIMARY (licence) | licence |
| github.com/viamrobotics/micro-rdk | `b03697b75c7dac7d9b1c591734c7fabcb8a80654` | main (GitHub API) | PRIMARY-METADATA | ESP32 target, licence |
| github.com/foxglove/foxglove-sdk | `8dc7525eda8c9b8cbe1b64cc885a14452db832b5` | 2026-11-10 (release sdk/v0.30.3, 2026-10-26) | PRIMARY (code, MIT) | SDK and ROS 2 bridge licence |
| github.com/FormantIO/formant | `64bcdb0dbafe6142ee2425afda5656f7ec8b8656` | 2026-10-29 | PRIMARY (Apache-2.0) | what Formant open-sources |
| github.com/ros2/ros2_documentation | `1c5c20cb9f14cbfec658690c44b70ca3d3ec81e7` | reused clone | PRIMARY | ROS 2 Foxy EOL date |

GitHub API metadata (licence, archived flag, last push), queried 2026-11-11: `foxglove/studio` (archived, no licence), `foxglove/ros-foxglove-bridge` (MIT, ROS 1 bridge), `foxglove/mcap` (MIT), `viamrobotics/viam-python-sdk` (Apache-2.0), `FormantIO/toolkit` (MIT), `balena-io-examples/balena-ros2-foxy-desktop` (archived, last push 2023-06-17).

## Web pages (saved as text)

| File | URL | Type | Claims |
|---|---|---|---|
| formant-agent-overview.txt | https://docs.formant.io/docs/the-formant-agent.md | PRIMARY | 001, 002, 007 |
| formant-sysreq.txt | https://docs.formant.io/docs/system-requirements.md | PRIMARY | 003, 006, 014 |
| formant-agent-debian.txt | https://docs.formant.io/docs/getting-started-install-the-formant-agent.md | PRIMARY | 004 |
| formant-agent-apt.txt | https://docs.formant.io/docs/install-formant-agent-apt.md | PRIMARY | 005 |
| formant-agent-faq.txt | https://docs.formant.io/docs/agent-faq.md | PRIMARY | 005 |
| formant-docker-ros2.txt | https://docs.formant.io/docs/getting-started-install-agent-docker-ros-2.md | PRIMARY | context |
| formant-terminal-sec.txt | https://docs.formant.io/docs/terminal-and-port-forwarding-security.md | PRIMARY | 008 |
| formant-llms.txt | https://docs.formant.io/llms.txt | PRIMARY | 015 |
| formant-channel.txt, formant-fleetmgmt.txt, formant-adapters-faq.txt | docs.formant.io (create-a-channel, fleet-management, does-the-agent-restart-adapters) | PRIMARY | context |
| formant-tos.txt | https://formant.io/terms-of-service | PRIMARY (legal text) | 009 |
| formant-home.txt | https://formant.io/ | PRIMARY (vendor marketing) | 013 |
| formant-f3-SECONDARY.txt | https://www.silicon.co.uk/press-release/formant-f3-brings-generative-ai-and-agentic-reasoning-to-robot-ops (reprint of the BusinessWire release of 2025-06-30) | SECONDARY | 011 |
| formant-21m-SECONDARY.txt | https://www.therobotreport.com/formant-brings-in-21m-to-expand-enterprise-focus/ | SECONDARY | 012 |
| foxglove-fleet.txt, foxglove-foxlet.txt, foxglove-foxlet-faq.txt | https://docs.foxglove.dev/docs/fleet, …/fleet/foxlet, …/fleet/foxlet/faq | PRIMARY | 020 |
| foxglove-foxlet-install.txt | https://docs.foxglove.dev/docs/fleet/foxlet/installation | PRIMARY | 021 |
| foxglove-bridge.txt | https://docs.foxglove.dev/docs/fleet/bridge | PRIMARY | context |
| foxglove-remote-access.txt | https://docs.foxglove.dev/docs/fleet/remote-access | PRIMARY | 022 |
| foxglove-edge-sites.txt | https://docs.foxglove.dev/docs/data/edge-sites | PRIMARY | 023 |
| foxglove-primary-onprem.txt | https://docs.foxglove.dev/docs/data/primary-sites/installation | PRIMARY | 024 |
| foxglove-pricing.txt, foxglove-docs-pricing.txt, foxglove-reduced-pricing.txt | https://foxglove.dev/pricing, https://docs.foxglove.dev/docs/pricing, https://foxglove.dev/blog/reduced-self-service-pricing | PRIMARY | 025 |
| foxglove-twoyears.txt | https://foxglove.dev/blog/foxglove-vs-foxglove-studio-two-years-on | PRIMARY (vendor blog) | 026 |
| foxglove-agents.txt, foxglove-agent-sidebar.txt, foxglove-mcp-server.txt | https://docs.foxglove.dev/docs/agents, …/agents/agent-sidebar, …/agents/mcp-server | PRIMARY | 028, 029 |
| foxglove-standalone.txt | https://docs.foxglove.dev/docs/standalone-license | PRIMARY | 030 |
| foxglove-llms.txt | https://docs.foxglove.dev/llms.txt | PRIMARY | index |
| viam-agent.txt | https://docs.viam.com/reference/viam-agent/ | PRIMARY | 043, 044, 046, 050, 057 |
| viam-manage-versions.txt | https://docs.viam.com/fleet/manage-versions/ | PRIMARY | 044, 049 |
| viam-server-ref.txt | https://docs.viam.com/reference/viam-server/ | PRIMARY | 048 |
| viam-mcp.txt | https://docs.viam.com/reference/mcp/ | PRIMARY | 051, 056 |
| viam-agent-guide.txt | https://docs.viam.com/build-apps/use-viam-from-an-agent/ | PRIMARY | 052, 055 |
| viam-ai-assistant.txt | https://docs.viam.com/hardware/ai-assistant/ | PRIMARY | 053 |
| viam-first-machine.txt | https://docs.viam.com/set-up-a-machine/first-machine/ | PRIMARY | 056 |
| viam-pricing.txt | https://www.viam.com/pricing | PRIMARY | 054 |
| viam-llms.txt | https://docs.viam.com/llms.txt | PRIMARY | index |
| balena-industries-robotics.txt | https://balena.io/industries/robotics | PRIMARY (vendor marketing) | 070 |
| balena-forum-robotics.txt | https://forums.balena.io/t/anyone-here-using-balenaos-for-robotics/36362 | SECONDARY (user forum) | 072 |
| ros-discourse-dualcopy.txt | https://discourse.openrobotics.org/t/automatic-deployment-of-ros2-based-system-to-remote-devices-dual-copy-or-containers/33884 | SECONDARY (practitioner forum) | 073 |

## Reused claims (not re-verified here)

Funding: [C-W16-024] (Foxglove Series B), [C-W16-025] (Viam Series B). Formats: [C-W7-059] (MCAP MIT), [C-W11-059] (Lichtblick MPL-2.0), [C-W19-036] (Viam module `meta.json`), [C-W19-037] (Foxglove extensions), [C-W7-043] (viam-agent on existing Linux). balenaOS internals: `C-TD-balenaos-*` from the Tier B teardown, and [C-REF-W19-longevity-011] (Pi overlay regression).

## Not obtained

- Formant pricing (no public page; `formant.io/pricing` returns 404) and the Formant agent source (proprietary).
- balena blog posts on the ROS "robot block": linked from the robotics page but not opened, so not cited.
- Search results claiming a "viam-community-mcp" or Rust "viam-mcp-sdk" are third-party and were not used.
