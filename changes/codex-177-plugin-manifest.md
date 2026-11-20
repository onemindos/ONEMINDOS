---
pr: 387
branch: codex/177-plugin-manifest
---
Adds the first DEV-PLG-1 slice: optional App tool extensions, restricted plugin permissions, backend and compatibility declarations, plus an offline Go validator exposed as onemind plugin validate. Unknown extension types fail closed. Artifact verification and owner approval remain required separately.

Image and compose Go builders include the embedded schema package required by the validator.
