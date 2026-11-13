---
pr: pending
branch: feat/test-security-2
---
Security attack suite in core/tests/security (runs in the normal core CI), replacing PR 56 under founder decision D1. An authorization matrix reads every route from the live app and checks it against one policy table for 13 principal kinds, so a route without a row fails; install-sandbox escape fixtures cover the known Kubernetes escapes (pod vectors in every workload kind, RBAC, webhooks, CRDs, volumes, Services, kustomize patches and generators); path traversal, header injection, SSRF, oversized bodies, JSON bombs and MCP prompt-injection fixtures are included. Fixes found by the suite: SSRF checks now look inside 6to4 and Teredo addresses and refuse 0.0.0.0/8 and site-local fec0::/10 for non-owners; handler-raised 403s in notifications and monitoring are audited as authz.denied; a deeply nested MCP payload no longer crashes list_nodes with a 500. Known defects are strict xfails with a reason. Guide: core/tests/security/README.md.
