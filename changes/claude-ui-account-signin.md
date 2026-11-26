---
pr: pending
branch: claude/ui-account-signin
---
Settings > Account and security gains a Password card (change it with the current password; other devices are signed out) and an Authenticator code card (set up with a QR code and key shown once, confirm with a 6-digit code, turn off with the password), and the CLI gains `onemind account show`, `account password` and `account totp setup`, `confirm` and `disable` (passwords asked without echo or read from --password-stdin, --json throughout). Both read the new `GET /v1/auth/methods` (password, authenticator code, passkeys) and the TOTP setup answer now has a typed schema. Following D-030, passkeys come first: the screen and CLI say that new people should use passkeys only and that the code is a fallback for people who already use a password; a passkey user sees the setup only inside a closed disclosure. The Security overview row now reads the real state instead of always showing Unknown. UI parity report row M1 (dashboard and CLI).
