---
pr: 958
branch: claude/roots-agent-browser
---
Agent browser, part 1 of 2 (#694): the rules and the box an agent's browser runs in, not yet mounted. URL rules (https on port 443, public DNS names only, no user@, no private suffixes), allowlist matching (example.org or *.example.org), and the steps that always need a one-time owner approval even on an approved site: sign-in pages, payment pages, every form submit and every download. A step approval is bound by plan hash to the exact URL the browser is sent, query included, and the card shows the query. The browser pod is sealed (in-memory profile, no service account token, no shared volume, no DevTools port, a lifetime deadline) behind a default-deny NetworkPolicy whose only way out is a CONNECT proxy in the gateway that never dials a private address. The service and the /v1/agent-browser routes come in part 2.
