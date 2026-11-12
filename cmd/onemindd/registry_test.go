// SPDX-License-Identifier: Apache-2.0

package main

import "testing"

func TestRegistry(t *testing.T) {
	if subcommands["update"] == nil {
		t.Fatal("onemindd update must stay registered")
	}
	seen := map[string]bool{}
	for _, s := range optionalServices {
		if s.Name == "" || s.Run == nil || seen[s.Name] {
			t.Errorf("optional service %q needs a unique name and a Run func", s.Name)
		}
		seen[s.Name] = true
		if subcommands[s.Name] != nil {
			t.Errorf("%q is both a subcommand and an optional service", s.Name)
		}
	}
}
