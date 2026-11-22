// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func bundle(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	data, err := os.ReadFile("testdata/tool.yaml")
	if err != nil {
		t.Fatal(err)
	}
	for name, content := range map[string][]byte{"onemind.app.yaml": data, "icon.svg": []byte("<svg/>")} {
		if err := os.WriteFile(filepath.Join(root, name), content, 0600); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.Mkdir(filepath.Join(root, "manifests"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "manifests", "kustomization.yaml"), []byte("resources: []\n"), 0600); err != nil {
		t.Fatal(err)
	}
	return root
}

func TestDirectory(t *testing.T) {
	if err := Directory(bundle(t)); err != nil {
		t.Fatal(err)
	}
	tests := []struct {
		name   string
		mutate func(*testing.T, string)
	}{
		{"missing icon", func(t *testing.T, root string) { must(t, os.Remove(filepath.Join(root, "icon.svg"))) }},
		{"missing workload", func(t *testing.T, root string) {
			must(t, os.Rename(filepath.Join(root, "manifests"), filepath.Join(root, "other")))
		}},
		{"manifest symlink", func(t *testing.T, root string) {
			path := filepath.Join(root, "onemind.app.yaml")
			must(t, os.Rename(path, path+".real"))
			must(t, os.Symlink(path+".real", path))
		}},
		{"icon symlink", func(t *testing.T, root string) {
			path := filepath.Join(root, "icon.svg")
			must(t, os.Remove(path))
			must(t, os.Symlink(filepath.Join(t.TempDir(), "outside.svg"), path))
		}},
		{"nested symlink", func(t *testing.T, root string) {
			must(t, os.Symlink(t.TempDir(), filepath.Join(root, "manifests", "escape")))
		}},
		{"internal symlink", func(t *testing.T, root string) {
			must(t, os.Symlink("kustomization.yaml", filepath.Join(root, "manifests", "alias.yaml")))
		}},
		{"wrong icon type", func(t *testing.T, root string) {
			path := filepath.Join(root, "icon.svg")
			must(t, os.Remove(path))
			must(t, os.Mkdir(path, 0700))
		}},
		{"traversal", func(t *testing.T, root string) { rewrite(t, root, "manifests: manifests/", "manifests: ../outside") }},
		{"root workload", func(t *testing.T, root string) { rewrite(t, root, "manifests: manifests/", "manifests: .") }},
		{"absolute workload", func(t *testing.T, root string) { rewrite(t, root, "manifests: manifests/", "manifests: /tmp/outside") }},
		{"oversized manifest", func(t *testing.T, root string) {
			must(t, os.WriteFile(filepath.Join(root, "onemind.app.yaml"), make([]byte, MaxManifestBytes+1), 0600))
		}},
		{"intermediate symlink", func(t *testing.T, root string) {
			must(t, os.Symlink(root, filepath.Join(root, "linked")))
			rewrite(t, root, "icon: icon.svg", "icon: linked/icon.svg")
		}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			root := bundle(t)
			tt.mutate(t, root)
			if err := Directory(root); err == nil {
				t.Fatal("accepted unsafe bundle")
			}
		})
	}
	root := bundle(t)
	link := filepath.Join(t.TempDir(), "root-link")
	must(t, os.Symlink(root, link))
	if err := Directory(link); err == nil {
		t.Fatal("accepted symlink root")
	}
}
func must(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}
func rewrite(t *testing.T, root, old, replacement string) {
	t.Helper()
	path := filepath.Join(root, "onemind.app.yaml")
	data, err := os.ReadFile(path)
	must(t, err)
	if !strings.Contains(string(data), old) {
		t.Fatal("missing replacement")
	}
	must(t, os.WriteFile(path, []byte(strings.ReplaceAll(string(data), old, replacement)), 0600))
}
