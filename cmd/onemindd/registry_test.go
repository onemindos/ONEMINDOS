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

func TestRescueLoopbackOnlyWithoutTLS(t *testing.T) {
	for addr, want := range map[string]bool{"127.0.0.1:7443": true, "[::1]:7443": true, "localhost:7443": true,
		":7443": false, "0.0.0.0:7443": false, "192.0.2.1:7443": false, "bad": false} {
		if loopbackAddr(addr) != want {
			t.Errorf("loopbackAddr(%q) != %v", addr, want)
		}
	}
	if subcommands["rescue"] == nil {
		t.Fatal("onemindd rescue must be registered")
	}
	// No certificate in the TLS dir and a LAN listen address: refuse to serve plain HTTP.
	if rc := runRescue([]string{"-listen", ":0", "-tls-dir", t.TempDir()}); rc != 2 {
		t.Fatalf("runRescue without TLS on all interfaces = %d, want 2", rc)
	}
}
