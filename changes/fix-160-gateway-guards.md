---
pr: pending
branch: fix/160-gateway-guards
---
Part of CORE-SEC-9 (#160): add canonical security headers to non-sensitive unhandled 500 responses through the existing gateway exception-handler wiring. Dedicated real-gateway regressions cover exception-detail redaction, propagation for server logging and already-started streams. Body processing and rate limits remain unchanged; unknown-length body-limit integration with resumable uploads remains unresolved under #160.
