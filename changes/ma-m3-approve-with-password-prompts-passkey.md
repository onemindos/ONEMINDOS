---
pr: 1302
branch: ma/m3-approve-with-password-prompts-passkey
---
Approving while signed in with a password no longer fails silently: when the hub asks for a passkey and the browser did not produce one, Approvals opens a "Use your passkey to approve" prompt with a button (Refs #1232, Refs #234), and an owner with no passkey gets a plain-words message saying to add one in Account and security.
