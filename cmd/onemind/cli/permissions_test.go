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
