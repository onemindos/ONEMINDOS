---
pr: pending
branch: claude/fu-passkey-sign-count
---
A passkey's signature counter is now stored as BIGINT. The WebAuthn counter is an unsigned 32-bit number, which a signed 32-bit PostgreSQL INTEGER cannot hold, so a passkey whose counter passed 2147483647 would have failed its sign-in update. Identity schema step 4 widens the column on PostgreSQL (SQLite needs nothing), and a test pins the column type and the upgrade.
