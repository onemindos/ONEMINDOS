---
pr: 1330
branch: claude/recovery-bundle-crypto
---
Adds offline recovery bundle encryption to the owner's hybrid kit key and an optional Argon2id passphrase. A dedicated Ed25519 export key certified by the owner's fabric root authenticates the bundle before it opens.
