// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func runKiosk(t *testing.T, args ...string) (string, error) {
	t.Helper()
	var out bytes.Buffer
	root, _ := NewRoot(Env{Stdout: &out, Stderr: &out, Stdin: strings.NewReader("")})
	root.SetArgs(args)
	err := root.Execute()
	return out.String(), err
}

func TestKioskEnableDisable(t *testing.T) {
	flag := filepath.Join(t.TempDir(), "kiosk", "enabled")
	f := "--flag-file=" + flag
	if out, err := runKiosk(t, "kiosk", "status", f); err != nil || !strings.Contains(out, "kiosk: off") {
		t.Fatalf("fresh box: %q %v", out, err)
	}
	if out, err := runKiosk(t, "kiosk", "enable", f); err != nil || !strings.Contains(out, "systemctl restart") {
		t.Fatalf("enable: %q %v", out, err)
	}
	if _, err := os.Stat(flag); err != nil {
		t.Fatalf("enable must create the flag file the units test: %v", err)
	}
	out, err := runKiosk(t, "--json", "kiosk", "status", f)
	var got struct{ Enabled bool }
	if err != nil || json.Unmarshal([]byte(out), &got) != nil || !got.Enabled {
		t.Fatalf("status after enable: %q %v", out, err)
	}
	if _, err := runKiosk(t, "kiosk", "disable", f); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(flag); !os.IsNotExist(err) {
		t.Fatalf("disable must remove the flag file: %v", err)
	}
	if _, err := runKiosk(t, "kiosk", "disable", f); err != nil {
		t.Fatalf("disable twice is fine: %v", err)
	}
}

func TestKioskFlagMatchesUnits(t *testing.T) {
	for _, u := range []string{"onemind-kiosk.service", "onemind-screen.service"} {
		b, err := os.ReadFile(filepath.Join("..", "..", "..", "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", u))
		if err != nil || !strings.Contains(string(b), "ConditionPathExists=") || !strings.Contains(string(b), kioskFlag) {
			t.Errorf("%s must test %s (%v)", u, kioskFlag, err)
		}
	}
}
