---
pr: pending
branch: codex/177-plugin-bundle-paths
---
Extends DEV-PLG-1 validation to unpacked plugin bundles: required files and directories must exist, declared paths cannot escape the bundle, and symlinks or special files are rejected. The CLI uses the same directory validator available to box tooling and CI.
