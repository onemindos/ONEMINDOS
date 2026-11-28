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

type abHub struct {
	mu    sync.Mutex
	calls []string
	posts []map[string]any
	idem  []string
}

func startAgentBrowserHub(t *testing.T) *abHub {
	t.Helper()
	isolate(t)
	h := &abHub{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h.mu.Lock()
		defer h.mu.Unlock()
		if r.Header.Get("Authorization") != "Bearer "+ownerTok {
			jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "no"})
			return
		}
		h.calls = append(h.calls, r.Method+" "+r.URL.Path)
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/v1/agent-browser/sites":
			jsonOut(w, 200, []any{map[string]any{"id": "s1", "agent": "hermes", "entry": "*.example.org", "approved_by": "owner", "created_at": "2026-11-26T12:00:00Z"}})
		case r.Method == http.MethodGet && r.URL.Path == "/v1/agent-browser/sessions":
			jsonOut(w, 200, []any{map[string]any{"id": "b1", "agent": "hermes", "state": "running", "pages": 2, "max_pages": 20, "expires_at": "2026-11-26T13:00:00Z"}})
		case r.Method == http.MethodPost && r.URL.Path == "/v1/agent-browser/sites":
			b, _ := io.ReadAll(r.Body)
			var in map[string]any
			_ = json.Unmarshal(b, &in)
			h.posts = append(h.posts, in)
			h.idem = append(h.idem, r.Header.Get("Idempotency-Key"))
			jsonOut(w, 201, map[string]any{"id": "act-9", "state": "awaiting_approval"})
		case r.Method == http.MethodDelete && r.URL.Path == "/v1/agent-browser/sites/s1":
			jsonOut(w, 200, map[string]any{"removed": true, "id": "s1"})
		case r.Method == http.MethodDelete && r.URL.Path == "/v1/agent-browser/sessions/b1":
			jsonOut(w, 200, map[string]any{"id": "b1", "state": "ended"})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return h
}

func TestAgentBrowserLists(t *testing.T) {
	startAgentBrowserHub(t)
	r := run(t, "", false, "agent-browser", "sites", "list")
	if r.code != 0 || !strings.Contains(r.out, "*.example.org") || !strings.Contains(r.out, "hermes") {
		t.Fatalf("sites list %+v", r)
	}
	r = run(t, "", false, "agent-browser", "sessions", "list")
	if r.code != 0 || !strings.Contains(r.out, "2/20") || !strings.Contains(r.out, "running") {
		t.Fatalf("sessions list %+v", r)
	}
	r = run(t, "", false, "agent-browser", "sites", "list", "--json")
	var v []map[string]any
	if r.code != 0 || json.Unmarshal([]byte(r.out), &v) != nil || len(v) != 1 {
		t.Fatalf("--json prints the gateway's list: %+v", r)
	}
}

func TestAgentBrowserRequestOnlyFilesARequest(t *testing.T) {
	h := startAgentBrowserHub(t)
	r := run(t, "", false, "agent-browser", "sites", "request", "docs.example.org", "--agent", "hermes", "--note", "reading docs")
	if r.code != 0 || !strings.Contains(r.out, "act-9") || !strings.Contains(r.out, "Waiting for an owner") {
		t.Fatalf("request %+v", r)
	}
	if len(h.posts) != 1 || h.posts[0]["entry"] != "docs.example.org" || h.posts[0]["agent"] != "hermes" || h.posts[0]["note"] != "reading docs" {
		t.Fatalf("body %+v", h.posts)
	}
	if !strings.HasPrefix(h.idem[0], "cli-agent-browser-site-") {
		t.Fatalf("a stable Idempotency-Key replays the same request: %q", h.idem[0])
	}
	for _, c := range h.calls {
		if strings.Contains(c, "/approve") {
			t.Fatalf("the CLI must never approve: %v", h.calls)
		}
	}
}

func TestAgentBrowserRequestNeedsAnAgent(t *testing.T) {
	h := startAgentBrowserHub(t)
	r := run(t, "", false, "agent-browser", "sites", "request", "docs.example.org")
	if r.code == 0 || len(h.posts) != 0 {
		t.Fatalf("no --agent must fail before any call: %+v", r)
	}
}

func TestAgentBrowserRemoveAndEnd(t *testing.T) {
	h := startAgentBrowserHub(t)
	if r := run(t, "", false, "agent-browser", "sites", "remove", "s1"); r.code != 0 || !strings.Contains(r.out, "Removed site s1") {
		t.Fatalf("remove %+v", r)
	}
	if r := run(t, "", false, "agent-browser", "sessions", "end", "b1"); r.code != 0 || !strings.Contains(r.out, "Ended session b1") {
		t.Fatalf("end %+v", r)
	}
	if r := run(t, "", false, "agent-browser", "sites", "remove", "nope"); r.code == 0 {
		t.Fatalf("an unknown site is an error: %+v", r)
	}
	_ = h
}
