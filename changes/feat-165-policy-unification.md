---
pr: pending
branch: feat/165-policy-unification
---
Refs #165 (partial): agent REST catalog visibility now reuses the same policy resolver and visibility predicate as MCP instead of maintaining a separate sensitive-category rule. HTTP parity regressions cover legacy metadata, health defaults, explicit policies and invalid values, owner display access, and central category-policy changes. Provider/model dispatch, consent, local routing, schema and app-detail UI remain outside this slice.
