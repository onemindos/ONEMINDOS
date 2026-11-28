// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

// A hub that answers /v1/os/updates and files actions, and records what was asked.
type rollbackGW struct {
	mu      sync.Mutex
	nodes   []any
	actions []map[string]any
	approve int
}

func (g *rollbackGW) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	g.mu.Lock()
	defer g.mu.Unlock()
	if r.Header.Get("Authorization") != "Bearer "+agentTok {
		jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "unknown token"})
		return
	}
	switch {
	case r.URL.Path == "/v1/os/updates":
		jsonOut(w, 200, map[string]any{"nodes": g.nodes})
	case r.URL.Path == "/v1/actions" && r.Method == http.MethodPost:
		var b map[string]any
		_ = json.NewDecoder(r.Body).Decode(&b)
		a := map[string]any{"id": "act-rb", "type": b["type"], "params": b["params"], "state": "awaiting_approval"}
		g.actions = append(g.actions, a)
		jsonOut(w, 201, a)
	case strings.HasSuffix(r.URL.Path, "/approve"):
		g.approve++
		jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "no"})
	default:
		jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no"})
	}
}

func node(id string, available bool, version, msg string) map[string]any {
	return map[string]any{"node_id": id, "hostname": id, "current_version": "0.1.1",
		"rollback": map[string]any{"available": available, "version": version, "slot": "B", "message": msg}}
}

func TestUpdateRollbackFilesARequestAndNeverApproves(t *testing.T) {
	isolate(t)
	g := &rollbackGW{nodes: []any{node("hub1", true, "0.1.0", "")}}
	srv := httptest.NewServer(g)
	defer srv.Close()
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", agentTok)
	r := run(t, "", false, "update", "rollback", "--json")
	var a map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &a) != nil || a["state"] != "awaiting_approval" || a["type"] != "os.rollback" {
		t.Fatalf("rollback %+v", r)
	}
	if p, _ := a["params"].(map[string]any); p["node_id"] != "hub1" || p["version"] != "0.1.0" || len(p) != 2 {
		t.Fatalf("params %v", p)
	}
	if r := run(t, "", false, "update", "rollback"); r.code != 0 || !strings.Contains(r.out, "0.1.1 to 0.1.0") || !strings.Contains(r.out, "passkey") {
		t.Fatalf("text %+v", r)
	}
	if r := run(t, "", false, "update", "rollback", "--quiet"); r.code != 0 || strings.TrimSpace(r.out) != "act-rb" {
		t.Fatalf("quiet %+v", r)
	}
	if g.approve != 0 || len(g.actions) != 3 {
		t.Fatalf("approvals %d actions %d", g.approve, len(g.actions))
	}
}

func TestUpdateRollbackRefusesWhenThereIsNothingSafeToGoBackTo(t *testing.T) {
	isolate(t)
	g := &rollbackGW{nodes: []any{node("hub1", false, "", "Slot B is not marked good (bad)")}}
	srv := httptest.NewServer(g)
	defer srv.Close()
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", agentTok)
	if r := run(t, "", false, "update", "rollback"); r.code == 0 || !strings.Contains(r.errOut, "not marked good") {
		t.Fatalf("%+v", r)
	}
	g.nodes = []any{node("hub1", true, "0.1.0", ""), node("edge2", true, "0.1.0", "")}
	if r := run(t, "", false, "update", "rollback"); r.code == 0 || !strings.Contains(r.errOut, "--node") {
		t.Fatalf("two machines without --node: %+v", r)
	}
	if r := run(t, "", false, "update", "rollback", "--node", "ghost"); r.code == 0 || !strings.Contains(r.errOut, "ghost") {
		t.Fatalf("unknown node: %+v", r)
	}
	if r := run(t, "", false, "update", "rollback", "--node", "edge2", "--version", "9.9.9"); r.code == 0 || !strings.Contains(r.errOut, "0.1.0") {
		t.Fatalf("version pin: %+v", r)
	}
	if len(g.actions) != 0 {
		t.Fatalf("a refused rollback filed a request: %v", g.actions)
	}
	if r := run(t, "", false, "update", "rollback", "--node", "edge2", "--version", "0.1.0", "--quiet"); r.code != 0 {
		t.Fatalf("pinned: %+v", r)
	}
}
