// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

// recGW is a small recorded gateway for the commands over existing routes: canned answers shaped
// like the real ones (core/onemind_core routers), and a log of every request so a test can prove
// what was sent and that nothing was approved.
type recGW struct {
	mu  sync.Mutex
	log []rec
	srv *httptest.Server
	// stepUp makes the direct owner creation route answer the step-up error.
	stepUp bool
	// noAISchedule makes GET /v1/update-policy leave ai_schedule out.
	noAISchedule bool
	// noInstall makes GET /v1/os/updates say the box has no host service to install with.
	noInstall bool
	// replayState makes POST /v1/backups/*, /v1/restores and /v1/actions answer as a replay of an
	// action already in this state (a repeat key), and conflict makes them answer the 409 for a key
	// used by a different request.
	replayState string
	conflict    bool
}

type rec struct {
	method, path, query string
	body                map[string]any
	idem                string // the Idempotency-Key header
}

func newRecGW(t *testing.T) *recGW {
	g := &recGW{}
	g.srv = httptest.NewServer(http.HandlerFunc(g.serve))
	t.Cleanup(g.srv.Close)
	t.Setenv("ONEMIND_HUB", g.srv.URL)
	return g
}

func (g *recGW) requests(method, path string) []rec {
	g.mu.Lock()
	defer g.mu.Unlock()
	var out []rec
	for _, r := range g.log {
		if r.method == method && r.path == path {
			out = append(out, r)
		}
	}
	return out
}

func (g *recGW) serve(w http.ResponseWriter, r *http.Request) {
	g.mu.Lock()
	defer g.mu.Unlock()
	var body map[string]any
	if raw, _ := io.ReadAll(r.Body); len(raw) > 0 {
		_ = json.Unmarshal(raw, &body)
	}
	g.log = append(g.log, rec{r.Method, r.URL.Path, r.URL.RawQuery, body, r.Header.Get("Idempotency-Key")})
	who := map[string]string{"Bearer " + ownerTok: "owner", "Bearer " + agentTok: "agent"}[r.Header.Get("Authorization")]
	if who == "" {
		jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "unknown token"})
		return
	}
	denyAgent := func() bool {
		if who == "agent" {
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "agent/agent may not do this"})
		}
		return who == "agent"
	}
	waiting := func(typ string, params any) map[string]any {
		st := "awaiting_approval"
		if g.replayState != "" {
			st = g.replayState
		}
		return map[string]any{"id": "act_1", "type": typ, "params": params, "state": st}
	}
	if g.conflict && r.Method == http.MethodPost && (strings.HasPrefix(r.URL.Path, "/v1/backups/") || r.URL.Path == "/v1/restores" || r.URL.Path == "/v1/actions") {
		jsonOut(w, 409, map[string]string{"error": "conflict", "message": "idempotency_key was already used for a different request"})
		return
	}
	switch p := r.URL.Path; {
	case p == "/v1/instance":
		jsonOut(w, 200, map[string]any{"name": "Box", "version": "0.1.0", "hub_node_id": "hub1"})
	case p == "/v1/users" && r.Method == http.MethodGet:
		if denyAgent() {
			return
		}
		jsonOut(w, 200, []any{
			map[string]any{"id": "usr_1", "username": "zeus", "display_name": "Zeus", "role": "owner", "enrolled": true, "disabled": false, "last_seen_at": "2026-11-25T01:00:00Z"},
			map[string]any{"id": "usr_2", "username": nil, "display_name": "Mia", "role": "teen", "enrolled": false, "disabled": false, "last_seen_at": nil},
			map[string]any{"id": "usr_3", "username": "old", "display_name": "Old", "role": "guest", "enrolled": true, "disabled": true, "last_seen_at": nil},
		})
	case p == "/v1/users" && r.Method == http.MethodPost:
		if denyAgent() {
			return
		}
		if g.stepUp {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "reason": "step_up_required", "message": "sign in again with your passkey to do this"})
			return
		}
		jsonOut(w, 201, map[string]any{"id": "usr_9", "display_name": body["display_name"], "role": body["role"],
			"one_time": map[string]any{"enrolment_code": "CODE", "enrolment_url": "https://box.example/signin#enrol=CODE", "expires_at": "2026-11-26T00:00:00Z"}})
	case p == "/v1/users/usr_2/invite" && r.Method == http.MethodPost:
		if denyAgent() {
			return
		}
		jsonOut(w, 202, waiting("users.reinvite", map[string]string{"user_id": "usr_2"}))
	case p == "/v1/users/usr_2/disable":
		jsonOut(w, 200, map[string]any{"id": "usr_2", "disabled": true})
	case p == "/v1/backups/status":
		jsonOut(w, 200, map[string]any{"health": "ok", "last_success_at": "2026-11-25T02:00:00Z", "last_verified_restore_at": nil,
			"next_run_at": "2026-11-26T02:00:00Z", "copies": 2, "agent": "ok", "reason": nil, "kit": map[string]any{"state": "confirmed"}})
	case p == "/v1/backups/snapshots" && r.URL.Query().Get("app_id") == "nodest":
		// a hub with no backup destination yet answers 200 with an empty list, not an error or a wait
		w.Header().Set("OneMind-Reason", "no backup destination yet")
		jsonOut(w, 200, []any{})
	case p == "/v1/backups/snapshots":
		jsonOut(w, 200, []any{map[string]any{"id": "abcd1234", "taken_at": "2026-11-25T02:00:00Z", "unit": "app:photos"}})
	case p == "/v1/backups/runs", p == "/v1/backups/verify":
		jsonOut(w, 202, waiting("backup.run", body))
	case p == "/v1/restores":
		if denyAgent() {
			return
		}
		jsonOut(w, 202, waiting("backup.restore", body))
	case p == "/v1/care/checkup":
		if denyAgent() {
			return
		}
		jsonOut(w, 200, []any{
			map[string]any{"id": "backup", "state": "finding", "detail": "No backup in 3 days.", "fix": "backup.run"},
			map[string]any{"id": "disk", "state": "clear", "detail": "Disks healthy.", "fix": nil},
		})
	case p == "/v1/update-policy" && r.Method == http.MethodGet:
		pol := map[string]any{"window_id": "win_nightly", "cool_off_hours": 48, "same_major_only": true, "backoff_after_failures": 3,
			"ai_schedule": map[string]any{"enabled": true, "tz": "box", "off": []any{map[string]any{"days": []any{"mon"}, "start": "23:00", "end": "07:00"}}},
			"customized":  false, "updated_at": nil, "updated_by": nil, "paused_apps": []any{}}
		if g.noAISchedule {
			delete(pol, "ai_schedule")
		}
		jsonOut(w, 200, pol)
	case p == "/v1/update-policy" && r.Method == http.MethodPut:
		if denyAgent() {
			return
		}
		jsonOut(w, 200, body)
	case p == "/v1/os/updates":
		install := map[string]any{"available": true, "reason": nil, "message": "ok"}
		if g.noInstall {
			install = map[string]any{"available": false, "reason": "engine_unreachable", "message": "Install at the box."}
		}
		jsonOut(w, 200, map[string]any{"install": install,
			"nodes": []any{
				map[string]any{"node_id": "hub1", "available_version": "0.2.0", "current_version": "0.1.0", "reported": true},
				map[string]any{"node_id": "idle", "available_version": nil, "current_version": "0.1.0", "reported": true},
			}})
	case p == "/v1/actions" && r.Method == http.MethodPost:
		jsonOut(w, 201, waiting(str(body["type"]), body["params"]))
	default:
		jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no such resource " + p})
	}
}

func asOwner(t *testing.T) *recGW {
	isolate(t)
	g := newRecGW(t)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return g
}

func mustJSON2(t *testing.T, s string) any {
	t.Helper()
	var v any
	if err := json.Unmarshal([]byte(s), &v); err != nil {
		t.Fatalf("not JSON: %v\n%s", err, s)
	}
	return v
}

func TestUsersListInviteDisable(t *testing.T) {
	g := asOwner(t)
	r := run(t, "", false, "users", "list")
	if r.code != 0 || !strings.Contains(r.out, "Mia") || !strings.Contains(r.out, "invited") || !strings.Contains(r.out, "disabled") || !strings.Contains(r.out, "active") {
		t.Fatalf("list %+v", r)
	}
	if r := run(t, "", false, "users", "list", "--json"); r.code != 0 || len(mustJSON2(t, r.out).([]any)) != 3 {
		t.Fatalf("list json %+v", r)
	}
	r = run(t, "", false, "users", "invite", "Sam", "--role", "child", "--username", "sam")
	if r.code != 0 || !strings.Contains(r.out, "Invited Sam") || !strings.Contains(r.out, "#enrol=CODE") {
		t.Fatalf("invite %+v", r)
	}
	post := g.requests("POST", "/v1/users")
	if len(post) != 1 || post[0].body["display_name"] != "Sam" || post[0].body["role"] != "child" || post[0].body["username"] != "sam" {
		t.Fatalf("invite body %+v", post)
	}
	r = run(t, "", false, "users", "invite", "Sam", "--json")
	if r.code != 0 {
		t.Fatalf("invite json %+v", r)
	}
	invite := obj(mustJSON2(t, r.out))
	if invite["id"] != "usr_9" || invite["role"] != "adult" || obj(invite["one_time"])["enrolment_code"] != "CODE" {
		t.Fatalf("unexpected invitation: %+v", invite)
	}
	if r := run(t, "", false, "users", "invite", "Sam", "--quiet"); r.code != 0 || r.out != "https://box.example/signin#enrol=CODE\n" {
		t.Fatalf("invite quiet %+v", r)
	}
	if r := run(t, "", false, "users", "invite", "Alex", "--role", "owner", "--quiet"); r.code != 0 ||
		r.out != "https://box.example/signin#enrol=CODE\n" {
		t.Fatalf("invite another owner %+v", r)
	}
	// Disabling needs --yes, and files nothing without it.
	if r := run(t, "", false, "users", "disable", "usr_2"); r.code != ExitUsage || len(g.requests("POST", "/v1/users/usr_2/disable")) != 0 {
		t.Fatalf("disable without --yes %+v", r)
	}
	if r := run(t, "", false, "users", "disable", "usr_2", "--yes", "--json"); r.code != 0 || obj(mustJSON2(t, r.out))["disabled"] != true {
		t.Fatalf("disable %+v", r)
	}
}

func TestUsersAgentTokenIsRefusedByTheGateway(t *testing.T) {
	asOwner(t)
	t.Setenv("ONEMIND_TOKEN", agentTok)
	for _, args := range [][]string{
		{"users", "list"}, {"users", "invite", "X"}, {"users", "reinvite", "usr_2", "--yes"},
		{"care", "checkup"}, {"update", "policy", "set", "--cool-off-hours", "1"},
	} {
		if r := run(t, "", false, args...); r.code != ExitPermissionDenied {
			t.Errorf("%v: exit %d, want %d (%s)", args, r.code, ExitPermissionDenied, r.errOut)
		}
	}
}

func TestUsersInviteAnotherOwnerExplainsPasskeyStepUp(t *testing.T) {
	g := asOwner(t)
	g.stepUp = true
	r := run(t, "", false, "users", "invite", "Sam", "--role", "owner")
	if r.code != ExitUnauthenticated || !strings.Contains(r.errOut, "passkey") || !strings.Contains(r.errOut, "dashboard") {
		t.Fatalf("%+v", r)
	}
}

func TestBackupReadsAndRequestsWaitForAnOwner(t *testing.T) {
	g := asOwner(t)
	if r := run(t, "", false, "backup", "status"); r.code != 0 || !strings.Contains(r.out, "2026-11-25T02:00:00Z") || !strings.Contains(r.out, "confirmed") {
		t.Fatalf("status %+v", r)
	}
	if r := run(t, "", false, "backup", "snapshots", "--app", "photos"); r.code != 0 || !strings.Contains(r.out, "abcd1234") {
		t.Fatalf("snapshots %+v", r)
	}
	if q := g.requests("GET", "/v1/backups/snapshots"); len(q) != 1 || q[0].query != "app_id=photos" {
		t.Fatalf("snapshots query %+v", q)
	}
	if r := run(t, "", false, "backup", "snapshots", "--app", "nodest"); r.code != 0 || !strings.Contains(r.out, "No snapshots yet") || strings.Contains(r.out, "SNAPSHOT") {
		t.Fatalf("empty snapshots %+v", r)
	}

	if r := run(t, "", false, "backup", "run"); r.code != 0 || !strings.Contains(r.out, "onemind actions approve act_1") {
		t.Fatalf("run %+v", r)
	}
	if r := run(t, "", false, "backup", "run", "--app", "photos", "--destination", "dst_0123456789abcdef", "--reason", "before upgrade", "--json"); r.code != 0 {
		t.Fatalf("run app %+v", r)
	}
	runs := g.requests("POST", "/v1/backups/runs")
	if len(runs) != 2 || runs[0].body["scope"] != "box" || obj(runs[1].body["scope"])["app_id"] != "photos" ||
		runs[1].body["destination_id"] != "dst_0123456789abcdef" || runs[1].body["reason"] != "before upgrade" {
		t.Fatalf("run bodies %+v", runs)
	}
	if r := run(t, "", false, "backup", "verify", "--mode", "check", "--json"); r.code != 0 {
		t.Fatalf("verify %+v", r)
	}
	if v := g.requests("POST", "/v1/backups/verify"); len(v) != 1 || v[0].body["mode"] != "check" || v[0].body["latest"] != true {
		t.Fatalf("verify body %+v", v)
	}
	if r := run(t, "", false, "backup", "verify", "--mode", "bogus"); r.code != ExitUsage {
		t.Fatalf("bad mode %+v", r)
	}

	if r := run(t, "", false, "backup", "restore", "abcd1234", "--app", "photos", "--path", "/data/p", "--json"); r.code != 0 {
		t.Fatalf("restore %+v", r)
	}
	rs := g.requests("POST", "/v1/restores")
	sc := obj(rs[0].body["scope"])
	if len(rs) != 1 || rs[0].body["snapshot_id"] != "abcd1234" || sc["app_id"] != "photos" || sc["path"] != "/data/p" || rs[0].body["target"] != "in_place" {
		t.Fatalf("restore body %+v", rs)
	}
	if r := run(t, "", false, "backup", "restore", "abcd1234"); r.code != ExitUsage {
		t.Fatalf("restore without --app %+v", r)
	}
	if r := run(t, "", false, "backup", "restore", "abcd1234", "--app", "photos", "--path", "rel"); r.code != ExitUsage {
		t.Fatalf("relative path %+v", r)
	}
	// Nothing here ever approves, and no body carries the owner shortcut.
	g.mu.Lock()
	defer g.mu.Unlock()
	for _, x := range g.log {
		if strings.Contains(x.path, "/approve") || x.body["approve"] != nil {
			t.Fatalf("the CLI approved something: %+v", x)
		}
	}
}

func TestCareCheckup(t *testing.T) {
	asOwner(t)
	r := run(t, "", false, "care", "checkup")
	if r.code != 0 || !strings.Contains(r.out, "No backup in 3 days.") || !strings.Contains(r.out, "onemind backup run") {
		t.Fatalf("%+v", r)
	}
	if r := run(t, "", false, "care", "checkup", "--json"); r.code != 0 || len(mustJSON2(t, r.out).([]any)) != 2 {
		t.Fatalf("json %+v", r)
	}
}

func TestUpdatePolicyShowAndSetKeepsTheRest(t *testing.T) {
	g := asOwner(t)
	if r := run(t, "", false, "update", "policy", "show"); r.code != 0 || !strings.Contains(r.out, "win_nightly") || !strings.Contains(r.out, "48") {
		t.Fatalf("show %+v", r)
	}
	if r := run(t, "", false, "update", "policy", "show", "--json"); r.code != 0 || obj(mustJSON2(t, r.out))["cool_off_hours"] != float64(48) {
		t.Fatalf("show json %+v", r)
	}
	if r := run(t, "", false, "update", "policy", "set"); r.code != ExitUsage {
		t.Fatalf("set with nothing %+v", r)
	}
	if r := run(t, "", false, "update", "policy", "set", "--cool-off-hours", "72", "--same-major-only=false"); r.code != 0 || !strings.Contains(r.out, "saved") {
		t.Fatalf("set %+v", r)
	}
	put := g.requests("PUT", "/v1/update-policy")
	if len(put) != 1 {
		t.Fatalf("puts %+v", put)
	}
	b := put[0].body
	// Changed flags change; everything else, the AI schedule included, is what the box already had.
	if b["cool_off_hours"] != float64(72) || b["same_major_only"] != false || b["window_id"] != "win_nightly" ||
		b["backoff_after_failures"] != float64(3) || obj(b["ai_schedule"])["enabled"] != true || len(b) != 5 {
		t.Fatalf("put body %+v", b)
	}
	if r := run(t, "", false, "update", "policy", "set", "--window", "win_x", "--json"); r.code != 0 || obj(mustJSON2(t, r.out))["window_id"] != "win_x" {
		t.Fatalf("set json %+v", r)
	}
}

func TestUpdateApplyFilesAnApprovalInsteadOfActingAsRoot(t *testing.T) {
	g := asOwner(t)
	r := run(t, "", false, "update", "apply")
	if r.code != 0 || !strings.Contains(r.out, "onemind actions approve act_1") || strings.Contains(r.errOut, "BREAK-GLASS") {
		t.Fatalf("apply %+v", r)
	}
	acts := g.requests("POST", "/v1/actions")
	if len(acts) != 1 || acts[0].body["type"] != "os.update.install" ||
		obj(acts[0].body["params"])["node_id"] != "hub1" || obj(acts[0].body["params"])["version"] != "0.2.0" {
		t.Fatalf("action %+v", acts)
	}
	if r := run(t, "", false, "update", "apply", "--json"); r.code != 0 || obj(mustJSON2(t, r.out))["state"] != "awaiting_approval" {
		t.Fatalf("json %+v", r)
	}
	// A retry is a replay: the same node and version give the same idempotency key.
	if acts := g.requests("POST", "/v1/actions"); len(acts) != 2 || acts[0].body["idempotency_key"] != acts[1].body["idempotency_key"] {
		t.Fatalf("retry made a different key: %+v", acts)
	}
	// No update on offer, an unknown node, and local-only flags without --local are refused before filing.
	n := len(g.requests("POST", "/v1/actions"))
	for _, args := range [][]string{{"--node", "idle"}, {"--node", "ghost"}, {"--no-reboot"}, {"--mirror", "/mnt/usb"}} {
		if r := run(t, "", false, append([]string{"update", "apply"}, args...)...); r.code == 0 {
			t.Errorf("%v accepted", args)
		}
	}
	if got := len(g.requests("POST", "/v1/actions")); got != n {
		t.Fatalf("filed %d extra actions", got-n)
	}
	// An explicit version is only forwarded: the real gateway refuses one the node does not offer.
	if r := run(t, "", false, "update", "apply", "--node", "idle", "--target-version", "0.3.0"); r.code != 0 {
		t.Fatalf("explicit version %+v", r)
	}
}

func TestUpdateApplyWithNoHostServiceFilesNothingAndSaysWhatWorks(t *testing.T) {
	g := asOwner(t)
	g.noInstall = true
	r := run(t, "", false, "update", "apply")
	if r.code != ExitConflict || len(g.requests("POST", "/v1/actions")) != 0 {
		t.Fatalf("apply %+v", r)
	}
	for _, want := range []string{"cannot run an approved install", "update apply --local", "Nothing was filed"} {
		if !strings.Contains(r.errOut, want) {
			t.Errorf("message lacks %q: %s", want, r.errOut)
		}
	}
}

func TestRepeatOfAFinishedActionSaysNothingWasFiled(t *testing.T) {
	g := asOwner(t)
	g.replayState = "succeeded"
	for _, args := range [][]string{{"backup", "run"}, {"backup", "restore", "abcd1234", "--app", "photos"}, {"update", "apply"}} {
		r := run(t, "", false, args...)
		if r.code != ExitConflict || !strings.Contains(r.errOut, "already succeeded, nothing filed") || strings.Contains(r.out, "Waiting for an owner") {
			t.Errorf("%v: %+v", args, r)
		}
	}
	// --json still prints the stored action, and the exit code still tells scripts nothing new was filed.
	if r := run(t, "", false, "backup", "run", "--json"); r.code != ExitConflict || obj(mustJSON2(t, r.out))["state"] != "succeeded" {
		t.Errorf("json: %+v", r)
	}
	g.replayState = "awaiting_approval"
	if r := run(t, "", false, "backup", "run"); r.code != 0 || !strings.Contains(r.out, "Waiting for an owner") {
		t.Errorf("waiting: %+v", r)
	}
}

func TestIdempotencyConflictIsExplainedInPlainWords(t *testing.T) {
	g := asOwner(t)
	g.conflict = true
	for _, args := range [][]string{{"backup", "restore", "abcd1234", "--app", "photos"}, {"update", "apply"}} {
		r := run(t, "", false, args...)
		if r.code != ExitConflict || !strings.Contains(r.errOut, "will not file it twice") {
			t.Errorf("%v: %+v", args, r)
		}
	}
}

func TestBackupRunAndVerifyUseAFreshKeyEachTime(t *testing.T) {
	g := asOwner(t)
	for _, c := range []struct {
		path string
		args []string
	}{{"/v1/backups/runs", []string{"backup", "run", "--app", "photos"}}, {"/v1/backups/verify", []string{"backup", "verify"}}} {
		run(t, "", false, c.args...)
		run(t, "", false, c.args...)
		got := g.requests("POST", c.path)
		if len(got) != 2 || got[0].idem == "" || got[0].idem == got[1].idem {
			t.Errorf("%s: keys %+v", c.path, got)
		}
	}
}

func TestRestoreSendsAStableIdempotencyKey(t *testing.T) {
	g := asOwner(t)
	args := []string{"backup", "restore", "abcd1234", "--app", "photos"}
	for _, extra := range [][]string{nil, {"--reason", "again"}} {
		if r := run(t, "", false, append(append([]string{}, args...), extra...)...); r.code != 0 {
			t.Fatalf("%+v", r)
		}
	}
	got := g.requests("POST", "/v1/restores")
	if len(got) != 2 || got[0].idem == "" || got[0].idem != got[1].idem {
		t.Fatalf("keys %+v", got)
	}
	run(t, "", false, "backup", "restore", "abcd1234", "--app", "notes")
	if got := g.requests("POST", "/v1/restores"); got[0].idem == got[2].idem {
		t.Fatal("different apps shared a key")
	}
}

func TestUpdateApplyLocalIsLabelledBreakGlass(t *testing.T) {
	g := asOwner(t)
	conf := t.TempDir() + "/missing.conf" // the engine stops at the config; the label comes first
	r := run(t, "", false, "update", "apply", "--local", "--config", conf)
	if r.code == 0 || !strings.Contains(r.errOut, "BREAK-GLASS") || len(g.requests("POST", "/v1/actions")) != 0 {
		t.Fatalf("--local %+v", r)
	}
	if r := run(t, "", false, "update", "apply", "--local", "--node", "hub1", "--config", conf); r.code != ExitUsage {
		t.Fatalf("--local with --node %+v", r)
	}
	// With no box selected and no --local there is no fallback to root: apply refuses.
	t.Setenv("ONEMIND_HUB", "")
	r = run(t, "", false, "update", "apply", "--config", conf)
	if r.code != ExitUsage || strings.Contains(r.errOut, "installing on this machine") {
		t.Fatalf("no box, no --local %+v", r)
	}
	// --node with no box must not install locally either.
	r = run(t, "", false, "update", "apply", "--node", "hub1", "--config", conf)
	if r.code != ExitUsage || strings.Contains(r.errOut, "installing on this machine") {
		t.Fatalf("no box, --node %+v", r)
	}
	// --local with no box is the explicit break-glass path.
	if r := run(t, "", false, "update", "apply", "--local", "--config", conf); r.code == 0 || !strings.Contains(r.errOut, "BREAK-GLASS") {
		t.Fatalf("--local, no box %+v", r)
	}
}

func TestUpdatePolicySetSkipsAISchedulePolicyWhenAbsent(t *testing.T) {
	g := asOwner(t)
	g.noAISchedule = true
	if r := run(t, "", false, "update", "policy", "set", "--cool-off-hours", "5"); r.code != 0 {
		t.Fatalf("set %+v", r)
	}
	put := g.requests("PUT", "/v1/update-policy")
	if len(put) != 1 {
		t.Fatalf("puts %+v", put)
	}
	if _, has := put[0].body["ai_schedule"]; has {
		t.Fatalf("ai_schedule sent as %v", put[0].body["ai_schedule"])
	}
}
