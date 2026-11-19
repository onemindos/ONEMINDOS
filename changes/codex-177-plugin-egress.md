---
pr: pending
branch: codex/177-plugin-egress
---
Adds optional DEV-PLG-1 internet egress declarations and offline hostname validation. Wildcard grants cannot cover a public or private suffix, and IP literals, URL components, invalid names and local-only destinations are rejected before install authorization.
