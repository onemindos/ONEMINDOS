<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind OS

**The operating system for sovereignty.** OneMind OS is a local-first home and edge cloud: a box you own runs your apps, files, photos, backups and AI, every device you add becomes a node, every app is plug-and-play, and **AI never acts on anything without your approval**.

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

> **Status: pre-alpha.** The pieces below are built and tested in CI, but there is no signed release yet. What a `v0.1.0-alpha` still needs is tracked in [docs/leap/ALPHA-CHECKLIST.md](docs/leap/ALPHA-CHECKLIST.md). Do not run it on data you cannot lose. The update channel in [os/update/channel.json](os/update/channel.json) points at this repo's GitHub Releases; a box can only download updates from it while those releases are publicly readable, so over-the-air updates need a public host (founder decision F-5).

## What it is made of

| Piece | What it does | Code |
|---|---|---|
| **The OS image** | Debian 13, read-only root, two copies of the system (A/B) updated with RAUC. A bad update boots the old copy again (health-gated rollback). | [`os/`](os/), [`test/qemu/`](test/qemu/) |
| **The gateway** | The one door into the box: owner login, approvals, the capability gateway that checks every app and AI request, and a tamper-evident audit log. | [`core/`](core/) (Python, FastAPI) |
| **`onemindd` and `onemind`** | The node daemon on every machine, and the command-line tool. Machines join over NATS and run apps on k3s. | [`cmd/`](cmd/), [`internal/`](internal/) (Go) |
| **Dashboard and clients** | The web dashboard, design system, phone app and desktop app. | [`dashboard/`](dashboard/), [`ui/`](ui/), [`mobile/`](mobile/), [`desktop/`](desktop/) |
| **Market apps** | Apps you install with one click. Each one is scanned and licence-checked in CI. | [`apps/`](apps/) |
| **SDK and contracts** | OpenAPI spec, generated clients, app manifest schema. | [`sdk/`](sdk/) |
| **Install and deploy** | Developer install on a stock Debian, and a Docker hub for a laptop. | [`deploy/`](deploy/) |
| **Website** | Landing page, docs and the apps catalogue (Astro). | [`site/`](site/) |
| **Mac client** | Native Finder location for a OneMind box (Swift spike). | [`desktop-mac/`](desktop-mac/) |

The foundation choices (Debian 13, RAUC A/B, k3s, NATS, restic backups, plugin sockets E1–E10, the capability gateway) are locked founder decisions: see [docs/DECISIONS.md](docs/DECISIONS.md).

## Repo map

| Directory | One line |
|---|---|
| `os/` | OS image: rootfs layers, board files, RAUC, update channel |
| `core/` | Gateway (Python, FastAPI) |
| `cmd/`, `internal/` | `onemindd` node daemon and `onemind` CLI (Go) |
| `sdk/` | OpenAPI spec (committed), generated clients, app manifest schema |
| `dashboard/`, `ui/` | Web dashboard (the desktop front door) and the design system |
| `mobile/`, `desktop/`, `desktop-mac/` | Phone app (Expo), desktop app (Tauri), Mac Finder client (Swift) |
| `apps/` | Market apps, scanned and licence-checked in CI |
| `deploy/` | Developer install script and the Docker compose hub |
| `site/`, `tips/`, `brand/` | Website (Astro), in-product tips, brand assets |
| `test/`, `tests/e2e/` | Unit, acceptance and QEMU suites; Playwright end-to-end |
| `lab-kits/` | Scripts for testing on real hardware |
| `scripts/`, `changes/` | Repo tooling; one change fragment per PR |
| `docs/`, `context/`, `research/`, `research-output/` | Requirements, decisions and plans; research behind them (`context/` is protected) |

## Branches and landing

Branch from `release/next` and open the pull request against `release/next` (draft first). Work lands on `release/next`, and `release/next` lands on `main` through the GitHub merge queue. Use merge commits; never rebase or force-push. Write `Refs #n`, not `Closes #n` (issues are closed by hand). Details: [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/leap/BUILDER-BRIEFING.md](docs/leap/BUILDER-BRIEFING.md).

## Try it

**On a laptop with Docker** (development only; every port is bound to `127.0.0.1`):

```sh
gh repo clone onemindos/ONEMINDOS && cd ONEMINDOS/deploy/compose   # needs repo access
./gen-tokens.sh                  # once: random owner and agent tokens into ./local/ (gitignored)
docker compose up -d --build     # NATS, gateway, dashboard, one node, two simulated machines
```

The dashboard is then on `http://127.0.0.1:8080`. Stop it with `docker compose down -v`.

**On a Debian 13 machine** (an unsupported developer install, with no OS rollback): `sudo deploy/install.sh --role hub`. Details, joining more machines and uninstalling are in [deploy/README.md](deploy/README.md).

**The real image** is built and boot-tested in QEMU by CI (`make image BOARD=x86_64-efi`, then `make battery`; needs Linux with KVM). See [the Makefile](Makefile) and [`os/`](os/).

## Build and test

Each part has its own checks, and CI runs the same ones. The full table is in [AGENTS.md](AGENTS.md#engineering-where-code-lives-and-how-to-build-it). The repo-wide ones:

```sh
make lint                          # every linter
make test                          # unit tests for every part
python3 -I scripts/changes.py check
make hygiene                       # gitleaks + public-repo hygiene greps
```

On a Mac, the tool setup is in [docs/learning/mac-dev-loop.md](docs/learning/mac-dev-loop.md).

## Where to find things

| Path | What |
|---|---|
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | Requirements with IDs: the source of truth for *what* we build |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Founder decisions D-001 to D-031 (no D-030) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/architecture/](docs/architecture/) | Architecture. Where they differ, D-007 and the code in `os/` win |
| [docs/security/](docs/security/) | Threat model and hardening backlog |
| [docs/leap/](docs/leap/) | The build plan: [status board](docs/leap/STATUS.md), [agent work queue](docs/leap/AGENT-QUEUE.md), [builder briefing](docs/leap/BUILDER-BRIEFING.md), [alpha checklist](docs/leap/ALPHA-CHECKLIST.md) |
| [docs/learning/](docs/learning/) | Plain-language lessons on how the OS works |
| [research-output/](research-output/), [research/](research/), [context/](context/) | The research behind the decisions (competitors, base OS, 180-day plan) |
| [CHANGELOG.md](CHANGELOG.md), [changes/](changes/) | What changed, and the per-PR change fragments that feed it |
| [brand/](brand/), [lab-kits/](lab-kits/) | Brand assets; scripts for testing on real hardware |

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). In short: PRs go into `release/next`, one issue per PR, tests in the same PR, a change fragment in `changes/`, and every commit signed off (`git commit -s`). AI coding agents start with [AGENTS.md](AGENTS.md) and [docs/leap/BUILDER-BRIEFING.md](docs/leap/BUILDER-BRIEFING.md).

## Security

Report a vulnerability to the maintainers directly, not in an issue thread. See [SECURITY.md](SECURITY.md).

## License

[Apache-2.0](LICENSE) (decision D-001, open core). We study proven projects such as Home Assistant OS, umbrelOS and Olares for ideas, but never copy code from licences that are not Apache-compatible.
