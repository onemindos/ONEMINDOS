# The plugin ecosystem and the Marketplace {#sec-plugins}

> **Explain it like I'm the founder.** A plugin system is a promise: *anyone can add to OneMind without asking us to change the OS.* Most plugins (apps, widgets, AI tools, automations) live inside k3s and never touch the OS. The hard ones are **drivers and OS profiles**, because the OS image is read-only. The fix is a standard Linux feature, **system extensions**, that lays a signed add-on over the read-only OS and peels it off cleanly; we tested it in a Debian 13 VM [C-W19-006]. So OneMind builds **ten sockets** into release 1. The lesson from other ecosystems is about trust: Omarchy, Obsidian, HACS and Umbrel's community stores install unsigned code from whatever is on GitHub today [C-W19-011, C-W19-021], and npm and Open VSX were hit by self-spreading worms in 2025 [C-W19-025]. OneMind controls robots, so it takes the strict path: **pinned, signed, permission-declared plugins, with a remote "pull this now" list** from day one.

## Seven plugin types {#sec-plugin-types}

| # | Type | Examples | Runs where | Touches the host? |
|---|---|---|---|---|
| 1 | **Market app** | Jellyfin, Frigate, a robot fleet UI | k3s pods | Only via a declared grant |
| 2 | **Dashboard widget / UI extension** | Greenhouse gauge, robot teleop panel | Sandboxed iframe on its own origin (MCP Apps) [C-W19-035] | No |
| 3 | **Desktop/shell plugin** | Bar widget on the Omarchy edition | User's home directory, as Omarchy does [C-W19-011] | No |
| 4 | **Device / driver / protocol adapter** | ROS 2 arm driver, OPC UA bridge, MAVLink bridge, MHS device profile | k3s pod + optional udev rule or kernel module | Sometimes, through E3/E4 only |
| 5 | **AI skill / agent / tool** | Agent Skill bundle, MCP server | Agent sandbox | No |
| 6 | **Automation / workflow** | "If soil < 20 %, open valve 2"; Node-RED or n8n flow | Automation engine pod | No; every action through gateway scopes |
| 7 | **OS / image profile** | Greenhouse, TAK node, industrial gateway, kiosk | Host + Market | Yes, through E3/E4 only, never by editing the image |

## The ten extension points (DC-16) and how plugins plug in {#sec-extension-points}

![How a third-party plugin travels from a publisher to a box, and which socket it uses.](img/plugin-ecosystem.png){width=100%}

| ID | Socket | Release-1 status | Key enforcement |
|---|---|---|---|
| E1 | Market controller reading `onemind.app.yaml` | Frozen v1 | Helm is a compile target; Compose is imported |
| E2 | Capability broker for host grants (devices, host network, GPU, real time) | Frozen v1 | Any host grant makes a plugin effectively host root [C-REF-W19-security-003]; only countersigned plugins get them |
| E3 | Signed system/config extensions (sysext/confext) | Frozen v1 | systemd accepts unsigned images by default [C-REF-W19-security-004]: signed-only, no directories; one bad image blocks every merge, so stage first [C-REF-W19-cost-005] |
| E4 | Driver packs: signed kernel modules built per kernel by OneMind | Frozen v1 | Per-vendor packs, as Flatcar fixed it [C-REF-W19-cost-010]; `module.sig_enforce=1` everywhere |
| E5 | Dashboard UI slot (sandboxed iframes, MCP Apps) | v1-beta | Contract may change until real plugins use it |
| E6 | Capability registry + approval gateway | v1-beta | Approval rules themselves are not beta |
| E7 | NATS grants inside the locked subject grammar | Frozen v1 | — |
| E8 | Profiles (confext + sysexts + app set + defaults) | v1-beta | — |
| E9 | Trust root: signatures, countersignature, revocation, API levels | Frozen v1 | Expiring, rollback-protected revocation list [C-REF-W19-security-008]; signing proves *who*, not *what* [C-REF-W19-security-009] |
| E10 | Boot-stage overlays (device trees, early drivers) | Frozen v1 | Only through the release pipeline, because sysext cannot reach the boot partition |

**A third-party driver binary cannot drop into any box:** kernel drivers must be built by OneMind's pipeline for each OneMind kernel, which is how Flatcar does it [C-W19-005]. **The one condition on the whole design:** a test must show an attacker cannot make an unsigned extension merge after a reboot or slot switch (T-W19-01). If that fails, host extensions ship only inside the signed image and third-party host plugins wait (Z-22).

## How a third party builds and publishes a plugin {#sec-publish}

![From `onemind plugin init` to an owner's box.](img/publish-flow.png){width=100%}

| Command | Does |
|---|---|
| `onemind plugin init --kind adapter` | Scaffold manifest, chart, tests and a CI workflow |
| `onemind plugin validate` | Same validator code as the store and the box (the Omarchy idea [C-W19-010]) |
| `onemind plugin dev --box <name>` | Live-install onto a dev box or a VM on the Mac |
| `onemind plugin test` | Conformance tests per type, including a simulated robot |
| `onemind plugin pack` | OCI artifacts, SBOM, provenance; optional offline `.ompkg` |
| `onemind plugin publish` | From CI only, with short-lived OIDC credentials (trusted publishing [C-W19-026]) |

**Quality ladder:** Bronze is fully machine-checked, as 60% of Home Assistant's own integrations are unrated [C-REF3-W19-technical-007]; Silver and Gold add tests and support duties, modelled on Home Assistant's quality scale [C-W19-018]. **Review is a pipeline:** in a sample of Omarchy's store, one listing in five had moved past its validated commit [C-REF3-W19-technical-002], so boxes pin digests and re-validate each new one automatically, with human review only when permissions change.

## "Connect a robot → use OneMind" (F-3) {#sec-robot-onboarding}

![Robot plug-and-play: identify, match a signed adapter, approve, self-test in safe mode, register capabilities.](img/robot-onboarding.png){width=100%}

**Non-negotiable safety gates:** new robots start in *observe-only*; motion needs a declared workspace, speed limits and a hardware e-stop check; every AI-initiated motion is approval-gated; revoking an adapter means a safe stop. **First-class at launch:** robots that already have ROS 2 drivers and USB-serial or Ethernet discovery, such as LeRobot SO-100/101 arms (Apache-2.0 [C-W7-051]; Hugging Face is an MHS early adopter [C-W7-047]), TurtleBot 4, PX4 drones over MAVLink, and Jetson kits. **OneMind wraps ROS rather than competing with it**: ROS's index already holds 859 repositories for Jazzy, and its new Lyrical release targets Debian trixie [C-W19-038].

## What proven ecosystems do (constraint fit) {#sec-ecosystems}

| Ecosystem | Signing / pinning | Kill switch | Constraint fit | OneMind copies |
|---|---|---|---|---|
| Omarchy | Clones mutable HEAD [C-W19-012] | Delisting only | High for manifest + validator; low for trust | Manifest shape, validator CLI |
| Home Assistant + HACS | None for custom code | HACS "critical" list auto-uninstalls every 6 h [C-W19-015] | High | Quality scale, version blocklist, kill switch |
| HA add-ons | Optional | — | High | Declared-privilege security rating [C-TD-home-assistant-os-025] |
| Works with Home Assistant | — | Badge withdrawal | High | Certification template: lab test, CHF 500/year [C-W19-020] |
| umbrelOS community stores | Unsigned, re-cloned every 5 minutes [C-W19-033] | None | Medium | Multi-store model, ID prefixes |
| Olares OAC | Linter; privileged check off by default [C-W19-034] | — | High for format | k3s + Helm + manifest |
| VS Code Marketplace | Signs every extension [C-W19-023] | Block list + auto-uninstall | High for supply chain | Signing, malware scan, verified publishers |
| Grafana | Signature levels [C-W19-030] | — | High | Tiers that map to paid plugins |
| WordPress | Directory updates | Directory replaced a plugin by auto-update [C-W19-028] | Warning case | Kill switch needs governance |
| ROS | Tagged release repos [C-W19-038] | EOL distros sealed | High for robots | Wrap ROS packages |
| Viam | Typed `api` + `model` modules [C-W19-036] | — | High | Typed robot adapters |

## Hybrid self-hosted + cloud, certification and money (F-5, F-6) {#sec-partner}

- **Every plugin must work local-only.** Cloud features (relay, off-site backup, burst GPU, fleet view, store mirror) are optional plugins; the store, revocation list and fleet manager are **self-hostable**, the openBalena lesson [C-W19-044].
- **"Works with OneMind"**: a public compatibility definition per device class, an affordable annual fee, a lab test on reference boxes (Pi 5 Lite, x86 Pro, Jetson Robotics), and a badge withdrawn if the adapter is revoked. Android made compatibility a written, testable contract before granting access to its services [C-W19-039].
- **Revenue share:** free plugins list free; paid plugins keep **100% of the first USD 1M lifetime, then 85%**, the Shopify shape [C-W19-042], the most startup-friendly reference found (Apple and Google keep 15% up to $1M a year [C-W19-040, C-W19-041]).

**Requirements served:** A-1, A-2, A-5, A-6, AI-1, AI-3, AI-5, P-4, P-8, F-3, F-4, F-5, F-6, W-8, N-4, N-10.
