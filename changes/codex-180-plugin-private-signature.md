---
pr: pending
branch: codex/180-plugin-private-signature
---
Plugin inspection can check a detached artifact signature against an explicitly supplied candidate public key, using the existing Sigstore crypto verifier. Invalid or unpaired proof inputs fail closed. A valid signature reports the candidate key fingerprint while overall verification remains false until enrollment, scan and revocation policy are satisfied.
