---
pr: pending
branch: feat/273-rescue-terminal
---
The rescue console gets an owner-only web terminal, built but switched off: a root shell on a pseudo-terminal behind the owner token, a switch file (`onemindd rescue terminal enable`), a fresh-passkey check and a tamper-evident audit chain that records each session start and end (not keystrokes). Passkeys do not exist yet, so every start is refused until they do, as D-014 requires. Agent and non-owner tokens get 403. A threat-model note is in docs/security.
