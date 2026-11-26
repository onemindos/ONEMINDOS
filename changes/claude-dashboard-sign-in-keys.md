---
pr: 1186
branch: claude/dashboard-sign-in-keys
---
Settings, Security, Sign-in keys in the dashboard (D-028, gateway permissions design PR 17). Each passkey and security key shows its verification level as a badge (L1 Device check or L2 Proven key), its model, whether it syncs between devices or stays on one, and, for a key that can only reach L1, the plain reason. Adding a key runs the browser's passkey ceremony; once you hold a proven key, the dashboard asks it to vouch for the new one with a step-up bound to that change. A two-key nudge asks for two proven keys so losing one is never a lock-out, says when high-risk approvals still accept a Device check key, and says your files never depend on a proven key. Owners see the trusted key models, can stop trusting one at once, and can ask to trust another, which waits in Approvals for a proven key. The Security overview now counts registered and proven keys and links here. All calls go through @onemind/sdk to real gateway routes.
