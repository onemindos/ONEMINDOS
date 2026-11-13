<!-- SPDX-License-Identifier: Apache-2.0 -->
# 12 · Competitor and adjacent teardowns (FB-11): the matrix

**Date:** 2026-11-12 · **Workstream:** FB-11 (Tier A for Fleet, FDO and NATS, which were run in labs; Tier B for the rest) · Detail per group in `competitors/`.
**Serves requirements:** RS-1, RS-2, F-4, F-5, F-11, M-7

> **Explain it like I'm the founder.** Thirty-odd systems were checked for one thing: how a machine joins, proves who it is, talks, works offline, updates, and whether AI can touch it. The pattern is clear. Industrial and robotics platforms all have an agent that calls out to a central manager; the best open one (Flight Control) even makes a human approve each new device, as OneMind does. Nobody combines that with local-first ownership, a home-friendly mesh and gateway-enforced approval for AI actions on physical devices. That combination is OneMind's lane.

## 1. Matrix (one line per system; ✓ = has it, ✗ = does not, ~ = partly, ? = UNVERIFIED)

| System | Group | Pull / no inbound port | Human-approved join | Works offline indefinitely | Staged rollout with halt | AI with gated actuation | Licence fits Apache core | Constraint fit |
|---|---|---|---|---|---|---|---|---|
| Rancher Fleet | k8s multi-cluster | ✓ [C-FB4-003] | ✗ (token) | ✓ (pull) | ~ (lab: needs care [C-FB4-016]) | ✗ | ✓ Apache-2.0 | High pattern |
| Open Cluster Management | k8s multi-cluster | ✓ [C-FB4-009] | ? | ✓ | ? | ✗ | ✓ | Medium |
| Argo CD ApplicationSet | GitOps | ✗ push [C-FB4-010] | ✗ | ✗ | ~ | ✗ | ✓ | Low for NATted sites |
| argocd-agent | GitOps | ✓ [C-FB4-011] | ? | ~ | ? | ✗ | ✓ (pre-1.0) | Watch |
| KubeEdge | k8s edge | ✓ edge→cloud | ✗ | ~ autonomy [C-FB4-014] | k8s | ✗ | ✓ | Low (cloud control plane) |
| OpenYurt | k8s edge | ✓ | ✗ | ~ [C-FB4-013] | k8s | ✗ | ✓ | Low |
| Akri | leaf devices | n/a | ✗ | ~ | n/a | ✗ | ✓ | Pattern |
| Cluster API | cluster lifecycle | n/a | ✗ | n/a | ~ | ✗ | ✓ | Low |
| Palette / Kairos | edge k8s | ? | ? | ? | ? | ✗ | ~ (Palette commercial) | Low |
| Talos Omni | k8s/edge | ? | ? | ? | ? | ✗ | ✗ BSL (C-TD-talos-036) | Low |
| Flight Control (Red Hat) | device fleet | ✓ [C-FB11-004] | **✓** `flightctl approve` | ✓ | ✓ success threshold [C-FB11-005] | ✗ | ✓ Apache-2.0 | **High pattern**, RHEL OS |
| Siemens Industrial Edge | industrial | ? | ? | ~ air-gapped IEM [C-FB11-007] | ? | ? | ✗ proprietary | Low |
| Litmus Edge | industrial | ? | ? | ✓ offline-first [C-FB11-010] | ? | ? | ✗ | Low |
| AWS Greengrass | industrial/IoT | ✓ | ✗ | ~ | ~ continuous [C-FB11-006] | ✗ | ~ (download licence) | Low |
| Azure IoT Operations | industrial | ✓ | ✗ | ✗ **72 h max** [C-FB11-009] | Arc | ✗ | ✗ | Low |
| Eclipse Kura / ioFog | gateways | ? | ? | ? | ? | ✗ | ✗ EPL-2.0 | Low |
| Formant | robotics | ✓ | ✗ | ~ buffers | ✗ in place | ? (F3, SECONDARY) | ✗ | Low |
| Viam | robotics | ✓ | ✗ (key in install line) | ~ 60 days config | ✗ no canary | ✗ destructive MCP tools act at once | ✗ AGPL | Medium (model), low (licence) |
| Foxglove | robotics data | ✓ | ✗ | ✓ Edge Sites | n/a | ✗ MCP, no approval | ~ SDK MIT | Medium (SDK) |
| balena | device OS + cloud | ✓ | ✗ (fleet key) | ~ | ✓ health rollback | ✗ | ~ (openBalena AGPL) | Medium |
| NVIDIA Jetson tooling | robotics | ? | ? | ? | A/B OTA (mission 01) | ? | ✗ EULA | UNVERIFIED |
| Anduril Lattice | defence C2 | ? | ? | ? | ? | ? | ✗ proprietary [C-FB11-012] | Low |
| Open-RMF | multi-fleet robots | n/a | n/a | ✓ site-local | packages | ✗ | ✓ Apache-2.0 | High **as an app** |
| Home Assistant | home | ✓ via Cloud/VPN [C-FB11-014] | n/a | ✓ | RAUC (HAOS) | ~ | ✓ Apache-2.0 | High as an app |
| umbrelOS | home | ✓ (Tailscale) | n/a | ✓ | OTA | ~ MCP | ✗ PolyForm NC | Patterns |
| Olares | home cluster | ~ | ✗ | ✓ | 11-stage upgrade | ~ | ✗ AGPL | Patterns |
| Tailscale / Headscale | network | ✓ | ~ (keys) | ✓ while peers connect | n/a | n/a | ✓ BSD-3 | **Underlay** (lab PASS) |
| NATS | bus | ✓ leaf [C-FB3-002] | n/a | ✓ (outbox, lab) | n/a | n/a | ✓ Apache-2.0 | **Adopted** |
| Zenoh | robot bus | ✓ | n/a | ✓ | n/a | n/a | ✓ Apache/EPL | Inside robots |
| FDO | onboarding | ✓ | ✓ if import is gated (lab) | n/a | n/a | n/a | ✓ go-fdo Apache-2.0 | Optional front end |
| SPIFFE/SPIRE | identity | n/a | ✗ (policy) | ~ cached SVIDs | n/a | n/a | ✓ | Pattern |
| Matter | home devices | n/a | ✓ (user commissions) | ✓ local | vendor | n/a | ✓ SDK Apache-2.0 | Through a Matter app |
| **OneMind (designed)** | — | ✓ | ✓ pairing code / voucher | ✓ no limit | ✓ (to build; F3 gate) | **✓ gateway approval + step-up** | ✓ | — |

## 2. Five lessons that change OneMind's plans

1. **Copy Flight Control's enrollment-request + approval and its success-threshold batches**; both match designs already on the board, and the one open tool with matching constraints does them [C-FB11-004, C-FB11-005].
2. **Do not copy shared provisioning keys** (balena, Viam): they conflict with FABRIC's "no long-lived shared secret".
3. **Define ring gating by the previous ring's measured health**; Fleet's rule counts pending updates as unavailability, which stalls strict settings, and an offline site holds back later rings (lab fb4 T3 and E6, [C-FB4-016, C-LAB-fb4-fleet-rings-009]).
4. **Registration is the attack surface of pull-based fleets** (three Fleet advisories in two months [C-FBREF-011]); ring membership must come from the hub's enrolment record, not from labels a site reports.
5. **No competitor puts a human approval in the gateway in front of AI-driven actuation** (Viam's and Foxglove's MCP servers do not [C-TD-tier-c-robotics-029, -051]): keep it as the core differentiator.
