---
pr: 453
branch: codex/180-plugin-owner-trust-fold
---
Ports owner-approved plugin signing-key enrollment and revocation onto the consolidated gateway stack. Canonical public-key fingerprints activate only after approved actions and active passkey step-up. The Settings UI uses generated API types and preserves current dashboard action validation and array-response checks. Private key input is rejected before action storage or auditing.
A signing-key revocation is final for every proposal filed before it, so a stale approved proposal cannot re-activate a key revoked as compromised, and a proposal may stay open for at most 24 hours.
