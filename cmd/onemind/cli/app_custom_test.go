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

// customGW answers the custom-app routes and leaves every other path to the shared fake gateway.
type customGW struct {
	*fakeGW
	srv      *httptest.Server
	mu       sync.Mutex
	calls    []string
	bodies   []map[string]any
	verdict  string
	whoCanDo string
}

func newCustomGW(t *testing.T) *customGW {
	g := &customGW{fakeGW: newFakeGW(t), verdict: "ready", whoCanDo: ownerTok}
	g.srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/v1/custom-apps") {
			g.fakeGW.serve(w, r)
			return
		}
		g.mu.Lock()
		defer g.mu.Unlock()
		raw, _ := io.ReadAll(r.Body)
		var body map[string]any
		_ = json.Unmarshal(raw, &body)
		g.calls = append(g.calls, r.Method+" "+r.URL.Path)
		g.bodies = append(g.bodies, body)
		if r.Header.Get("Authorization") != "Bearer "+g.whoCanDo && r.Method == http.MethodPost {
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "agent/agent may not plan a custom app"})
			return
		}
		switch {
		case r.URL.Path == "/v1/custom-apps/plan":
			plan := map[string]any{"app_id": "ntfy", "name": "ntfy", "version": "1.0.0", "revision": 3, "commit": strings.Repeat("a", 40),
				"verdict": g.verdict, "action_type": "app.install", "problems": []string{}, "notes": []string{"A Containerfile is in the repository"},
				"scan":      map[string]any{"result": "pass"},
				"signature": map[string]any{"policy": "undecided", "status": "not_checked", "detail": "No signing policy for custom apps is decided yet."}}
			if g.verdict != "ready" {
				plan["action_type"], plan["problems"] = nil, []string{"F-01 Deployment/x: spec.hostNetwork is not allowed"}
			}
			jsonOut(w, 200, plan)
		case strings.HasSuffix(r.URL.Path, "/rollback"):
			jsonOut(w, 200, map[string]any{"app_id": "kuma", "from_revision": 3, "to_revision": 2, "commit": strings.Repeat("b", 40), "action_type": "app.update"})
		default:
			jsonOut(w, 200, map[string]any{"app_id": "kuma", "revisions": []any{
				map[string]any{"revision": 3, "commit": strings.Repeat("a", 40), "version": "1.2.0", "scan": map[string]any{"result": "pass"}, "deployed": true, "deployed_at": "2026-11-25T10:00:00Z"},
				map[string]any{"revision": 2, "commit": strings.Repeat("b", 40), "version": "1.1.0", "scan": map[string]any{"result": "pass"}, "deployed_at": "2026-11-24T10:00:00Z"}}})
		}
	}))
	t.Cleanup(g.srv.Close)
	return g
}

func (g *customGW) env(t *testing.T, token string) {
	isolate(t)
	t.Setenv("ONEMIND_HUB", g.srv.URL)
	t.Setenv("ONEMIND_TOKEN", token)
}

func TestAppDeployPlansThenFilesTheInstallRequest(t *testing.T) {
	g := newCustomGW(t)
	g.env(t, ownerTok)
	r := run(t, "", false, "app", "deploy", "--git", "https://git.example.org/me/ntfy", "--ref", "main", "--no-approve", "--json")
	var act map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &act) != nil || act["state"] != "awaiting_approval" || act["type"] != "app.install" {
		t.Fatalf("deploy %+v", r)
	}
	if g.bodies[0]["url"] != "https://git.example.org/me/ntfy" || g.bodies[0]["ref"] != "main" {
		t.Fatalf("plan body %v", g.bodies[0])
	}
	if !strings.Contains(r.errOut, "revision 3") || !strings.Contains(r.errOut, "Signature: not_checked (undecided)") || !strings.Contains(r.errOut, "Containerfile") {
		t.Fatalf("plan not shown: %s", r.errOut)
	}
	// Planned, and only requested: nothing is approved by the deploy itself.
	for _, a := range g.actions {
		if a["state"] != "awaiting_approval" {
			t.Fatalf("approved without being asked: %v", a)
		}
	}
	// The owner at a terminal answers no: still waiting (exit 9).
	if r := run(t, "n\n", true, "app", "deploy", "--git", "https://git.example.org/me/ntfy", "--ref", "v1"); r.code != ExitPending || !strings.Contains(r.out, "Planned ntfy") {
		t.Fatalf("declined %+v", r)
	}
}

func TestAppDeployRefusesBeforeAnyRequest(t *testing.T) {
	g := newCustomGW(t)
	g.env(t, ownerTok)
	for _, u := range []string{"http://git.example.org/r", "https://user:" + "x" + "@git.example.org/r", "https://git.example.org/r?x=1", "ssh://git.example.org/r"} {
		if r := run(t, "", false, "app", "deploy", "--git", u, "--ref", "main", "--no-approve"); r.code != ExitUsage {
			t.Fatalf("%s accepted: %+v", u, r)
		}
	}
	if r := run(t, "", false, "app", "deploy", "--git", "https://git.example.org/r", "--ref", "main"); r.code != ExitUsage {
		t.Fatalf("no tty %+v", r)
	}
	if r := run(t, "", false, "app", "deploy", "--git", "https://git.example.org/r"); r.code == 0 || !strings.Contains(r.errOut, "ref") {
		t.Fatalf("ref is required %+v", r)
	}
	if len(g.calls) != 0 || len(g.actions) != 0 {
		t.Fatalf("something was sent: %v %v", g.calls, g.actions)
	}
}

func TestAppDeployBlockedByTheChecksFilesNothing(t *testing.T) {
	g := newCustomGW(t)
	g.verdict = "blocked"
	g.env(t, ownerTok)
	r := run(t, "", false, "app", "deploy", "--git", "https://git.example.org/me/ntfy", "--ref", "main", "--no-approve")
	if r.code != ExitVerifyFailed || !strings.Contains(r.errOut, "F-01") || len(g.actions) != 0 {
		t.Fatalf("blocked %+v", r)
	}
}

func TestAppDeployByAnAgentIsRefused(t *testing.T) {
	g := newCustomGW(t)
	g.env(t, agentTok)
	r := run(t, "", false, "app", "deploy", "--git", "https://git.example.org/me/ntfy", "--ref", "main", "--no-approve")
	if r.code != ExitPermissionDenied || len(g.actions) != 0 {
		t.Fatalf("agent %+v", r)
	}
}

func TestAppRollbackFilesAnUpdateAndHistoryListsRevisions(t *testing.T) {
	g := newCustomGW(t)
	g.env(t, ownerTok)
	r := run(t, "", false, "app", "rollback", "kuma", "--revision", "2", "--no-approve", "--json")
	var act map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &act) != nil || act["type"] != "app.update" || act["state"] != "awaiting_approval" {
		t.Fatalf("rollback %+v", r)
	}
	if g.bodies[0]["revision"] != float64(2) {
		t.Fatalf("revision not sent: %v", g.bodies[0])
	}
	if r := run(t, "", false, "app", "rollback", "kuma"); r.code != ExitUsage {
		t.Fatalf("no tty %+v", r)
	}
	h := run(t, "", false, "app", "history", "kuma")
	if h.code != 0 || !strings.Contains(h.out, "running") || !strings.Contains(h.out, "1.1.0") || !strings.Contains(h.out, strings.Repeat("b", 12)) {
		t.Fatalf("history %+v", h)
	}
}
