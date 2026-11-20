---
pr: pending
branch: codex/180-plugin-owner-keys
---
Owners can request private plugin signing-key enrollment and revocation from Settings. Canonical public-key fingerprints become trusted only after explicit action approval, with a passkey challenge when available. Private PEM is rejected before candidate storage or action auditing. Generated clients expose the API and the dashboard completes action-bound approval challenges.
