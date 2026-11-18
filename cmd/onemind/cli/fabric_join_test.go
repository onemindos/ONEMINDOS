// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// --code-file (IMG-MESH-01, #292): the OS image keeps the join text in a 0600 file, so it never
// appears in the process list.
func TestFabricJoinCodeFile(t *testing.T) {
	old := isRoot
	isRoot = func() bool { return false } // stop right after the code is parsed
	t.Cleanup(func() { isRoot = old })

	dir := t.TempDir()
	qr := "onemind-join:v1?code=7KQ4-M2XP-9D3F&ca=" + strings.Repeat("ab", 32) + "&role=leaf&hub=https%3A%2F%2Fbox.local"
	good := filepath.Join(dir, "join-code")
	if err := os.WriteFile(good, []byte(qr+"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	empty := filepath.Join(dir, "empty")
	if err := os.WriteFile(empty, []byte("\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	for _, c := range []struct {
		name string
		args []string
		want string
	}{
		{"read and parsed", []string{"--code-file", good}, "run as root"},
		{"empty file", []string{"--code-file", empty}, "file is empty"},
		{"missing file", []string{"--code-file", filepath.Join(dir, "nope")}, "--code-file"},
		{"not with the text", []string{qr, "--code-file", good}, "give only one"},
		{"not with --code", []string{"--code", "7KQ4-M2XP-9D3F", "--code-file", good}, "give only one"},
	} {
		err := fabricJoin(c.args, io.Discard)
		if err == nil || !strings.Contains(err.Error(), c.want) {
			t.Errorf("%s: got %v, want an error containing %q", c.name, err, c.want)
		}
	}
}
