---
pr: 1287
branch: claude/box-export-import
---
Box export and import, phase 1 of 8: the design (docs/architecture/BOX-EXPORT-IMPORT.md, founder note 16), the versioned bundle manifest schema (sdk/schema/onemind.box-bundle.schema.json) and core/onemind_core/boxbundle with layer a (box name, time zone, update policy, backup destinations without credentials, content tier): collect, check, a per-field import preview and a safe write-back, with a round-trip test from one box to an empty one (box settings and update policy match; destinations stay for the owner). Review fixes: a destination's config is checked against a per-kind allow-list in the schema, unknown fields are refused at the current format version and only set aside from a newer one (a destination config key included), apply writes in one transaction, and the design says the printed kit at the box still imports when an L2 key is lost. No route yet.
