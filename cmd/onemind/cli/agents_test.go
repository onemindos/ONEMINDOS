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

// A stand-in for PUT and GET /v1/agents/{id}/inputs: owner only, replaces the list.
func inputsGW(t *testing.T) (*httptest.Server, *[]map[string]any) {
	var mu sync.Mutex
	bodies := []map[string]any{}
	state := map[string]any{"id": "agent:hermes", "external_inputs": []any{}, "accept_injection_risk": []any{}}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "only the owner"})
			return
		}
		if r.URL.EscapedPath() != "/v1/agents/agent:hermes/inputs" && r.URL.Path != "/v1/agents/agent:hermes/inputs" {
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
			return
		}
		if r.Method == http.MethodPut {
			var b map[string]any
			_ = json.NewDecoder(r.Body).Decode(&b)
			bodies = append(bodies, b)
			state["external_inputs"], state["accept_injection_risk"] = b["external_inputs"], b["accept_injection_risk"]
		}
		jsonOut(w, 200, state)
	}))
	t.Cleanup(srv.Close)
	return srv, &bodies
}

func TestAgentsInputsSetAndGet(t *testing.T) {
	isolate(t)
	srv, bodies := inputsGW(t)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "agents", "inputs", "get", "agent:hermes")
	if r.code != 0 || !strings.Contains(r.out, "reads nothing outside") {
		t.Fatalf("get %+v", r)
	}
	r = run(t, "", false, "agents", "inputs", "set", "agent:hermes", "--web", "--files", "--accept-risk", "app.restart")
	if r.code != 0 || !strings.Contains(r.out, "web, files") || !strings.Contains(r.out, "app.restart") {
		t.Fatalf("set %+v", r)
	}
	b := (*bodies)[0]
	if got, _ := json.Marshal(b); string(got) != `{"accept_injection_risk":["app.restart"],"external_inputs":["web","files"]}` {
		t.Fatalf("body %s", got)
	}
	r = run(t, "", false, "agents", "inputs", "set", "agent:hermes", "--none", "--json")
	var s map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &s) != nil || len(s["external_inputs"].([]any)) != 0 {
		t.Fatalf("none %+v", r)
	}
	// Nothing said is a usage error, not a silent "reads nothing"; the two cannot be combined.
	if r := run(t, "", false, "agents", "inputs", "set", "agent:hermes"); r.code != ExitUsage {
		t.Fatalf("empty set %+v", r)
	}
	if r := run(t, "", false, "agents", "inputs", "set", "agent:hermes", "--none", "--web"); r.code != ExitUsage {
		t.Fatalf("none+web %+v", r)
	}
	t.Setenv("ONEMIND_TOKEN", agentTok)
	if r := run(t, "", false, "agents", "inputs", "set", "agent:hermes", "--none"); r.code != ExitPermissionDenied {
		t.Fatalf("agent set %+v", r)
	}
}

// Once passkeys are active a token-only caller cannot loosen an agent; the CLI says what to do, and
// a default (never declared) agent does not look like an owner declaration.
func TestAgentsInputsStepUpAndDefaultWording(t *testing.T) {
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPut {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "sign in again", "reason": "step_up_required"})
			return
		}
		jsonOut(w, 200, map[string]any{"id": "agent:hermes", "external_inputs": []any{"undeclared"}, "declared": false,
			"accept_injection_risk": []any{}})
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "agents", "inputs", "get", "agent:hermes")
	if r.code != 0 || !strings.Contains(r.out, "default") || !strings.Contains(r.out, "not declared") {
		t.Fatalf("get %+v", r)
	}
	r = run(t, "", false, "agents", "inputs", "set", "agent:hermes", "--none")
	if r.code != ExitUsage || !strings.Contains(r.errOut, "passkey in the dashboard") {
		t.Fatalf("step-up %+v", r)
	}
}
