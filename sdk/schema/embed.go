// SPDX-License-Identifier: Apache-2.0

// Package schema embeds the manifest contract and the NATS subject tree for offline validation on box and CI.
package schema

import _ "embed"

// App is the same JSON Schema consumed by sdk/tools/validate-apps.
//
//go:embed onemind.app.schema.json
var App string

// WidgetTemplates is the standalone typed-widget data contract for host consumers.
//
//go:embed widget-templates.schema.json
var WidgetTemplates string

// Subjects is the one NATS subject tree (issue #600): kinds, publishers, streams, envelopes, mappings.
//
//go:embed onemind.subjects.json
var Subjects string

// Datapoint is the onemind.datapoint/v1 envelope of the asset, intel, metric and layer subjects.
//
//go:embed onemind.datapoint.schema.json
var Datapoint string

// Event is the onemind.event/v1 envelope (contract section 12.8), the same on SSE and NATS.
//
//go:embed onemind.event.schema.json
var Event string
