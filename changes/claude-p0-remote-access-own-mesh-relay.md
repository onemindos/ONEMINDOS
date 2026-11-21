---
pr: pending
branch: claude/p0-remote-access-own-mesh-relay
---
First slice of remote access with your own relay and no outside service: the relay role (`onemindd relay`, with init, serve and status) that passes only encrypted traffic for exact named routes and closes everything else, the owner's relay address carried in the join bundle in its own field (no client uses it yet, so away access does not work yet), and a plain message in the mesh view when no relay is set up. Design note and follow-ups in docs/learning/remote-access-relay.md.
