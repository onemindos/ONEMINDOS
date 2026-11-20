// SPDX-License-Identifier: Apache-2.0

package scaffold

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/onemindos/onemindos/internal/plugin/validate"
)

func TestGeneratedPluginUsesRealValidator(t *testing.T) {
	directory := filepath.Join(t.TempDir(), "settings-card")
	if err := Create(directory, "settings-card", "settings", "https://example.invalid/source"); err != nil {
		t.Fatal(err)
	}
	if err := validate.DirectoryForAPI(directory, "0.3"); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(directory, "settings.schema.json"), []byte(`{"$ref":"https://example.invalid/schema"}`), 0600); err != nil {
		t.Fatal(err)
	}
	if err := validate.Directory(directory); err == nil {
		t.Fatal("validator accepted a remote schema reference")
	}
}

func TestNeverOverwritesExistingDestination(t *testing.T) {
	for _, kind := range []string{"directory", "file", "symlink"} {
		t.Run(kind, func(t *testing.T) {
			root := t.TempDir()
			target := filepath.Join(root, "existing")
			switch kind {
			case "directory":
				if err := os.Mkdir(target, 0700); err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(filepath.Join(target, "keep"), []byte("user data"), 0600); err != nil {
					t.Fatal(err)
				}
			case "file":
				if err := os.WriteFile(target, []byte("user data"), 0600); err != nil {
					t.Fatal(err)
				}
			case "symlink":
				if err := os.Symlink(root, target); err != nil {
					t.Fatal(err)
				}
			}
			if err := Create(target, "example", "settings", "https://example.invalid/source"); err == nil {
				t.Fatal("existing path replaced")
			}
			if kind == "directory" {
				got, err := os.ReadFile(filepath.Join(target, "keep"))
				if err != nil || string(got) != "user data" {
					t.Fatal("existing data changed")
				}
			}
		})
	}
}

func TestInvalidInputLeavesNoDestination(t *testing.T) {
	for _, id := range []string{"../escape", "Uppercase", "", "a/b"} {
		directory := filepath.Join(t.TempDir(), "target")
		if err := Create(directory, id, "settings", "https://example.invalid/source"); err == nil {
			t.Fatal("invalid id accepted")
		}
		if _, err := os.Stat(directory); !os.IsNotExist(err) {
			t.Fatal("invalid input created files")
		}
	}
	if err := Create(filepath.Join(t.TempDir(), "target"), "valid", "unknown", "https://example.invalid/source"); err == nil {
		t.Fatal("unknown template accepted")
	}
}
