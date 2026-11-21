---
pr: pending
branch: claude/polish-market-signin-copy
---
Colour-independent polish for family screens (Refs #440). Sign-in is a translucent card over the default wallpaper with the passkey as the one primary button, the account and token forms behind a single Other ways to sign in link (open by default when the browser has no passkeys), and the demo note as a small dismissible chip. Settings and About lose their developer copy; About becomes a device card with name, version, uptime, memory, a storage bar and Log out, with the rest under Technical details. The Market category row hides categories that have no apps. The app request card says what happened in one plain line, with the ledger state under Technical details.

Fix round: Approvals keeps spec ids and the API call behind a collapsed Technical details and pins Approve and Deny in a bar above the dock on phones (48 px buttons, safe-area padding); the phone shell clips sideways overflow; disclosures show a chevron; the About card says when storage and memory will appear; sign-in shows the box name through the new open GET /v1/instance/name, which serves the name and nothing else.
