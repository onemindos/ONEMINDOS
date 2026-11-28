---
pr: 1287
branch: claude/box-export-import
---
Box export and import, phase 1 of 8: the design (docs/architecture/BOX-EXPORT-IMPORT.md, founder note 16), the versioned bundle manifest schema (sdk/schema/onemind.box-bundle.schema.json) and core/onemind_core/boxbundle with layer a (box name, time zone, update policy, backup destinations without credentials, content tier): collect, check, a per-field import preview and a safe write-back, with a round-trip test from one box to an empty one (box settings and update policy match; destinations stay for the owner). Review fixes: a destination's config is checked against a per-kind allow-list in the schema, unknown fields are refused at the current format version and only set aside from a newer one (a destination config key included), apply writes in one transaction, and the design says the printed kit at the box still imports when an L2 key is lost. No route yet.

Round-one fixes omit credential-bearing backup addresses, validate the whole manifest before skipping newer layers, and find the schema on the Debian appliance. The preview shows backup choice and primary destination changes for the owner. Import shares the gateway's AI schedule validation, preserves concurrent backup changes, and can apply an update policy in the same transaction as its selected maintenance window.

The [founder's 1.0 scope](https://github.com/onemindos/ONEMINDOS/pull/1287#issuecomment-7234926382) includes both the encrypted recovery bundle and the secret-free YAML config-as-code export, with expanded settings coverage. Refs #1285.
