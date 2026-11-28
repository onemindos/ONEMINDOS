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

// areaGW is a recorded gateway for the search and radios commands: answers shaped like the real
// ones, a log of every request, and a 403 for any token that is not the owner's.
type areaGW struct {
	mu   sync.Mutex
	log  []rec
	hits []any
}

func newAreaGW(t *testing.T, serve func(g *areaGW, w http.ResponseWriter, r *http.Request, body map[string]any)) *areaGW {
	g := &areaGW{}
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

func (g *areaGW) requests(method, path string) []rec {
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

func radioCard(confirmed bool) map[string]any {
	return map[string]any{"id": "abc.lora0", "node_id": "abc", "node_status": "online", "hostname": "garage", "kind": "lora", "model": "T-Beam",
		"confirm": map[string]any{"profile": "meshcore-companion-usb", "label": "MeshCore companion (USB)", "confirmed": confirmed, "confirmed_at": nil}}
}

func TestSearchPrintsHitsAndSendsTheWordsOnce(t *testing.T) {
	isolate(t)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	g := newAreaGW(t, func(g *areaGW, w http.ResponseWriter, r *http.Request, _ map[string]any) {
		jsonOut(w, 200, g.hits)
	})
	g.hits = []any{map[string]any{"provider": "files", "app_id": "files", "type": "file", "id": "1", "title": "Tax 2025.pdf", "subtitle": nil, "link": "onemind://app/files/browse/Documents"}}
	r := run(t, "", false, "search", "tax", "2025", "--types", "file")
	if r.code != 0 || !strings.Contains(r.out, "Tax 2025.pdf") || !strings.Contains(r.out, "onemind://app/files") {
		t.Fatalf("search %+v", r)
	}
	got := g.requests("GET", "/v1/search")
	if len(got) != 1 || !strings.Contains(got[0].query, "q=tax+2025") || !strings.Contains(got[0].query, "types=file") || !strings.Contains(got[0].query, "limit=20") {
		t.Fatalf("query %+v", got)
	}
	if r := run(t, "", false, "search", "tax", "--json"); r.code != 0 || len(mustJSON2(t, r.out).([]any)) != 1 {
		t.Fatalf("json %+v", r)
	}
	g.hits = []any{}
	if r := run(t, "", false, "search", "zzz"); r.code != 0 || !strings.Contains(r.out, "Nothing found") {
		t.Fatalf("empty %+v", r)
	}
	if r := run(t, "", false, "search", "x", "--limit", "500"); r.code != ExitUsage {
		t.Fatalf("limit %+v", r)
	}
}

func TestRadiosListAndConfirmUsesTheCardsOwnProfile(t *testing.T) {
	isolate(t)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	state := false
	g := newAreaGW(t, func(g *areaGW, w http.ResponseWriter, r *http.Request, body map[string]any) {
		switch {
		case r.URL.Path == "/v1/radios":
			jsonOut(w, 200, []any{radioCard(state)})
		case r.URL.Path == "/v1/radios/abc.lora0/confirm" && r.Method == http.MethodPost:
			state = true
			jsonOut(w, 200, radioCard(true))
		default:
			jsonOut(w, 404, map[string]string{"error": "not_found", "message": r.URL.Path})
		}
	})
	if r := run(t, "", false, "radios", "list"); r.code != 0 || !strings.Contains(r.out, "not confirmed") || !strings.Contains(r.out, "garage") {
		t.Fatalf("list %+v", r)
	}
	r := run(t, "", false, "radios", "confirm", "abc.lora0")
	if r.code != 0 || !strings.Contains(r.out, "MeshCore companion (USB)") {
		t.Fatalf("confirm %+v", r)
	}
	post := g.requests("POST", "/v1/radios/abc.lora0/confirm")
	if len(post) != 1 || post[0].body["profile"] != "meshcore-companion-usb" {
		t.Fatalf("body %+v", post)
	}
	if r := run(t, "", false, "radios", "list"); !strings.Contains(r.out, "confirmed as MeshCore companion (USB)") {
		t.Fatalf("after %+v", r)
	}
	if r := run(t, "", false, "radios", "confirm", "nope.lora1"); r.code != ExitNotFound {
		t.Fatalf("unknown radio %+v", r)
	}
}

func TestRadiosConfirmIsRefusedForAnAgentToken(t *testing.T) {
	isolate(t)
	t.Setenv("ONEMIND_TOKEN", agentTok)
	g := newAreaGW(t, func(g *areaGW, w http.ResponseWriter, r *http.Request, _ map[string]any) {
		if r.Method == http.MethodPost {
			jsonOut(w, 403, map[string]string{"error": "permission_denied", "message": "only an owner may confirm a radio"})
			return
		}
		jsonOut(w, 200, []any{radioCard(false)})
	})
	r := run(t, "", false, "radios", "confirm", "abc.lora0")
	if r.code == 0 || !strings.Contains(r.errOut, "only an owner") {
		t.Fatalf("agent must be refused: %+v", r)
	}
	if len(g.requests("POST", "/v1/radios/abc.lora0/confirm")) != 1 {
		t.Fatalf("exactly one attempt expected")
	}
}
