// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"strings"
	"testing"
)

// `onemind machines create|start|stop|delete` only files a request that waits for an owner; the
// command never approves, so an agent token can run it and still never actuate (MACH-01, #281).
func TestMachinesRequestsWaitForAnOwner(t *testing.T) {
	isolate(t)
	g := newFakeGW(t)
	t.Setenv("ONEMIND_HUB", g.srv.URL)
	t.Setenv("ONEMIND_TOKEN", agentTok)
	r := run(t, "", false, "machines", "create", "win", "--ram-mb", "4096", "--cpus", "2", "--disk-gb", "40",
		"--image-url", "https://images.example.org/d.qcow2", "--json")
	var a map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &a) != nil || a["state"] != "awaiting_approval" || a["type"] != "machine.create" {
		t.Fatalf("create %+v", r)
	}
	p, _ := a["params"].(map[string]any)
	if p["name"] != "win" || p["ram_mb"] != float64(4096) || p["image_url"] != "https://images.example.org/d.qcow2" {
		t.Fatalf("params %v", p)
	}
	if r := run(t, "", false, "machines", "start", "win"); r.code != 0 || !strings.Contains(r.out, "onemind actions approve") {
		t.Fatalf("start %+v", r)
	}
	if r := run(t, "", false, "machines", "delete", "win", "--confirm", "win", "--quiet"); r.code != 0 || !strings.HasPrefix(r.out, "act-") {
		t.Fatalf("delete %+v", r)
	}
	for _, x := range g.actions { // none was approved by the CLI
		if x["state"] != "awaiting_approval" {
			t.Fatalf("an action left the waiting state: %v", x)
		}
	}
	if r := run(t, "", false, "machines", "create", "win"); r.code == 0 {
		t.Fatalf("create without --image-url accepted: %+v", r)
	}
}

// restart, force-stop, snapshot and clone are requests too: each waits for an owner, and the
// snapshot list is a plain read.
func TestMachinesLifecycleRequestsWaitForAnOwner(t *testing.T) {
	isolate(t)
	g := newFakeGW(t)
	t.Setenv("ONEMIND_HUB", g.srv.URL)
	t.Setenv("ONEMIND_TOKEN", agentTok)
	want := map[string]map[string]any{
		"machine.restart":    {"name": "win"},
		"machine.force_stop": {"name": "win"},
		"machine.snapshot":   {"name": "win", "snapshot": "before"},
		"machine.clone":      {"source": "win", "name": "copy"},
	}
	for _, args := range [][]string{{"restart", "win"}, {"force-stop", "win"}, {"snapshot", "win", "--snapshot", "before"}, {"clone", "win", "copy"}} {
		r := run(t, "", false, append([]string{"machines"}, append(args, "--json")...)...)
		var a map[string]any
		if r.code != 0 || json.Unmarshal([]byte(r.out), &a) != nil || a["state"] != "awaiting_approval" {
			t.Fatalf("%v: %+v", args, r)
		}
		typ, _ := a["type"].(string)
		w, ok := want[typ]
		p, _ := a["params"].(map[string]any)
		if !ok || len(p) != len(w) {
			t.Fatalf("%v: type %q params %v", args, typ, p)
		}
		for k, v := range w {
			if p[k] != v {
				t.Fatalf("%v: param %s = %v, want %v", args, k, p[k], v)
			}
		}
		delete(want, typ)
	}
	if len(want) != 0 {
		t.Fatalf("not filed: %v", want)
	}
	if r := run(t, "", false, "machines", "snapshot", "win"); r.code == 0 {
		t.Fatalf("snapshot without --snapshot accepted: %+v", r)
	}
	if r := run(t, "", false, "machines", "clone", "win"); r.code == 0 {
		t.Fatalf("clone without a new name accepted: %+v", r)
	}
	for _, x := range g.actions {
		if x["state"] != "awaiting_approval" {
			t.Fatalf("an action left the waiting state: %v", x)
		}
	}
}
