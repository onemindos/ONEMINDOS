---
pr: 397
branch: codex/177-plugin-ui-bundle
---
Checks unpacked DEV-PLG-1 UI bundles for safe regular files, offline settings schemas and bounded markup. The shared directory validator rejects UI symlinks, missing files, remote or inline scripts, inline event handlers and base or srcdoc markup. Local script sources must stay inside the UI tree; runtime sandboxing and artifact verification remain separate gates. Tool schema declarations explicitly require the 2020-12 dialect.
