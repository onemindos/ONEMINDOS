---
pr: 390
branch: codex/177-plugin-api-compat
---
Adds offline validation of a plugin compatibility range against a caller-supplied box API level. The onemind plugin validate command accepts --api-level; incompatible bundles fail validation without contacting the network or changing the box.
