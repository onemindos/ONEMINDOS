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
	if err := os.WriteFile(filepath.Join(dir, "icon.svg"), []byte("<svg/>"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(dir, "manifests"), 0700); err != nil {
		t.Fatal(err)
	}
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

func TestPluginValidateRequiresBundleFiles(t *testing.T) {
	fixture, err := os.ReadFile("../../../internal/plugin/validate/testdata/tool.yaml")
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "onemind.app.yaml"), fixture, 0600); err != nil {
		t.Fatal(err)
	}
	var out, stderr bytes.Buffer
	code := Run([]string{"plugin", "validate", dir, "--json"}, Env{Stdout: &out, Stderr: &stderr})
	if code != ExitVerifyFailed || !strings.Contains(stderr.String(), "metadata.icon") {
		t.Fatalf("%d %s", code, &stderr)
	}
}
