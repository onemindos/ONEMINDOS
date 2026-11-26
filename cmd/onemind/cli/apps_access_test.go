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

// A stand-in for GET and PUT /v1/apps/{id}/access: owner only, replaces the lists; widening answers
// step_up_required when stepUp is set (passkeys active), like the gateway.
func accessGW(t *testing.T, stepUp bool) (*httptest.Server, *[]map[string]any) {
	var mu sync.Mutex
	bodies := []map[string]any{}
	state := map[string]any{"app_id": "notes", "roles": []any{"owner", "adult"}, "people": []any{map[string]any{"id": "usr_gus", "display_name": "Gus"}}, "auth": "onemind"}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "only the owner"})
			return
		}
		if r.URL.Path != "/v1/apps/notes/access" {
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
			return
		}
		if r.Method == http.MethodPut {
			var b map[string]any
			_ = json.NewDecoder(r.Body).Decode(&b)
			bodies = append(bodies, b)
			if stepUp && len(b["roles"].([]any)) > 0 {
				jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "confirm it is you", "reason": "step_up_required"})
				return
			}
			roles := append([]any{"owner"}, b["roles"].([]any)...)
			ppl := []any{}
			for _, id := range b["people"].([]any) {
				ppl = append(ppl, map[string]any{"id": id, "display_name": "Person"})
			}
			state["roles"], state["people"], state["auth"] = roles, ppl, b["auth"]
		}
		jsonOut(w, 200, state)
	}))
	t.Cleanup(srv.Close)
	return srv, &bodies
}

func TestAppsAccessGetAndSet(t *testing.T) {
	isolate(t)
	srv, bodies := accessGW(t, false)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "apps", "access", "get", "notes")
	if r.code != 0 || !strings.Contains(r.out, "Gus (usr_gus)") || !strings.Contains(r.out, "OneMind sign-in") {
		t.Fatalf("get %+v", r)
	}
	// Flags left out keep their current value: only the roles change here, Gus stays.
	r = run(t, "", false, "apps", "access", "set", "notes", "--role", "guest")
	if r.code != 0 {
		t.Fatalf("set %+v", r)
	}
	if got, _ := json.Marshal((*bodies)[0]); string(got) != `{"auth":"onemind","people":["usr_gus"],"roles":["guest"]}` {
		t.Fatalf("body %s", got)
	}
	r = run(t, "", false, "--json", "apps", "access", "set", "notes", "--none", "--auth", "app")
	var out map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &out) != nil || out["auth"] != "app" {
		t.Fatalf("none %+v", r)
	}
	if got, _ := json.Marshal((*bodies)[1]); string(got) != `{"auth":"app","people":[],"roles":[]}` {
		t.Fatalf("none body %s", got)
	}
	for _, bad := range [][]string{{"set", "notes"}, {"set", "notes", "--none", "--role", "guest"}, {"set", "notes", "--auth", "sso"}} {
		if r := run(t, "", false, append([]string{"apps", "access"}, bad...)...); r.code != ExitUsage {
			t.Fatalf("%v: %+v", bad, r)
		}
	}
	t.Setenv("ONEMIND_TOKEN", agentTok)
	if r := run(t, "", false, "apps", "access", "set", "notes", "--none"); r.code != ExitPermissionDenied {
		t.Fatalf("agent set %+v", r)
	}
}

// Once passkeys are active a token cannot widen sharing; the CLI says where to do it, and narrowing works.
func TestAppsAccessWideningNeedsTheDashboard(t *testing.T) {
	isolate(t)
	srv, _ := accessGW(t, true)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "apps", "access", "set", "notes", "--role", "guest")
	if r.code != ExitUsage || !strings.Contains(r.errOut, "Settings > Permissions > By app") {
		t.Fatalf("step-up %+v", r)
	}
	if r := run(t, "", false, "apps", "access", "set", "notes", "--none"); r.code != 0 {
		t.Fatalf("narrowing %+v", r)
	}
}
