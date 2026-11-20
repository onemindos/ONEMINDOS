---
pr: 419
branch: codex/180-plugin-oci-inspect
---
Adds exact-digest OCI plugin inspection with blob size/hash checks and bounded extraction into a private temporary directory. Archive traversal, links, special files, duplicate/reserved entries and trailing data fail closed. The extracted bundle passes the shared validator; the CLI explicitly reports that integrity does not establish publisher trust.
