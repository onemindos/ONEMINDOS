// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"fmt"
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

func TestPermissionWritesReportQueuedActions(t *testing.T) {
	isolate(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method + " " + r.URL.Path {
		case "PUT /v1/permission-modes/agent:hermes",
			"DELETE /v1/approval-denies/den_1",
			"PATCH /v1/approval-policies/pol_1",
			"POST /v1/approval-policies/pol_1/confirm",
			"PUT /v1/agents/hermes/inputs":
			jsonOut(w, http.StatusAccepted, map[string]any{"id": "act_1", "state": "awaiting_approval", "requested_by": map[string]string{"id": "owner"}})
		default:
			t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
			http.NotFound(w, r)
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	for _, args := range [][]string{
		{"permissions", "mode", "set", "agent:hermes", "auto"},
		{"permissions", "deny", "remove", "den_1"},
		{"permissions", "rules", "narrow", "pol_1", "--per-day", "9"},
		{"permissions", "rules", "confirm", "pol_1"},
		{"agents", "inputs", "set", "hermes", "--none"},
	} {
		t.Run(strings.Join(args, "_"), func(t *testing.T) {
			result := run(t, "", false, args...)
			if result.code != 0 || result.out != "Request act_1 is waiting in Approvals.\n" {
				t.Fatalf("queued output %+v", result)
			}
			result = run(t, "", false, append(args, "--json")...)
			var action map[string]any
			if result.code != 0 || json.Unmarshal([]byte(result.out), &action) != nil ||
				action["id"] != "act_1" || action["state"] != "awaiting_approval" || action["requested_by"] == nil {
				t.Fatalf("queued JSON %+v", result)
			}
		})
	}
}

func TestPermissionsRulesShowWithHistoryAndRevokeAll(t *testing.T) {
	isolate(t)
	var revokeBody map[string]any
	var auditQuery string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/approval-policies":
			jsonOut(w, 200, []map[string]any{{"id": "pol_1", "revision": 2, "state": "active", "forever": false,
				"expires_at": "2027-01-01T00:00:00Z", "created_at": "2026-11-01T00:00:00Z", "uses": 3, "uses_24h": 1,
				"notify_after": "digest", "lapse_unused_days": 14, "limits": map[string]any{"per_day": 5, "max_uses": nil},
				"allow": map[string]any{"requested_by": []string{"agent:hermes"}, "types": []string{"backup.run"}}}})
		case r.Method == http.MethodGet && r.URL.Path == "/v1/audit/events":
			auditQuery = r.URL.RawQuery
			jsonOut(w, 200, []map[string]any{
				{"seq": 1, "ts": "2026-11-01T00:00:00Z", "event": "automation.policy.created", "data": map[string]any{"policy_id": "pol_1", "revision": 1}},
				{"seq": 2, "ts": "2026-11-02T00:00:00Z", "event": "approval.policy.revised", "data": map[string]any{"policy_id": "pol_9", "revision": 4}},
				{"seq": 3, "ts": "2026-11-03T00:00:00Z", "event": "approval.policy.revised", "data": map[string]any{"policy_id": "pol_1", "revision": 2}},
			})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/approval-policies/revoke-all":
			_ = json.NewDecoder(r.Body).Decode(&revokeBody)
			jsonOut(w, 200, map[string]any{"revoked": []string{"pol_1"}})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "permissions", "rules", "show", "pol_1")
	if r.code != 0 || !strings.Contains(r.out, "per day 5, max uses -, uses 3 (1 in 24 h)") ||
		!strings.Contains(r.out, "automation.policy.created rev 1") || !strings.Contains(r.out, "approval.policy.revised rev 2") ||
		strings.Contains(r.out, "rev 4") {
		t.Fatalf("show %+v", r)
	}
	if !strings.Contains(auditQuery, "since=2026-10-31T23%3A59%3A59Z") || !strings.Contains(auditQuery, "approval.policy.%2A") {
		t.Fatalf("audit query %q", auditQuery)
	}
	r = run(t, "", false, "permissions", "rules", "show", "pol_1", "--json")
	var out map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &out) != nil || len(out["history"].([]any)) != 2 {
		t.Fatalf("show --json %+v", r)
	}
	if r := run(t, "", false, "permissions", "rules", "show", "pol_x"); r.code != ExitNotFound {
		t.Fatalf("missing rule %+v", r)
	}
	r = run(t, "", false, "permissions", "rules", "revoke-all", "--principal", "agent:hermes")
	if r.code != 0 || !strings.Contains(r.out, "Revoked 1 rule(s). pol_1") || revokeBody["principal"] != "agent:hermes" {
		t.Fatalf("revoke-all %+v %v", r, revokeBody)
	}
	if r := run(t, "", false, "permissions", "rules", "revoke-all"); r.code != 0 || revokeBody["principal"] != nil {
		t.Fatalf("revoke-all every rule %+v %v", r, revokeBody)
	}
}

func TestPermissionsLogListsOnlyRuleApprovalsNewestFirst(t *testing.T) {
	isolate(t)
	var query string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/audit/events" {
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
			return
		}
		query = r.URL.RawQuery
		jsonOut(w, 200, []map[string]any{
			{"seq": 1, "ts": "2026-11-20T00:00:00Z", "action_id": "a1", "data": map[string]any{"type": "backup.run", "requested_by": "agent:hermes", "approved_via": "policy", "policy_id": "pol_1", "policy_revision": 2, "uses": "1/5"}},
			{"seq": 2, "ts": "2026-11-21T00:00:00Z", "action_id": "a2", "data": map[string]any{"type": "app.install", "approved_by": "owner"}},
			{"seq": 3, "ts": "2026-11-22T00:00:00Z", "action_id": "a3", "data": map[string]any{"type": "notes.read", "requested_by": "agent:reader", "approved_via": "policy", "policy_id": "pol_2", "policy_revision": 1, "uses": "2/5"}},
		})
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "permissions", "log", "--days", "7")
	if r.code != 0 || strings.Contains(r.out, "app.install") || strings.Index(r.out, "notes.read") > strings.Index(r.out, "backup.run") ||
		!strings.Contains(r.out, "rule pol_1 rev 2  (use 1/5)") {
		t.Fatalf("log %+v", r)
	}
	if !strings.Contains(query, "event=action.approved") || !strings.Contains(query, "since=") {
		t.Fatalf("query %q", query)
	}
	r = run(t, "", false, "permissions", "log", "--json")
	var out []map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &out) != nil || len(out) != 2 || out[0]["policy_id"] != "pol_2" {
		t.Fatalf("log --json %+v", r)
	}
	if r := run(t, "", false, "permissions", "log", "--days", "0"); r.code != ExitUsage {
		t.Fatalf("bad --days %+v", r)
	}
}

func TestSeqCursorIsAlwaysPlainDigits(t *testing.T) {
	for in, want := range map[any]string{float64(1): "1", float64(1000000): "1000000", float64(1234567): "1234567",
		float64(98765432101): "98765432101", json.Number("2000000"): "2000000", 7: "7", int64(3000000): "3000000",
		float64(1.5): "", float64(-1): "", nil: "", "12": "", json.Number("1e6"): ""} {
		if got := seqCursor(in); got != want {
			t.Errorf("seqCursor(%#v) = %q, want %q", in, got, want)
		}
	}
}

// A long-running box: more than 500 policy events, with seq past a million. Page 2 must ask for
// after_seq=<digits>, never 1.0005e+06 (the gateway answers 422 to that).
func TestPermissionsRulesShowPagesPastAMillion(t *testing.T) {
	isolate(t)
	var afters []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/approval-policies":
			jsonOut(w, 200, []map[string]any{{"id": "pol_1", "revision": 1, "state": "active", "created_at": "2026-11-01T00:00:00Z",
				"limits": map[string]any{}, "allow": map[string]any{"requested_by": []string{"agent:hermes"}, "types": []string{"backup.run"}}}})
		case r.Method == http.MethodGet && r.URL.Path == "/v1/audit/events":
			after := r.URL.Query().Get("after_seq")
			afters = append(afters, after)
			if after == "" {
				page := make([]map[string]any, 500)
				for i := range page {
					page[i] = map[string]any{"seq": 1000001 + i, "ts": "2026-11-02T00:00:00Z", "event": "approval.policy.revised",
						"data": map[string]any{"policy_id": "pol_other", "revision": 1}}
				}
				page[0]["data"] = map[string]any{"policy_id": "pol_1", "revision": 1}
				jsonOut(w, 200, page)
				return
			}
			if after != fmt.Sprint(1000500) {
				jsonOut(w, 422, map[string]string{"error": "conflict", "message": "after_seq must be an integer"})
				return
			}
			jsonOut(w, 200, []map[string]any{{"seq": 1000501, "ts": "2026-11-03T00:00:00Z", "event": "approval.policy.revoked",
				"data": map[string]any{"policy_id": "pol_1", "revision": 1}}})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "permissions", "rules", "show", "pol_1", "--json")
	var out map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &out) != nil {
		t.Fatalf("show --json %+v (after_seq sent: %v)", r, afters)
	}
	if h := out["history"].([]any); len(h) != 2 || len(afters) != 2 || afters[1] != "1000500" {
		t.Fatalf("history %d lines, after_seq sent %v", len(h), afters)
	}
}

// `permissions log` pages with the same helper: more than 500 approvals and seq past a million.
func TestPermissionsLogPagesPastAMillion(t *testing.T) {
	isolate(t)
	var afters []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/audit/events" {
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
			return
		}
		after := r.URL.Query().Get("after_seq")
		afters = append(afters, after)
		switch after {
		case "":
			page := make([]map[string]any, 500)
			for i := range page {
				page[i] = map[string]any{"seq": 1999501 + i, "ts": "2026-11-20T00:00:00Z", "action_id": fmt.Sprint("a", i),
					"data": map[string]any{"type": "backup.run", "requested_by": "agent:hermes", "approved_via": "policy", "policy_id": "pol_1", "policy_revision": 1}}
			}
			jsonOut(w, 200, page)
		case "2000000":
			jsonOut(w, 200, []map[string]any{{"seq": 2000001, "ts": "2026-11-21T00:00:00Z", "action_id": "last",
				"data": map[string]any{"type": "notes.read", "requested_by": "agent:reader", "approved_via": "policy", "policy_id": "pol_2", "policy_revision": 1}}})
		default:
			jsonOut(w, 422, map[string]string{"error": "conflict", "message": "after_seq must be an integer"})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "permissions", "log", "--json")
	var out []map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &out) != nil || len(out) != 501 || out[0]["action_id"] != "last" {
		t.Fatalf("log --json %d lines, after_seq sent %v: %+v", len(out), afters, r.errOut)
	}
}
