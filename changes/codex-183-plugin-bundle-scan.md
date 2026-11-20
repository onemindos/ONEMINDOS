---
pr: pending
branch: codex/183-plugin-bundle-scan
---
The app gate scans frozen unpacked plugin files with ClamAV, including UI assets outside workload images. Malware blocks both the gate and computed tier. Scanner failures, symlinks, special files and oversized bundles fail closed. OCI/referrer verification and runtime scan-attestation binding remain dependent on plugin packaging.
