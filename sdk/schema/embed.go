// SPDX-License-Identifier: Apache-2.0

// Package schema embeds the manifest contract for offline validation on box and CI.
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
