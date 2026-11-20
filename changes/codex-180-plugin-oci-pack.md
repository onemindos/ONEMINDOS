---
pr: pending
branch: codex/180-plugin-oci-pack
---
Adds onemind plugin pack for deterministic unsigned OCI layouts with the documented plugin media types. Blob digests and lengths describe exact config/workload/UI/README bytes; archives normalize metadata and omit unreferenced root files. Existing output paths and outputs inside the source are refused. Trust verification, remote transport and installation follow separately.
