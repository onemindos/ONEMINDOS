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
