// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestAutomationRulesRunsAndSwitch(t *testing.T) {
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/automation/rules": ok([]any{
			map[string]any{"id": "rul_1", "name": "Nightly backup", "enabled": true, "trigger": map[string]any{"schedule": map[string]any{"cron": "0 2 * * *"}}, "last_fired_at": "2026-11-25T02:00:00Z", "breaker": nil},
			map[string]any{"id": "rul_2", "name": "On alert", "enabled": false, "trigger": map[string]any{"event": map[string]any{"type": "alert.opened"}}}}),
		"GET /v1/automation/rules/rul_1": ok(map[string]any{"id": "rul_1", "name": "Nightly backup", "enabled": true, "revision": 2.0,
			"trigger": map[string]any{"schedule": map[string]any{"cron": "0 2 * * *", "tz": "box"}}, "conditions": []any{},
			"actions": []any{map[string]any{"type": "backup.run", "params": map[string]any{}}}, "options": map[string]any{"window_id": "win_nightly"}}),
		"POST /v1/automation/rules": func(b map[string]any) (int, any) { return 201, map[string]any{"id": "rul_3", "name": b["name"]} },
		"POST /v1/automation/rules/rul_2/enable": func(map[string]any) (int, any) {
			return 409, map[string]any{"error": "conflict", "message": "dry-run it first"}
		},
		"POST /v1/automation/rules/rul_1/disable": ok(map[string]any{"id": "rul_1", "enabled": false}),
		"POST /v1/automation/rules/rul_1/dry-run": ok(map[string]any{"id": "dry_1", "rule_id": "rul_1", "revision": 2.0, "from": "2026-11-26T00:00:00Z",
			"to": "2026-12-03T00:00:00Z", "would_request": []any{map[string]any{"at": "2026-11-27T02:00:00Z", "index": 0.0, "type": "backup.run",
				"params": map[string]any{}, "risk": "low", "verdict": "needs_approval"}}, "skipped": []any{map[string]any{"at": "2026-11-28T02:00:00Z", "reason": "skipped_window"}},
			"policy_outcome": "needs_approval", "truncated": false, "source": "schedule"}),
		"DELETE /v1/automation/rules/rul_1":  func(map[string]any) (int, any) { return 204, nil },
		"GET /v1/automation/runs":            ok([]any{map[string]any{"fired_at": "2026-11-25T02:00:00Z", "rule_id": "rul_1", "outcome": "filed", "action_ids": []any{"act_1"}}}),
		"GET /v1/automation/schedules":       ok([]any{map[string]any{"rule_id": "rul_1", "name": "Nightly backup", "enabled": true, "cron": "0 2 * * *", "tz": "box", "next_fire_at": "2026-11-26T02:00:00Z"}}),
		"GET /v1/automation/state":           ok(map[string]any{"paused": true, "changed_by": "usr_1", "changed_at": "2026-11-26T00:00:00Z", "reason": "away"}),
		"POST /v1/automation/pause":          ok(map[string]any{"paused": true}),
		"POST /v1/automation/resume":         ok(map[string]any{"paused": false}),
		"GET /v1/approval-policies":          ok([]any{map[string]any{"id": "pol_1", "name": "Nightly restart", "state": "active", "limits": map[string]any{"per_day": 3.0}, "uses_24h": 1.0, "expires_at": "2027-01-01T00:00:00Z"}}),
		"DELETE /v1/approval-policies/pol_1": func(map[string]any) (int, any) { return 204, nil },
		"GET /v1/windows":                    ok([]any{map[string]any{"id": "win_nightly", "name": "Nights", "tz": "box", "open_now": true, "ranges": []any{map[string]any{"days": []any{"mon"}, "start": "01:00", "end": "05:00"}}}}),
		"PUT /v1/windows/win_nightly": func(map[string]any) (int, any) {
			return 401, map[string]any{"error": "unauthenticated", "reason": "step_up_required", "message": "sign in again"}
		},
	})
	outHas(t, run(t, "", false, "automation", "rules", "list").out, "rul_1", "schedule 0 2 * * *", "event alert.opened", "yes", "no")
	r := run(t, "", false, "automation", "rules", "show", "rul_1")
	outHas(t, r.out, "Nightly backup", "schedule 0 2 * * *", "backup.run", "win_nightly", "--json")
	if strings.Contains(r.out, "{") {
		t.Fatalf("show prints text, not JSON: %s", r.out)
	}
	if obj(jsonOf(t, run(t, "", false, "automation", "rules", "show", "rul_1", "--json").out))["revision"] != 2.0 {
		t.Fatal("show --json")
	}
	f := filepath.Join(t.TempDir(), "r.json")
	_ = os.WriteFile(f, []byte(`{"name": "Mine", "trigger": {"manual": {}}}`), 0o600)
	outHas(t, run(t, "", false, "automation", "rules", "create", "--file", f).out, "rul_3", "off", "dry-run")
	r = run(t, "", false, "automation", "rules", "enable", "rul_2")
	if r.code == 0 || !strings.Contains(r.errOut, "dry-run") {
		t.Fatalf("enable must report the gateway's refusal: %+v", r)
	}
	outHas(t, run(t, "", false, "automation", "rules", "disable", "rul_1").out, "Turned off rul_1")
	r = run(t, "", false, "automation", "rules", "dry-run", "rul_1")
	outHas(t, r.out, "nothing was done", "backup.run", "needs_approval", "Skipped 1", "A person would have to approve")
	if strings.Contains(r.out, "{") {
		t.Fatalf("dry-run prints text, not JSON: %s", r.out)
	}
	if obj(jsonOf(t, run(t, "", false, "automation", "rules", "dry-run", "rul_1", "--json").out))["policy_outcome"] != "needs_approval" {
		t.Fatal("dry-run --json")
	}
	if r := run(t, "", false, "automation", "rules", "delete", "rul_1"); r.code != ExitUsage || len(g.sent("DELETE", "/v1/automation/rules/rul_1")) != 0 {
		t.Fatalf("needs --yes %+v", r)
	}
	if r := run(t, "", false, "automation", "rules", "delete", "rul_1", "--yes", "--json"); r.code != 0 || obj(jsonOf(t, r.out))["deleted"] != true {
		t.Fatalf("delete %+v", r)
	}
	outHas(t, run(t, "", false, "automation", "runs", "--rule", "rul_1", "--limit", "5").out, "filed", "act_1")
	if q := g.sent("GET", "/v1/automation/runs")[0].query; !strings.Contains(q, "rule_id=rul_1") || !strings.Contains(q, "limit=5") {
		t.Fatalf("runs query %q", q)
	}
	outHas(t, run(t, "", false, "automation", "schedules").out, "0 2 * * * box", "2026-11-26")
	outHas(t, run(t, "", false, "automation", "state").out, "PAUSED", "away")
	run(t, "", false, "automation", "pause", "--reason", "holiday")
	if g.sent("POST", "/v1/automation/pause")[0].body["reason"] != "holiday" {
		t.Fatal("pause reason")
	}
	outHas(t, run(t, "", false, "automation", "resume").out, "running again")
	outHas(t, run(t, "", false, "automation", "policies", "list").out, "pol_1", "Nightly restart", "active", "3", "1")
	if r := run(t, "", false, "automation", "policies", "revoke", "pol_1"); r.code != ExitUsage {
		t.Fatalf("needs --yes %+v", r)
	}
	if r := run(t, "", false, "automation", "policies", "revoke", "pol_1", "--yes"); r.code != 0 {
		t.Fatalf("revoke %+v", r)
	}
	outHas(t, run(t, "", false, "automation", "windows", "list").out, "win_nightly", "yes", `"start":"01:00"`)
	wf := filepath.Join(t.TempDir(), "w.json")
	_ = os.WriteFile(wf, []byte(`{"name": "Nights", "tz": "box", "ranges": []}`), 0o600)
	r = run(t, "", false, "automation", "windows", "set", "win_nightly", "--file", wf)
	if r.code == 0 || !strings.Contains(r.errOut, "passkey") {
		t.Fatalf("window step-up must be explained: %+v", r)
	}
	g.neverApproved(t)
}

func TestAlertsAndMonitoring(t *testing.T) {
	g := newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/alerts": ok([]any{
			map[string]any{"id": "alrt_1", "severity": "warning", "state": "open", "title": "No backup in 3 days", "opened_at": "2026-11-23T00:00:00Z", "fix": map[string]any{"type": "backup.run"}},
			map[string]any{"id": "alrt_2", "severity": "info", "state": "acknowledged", "title": "Update available", "opened_at": "2026-11-24T00:00:00Z", "fix": nil}}),
		"GET /v1/alerts/alrt_1":          ok(map[string]any{"id": "alrt_1", "severity": "warning", "state": "open", "title": "No backup", "body": "Last backup was 3 days ago", "opened_at": "x", "occurrences": 2.0, "fix": map[string]any{"type": "backup.run"}}),
		"POST /v1/alerts/alrt_1/ack":     ok(map[string]any{"id": "alrt_1", "state": "acknowledged"}),
		"POST /v1/alerts/alrt_1/resolve": ok(map[string]any{"id": "alrt_1", "state": "resolved"}),
		"POST /v1/alerts/alrt_1/fix":     waitingAction,
		"GET /v1/monitoring/summary": ok(map[string]any{"nodes": map[string]any{"online": 2.0, "stale": 0.0, "offline": 1.0},
			"apps":        map[string]any{"healthy": 5.0, "unhealthy": 1.0, "starting": 0.0, "stopped": 0.0, "unknown": 0.0},
			"open_alerts": map[string]any{"info": 1.0, "warning": 2.0, "critical": 0.0}, "storage": []any{map[string]any{"node_id": "hub1", "state": "protected"}}, "at": "2026-11-26T00:00:00Z"}),
	})
	out := run(t, "", false, "alerts", "list").out
	outHas(t, out, "alrt_1", "No backup in 3 days", "yes", "alrt_2", "acknowledged")
	if g.sent("GET", "/v1/alerts")[0].query != "state=open" {
		t.Fatalf("default is open: %q", g.sent("GET", "/v1/alerts")[0].query)
	}
	outHas(t, run(t, "", false, "alerts", "show", "alrt_1").out, "Last backup was 3 days ago", "backup.run", "approved by a person")
	outHas(t, run(t, "", false, "alerts", "ack", "alrt_1").out, "Acknowledged alrt_1")
	outHas(t, run(t, "", false, "alerts", "resolve", "alrt_1").out, "Resolved alrt_1")
	r := run(t, "", false, "alerts", "fix", "alrt_1", "--reason", "now")
	outHas(t, r.out, "Requested", "act_7", "onemind actions approve act_7")
	if b := g.sent("POST", "/v1/alerts/alrt_1/fix")[0].body; b["approve"] != nil || b["reason"] != "now" {
		t.Fatalf("fix body %+v", b)
	}
	g.neverApproved(t)
	outHas(t, run(t, "", false, "monitoring", "summary").out, "2 online, 0 stale, 1 offline", "5 healthy, 1 unhealthy", "0 critical, 2 warning", "storage on hub1", "protected")
	if r := run(t, "", false, "monitoring", "summary", "--json"); obj(obj(jsonOf(t, r.out))["nodes"])["offline"] != 1.0 {
		t.Fatalf("json %+v", r)
	}
}

func TestAlertsEmptyAndAgentRefused(t *testing.T) {
	newRouteGW(t, map[string]func(map[string]any) (int, any){
		"GET /v1/alerts": ok([]any{}),
		"POST /v1/alerts/a1/resolve": func(map[string]any) (int, any) {
			return 403, map[string]any{"error": "permission_denied", "message": "only owners resolve alerts"}
		},
	})
	outHas(t, run(t, "", false, "alerts", "list").out, "Nothing needs your attention")
	if r := run(t, "", false, "alerts", "resolve", "a1"); r.code == 0 || !strings.Contains(r.errOut, "only owners") {
		t.Fatalf("a refusal must reach the person: %+v", r)
	}
}
