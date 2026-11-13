---
pr: 56
branch: feat/test-security
---
Repair the TypeScript live gateway conformance fixture to exercise a lost-response retry of one logical action request using the existing fetch seam. Cross a full second boundary, require identical serialized payload and expiry on both attempts and one request/dispatch in the audit trail, and prove a same-key request with changed expiry still receives 409. Preserve agent refusal, owner approval, event-stream and audit verification assertions without changing SDK APIs or server idempotency.
