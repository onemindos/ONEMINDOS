// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPluginCardValidateCLI(t *testing.T) {
	examples := "../../../sdk/schema/examples/device-card/"
	var out, stderr bytes.Buffer
	code := Run([]string{"plugin", "card", "validate", examples + "relay.json", examples + "temperature-sensor.json", "--json"}, Env{Stdout: &out, Stderr: &stderr})
	if code != ExitOK || !strings.Contains(out.String(), `"valid": true`) {
		t.Fatalf("%d %s %s", code, &out, &stderr)
	}

	relay, err := os.ReadFile(examples + "relay.json")
	if err != nil {
		t.Fatal(err)
	}
	bad := filepath.Join(t.TempDir(), "relay.json")
	if err := os.WriteFile(bad, bytes.Replace(relay, []byte(`"needsHold": true`), []byte(`"needsHold": false`), 1), 0600); err != nil {
		t.Fatal(err)
	}
	out.Reset()
	stderr.Reset()
	code = Run([]string{"plugin", "card", "validate", bad}, Env{Stdout: &out, Stderr: &stderr})
	if code != ExitVerifyFailed || !strings.Contains(out.String(), "hold-required at /actions/switch/om:safety/needsHold") ||
		!strings.Contains(stderr.String(), "device cards are invalid") {
		t.Fatalf("%d %s %s", code, &out, &stderr)
	}
}
