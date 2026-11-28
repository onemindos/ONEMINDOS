---
pr: 448
branch: codex/183-plugin-ci-gate
---
Consolidates shared box-validator integration into app CI and bounded malware scanning of unpacked plugin UI and bundle bytes. Missing or failed validators and scanners fail closed. CI installs the real ClamAV engine so the EICAR test executes. No scan of mutable source is treated as trust in a signed artifact. A manifests/ folder without a declared spec.manifests is refused by the shared directory validator, and the gateway no longer falls back to it for extension apps, so nothing unscanned can be rendered.
