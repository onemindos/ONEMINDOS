// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func declarativeFixture(t *testing.T) map[string]any {
	t.Helper()
	value := comparisonFixture(t)
	spec := value["spec"].(map[string]any)
	delete(spec, "plugin")
	delete(spec, "manifests")
	delete(spec, "permissions")
	spec["extensions"] = map[string]any{"settings": map[string]any{"schema": "settings.schema.json"}}
	value["metadata"].(map[string]any)["publisher"] = map[string]any{"id": "example-dev", "name": "Example Dev"}
	return value
}

func TestDeclarativeBundleWithoutWorkload(t *testing.T) {
	value := declarativeFixture(t)
	root := t.TempDir()
	for name, data := range map[string][]byte{
		"onemind.app.yaml":     manifestBytes(t, value),
		"icon.svg":             []byte("<svg/>"),
		"settings.schema.json": []byte(`{"type":"object","additionalProperties":false}`),
	} {
		if err := os.WriteFile(filepath.Join(root, name), data, 0600); err != nil {
			t.Fatal(err)
		}
	}
	if err := Directory(root); err != nil {
		t.Fatal(err)
	}
	if _, err := Compare(manifestBytes(t, value), manifestBytes(t, value)); err != nil {
		t.Fatal(err)
	}
	// An undeclared manifests/ folder would be applied by the gateway unchecked.
	if err := os.MkdirAll(filepath.Join(root, "manifests"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "manifests", "pod.yaml"), []byte("kind: Pod\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := Directory(root); err == nil {
		t.Fatal("undeclared manifests/ folder accepted")
	}
	spec := value["spec"].(map[string]any)
	spec["extensions"] = map[string]any{"tiles": []any{map[string]any{"id": "open", "label": "Open", "opens": "web"}}}
	if err := Manifest(manifestBytes(t, value)); err != nil {
		t.Fatal(err)
	}
}

func TestRuntimeDeclarationsRequireBackendAndWorkload(t *testing.T) {
	for _, kind := range []string{"tools", "iframe", "subscription"} {
		for _, missing := range []string{"plugin", "backend", "manifests"} {
			t.Run(kind+" missing "+missing, func(t *testing.T) {
				value := comparisonFixture(t)
				spec := value["spec"].(map[string]any)
				ext := spec["extensions"].(map[string]any)
				switch kind {
				case "iframe":
					delete(ext, "tools")
					ext["widgets"] = []any{map[string]any{"id": "live", "title": "Live", "render": "iframe", "entry": "ui/index.html", "surfaces": []any{"dashboard"}}}
				case "subscription":
					delete(ext, "tools")
					spec["permissions"] = []any{"events:subscribe:onemind.node.*.status"}
					ext["events"] = map[string]any{"subscribe": []any{"onemind.node.*.status"}}
				}
				if err := Manifest(manifestBytes(t, value)); err != nil {
					t.Fatal("valid runtime declaration:", err)
				}
				if missing == "backend" {
					delete(spec["plugin"].(map[string]any), missing)
				} else {
					delete(spec, missing)
				}
				if err := Manifest(manifestBytes(t, value)); err == nil {
					t.Fatal("accepted missing", missing)
				}
			})
		}
	}
}

func TestPublisherIsBoundedDeclaration(t *testing.T) {
	for _, publisher := range []any{
		map[string]any{"id": "../bad", "name": "Bad"},
		map[string]any{"id": "good", "name": ""},
		map[string]any{"id": "good", "name": "Good", "verified": true},
		map[string]any{"name": "Missing id"},
		"trusted",
	} {
		value := declarativeFixture(t)
		value["metadata"].(map[string]any)["publisher"] = publisher
		if err := Manifest(manifestBytes(t, value)); err == nil {
			t.Fatalf("accepted invalid publisher %#v", publisher)
		}
	}
}

func TestDeclarativeChangesStillGuardRemovedTools(t *testing.T) {
	previous := comparisonFixture(t)
	current := declarativeFixture(t)
	if _, err := Compare(manifestBytes(t, previous), manifestBytes(t, current)); err == nil {
		t.Fatal("removed tools without major bump")
	}
	current["metadata"].(map[string]any)["version"] = "3.0.0"
	if _, err := Compare(manifestBytes(t, previous), manifestBytes(t, current)); err != nil {
		t.Fatal(err)
	}
}

func TestAppWorkloadContractAndPrincipalSeparation(t *testing.T) {
	// The shared App schema still requires workloads for ordinary apps.
	value := declarativeFixture(t)
	spec := value["spec"].(map[string]any)
	delete(spec, "extensions")
	s, err := compiled()
	if err != nil {
		t.Fatal(err)
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	var document any
	if err := json.Unmarshal(encoded, &document); err != nil {
		t.Fatal(err)
	}
	if err := s.Validate(document); err == nil {
		t.Fatal("ordinary app missing manifests accepted")
	}
	spec["manifests"] = "manifests/"
	encoded, _ = json.Marshal(value)
	if err := json.Unmarshal(encoded, &document); err != nil {
		t.Fatal(err)
	}
	if err := s.Validate(document); err != nil {
		t.Fatal("ordinary app contract changed:", err)
	}
	value = comparisonFixture(t)
	spec = value["spec"].(map[string]any)
	spec["agent"] = map[string]any{"principal": true, "secret": "other-token"}
	if err := Manifest(manifestBytes(t, value)); err == nil {
		t.Fatal("plugin also acquired an unscoped agent principal")
	}
}
