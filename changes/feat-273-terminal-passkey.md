---
pr: 346
branch: feat/273-terminal-passkey
---
The rescue web terminal now opens only after a fresh owner passkey assertion: the console asks the gateway on loopback for a single-use challenge, the browser signs it, the gateway verifies it with its own WebAuthn code and audits it, and only then is a shell started. Each shell needs a new touch, and the open session is tied to the owner token that started it. The rescue unit allows a pty and its audit file and nothing more, pinned by a test. Depends on the terminal PR. The console keeps the one capability it needs (CAP_DAC_READ_SEARCH, from CORE-UPDATE-9), while the terminal's shell starts through `onemindd rescue-shell`, which drops every capability under no_new_privs before exec, so the shell holds none.
