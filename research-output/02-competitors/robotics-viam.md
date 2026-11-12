# Viam: Tier C teardown (robot software platform)

**Workstream:** W1 (Tier C) · **Tag:** `TD-tier-c-robotics` · **Date:** 2026-11-11 · **Status:** draft, brief (Tier C: no refuter pass)
**Claims:** `evidence/claims/TD-tier-c-robotics.csv` (C-TD-tier-c-robotics-040…057, 073) plus reused [C-W16-025], [C-W19-036], [C-W7-043] · **Sources:** `evidence/sources/TD-tier-c-robotics.md`
**What was read:** Viam's docs (viam-agent, viam-server, versions and rollouts, MCP, AI assistant, agent guide, pricing) on 2026-11-11, and code at `viamrobotics/agent@6d641fa` (2026-11-10) and `viamrobotics/rdk@046082e` (2026-11-10). Permalink prefix **AG** = `https://github.com/viamrobotics/agent/blob/6d641fa60f76984720c3fa8a8e9300a1f5e78595/`.

> ### Explain it like I'm the founder
> Viam is the closest thing to **"connect a robot, use Viam"** that exists today. You run a one-line installer on a Pi, Jetson or PC; it sets up **viam-agent** (a supervisor) and **viam-server** (the robot runtime). In the web app you pick parts from a catalogue ("Raspberry Pi 5", "xArm6", "webcam"), and every part becomes a typed, programmable API [C-TD-tier-c-robotics-055]. Drivers and features are **modules** downloaded from a registry [C-W19-036]. There is also an **MCP server**, so Claude can configure a fleet and even move hardware [C-TD-tier-c-robotics-051].
>
> Two catches. First, the core (viam-server and viam-agent) is **AGPL-3.0** [C-TD-tier-c-robotics-040][C-TD-tier-c-robotics-041], so OneMind may study it but must not copy its code into Apache-2.0 OneMind. Second, it is **not an OS**: OS updates are plain `apt`/`dnf` in place, and a bad viam-server release is **not rolled back automatically** [C-TD-tier-c-robotics-044][C-TD-tier-c-robotics-046]. That is exactly the gap OneMind's health-gated A/B update fills.

---

## 1. Profile

| Topic | What Viam does | Evidence |
|---|---|---|
| **Architecture** | Cloud app + on-device `viam-server` (built from the RDK) + `viam-agent` (systemd supervisor for viam-server, first-boot Wi-Fi/Bluetooth provisioning, OS settings, networking; polls the cloud every ≥5 s). Each machine is a set of typed resources (component/service APIs in protobuf over gRPC) that it can list at runtime. | [C-TD-tier-c-robotics-040][C-TD-tier-c-robotics-043][C-TD-tier-c-robotics-055] |
| **Base OS** | None. Runs on the customer's Linux (Debian, Ubuntu, Pi OS, Fedora/RHEL family), plus macOS/Windows for development; ESP32 microcontrollers via the micro-RDK. | [C-TD-tier-c-robotics-046][C-TD-tier-c-robotics-042][C-W7-043] |
| **Install** | A `curl … | sh` one-liner that embeds the machine's API key; a preinstall script for baking devices at manufacture. | [C-TD-tier-c-robotics-050] |
| **Update / rollback** | viam-server and viam-agent: download → SHA-256 check → atomic symlink swap; old binary kept 30 days. **No automatic rollback** (`Versions` keeps `PreviousVersion` "for (TODO) rollback", AG `version_control.go#L77-L82`). Config: cached locally for 60 days offline, revertible from History. OS: in-place `unattended-upgrades` or agent-run `apt`/`dnf`/`yum`, with reboots held for a maintenance window (AG `subsystems/syscfg/managed_upgrades_linux.go#L3-L11`). | [C-TD-tier-c-robotics-044][C-TD-tier-c-robotics-045][C-TD-tier-c-robotics-048][C-TD-tier-c-robotics-046] |
| **Rollout control** | Modules track latest, or pin a version, or follow a fragment tag. Maintenance window = a boolean sensor. No canary or percentage rollout; per-machine versions are not shown in the fleet dashboard. | [C-TD-tier-c-robotics-049] |
| **App format** | Modules: `meta.json` with `module_id`, models as `api` + `model` pairs, per-arch builds, optional first-run setup. Fragments are reusable config blocks. | [C-W19-036][C-TD-tier-c-robotics-049] |
| **AI features** | In-app AI assistant stages config changes for review; shell commands need approval. A remote OAuth MCP server, scoped to the user's permissions, whose "Live machine (destructive)" tools act immediately "with no draft and no undo". Cloud simulation of a machine before hardware arrives. ML training/deployment (pricing page). | [C-TD-tier-c-robotics-053][C-TD-tier-c-robotics-051][C-TD-tier-c-robotics-056][C-TD-tier-c-robotics-054] |
| **Security** | API keys scoped to machine, location or org, **full write by default**; per-method limits optional. The MCP server creates a machine API key if none exists. | [C-TD-tier-c-robotics-052][C-TD-tier-c-robotics-051] |
| **Hardware** | Setup guides for Raspberry Pi, Jetson AGX Orin and Orin Nano; ESP32. ext4 error counters stand in for SMART on SD cards (AG `storage_health_linux.go#L27`). | [C-TD-tier-c-robotics-057][C-TD-tier-c-robotics-047] |
| **Licence** | RDK, agent and micro-RDK: AGPL-3.0. SDKs (e.g. Python): Apache-2.0. | [C-TD-tier-c-robotics-040][C-TD-tier-c-robotics-041][C-TD-tier-c-robotics-042] |
| **Business model** | On-device software free; cloud usage billed after USD 5/month (data, egress, compute, notifications). USD 45M Series B, USD 87M total (SECONDARY). | [C-TD-tier-c-robotics-054][C-W16-025] |

## 2. Strengths and weaknesses

| Strengths | Weaknesses |
|---|---|
| Best developer experience studied: typed hardware APIs, a module registry, fragments, simulation first [C-TD-tier-c-robotics-055][C-TD-tier-c-robotics-056] | Not an OS; OS updates in place with no A/B [C-TD-tier-c-robotics-046] |
| Works offline on cached config for 60 days [C-TD-tier-c-robotics-048] | No automatic rollback of viam-server or agent; a crashing release retries until a human pins an older one [C-TD-tier-c-robotics-044] |
| First-boot provisioning over hotspot/Bluetooth (QR-style onboarding) [C-TD-tier-c-robotics-043] | Keys default to full write; MCP live tools can move hardware with no undo [C-TD-tier-c-robotics-052][C-TD-tier-c-robotics-051] |
| AI that drafts changes for review [C-TD-tier-c-robotics-053] | AGPL core; fleet and MCP depend on Viam's cloud [C-TD-tier-c-robotics-040][C-TD-tier-c-robotics-051] |

## 3. What competitors do (robot runtime and app layer)

| Product | Robot app format | Automatic rollback? | Offline operation | AI / MCP on hardware | Licence | Constraint fit to OneMind |
|---|---|---|---|---|---|---|
| **Viam** | Modules (`meta.json`, api + model) [C-W19-036] | **No** [C-TD-tier-c-robotics-044] | 60-day cached config [C-TD-tier-c-robotics-048] | Cloud MCP, destructive live tools [C-TD-tier-c-robotics-051] | AGPL-3.0 core | **Candidate** for the device/adapter model and onboarding UX; **Low** for OS, updates and code reuse |
| Formant ([robotics-formant.md](robotics-formant.md)) | None | No | Buffered telemetry [C-TD-tier-c-robotics-006] | F3 (SECONDARY) | Proprietary | Low |
| balena ([robotics-balena.md](robotics-balena.md)) | Compose subset + contracts [C-TD-balenaos-031][C-TD-balenaos-034] | OS: boot-count fallback [C-TD-balenaos-020] | Runs offline; updates via cloud | Experimental CLI MCP [C-TD-balenaos-057] | Apache-2.0 OS | Candidate |
| ROS 2 (rosdistro) | `package.xml` packages [C-W19-038] | n/a | Native | None | Mostly Apache-2.0/BSD | High (adapters wrap ROS) |
| **OneMind target** | Helm + `onemind.app.yaml`; adapters with typed capabilities | Yes, health-gated A/B | Local-first | Local MCP gateway with approvals | Apache-2.0 | — |

## 4. Constraint fit

Viam targets the same user OneMind does ("connect a robot") and the same boards (Pi, Jetson, x86) [C-TD-tier-c-robotics-057], so its **user experience** is the best match in this tier. Its constraints differ where the foundation is decided: no OS, no image updates, cloud-dependent fleet control, and an AGPL core that OneMind cannot fold into Apache-2.0 code (D-001). **Fit: Candidate** for the device model, module registry and onboarding; **Low** for base OS and updates. It is a competitor-partner: a OneMind node could run viam-server as a Market app for customers already on Viam.

## 5. What OneMind copies and what it does better

| ID | Recommendation | Evidence | Req IDs |
|---|---|---|---|
| REC-TDC-VIAM-01 | Copy the device model: every robot part is a typed capability (`api` + `model` + name) the node can list at runtime, so AI and the dashboard can discover a robot without docs. Write it fresh; do not copy AGPL code. | [C-TD-tier-c-robotics-055][C-W19-036][C-TD-tier-c-robotics-040] | N-1, N-3, F-3, F-5, AI-1 |
| REC-TDC-VIAM-02 | Copy first-boot provisioning (hotspot or Bluetooth) and a factory preinstall path; do better by using a QR code that carries a one-time enrolment token instead of an API key in a shell one-liner. | [C-TD-tier-c-robotics-043][C-TD-tier-c-robotics-050] | N-4, F-3, U-4 |
| REC-TDC-VIAM-03 | Copy "simulate before hardware": a robot can be added as a simulated node first, then swapped for the real one. | [C-TD-tier-c-robotics-056] | N-7, F-1 |
| REC-TDC-VIAM-04 | Do better on updates: health-gated A/B for the OS (REC-DEC-07) and automatic rollback for the robot runtime and adapters too, with a canary ring and per-machine version view. | [C-TD-tier-c-robotics-044][C-TD-tier-c-robotics-049] | R-1, R-3, UX-6 |
| REC-TDC-VIAM-05 | Do better on AI safety: least-privilege keys by default, MCP runs locally, and any tool that moves hardware needs a human approval and leaves an audit record. | [C-TD-tier-c-robotics-051][C-TD-tier-c-robotics-052] | AI-2, AI-4, AI-5, U-4 |
| REC-TDC-VIAM-06 | Copy the cheap SD-card health signal (ext4 error counters) into the node agent for Pi-class nodes. | [C-TD-tier-c-robotics-047] | N-2, UX-4 |
| REC-TDC-VIAM-07 | Offer viam-server as an optional Market app (as a separate program under its own licence) for customers already on Viam. Check AGPL network-use terms before listing. | [C-TD-tier-c-robotics-040] | F-5, F-6, A-1 |

## 6. Gaps

- Only the agent's update, OS-upgrade and storage-health code was read; viam-server internals were not.
- The docs show agent version examples (e.g. 1.4.0) newer than the latest GitHub release (v1.2.1); not resolved.
- Viam's enterprise pricing and the ML training service were not examined.

## Glossary

| Term | Meaning |
|---|---|
| **RDK** | Robot Development Kit: Viam's open-source runtime that becomes viam-server. |
| **Module / registry** | A downloadable driver or feature, and the catalogue it comes from. |
| **Fragment** | A reusable block of robot configuration applied to many machines. |
| **Typed API** | A fixed interface per device kind (arm, camera, motor) so any arm can be driven the same way. |
| **gRPC / protobuf** | A fast way for programs to call each other over a network, and its message format. |
| **Symlink swap** | Pointing a shortcut at the new program file; quick to switch, but no automatic way back. |
| **Canary rollout** | Updating a few devices first and the rest only if they stay healthy. |
| **AGPL-3.0** | A strong copyleft licence; code copied from it must be released under it, even when only offered over a network. |
| **Maintenance window** | The time a machine is allowed to take updates or reboot. |
| **ESP32** | A cheap Wi-Fi microcontroller common in IoT devices. |
