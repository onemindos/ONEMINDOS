// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// settingsGW is rollbackGW plus PUT /v1/os/settings, which fills a field left out from the node like the gateway.
type settingsGW struct{ rollbackGW }

func (g *settingsGW) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/v1/os/settings" {
		g.rollbackGW.ServeHTTP(w, r)
		return
	}
	g.mu.Lock()
	defer g.mu.Unlock()
	if r.Method != http.MethodPut || r.Header.Get("Authorization") != "Bearer "+agentTok {
		jsonOut(w, 405, map[string]string{"error": "conflict", "message": "no"})
		return
	}
	var b map[string]any
	_ = json.NewDecoder(r.Body).Decode(&b)
	params := map[string]any{"node_id": b["node_id"], "policy": "notify", "window": "02:00-05:00"}
	for _, k := range []string{"policy", "window"} {
		if v, ok := b[k]; ok {
			params[k] = v
		}
	}
	a := map[string]any{"id": "act-set", "type": "os.update.settings", "params": params, "state": "awaiting_approval", "sent": b}
	g.actions = append(g.actions, a)
	jsonOut(w, 202, a)
}

func settingsNode(id string) map[string]any {
	return map[string]any{"node_id": id, "reported": true, "channel": "security", "policy": "notify", "window": "02:00-05:00", "settings_source": "image"}
}

// REL-02 (#154): `onemind update settings set` files os.update.settings for the owner, keeps the value
// of a flag left out, and never approves.
func TestUpdateSettingsSetFilesARequestAndNeverApproves(t *testing.T) {
	isolate(t)
	g := &settingsGW{rollbackGW{nodes: []any{settingsNode("hub1")}}}
	srv := httptest.NewServer(g)
	defer srv.Close()
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", agentTok)
	if r := run(t, "", false, "update", "settings", "show"); r.code != 0 || !strings.Contains(r.out, "02:00-05:00") || !strings.Contains(r.out, "image") {
		t.Fatalf("show %+v", r)
	}
	r := run(t, "", false, "update", "settings", "set", "--policy", "off", "--json")
	var a map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &a) != nil || a["type"] != "os.update.settings" {
		t.Fatalf("set %+v", r)
	}
	if p, _ := a["params"].(map[string]any); p["node_id"] != "hub1" || p["policy"] != "off" || p["window"] != "02:00-05:00" || len(p) != 3 {
		t.Fatalf("params %v", p)
	}
	if sent, _ := a["sent"].(map[string]any); sent["window"] != nil || sent["policy"] != "off" { // a flag left out is not sent
		t.Fatalf("sent %v", sent)
	}
	if r := run(t, "", false, "update", "settings", "set", "--window", "01:00-03:00"); r.code != 0 || !strings.Contains(r.out, "policy notify, window 01:00-03:00") || !strings.Contains(r.out, "passkey") {
		t.Fatalf("text %+v", r)
	}
	if g.approve != 0 || len(g.actions) != 2 {
		t.Fatalf("approvals %d actions %d", g.approve, len(g.actions))
	}
}

func TestUpdateSettingsSetRefusesBadInput(t *testing.T) {
	isolate(t)
	g := &settingsGW{rollbackGW{nodes: []any{settingsNode("hub1"), settingsNode("edge2")}}}
	srv := httptest.NewServer(g)
	defer srv.Close()
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", agentTok)
	for _, args := range [][]string{
		{"--node", "hub1"},                          // nothing to change
		{"--node", "hub1", "--policy", "sometimes"}, // bad policy
		{"--node", "hub1", "--window", "25:00-01:00"},
		{"--policy", "off"},                    // two machines, no --node
		{"--node", "ghost", "--policy", "off"}, // unknown machine
	} {
		if r := run(t, "", false, append([]string{"update", "settings", "set"}, args...)...); r.code == 0 {
			t.Errorf("%v accepted: %+v", args, r)
		}
	}
	if len(g.actions) != 0 {
		t.Fatalf("a refused change filed a request: %v", g.actions)
	}
}
