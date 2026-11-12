# Foxglove: Tier C teardown (robotics data and visualisation)

**Workstream:** W1 (Tier C) · **Tag:** `TD-tier-c-robotics` · **Date:** 2026-11-11 · **Status:** draft, brief (Tier C: no refuter pass)
**Claims:** `evidence/claims/TD-tier-c-robotics.csv` (C-TD-tier-c-robotics-020…030) plus reused [C-W16-024], [C-W7-059], [C-W11-059], [C-W19-037] · **Sources:** `evidence/sources/TD-tier-c-robotics.md`
**What was read:** Foxglove's docs (fleet, Foxlet, remote access, Edge and Primary Sites, agents, MCP, standalone licence, pricing) on 2026-11-11, its "two years on" blog post, and `foxglove/foxglove-sdk@8dc7525` (release sdk/v0.30.3, MIT).

> ### Explain it like I'm the founder
> Foxglove is the **"Grafana for robots"**: the tool robotics engineers use to replay and inspect what a robot saw and did (camera, lidar, joint angles, logs), live or from recordings. It created **MCAP**, the open recording format that ROS 2 now uses [C-W7-059]. In 2024 it **closed its app**: the last open-source version was v1.87.0 [C-TD-tier-c-robotics-026]. Today it is a paid data platform with open-source plumbing (SDK and ROS bridge, MIT) [C-TD-tier-c-robotics-027], cloud or on-premises storage, and AI agents that build dashboards and search recordings for you [C-TD-tier-c-robotics-028].
>
> **Why it matters to OneMind:** Foxglove is **not an OS and not a fleet updater**. It is the best visualisation layer in robotics and the one most likely to be a **partner, not a rival**. OneMind should speak its formats (MCAP, the Foxglove WebSocket protocol), embed the open fork Lichtblick in the dashboard [C-W11-059], and let a customer point the paid Foxglove app at their OneMind robots.

---

## 1. Profile

| Topic | What Foxglove does | Evidence |
|---|---|---|
| **Architecture** | Three on-device parts: the SDK (C++/Python/Rust; logs MCAP and serves live data), the Foxglove Bridge (a ROS 1/2 package on top of the SDK), and **Foxlet**, a daemon that watches a folder for recordings and uploads them. Cloud side: a data platform (Primary Sites) and optional **Edge Sites** that hold data near the robots. | [C-TD-tier-c-robotics-020][C-TD-tier-c-robotics-023] |
| **Base OS** | None. Foxlet ships as a .deb, a static binary or a Docker image for amd64/arm64. | [C-TD-tier-c-robotics-021] |
| **Remote access** | A WebRTC gateway on the robot dials out with a device token; Foxglove runs STUN/TURN and a forwarding server (SFU). Video adapts to bandwidth; point clouds are compressed. | [C-TD-tier-c-robotics-022] |
| **Update / rollback** | Not offered for robots. Foxglove updates only its own components (edge controller, Foxlet) through their packages. | [C-TD-tier-c-robotics-023][C-TD-tier-c-robotics-021] |
| **App format** | No robot apps. Extensions (`.foxe`) add custom panels and message converters to the Foxglove app. | [C-W19-037][C-TD-tier-c-robotics-030] |
| **Self-hosting** | Enterprise only. An on-prem Primary Site needs Kubernetes 1.30+, Helm 3.12+ and S3-compatible storage (tested with MinIO). Edge controllers can also install by Helm. A standalone licence runs the desktop app air-gapped. | [C-TD-tier-c-robotics-024][C-TD-tier-c-robotics-023][C-TD-tier-c-robotics-030] |
| **AI features** | An in-app agent that asks before changing anything; a Slack bot; a desktop-only local MCP server for Claude Code, Cursor and others. The MCP server adds no approval of its own: it labels tools read-only or destructive and leaves approval to the client. Actions are logged as the user, not the agent. Agents can only list devices, not command them. | [C-TD-tier-c-robotics-028][C-TD-tier-c-robotics-029] |
| **Hardware** | Hardware-agnostic; framework guides for ROS 1/2, PX4 and LeRobot. | `foxglove-llms.txt` index (saved) |
| **Licence** | Open: SDK, ROS 2 bridge (MIT, now in the SDK repo), MCAP (MIT). Closed: the app and data platform since February 2024. The old app lives on as the community fork Lichtblick (MPL-2.0). | [C-TD-tier-c-robotics-027][C-TD-tier-c-robotics-026][C-W7-059][C-W11-059] |
| **Business model** | Free (10 GB, 3 users, 5 devices); Pro USD 20/month plus usage, billed by monthly active devices; Enterprise custom with self-hosting. USD 40M Series B in November 2025. | [C-TD-tier-c-robotics-025][C-W16-024] |

## 2. Strengths and weaknesses

| Strengths | Weaknesses |
|---|---|
| The de-facto robotics data format (MCAP) and visualiser; broad framework coverage [C-W7-059] | Closed the app in 2024; open users were left on a frozen 1.x or forks [C-TD-tier-c-robotics-026] |
| Self-hosting on Kubernetes with MinIO: the same stack OneMind runs [C-TD-tier-c-robotics-024] | Self-hosting and on-prem are Enterprise-only, custom-priced [C-TD-tier-c-robotics-025] |
| Clear agent safety model in the app (ask first) and honest docs on MCP risk [C-TD-tier-c-robotics-029] | Not a fleet manager: no OS, no software deployment, no rollback [C-TD-tier-c-robotics-020] |
| Remote access built for bad networks (adaptive video, compression) [C-TD-tier-c-robotics-022] | Remote access and agents depend on Foxglove's cloud [C-TD-tier-c-robotics-022][C-TD-tier-c-robotics-028] |

## 3. What competitors do (robot data and visualisation)

| Product | Open visualiser? | Recording format | Self-hosted data | AI / MCP | Constraint fit to OneMind |
|---|---|---|---|---|---|
| **Foxglove** | No (since v1.87.0) [C-TD-tier-c-robotics-026] | MCAP (MIT) [C-W7-059] | Enterprise, Kubernetes + MinIO [C-TD-tier-c-robotics-024] | Sidebar + local MCP [C-TD-tier-c-robotics-028] | **Candidate** for data formats and an optional paid integration; **Low** as a foundation |
| Lichtblick | Yes, MPL-2.0 [C-W11-059] | MCAP, bags | n/a (desktop/web app) | None found | **Default** for the embedded robot panel (REC already in `12-…` §14) |
| Formant ([robotics-formant.md](robotics-formant.md)) | No | Proprietary streams | Licensed private cloud [C-TD-tier-c-robotics-009] | F3 agents (SECONDARY) [C-TD-tier-c-robotics-011] | Low |
| Viam ([robotics-viam.md](robotics-viam.md)) | Web app (cloud) | Viam data capture | No | Cloud MCP that can move hardware [C-TD-tier-c-robotics-051] | Candidate |

## 4. Constraint fit

Foxglove's customers are robotics engineering teams; OneMind's users include people who never open a lidar view. Foxglove has no OS, no app runtime and no robot control, so it cannot be the default for any foundation layer. **Fit: Low** for the foundation, **Candidate** for data and visualisation, and **High** as an integration partner, because its on-prem stack (Kubernetes, Helm, S3/MinIO) already matches OneMind's platform tier [C-TD-tier-c-robotics-024].

## 5. What OneMind copies and what it does better

| ID | Recommendation | Evidence | Req IDs |
|---|---|---|---|
| REC-TDC-FOX-01 | Make MCAP the native robot recording format and expose robot topics through the Foxglove WebSocket protocol via the MIT SDK/bridge, so both Lichtblick and the paid Foxglove app work against a OneMind robot with no adapter. | [C-W7-059][C-TD-tier-c-robotics-027] | M-7, N-7, F-5 |
| REC-TDC-FOX-02 | Ship a "Foxglove Primary Site" as a Market app candidate for Enterprise buyers (they bring the licence); OneMind supplies k3s, Helm and MinIO-compatible storage. Verify licence terms before listing. | [C-TD-tier-c-robotics-024][C-TD-tier-c-robotics-025] | A-1, F-5, F-6 |
| REC-TDC-FOX-03 | Copy the edge-site idea: recordings stay on the box near the robots and are forwarded to cloud only when chosen. | [C-TD-tier-c-robotics-023] | M-1, N-5, N-6 |
| REC-TDC-FOX-04 | Copy the agent rule "ask before changing anything, with one / this chat / always scopes", and do better for MCP: OneMind's gateway enforces approval itself for destructive or physical tools instead of trusting the client, and logs the agent as its own identity. | [C-TD-tier-c-robotics-028][C-TD-tier-c-robotics-029] | AI-2, AI-4, AI-5, U-4 |
| REC-TDC-FOX-05 | Lesson from 2024: keep the parts of OneMind that users depend on open under Apache-2.0 (D-001), and say in writing which parts are paid, so a later licence change cannot strand users the way Studio 1.x users were. | [C-TD-tier-c-robotics-026] | D-001, M-8, A-6 |

## 6. Gaps

- No code read beyond the SDK licence and package metadata; the platform is closed.
- Enterprise self-hosting prices and licence terms are not public.

## Glossary

| Term | Meaning |
|---|---|
| **MCAP** | An open file format for recording multi-sensor robot data with timestamps; the ROS 2 default bag format. |
| **Bag / recording** | A file holding everything a robot published over a period, for replay. |
| **SDK** | Software Development Kit: libraries developers build into their own programs. |
| **SFU** | Selective Forwarding Unit: a server that receives one video stream and forwards it to many viewers. |
| **Primary Site / Edge Site** | Foxglove's main data store, and a small store near the robots that forwards to it. |
| **Helm / MinIO** | Kubernetes's package format, and an open-source S3-compatible object store. |
| **MCP** | Model Context Protocol, the standard way AI agents call tools. |
| **Fork** | A copy of open-source code that continues separately (Lichtblick is a fork of Foxglove Studio). |
| **MPL-2.0** | A file-level copyleft licence: changes to its files stay open, your own files can stay Apache-2.0. |
