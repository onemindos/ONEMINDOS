// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/cmd/onemind/cli/appmodule"
)

func moduleCheckout(t *testing.T) {
	t.Helper()
	t.Chdir(t.TempDir())
	for _, dir := range []string{"core/onemind_core/routers", "dashboard/src/screens", "core/tests", "sdk/schema"} {
		if err := os.MkdirAll(dir, 0755); err != nil {
			t.Fatal(err)
		}
	}
}

func TestAppNewModule(t *testing.T) {
	moduleCheckout(t)
	r := run(t, "", false, "app", "new", "bird-log", "--kind", "module")
	if r.code != 0 {
		t.Fatalf("app new: %s", r.errOut)
	}
	for _, path := range []string{"core/onemind_core/bird-log/store.py", "core/onemind_core/bird-log/service.py",
		"core/onemind_core/bird-log/onemind.app.yaml", "core/onemind_core/routers/bird_log.py",
		"core/tests/test_bird_log.py", "dashboard/src/screens/bird-log/screen.ts", "dashboard/src/screens/bird-log/Page.tsx"} {
		if data, err := os.ReadFile(path); err != nil || len(data) == 0 || strings.Contains(string(data), "{{.") {
			t.Errorf("incomplete scaffold at %s: %v", path, err)
		}
	}
	if r = run(t, "", false, "app", "new", "bird-log", "--kind", "module"); r.code == 0 {
		t.Fatal("overwrote an existing module")
	}
}

func TestAppNewRefusesPartialAndInvalidModules(t *testing.T) {
	moduleCheckout(t)
	collision := "core/tests/test_notes.py"
	if err := os.WriteFile(collision, []byte("local work"), 0600); err != nil {
		t.Fatal(err)
	}
	for _, args := range [][]string{{"new", "notes"}, {"new", "../outside"}, {"new", "a/b"}, {"new", "notes", "--kind", "service"}} {
		if r := run(t, "", false, append([]string{"app"}, args...)...); r.code == 0 {
			t.Fatalf("accepted %q", args)
		}
	}
	if body, _ := os.ReadFile(collision); string(body) != "local work" {
		t.Fatal("pre-existing file was changed")
	}
	if _, err := os.Stat("core/onemind_core/notes"); !os.IsNotExist(err) {
		t.Fatal("left a partial module")
	}
	if r := run(t, "", false, "app", "new", "another"); r.code != 0 {
		t.Fatal(r.errOut)
	}
}

func TestAppDevRunsLocalGatewayAndDashboard(t *testing.T) {
	moduleCheckout(t)
	bin := t.TempDir()
	log := filepath.Join(bin, "commands")
	t.Setenv("OM_DEV_TEST_LOG", log)
	t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
	t.Setenv("VITE_MOCK", "1")
	t.Setenv("ONEMIND_EXECUTOR", "kubernetes")
	t.Setenv("ONEMIND_DB_URL", "outside-dev")
	for _, tool := range []string{"make", "npm"} {
		script := `#!/bin/sh
echo "${0##*/} $* executor=$ONEMIND_EXECUTOR mock=$VITE_MOCK db=$ONEMIND_DB_URL" >> "$OM_DEV_TEST_LOG"
case "$*" in
  *"core run") sleep 12 ;;
  *"run dev"*) exit 17 ;;
esac
`
		if err := os.WriteFile(filepath.Join(bin, tool), []byte(script), 0700); err != nil {
			t.Fatal(err)
		}
	}
	if r := run(t, "", false, "app", "dev"); r.code == 0 {
		t.Fatal("lost dashboard error")
	}
	out, err := os.ReadFile(log)
	if err != nil {
		t.Fatal(err)
	}
	for _, command := range []string{"make -C sdk openapi gen-ts", "npm --prefix dashboard ci", "make -C core run", "npm --prefix dashboard run dev -- --config app-dev/vite.config.ts --host 127.0.0.1"} {
		if !strings.Contains(string(out), command) {
			t.Errorf("missing %q in %s", command, out)
		}
	}
	if strings.Contains(string(out), "kubernetes") || strings.Contains(string(out), "outside-dev") || strings.Contains(string(out), "mock=1") {
		t.Fatalf("inherited live configuration: %s", out)
	}
}

func TestAppNewReservesAModuleOnce(t *testing.T) {
	moduleCheckout(t)
	errs := make(chan error, 2)
	for range 2 {
		go func() { errs <- appmodule.Create(".", "daily-log") }()
	}
	first, second := <-errs, <-errs
	if (first == nil) == (second == nil) {
		t.Fatalf("expected exactly one successful writer: %v, %v", first, second)
	}
	if _, err := os.Stat("dashboard/src/screens/daily-log/screen.ts"); err != nil {
		t.Fatal(err)
	}
}
