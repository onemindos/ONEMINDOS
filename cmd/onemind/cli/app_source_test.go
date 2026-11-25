// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestAppNewThenCheck(t *testing.T) {
	// Test fixture only. The scaffolder copies the user's pin and never invents one.
	image := fmt.Sprintf("example.invalid/app/workload:0.1@sha256:%x", sha256.Sum256([]byte("scaffold fixture")))
	for _, template := range []string{"declarative", "telemetry", "container"} {
		t.Run(template, func(t *testing.T) {
			dir := filepath.Join(t.TempDir(), template)
			args := []string{"app", "new", dir, "--template", template, "--source", "https://example.invalid/source", "--json"}
			if template == "container" {
				args = append(args, "--image", image)
			}
			var stdout, stderr bytes.Buffer
			env := Env{Stdout: &stdout, Stderr: &stderr}
			if code := Run(args, env); code != ExitOK {
				t.Fatalf("new: %d %s", code, &stderr)
			}
			manifestPath := filepath.Join(dir, "onemind.app.yaml")
			manifest, err := os.ReadFile(manifestPath)
			if err != nil {
				t.Fatal(err)
			}
			switch template {
			case "declarative":
				if !bytes.Contains(manifest, []byte(`"settings"`)) {
					t.Fatal("settings declaration absent")
				}
			case "telemetry":
				if !bytes.Contains(manifest, []byte(`"reading"`)) {
					t.Fatal("telemetry event declaration absent")
				}
			case "container":
				deployment, err := os.ReadFile(filepath.Join(dir, "manifests", "deployment.yaml"))
				if err != nil {
					t.Fatal(err)
				}
				if !bytes.Contains(deployment, []byte(image)) || bytes.Count(deployment, []byte("@sha256:")) != 1 {
					t.Fatal("image reference did not preserve the supplied pin")
				}
			}
			stdout.Reset()
			stderr.Reset()
			if code := Run([]string{"app", "check", dir, "--json"}, env); code != ExitOK {
				t.Fatalf("check: %d %s", code, &stderr)
			}
			var check struct {
				Valid           bool     `json:"valid"`
				Tier            string   `json:"tier"`
				MissingEvidence []string `json:"missing_evidence"`
			}
			if err := json.Unmarshal(stdout.Bytes(), &check); err != nil || !check.Valid || check.Tier != "none" || len(check.MissingEvidence) == 0 {
				t.Fatalf("unverified source check: %v %s", err, &stdout)
			}
			if code := Run(args, env); code != ExitUsage {
				t.Fatalf("existing directory accepted: %d", code)
			}
			if after, err := os.ReadFile(manifestPath); err != nil || !bytes.Equal(after, manifest) {
				t.Fatalf("existing manifest changed: %v", err)
			}
			if err := os.Remove(filepath.Join(dir, "icon.svg")); err != nil {
				t.Fatal(err)
			}
			if code := Run([]string{"app", "check", dir}, env); code != ExitVerifyFailed {
				t.Fatalf("invalid source accepted: %d", code)
			}
		})
	}
}

func TestAppNewRejectsUnpinnedContainer(t *testing.T) {
	for _, image := range []string{"", "example.invalid/app/workload:latest", "example.invalid/app/workload:latest@sha256:invalid"} {
		dir := filepath.Join(t.TempDir(), "workload")
		var stderr bytes.Buffer
		args := []string{"app", "new", dir, "--template", "container", "--source", "https://example.invalid/source", "--image", image}
		if code := Run(args, Env{Stderr: &stderr}); code != ExitUsage || !strings.Contains(stderr.String(), "pinned by SHA-256") {
			t.Fatalf("unpinned image was not refused: %d %s", code, &stderr)
		}
		if _, err := os.Stat(dir); !os.IsNotExist(err) {
			t.Fatalf("failed scaffolding published a directory: %v", err)
		}
	}
}

func TestPluginAliasPreservesAppTree(t *testing.T) {
	for _, root := range []string{"app", "plugin"} {
		var stdout, stderr bytes.Buffer
		if code := Run([]string{root, "--help"}, Env{Stdout: &stdout, Stderr: &stderr}); code != ExitOK {
			t.Fatalf("%s: %d %s", root, code, &stderr)
		}
		for _, command := range []string{"check", "dev", "init", "new", "pack", "validate"} {
			if !strings.Contains(stdout.String(), "  "+command+" ") {
				t.Fatalf("%s help does not list %s: %s", root, command, &stdout)
			}
		}
	}
}
