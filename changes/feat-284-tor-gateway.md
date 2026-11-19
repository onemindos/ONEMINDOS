---
pr: pending
branch: feat/284-tor-gateway
---
The sign-in accepts a well-formed version 3 .onion address as its passkey origin over http, so a passkey made on the home network is not mixed up with Tor. Over Tor an owner signs in with the password. Registering a passkey over an onion address is refused (403, passkey_enrolment_unavailable_on_onion), because an onion-bound passkey cannot work on the home network and, once any owner has a passkey, owner approvals need one: it would lock approvals at home. Add passkeys on the home network. An owner-approved onion enrolment is a follow-up on #284. The dashboard-port path for the app and the live Tor test stay open on the issue.
