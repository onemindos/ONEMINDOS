---
pr: pending
branch: codex/178-plugin-credentials
---
Approved plugin installs issue a hashed, scoped installation credential and deliver its bearer only through the executor's Secret channel. The installed declaration and Secret name persist independently of mutable catalog data. Plugin and agent identities cannot coexist, API rotation cannot expose managed tokens, and unsuccessful installs retire their credentials.
