// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestAppDevRunsLocalGatewayAndDashboard(t *testing.T) {
	t.Chdir(t.TempDir())
	for _, file := range []string{"core/Makefile", "sdk/Makefile", "dashboard/package-lock.json", "dashboard/app-dev/vite.config.ts"} {
		if err := os.MkdirAll(filepath.Dir(file), 0755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(file, nil, 0644); err != nil {
			t.Fatal(err)
		}
	}
	bin := t.TempDir()
	log := filepath.Join(bin, "commands")
	ready := filepath.Join(bin, "gateway-ready")
	stop := filepath.Join(bin, "gateway-stop")
	if out, err := exec.Command("mkfifo", ready, stop).CombinedOutput(); err != nil {
		t.Fatalf("create gateway synchronization pipes: %v: %s", err, out)
	}
	t.Setenv("OM_DEV_TEST_LOG", log)
	t.Setenv("OM_DEV_TEST_READY", ready)
	t.Setenv("OM_DEV_TEST_STOP", stop)
	t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
	t.Setenv("VITE_MOCK", "1")
	t.Setenv("ONEMIND_EXECUTOR", "kubernetes")
	t.Setenv("ONEMIND_DB_URL", "outside-dev")
	for _, tool := range []string{"make", "npm"} {
		script := `#!/bin/sh
echo "${0##*/} $* executor=$ONEMIND_EXECUTOR mock=$VITE_MOCK db=$ONEMIND_DB_URL" >> "$OM_DEV_TEST_LOG"
case "$*" in
  *"core run")
    # Signal only after the gateway recorded its invocation, then wait for CLI cancellation.
    printf '%s\n' ready > "$OM_DEV_TEST_READY"
    read -r ignored < "$OM_DEV_TEST_STOP"
    ;;
  *"run dev"*)
    read -r state < "$OM_DEV_TEST_READY" || exit 18
    [ "$state" = ready ] || exit 18
    exit 17
    ;;
esac
`
		if err := os.WriteFile(filepath.Join(bin, tool), []byte(script), 0700); err != nil {
			t.Fatal(err)
		}
	}
	if r := run(t, "", false, "app", "dev"); r.code == 0 || !strings.Contains(r.errOut, "exit status 17") {
		t.Fatalf("lost dashboard error: %s", r.errOut)
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

func TestAppDevRequiresTheSourceCheckout(t *testing.T) {
	t.Chdir(t.TempDir())
	r := run(t, "", false, "app", "dev")
	if r.code == 0 || !strings.Contains(r.errOut, "OneMind source checkout root") {
		t.Fatalf("unexpected result outside a checkout: %d %s", r.code, r.errOut)
	}
}
