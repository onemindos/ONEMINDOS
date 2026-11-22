// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestWidgetDataExamples(t *testing.T) {
	const timestamp = `"observed_at":"2026-11-12T10:00:00Z"`
	examples := []string{
		`{"template":"stat","value":"Hello, Ada","label":"Greeting","trend":null,` + timestamp + `}`,
		`{"template":"stat","value":42,"label":"Count",` + timestamp + `}`,
		`{"template":"list","items":[{"title":"beelink","subtitle":"online","status":"ok"}],` + timestamp + `}`,
		`{"template":"list","items":[],` + timestamp + `}`,
		`{"template":"progress","value":0.42,"label":"Backup",` + timestamp + `}`,
		`{"template":"progress","value":0,"label":"Backup",` + timestamp + `}`,
		`{"template":"progress","value":1,"label":"Backup",` + timestamp + `}`,
	}
	for _, state := range []string{"ok", "warn", "error", "unknown"} {
		examples = append(examples, `{"template":"status","state":"`+state+`","text":"All checks pass",`+timestamp+`}`)
	}
	for _, example := range examples {
		if err := WidgetData([]byte(example)); err != nil {
			t.Fatalf("%s: %v", example, err)
		}
	}
	// Staleness is a display decision: old but valid timestamps remain valid data.
	if err := WidgetData([]byte(strings.ReplaceAll(examples[0], "2026-11-12T10:00:00Z", "2000-01-01T00:00:00Z"))); err != nil {
		t.Fatal(err)
	}
}

func TestWidgetDataRejectsMalformedResults(t *testing.T) {
	base := map[string]any{"template": "stat", "value": "Hello, Ada", "label": "Greeting", "observed_at": "2026-11-12T10:00:00Z"}
	tests := []struct {
		name   string
		mutate func(map[string]any)
	}{
		{"missing timestamp", func(v map[string]any) { delete(v, "observed_at") }},
		{"bad timestamp", func(v map[string]any) { v["observed_at"] = "yesterday" }},
		{"date without time", func(v map[string]any) { v["observed_at"] = "2026-11-12" }},
		{"unknown template", func(v map[string]any) { v["template"] = "html" }},
		{"missing label", func(v map[string]any) { delete(v, "label") }},
		{"bad value type", func(v map[string]any) { v["value"] = true }},
		{"numeric trend unspecified", func(v map[string]any) { v["trend"] = 0.2 }},
		{"image URL", func(v map[string]any) { v["image_url"] = "https://example.com/image.png" }},
		{"URL fetch target", func(v map[string]any) { v["url"] = "https://example.com/data" }},
		{"HTML extension", func(v map[string]any) { v["html"] = "<script>alert(1)</script>" }},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			v := map[string]any{}
			for k, x := range base {
				v[k] = x
			}
			tt.mutate(v)
			b, _ := json.Marshal(v)
			if err := WidgetData(b); err == nil {
				t.Fatal("accepted malformed result")
			}
		})
	}
	invalid := []string{
		`{"template":"progress","value":-0.1,"label":"Backup","observed_at":"2026-11-12T10:00:00Z"}`,
		`{"template":"progress","value":1.1,"label":"Backup","observed_at":"2026-11-12T10:00:00Z"}`,
		`{"template":"progress","value":"0.5","label":"Backup","observed_at":"2026-11-12T10:00:00Z"}`,
		`{"template":"status","state":"healthy","text":"OK","observed_at":"2026-11-12T10:00:00Z"}`,
		`{"template":"list","items":[{"title":"box","subtitle":"online","status":"ok","url":"https://example.com"}],"observed_at":"2026-11-12T10:00:00Z"}`,
		`{"template":"list","items":[{"title":42,"subtitle":"online","status":"ok"}],"observed_at":"2026-11-12T10:00:00Z"}`,
		`{"template":"list","items":{},"observed_at":"2026-11-12T10:00:00Z"}`,
		`{} {}`, `null`, `[]`,
	}
	for _, value := range invalid {
		if err := WidgetData([]byte(value)); err == nil {
			t.Fatalf("accepted %s", value)
		}
	}
	if err := WidgetData(make([]byte, MaxManifestBytes+1)); err == nil {
		t.Fatal("accepted oversized widget data")
	}
}
