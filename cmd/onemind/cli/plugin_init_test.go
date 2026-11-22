// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"path/filepath"
	"strings"
	"testing"
)

func TestPluginInitThenValidateCLI(t *testing.T) {
	directory := filepath.Join(t.TempDir(), "my-settings")
	var out, stderr bytes.Buffer
	if code := Run([]string{"plugin", "init", directory, "--source", "https://example.invalid/source", "--json"}, Env{Stdout: &out, Stderr: &stderr}); code != ExitOK || !strings.Contains(out.String(), `"created": true`) {
		t.Fatalf("%d %s %s", code, &out, &stderr)
	}
	out.Reset()
	stderr.Reset()
	if code := Run([]string{"plugin", "validate", directory}, Env{Stdout: &out, Stderr: &stderr}); code != ExitOK {
		t.Fatalf("%d %s", code, &stderr)
	}
	if code := Run([]string{"plugin", "init", directory, "--source", "https://example.invalid/source"}, Env{Stdout: &out, Stderr: &stderr}); code != ExitUsage {
		t.Fatalf("existing directory: %d", code)
	}
}
