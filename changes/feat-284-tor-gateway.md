---
pr: pending
branch: feat/284-tor-gateway
---
The sign-in accepts a box's own version 3 .onion address as its passkey origin over http, so a device that reaches the box through the Tor remote-access app can sign in with the usual rules (the relying party is the exact address, other names still need https). The dashboard-port path for the app and the live Tor test stay open on the issue.
