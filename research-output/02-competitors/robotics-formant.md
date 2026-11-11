# Formant: Tier C teardown (robotics fleet operations)

**Workstream:** W1 (Tier C) · **Tag:** `TD-tier-c-robotics` · **Date:** 2026-11-11 · **Status:** draft, brief (Tier C: no refuter pass)
**Claims:** `evidence/claims/TD-tier-c-robotics.csv` (C-TD-tier-c-robotics-001…015, 073) · **Sources:** `evidence/sources/TD-tier-c-robotics.md`
**What was read:** Formant's public docs (Markdown versions, page dates 2025-11-11 to 2026-09-24), its Terms of Service (last updated 2026-04-16), its homepage, and the Apache-2.0 repo `FormantIO/formant@64bcdb0`. The agent itself is closed source, so this teardown reads docs and contract text, not code. Press and funding facts are labelled SECONDARY.

> ### Explain it like I'm the founder
> Formant is a **cloud control room for robot fleets**. You install a small program (the "agent") on each robot's existing Linux. It sends data to Formant's cloud, lets an operator drive the robot from a web browser, and runs commands you define [C-TD-tier-c-robotics-001]. Formant does **not** ship an operating system: it installs on top of Ubuntu and updates itself with `apt` [C-TD-tier-c-robotics-002][C-TD-tier-c-robotics-005]. Since mid-2025 it sells itself as the "operating layer for physical AI", with chat-style AI agents that investigate fleet problems [C-TD-tier-c-robotics-011][C-TD-tier-c-robotics-013].
>
> **Why it matters to OneMind:** Formant shows what a robot operator wants to see every day: live telemetry, a map, video, a teleop panel, events and alerts, and "drive with approval". Copy that **screen design**. Do not copy the **model**: Formant is closed, cloud-first, and sold only through sales calls. OneMind's edge is to put the same control room **on the customer's own box**, open source, working offline.

---

## 1. Profile

| Topic | What Formant does | Evidence |
|---|---|---|
| **Architecture** | Closed SaaS platform plus an on-robot agent. The agent ingests telemetry (default 0.5 Hz, buffered on the device, uploadable on demand), is a WebRTC teleop peer, runs commands, and applies config pushed from the cloud. Teleop uses Twilio for signalling and TURN relay. | [C-TD-tier-c-robotics-001][C-TD-tier-c-robotics-006][C-TD-tier-c-robotics-007] |
| **Base OS** | None of its own. Agent page: Ubuntu 18.04 to 24.04 with ROS 1 Melodic/Noetic or ROS 2 Humble/Jazzy, amd64 and arm64. The system-requirements page lists a different set (adds Debian 9–11, drops 24.04): the docs contradict each other. | [C-TD-tier-c-robotics-002][C-TD-tier-c-robotics-003] |
| **Install** | A copy-paste command with a 72-hour provisioning token. The native script install is "not officially supported"; Docker is "highly recommended". Bulk and automated provisioning exist. | [C-TD-tier-c-robotics-004][C-TD-tier-c-robotics-015] |
| **Update / rollback** | Agent only: an apt package (`apt upgrade formant-agent`) from a GPG-signed repo, or a new Docker image. **No OS updates, no A/B, no rollback.** Device config changes are pushed from the cloud. | [C-TD-tier-c-robotics-005][C-TD-tier-c-robotics-001] |
| **App format** | None. Formant does not deploy robot software. It defines data streams, commands, views/modules, device configuration templates, and embeddable web views; an Agent SDK lets your code talk to the agent. | [C-TD-tier-c-robotics-015] |
| **AI features** | Theopolis, a natural-language interface (2023, SECONDARY); F3 (2025-06-30, SECONDARY): generative-AI interface, a 24/7 "agentic" monitoring layer, and multi-step investigation agents built on third-party models. The ToS defines "Formant AI" as Formant-owned technology. | [C-TD-tier-c-robotics-012][C-TD-tier-c-robotics-011][C-TD-tier-c-robotics-009] |
| **Security / identity** | Web terminal runs as a non-root `formant` user; terminal and port forwarding can be switched off on the robot. Google and OIDC SSO. Web app supports Chrome only. | [C-TD-tier-c-robotics-008][C-TD-tier-c-robotics-015][C-TD-tier-c-robotics-014] |
| **Hardware** | Any amd64/arm64 Ubuntu robot (so Jetson on its Ubuntu-based L4T, in principle). No hardware sold. | [C-TD-tier-c-robotics-002] |
| **Licence** | Proprietary. The agent, platform and AI are "Formant Technology" under the ToS. Only SDK resources and examples are open (Apache-2.0). A customer-hosted (private cloud / VPC) deployment is a licensed option. | [C-TD-tier-c-robotics-009][C-TD-tier-c-robotics-010] |
| **Business model** | Enterprise sales: no public price list (the pricing URL is a 404); "start a discovery session". USD 21M raised in 2023 led by BMW i Ventures (SECONDARY). Claims 644 production organizations (vendor figure, May 2026). | [C-TD-tier-c-robotics-013][C-TD-tier-c-robotics-012] |

## 2. Strengths and weaknesses

| Strengths | Weaknesses |
|---|---|
| Mature operator workflow: teleop, 3D scene, maps, events, interventions, analytics [C-TD-tier-c-robotics-015] | No OS, no app deployment, no rollback: it monitors robots but cannot keep their software healthy [C-TD-tier-c-robotics-005] |
| Works on flaky links: on-device buffering and on-demand upload [C-TD-tier-c-robotics-006] | Cloud-dependent: install needs internet, teleop goes through Twilio [C-TD-tier-c-robotics-004][C-TD-tier-c-robotics-007] |
| Sensible safety switches for remote shell and port forwarding [C-TD-tier-c-robotics-008] | Closed source; "Formant AI" outputs are Formant Technology under the ToS [C-TD-tier-c-robotics-009] |
| Early to AI agents on fleet data [C-TD-tier-c-robotics-011] | Docs disagree on supported OSes; native install officially unsupported [C-TD-tier-c-robotics-003][C-TD-tier-c-robotics-004] |

## 3. What competitors do (robotics fleet layer)

| Product | Ships an OS? | Updates robot software? | Self-hosted? | Licence | Constraint fit to OneMind |
|---|---|---|---|---|---|
| **Formant** | No | No (agent only, apt) [C-TD-tier-c-robotics-005] | Licensed private-cloud option [C-TD-tier-c-robotics-009] | Proprietary | **Low** for the foundation; **Candidate** for the operator-UI pattern |
| Viam ([robotics-viam.md](robotics-viam.md)) | No | Yes: modules, viam-server; OS via apt in place [C-TD-tier-c-robotics-046] | No (cloud) | AGPL-3.0 core | Candidate (app model) |
| Foxglove ([robotics-foxglove.md](robotics-foxglove.md)) | No | No | Enterprise on-prem on Kubernetes [C-TD-tier-c-robotics-024] | MIT SDK, closed app | Candidate (data/visualisation) |
| balena ([robotics-balena.md](robotics-balena.md)) | Yes (Yocto) | Yes, A/B OS + containers [C-TD-balenaos-012] | openBalena (AGPL) [C-TD-balenaos-006] | Apache-2.0 OS | Candidate (update engine) |
| **OneMind target** | Yes (Debian 13 + L4T flavour) | Yes, health-gated A/B + Helm apps | Default | Apache-2.0 | — |

## 4. Constraint fit

Formant's constraints differ from OneMind's on every axis that matters for the foundation: it is closed, cloud-hosted, has no OS, no app runtime and no Kubernetes, and targets enterprise fleets with a sales team. **Fit: Low** for base OS, updates and licensing. **Candidate** for one layer only: the operator experience (teleop, events, interventions), where it is the most mature reference studied. Practitioners note the same split: robotics teams still have to pick an OS update method separately (A/B vs containers) [C-TD-tier-c-robotics-073].

## 5. What OneMind copies and what it does better

| ID | Recommendation | Evidence | Req IDs |
|---|---|---|---|
| REC-TDC-FOR-01 | Copy the operator feature set for the robot card: live telemetry, map, video, teleop, events with notifications, intervention requests, scheduled commands. Pattern only. | [C-TD-tier-c-robotics-001][C-TD-tier-c-robotics-015] | M-7, N-7, UX-4, UX-5 |
| REC-TDC-FOR-02 | Copy on-device buffering with on-demand upload, and per-stream rate limits, into the OneMind node agent (NATS JetStream already buffers). | [C-TD-tier-c-robotics-006] | N-5, N-6, M-1 |
| REC-TDC-FOR-03 | Copy the robot-side kill switches: remote shell and port forwarding off unless enabled on the device, running as a non-root user. | [C-TD-tier-c-robotics-008] | U-4, AI-5 |
| REC-TDC-FOR-04 | Do better: teleop must work peer-to-peer on the LAN or tailnet with no third-party relay, and the whole control room must run on the customer's box. | [C-TD-tier-c-robotics-007] | M-1, M-2, U-5, F-6 |
| REC-TDC-FOR-05 | Do better: pair monitoring with what Formant lacks: signed A/B OS updates with health-gated rollback and app deployment, in one product. | [C-TD-tier-c-robotics-005][C-MATRIX-002] | R-1, R-3, F-3, F-4 |
| REC-TDC-FOR-06 | Do better on AI: Formant's agents work on cloud data under proprietary terms; OneMind's agents run locally through MCP with per-agent scopes and human approval for any physical action. | [C-TD-tier-c-robotics-009][C-TD-tier-c-robotics-011] | AI-2, AI-4, AI-5 |
| REC-TDC-FOR-07 | Publish one support matrix per OS, generated from CI, so docs cannot contradict each other the way Formant's two pages do. | [C-TD-tier-c-robotics-003] | R-2, W-3 |

## 6. Gaps

- No code read: the agent is proprietary. Behaviour comes from docs and the ToS.
- F3, Theopolis and funding come from press reprints (SECONDARY). Formant's pricing is not public.
- The "644 organizations" figure is the vendor's own and unaudited.

## Glossary

| Term | Meaning |
|---|---|
| **Agent** | A small program on each robot that talks to a cloud service. |
| **Telemetry / ingestion** | Data a robot reports (position, battery, video), and the act of uploading it. |
| **Teleoperation (teleop)** | Driving a robot remotely from a screen. |
| **WebRTC** | The browser technology for live, low-latency video and data between two peers. |
| **TURN relay** | A server that forwards WebRTC traffic when two peers cannot connect directly; it sees the (encrypted) traffic flow. |
| **SaaS** | Software run by the vendor in its cloud and rented by subscription. |
| **apt** | Debian/Ubuntu's package installer; updates files in place, so it cannot roll back a whole system. |
| **A/B update** | Two OS copies; the update goes to the spare and the device falls back if it fails. |
| **ROS 1 / ROS 2** | The Robot Operating System frameworks; ROS 1 is end-of-life, ROS 2 is current. |
| **Agentic AI** | AI that plans and takes multi-step actions, not just answers questions. |
