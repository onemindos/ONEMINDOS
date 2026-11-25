---
pr: 1051
branch: bundle/s-767
---
Add a local approval practice card and a timed Hold to approve control. Send elapsed time and the reviewed plan fingerprint through the existing passkey approval flow A hold no longer forces a passkey: only physical actions need one, and the gateway asks for it. A destructive action with no plan can still be held and approved (Refs #767).
