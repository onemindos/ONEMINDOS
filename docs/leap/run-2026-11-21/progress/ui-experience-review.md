<!-- SPDX-License-Identifier: Apache-2.0 -->
# UI and experience review

**Part:** clients and core. **State:** review done. The sprint list below is not yet filed as issues.

**Verdict:** polished on the surface, but screens and backend do not match yet. The D-016 desktop, Market Discover, the app trust card, the audit chain and the first-run wizard are good.

## Three problems found

1. **Screens say shipped features are "coming".** Home widgets, `Coming.tsx`, Settings and the Nodes empty state do this even though the files, photos, secrets, network, OS update and backup routes are mounted. The desktop calls `/v1/os/status`, which the gateway does not serve.
2. **The approval loop breaks on the dashboard.** Approve sends no body. Passkey step-up is on by default, so once an owner adds a passkey, dashboard approvals fail. No client sends sealed install secrets.
3. **Family safety is not enforced in the UI.** Child and Guest get the owner's Home, and role filtering is incomplete.

## Principles adopted for the next UI sprint

- Real or honest: every widget reads a live route, otherwise it says "not on this box".
- Every change is a request with a plain-language plan; JSON goes behind Advanced.
- Screens are designed per role; never show a button that fails.
- Phone parity for the core loop.
- One source of truth through the generated SDK.

## P0 sprint items

- Approvals that work: approve-options, passkey step-up, approve with `plan_sha256`; a sealed-secrets form on dashboard and phone; plain-language plan.
- Delete stale "coming" text and wire the mounted routes.
- Role-shaped Home and screens.

## What is left

File the issues, order them, and build. Related PRs: #480 (approve body), #482, #463.
