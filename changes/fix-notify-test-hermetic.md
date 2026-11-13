---
pr: pending
branch: fix/notify-test-hermetic
---
Make the notification-channel ownership privacy test independent of public DNS by supplying a globally routable DNS answer and rejecting unexpected HTTP delivery within that test. Preserve all existing ownership assertions and the real SSRF validation and DNS-rebinding tests (contract §12.14).
