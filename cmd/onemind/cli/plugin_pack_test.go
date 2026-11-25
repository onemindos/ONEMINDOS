// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"path/filepath"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/plugin/scaffold"
)

func TestPluginPackCLIReportsUnsignedLayout(t *testing.T) {
	source := filepath.Join(t.TempDir(), "example")
	if err := scaffold.Create(source, "example", "settings", "https://example.invalid/source"); err != nil {
		t.Fatal(err)
	}
	var out, stderr bytes.Buffer
	output := filepath.Join(t.TempDir(), "oci")
	code := Run([]string{"plugin", "pack", source, "--output", output, "--json"}, Env{Stdout: &out, Stderr: &stderr})
	if code != ExitOK || !strings.Contains(out.String(), `"verified": false`) || !strings.Contains(out.String(), `sha256:`) {
		t.Fatalf("%d %s %s", code, &out, &stderr)
	}
}
