// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"os"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestManifest(t *testing.T) {
	data, err := os.ReadFile("testdata/tool.yaml")
	if err != nil {
		t.Fatal(err)
	}
	if err := Manifest(data); err != nil {
		t.Fatal(err)
	}
	tests := []struct{ name, from, to string }{
		{"approve", "nodes:read", "actions:approve"},
		{"admin", "nodes:read", "users:admin"},
		{"broad request", "actions:request:app.install", "actions:request"},
		{"actuate", "effect: read", "effect: actuate"},
		{"unknown effect", "effect: read", "effect: execute"},
		{"principal", "principal: true", "principal: false"},
		{"no backend", "backend:", "unknown:"},
		{"bad port", "port: 3001}", "port: 0}"},
		{"bad compat", ">=0.3 <1.0", "not-a-range"},
		{"bad version", "version: \"2.5.11\"", "version: \"latest\""},
		{"numeric prerelease", "version: \"2.5.11\"", "version: \"2.5.11-01\""},
		{"open schema", "additionalProperties: false", "additionalProperties: true"},
		{"older dialect", "type: object, additionalProperties: false", "type: object, additionalProperties: false, $schema: 'http://json-schema.org/draft-07/schema#'"},
		{"invalid schema", "type: object, additionalProperties: false", "type: object, additionalProperties: false, required: 42"},
		{"external ref", "type: object, additionalProperties: false", "type: object, additionalProperties: false, $ref: 'https://example.com/schema'"},
		{"traversal", "manifests: manifests/", "manifests: ../outside"},
		{"unknown extension", "tools:", "widgets:"},
		{"multiple docs", "apiVersion: onemind.app/v1alpha1", "---\n{}\n---\napiVersion: onemind.app/v1alpha1"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if !strings.Contains(string(data), tt.from) {
				t.Fatal("test replacement missing")
			}
			if err := Manifest([]byte(strings.ReplaceAll(string(data), tt.from, tt.to))); err == nil {
				t.Fatal("accepted invalid manifest")
			}
		})
	}
	for _, effect := range []string{"write", "destructive"} {
		if err := Manifest([]byte(strings.ReplaceAll(string(data), "effect: read", "effect: "+effect))); err != nil {
			t.Fatal(err)
		}
	}
	var value map[string]any
	if err := yaml.Unmarshal(data, &value); err != nil {
		t.Fatal(err)
	}
	ext := value["spec"].(map[string]any)["extensions"].(map[string]any)
	tools := ext["tools"].([]any)
	ext["tools"] = append(tools, tools[0])
	duplicate, _ := yaml.Marshal(value)
	if err := Manifest(duplicate); err == nil {
		t.Fatal("accepted duplicate tools")
	}
	if err := Manifest(make([]byte, MaxManifestBytes+1)); err == nil {
		t.Fatal("accepted oversized manifest")
	}
}

func TestExistingAppSchemaCompiles(t *testing.T) {
	if _, err := compiled(); err != nil {
		t.Fatal(err)
	}
}
