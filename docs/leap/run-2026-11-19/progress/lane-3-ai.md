<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lane 3: AI

Founder-directed order (2026-11-19): #240, #169, #168, #166, #167, #128, #247, #246.
Ties to AIG-05 (#240), the AI Gateway workstream and D-007 (Debian 13).

## Draft

- #240 claimed by Codex on `codex/240-model-manager`. Claim-only draft; implementation has not started.
- Plan: inspect existing model, hardware, action and backup interfaces; implement an approved catalogue with artifact sizes and RAM/VRAM requirements; derive fit from detected hardware; implement owner-approved downloads with progress, disk reservation/budget checks and safe removal; expose through mounted gateway routes and the generated SDK, with a reachable owner interface.
- Verification: fit and unknown-hardware behavior, disk exhaustion/concurrent downloads, interrupted or invalid downloads, removal safety, authorization and agent approval refusal; touched gateway/SDK/interface suites, hygiene and secret scanning.
- Dependencies: #166 (router) and #164 (model backups) are open. Keep integration requirements explicit; do not claim end-to-end completion until verified.

## Next

- #169: MCP revision 2026-07-28; verify the published specification before implementation.
- #167, #128, #247, #246 follow in the founder-directed order, subject to dependencies.

## Blocked

- #168 and #166: wait until #165 is merged. Checked using `gh issue view 165 -R onemindos/ONEMINDOS`: OPEN on 2026-11-19.

## Guardrails

- Never edit `core/onemind_core/ai_policy.py`; call its existing interfaces.
- AI never actuates without owner approval.
- This is the only progress/documentation file this lane updates; do not change other lane progress or shared run documents.
- One issue per PR; gate performs review and merging.
