// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// The golden cases of manifest v1 (#604), shared with sdk/tools/tests/test_manifest_blocks.py.
var golden = filepath.Join("..", "..", "..", "sdk", "testdata", "manifest-v1")

type goldenCase struct {
	Name   string           `yaml:"name"`
	Expect string           `yaml:"expect"`
	Ops    []map[string]any `yaml:"ops"`
}

func goldenBase(t *testing.T) map[string]any {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(golden, "base.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var doc map[string]any
	if err := yaml.Unmarshal(data, &doc); err != nil {
		t.Fatal(err)
	}
	return doc
}

func goldenCases(t *testing.T) (valid, invalid []goldenCase) {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(golden, "cases.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var cases struct{ Valid, Invalid []goldenCase }
	if err := yaml.Unmarshal(data, &cases); err != nil {
		t.Fatal(err)
	}
	return cases.Valid, cases.Invalid
}

// apply is the same tiny JSON-pointer patcher as the Python test: set (value or join) and remove.
func apply(t *testing.T, doc map[string]any, ops []map[string]any) []byte {
	t.Helper()
	data, _ := yaml.Marshal(doc)
	var out map[string]any
	if err := yaml.Unmarshal(data, &out); err != nil { // deep copy
		t.Fatal(err)
	}
	for _, op := range ops {
		parts := strings.Split(strings.TrimPrefix(op["path"].(string), "/"), "/")
		var node any = out
		for _, part := range parts[:len(parts)-1] {
			if list, ok := node.([]any); ok {
				i, _ := strconv.Atoi(part)
				node = list[i]
			} else {
				node = node.(map[string]any)[part]
			}
		}
		last := parts[len(parts)-1]
		value := op["value"]
		if join, ok := op["join"].([]any); ok {
			var b strings.Builder
			for _, p := range join {
				b.WriteString(p.(string))
			}
			value = b.String()
		}
		switch n := node.(type) {
		case []any:
			i, _ := strconv.Atoi(last)
			if op["op"] == "remove" {
				t.Fatalf("remove from a list is not used by the cases (%s)", op["path"])
			}
			n[i] = value
		case map[string]any:
			if op["op"] == "remove" {
				delete(n, last)
			} else {
				n[last] = value
			}
		}
	}
	data, err := yaml.Marshal(out)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestGoldenManifestCoversEveryNewBlock(t *testing.T) {
	spec := goldenBase(t)["spec"].(map[string]any)
	for _, name := range []string{"runtime", "placement", "data", "services", "search", "share", "notifications",
		"mapLayers", "jobs", "backup", "roles", "continue", "needs", "terms", "requires", "recommends", "supports"} {
		if _, ok := spec[name]; !ok {
			t.Errorf("base.yaml lacks spec.%s", name)
		}
	}
	for _, name := range []string{"bridge", "connector", "videoSource", "nats"} {
		if _, ok := spec["extensions"].(map[string]any)[name]; !ok {
			t.Errorf("base.yaml lacks spec.extensions.%s", name)
		}
	}
}

func TestGoldenCasesSameVerdictAsCore(t *testing.T) {
	base := goldenBase(t)
	valid, invalid := goldenCases(t)
	if len(valid) == 0 || len(invalid) < 40 {
		t.Fatalf("too few golden cases: %d valid, %d invalid", len(valid), len(invalid))
	}
	for _, c := range valid {
		t.Run("valid/"+c.Name, func(t *testing.T) {
			if err := Manifest(apply(t, base, c.Ops)); err != nil {
				t.Fatal(err)
			}
		})
	}
	for _, c := range invalid {
		t.Run("invalid/"+c.Name, func(t *testing.T) {
			err := Manifest(apply(t, base, c.Ops))
			if err == nil {
				t.Fatal("accepted")
			}
			if c.Expect != "" && !strings.Contains(err.Error(), c.Expect) {
				t.Fatalf("want %q, got %v", c.Expect, err)
			}
			for _, op := range c.Ops {
				if join, ok := op["join"].([]any); ok && strings.Contains(err.Error(), join[len(join)-1].(string)) {
					t.Fatalf("error repeats the credential: %v", err)
				}
			}
		})
	}
}

func TestSchemaErrorNeverRepeatsACredential(t *testing.T) {
	data := apply(t, goldenBase(t), []map[string]any{
		{"op": "set", "path": "/spec/extensions/bridge/hosts/0", "join": []any{"AKIA", "ABCDEFGHIJKLMNOP"}}})
	err := Manifest(data)
	if err == nil || strings.Contains(err.Error(), "ABCDEFGHIJKLMNOP") {
		t.Fatalf("want a hidden refusal, got %v", err)
	}
}

func TestLooseningNewBlocksWidensGrants(t *testing.T) {
	base := goldenBase(t)
	previous := apply(t, base, nil)
	same, err := Compare(previous, previous)
	if err != nil || same.WidensGrants {
		t.Fatalf("unchanged manifest: %+v %v", same, err)
	}
	cases := []struct {
		name, reason string
		ops          []map[string]any
	}{
		{"redistribution", "terms redistribution widened: nws/tak", []map[string]any{
			{"op": "set", "path": "/spec/terms/providers/1/redistribute/tak", "value": true}}},
		{"store", "terms store widened: nws", []map[string]any{
			{"op": "set", "path": "/spec/terms/providers/1/store", "value": "keep"},
			{"op": "remove", "path": "/spec/terms/providers/1/maxCacheSeconds"}}},
		{"key", "terms key added: usgs", []map[string]any{
			{"op": "set", "path": "/spec/terms/providers/0/keyNeeded", "value": true}}},
		{"host", "bridge host added: api.weather.gov", []map[string]any{
			{"op": "set", "path": "/spec/extensions/bridge/hosts", "value": []any{"earthquake.usgs.gov", "api.weather.gov"}}}},
		{"nats import", "nats imports added: onemind.alert.core.disk", []map[string]any{
			{"op": "set", "path": "/spec/extensions/nats/imports", "value": []any{"onemind.event.app.installed", "onemind.alert.core.disk"}}}},
		{"data reads", "data reads added: activity", []map[string]any{
			{"op": "set", "path": "/spec/data/reads", "value": []any{"location", "activity"}}}},
		{"recording", "videoSource record switched on", []map[string]any{
			{"op": "set", "path": "/spec/extensions/videoSource/record", "value": true}}},
		{"connector auth", "connector auth changed", []map[string]any{
			{"op": "set", "path": "/spec/extensions/connector/auth", "value": "api-key"}}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			diff, err := Compare(previous, apply(t, base, c.ops))
			if err != nil {
				t.Fatal(err)
			}
			if !diff.WidensGrants || !strings.Contains(strings.Join(diff.Reasons, "\n"), c.reason) {
				t.Fatalf("want %q, got %+v", c.reason, diff)
			}
		})
	}
	// Tightening is not a widening.
	tighter := apply(t, base, []map[string]any{
		{"op": "set", "path": "/spec/terms/providers/0/redistribute/publicShare", "value": false}})
	diff, err := Compare(previous, tighter)
	if err != nil || diff.WidensGrants {
		t.Fatalf("tightening widened: %+v %v", diff, err)
	}
}
