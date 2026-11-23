---
pr: 914
branch: claude/ab2-openapi-lint
---
A contract lint for the committed OpenAPI spec (sdk/tools/openapi-lint, run by make -C sdk check-stale and make -C sdk contract-lint). Every route must name a declared security scheme or sit on a short reviewed public list, every secured route must list scopes, list routes must use the one paging shape of contract §12.1 (limit, cursor, Link rel=next), every error response must be ErrorBody, and every POST, PUT, PATCH and DELETE must take an Idempotency-Key header or sit on a reviewed exception list. The 387 violations in today's spec are in a checked-in baseline with an owner each, so the lint fails only on a new violation or on a baseline line that a fix made stale. It reads the spec only and changes no route.
