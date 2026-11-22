// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"path/filepath"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/plugin/artifact"
	"github.com/onemindos/onemindos/internal/plugin/scaffold"
)

func TestPluginInspectIntegrityDoesNotImplyTrust(t *testing.T) {
	src := filepath.Join(t.TempDir(), "example")
	if err := scaffold.Create(src, "example", "settings", "https://example.invalid/source"); err != nil {
		t.Fatal(err)
	}
	output := filepath.Join(t.TempDir(), "oci")
	digest, err := artifact.Pack(src, output)
	if err != nil {
		t.Fatal(err)
	}
	var out, stderr bytes.Buffer
	code := Run([]string{"plugin", "inspect", output, "--digest", digest, "--json"}, Env{Stdout: &out, Stderr: &stderr})
	if code != ExitOK || !strings.Contains(out.String(), `"verified": false`) || !strings.Contains(out.String(), `"integrity": true`) {
		t.Fatalf("%d %s %s", code, &out, &stderr)
	}
	code = Run([]string{"plugin", "inspect", output, "--digest", "latest"}, Env{Stdout: &out, Stderr: &stderr})
	if code != ExitVerifyFailed {
		t.Fatalf("mutable reference accepted: %d", code)
	}
}
