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

// A stand-in for the gateway's agent kill switch (CORE-SEC-6, #159): owner-only PUT, and every
// agent request refused with reason agents_stopped while it is on.
func killSwitchGW(t *testing.T) *httptest.Server {
	var mu sync.Mutex
	state := map[string]any{"on": false, "changed_by": nil, "changed_at": nil, "reason": nil}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		who := map[string]string{"Bearer " + ownerTok: "owner", "Bearer " + agentTok: "hermes"}[r.Header.Get("Authorization")]
		if who == "" {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "unknown token"})
			return
		}
		if who == "hermes" && state["on"] == true {
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "agents stopped", "reason": "agents_stopped"})
			return
		}
		if r.URL.Path != "/v1/agents/kill-switch" {
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
			return
		}
		if r.Method == http.MethodPut {
			if who != "owner" {
				jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "only the owner"})
				return
			}
			var b map[string]any
			_ = json.NewDecoder(r.Body).Decode(&b)
			state = map[string]any{"on": b["on"], "changed_by": map[string]any{"id": "owner", "kind": "person", "role": "owner"},
				"changed_at": "2026-11-18T12:00:00Z", "reason": b["reason"]}
		}
		jsonOut(w, 200, state)
	}))
	t.Cleanup(srv.Close)
	return srv
}

func TestAgentsKillSwitchOwnerStopsAndResumes(t *testing.T) {
	isolate(t)
	srv := killSwitchGW(t)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	if r := run(t, "", false, "agents", "status", "--quiet"); r.code != 0 || strings.TrimSpace(r.out) != "running" {
		t.Fatalf("status %+v", r)
	}
	r := run(t, "", false, "agents", "stop", "--reason", "looking into it")
	if r.code != 0 || !strings.Contains(r.out, "STOPPED") || !strings.Contains(r.out, "looking into it") {
		t.Fatalf("stop %+v", r)
	}
	// An agent cannot resume: the gateway refuses it at the door while agents are stopped.
	t.Setenv("ONEMIND_TOKEN", agentTok)
	if r := run(t, "", false, "agents", "resume"); r.code != ExitPermissionDenied {
		t.Fatalf("agent resume %+v", r)
	}
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r = run(t, "", false, "agents", "resume", "--json")
	var s map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &s) != nil || s["on"] != false {
		t.Fatalf("resume %+v", r)
	}
	// With agents running, an agent still may not stop or resume them.
	t.Setenv("ONEMIND_TOKEN", agentTok)
	if r := run(t, "", false, "agents", "stop"); r.code != ExitPermissionDenied {
		t.Fatalf("agent stop %+v", r)
	}
	if r := run(t, "", false, "agents"); r.code != ExitUsage {
		t.Fatalf("bare group %+v", r)
	}
}
