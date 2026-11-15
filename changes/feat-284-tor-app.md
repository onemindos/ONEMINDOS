---
pr: pending
branch: feat/284-tor-app
---
Remote access over Tor arrives as an optional Market app (NET-TOR-01, D-014, #284 part 1): a Tor onion service for the OneMind dashboard only, for homes behind CGNAT, with no server of ours. Only devices the owner adds can reach the address (Tor client authorization, one key per device, shown once and never stored), and an empty device list stays closed. Removing a device restarts Tor so an open connection is cut at once. Tor here is never a proxy, relay or exit (SocksPort 0), and the app's NetworkPolicy has no LAN egress. The owner page answers only the owner. The gateway path to the dashboard comes in the next part, so until then the app stops with a clear message instead of pretending to work.
