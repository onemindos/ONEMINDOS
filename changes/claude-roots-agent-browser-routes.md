---
pr: 997
branch: claude/roots-agent-browser-routes
---
Agent browser, part 2 of 2 (#694): AI agents can open web pages, but only on sites the owner approved. A site joins an agent's allowlist only through an agentbrowser.site.allow action that the owner approves (plan hash over agent and site). Each session starts a fresh sealed browser pod whose only way out is the gateway's egress proxy, which checks the allowlist on every connection. Sign-in pages, payment pages, every form submit and every download need a one-time agentbrowser.step approval bound to the exact URL, query included. Every visit is audited with the URL minus its query. Sessions have a page budget, a lifetime and a per-agent cap, and the agent kill switch ends them all at once. Routes are under /v1/agent-browser, for the owner and AI agents only. The feature is off until a browser image pinned by digest is configured (ONEMIND_AGENTBROWSER_ENABLED, ONEMIND_AGENTBROWSER_IMAGE).
