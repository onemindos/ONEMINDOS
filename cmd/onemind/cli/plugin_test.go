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
