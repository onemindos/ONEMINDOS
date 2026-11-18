// SPDX-License-Identifier: Apache-2.0

package rescue

import (
	"reflect"
	"testing"
)

// The pty never runs the shell itself: it runs onemindd's helper, which drops every capability, then the shell.
func TestShellStartsThroughTheCapabilityDropper(t *testing.T) {
	got, err := shellArgv("/usr/bin/onemindd", "/bin/sh")
	if err != nil {
		t.Fatal(err)
	}
	if want := []string{"/usr/bin/onemindd", "rescue-shell", "--", "/bin/sh"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("argv = %q, want %q", got, want)
	}
	if sh, err := helperShell(got[2:]); err != nil || sh != "/bin/sh" {
		t.Fatalf("the helper reads its own argv as %q, %v", sh, err)
	}
	for _, bad := range [][2]string{{"onemindd", "/bin/sh"}, {"/usr/bin/onemindd", "sh"}, {"/usr/bin/onemindd", ""}} {
		if _, err := shellArgv(bad[0], bad[1]); err == nil {
			t.Errorf("shellArgv(%q, %q) accepted a relative path: PATH would pick the program", bad[0], bad[1])
		}
	}
	for _, bad := range [][]string{nil, {"/bin/sh"}, {"--", "sh"}, {"--", "/bin/sh", "-c", "id"}, {"-x", "/bin/sh"}} {
		if _, err := helperShell(bad); err == nil {
			t.Errorf("helperShell(%q) accepted", bad)
		}
	}
}
