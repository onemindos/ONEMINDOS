---
pr: pending
branch: claude/fnd-manifest-v1-typeguard
---
Manifest v1 follow-up: a manifest with a map or list where a name belongs (a host, a provider or provider id, a job or action tool, an emit name, a tool name or a map layer id) is now refused by the schema with a named error instead of crashing the gateway's validator. The cross-field rules run only on a schema-valid manifest, as in Go, and never use an unchecked value as a key, so one bad apps/ folder or community source manifest no longer stops the catalog from loading or hides the other apps. Eight new golden cases hold Python and Go to the same verdict.
