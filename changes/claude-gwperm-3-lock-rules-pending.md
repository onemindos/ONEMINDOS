---
pr: pending
branch: claude/gwperm-3-lock-rules-pending
---
The standing-approval rules list is now the owner's alone: an agent, plugin, guest or child that asks for GET /v1/approval-policies gets 403 with an authz.denied audit line, so an agent can no longer read the rules to shape its requests to fit one. A request nobody decides can no longer wait for ever: expires_at is refused past 72 hours for agents, automations, nodes and plugins and past 7 days for a person, on every filing path (lifecycle, configure, feature and handler types). Gateway permissions design PR 3 (gaps 3 and 9, review item 15). No setting changes here, so no new dashboard or CLI control; the Settings and CLI screens for the rules come in design PRs 14 and 16.
Fix round: an automation rule's expires_s is now capped at 72 hours (it allowed 7 days, which the gateway then refused on every fire); a rule already stored with a longer value is clamped to 72 hours when it fires. Not done: requests already pending with a far-future expires_at, filed before this ships, stay pending until they expire or are decided; a one-time clamp can follow if wanted.
