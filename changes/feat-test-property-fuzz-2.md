---
pr: pending
branch: feat/test-property-fuzz-2
---
Property tests (Hypothesis), API fuzzing (Schemathesis) and Go fuzz targets, replacing PR 55 under founder decision D1 because its five Legacy commits are unsigned. Adds action, audit, licence, sandbox and heartbeat properties, a bounded api-fuzz workflow and go-fuzz workflow, and the fixes they found: hidden MCP methods authenticate before their 405, out-of-range expiry is refused instead of a 500, malformed policy profiles are refused, and Schemathesis body-limit status adaptation is scoped to the reproduced token and app-access operations. The live TypeScript conformance fixture now retries one accepted request after a lost response across a second boundary and requires byte-identical expiry.
