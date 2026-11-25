// SPDX-License-Identifier: Apache-2.0

// Package scaffold creates local plugin sources without installing a workload.
package scaffold

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/google/go-containerregistry/pkg/name"

	"github.com/onemindos/onemindos/internal/plugin/validate"
)

var identifier = regexp.MustCompile(`^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`)

// Create preserves the original settings-only `plugin init` command.
func Create(directory, id, template, source string) error {
	if template != "settings" {
		return fmt.Errorf("supported template: settings (backend templates require packaging)")
	}
	return create(directory, id, template, source, "")
}

// CreateApp scaffolds local app sources without registering or installing an app.
func CreateApp(directory, id, template, source, image string) error {
	switch template {
	case "declarative", "telemetry":
		if image != "" {
			return fmt.Errorf("--image is only used by the container template")
		}
	case "container":
		ref, _, split := strings.Cut(image, "@")
		_, tagErr := name.NewTag(ref, name.StrictValidation)
		_, digestErr := name.NewDigest(image, name.StrictValidation)
		if !split || tagErr != nil || digestErr != nil {
			return fmt.Errorf("container template requires a tagged image pinned by SHA-256 digest")
		}
	case "module":
		return fmt.Errorf("module templates need the signed system-app development workflow")
	default:
		return fmt.Errorf("supported templates: declarative, telemetry, container")
	}
	return create(directory, id, template, source, image)
}

// create builds and validates every source file before publishing into a new path.
func create(directory, id, template, source, image string) error {
	if len(id) == 0 || len(id) > 59 || !identifier.MatchString(id) {
		return fmt.Errorf("plugin id must be a DNS label of 1–59 characters")
	}
	manifest := map[string]any{
		"apiVersion": "onemind.app/v1alpha1", "kind": "App",
		"metadata": map[string]any{"id": id, "name": id, "version": "0.1.0", "description": "Declarative plugin settings", "category": "developer",
			// age_rating is required (sdk/schema); 18 is the safest placeholder until the author rates the plugin with the apps/README.md rubric.
			"age_rating": 18, "age_reason": "UNVERIFIED: placeholder (the safest); say in one line why, from what the plugin does",
			"icon": "icon.svg", "license": "Apache-2.0", "licenceClass": "L1", "source": source,
			"links":    map[string]any{"docs": "UNVERIFIED", "github": "UNVERIFIED", "website": "UNVERIFIED", "support": "UNVERIFIED"},
			"upstream": map[string]any{"release": "UNVERIFIED", "released_at": "UNVERIFIED", "archived": false}, "tier": "blocked"},
		"spec": map[string]any{
			"archs": []string{"amd64", "arm64"}, "requires": map[string]any{"gpu": false, "minMemoryMb": 64},
			"updates":    map[string]any{"channel": "stable", "automerge": "none"},
			"compat":     map[string]any{"onemind": ">=0.3 <1.0"},
			"extensions": map[string]any{"settings": map[string]any{"schema": "settings.schema.json"}},
		},
	}
	files := map[string][]byte{
		"settings.schema.json": []byte("{\"$schema\":\"https://json-schema.org/draft/2020-12/schema\",\"type\":\"object\",\"additionalProperties\":false,\"properties\":{\"label\":{\"type\":\"string\",\"maxLength\":80}}}\n"),
		"icon.svg":             []byte("<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 64 64\"><rect x=\"8\" y=\"8\" width=\"48\" height=\"48\" rx=\"12\" fill=\"#4559ff\"/></svg>\n"),
		"README.md":            []byte("# " + id + "\n\nA declarative settings plugin. No backend, network grants or workload credentials.\n\nValidate with `onemind plugin validate .`. The files are local sources; validation does not install or approve a plugin. Packaging, signing and the widget host are required before installation.\n"),
	}
	if template != "settings" {
		appFiles(manifest, files, id, template, image)
	}
	encoded, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return err
	}
	files["onemind.app.yaml"] = append(encoded, '\n')
	absolute, err := filepath.Abs(directory)
	if err != nil {
		return err
	}
	parent, err := filepath.EvalSymlinks(filepath.Dir(absolute))
	if err != nil {
		return fmt.Errorf("destination parent: %w", err)
	}
	absolute = filepath.Join(parent, filepath.Base(absolute))
	// Build and validate before publishing files to the destination.
	stage, err := os.MkdirTemp(parent, ".onemind-plugin-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(stage)
	for name, contents := range files {
		if err := os.MkdirAll(filepath.Dir(filepath.Join(stage, name)), 0755); err != nil {
			return err
		}
		if err := os.WriteFile(filepath.Join(stage, name), contents, 0644); err != nil {
			return err
		}
	}
	if err := validate.Directory(stage); err != nil {
		return fmt.Errorf("generated bundle: %w", err)
	}
	if err := os.Mkdir(absolute, 0755); err != nil {
		return fmt.Errorf("destination must not exist: %w", err)
	}
	created := []string{}
	folders := map[string]bool{".": true}
	success := false
	defer func() {
		if !success {
			for i := len(created) - 1; i >= 0; i-- {
				_ = os.Remove(filepath.Join(absolute, created[i]))
			}
			_ = os.Remove(absolute) // never recursively remove another process's files
		}
	}()
	for name := range files {
		dir := filepath.Dir(name)
		if !folders[dir] {
			if err := os.Mkdir(filepath.Join(absolute, dir), 0755); err != nil {
				return err
			}
			created = append(created, dir)
			folders[dir] = true
		}
		// A hard link publishes each validated file without overwriting any existing file.
		if err := os.Link(filepath.Join(stage, name), filepath.Join(absolute, name)); err != nil {
			return err
		}
		created = append(created, name)
	}
	success = true
	return nil
}
