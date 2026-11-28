// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"io"
	"os"
	"regexp"
	"strings"
	"testing"
)

// The desktop launcher and command palette show "the exact onemind command" for each action (#844, final design
// 03). Every `onemind ...` line in ui/src/shell/palette.ts must name a real command and real flags, so a person can
// paste it into a terminal. Template parts (${app.id}) stand for an argument.
var paletteLine = regexp.MustCompile("[`'](onemind [^`']+)[`']")

func TestPaletteCLILinesResolve(t *testing.T) {
	src, err := os.ReadFile("../../../ui/src/shell/palette.ts")
	if err != nil {
		t.Fatal(err)
	}
	lines := paletteLine.FindAllStringSubmatch(string(src), -1)
	if len(lines) < 8 {
		t.Fatalf("found %d onemind lines in palette.ts; the pattern no longer matches the file", len(lines))
	}
	for _, m := range lines {
		words := strings.Fields(m[1])[1:]
		var path, flags []string
		pathDone := false
		for _, w := range words {
			switch {
			case strings.HasPrefix(w, "--"):
				flags = append(flags, strings.SplitN(strings.TrimPrefix(w, "--"), "=", 2)[0])
				pathDone = true
			case strings.Contains(w, "${") || pathDone:
				pathDone = true // an argument (or a flag's value): the command path has ended
			default:
				path = append(path, w)
			}
		}
		root, _ := NewRoot(Env{Stdout: io.Discard, Stderr: io.Discard})
		cmd, rest, err := root.Find(path)
		if err != nil || len(rest) != 0 || cmd.CommandPath() != "onemind "+strings.Join(path, " ") {
			t.Errorf("%q: %v is not a command (resolved %q, left %v, err %v)", m[1], path, cmd.CommandPath(), rest, err)
			continue
		}
		if cmd.RunE == nil && cmd.Run == nil {
			t.Errorf("%q: %q is a group, not a runnable command", m[1], cmd.CommandPath())
		}
		for _, f := range flags {
			if cmd.Flags().Lookup(f) == nil && cmd.InheritedFlags().Lookup(f) == nil {
				t.Errorf("%q: %q has no --%s flag", m[1], cmd.CommandPath(), f)
			}
		}
	}
}
