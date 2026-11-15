---
pr: pending
branch: fix/160-gateway-guards
---
CORE-SEC-9 (#160): enforce the gateway body limit for unknown-length requests even without transfer-encoding, and add canonical security headers to non-sensitive unhandled 500 responses. Real gateway regressions cover HTTP/1.1 and HTTP/2 ASGI bodies, boundary replay, exception propagation and already-started streams; existing rate-limit protections remain unchanged.
