// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/spf13/cobra"
)

const ownerTok = "owner-token-0123456789abcdef"
const agentTok = "agent-token-0123456789abcdef"

// fakeGW is just enough of the gateway for the CLI: instance, nodes, apps, actions, audit, /mcp.
type fakeGW struct {
	mu      sync.Mutex
	actions map[string]map[string]any
	n       int
	srv     *httptest.Server
}

func newFakeGW(t *testing.T) *fakeGW {
	g := &fakeGW{actions: map[string]map[string]any{}}
	g.srv = httptest.NewServer(http.HandlerFunc(g.serve))
	t.Cleanup(g.srv.Close)
	return g
}

func jsonOut(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func (g *fakeGW) serve(w http.ResponseWriter, r *http.Request) {
	g.mu.Lock()
	defer g.mu.Unlock()
	who := map[string]string{"Bearer " + ownerTok: "owner", "Bearer " + agentTok: "hermes"}[r.Header.Get("Authorization")]
	if who == "" {
		jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "unknown token"})
		return
	}
	p := r.URL.Path
	switch {
	case p == "/mcp":
		if who != "hermes" {
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "agents only"})
			return
		}
		var m map[string]any
		_ = json.NewDecoder(r.Body).Decode(&m)
		if _, ok := m["id"]; !ok {
			w.WriteHeader(202)
			return
		}
		res := map[string]any{}
		if m["method"] == "initialize" {
			res = map[string]any{"protocolVersion": "2025-06-18", "serverInfo": map[string]any{"version": "0.1.0"}}
		} else if m["method"] == "tools/list" {
			res = map[string]any{"tools": []any{map[string]any{"name": "list_nodes"}, map[string]any{"name": "request_action"}}}
		}
		jsonOut(w, 200, map[string]any{"jsonrpc": "2.0", "id": m["id"], "result": res})
	case p == "/v1/instance":
		jsonOut(w, 200, map[string]any{"name": "Test \x1b[31mBox", "version": "0.1.0", "hub_node_id": "abc"})
	case p == "/v1/nodes":
		jsonOut(w, 200, []any{map[string]any{"node_id": "abc", "hostname": "hub", "status": "online", "last_seen": "2026-11-12T09:00:00Z", "zeta": 1, "alpha": 2}})
	case p == "/v1/apps":
		jsonOut(w, 200, []any{
			map[string]any{"id": "ntfy", "name": "ntfy", "version": "2.14.0", "category": "tools", "installed": false, "status": "not_installed", "archs": []string{"amd64"}, "requires": map[string]any{}, "links": map[string]any{}, "license": "Apache-2.0", "scan": map[string]any{"result": "pass", "scanned_at": "2026-11-11T09:00:00Z"}},
			map[string]any{"id": "kuma", "name": "Uptime Kuma", "version": "1.0", "category": "monitoring", "installed": true, "status": "installed", "archs": []string{"amd64"}, "requires": map[string]any{}, "links": map[string]any{}},
		})
	case p == "/v1/actions" && r.Method == http.MethodPost:
		var b map[string]any
		_ = json.NewDecoder(r.Body).Decode(&b)
		g.n++
		id := fmt.Sprintf("act-%d", g.n)
		a := map[string]any{"id": id, "type": b["type"], "params": b["params"], "state": "awaiting_approval",
			"requested_by": map[string]any{"id": who, "kind": map[string]string{"owner": "person", "hermes": "agent"}[who]},
			"idempotency_key": b["idempotency_key"], "created_at": "2026-11-12T09:00:00Z", "updated_at": "t",
			"expires_at": b["expires_at"], "decided_by": nil, "decided_at": nil, "result": nil, "version": 1}
		g.actions[id] = a
		jsonOut(w, 201, a)
	case p == "/v1/actions":
		out := []any{}
		for _, a := range g.actions {
			out = append(out, a)
		}
		jsonOut(w, 200, out)
	case strings.HasPrefix(p, "/v1/actions/"):
		parts := strings.Split(strings.TrimPrefix(p, "/v1/actions/"), "/")
		a, ok := g.actions[parts[0]]
		if !ok {
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no such action"})
			return
		}
		if len(parts) == 2 {
			if who != "owner" {
				jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "agent/agent may not approve action"})
				return
			}
			a["decided_by"] = map[string]any{"id": "owner", "kind": "person", "role": "owner"}
			a["state"] = map[string]string{"approve": "succeeded", "deny": "cancelled"}[parts[1]]
		}
		jsonOut(w, 200, a)
	case p == "/v1/audit/events":
		raw, _ := os.ReadFile(filepath.Join("..", "..", "..", "sdk", "testdata", "audit", "good.jsonl"))
		var out []json.RawMessage
		for _, l := range strings.Split(strings.TrimSpace(string(raw)), "\n") {
			out = append(out, json.RawMessage(l))
		}
		if r.URL.Query().Get("event") == "action.requested" {
			out = out[1:2]
		}
		jsonOut(w, 200, out)
	case p == "/v1/audit/verify":
		jsonOut(w, 200, map[string]any{"ok": true, "records": 3, "head": nil, "first_bad_seq": nil, "reason": "ok", "checked_at": "t", "last_checkpoint": nil})
	default:
		jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no such resource"})
	}
}

type result struct {
	code        int
	out, errOut string
}

func run(t *testing.T, stdin string, tty bool, args ...string) result {
	t.Helper()
	var out, errb bytes.Buffer
	code := Run(args, Env{Stdout: &out, Stderr: &errb, Stdin: strings.NewReader(stdin), Interactive: func() bool { return tty }})
	return result{code, out.String(), errb.String()}
}

func isolate(t *testing.T) string {
	dir := t.TempDir()
	t.Setenv("XDG_CONFIG_HOME", dir)
	for _, k := range []string{"ONEMIND_HUB", "ONEMIND_TOKEN", "ONEMIND_CONTEXT", "ONEMIND_CONFIG"} {
		t.Setenv(k, "")
	}
	return dir
}

func TestUsageAndUnknownCommands(t *testing.T) {
	isolate(t)
	for _, args := range [][]string{nil, {"apps"}, {"apps", "nope"}, {"nodez"}, {"nodes", "--bogus"}, {"update"}} {
		r := run(t, "", false, args...)
		if r.code != ExitUsage || !strings.Contains(r.errOut, "Usage:") {
			t.Errorf("%v: exit %d stderr %q", args, r.code, r.errOut)
		}
	}
	if r := run(t, "", false, "version", "extra"); r.code != 0 || !strings.HasPrefix(r.out, "onemind ") {
		t.Fatalf("version %+v", r)
	}
	if r := run(t, "", false, "nodes"); r.code != ExitUsage || !strings.Contains(r.errOut, "onemind login") {
		t.Fatalf("no hub: %+v", r)
	}
}

func TestEveryCommandHasHelpAndJSONFlag(t *testing.T) {
	root, _ := NewRoot(Env{Stdout: io.Discard, Stderr: io.Discard})
	var walk func(c *cobra.Command)
	walk = func(c *cobra.Command) {
		if c.Short == "" && c.Name() != "onemind" {
			t.Errorf("%s has no help text", c.CommandPath())
		}
		if c.Flags().Lookup("json") == nil && c.InheritedFlags().Lookup("json") == nil && c.Name() != "onemind" {
			t.Errorf("%s has no --json", c.CommandPath())
		}
		for _, s := range c.Commands() {
			walk(s)
		}
	}
	walk(root)
}

func TestLoginContextsAndConfigModes(t *testing.T) {
	dir := isolate(t)
	g := newFakeGW(t)
	r := run(t, ownerTok+"\n", false, "login", "--hub", g.srv.URL, "--token-stdin", "--name", "home", "--principal", "owner")
	if r.code != 0 || !strings.Contains(r.out, "Saved:") || strings.Contains(r.out, "\x1b") {
		t.Fatalf("login %+v", r)
	}
	for _, f := range []string{"config.yaml", "credentials.yaml"} {
		st, err := os.Stat(filepath.Join(dir, "onemind", f))
		if err != nil || st.Mode().Perm() != 0o600 {
			t.Fatalf("%s: %v %v", f, err, st)
		}
	}
	cfg, _ := os.ReadFile(filepath.Join(dir, "onemind", "config.yaml"))
	if strings.Contains(string(cfg), ownerTok) {
		t.Fatal("config holds the token")
	}
	if r := run(t, "", false, "nodes", "--json"); r.code != 0 || !strings.Contains(r.out, `"alpha": 2`) {
		t.Fatalf("nodes via context %+v", r)
	}
	if r := run(t, "", false, "context", "list"); !strings.Contains(r.out, "*        home") {
		t.Fatalf("context list %q", r.out)
	}
	if r := run(t, "", false, "context", "rename", "home", "box"); r.code != 0 {
		t.Fatal(r)
	}
	if r := run(t, "", false, "--context", "home", "nodes"); r.code != ExitNotFound {
		t.Fatalf("old name: %+v", r)
	}
	if r := run(t, "", false, "status", "--json"); r.code != 0 || !strings.Contains(r.out, `"onemind.cli.status/v1"`) {
		t.Fatalf("status %+v", r)
	}
	if r := run(t, "", false, "logout"); r.code != 0 {
		t.Fatal(r)
	}
	if r := run(t, "", false, "nodes"); r.code != ExitUnauthenticated {
		t.Fatalf("after logout: %+v", r)
	}
	if r := run(t, "", false, "login", "--hub", g.srv.URL); r.code != ExitUsage || !strings.Contains(r.errOut, "--token-stdin") {
		t.Fatalf("login without tty: %+v", r)
	}
}

func TestJSONErrorsGoToStderrOnly(t *testing.T) {
	isolate(t)
	g := newFakeGW(t)
	t.Setenv("ONEMIND_TOKEN", "nope-nope-nope-nope")
	r := run(t, "", false, "--hub", g.srv.URL, "--json", "apps", "list")
	if r.code != ExitUnauthenticated || r.out != "" {
		t.Fatalf("%+v", r)
	}
	var e map[string]any
	if err := json.Unmarshal([]byte(r.errOut), &e); err != nil || e["error"] != "unauthenticated" || e["exit_code"] != float64(3) {
		t.Fatalf("stderr %q", r.errOut)
	}
}

func TestAppsAndTheApprovalFlow(t *testing.T) {
	isolate(t)
	g := newFakeGW(t)
	t.Setenv("ONEMIND_HUB", g.srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	if r := run(t, "", false, "apps", "list", "--installed"); r.code != 0 || !strings.Contains(r.out, "kuma") || strings.Contains(r.out, "ntfy") {
		t.Fatalf("list %+v", r)
	}
	if r := run(t, "", false, "apps", "info", "nope"); r.code != ExitNotFound {
		t.Fatalf("info %+v", r)
	}
	// No TTY and neither --no-approve nor --yes: refuse before filing anything.
	if r := run(t, "", false, "apps", "install", "ntfy"); r.code != ExitUsage || len(g.actions) != 0 {
		t.Fatalf("no tty %+v", r)
	}
	r := run(t, "", false, "apps", "install", "ntfy", "--no-approve", "--json")
	var a map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &a) != nil || a["state"] != "awaiting_approval" {
		t.Fatalf("no-approve %+v", r)
	}
	// TTY, answer no: stays pending (exit 9).
	if r := run(t, "n\n", true, "apps", "install", "ntfy"); r.code != ExitPending {
		t.Fatalf("declined %+v", r)
	}
	// TTY, answer yes: approved and followed to the end.
	if r := run(t, "y\n", true, "apps", "install", "ntfy"); r.code != 0 || !strings.Contains(r.out, "succeeded") {
		t.Fatalf("approved %+v", r)
	}
	// Removal wants the app id typed.
	if r := run(t, "y\n", true, "apps", "remove", "kuma"); r.code != ExitPending {
		t.Fatalf("remove with y %+v", r)
	}
	if r := run(t, "kuma\n", true, "apps", "remove", "kuma"); r.code != 0 {
		t.Fatalf("remove typed %+v", r)
	}
	// An agent token can request but the owner step is refused (exit 4) with a hint.
	t.Setenv("ONEMIND_TOKEN", agentTok)
	if r := run(t, "", false, "apps", "install", "ntfy", "--yes"); r.code != ExitPermissionDenied || !strings.Contains(r.errOut, "actions approve") {
		t.Fatalf("agent %+v", r)
	}
}

func TestActionsListApproveDeny(t *testing.T) {
	isolate(t)
	g := newFakeGW(t)
	t.Setenv("ONEMIND_HUB", g.srv.URL)
	t.Setenv("ONEMIND_TOKEN", agentTok)
	run(t, "", false, "apps", "install", "ntfy", "--no-approve")
	run(t, "", false, "apps", "install", "kuma", "--no-approve")
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	r := run(t, "", false, "actions", "list", "--pending")
	if r.code != 0 || strings.Count(r.out, "agent:hermes") != 2 {
		t.Fatalf("list %+v", r)
	}
	if r := run(t, "", false, "actions", "approve", "act-1"); r.code != ExitUsage || !strings.Contains(r.errOut, "--yes") {
		t.Fatalf("approve without tty %+v", r)
	}
	r = run(t, "", false, "actions", "approve", "act-1", "--yes")
	if r.code != 0 || !strings.Contains(r.out, "untrusted") || !strings.Contains(r.out, "Owner asked for phone alerts") {
		t.Fatalf("approve %+v", r)
	}
	if r := run(t, "", false, "actions", "approve", "act-1", "--yes"); r.code != ExitConflict {
		t.Fatalf("second approve %+v", r)
	}
	if r := run(t, "", false, "actions", "deny", "act-2", "--yes", "--json"); r.code != 0 || !strings.Contains(r.out, `"cancelled"`) {
		t.Fatalf("deny %+v", r)
	}
	if r := run(t, "", false, "actions", "info", "nope"); r.code != ExitNotFound {
		t.Fatalf("info %+v", r)
	}
}

func TestAuditVerifyFileAndRemote(t *testing.T) {
	isolate(t)
	vec := filepath.Join("..", "..", "..", "sdk", "testdata", "audit")
	if r := run(t, "", false, "audit", "verify", "--file", filepath.Join(vec, "good.jsonl")); r.code != 0 || !strings.Contains(r.out, "3 entries · chain ok") {
		t.Fatalf("good %+v", r)
	}
	r := run(t, "", false, "audit", "verify", "--file", filepath.Join(vec, "tampered.jsonl"))
	if r.code != ExitVerifyFailed || !strings.Contains(r.out, "FAIL at seq 2") {
		t.Fatalf("tampered %+v", r)
	}
	g := newFakeGW(t)
	t.Setenv("ONEMIND_HUB", g.srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	if r := run(t, "", false, "audit", "verify"); r.code != 0 || !strings.Contains(r.out, "chain ok") {
		t.Fatalf("remote %+v", r)
	}
	if r := run(t, "", false, "audit", "tail", "-n", "2"); r.code != 0 || strings.Count(strings.TrimSpace(r.out), "\n") != 1 {
		t.Fatalf("tail %+v", r)
	}
}

func TestMCPHelpers(t *testing.T) {
	isolate(t)
	g := newFakeGW(t)
	if r := run(t, ownerTok+"\n", false, "mcp", "login", "--hub", g.srv.URL, "--token-stdin"); r.code != ExitPermissionDenied {
		t.Fatalf("owner token as agent %+v", r)
	}
	if r := run(t, agentTok+"\n", false, "mcp", "login", "--hub", g.srv.URL, "--token-stdin", "--name", "laptop"); r.code != 0 {
		t.Fatalf("mcp login %+v", r)
	}
	r := run(t, "", false, "mcp", "doctor")
	if r.code != 0 || !strings.Contains(r.out, "2025-06-18") || !strings.Contains(r.out, "list_nodes request_action") {
		t.Fatalf("doctor %+v", r)
	}
	r = run(t, "", false, "mcp", "config", "claude-desktop")
	if r.code != 0 || !strings.Contains(r.out, `"--context"`) || strings.Contains(r.out, agentTok) {
		t.Fatalf("config %+v", r)
	}
	in := `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}` + "\n" + `{"jsonrpc":"2.0","method":"notifications/initialized"}` + "\n"
	r = run(t, in, false, "mcp")
	if r.code != 0 || strings.Count(r.out, "\n") != 1 || !strings.Contains(r.out, `"protocolVersion":"2025-06-18"`) || strings.Contains(r.errOut, agentTok) {
		t.Fatalf("bridge %+v", r)
	}
}

func TestCompletionAndSanitize(t *testing.T) {
	isolate(t)
	for _, sh := range []string{"bash", "zsh", "fish", "powershell"} {
		if r := run(t, "", false, "completion", sh); r.code != 0 || !strings.Contains(r.out, "onemind") {
			t.Errorf("%s: %+v", sh, r.code)
		}
	}
	if got := sanitize("ok\x1b[2J\x1b]0;evil\x07‮\x07done\n"); got != "okdone\n" {
		t.Fatalf("sanitize %q", got)
	}
}
