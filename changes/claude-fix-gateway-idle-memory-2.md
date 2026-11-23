---
pr: 0
branch: claude/fix-gateway-idle-memory-2
---
Idle gateway memory (issue 849, budget 100 MiB): the NATS monitor reader no longer builds its httpx client at startup, so httpx's TLS trust store (httpcore, certifi, ssl context) loads on the first engine read instead. Measured on Linux in the dev venv: about 1.4 MiB less private memory. The idle-memory test now also proves httpcore and certifi are not imported at startup.
