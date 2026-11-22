// SPDX-License-Identifier: Apache-2.0

// Package appmodule implements the local development commands for built-in gateway modules.
package appmodule

import (
	"crypto/sha256"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path"
	"regexp"
	"slices"
	"strings"
	"text/template"
)

//go:embed templates/*.tmpl
var sources embed.FS
var templates = template.Must(template.ParseFS(sources, "templates/*.tmpl"))
var moduleID = regexp.MustCompile(`^[a-z]([a-z0-9-]{0,57}[a-z0-9])?$`)

func checkRoot(root *os.Root) error {
	for _, dir := range []string{"core/onemind_core/routers", "core/tests", "dashboard/src/screens", "sdk/schema"} {
		if info, err := root.Stat(dir); err != nil || !info.IsDir() {
			return errors.New("run this command from the OneMind source checkout root")
		}
	}
	return nil
}

// A feature may share a router source file with others. The public contract is the
// authority on occupied URLs, even when a matching filename does not exist.
func checkRoute(root *os.Root, id string) error {
	f, err := root.Open("sdk/openapi/onemind-v1.json")
	if err != nil {
		return err
	}
	defer f.Close()
	var doc struct{ Paths map[string]struct{} }
	if err := json.NewDecoder(f).Decode(&doc); err != nil {
		return err
	}
	if len(doc.Paths) == 0 {
		return errors.New("the gateway contract has no paths")
	}
	screen, api := "/"+id, "/v1/"+id
	if _, exists := doc.Paths[screen]; exists || screen == "/v1" {
		return fmt.Errorf("reserved gateway path: %s", screen)
	}
	for existing := range doc.Paths {
		if existing == api || strings.HasPrefix(existing, api+"/") {
			return fmt.Errorf("gateway already serves %s", existing)
		}
	}
	return nil
}

func Create(directory, id string) error {
	if !moduleID.MatchString(id) {
		return errors.New("use a built-in app id of up to 59 lowercase letters, digits and hyphens, starting with a letter and ending with a letter or digit")
	}
	root, err := os.OpenRoot(directory)
	if err != nil {
		return err
	}
	defer root.Close()
	if err := checkRoot(root); err != nil {
		return err
	}
	if err := checkRoute(root, id); err != nil {
		return err
	}
	module := strings.ReplaceAll(id, "-", "_")
	schema := module
	if len(schema) > 40 { // store.FeatureSchema caps the migration namespace at 40 characters
		digest := sha256.Sum256([]byte(id))
		schema = fmt.Sprintf("%s_%x", module[:23], digest[:8])
	}
	data := struct{ ID, Module, Schema string }{id, module, schema}
	pkg := path.Join("core/onemind_core", id)
	screen := path.Join("dashboard/src/screens", id)
	files := []struct{ name, dst string }{
		{"init", pkg + "/__init__.py"}, {"store", pkg + "/store.py"}, {"service", pkg + "/service.py"},
		{"descriptor", pkg + "/onemind.app.yaml"}, {"router", "core/onemind_core/routers/" + module + ".py"},
		{"test", "core/tests/test_" + module + ".py"}, {"screen", screen + "/screen.ts"}, {"page", screen + "/Page.tsx"},
	}
	// Reserve the feature directories before writing. Each file is exclusively created, including
	// the two files in shared directories. Clean up only names this invocation created.
	for _, p := range []string{pkg + ".py", pkg, screen} {
		if _, err := root.Lstat(p); !errors.Is(err, fs.ErrNotExist) {
			if err == nil {
				return fmt.Errorf("path already exists: %s", p)
			}
			return err
		}
	}
	var created []string
	success := false
	defer func() {
		if !success {
			for _, p := range slices.Backward(created) {
				_ = root.Remove(p)
			}
		}
	}()
	for _, dir := range []string{pkg, screen} {
		if err := root.Mkdir(dir, 0755); err != nil {
			return err
		}
		created = append(created, dir)
	}
	for _, item := range files {
		f, err := root.OpenFile(item.dst, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0644)
		if err != nil {
			return err
		}
		created = append(created, item.dst)
		writeErr := templates.ExecuteTemplate(f, item.name+".tmpl", data)
		if err := errors.Join(writeErr, f.Close()); err != nil {
			return err
		}
	}
	success = true
	return nil
}
