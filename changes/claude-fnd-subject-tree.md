---
pr: pending
branch: claude/fnd-subject-tree
---
One NATS subject tree (Refs #600): sdk/schema/onemind.subjects.json registers the grammar onemind.<kind>.<scope>.<id>.<field> with eleven kinds (node, audit, event, alert, asset, intel, metric, plugin, layer, notification, request), each with its publishers, stream, retention and envelope schema (new onemind.datapoint/v1 with value, unit, time, quality, source, licence, sequence and a WGS-84 position that refuses 0,0, and onemind.event/v1). The gateway checks subjects against it (GET /v1/subjects and GET /v1/subjects/check answer with a reason), make lint fails on any subject in code that is not registered, and Go embeds the same file. Contract 12.9 is reconciled and carries the mapping table from the plugin SDK and cluster grammars; app spec.streams now land under onemind.plugin.<app_id>. and onemind.app is a reserved, refused kind, so no plugin can name a core subject.
