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

// contentGW is a recorded gateway for backup content and verifications.
type contentGW struct {
	mu  sync.Mutex
	log []rec
}

func newContentGW(t *testing.T, token string) *contentGW {
	isolate(t)
	t.Setenv("ONEMIND_TOKEN", token)
	g := &contentGW{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		g.mu.Lock()
		defer g.mu.Unlock()
		var body map[string]any
		if raw, _ := io.ReadAll(r.Body); len(raw) > 0 {
			_ = json.Unmarshal(raw, &body)
		}
		g.log = append(g.log, rec{r.Method, r.URL.Path, r.URL.RawQuery, body, r.Header.Get("Idempotency-Key")})
		switch {
		case r.URL.Path == "/v1/backups/verifications":
			jsonOut(w, 200, []any{map[string]any{"id": "v1", "snapshot_id": "abcdef123456", "unit": "app:photos", "mode": "scratch_restore", "result": "pass", "finished_at": "2026-11-25T03:00:00Z"},
				map[string]any{"id": "v2", "snapshot_id": "99", "unit": "box", "mode": "check", "result": "fail", "finished_at": nil}})
		case r.URL.Path == "/v1/backups/content" && r.Method == http.MethodGet:
			jsonOut(w, 200, []any{map[string]any{"app_id": "jellyfin", "name": "Jellyfin", "enabled": false, "size_bytes": 4.2e9, "files": 1200.0},
				map[string]any{"app_id": "ollama", "enabled": true, "size_bytes": nil, "files": nil}})
		case r.URL.Path == "/v1/backups/content" && r.Method == http.MethodPost:
			if token != ownerTok {
				jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "agent/agent may not do this"})
				return
			}
			jsonOut(w, 202, map[string]any{"id": "act_5", "type": "backup.content.set", "params": body, "state": "awaiting_approval"})
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	}))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	return g
}

func (g *contentGW) posts() []rec {
	g.mu.Lock()
	defer g.mu.Unlock()
	var out []rec
	for _, r := range g.log {
		if r.method == http.MethodPost {
			out = append(out, r)
		}
	}
	return out
}

func TestBackupVerificationsAndContentReads(t *testing.T) {
	g := newContentGW(t, ownerTok)
	r := run(t, "", false, "backup", "verifications")
	if r.code != 0 || !strings.Contains(r.out, "restore test") || !strings.Contains(r.out, "fail") || !strings.Contains(r.out, "app:photos") {
		t.Fatalf("verifications %+v", r)
	}
	if r := run(t, "", false, "backup", "verifications", "--json"); r.code != 0 || len(mustJSON2(t, r.out).([]any)) != 2 {
		t.Fatalf("json %+v", r)
	}
	r = run(t, "", false, "backup", "content", "list")
	if r.code != 0 || !strings.Contains(r.out, "4.2 GB") || !strings.Contains(r.out, "included") || !strings.Contains(r.out, "not measured") {
		t.Fatalf("content list %+v", r)
	}
	if len(g.posts()) != 0 {
		t.Fatalf("reads must not write: %+v", g.posts())
	}
}

func TestBackupContentIncludeSendsTheSizeShownAndOnlyFilesARequest(t *testing.T) {
	g := newContentGW(t, ownerTok)
	r := run(t, "", false, "backup", "content", "set", "jellyfin", "--include")
	if r.code != 0 || !strings.Contains(r.out, "4.2 GB") || !strings.Contains(r.out, "Waiting for an owner") {
		t.Fatalf("include %+v", r)
	}
	p := g.posts()
	if len(p) != 1 || p[0].body["app_id"] != "jellyfin" || p[0].body["enabled"] != true || p[0].body["seen_size_bytes"] != 4.2e9 || p[0].body["approve"] != nil || p[0].idem == "" {
		t.Fatalf("body %+v", p)
	}
	if r := run(t, "", false, "backup", "content", "set", "jellyfin", "--leave-out"); r.code != 0 {
		t.Fatalf("leave out %+v", r)
	}
	if p := g.posts(); len(p) != 2 || p[1].body["enabled"] != false || p[1].body["seen_size_bytes"] != nil {
		t.Fatalf("leave-out body %+v", p)
	}
	for _, args := range [][]string{{"backup", "content", "set", "jellyfin"}, {"backup", "content", "set", "jellyfin", "--include", "--leave-out"}} {
		if r := run(t, "", false, args...); r.code != ExitUsage {
			t.Fatalf("%v: %+v", args, r)
		}
	}
	if r := run(t, "", false, "backup", "content", "set", "ollama", "--include"); r.code != ExitNotFound {
		t.Fatalf("unmeasured %+v", r)
	}
}

func TestBackupContentSetIsRefusedForAnAgent(t *testing.T) {
	newContentGW(t, agentTok)
	if r := run(t, "", false, "backup", "content", "set", "jellyfin", "--leave-out"); r.code == 0 || !strings.Contains(r.errOut, "may not do this") {
		t.Fatalf("agent %+v", r)
	}
}
