---
pr: pending
branch: apps/market-batch-7
---
Market batch 7: PrivateBin (encrypted pastebin), non-root with a read-only root filesystem, pinned by tag and digest, probe on `GET /` checked by running the pinned image as the pod's user with all capabilities dropped. Adds its research licence-matrix row (Zlib, read from LICENSE.md at 2.1.1) and a gate test that also covers the existing Mosquitto and LibreChat rows. Its tier stays community until the CI app gate computes one. Glances is skipped: it needs host access.
