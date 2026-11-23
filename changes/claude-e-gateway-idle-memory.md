---
pr: 922
branch: claude/e-gateway-idle-memory
---
Gateway idle memory back under its 100 MiB budget (issue 849): both gateway units cap glibc malloc arenas (MALLOC_ARENA_MAX=2), and py_webauthn loads on the first passkey ceremony instead of at startup. A Linux probe of the idle gateway with TLS on went from 114 to 100 MiB of private memory in the dev venv.
