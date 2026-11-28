---
pr: 1185
branch: claude/ui-verification-badge
---
Design-system controls for verification levels (D-028, gateway permissions design PR 15). A new VerificationBadge names a level by number and word (L1 Device check, L2 Proven key, L3 Biometric-only key) with a dot count as a shape, and never claims which check the device used, because WebAuthn only reports that the person was verified. HoldToApprove and the approval card show the level an approval needs (Needs L2 Proven key); the dashboard's Approvals cards take it from the request's required_level, so it shows before the owner tries. A test pins that a short press or a click never approves.
