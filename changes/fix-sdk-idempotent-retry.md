---
pr: pending
branch: fix/sdk-idempotent-retry
---
SDK fix (issue 89): the Go, TypeScript and Python SDKs now compute expires_at once per caller-supplied idempotency key and reuse it on later actions.request calls from the same client, so a retry that lands in a later second no longer gets a 409 from the gateway. Calls without a key are unchanged. The live conformance tests now replay after a 1.2 s gap, and each SDK has a unit test with a moving hub clock.
