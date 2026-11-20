---
pr: pending
branch: codex/180-plugin-sign
---
The plugin sign command signs a validated local OCI artifact at an exact SHA-256 digest using an existing PKCS8 private key. It requires a regular owner-only key file, refuses weak keys and existing output files, and writes a detached base64 signature compatible with plugin inspect. Signing grants neither trust nor installation approval.
