---
pr: pending
branch: claude/ui-approvals-passkey-secrets
---
Approvals that work end to end in the dashboard. Approving now asks the gateway for a challenge bound to the action and its plan, refuses if the plan on screen is not the plan being signed, signs with the owner's passkey (every approval once the owner has one, and on demand when the gateway asks for step-up), and sends the plan hash with the approval, so an owner who adds a passkey is no longer locked out of approving. An app install that declares owner-typed secrets opens a form whose values are sealed in the browser to the box public key and sent with the approval, never as plain text. The gateway plan is shown as plain effects (data kept or deleted, network paths opened, warnings) with the raw plan under Advanced, and the developer copy about CORE-SEC-2 is gone. The mobile sealed-secrets form and the requester reason are not part of this first slice.
