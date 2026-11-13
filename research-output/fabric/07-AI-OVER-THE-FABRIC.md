<!-- SPDX-License-Identifier: Apache-2.0 -->
# 07 · AI over the fabric (FB-6): every machine reachable by AI, without one giant attack surface

**Date:** 2026-11-12 · **Workstream:** FB-6 (Tier A; the actuation lab `fb-bridges` is BLOCKED, so the evidence is sources + OneMind's merged code paths) · **Status:** design rules that extend contract §11–§12; no contract edit.
**Serves requirements:** AI-1, AI-2, AI-3, AI-4, AI-5, AI-7, AI-9, N-10, M-2, U-4 · risk RR-06 (prompt injection drives a physical action)

> **Explain it like I'm the founder.** Your AI should be able to *see* every machine and *ask* any of them to do things, but it must never be able to *make* one of them move on its own. So the AI talks to exactly one door per site: that site's gateway. The door knows who the AI is, what it is allowed to touch, and which actions need you. Anything that moves or switches something in the real world creates an approval card on the phone of the person who owns that machine; nothing happens until that person taps approve with their passkey. Machines never open their own AI door, and one site never accepts another site's AI keys. That way, fooling the AI (for example with a poisoned web page) can at most produce a request you can see and refuse.

## 1. Rules (each with its reason)

| # | Rule | Reason / evidence |
|---|---|---|
| A1 | **One AI entry point per site: the site gateway** (MCP, CLI, API, all the same capabilities). Nodes, adapters and robots **never** expose MCP or an AI API of their own. | Every extra door is an attack surface; contract §11 (`/mcp` on the gateway); REC-W11-20 (GUI and agent are equal front doors over the same capabilities) |
| A2 | **Agents are principals, not the owner.** An agent acts as "user ∩ grant", has its own token, never self-approves. | brief 30 D-B9.3, D-B9.6 |
| A3 | **Tokens are audience-bound and never passed through.** A token minted by site A's gateway is rejected by site B and by any adapter. | MCP 2026-07-28: clients send RFC 8707 `resource`, servers MUST validate the audience and "MUST NOT accept or transit any other tokens" [C-FB6-001]; D-B9.2 |
| A4 | **Risk class decides the human step**: `read` auto, `write` owner or standing approval, `sensitive` owner, `destructive` owner + step-up, **`actuate` owner + step-up, never a policy, lab-only until LT-VM-18**. | contract §12.3; mission 01 safety line |
| A5 | **Approval goes to the owner of the target**, not to whoever happens to be signed in: the action carries the target's `site_id` and `node_id`; the gateway routes the card to principals with `can_approve` on that site (household roles) and to their phones. | contract §12.6 roles; NOTIFICATIONS; needed once there are several sites with different owners (ZF-07) |
| A6 | **The card shows the plan, not the agent's words.** Exact normalised parameters, target, expiry, `plan_sha256`; an agent's free text is shown as untrusted. | OWASP LLM01: separate and clearly denote untrusted content; human-in-the-loop for privileged operations [C-FB6-002]; D-B9.6 |
| A7 | **Commands are published only by the gateway, after approval**; adapters execute only gateway-signed, unexpired commands (same envelope as jobs, FABRIC §5.4). | defence in depth: NATS permissions + signature; FABRIC §5.4; contract §12.11 |
| A8 | **Cross-site AI goes gateway to gateway.** A fleet-hub agent asks a site's gateway, which applies its own policy and its own owner's approval. The fleet hub holds no site credentials that can act. | sovereignty (M-1, M-2); no token passthrough [C-FB6-001] |
| A9 | **Audit is local, mirrored read-only.** Each site's hash-chained audit stays on the site; the fleet hub may source a read-only copy for search. | contract §12.9 (`ONEMIND_AUDIT`, deny delete); D-B9.7 |
| A10 | **Data from devices and apps is untrusted input to the model.** Telemetry, device names, camera text and web pages are labelled as data in prompts and never become tool arguments without validation. | OWASP LLM01 indirect injection "from external sources, such as websites or files" [C-FB6-002] |

## 2. How a request flows

```mermaid
sequenceDiagram
  participant AG as AI agent (any MCP client)
  participant FH as Fleet hub gateway (optional)
  participant SG as Site gateway
  participant OP as Owner's phone
  participant AD as Adapter on a node
  participant DV as Device (valve, arm, drone)
  AG->>SG: tools/call irrigation.valve.open (token aud = this site)
  Note over SG: policy: agent ∩ grant; effect = actuate → approval required
  SG->>OP: card: site, node, device, exact params, expiry, plan hash
  OP->>SG: approve (passkey step-up)
  SG->>AD: cmd.irrigation.<node>-<device>.open (signed, expires_at)
  AD->>DV: protocol write (Modbus / MQTT / MAVLink)
  AD->>SG: result + observed state
  SG->>AG: outcome (succeeded / failed / outcome_unknown)
  Note over FH,SG: cross-site: the fleet hub calls SG as its own principal; SG still asks its own owner
```

## 3. What a successful prompt injection can and cannot do

| Attacker gets the agent to… | Result under these rules |
|---|---|
| read every sensor it is granted | possible (reads are the point); limited by the grant and by M-2 data scopes |
| call `actuate` on a valve or arm | an approval card the owner can refuse; never executes on its own (A4, A6) |
| use a token stolen from site A at site B | refused: wrong audience (A3) |
| publish `cmd.` on the bus directly | refused: agents have no NATS credentials; nodes can publish only their own subjects [C-FB3-001] |
| approve its own request | impossible: no self-approval (A2) |
| hide what it is doing | every request, approval and outcome is in the site's hash-chained audit (A9) |

## 4. What competitors do (constraint-matched)

| Product | AI access | Human approval of physical actions? | Constraint fit | Take |
|---|---|---|---|---|
| Viam | remote OAuth MCP server scoped to the user; "Live machine (destructive)" tools can move hardware and act immediately (C-TD-tier-c-robotics-051); in-app assistant stages config changes and asks before shell commands (C-TD-tier-c-robotics-053) | Not for MCP tool calls | Medium (robotics, cloud) | The beat: OneMind puts approval in the gateway, not in the client |
| Foxglove | desktop-only local MCP server with a bearer token; "adds no approval step of its own" (C-TD-tier-c-robotics-028, -029) | No (relies on the client) | Low (visualisation) | Same beat |
| Formant | F3 "agentic" layer over the whole platform (C-TD-tier-c-robotics-011, SECONDARY) | UNVERIFIED | Low (cloud) | — |
| umbrelOS 2 | MCP for managing the box (`docs/umbrel2/mcp-agents.md`) | per that study | High (home OS) | OneMind matches and adds risk classes + passkey step-up |
| Anduril Lattice | Entities and Tasks APIs over gRPC/REST for drones, robots, sensors [C-FB11-011]; proprietary SDK licence [C-FB11-012] | Not described in public overview | Low (defence, proprietary) | Entity/task split is a useful vocabulary |

## 5. Open items

- **ZF-07** who approves in a site shared by several owners (any owner, all owners, or a named operator role).
- **ZF-08** whether a fleet hub may hold standing *read* grants on sites by default.
- Proposed **F-19**: "no device actuation path exists that bypasses the site gateway's approval; tested by a negative test per adapter".
- Lab: `fb-bridges` T3/T4 (actuation blocked until approval; no bypass) runs when the adapter SDK and the `actuate` action type exist (build path P2).

## Glossary

| Term | Meaning |
|---|---|
| MCP | Model Context Protocol: the standard way AI clients call tools |
| Principal | Anyone or anything that can act: a person, a node, an app, an agent |
| Audience binding | A token names the one server it is for; others reject it |
| Step-up | A fresh passkey check at the moment of approval |
| Prompt injection | Text that tricks an AI into doing something its user did not intend |
