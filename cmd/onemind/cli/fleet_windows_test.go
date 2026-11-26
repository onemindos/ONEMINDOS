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

// fleetRecGW is a recorded gateway for the fleet, rollout and window commands: canned answers shaped
// like the real ones (core/onemind_core/routers/rollouts.py and automation.py) and a log of requests.
type fleetRecGW struct {
	mu  sync.Mutex
	log []rec
	// stepUp makes a PUT answer the passkey step-up error.
	stepUp bool
}

func newFleetRecGW(t *testing.T, serve func(g *fleetRecGW, w http.ResponseWriter, r *http.Request, body map[string]any)) *fleetRecGW {
	g := &fleetRecGW{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		g.mu.Lock()
		defer g.mu.Unlock()
		var body map[string]any
		if raw, _ := io.ReadAll(r.Body); len(raw) > 0 {
			_ = json.Unmarshal(raw, &body)
		}
		g.log = append(g.log, rec{r.Method, r.URL.Path, r.URL.RawQuery, body, r.Header.Get("Idempotency-Key")})
		serve(g, w, r, body)
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	return g
}

func (g *fleetRecGW) requests(method, path string) []rec {
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

func fleetGW(t *testing.T, token string) *fleetRecGW {
	isolate(t)
	t.Setenv("ONEMIND_TOKEN", token)
	owner := token == ownerTok
	return newFleetRecGW(t, func(g *fleetRecGW, w http.ResponseWriter, r *http.Request, body map[string]any) {
		deny := func() bool {
			if !owner {
				jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "only an owner may do this"})
			}
			return !owner
		}
		switch p := r.URL.Path; {
		case p == "/v1/os/fleet":
			jsonOut(w, 200, map[string]any{"machines": []any{
				map[string]any{"node_id": "n1", "hostname": "hub", "board": "x86_64-efi", "status": "online", "version": "1.2.0", "update_state": "idle", "available_version": "1.3.0"},
				map[string]any{"node_id": "n2", "hostname": "pi", "board": "rpi5", "status": "stale", "version": nil, "update_state": nil, "available_version": nil}},
				"versions": []any{map[string]any{"version": "1.2.0", "count": 1}, map[string]any{"version": "unknown", "count": 1}}, "active_rollout_id": "rol_aaaaaaaaaaaaaaaaaaaaaaaaaa"})
		case p == "/v1/os/rollouts":
			jsonOut(w, 200, []any{map[string]any{"id": "rol_a", "version": "1.3.0", "state": "paused", "stage": 1, "stages": []any{10.0, 50.0, 100.0}, "reason": "a machine rolled back"}})
		case p == "/v1/os/rollouts/rol_a":
			jsonOut(w, 200, map[string]any{"id": "rol_a", "version": "1.3.0", "state": "paused", "stage": 1, "stages": []any{10.0, 100.0}, "reason": nil,
				"nodes": []any{map[string]any{"node_id": "n1", "wave": 0, "state": "failed", "reason": "rolled back"}}})
		case p == "/v1/os/rollouts/rol_a/cancel":
			if deny() {
				return
			}
			jsonOut(w, 200, map[string]any{"id": "rol_a", "state": "cancelled"})
		case p == "/v1/actions":
			jsonOut(w, 201, map[string]any{"id": "act_9", "type": body["type"], "params": body["params"], "state": "awaiting_approval"})
		case p == "/v1/windows" && r.Method == http.MethodGet:
			jsonOut(w, 200, []any{map[string]any{"id": "win_nightly", "name": "Nightly", "tz": "box", "open_now": true,
				"ranges": []any{map[string]any{"days": []any{"mon", "tue"}, "start": "22:00", "end": "06:00"}, map[string]any{"start": "01:00", "end": "02:00"}}}})
		case p == "/v1/windows/win_nightly" && r.Method == http.MethodPut:
			if deny() {
				return
			}
			if g.stepUp {
				jsonOut(w, 401, map[string]string{"error": "unauthenticated", "reason": "step_up_required", "message": "sign in again with your passkey to do this"})
				return
			}
			jsonOut(w, 200, map[string]any{"id": "win_nightly", "name": body["name"]})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": p})
		}
	})
}

func TestUpdateFleetAndRolloutReads(t *testing.T) {
	fleetGW(t, ownerTok)
	r := run(t, "", false, "update", "fleet")
	if r.code != 0 || !strings.Contains(r.out, "1.3.0") || !strings.Contains(r.out, "Rollout in progress") || !strings.Contains(r.out, "unknown x1") {
		t.Fatalf("fleet %+v", r)
	}
	if r := run(t, "", false, "update", "rollouts", "list"); r.code != 0 || !strings.Contains(r.out, "2 of 3") || !strings.Contains(r.out, "a machine rolled back") {
		t.Fatalf("list %+v", r)
	}
	if r := run(t, "", false, "update", "rollouts", "show", "rol_a"); r.code != 0 || !strings.Contains(r.out, "rolled back") {
		t.Fatalf("show %+v", r)
	}
	if r := run(t, "", false, "update", "rollouts", "list", "--json"); r.code != 0 || len(mustJSON2(t, r.out).([]any)) != 1 {
		t.Fatalf("json %+v", r)
	}
}

func TestRolloutStartAndResumeOnlyFileRequests(t *testing.T) {
	g := fleetGW(t, ownerTok)
	r := run(t, "", false, "update", "rollouts", "start", "--target-version", "1.3.0", "--stages", "10,100", "--max-failures", "1")
	if r.code != 0 || !strings.Contains(r.out, "Waiting for an owner") {
		t.Fatalf("start %+v", r)
	}
	post := g.requests("POST", "/v1/actions")
	p := obj(post[0].body["params"])
	if len(post) != 1 || post[0].body["type"] != "os.rollout.start" || p["version"] != "1.3.0" || len(list(p["stages"])) != 2 || post[0].idem == "" {
		t.Fatalf("body %+v", post)
	}
	if r := run(t, "", false, "update", "rollouts", "resume", "rol_a"); r.code != 0 || !strings.Contains(r.out, "Waiting for an owner") {
		t.Fatalf("resume %+v", r)
	}
	if got := g.requests("POST", "/v1/actions"); got[1].body["type"] != "os.rollout.resume" {
		t.Fatalf("resume body %+v", got)
	}
	for _, c := range g.log {
		if strings.Contains(c.path, "approve") {
			t.Fatalf("a rollout command must never approve: %+v", c)
		}
	}
	if r := run(t, "", false, "update", "rollouts", "start"); r.code != ExitUsage {
		t.Fatalf("missing version %+v", r)
	}
	if r := run(t, "", false, "update", "rollouts", "start", "--target-version", "1", "--stages", "a"); r.code != ExitUsage {
		t.Fatalf("bad stages %+v", r)
	}
}

func TestRolloutCancelIsOwnerOnly(t *testing.T) {
	fleetGW(t, ownerTok)
	if r := run(t, "", false, "update", "rollouts", "cancel", "rol_a"); r.code != 0 || !strings.Contains(r.out, "already updated stay updated") {
		t.Fatalf("owner %+v", r)
	}
	fleetGW(t, agentTok)
	if r := run(t, "", false, "update", "rollouts", "cancel", "rol_a"); r.code == 0 || !strings.Contains(r.errOut, "only an owner") {
		t.Fatalf("agent %+v", r)
	}
}

func TestWindowsListAndSet(t *testing.T) {
	g := fleetGW(t, ownerTok)
	if r := run(t, "", false, "windows", "list"); r.code != 0 || !strings.Contains(r.out, "open now") || !strings.Contains(r.out, "mon,tue 22:00-06:00") || !strings.Contains(r.out, "every day 01:00-02:00") {
		t.Fatalf("list %+v", r)
	}
	r := run(t, "", false, "windows", "set", "win_nightly", "--name", "Night", "--range", "mon,tue 22:00-06:00", "--range", "01:00-02:00")
	if r.code != 0 || !strings.Contains(r.out, "Saved win_nightly") {
		t.Fatalf("set %+v", r)
	}
	put := g.requests("PUT", "/v1/windows/win_nightly")
	rs := list(put[0].body["ranges"])
	if len(put) != 1 || put[0].body["tz"] != "box" || len(rs) != 2 || obj(rs[0])["start"] != "22:00" || len(list(obj(rs[0])["days"])) != 2 || obj(rs[1])["days"] != nil {
		t.Fatalf("body %+v", put)
	}
	for _, bad := range [][]string{{"windows", "set", "nightly", "--name", "x", "--range", "22:00-06:00"}, {"windows", "set", "win_a", "--name", "x"}, {"windows", "set", "win_a", "--name", "x", "--range", "late"}} {
		if r := run(t, "", false, bad...); r.code != ExitUsage {
			t.Fatalf("%v: %+v", bad, r)
		}
	}
}

func TestWindowsSetExplainsStepUpAndRefusesAgents(t *testing.T) {
	g := fleetGW(t, ownerTok)
	g.stepUp = true
	r := run(t, "", false, "windows", "set", "win_nightly", "--name", "N", "--range", "22:00-06:00")
	if r.code == 0 || !strings.Contains(r.errOut, "passkey") || !strings.Contains(r.errOut, "dashboard") {
		t.Fatalf("step-up %+v", r)
	}
	fleetGW(t, agentTok)
	if r := run(t, "", false, "windows", "set", "win_nightly", "--name", "N", "--range", "22:00-06:00"); r.code == 0 || !strings.Contains(r.errOut, "only an owner") {
		t.Fatalf("agent %+v", r)
	}
}
