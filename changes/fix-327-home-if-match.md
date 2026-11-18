---
pr: pending
branch: fix/327-home-if-match
---
Fix #327: declare the required If-Match header on PUT /v1/me/home in OpenAPI, preserving the existing 428 missing-header and 412 stale-tag responses. Regenerate the SDKs and cover the required header and error envelopes with a contract regression test alongside the existing write-precondition tests. Scope the fuzz harness's missing-header 428 and schema-valid stale-tag 412 expectations to me.home.save only; retain global checks and cover the generated configuration with a failing-before-fix regression.
