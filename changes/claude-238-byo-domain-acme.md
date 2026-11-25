---
pr: pending
branch: claude/238-byo-domain-acme
---
Bring your own domain, off by default (ONEMIND_DOMAINS_ENABLED=1). The owner registers a domain, proves it with a DNS TXT record the box checks itself, then requests and separately approves each app name such as app.example.org. Admin names (hub, control, admin, api) can never be handed out. The ACME account key is created on the box with 0600 permissions and never leaves it. Approving records the decision only; certificate issuance, serving the name and the dynamic DNS updater come next.
