---
pr: pending
branch: codex/183-plugin-ci-gate
---
Consolidates shared box-validator integration into app CI and bounded malware scanning of unpacked plugin UI and bundle bytes. Missing or failed validators and scanners fail closed. CI installs the real ClamAV engine so the EICAR test executes. No scan of mutable source is treated as trust in a signed artifact.
