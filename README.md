# ONEMINDOS

> 🤖 **Research agents: start with [RESEARCH-MISSION.md](RESEARCH-MISSION.md).** Output goes in [research-output/](research-output/). Humans: the copy-paste kickoff prompt is in [KICKOFF-PROMPT.md](KICKOFF-PROMPT.md).

The operating system for sovereignty: a local-first home/edge cloud OS where every device is a node, every app is plug-and-play, and everything is readable by AI.

This repo holds OneMind OS research, requirements and architecture, and the code that implements them: `core/` (gateway), `cmd/` and `internal/` (Go agent and CLI), `os/` (image), `apps/`, `dashboard/`, `ui/`, `mobile/`, `site/`, `deploy/` and `sdk/`. Build status: [docs/leap/STATUS.md](docs/leap/STATUS.md); history: [CHANGELOG.md](CHANGELOG.md). AI agents: read [AGENTS.md](AGENTS.md) first.

## Layout

| Path | What |
|---|---|
| [RESEARCH-MISSION.md](RESEARCH-MISSION.md) | **The master research brief** for the ultracode research run |
| [RESEARCH-MISSION-02-ONE-MIND-FABRIC.md](RESEARCH-MISSION-02-ONE-MIND-FABRIC.md) | **Mission 02:** how every machine (cloud, servers, PCs, Pi, robots, drones, vehicles, sensors) joins one OneMind, with phones as clients; output in `research-output/fabric/` |
| [context/](context/) | Context pack: conversation record, proven cluster, prior planning, findings index, founder/ecosystem, **335-question research bank** |
| [research-output/](research-output/) | Where the research agent writes its deliverables (reviewed via PR) |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | Founder requirements with IDs. The source of truth for *what* we build. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture v0.1. Partly superseded: **D-007 (Debian 13 base, RAUC A/B) wins on base OS, image and updates; ADR-001 is still PROPOSED and names Rugix, so where they differ D-007 and the code in `os/` rule** |
| [docs/ADR-001-foundation.md](docs/ADR-001-foundation.md) | **Foundation decision** (proposed): base OS, image, updates, k3s, backups, security, all based on what competitors actually do |
| [docs/DASHBOARD.md](docs/DASHBOARD.md) | How the dashboard works for household users and operators |
| [docs/learning/](docs/learning/) | Zeus's learning track (lessons) |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Founder decisions D-001…D-007 (license, tiers, apps, hardware, iOS push, partner programs) |
| [docs/HARDWARE.md](docs/HARDWARE.md) | Hardware on hand, phased buy list, competitor box specs, OneMind box family |
| [docs/APPS.md](docs/APPS.md) | App suite scaffold: system apps + domain modules, build order |
| [docs/applications/](docs/applications/) | NVIDIA Inception + Anthropic MHS application drafts |
| [research/competitors/](research/competitors/) | Umbrel, Olares, the wider landscape, and the repos the founder flagged |
| [research/platform/](research/platform/) | Base OS and orchestration, robotics/IoT/XR/NVIDIA, AI-native protocols and UX, website patterns |

## Rules

- **No guessing.** Every fact cites a source; unverified items are labeled.
- Every design decision traces to a requirement ID.
- Earlier planning docs (Nov 3–4, 2026) are kept offline by the founder; their authoritative summary is [context/02-prior-planning.md](context/02-prior-planning.md) (the Blueprint is canonical for Core contracts).
