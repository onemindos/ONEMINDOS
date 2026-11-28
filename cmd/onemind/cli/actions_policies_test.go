// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

// A stand-in for /v1/approval-policies: owner only; with stepUp set (passkeys active) create and confirm
// answer step_up_required, like the gateway.
func policiesGW(t *testing.T, stepUp bool) (*httptest.Server, *[]string, *[]map[string]any) {
	var mu sync.Mutex
	seen := []string{}
	bodies := []map[string]any{}
	pol := map[string]any{"id": "pol_1", "revision": 1, "name": "Nightly", "state": "paused", "uses_24h": 1,
		"allow":  map[string]any{"types": []any{"app.restart"}, "requested_by": []any{"agent:hermes"}, "params": map[string]any{}},
		"limits": map[string]any{"per_day": 3}, "window_id": nil, "expires_at": "2026-12-20T00:00:00Z"}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		seen = append(seen, r.Method+" "+r.URL.Path)
		if r.URL.Path == "/v1/instance" {
			w.Header().Set("Date", time.Now().UTC().Format(http.TimeFormat))
			jsonOut(w, 200, map[string]any{"name": "box"})
			return
		}
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "only the owner"})
			return
		}
		up := func() bool {
			if stepUp {
				jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "confirm it is you", "reason": "step_up_required"})
			}
			return stepUp
		}
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/approval-policies":
			jsonOut(w, 200, []any{pol})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/approval-policies":
			var b map[string]any
			_ = json.NewDecoder(r.Body).Decode(&b)
			bodies = append(bodies, b)
			if up() {
				return
			}
			jsonOut(w, 201, map[string]any{"id": "pol_2", "expires_at": b["expires_at"], "state": "active"})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/approval-policies/pol_1/confirm":
			if up() {
				return
			}
			pol["state"] = "active"
			jsonOut(w, 200, pol)
		case r.Method == http.MethodDelete && r.URL.Path == "/v1/approval-policies/pol_1":
			w.WriteHeader(http.StatusNoContent)
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	return srv, &seen, &bodies
}

func TestActionsPoliciesListCreateConfirmRemove(t *testing.T) {
	isolate(t)
	srv, seen, bodies := policiesGW(t, false)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "actions", "policies", "list")
	if r.code != 0 || !strings.Contains(r.out, "pol_1") || !strings.Contains(r.out, "1/3") || !strings.Contains(r.out, "any time") {
		t.Fatalf("list %+v", r)
	}
	r = run(t, "", false, "actions", "policies", "create", "--type", "app.restart", "--from", "agent:hermes", "--per-day", "2", "--days", "7",
		"--window", "win_nightly", "--name", "Nightly", "--params", `{"app_id":{"enum":["notes"]}}`)
	if r.code != 0 || !strings.Contains(r.out, "pol_2 created") {
		t.Fatalf("create %+v", r)
	}
	b := (*bodies)[0]
	exp, err := time.Parse(time.RFC3339, b["expires_at"].(string))
	if err != nil || exp.Sub(time.Now()) < 6*24*time.Hour || exp.Sub(time.Now()) > 8*24*time.Hour {
		t.Fatalf("expires_at %v", b["expires_at"])
	}
	delete(b, "expires_at")
	if got, _ := json.Marshal(b); string(got) != `{"allow":{"params":{"app_id":{"enum":["notes"]}},"requested_by":["agent:hermes"],"types":["app.restart"]},"limits":{"per_day":2},"name":"Nightly","window_id":"win_nightly"}` {
		t.Fatalf("body %s", got)
	}
	if r := run(t, "", false, "--json", "actions", "policies", "confirm", "pol_1"); r.code != 0 || !strings.Contains(r.out, `"state": "active"`) {
		t.Fatalf("confirm %+v", r)
	}
	if r := run(t, "", false, "standing", "remove", "pol_1"); r.code == 0 {
		t.Fatalf("the alias lives under actions, not the root: %+v", r)
	}
	if r := run(t, "", false, "actions", "standing", "remove", "pol_1"); r.code != 0 || !strings.Contains(r.out, "wait for a person again") {
		t.Fatalf("remove %+v", r)
	}
	if !strings.Contains(strings.Join(*seen, "\n"), "DELETE /v1/approval-policies/pol_1") {
		t.Fatalf("no delete: %v", *seen)
	}
	for _, bad := range [][]string{{"create"}, {"create", "--type", "a.b", "--from", "agent:x", "--days", "91"},
		{"create", "--type", "a.b", "--from", "agent:x", "--per-day", "0"}, {"create", "--type", "a.b", "--from", "agent:x", "--params", "[1]"}} {
		if r := run(t, "", false, append([]string{"actions", "policies"}, bad...)...); r.code != ExitUsage {
			t.Fatalf("%v: %+v", bad, r)
		}
	}
	t.Setenv("ONEMIND_TOKEN", agentTok)
	if r := run(t, "", false, "actions", "policies", "list"); r.code != ExitPermissionDenied {
		t.Fatalf("agent list %+v", r)
	}
}

// With passkeys active a token cannot create or re-enable one; the CLI says where to do it.
func TestActionsPoliciesStepUpPointsToTheDashboard(t *testing.T) {
	isolate(t)
	srv, _, _ := policiesGW(t, true)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	for _, args := range [][]string{{"create", "--type", "app.restart", "--from", "agent:hermes"}, {"confirm", "pol_1"}} {
		r := run(t, "", false, append([]string{"actions", "policies"}, args...)...)
		if r.code != ExitUsage || !strings.Contains(r.errOut, "Settings > Standing approvals") {
			t.Fatalf("%v: %+v", args, r)
		}
	}
	if r := run(t, "", false, "actions", "policies", "remove", "pol_1"); r.code != 0 {
		t.Fatalf("remove needs no step-up: %+v", r)
	}
}
