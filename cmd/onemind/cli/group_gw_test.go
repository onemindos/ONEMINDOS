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

// routeGW is a small recorded gateway for one command group: each test names the routes it needs
// ("GET /v1/tokens") and what they answer, and the gateway logs every request, so a test can prove what
// was sent and, above all, that the CLI never approved anything.
type routeGW struct {
	mu     sync.Mutex
	routes map[string]func(body map[string]any) (int, any)
	log    []rec
	hdrs   []http.Header // the request headers of log[i]
	cur    *http.Request // the request being answered (a handler may read its headers)
}

// withHeaders lets a route answer with response headers (ETag, Link): return it as the body.
type withHeaders struct {
	body    any
	headers map[string]string
}

func newRouteGW(t *testing.T, routes map[string]func(body map[string]any) (int, any)) *routeGW {
	t.Helper()
	isolate(t)
	g := &routeGW{routes: routes}
	srv := httptest.NewServer(http.HandlerFunc(g.serve))
	t.Cleanup(srv.Close)
	t.Setenv("ONEMIND_HUB", srv.URL)
	t.Setenv("ONEMIND_TOKEN", ownerTok)
	return g
}

func (g *routeGW) serve(w http.ResponseWriter, r *http.Request) {
	g.mu.Lock()
	defer g.mu.Unlock()
	var body map[string]any
	if raw, _ := io.ReadAll(r.Body); len(raw) > 0 {
		_ = json.Unmarshal(raw, &body)
	}
	g.log = append(g.log, rec{r.Method, r.URL.Path, r.URL.RawQuery, body, r.Header.Get("Idempotency-Key")})
	g.hdrs = append(g.hdrs, r.Header.Clone())
	g.cur = r
	if r.Header.Get("Authorization") != "Bearer "+ownerTok {
		jsonOut(w, 401, map[string]string{"error": "unauthenticated", "message": "unknown token"})
		return
	}
	h, ok := g.routes[r.Method+" "+r.URL.Path]
	if !ok {
		jsonOut(w, 404, map[string]string{"error": "not_found", "message": "no such resource " + r.URL.Path})
		return
	}
	status, v := h(body)
	if wh, ok := v.(withHeaders); ok {
		for k, hv := range wh.headers {
			w.Header().Set(k, hv)
		}
		v = wh.body
	}
	if status == http.StatusNoContent {
		w.WriteHeader(status)
		return
	}
	jsonOut(w, status, v)
}

func (g *routeGW) sent(method, path string) []rec {
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

// header is a request header of every call to method+path, in order.
func (g *routeGW) header(method, path, name string) []string {
	g.mu.Lock()
	defer g.mu.Unlock()
	var out []string
	for i, r := range g.log {
		if r.method == method && r.path == path {
			out = append(out, g.hdrs[i].Get(name))
		}
	}
	return out
}

// neverApproved fails the test if the CLI called any approve route.
func (g *routeGW) neverApproved(t *testing.T) {
	t.Helper()
	g.mu.Lock()
	defer g.mu.Unlock()
	for _, r := range g.log {
		if strings.Contains(r.path, "/approve") {
			t.Fatalf("the CLI approved something: %s %s", r.method, r.path)
		}
		if b, ok := r.body["approve"]; ok && b == true {
			t.Fatalf("the CLI sent the approve shortcut: %s %s", r.method, r.path)
		}
	}
}

func ok(v any) func(map[string]any) (int, any) {
	return func(map[string]any) (int, any) { return 200, v }
}

func waitingAction(map[string]any) (int, any) {
	return 202, map[string]any{"id": "act_7", "state": "awaiting_approval"}
}

// jsonOf parses command output as JSON.
func jsonOf(t *testing.T, s string) any {
	t.Helper()
	var v any
	if err := json.Unmarshal([]byte(s), &v); err != nil {
		t.Fatalf("not JSON: %v\n%s", err, s)
	}
	return v
}

func outHas(t *testing.T, out string, want ...string) {
	t.Helper()
	for _, w := range want {
		if !strings.Contains(out, w) {
			t.Fatalf("output lacks %q:\n%s", w, out)
		}
	}
}
