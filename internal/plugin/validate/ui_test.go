// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"os"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

const uiDeclarations = `
widgets:
  - id: greeting
    title: Greeting
    render: template
    template: stat
    source: {tool: status, args: {}}
    refresh: 60s
    surfaces: [dashboard, mobile]
  - id: live
    title: Live greeting
    render: iframe
    entry: ui/index.html
    size: {w: 2, h: 2}
    surfaces: [dashboard]
settings: {schema: settings.schema.json}
alerts:
  actions:
    - {id: reset, label: Reset greeting, tool: status, args: {}}
tiles:
  - {id: open, label: Hello, icon: ui/icon.svg, opens: web}
`

func uiManifest(t *testing.T, declarations string, writeTool bool) []byte {
	t.Helper()
	data, err := os.ReadFile("testdata/tool.yaml")
	if err != nil {
		t.Fatal(err)
	}
	if writeTool {
		data = []byte(strings.ReplaceAll(string(data), "effect: read", "effect: write"))
	}
	var value, ui map[string]any
	if err := yaml.Unmarshal(data, &value); err != nil {
		t.Fatal(err)
	}
	if err := yaml.Unmarshal([]byte(declarations), &ui); err != nil {
		t.Fatal(err)
	}
	extensions := value["spec"].(map[string]any)["extensions"].(map[string]any)
	for key, entry := range ui {
		extensions[key] = entry
	}
	data, err = yaml.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestUIManifest(t *testing.T) {
	if err := Manifest(uiManifest(t, uiDeclarations, false)); err != nil {
		t.Fatal(err)
	}
	tests := []struct{ name, old, replacement string }{
		{"unknown source", "source: {tool: status", "source: {tool: missing"},
		{"unknown alert tool", "label: Reset greeting, tool: status", "label: Reset greeting, tool: missing"},
		{"mobile iframe", "surfaces: [dashboard]\nsettings", "surfaces: [mobile]\nsettings"},
		{"traversal entry", "entry: ui/index.html", "entry: ui/../index.html"},
		{"absolute entry", "entry: ui/index.html", "entry: /ui/index.html"},
		{"outside UI", "entry: ui/index.html", "entry: other/index.html"},
		{"double separator", "entry: ui/index.html", "entry: ui//index.html"},
		{"dot component", "entry: ui/index.html", "entry: ui/./index.html"},
		{"newline entry", "entry: ui/index.html", `entry: "ui/index.html\n"`},
		{"settings traversal", "schema: settings.schema.json", "schema: ../settings.schema.json"},
		{"icon traversal", "icon: ui/icon.svg", "icon: ../icon.svg"},
		{"invalid template", "template: stat", "template: html"},
		{"invalid render", "render: iframe", "render: module"},
		{"iframe source", "entry: ui/index.html", "entry: ui/index.html\n    source: {tool: status}"},
		{"template entry", "template: stat", "template: stat\n    entry: ui/index.html"},
		{"bad refresh", "refresh: 60s", "refresh: often"},
		{"zero refresh", "refresh: 60s", "refresh: 0s"},
		{"negative refresh", "refresh: 60s", "refresh: -1s"},
		{"duplicate widget", "id: live", "id: greeting"},
		{"newline id", "id: greeting", `id: "greeting\n"`},
		{"duplicate surface", "[dashboard, mobile]", "[dashboard, dashboard]"},
		{"zero width", "w: 2", "w: 0"},
		{"unknown source property", "tool: status, args: {}", "tool: status, approve: true"},
		{"unknown widget property", "title: Greeting", "title: Greeting\n    approve: true"},
		{"unsupported tile target", "opens: web", "opens: terminal"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if !strings.Contains(uiDeclarations, tt.old) {
				t.Fatal("missing test replacement")
			}
			data := uiManifest(t, strings.ReplaceAll(uiDeclarations, tt.old, tt.replacement), false)
			if err := Manifest(data); err == nil {
				t.Fatal("accepted invalid UI declaration")
			}
		})
	}
	if err := Manifest(uiManifest(t, uiDeclarations, true)); err == nil {
		t.Fatal("accepted write tool as template source")
	}
	// A notification action may request a write; it never grants approval authority.
	if err := Manifest(uiManifest(t, "alerts:\n  actions: [{id: reset, label: Reset, tool: status}]\n", true)); err != nil {
		t.Fatal(err)
	}
	for _, declarations := range []string{
		"tiles: [{id: open, label: Open, opens: web}, {id: open, label: Again, opens: web}]",
		"alerts: {actions: [{id: reset, label: Reset, tool: status}, {id: reset, label: Again, tool: status}]}",
	} {
		if err := Manifest(uiManifest(t, declarations, false)); err == nil {
			t.Fatal("accepted duplicate UI ids")
		}
	}
}

func TestToolNameCannotEndInNewline(t *testing.T) {
	data, err := os.ReadFile("testdata/tool.yaml")
	if err != nil {
		t.Fatal(err)
	}
	data = []byte(strings.ReplaceAll(string(data), "name: status", `name: "status\n"`))
	if err := Manifest(data); err == nil {
		t.Fatal("accepted tool name with trailing newline")
	}
}
