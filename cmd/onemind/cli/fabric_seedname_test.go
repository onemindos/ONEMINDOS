// SPDX-License-Identifier: Apache-2.0
package cli

import (
	"os"
	"path/filepath"
	"testing"
)

func TestSeedName(t *testing.T) {
	dir := t.TempDir()
	w := func(body string) string {
		p := filepath.Join(dir, "state.json")
		if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
		return p
	}
	if got := seedName(w(`{"name": "Garage Pi"}`)); got != "Garage Pi" {
		t.Fatalf("seed name: %q", got)
	}
	if got := seedName(w(`{"name": "OneMind"}`)); got != "" {
		t.Fatalf("default name must fall back to the hostname, got %q", got)
	}
	if got := seedName(w(`not json`)); got != "" {
		t.Fatalf("bad json: %q", got)
	}
	if got := seedName(filepath.Join(dir, "missing.json")); got != "" {
		t.Fatalf("missing file: %q", got)
	}
	if hostLabel("Garage Pi") != "Garage-Pi" {
		t.Fatal("the seed name becomes a DNS label")
	}
}
