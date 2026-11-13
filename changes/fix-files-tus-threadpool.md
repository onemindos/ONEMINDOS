---
pr: pending
branch: fix/files-tus-threadpool
---
Files uploads: `PATCH /v1/files/uploads/{id}` now writes each chunk (and rolls back a failed one) in a worker thread instead of inside the async handler, so a large or slow disk write no longer freezes the gateway event loop for every other request. Offset checks, free-space checks, path confinement and the one-writer-per-upload busy mark are unchanged, and the rollback is shielded from request cancellation. Tests use a slow writer to show other requests are served mid-write, that a concurrent PATCH of the same upload gets 409, and that different uploads proceed side by side.
