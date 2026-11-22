// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/onemindos/onemindos/internal/mesh"
)

// fakeTS answers `tailscale status --json` with a fixed document (example
// mesh addresses from 100.64.0.0/10).
type fakeTS struct{ out string }

func (f fakeTS) Run(context.Context, ...string) ([]byte, error) { return []byte(f.out), nil }

func TestMeshStatus(t *testing.T) {
	old := newMeshClient
	defer func() { newMeshClient = old }()
	newMeshClient = func() *mesh.Client {
		return &mesh.Client{Runner: fakeTS{`{"BackendState":"Running","Self":{"TailscaleIPs":["100.64.0.5"]},` +
			`"Peer":{"k":{"HostName":"hub","Tags":["tag:onemind-hub"],"CurAddr":"203.0.113.10:41641","Online":true}}}`}, Now: time.Now}
	}
	l, _ := net.Listen("tcp", "127.0.0.1:0")
	srv := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"leafnodes":1,"leafs":[{"name":"hub","rtt":"1.2ms"}]}`))
	})}
	go srv.Serve(l)
	defer srv.Close()

	var out bytes.Buffer
	if err := meshCmd([]string{"status", "--leaf-monitor", l.Addr().String()}, &out); err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"state:", "up", "100.64.0.5", "hub: direct", "nats leaf: up (rtt 1.2ms)"} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("missing %q in:\n%s", want, out.String())
		}
	}
	out.Reset()
	if err := meshCmd([]string{"status", "--json", "--leaf-monitor", l.Addr().String()}, &out); err != nil {
		t.Fatal(err)
	}
	var v struct {
		Mesh mesh.State
		Leaf struct{ State string }
	}
	if err := json.Unmarshal(out.Bytes(), &v); err != nil || v.Mesh.State != "up" || v.Leaf.State != "up" {
		t.Fatalf("%v %+v", err, v)
	}
	if err := meshCmd(nil, &out); err == nil {
		t.Fatal("missing subcommand accepted")
	}
}

// fakeMeshHub serves GET /v1/mesh and PUT /v1/mesh/settings like the gateway (CORE-NET-8): only
// the owner changes the state, and turning the mesh on with no provider is refused.
type fakeMeshHub struct {
	settings map[string]any
	puts     []map[string]any
}

func (h *fakeMeshHub) view() map[string]any {
	setup := map[string]any{"state": "not_set_up", "reason": "no_provider", "detail": "No mesh provider is chosen.",
		"next_step": "Choose the mesh provider: onemind mesh settings --provider headscale --enable (owner only)."}
	if h.settings["provider"] != nil {
		setup = map[string]any{"state": "off", "reason": "disabled", "detail": "The mesh is off.",
			"next_step": "Turn the mesh on: onemind mesh settings --enable (owner only)."}
		if h.settings["enabled"] == true {
			setup = map[string]any{"state": "ready", "reason": nil, "detail": "The mesh is on (headscale).", "next_step": nil}
		}
	}
	return map[string]any{"mode": "off", "settings": h.settings, "setup": setup}
}

func (h *fakeMeshHub) serve(w http.ResponseWriter, r *http.Request) {
	who := map[string]string{"Bearer " + ownerTok: "owner", "Bearer " + agentTok: "hermes"}[r.Header.Get("Authorization")]
	switch {
	case who == "":
		jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "unknown token"})
	case r.Method == http.MethodGet && r.URL.Path == "/v1/mesh":
		jsonOut(w, 200, h.view())
	case r.Method == http.MethodPut && r.URL.Path == "/v1/mesh/settings":
		if who != "owner" {
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "agent/agent may not change the mesh settings"})
			return
		}
		var b map[string]any
		_ = json.NewDecoder(r.Body).Decode(&b)
		h.puts = append(h.puts, b)
		next := map[string]any{}
		for k, v := range h.settings {
			next[k] = v
		}
		for k, v := range b {
			next[k] = v
		}
		if next["provider"] == "none" {
			next["provider"] = nil
		}
		if next["enabled"] == true && next["provider"] == nil {
			jsonOut(w, 409, map[string]string{"error": "conflict", "message": "No mesh provider is chosen.", "reason": "mesh_no_provider"})
			return
		}
		next["saved"] = true
		h.settings = next
		jsonOut(w, 200, h.view())
	default:
		jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no such resource"})
	}
}

func TestMeshSettingsShowsAndChangesTheHubsMesh(t *testing.T) {
	isolate(t)
	h := &fakeMeshHub{settings: map[string]any{"enabled": false, "provider": nil,
		"control_url": "https://control.onemind.internal:8444", "saved": false, "updated_at": nil, "updated_by": nil}}
	srv := httptest.NewServer(http.HandlerFunc(h.serve))
	defer srv.Close()
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)

	r := run(t, "", false, "mesh", "settings")
	if r.code != 0 || !strings.Contains(r.out, "not_set_up") || !strings.Contains(r.out, "none chosen") ||
		!strings.Contains(r.out, "onemind mesh settings --provider headscale --enable") || len(h.puts) != 0 {
		t.Fatalf("show: %+v puts %v", r, h.puts)
	}
	if r := run(t, "", false, "mesh", "settings", "--enable"); r.code == 0 || !strings.Contains(r.errOut, "provider") {
		t.Fatalf("enable with no provider: %+v", r)
	}
	r = run(t, "", false, "mesh", "settings", "--provider", "headscale", "--enable", "--json")
	var v meshView
	if r.code != 0 || json.Unmarshal([]byte(r.out), &v) != nil || v.Setup.State != "ready" || !v.Settings.Enabled ||
		v.Settings.Provider == nil || *v.Settings.Provider != "headscale" {
		t.Fatalf("enable: %+v", r)
	}
	if last := h.puts[len(h.puts)-1]; len(last) != 2 || last["provider"] != "headscale" || last["enabled"] != true {
		t.Fatalf("PUT body %v", last)
	}
	if r := run(t, "", false, "mesh", "settings", "--disable"); r.code != 0 || !strings.Contains(r.out, "off") {
		t.Fatalf("disable: %+v", r)
	}
	if r := run(t, "", false, "mesh", "settings", "--enable", "--disable"); r.code != ExitUsage {
		t.Fatalf("both flags: %+v", r)
	}
	// an agent reads the state but cannot change it: the hub refuses and the CLI says so
	t.Setenv("ONEMIND_TOKEN", agentTok)
	n := len(h.puts)
	if r := run(t, "", false, "mesh", "settings", "--enable"); r.code == 0 || len(h.puts) != n {
		t.Fatalf("agent change: %+v", r)
	}
	if r := run(t, "", false, "mesh", "settings"); r.code != 0 {
		t.Fatalf("agent read: %+v", r)
	}
}

// `onemind mesh status` still reaches the local status command once `mesh` has a subcommand.
func TestMeshStatusStillRoutesThroughTheRoot(t *testing.T) {
	isolate(t)
	old := newMeshClient
	defer func() { newMeshClient = old }()
	newMeshClient = func() *mesh.Client {
		return &mesh.Client{Runner: fakeTS{`{"BackendState":"Running","Self":{"TailscaleIPs":["100.64.0.5"]},"Peer":{}}`}, Now: time.Now}
	}
	r := run(t, "", false, "mesh", "status", "--json", "--leaf-monitor", "127.0.0.1:1")
	var v struct{ Mesh mesh.State }
	if r.code != 0 || json.Unmarshal([]byte(r.out), &v) != nil || v.Mesh.State != "up" {
		t.Fatalf("%+v", r)
	}
}
