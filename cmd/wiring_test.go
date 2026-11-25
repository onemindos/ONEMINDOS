// SPDX-License-Identifier: Apache-2.0

// Package cmd_test guards against merged-but-unwired code (slop audit CS-01, CS-02): every
// internal/* package must be a dependency of a shipped binary under cmd/, or be listed below
// with the epic that will wire it. A new package that nothing calls fails this test.
package cmd_test

import (
	"os"
	"os/exec"
	"strings"
	"testing"
)

// notWiredYet maps an internal package to the epic that wires it. Remove the line when it is wired.
var notWiredYet = map[string]string{}

// Package-level reachability is coarse: internal/leaf is imported (its health check backs
// `onemind mesh status`), so TestSymbolsAreCalled below checks the symbols it names (slop CS2-06).

func goList(t *testing.T, args ...string) []string {
	t.Helper()
	out, err := exec.Command("go", args...).Output()
	if err != nil {
		t.Fatalf("go %s: %v", strings.Join(args, " "), err)
	}
	return strings.Fields(string(out))
}

func TestEveryInternalPackageIsReachableFromABinary(t *testing.T) {
	const mod = "github.com/onemindos/onemindos/"
	deps := map[string]bool{}
	for _, p := range goList(t, "list", "-deps", "../cmd/...") {
		deps[p] = true
	}
	for _, p := range goList(t, "list", "../internal/...") {
		name := strings.TrimPrefix(p, mod+"internal/")
		if strings.Contains(name, "tuftest") { // test helpers
			continue
		}
		if deps[p] {
			if why, ok := notWiredYet[name]; ok {
				t.Errorf("internal/%s is wired now; delete it from notWiredYet (%s)", name, why)
			}
			continue
		}
		if _, ok := notWiredYet[name]; !ok {
			t.Errorf("internal/%s is not used by any binary under cmd/. Wire it (docs/leap/core/PLUMBING.md sections 6-7) or list it in notWiredYet with its epic", name)
		}
	}
}

// TestSymbolsAreCalled covers what the package-level check cannot see (slop CS2-06): a finished
// function whose package is imported but which nothing calls. Each entry names a file under cmd/
// and the text that must be in it.
func TestSymbolsAreCalled(t *testing.T) {
	for _, c := range []struct{ file, text, why string }{
		{"onemindd/registry.go", "leafSupervisor.Service(", "leaf.Supervisor.Run supervises the NATS leaf (CORE-NET-12)"},
		{"onemindd/net.go", "fabric.Reporter(role, leafSupervisor.Link)", "the heartbeat's fabric.leaf_link reads the supervisor"},
		{"onemindd/net.go", "mesh.Reporter(log)", "the heartbeat's mesh object"},
	} {
		raw, err := os.ReadFile(c.file)
		if err != nil {
			t.Fatal(err)
		}
		if !strings.Contains(string(raw), c.text) {
			t.Errorf("%s no longer contains %q: %s", c.file, c.text, c.why)
		}
	}
}
