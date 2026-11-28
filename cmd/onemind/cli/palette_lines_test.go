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
		var path []string
		for _, w := range words {
			if strings.HasPrefix(w, "-") || strings.Contains(w, "${") {
				break // the command path ends at the first flag or argument
			}
			path = append(path, w)
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
		// The rest: flags (each must exist; a non-bool flag without "=" takes the next word) and positional arguments,
		// which must satisfy the command's Args rule (an ID-taking command shown without its ID would fail at once).
		var args []string
		tail := words[len(path):]
		for k := 0; k < len(tail); k++ {
			w := tail[k]
			if !strings.HasPrefix(w, "--") {
				args = append(args, w)
				continue
			}
			name, _, hasValue := strings.Cut(strings.TrimPrefix(w, "--"), "=")
			f := cmd.Flags().Lookup(name)
			if f == nil {
				f = cmd.InheritedFlags().Lookup(name)
			}
			if f == nil {
				t.Errorf("%q: %q has no --%s flag", m[1], cmd.CommandPath(), name)
				continue
			}
			if !hasValue && f.Value.Type() != "bool" {
				k++ // the flag's value
			}
		}
		if err := cmd.ValidateArgs(args); err != nil {
			t.Errorf("%q: arguments %v rejected by %q: %v", m[1], args, cmd.CommandPath(), err)
		}
	}
}
