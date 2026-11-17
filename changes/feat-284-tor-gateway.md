---
pr: pending
branch: feat/284-tor-gateway
---
The sign-in accepts a well-formed version 3 .onion address as its passkey origin over http. Known limit: a passkey works only on the address it was created for, so over Tor an owner signs in with the password; the LAN passkey does not work there, and adding an onion passkey needs a passkey sign-in on that same address, which is not possible yet. Owner approvals that need a passkey therefore do not work over Tor until a follow-up adds a safe enrolment path. The dashboard-port path for the app and the live Tor test stay open on the issue.
