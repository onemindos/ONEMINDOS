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

// Services is the services registry contract (os/.../usr/lib/onemind/services.yaml, #623),
// read by `onemindd host serve` (internal/svcregistry).
//
//go:embed onemind.services.schema.json
var Services string

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

// Message, RadioStatus, LoraJob, MessageEvent and MessageImport are the Messages contract (#855):
// the stored message, the radio's own report in physical units, the LoRa kinds of the signed job
// envelope that onemindd verifies (#740), the ids-only message events and the direct-mode import body.
//
//go:embed onemind.message.schema.json
var Message string

//go:embed onemind.radio.status.schema.json
var RadioStatus string

//go:embed onemind.job.lora.schema.json
var LoraJob string

//go:embed onemind.message.event.schema.json
var MessageEvent string

//go:embed onemind.message.import.schema.json
var MessageImport string
