---
pr: pending
branch: w0/core3-domains
status_rows:
  - NET-DOM-01 | in-review | properties test knows the switched-off domains answer
---
The API property test now accepts the 503 answer with reason domains_disabled for a switched-off bring-your-own-domain feature, the same way it already accepts backups_disabled. The routes already document 503 in the OpenAPI spec, so the spec and SDK do not change.
