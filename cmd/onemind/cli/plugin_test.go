// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPluginValidateCLI(t *testing.T) {
	fixture, err := os.ReadFile("../../../internal/plugin/validate/testdata/tool.yaml")
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	path := filepath.Join(dir, "onemind.app.yaml")
	for _, valid := range []bool{true, false} {
		data := fixture
		if !valid {
			data = []byte(strings.ReplaceAll(string(data), "nodes:read", "actions:approve"))
		}
		if err := os.WriteFile(path, data, 0600); err != nil {
			t.Fatal(err)
		}
		var out, stderr bytes.Buffer
		code := Run([]string{"plugin", "validate", dir, "--json"}, Env{Stdout: &out, Stderr: &stderr})
		if valid && (code != ExitOK || !strings.Contains(out.String(), `"valid": true`)) {
			t.Fatalf("%d %s %s", code, &out, &stderr)
		}
		if !valid && (code != ExitVerifyFailed || !strings.Contains(stderr.String(), "validation_failed")) {
			t.Fatalf("%d %s", code, &stderr)
		}
	}
}

func TestPluginValidatePreviousGrants(t *testing.T) {
	fixture, err := os.ReadFile("../../../internal/plugin/validate/testdata/tool.yaml")
	if err != nil {
		t.Fatal(err)
	}
	previous, current := t.TempDir(), t.TempDir()
	if err := os.WriteFile(filepath.Join(previous, "onemind.app.yaml"), fixture, 0600); err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		name     string
		data     []byte
		json     bool
		code     int
		contains string
	}{
		{"unchanged", fixture, true, ExitOK, `"widens_grants": false`},
		{"widened", []byte(strings.ReplaceAll(string(fixture), "actions:request:app.install", "apps:read")), true, ExitOK, `"widens_grants": true`},
		{"text", []byte(strings.ReplaceAll(string(fixture), "actions:request:app.install", "apps:read")), false, ExitOK, "widens_grants: true (informational; owner approval still required)"},
		{"different id", []byte(strings.ReplaceAll(string(fixture), "id: uptime-kuma", "id: another-plugin")), true, ExitVerifyFailed, "different plugin IDs"},
	} {
		t.Run(test.name, func(t *testing.T) {
			if err := os.WriteFile(filepath.Join(current, "onemind.app.yaml"), test.data, 0600); err != nil {
				t.Fatal(err)
			}
			args := []string{"plugin", "validate", current, "--previous", previous}
			if test.json {
				args = append(args, "--json")
			}
			var out, stderr bytes.Buffer
			code := Run(args, Env{Stdout: &out, Stderr: &stderr})
			if code != test.code || !strings.Contains(out.String()+stderr.String(), test.contains) {
				t.Fatalf("code %d: %s %s", code, &out, &stderr)
			}
		})
	}
	if err := os.WriteFile(filepath.Join(previous, "onemind.app.yaml"), []byte("invalid"), 0600); err != nil {
		t.Fatal(err)
	}
	var out, stderr bytes.Buffer
	code := Run([]string{"plugin", "validate", current, "--previous", previous}, Env{Stdout: &out, Stderr: &stderr})
	if code != ExitVerifyFailed {
		t.Fatalf("invalid previous manifest accepted: %d", code)
	}
}

func TestPluginValidateRejectsEmptyPrevious(t *testing.T) {
	fixture, err := os.ReadFile("../../../internal/plugin/validate/testdata/tool.yaml")
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "onemind.app.yaml"), fixture, 0600); err != nil {
		t.Fatal(err)
	}
	for _, previous := range []string{"", " ", "\t\n"} {
		t.Run(previous, func(t *testing.T) {
			var out, stderr bytes.Buffer
			code := Run([]string{"plugin", "validate", dir, "--previous", previous, "--json"}, Env{Stdout: &out, Stderr: &stderr})
			if code != ExitVerifyFailed || out.Len() != 0 || !strings.Contains(stderr.String(), `"error":"validation_failed"`) || !strings.Contains(stderr.String(), "--previous requires a non-empty directory") {
				t.Fatalf("code %d: stdout %s stderr %s", code, &out, &stderr)
			}
		})
	}
}
