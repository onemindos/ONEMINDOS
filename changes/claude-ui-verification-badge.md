---
pr: pending
branch: claude/ui-verification-badge
---
Design-system controls for verification levels (D-028, gateway permissions design PR 15). A new VerificationBadge names a level by number and word (L1 Device check, L2 Proven key, L3 Biometric-only key) with a dot count as a shape, and never claims which check the device used, because WebAuthn only reports that the person was verified. HoldToApprove and the approval card can show the level an approval needs (Needs L2 Proven key), and a test pins that a short press or a click never approves.
