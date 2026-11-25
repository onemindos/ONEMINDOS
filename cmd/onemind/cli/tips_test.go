// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"io"
	"testing"
)

func TestTipsAuthoringCommands(t *testing.T) {
	root, _ := NewRoot(Env{Stdout: io.Discard, Stderr: io.Discard})
	for _, name := range []string{"check", "new", "preview"} {
		cmd, args, err := root.Find([]string{"tips", name})
		if err != nil || len(args) != 0 || cmd.CommandPath() != "onemind tips "+name || cmd.RunE == nil {
			t.Fatalf("tips %s unavailable: remaining %v, err %v", name, args, err)
		}
	}
}
