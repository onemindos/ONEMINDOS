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

// A stand-in for /v1/approval-denies: anyone signed in adds, only the owner removes, and removing
// asks for a passkey step-up until the test says it was given.
func denyGW(t *testing.T, stepUp *bool) (*httptest.Server, *[]map[string]any) {
	var mu sync.Mutex
	rows := []map[string]any{}
	bodies := []map[string]any{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		owner := r.Header.Get("Authorization") == "Bearer "+ownerTok
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/approval-denies":
			jsonOut(w, 200, rows)
		case r.Method == http.MethodPost && r.URL.Path == "/v1/approval-denies":
			var b map[string]any
			_ = json.NewDecoder(r.Body).Decode(&b)
			bodies = append(bodies, b)
			row := map[string]any{"id": "den_1", "principal": b["principal"], "action_type": b["action_type"],
				"tier": b["tier"], "reason": b["reason"]}
			rows = append(rows, row)
			jsonOut(w, 201, row)
		case r.Method == http.MethodDelete && r.URL.Path == "/v1/approval-denies/den_1":
			if !owner {
				jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "owner only"})
				return
			}
			if !*stepUp {
				jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "step up", "reason": "step_up_required"})
				return
			}
			rows = rows[:0]
			w.WriteHeader(204)
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	return srv, &bodies
}

func TestPermissionsDenyAddListRemove(t *testing.T) {
	isolate(t)
	stepped := false
	srv, bodies := denyGW(t, &stepped)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	if r := run(t, "", false, "permissions", "deny", "list"); r.code != 0 || !strings.Contains(r.out, "No deny rules") {
		t.Fatalf("empty list %+v", r)
	}
	r := run(t, "", false, "permissions", "deny", "add", "agent:hermes", "--tier", "T3", "--reason", "never delete")
	if r.code != 0 || !strings.Contains(r.out, "agent:hermes may never: every T3 request (never delete)") {
		t.Fatalf("add %+v", r)
	}
	if got, _ := json.Marshal((*bodies)[0]); string(got) != `{"principal":"agent:hermes","reason":"never delete","tier":"T3"}` {
		t.Fatalf("body %s", got)
	}
	r = run(t, "", false, "permissions", "deny", "list", "--json")
	var out []map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &out) != nil || len(out) != 1 || out[0]["id"] != "den_1" {
		t.Fatalf("list %+v", r)
	}
	// Removing loosens: without a fresh passkey the gateway refuses and the CLI says what to do.
	if r := run(t, "", false, "permissions", "deny", "remove", "den_1"); r.code != ExitUsage || !strings.Contains(r.errOut, "passkey") {
		t.Fatalf("remove without step-up %+v", r)
	}
	stepped = true
	if r := run(t, "", false, "permissions", "deny", "remove", "den_1"); r.code != 0 || !strings.Contains(r.out, "Removed") {
		t.Fatalf("remove %+v", r)
	}
	// One of --type or --tier, never both or neither.
	if r := run(t, "", false, "permissions", "deny", "add", "agent:hermes"); r.code != ExitUsage {
		t.Fatalf("neither %+v", r)
	}
	if r := run(t, "", false, "permissions", "deny", "add", "agent:hermes", "--tier", "T1", "--type", "app.restart"); r.code != ExitUsage {
		t.Fatalf("both %+v", r)
	}
}

// A stand-in for the rules routes: revoke needs nothing more; a PATCH that raises per_day widens and
// answers step_up_required; lowering it applies.
func TestPermissionsRulesListRevokeNarrow(t *testing.T) {
	isolate(t)
	var mu sync.Mutex
	var patches []map[string]any
	rule := map[string]any{"id": "pol_1", "revision": 1, "state": "active", "forever": true, "expires_at": nil,
		"allow": map[string]any{"types": []any{"backup.run"}, "requested_by": []any{"agent:notes"}}, "review_due": true}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/approval-policies":
			jsonOut(w, 200, []map[string]any{rule})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/approval-policies/pol_1/revoke":
			rule["state"] = "revoked"
			jsonOut(w, 200, rule)
		case r.Method == http.MethodPatch && r.URL.Path == "/v1/approval-policies/pol_1":
			var b map[string]any
			_ = json.NewDecoder(r.Body).Decode(&b)
			patches = append(patches, b)
			if l, ok := b["limits"].(map[string]any); ok && l["per_day"].(float64) > 5 {
				jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "widen", "reason": "step_up_required"})
				return
			}
			rule["revision"] = 2
			jsonOut(w, 200, rule)
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "permissions", "rules", "list")
	if r.code != 0 || !strings.Contains(r.out, "FOREVER") || !strings.Contains(r.out, "review due") || !strings.Contains(r.out, "agent:notes may backup.run") {
		t.Fatalf("list %+v", r)
	}
	if r := run(t, "", false, "permissions", "rules", "narrow", "pol_1", "--per-day", "2"); r.code != 0 || !strings.Contains(r.out, "rev 2") {
		t.Fatalf("narrow %+v", r)
	}
	if got, _ := json.Marshal(patches[0]); string(got) != `{"limits":{"per_day":2}}` {
		t.Fatalf("patch %s", got)
	}
	if r := run(t, "", false, "permissions", "rules", "narrow", "pol_1", "--per-day", "9"); r.code != ExitUsage || !strings.Contains(r.errOut, "passkey") {
		t.Fatalf("widen %+v", r)
	}
	if r := run(t, "", false, "permissions", "rules", "narrow", "pol_1"); r.code != ExitUsage {
		t.Fatalf("nothing to narrow %+v", r)
	}
	r = run(t, "", false, "permissions", "rules", "revoke", "pol_1", "--json")
	var out map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &out) != nil || out["state"] != "revoked" {
		t.Fatalf("revoke %+v", r)
	}
}

func TestPermissionsModeGetSet(t *testing.T) {
	isolate(t)
	var mu sync.Mutex
	state := map[string]any{"principal": "agent:hermes", "mode": "ask", "own": false, "owner_passkey": false}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/permission-modes/agent:hermes":
			jsonOut(w, 200, state)
		case r.Method == http.MethodPut && r.URL.Path == "/v1/permission-modes/agent:hermes":
			var b map[string]any
			_ = json.NewDecoder(r.Body).Decode(&b)
			if b["mode"] == "auto" && state["owner_passkey"] == false {
				jsonOut(w, 409, map[string]string{"error": "conflict", "message": "add a passkey first", "reason": "no_owner_passkey"})
				return
			}
			state["mode"], state["own"] = b["mode"], true
			jsonOut(w, 200, state)
		case r.Method == http.MethodPut && r.URL.Path == "/v1/permission-modes":
			jsonOut(w, 200, map[string]any{"principal": "*", "mode": "ask", "own": true, "owner_passkey": true})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "permissions", "mode", "get", "agent:hermes")
	if r.code != 0 || !strings.Contains(r.out, "agent:hermes: Always ask (household default)") || !strings.Contains(r.out, "No owner passkey") {
		t.Fatalf("get %+v", r)
	}
	if r := run(t, "", false, "permissions", "mode", "set", "agent:hermes", "auto"); r.code != ExitUsage || !strings.Contains(r.errOut, "add a passkey first") {
		t.Fatalf("loosen before passkey %+v", r)
	}
	if r := run(t, "", false, "permissions", "mode", "set", "agent:hermes", "locked", "--reason", "pause"); r.code != 0 || !strings.Contains(r.out, "Locked") {
		t.Fatalf("lock %+v", r)
	}
	if r := run(t, "", false, "permissions", "mode", "set", "agent:hermes", "sideways"); r.code != ExitUsage {
		t.Fatalf("bad mode %+v", r)
	}
	if r := run(t, "", false, "permissions", "mode", "set", "default", "ask", "--json"); r.code != 0 || !strings.Contains(r.out, `"principal": "*"`) {
		t.Fatalf("default %+v", r)
	}
}
