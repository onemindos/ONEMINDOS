// SPDX-License-Identifier: Apache-2.0
package cli

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// #943: the fabric id comes from first boot's per-machine node_id (or ONEMIND_NODE_ID), never from a
// machine-id that every machine built from one image may share.
func TestFabricNodeIDPrefersFirstBoot(t *testing.T) {
	dir := t.TempDir()
	state := func(name, body string) string {
		p := filepath.Join(dir, name)
		if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
		return p
	}
	const shared = "5b2c0f1e9a3d" // sha256(machine-id) of the image, the same on every machine

	got, err := fabricNodeID("", state("a.json", `{"node_id": "a1b2c3d4e5f6", "name": "Garage Pi"}`), shared)
	if err != nil || got != "a1b2c3d4e5f6" {
		t.Fatalf("first boot node_id: %q %v", got, err)
	}
	got, err = fabricNodeID("envid0001", state("b.json", `{"node_id": "a1b2c3d4e5f6"}`), shared)
	if err != nil || got != "envid0001" {
		t.Fatalf("ONEMIND_NODE_ID wins, as in onemind node info: %q %v", got, err)
	}
	for _, body := range []string{`{}`, `not json`, `{"node_id": "Not/Valid"}`, `{"node_id": ""}`} {
		got, err = fabricNodeID("", state("c.json", body), shared)
		if err != nil || got != shared {
			t.Fatalf("no usable first boot id in %q must fall back to the detected id: %q %v", body, got, err)
		}
	}
	got, err = fabricNodeID("", filepath.Join(dir, "missing.json"), shared)
	if err != nil || got != shared {
		t.Fatalf("missing state: %q %v", got, err)
	}
	if _, err = fabricNodeID("Bad_ID", "", shared); err == nil || !strings.Contains(err.Error(), "ONEMIND_NODE_ID") {
		t.Fatalf("an env id the hub would refuse must fail here, got %v", err)
	}
}

func TestTwoNodesFromOneImageGetDifferentFabricIDs(t *testing.T) {
	const shared = "5b2c0f1e9a3d"
	ids := map[string]bool{}
	for i, id := range []string{"0c1d2e3f4a5b", "9f8e7d6c5b4a"} { // first boot draws a random id on each machine
		p := filepath.Join(t.TempDir(), "state.json")
		if err := os.WriteFile(p, []byte(`{"node_id": "`+id+`"}`), 0o644); err != nil {
			t.Fatal(err)
		}
		got, err := fabricNodeID("", p, shared)
		if err != nil {
			t.Fatal(err)
		}
		if got == shared {
			t.Fatalf("node %d joined with the image-wide id", i)
		}
		ids[got] = true
	}
	if len(ids) != 2 {
		t.Fatalf("two nodes from one image must ask to join with two ids, got %v", ids)
	}
}
