---
pr: pending
branch: claude/sec-first-boot-token-retire
---
The first-boot owner token is now break-glass as SECURITY.md section 3.2 says. First boot marks it retire_on_setup in the gateway tokens file, and once the first owner account exists the gateway answers 401 for it on the API and no longer lists it, so a token sniffed from the wizard page or the console stops being a permanent owner credential. The file entry stays, so the rescue console still signs in with it (D-008).
