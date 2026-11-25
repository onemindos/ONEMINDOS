---
pr: 807
branch: feat/machine-media-upload
---
An owner can attach a completed Home upload to a machine creation request. After approval the gateway verifies the exact bytes, streams the installer, disk or drivers to CDI, and returns each volume’s SHA-256. The machine stays halted until its media is ready. Refs #689.
