---
pr: pending
branch: fix/160-streaming-body-limit
---
Count request bytes as gateway routes consume them, including bodies without framing headers, and reject overflow with the existing 413 error and security headers without eagerly buffering uploads or delaying route-owned read deadlines. Preserve the 256 KiB per-PATCH cap and correct the photo disconnect regression to use within-cap requests. Add real-gateway ASGI boundary, offset, disconnect and stalled-read coverage. Part of #160; full-suite and final review acceptance remain outstanding.
