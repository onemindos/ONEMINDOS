---
pr: pending
branch: claude/284-tor-app
---
NET-TOR-01 (#284, PR B2): the gateway path for the Tor app. On install and update the gateway writes ConfigMap `onemind-gateway-path` with the dashboard's address into the app's namespace and opens one egress allowance to exactly that IPv4 address and port, for the `tor-remote-access` app id only (fixed in the gateway, never asked for in a manifest). The LAN stays excluded and no other app gets it. Before this the app's init step stopped for lack of the address. Tests check the ConfigMap, the single /32 allowance, the order before the manifests, and that other apps or an unresolvable address get nothing. Still open on #284: the live test with real `tor`, the owner-approved onion passkey enrolment, and a Tor Browser cookie check.
