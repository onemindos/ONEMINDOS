// SPDX-License-Identifier: Apache-2.0

package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// The owner's switch: off by default, each change recorded on the chain before it happens.
func TestRescueTerminalSwitch(t *testing.T) {
	d := t.TempDir()
	sw, au := filepath.Join(d, "on"), filepath.Join(d, "audit.jsonl")
	args := func(cmd string) []string { return []string{cmd, "-terminal-switch", sw, "-audit", au} }
	if rc := runRescueTerminal(args("status")); rc != 0 {
		t.Fatalf("status = %d", rc)
	}
	if _, err := os.Stat(sw); err == nil {
		t.Fatal("the switch exists on a fresh box")
	}
	if rc := runRescueTerminal(args("enable")); rc != 0 {
		t.Fatalf("enable = %d", rc)
	}
	if st, err := os.Stat(sw); err != nil || st.Mode().Perm() != 0o600 {
		t.Fatalf("switch file: %v %v", st, err)
	}
	if rc := runRescueTerminal(args("disable")); rc != 0 {
		t.Fatalf("disable = %d", rc)
	}
	if _, err := os.Stat(sw); err == nil {
		t.Fatal("disable left the switch")
	}
	b, _ := os.ReadFile(au)
	if strings.Count(string(b), `"event":"terminal.switch"`) != 2 || !strings.Contains(string(b), `"state":"enabled"`) ||
		!strings.Contains(string(b), `"state":"disabled"`) {
		t.Fatalf("audit = %s", b)
	}
	if rc := runRescueTerminal(args("bogus")); rc != 2 {
		t.Fatalf("bogus = %d", rc)
	}
	// a chain that does not verify blocks the change
	if err := os.WriteFile(au, []byte("not json\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if rc := runRescueTerminal(args("enable")); rc != 1 {
		t.Fatalf("enable on a broken chain = %d, want 1", rc)
	}
	if _, err := os.Stat(sw); err == nil {
		t.Fatal("the switch was turned on with a broken audit chain")
	}
}
