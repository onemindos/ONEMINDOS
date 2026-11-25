---
pr: 1130
branch: claude/p09-fw-view
---
Firewall: view (P-09 part 1, refs #239). `GET /v1/network/firewall` (owner only, read only) returns the box's live nftables rules in a checked, structured form: the host service runs `nft -j list ruleset` and the gateway re-checks every field, works out who each rule lets in (this box, the mesh, the apps on it, the home network, or any address) and writes one plain sentence per rule. It answers the headline question directly (`exposure`: never the internet, open to the internet, or not protected) and lists any service open to any address. The Network screen has a new Firewall section, and `onemind firewall show` prints the same words. An unreadable firewall is reported as unknown, never as safe. Nothing can be changed yet: allow rules with automatic revert are part 2 (the API and CLI carry `editable: false` and have no write command).
