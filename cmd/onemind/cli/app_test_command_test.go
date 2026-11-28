// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestAppTestReplaysTheCheckoutHarnessResult(t *testing.T) {
	t.Chdir(t.TempDir())
	out := run(t, "", false, "app", "test")
	if out.code != ExitUsage || !strings.Contains(out.errOut, "source checkout root") {
		t.Fatalf("outside checkout: %+v", out)
	}
	for _, directory := range []string{"sdk/tools", "core"} {
		if err := os.MkdirAll(directory, 0755); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile("core/pyproject.toml", nil, 0644); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join("sdk", "tools", "app-refusals")
	script := "import sys\nassert sys.flags.isolated\nprint('refusal harness ran')\n"
	if err := os.WriteFile(path, []byte(script), 0644); err != nil {
		t.Fatal(err)
	}
	out = run(t, "", false, "app", "test")
	if out.code != 0 || !strings.Contains(out.out, "refusal harness ran") {
		t.Fatalf("harness success: %+v", out)
	}
	if err := os.WriteFile(path, []byte(script+"sys.exit(4)\n"), 0644); err != nil {
		t.Fatal(err)
	}
	out = run(t, "", false, "app", "test")
	if out.code != ExitVerifyFailed || !strings.Contains(out.errOut, "exit status 4") {
		t.Fatalf("harness refusal lost: %+v", out)
	}
}
